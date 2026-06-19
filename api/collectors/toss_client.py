"""toss_client — 토스증권 Open API 클라이언트 (시세·캔들, 읽기 전용).

2026-06-20 신설. 토스 Open API GA(개인 키). 실측 검증:
  · OAuth2 client_credentials → JWT, expires_in≈86400s(24h), **자유 재발급**(3회 연속 200) = KIS 1일1토큰 제약 없음.
  · IP allowlist 필수(403 "IP address not allowed" 실측) → 호출 IP를 토스 콘솔 등록 필요.
    🚨 프로덕션 = 고정 egress IP(Railway Pro/static proxy) 등록 필요. 동적 IP(서버리스/핫스팟) 불가.
  · base https://openapi.tossinvest.com · GET /api/v1/prices(symbols) · /api/v1/candles(symbol,interval,count).
  · 🚨 키에 주문 권한 포함 — 본 클라이언트는 시세/캔들 read-only만. 주문 endpoint 절대 미구현. 키=서버 전용.

토큰 캐시 = ~/.cache/verity_toss_token.json (🚨 data/ 발행 경로엔 절대 안 씀 — 토큰 유출 방지).
KIS 무관(RULE1 별개). 출력 캔들 = {date:YYYYMMDD, open, high, low, close, volume} 오름차순 (=/api/chart daily 호환).
"""
from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Optional

import requests

_BASE = "https://openapi.tossinvest.com"
_TOKEN_CACHE = os.path.expanduser("~/.cache/verity_toss_token.json")
_token: Optional[str] = None
_token_exp: float = 0.0


def _keys() -> tuple[str, str]:
    k = os.environ.get("TOSS_API_KEY") or ""
    s = os.environ.get("TOSS_SECRET_KEY") or ""
    if k and s:
        return k, s
    # 로컬 fallback: .env 파싱 (프로덕션은 환경변수 주입)
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    envp = os.path.join(root, ".env")
    if os.path.isfile(envp):
        for line in open(envp, encoding="utf-8"):
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                kk, _, vv = line.partition("=")
                vv = vv.strip().strip('"').strip("'")
                if kk.strip() == "TOSS_API_KEY":
                    k = k or vv
                elif kk.strip() == "TOSS_SECRET_KEY":
                    s = s or vv
    return k, s


def _load_cached() -> None:
    global _token, _token_exp
    if _token and time.time() < _token_exp:
        return
    try:
        with open(_TOKEN_CACHE, encoding="utf-8") as f:
            d = json.load(f)
        if d.get("access_token") and float(d.get("expires_ts", 0)) > time.time() + 60:
            _token = d["access_token"]
            _token_exp = float(d["expires_ts"])
    except (OSError, json.JSONDecodeError, ValueError):
        pass


def get_token() -> Optional[str]:
    """OAuth2 토큰 (캐시 우선, 만료 시 재발급 — 자유 재발급 가능)."""
    global _token, _token_exp
    if _token and time.time() < _token_exp:
        return _token
    _load_cached()
    if _token and time.time() < _token_exp:
        return _token
    k, s = _keys()
    if not k or not s:
        return None
    try:
        r = requests.post(_BASE + "/oauth2/token",
                          data={"grant_type": "client_credentials", "client_id": k, "client_secret": s},
                          timeout=15)
        if r.status_code != 200:
            return None
        j = r.json()
        _token = j.get("access_token")
        _token_exp = time.time() + float(j.get("expires_in", 3600)) - 120
        try:
            os.makedirs(os.path.dirname(_TOKEN_CACHE), exist_ok=True)
            with open(_TOKEN_CACHE, "w", encoding="utf-8") as f:
                json.dump({"access_token": _token, "expires_ts": _token_exp}, f)
        except OSError:
            pass
        return _token
    except Exception:  # noqa: BLE001
        return None


def _headers() -> Optional[Dict[str, str]]:
    t = get_token()
    return {"Authorization": "Bearer " + t} if t else None


def get_prices(symbols: List[str]) -> Dict[str, Dict[str, Any]]:
    """현재가 — {symbol: {price, timestamp, currency}}. read-only."""
    h = _headers()
    if not h or not symbols:
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    try:
        r = requests.get(_BASE + "/api/v1/prices", params={"symbols": ",".join(symbols[:200])}, headers=h, timeout=15)
        if r.status_code != 200:
            return {}
        for it in (r.json().get("result") or []):
            sym = str(it.get("symbol") or "")
            if sym:
                out[sym] = {"price": _f(it.get("lastPrice")), "timestamp": it.get("timestamp"), "currency": it.get("currency")}
    except Exception:  # noqa: BLE001
        return {}
    return out


def get_candles(symbol: str, interval: str = "1d", count: int = 100) -> List[Dict[str, Any]]:
    """일/분봉 → [{date:YYYYMMDD, open, high, low, close, volume}] 오름차순(=/api/chart daily 호환)."""
    h = _headers()
    if not h or not symbol:
        return []
    try:
        r = requests.get(_BASE + "/api/v1/candles",
                         params={"symbol": symbol, "interval": interval, "count": min(max(count, 1), 200)},
                         headers=h, timeout=15)
        if r.status_code != 200:
            return []
        rows = (r.json().get("result") or {}).get("candles") or []
    except Exception:  # noqa: BLE001
        return []
    out = []
    for c in rows:
        ts = str(c.get("timestamp") or "")  # 2026-06-19T00:00:00.000+09:00
        date = ts[:10].replace("-", "") if len(ts) >= 10 else ""
        if not date:
            continue
        out.append({
            "date": date,
            "open": _f(c.get("openPrice")), "high": _f(c.get("highPrice")),
            "low": _f(c.get("lowPrice")), "close": _f(c.get("closePrice")),
            "volume": _f(c.get("volume")),
        })
    out.sort(key=lambda x: x["date"])  # 오름차순
    return out


def _f(v: Any) -> float:
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return 0.0


if __name__ == "__main__":
    import sys
    print("[toss] token:", "OK" if get_token() else "FAIL", file=sys.stderr)
    print("[toss] prices:", get_prices(["005930", "000660"]), file=sys.stderr)
    cs = get_candles("005930", "1d", 3)
    print(f"[toss] candles: {len(cs)} → {cs}", file=sys.stderr)
