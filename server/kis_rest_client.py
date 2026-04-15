"""
KIS REST API 클라이언트 — Railway 상시 구동용.

토큰 전략:
  1. 디스크 캐시 (/tmp/verity_kis_rest_token.json) → 재시작 시 기존 토큰 재사용
  2. 메모리 캐시 → 프로세스 수명 동안 재발급 없음
  3. 만료 5분 전에만 갱신
"""
from __future__ import annotations

import json as _json
import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests

from server.config import KIS_APP_KEY, KIS_APP_SECRET, KIS_ACCOUNT_NO, KIS_BASE_URL

logger = logging.getLogger(__name__)
KST = timezone(timedelta(hours=9))

_lock = threading.Lock()
_token: Optional[str] = None
_token_expires: float = 0.0  # unix timestamp

_TOKEN_CACHE_PATH = os.path.join(
    os.environ.get("XDG_CACHE_HOME", "/tmp"),
    "verity_kis_rest_token.json",
)


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
    """현재 메모리 토큰을 디스크에 저장."""
    try:
        os.makedirs(os.path.dirname(_TOKEN_CACHE_PATH) or "/tmp", exist_ok=True)
        with open(_TOKEN_CACHE_PATH, "w", encoding="utf-8") as f:
            _json.dump({
                "access_token": _token,
                "expires_ts": _token_expires,
                "app_key": KIS_APP_KEY,
            }, f)
    except Exception as e:
        logger.debug("토큰 캐시 저장 실패 (무시): %s", e)


def _get_token() -> str:
    global _token, _token_expires
    with _lock:
        if _token and time.time() < _token_expires:
            return _token
        if _load_cached_token():
            return _token  # type: ignore
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
        _save_cached_token()
        logger.info("KIS REST 토큰 신규 발급 (만료: %s)", exp_str)
        return _token


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
