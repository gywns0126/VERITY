"""
VERITY 차트/호가/체결 API — KIS OpenAPI 실시간 프록시.
GET /api/chart?ticker=005930
GET /api/chart?ticker=005930&type=minute   (분봉)
GET /api/chart?ticker=005930&type=all      (일봉+분봉+호가+체결 전부)

촘촘한 차트 데이터를 KIS에서 직접 조회.
"""
from http.server import BaseHTTPRequestHandler
import json
import os
import requests
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse
from concurrent.futures import ThreadPoolExecutor

KST = timezone(timedelta(hours=9))
_PROD_URL = "https://openapi.koreainvestment.com:9443"
_token_cache = {"token": None, "expires": None}


def _env(key: str) -> str:
    return os.environ.get(key, "").strip().strip('"')


def _auth() -> str:
    now = datetime.now(KST)
    if _token_cache["token"] and _token_cache["expires"] and now < _token_cache["expires"]:
        return _token_cache["token"]
    base = (_env("KIS_OPENAPI_BASE_URL") or _PROD_URL).rstrip("/")
    r = requests.post(f"{base}/oauth2/tokenP", json={
        "grant_type": "client_credentials",
        "appkey": _env("KIS_APP_KEY"),
        "appsecret": _env("KIS_APP_SECRET"),
    }, timeout=8)
    r.raise_for_status()
    d = r.json()
    _token_cache["token"] = d["access_token"]
    exp = d.get("access_token_token_expired", "")
    try:
        _token_cache["expires"] = datetime.strptime(exp, "%Y-%m-%d %H:%M:%S").replace(tzinfo=KST)
    except Exception:
        _token_cache["expires"] = now + timedelta(hours=20)
    return _token_cache["token"]


def _headers(tr_id: str) -> dict:
    token = _auth()
    return {
        "Content-Type": "application/json; charset=utf-8",
        "authorization": f"Bearer {token}",
        "appkey": _env("KIS_APP_KEY"),
        "appsecret": _env("KIS_APP_SECRET"),
        "tr_id": tr_id,
        "custtype": "P",
    }


def _base() -> str:
    return (_env("KIS_OPENAPI_BASE_URL") or _PROD_URL).rstrip("/")


def _get(path: str, tr_id: str, params: dict) -> dict:
    r = requests.get(f"{_base()}{path}", headers=_headers(tr_id), params=params, timeout=8)
    r.raise_for_status()
    return r.json()


# ── 일봉 (최대 100일) ──

def fetch_daily(ticker: str, days: int = 100) -> list:
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
    raw = d.get("output2", [])
    candles = []
    for r in reversed(raw):
        o = int(r.get("stck_oprc", 0) or 0)
        h = int(r.get("stck_hgpr", 0) or 0)
        l = int(r.get("stck_lwpr", 0) or 0)
        c = int(r.get("stck_clpr", 0) or 0)
        v = int(r.get("acml_vol", 0) or 0)
        if h > 0:
            candles.append({"date": r.get("stck_bsop_date", ""), "open": o, "high": h, "low": l, "close": c, "volume": v})
    return candles


# ── 분봉 (당일) ──

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
    raw = d.get("output2", [])
    candles = []
    for r in reversed(raw):
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


# ── 호가 (10호가) ──

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


# ── 체결 (최근 30건) ──

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
            trades.append({"time": time_fmt, "price": price, "change": change, "change_pct": pct, "volume": vol, "side": side})
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


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        params = parse_qs(urlparse(self.path).query)
        ticker = (params.get("ticker", [""])[0] or params.get("t", [""])[0]).strip().zfill(6)
        qtype = params.get("type", ["all"])[0].strip().lower()

        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "s-maxage=30, stale-while-revalidate=60")
        self.end_headers()

        if not ticker or ticker == "000000":
            self.wfile.write(json.dumps({"error": "ticker 파라미터 필요"}, ensure_ascii=False).encode())
            return

        if not _env("KIS_APP_KEY"):
            self.wfile.write(json.dumps({"error": "KIS API 키 미설정"}, ensure_ascii=False).encode())
            return

        result = {"ticker": ticker}
        try:
            with ThreadPoolExecutor(max_workers=5) as pool:
                futures = {}

                if qtype in ("all", "daily"):
                    futures["daily"] = pool.submit(fetch_daily, ticker)
                if qtype in ("all", "minute"):
                    futures["minute"] = pool.submit(fetch_minute, ticker)
                if qtype in ("all", "orderbook"):
                    futures["orderbook"] = pool.submit(fetch_orderbook, ticker)
                if qtype in ("all", "trades"):
                    futures["trades"] = pool.submit(fetch_trades, ticker)
                if qtype in ("all", "price"):
                    futures["price"] = pool.submit(fetch_price, ticker)

                for key, fut in futures.items():
                    try:
                        result[key] = fut.result(timeout=8)
                    except Exception as e:
                        result[key] = {"error": str(e)[:200]}

        except Exception as e:
            result["error"] = str(e)[:200]

        self.wfile.write(json.dumps(result, ensure_ascii=False).encode())
