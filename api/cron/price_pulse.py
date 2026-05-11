"""
가격 펄스 — 1~2분 cron 으로 KOSPI/KOSDAQ/NDX/SPX + 보유 + 추천 종목 가격만 갱신.

설계 의도 (2026-05-11 사용자 결정):
- main.py 의 무거운 import (4m50s) + STEP 0 자가진단 (3m41s) 회피
- 핵심 가격만 ~30초 안에 fetch + 저장
- output = data/price_pulse.json (portfolio.json 과 별도 파일, race 없음)
- Vercel API 가 portfolio + price_pulse merge 해서 사이트 노출

light import 만 — yfinance / pandas / pykrx 의도적으로 import 안 함 (각 1~5초 startup).
사용:
- KIS get_current_price (KR 종목)
- yahoo finance raw HTTP (US 종목 + 지수)
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from typing import Any

KST = timezone(timedelta(hours=9))

# 프로젝트 root 경로 — repo root 에서 실행 가정
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

_DATA = os.path.join(_ROOT, "data")
_PORTFOLIO = os.path.join(_DATA, "portfolio.json")
_RECS = os.path.join(_DATA, "recommendations.json")
_OUT = os.path.join(_DATA, "price_pulse.json")

# 지수 yahoo 심볼
_INDEX_SYMBOLS = {
    "kospi": "^KS11",
    "kosdaq": "^KQ11",
    "sp500": "^GSPC",
    "nasdaq": "^IXIC",
    "dow": "^DJI",
    "vix": "^VIX",
    "usdkrw": "KRW=X",
}


def _now_iso() -> str:
    return datetime.now(KST).strftime("%Y-%m-%dT%H:%M:%S+09:00")


def _load_json(path: str, default: Any) -> Any:
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def fetch_yahoo_quotes(symbols: list[str]) -> dict:
    """yfinance.Tickers batch fetch — yahoo raw API 가 401 인증 요구라 yfinance 경유.

    반환: {symbol: {price, change_pct}}
    """
    if not symbols:
        return {}
    try:
        import yfinance as yf  # ~2~3s startup, lazy
    except Exception as e:
        print(f"[pulse] yfinance import 실패: {e}")
        return {}

    out: dict = {}
    try:
        tk = yf.Tickers(" ".join(symbols))
        for sym in symbols:
            try:
                info = tk.tickers[sym].fast_info
                price = info.get("last_price") or info.get("lastPrice")
                prev = info.get("previous_close") or info.get("previousClose")
                if price is None:
                    continue
                change_pct = None
                if prev and prev > 0:
                    change_pct = round((price - prev) / prev * 100, 2)
                out[sym] = {"price": float(price), "change_pct": change_pct}
            except Exception:
                continue
    except Exception as e:
        print(f"[pulse] yfinance batch 실패: {e}")
    return out


def fetch_kis_prices(kr_tickers: list[str]) -> dict:
    """KIS API 로 KR 종목 가격. broker import 는 호출 시점에 lazy.

    반환: {ticker(6자리): price_int}
    """
    if not kr_tickers:
        return {}
    try:
        from api.trading.kis_broker import KISBroker
    except Exception as e:
        print(f"[pulse] KIS broker import 실패: {e}")
        return {}
    try:
        broker = KISBroker()
        if not getattr(broker, "is_configured", False):
            print("[pulse] KIS 미설정 — KR 가격 skip (env KIS_APP_KEY/KIS_APP_SECRET 확인)")
            return {}
        # token 확보 — 캐시 hit 시 즉시, 없으면 daily lock 우회 시도. 실패 시 첫 호출 fail.
        try:
            tok = broker.authenticate(force_refresh=False)
            print(f"[pulse] KIS token OK ({len(tok) if tok else 0}자)")
        except Exception as e:
            print(f"[pulse] KIS authenticate 실패: {e}")
    except Exception as e:
        print(f"[pulse] KIS broker init 실패: {e}")
        return {}

    out: dict = {}
    fail_count = 0
    first_fail = None
    for raw in kr_tickers:
        t = str(raw).zfill(6)
        try:
            snap = broker.get_current_price(t)
            p = int(snap.get("stck_prpr", 0) or 0)
            if p > 0:
                out[t] = float(p)
            else:
                fail_count += 1
        except Exception as e:
            fail_count += 1
            if first_fail is None:
                first_fail = str(e)[:200]
    if fail_count and not out:
        print(f"[pulse] KIS 전체 실패 ({fail_count}건) — first error: {first_fail}")
    elif fail_count:
        print(f"[pulse] KIS 부분 실패 {fail_count}/{len(kr_tickers)} — first error: {first_fail}")
    return out


def main() -> int:
    t0 = time.perf_counter()
    print(f"[pulse] 시작 {_now_iso()}")

    # 1) 입력 — portfolio + recommendations 에서 티커 추출
    portfolio = _load_json(_PORTFOLIO, {})
    recs_root = _load_json(_RECS, {})
    recs = recs_root.get("recommendations", []) if isinstance(recs_root, dict) else (recs_root or [])

    kr_tickers: set[str] = set()
    us_symbols: set[str] = set()

    for h in (portfolio.get("vams", {}) or {}).get("holdings", []) or []:
        tk = h.get("ticker")
        if not tk:
            continue
        if (h.get("currency") or "").upper() == "USD":
            us_symbols.add(str(tk))
        else:
            kr_tickers.add(str(tk).zfill(6))

    for r in recs:
        tk = r.get("ticker")
        if not tk:
            continue
        if (r.get("currency") or "").upper() == "USD":
            us_symbols.add(str(tk))
        else:
            kr_tickers.add(str(tk).zfill(6))

    print(f"[pulse] 대상 KR={len(kr_tickers)} US={len(us_symbols)}")

    # 2) 지수 + US 종목 batch fetch (yahoo)
    yahoo_batch = list(_INDEX_SYMBOLS.values()) + [
        s if "." in s or "^" in s else s for s in us_symbols
    ]
    t_y0 = time.perf_counter()
    yahoo = fetch_yahoo_quotes(yahoo_batch)
    t_y = time.perf_counter() - t_y0
    print(f"[pulse] yahoo {len(yahoo)}/{len(yahoo_batch)} ({t_y:.1f}s)")

    # 3) KR 종목 KIS fetch
    t_k0 = time.perf_counter()
    kis_prices = fetch_kis_prices(sorted(kr_tickers))
    t_k = time.perf_counter() - t_k0
    print(f"[pulse] KIS {len(kis_prices)}/{len(kr_tickers)} ({t_k:.1f}s)")

    # 4) 결과 조립
    indices = {}
    for key, sym in _INDEX_SYMBOLS.items():
        q = yahoo.get(sym)
        if q and q.get("price") is not None:
            indices[key] = {
                "value": q["price"],
                "change_pct": q.get("change_pct"),
                "symbol": sym,
            }

    prices: dict = {}
    prices.update(kis_prices)
    for sym in us_symbols:
        q = yahoo.get(sym)
        if q and q.get("price") is not None:
            prices[sym] = q["price"]

    result = {
        "updated_at": _now_iso(),
        "elapsed_sec": round(time.perf_counter() - t0, 2),
        "indices": indices,
        "prices": prices,
        "counts": {
            "indices": len(indices),
            "kr": len(kis_prices),
            "us": sum(1 for s in us_symbols if s in prices),
            "kr_requested": len(kr_tickers),
            "us_requested": len(us_symbols),
        },
    }

    os.makedirs(_DATA, exist_ok=True)
    with open(_OUT, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"[pulse] 완료 {result['elapsed_sec']}s — 지수 {len(indices)} KR {len(kis_prices)} US {result['counts']['us']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
