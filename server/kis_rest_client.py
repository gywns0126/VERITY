"""
KIS REST API 클라이언트 — Railway 상시 구동용.

토큰 전략:
  1. 디스크 캐시 (/tmp/verity_kis_rest_token.json) → 재시작 시 기존 토큰 재사용
  2. 메모리 캐시 → 프로세스 수명 동안 재발급 없음
  3. 만료 5분 전에만 갱신
"""
from __future__ import annotations

import hashlib
import json as _json
import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests

from server.config import (
    KIS_APP_KEY,
    KIS_APP_SECRET,
    KIS_ACCOUNT_NO,
    KIS_BASE_URL,
    SUPABASE_URL,
    SUPABASE_SERVICE_ROLE_KEY,
)

logger = logging.getLogger(__name__)
KST = timezone(timedelta(hours=9))

_lock = threading.Lock()
_token: Optional[str] = None
_token_expires: float = 0.0  # unix timestamp
_token_source: str = "none"  # shared_consumer / tmp_cache / legacy_stale_guard / self_issue / none (RULE 1 관측성)

_TOKEN_CACHE_PATH = os.path.join(
    os.environ.get("XDG_CACHE_HOME", "/tmp"),
    "verity_kis_rest_token.json",
)

# 🚨 RULE 1 — KIS 발급 간격 최소 24h. 발급원 = GH Actions 단일 (PM 결정 2026-05-31).
# Railway(이 모듈) = KIS_SHARED_TOKEN=1 시 순수 소비자 (Supabase 공유 store 읽기, 발급 금지).
# flag off = legacy 롤백 (자체 발급 + /tmp + 24h 가드). _MIN_ISSUE_INTERVAL_S = legacy 가드용.
_MIN_ISSUE_INTERVAL_S = 24 * 3600


def _app_key_fp() -> str:
    """app_key fingerprint — GH publish 분과 자기 키 일치 검증용. 키 노출 없음."""
    return hashlib.sha256(KIS_APP_KEY.encode("utf-8")).hexdigest()[:12]


def _shared_enabled() -> bool:
    # flag 는 os.environ 직접 (import 시점 캐싱 회피). URL/KEY 는 deploy env (config).
    flag_on = os.environ.get("KIS_SHARED_TOKEN", "").strip().lower() in ("1", "true", "yes", "on")
    return bool(flag_on and SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY)


def _sb_headers() -> dict:
    return {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }


def _read_shared_token() -> Optional[dict]:
    """Supabase kis_shared_token 단일 행 읽기. 실패/없음 = None (caller fallback)."""
    if not _shared_enabled():
        return None
    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/kis_shared_token",
            headers=_sb_headers(),
            params={"id": "eq.kis_rest", "select": "*"},
            timeout=8,
        )
        r.raise_for_status()
        rows = r.json()
        return rows[0] if rows else None
    except Exception as e:
        logger.warning("KIS 공유 토큰 read 실패 (fallback): %s", e)
        return None


def _parse_ts(iso: Optional[str]) -> float:
    """ISO timestamptz → unix ts. 실패 시 0.0."""
    if not iso:
        return 0.0
    try:
        s = iso.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=KST)
        return dt.timestamp()
    except Exception:
        return 0.0


def _load_cached_token() -> bool:
    """디스크 캐시에서 유효한 토큰을 메모리로 로드. 성공 시 True."""
    global _token, _token_expires
    try:
        with open(_TOKEN_CACHE_PATH, "r", encoding="utf-8") as f:
            cached = _json.load(f)
        token = cached.get("access_token", "")
        expires_ts = cached.get("expires_ts", 0)
        app_key = cached.get("app_key", "")
        if token and expires_ts and app_key == KIS_APP_KEY:
            if time.time() < expires_ts:
                _token = token
                _token_expires = expires_ts
                logger.info("KIS REST 토큰 디스크 캐시 적중 (남은: %.0f분)", (expires_ts - time.time()) / 60)
                return True
    except (FileNotFoundError, _json.JSONDecodeError, KeyError):
        pass
    except Exception as e:
        logger.debug("토큰 캐시 로드 실패 (무시): %s", e)
    return False


def _save_cached_token() -> None:
    """현재 메모리 토큰을 디스크에 저장. 파일 권한 0600 강제 (preflight MAJ-5)."""
    try:
        os.makedirs(os.path.dirname(_TOKEN_CACHE_PATH) or "/tmp", exist_ok=True)
        with open(_TOKEN_CACHE_PATH, "w", encoding="utf-8") as f:
            _json.dump({
                "access_token": _token,
                "expires_ts": _token_expires,
                "app_key": KIS_APP_KEY,
            }, f)
        # /tmp 기본 permission 은 0644 — 같은 머신의 다른 프로세스 읽기 가능.
        # 토큰 탈취 시 실자금 거래 가능하므로 owner-only 로 제한.
        try:
            os.chmod(_TOKEN_CACHE_PATH, 0o600)
        except OSError:
            pass  # Windows 등 chmod 미지원 환경은 무시
    except Exception as e:
        logger.debug("토큰 캐시 저장 실패 (무시): %s", e)


def _get_token() -> str:
    """KIS REST 토큰 — 발급원 = GH Actions 단일 (PM 결정 2026-05-31).

    🚨 RULE 1 — KIS 1일 1토큰. 사고 2026-05-31: Railway(/tmp 6h) + GH(file lock 24h)
    두 발급원 독립 발급 → 하루 2토큰. /tmp 는 재시작마다 초기화돼 6h 가드 무력 → 재시작마다
    신규 발급. 해법: 발급원을 GH 1곳으로 일원화, GH 가 Supabase 공유 store 에 publish.

    조회 순서 (KIS_SHARED_TOKEN=1 — 순수 소비자, 발급 절대 안 함):
      1. 메모리 cache 유효 → 반환
      2. Supabase 공유 store (GH publish 분) 유효 → 사용 + /tmp cache. 반환.
      3. /tmp cache fallback (Supabase 일시 장애).
      4. 어디에도 없음 → RuntimeError. GH 가 아직 publish 안 함 — 소비자는 발급 금지.
         (_get/_post 가 catch → {} 반환. 다음 GH 발급/publish 까지 대기.)

    KIS_SHARED_TOKEN 미설정 시(legacy 롤백) = 자체 발급 + /tmp + 24h 가드.
    """
    global _token, _token_expires, _token_source
    with _lock:
        # 1) 메모리 cache 유효
        if _token and time.time() < _token_expires:
            return _token

        # 2) Supabase 공유 store (GH 단일 발급원 publish 분) — Railway 는 읽기만
        srow = _read_shared_token()
        if srow:
            s_tok = srow.get("access_token", "")
            s_exp = _parse_ts(srow.get("expires_at"))
            if s_tok and s_exp and srow.get("app_key_fp") == _app_key_fp():
                if time.time() < s_exp - 300:  # 유효 (5분 여유)
                    _token, _token_expires = s_tok, s_exp - 300
                    _token_source = "shared_consumer"
                    _save_cached_token()
                    logger.info("KIS REST 공유 store 소비 (GH 발급분, 남은: %.0f분)", (s_exp - time.time()) / 60)
                    return _token

        # 3) /tmp cache fallback (Supabase 일시 장애 대비)
        if _load_cached_token():
            _token_source = "tmp_cache"
            return _token  # type: ignore

        # ★ 순수 소비자 모드 — store/cache 어디에도 없음 → 발급 금지 (RULE 1 GH 단일 발급원).
        if _shared_enabled():
            raise RuntimeError(
                "KIS REST 공유 store 유효 토큰 없음 (소비자 모드). "
                "GH Actions 단일 발급원이 아직 발급/publish 안 함 — Railway 발급 금지 (RULE 1)."
            )

        # ── 이하 legacy 롤백 경로 (KIS_SHARED_TOKEN off) — 자체 발급 + 24h 가드 ──
        # 4) ★ 24h minimum interval 가드 — cache 만료 직전이어도 24h 안 지났으면 cache 반환.
        #    2026-05-31 RULE 1 정정: 6h → 24h. _load_cached_token() fail 했지만 disk stale 가능.
        try:
            with open(_TOKEN_CACHE_PATH, "r", encoding="utf-8") as f:
                stale = _json.load(f)
            stale_expires = float(stale.get("expires_ts", 0))
            stale_token = stale.get("access_token", "")
            if stale_token and stale_expires:
                # issued_at = expires - 24h (KIS 정책)
                stale_issued = stale_expires - 24 * 3600
                if time.time() - stale_issued < _MIN_ISSUE_INTERVAL_S:
                    logger.warning(
                        "KIS REST 24h minimum interval — stale cache 반환 (정책 위반 차단). "
                        "issued_ts=%.0f, expires_ts=%.0f, now=%.0f",
                        stale_issued, stale_expires, time.time(),
                    )
                    _token = stale_token
                    _token_expires = stale_expires
                    _token_source = "legacy_stale_guard"
                    return _token
        except (FileNotFoundError, _json.JSONDecodeError, KeyError, ValueError):
            pass
        except Exception as e:
            logger.debug("stale cache 검사 실패 (무시): %s", e)

        # 5) 새 발급 (24h 가드 통과 — 당일 미발급 확정 시에만 도달)
        r = requests.post(
            f"{KIS_BASE_URL}/oauth2/tokenP",
            json={
                "grant_type": "client_credentials",
                "appkey": KIS_APP_KEY,
                "appsecret": KIS_APP_SECRET,
            },
            timeout=10,
        )
        r.raise_for_status()
        d = r.json()
        _token = d["access_token"]
        exp_str = d.get("access_token_token_expired", "")
        try:
            exp_dt = datetime.strptime(exp_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=KST)
            _token_expires = exp_dt.timestamp() - 300  # 5분 여유
        except Exception:
            _token_expires = time.time() + 20 * 3600
        _token_source = "self_issue"
        _save_cached_token()
        logger.info("KIS REST 토큰 신규 발급 (legacy 롤백 모드, 만료: %s)", exp_str)
        return _token


def token_status() -> dict:
    """런타임 KIS REST 토큰 상태 — /health 노출용 (RULE 1 관측성, 2026-06-07).

    rule1_ok=False (shared_flag=True 인데 source='self_issue') = Railway 자체 발급 = P0.
    토큰 값/키는 노출 안 함 (app_key_fp = sha256 prefix 12, 키 일치 확인용).
    """
    now = time.time()
    return {
        "shared_flag": _shared_enabled(),
        "source": _token_source,
        "has_valid_token": bool(_token and now < _token_expires),
        "remaining_hours": round((_token_expires - now) / 3600, 1) if _token_expires else None,
        "app_key_fp": _app_key_fp(),
        "rule1_ok": (_token_source != "self_issue") if _shared_enabled() else True,
    }


def _headers(tr_id: str) -> dict:
    return {
        "Content-Type": "application/json; charset=utf-8",
        "authorization": f"Bearer {_get_token()}",
        "appkey": KIS_APP_KEY,
        "appsecret": KIS_APP_SECRET,
        "tr_id": tr_id,
        "custtype": "P",
    }


def _get(path: str, tr_id: str, params: dict) -> dict:
    try:
        r = requests.get(
            f"{KIS_BASE_URL}{path}",
            headers=_headers(tr_id),
            params=params,
            timeout=8,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.warning("KIS REST 요청 실패 %s: %s", path, e)
        return {}


def _post(path: str, tr_id: str, body: dict) -> dict:
    try:
        r = requests.post(
            f"{KIS_BASE_URL}{path}",
            headers=_headers(tr_id),
            json=body,
            timeout=8,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.warning("KIS REST POST 실패 %s: %s", path, e)
        return {}


def _account_parts() -> tuple[str, str]:
    raw = KIS_ACCOUNT_NO.replace("-", "")
    cano = raw[:8] if len(raw) >= 8 else raw
    prdt = raw[8:10] if len(raw) >= 10 else "01"
    return cano, prdt


# ── 일봉 ──

def fetch_daily(ticker: str, days: int = 365) -> list:
    now = datetime.now(KST)
    d = _get(
        "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice",
        "FHKST03010100",
        {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": ticker,
            "FID_INPUT_DATE_1": (now - timedelta(days=days)).strftime("%Y%m%d"),
            "FID_INPUT_DATE_2": now.strftime("%Y%m%d"),
            "FID_PERIOD_DIV_CODE": "D",
            "FID_ORG_ADJ_PRC": "0",
        },
    )
    candles = []
    for r in reversed(d.get("output2", [])):
        o = int(r.get("stck_oprc", 0) or 0)
        h = int(r.get("stck_hgpr", 0) or 0)
        l = int(r.get("stck_lwpr", 0) or 0)
        c = int(r.get("stck_clpr", 0) or 0)
        v = int(r.get("acml_vol", 0) or 0)
        if h > 0:
            candles.append({
                "date": r.get("stck_bsop_date", ""),
                "open": o, "high": h, "low": l, "close": c, "volume": v,
            })
    return candles


# ── 분봉 ──

def fetch_minute(ticker: str) -> list:
    d = _get(
        "/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice",
        "FHKST03010200",
        {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": ticker,
            "FID_INPUT_HOUR_1": "090000",
            "FID_PW_DATA_INCU_YN": "N",
            "FID_ETC_CLS_CODE": "",
        },
    )
    candles = []
    for r in reversed(d.get("output2", [])):
        o = int(r.get("stck_oprc", 0) or 0)
        h = int(r.get("stck_hgpr", 0) or 0)
        l = int(r.get("stck_lwpr", 0) or 0)
        c = int(r.get("stck_prpr", r.get("stck_clpr", 0)) or 0)
        v = int(r.get("cntg_vol", r.get("acml_vol", 0)) or 0)
        t = r.get("stck_cntg_hour", "")
        if h > 0:
            time_fmt = f"{t[:2]}:{t[2:4]}" if len(t) >= 4 else t
            candles.append({"time": time_fmt, "open": o, "high": h, "low": l, "close": c, "volume": v})
    return candles


# ── 호가 ──

def fetch_orderbook(ticker: str) -> dict:
    d = _get(
        "/uapi/domestic-stock/v1/quotations/inquire-asking-price-exp-ccn",
        "FHKST01010200",
        {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": ticker},
    )
    o1 = d.get("output1", {})
    _i = lambda k: int(o1.get(k, "0") or "0")

    asks, bids = [], []
    for i in range(10, 0, -1):
        p = _i(f"askp{i}")
        v = _i(f"askp_rsqn{i}")
        if p > 0:
            asks.append({"price": p, "volume": v, "side": "ask"})
    for i in range(1, 11):
        p = _i(f"bidp{i}")
        v = _i(f"bidp_rsqn{i}")
        if p > 0:
            bids.append({"price": p, "volume": v, "side": "bid"})

    return {
        "ticker": ticker,
        "asks": asks,
        "bids": bids,
        "total_ask_vol": _i("total_askp_rsqn"),
        "total_bid_vol": _i("total_bidp_rsqn"),
        "timestamp": datetime.now(KST).isoformat(),
    }


# ── 체결 ──

def fetch_trades(ticker: str) -> list:
    d = _get(
        "/uapi/domestic-stock/v1/quotations/inquire-time-itemconclusion",
        "FHPST01060000",
        {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": ticker,
            "FID_INPUT_HOUR_1": "",
        },
    )
    trades = []
    for r in (d.get("output", []) or [])[:30]:
        h = str(r.get("stck_cntg_hour", "") or "")
        price = int(r.get("stck_prpr", "0") or "0")
        change = int(r.get("prdy_vrss", "0") or "0")
        sign = str(r.get("prdy_vrss_sign", "3") or "3")
        vol = int(r.get("cntg_vol", "0") or "0")
        pct = float(r.get("prdy_ctrt", "0") or "0")
        side = "buy" if sign in ("1", "2") else ("sell" if sign in ("4", "5") else "neutral")
        time_fmt = f"{h[:2]}:{h[2:4]}:{h[4:6]}" if len(h) >= 6 else h
        if price > 0:
            trades.append({
                "time": time_fmt, "price": price,
                "change": change, "change_pct": pct,
                "volume": vol, "side": side,
            })
    return trades


# ── 현재가 ──

def fetch_price(ticker: str) -> dict:
    d = _get(
        "/uapi/domestic-stock/v1/quotations/inquire-price",
        "FHKST01010100",
        {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": ticker},
    )
    o = d.get("output", {})
    _i = lambda k: int(o.get(k, "0") or "0")
    _f = lambda k: float(o.get(k, "0") or "0")
    return {
        "price": _i("stck_prpr"),
        "prev_close": _i("stck_sdpr"),
        "change": _i("prdy_vrss"),
        "change_pct": _f("prdy_ctrt"),
        "volume": _i("acml_vol"),
        "open": _i("stck_oprc"),
        "high": _i("stck_hgpr"),
        "low": _i("stck_lwpr"),
        "upper_limit": _i("stck_mxpr"),
        "lower_limit": _i("stck_llam"),
    }


def fetch_program_trade(market: str = "K") -> dict:
    """KIS 프로그램매매 종합현황(시간) — comp-program-trade-today, tr_id FHPPG04600101.

    2026-06-03: KRX getJsonData 스크래핑(해외IP 차단 + 안티봇 LOGOUT)을 KIS 공식 API 로 대체.
    토큰 인증이라 IP/안티봇 무관. market: K(코스피)/Q(코스닥). output 구조는 raw 반환 —
    collector 측에서 차익/비차익 순매수 필드 매핑 (실호출로 필드명 확정 후).
    """
    d = _get(
        "/uapi/domestic-stock/v1/quotations/comp-program-trade-today",
        "FHPPG04600101",
        {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_MRKT_CLS_CODE": market,
            "FID_SCTN_CLS_CODE": "",
            "FID_INPUT_ISCD": "",
            "FID_COND_MRKT_DIV_CODE1": "",
            "FID_INPUT_HOUR_1": "",
        },
    )
    return d


# ── 국내 주문 ──

def place_kr_order(ticker: str, side: str, qty: int, price: int, order_type: str) -> dict:
    cano, prdt = _account_parts()
    tr_id = "TTTC0802U" if side == "buy" else "TTTC0801U"
    data = _post(
        "/uapi/domestic-stock/v1/trading/order-cash",
        tr_id,
        {
            "CANO": cano,
            "ACNT_PRDT_CD": prdt,
            "PDNO": ticker.zfill(6),
            "ORD_DVSN": order_type,
            "ORD_QTY": str(qty),
            "ORD_UNPR": str(price),
        },
    )
    if data.get("rt_cd") != "0":
        return {"success": False, "message": data.get("msg1", "주문 실패"), "raw": data}
    output = data.get("output", {})
    return {"success": True, "order_id": output.get("ODNO", ""), "message": data.get("msg1", "주문 접수"), "raw": data}


# ── 해외 주문 ──

def place_us_order(excd: str, ticker: str, side: str, qty: int, price: float, order_type: str) -> dict:
    cano, prdt = _account_parts()
    tr_id = "TTTT1002U" if side == "buy" else "TTTT1006U"
    data = _post(
        "/uapi/overseas-stock/v1/trading/order",
        tr_id,
        {
            "CANO": cano,
            "ACNT_PRDT_CD": prdt,
            "OVRS_EXCG_CD": excd,
            "PDNO": ticker,
            "ORD_DVSN": order_type,
            "ORD_QTY": str(qty),
            "OVRS_ORD_UNPR": str(price),
        },
    )
    if data.get("rt_cd") != "0":
        return {"success": False, "message": data.get("msg1", "주문 실패"), "raw": data}
    output = data.get("output", {})
    return {"success": True, "order_id": output.get("ODNO", ""), "message": data.get("msg1", "주문 접수"), "raw": data}


# ── 잔고 조회 ──

def get_balance(market: str = "kr") -> dict:
    cano, prdt = _account_parts()
    if market == "us":
        return _get(
            "/uapi/overseas-stock/v1/trading/inquire-balance",
            "TTTS3012R",
            {
                "CANO": cano, "ACNT_PRDT_CD": prdt,
                "OVRS_EXCG_CD": "NASD", "TR_CRCY_CD": "USD",
                "CTX_AREA_FK200": "", "CTX_AREA_NK200": "",
            },
        )
    return _get(
        "/uapi/domestic-stock/v1/trading/inquire-balance",
        "TTTC8434R",
        {
            "CANO": cano, "ACNT_PRDT_CD": prdt,
            "AFHR_FLPR_YN": "N", "OFL_YN": "",
            "INQR_DVSN": "02", "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N", "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "01", "CTX_AREA_FK100": "", "CTX_AREA_NK100": "",
        },
    )
