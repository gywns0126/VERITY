"""
VERITY 주문 API — 한국투자증권 Open API 실전 주문 프록시.
POST /api/order
Body: { "ticker": "005930", "side": "buy"|"sell", "qty": 1, "price": 0, "order_type": "00"|"01", "market": "kr"|"us", "excd": "NAS" }
order_type: "00" = 지정가, "01" = 시장가
price: 시장가 주문 시 0
"""
from http.server import BaseHTTPRequestHandler
import json
import os
import time
import requests
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
_PROD_URL = "https://openapi.koreainvestment.com:9443"

_token_cache = {"token": None, "expires": None}


def _get_env(key: str) -> str:
    return os.environ.get(key, "").strip().strip('"')


def _authenticate() -> str:
    now = datetime.now(KST)
    if _token_cache["token"] and _token_cache["expires"] and now < _token_cache["expires"]:
        return _token_cache["token"]
    base = _get_env("KIS_OPENAPI_BASE_URL") or _PROD_URL
    url = f"{base.rstrip('/')}/oauth2/tokenP"
    body = {
        "grant_type": "client_credentials",
        "appkey": _get_env("KIS_APP_KEY"),
        "appsecret": _get_env("KIS_APP_SECRET"),
    }
    r = requests.post(url, json=body, timeout=8)
    r.raise_for_status()
    data = r.json()
    _token_cache["token"] = data["access_token"]
    exp = data.get("access_token_token_expired", "")
    try:
        _token_cache["expires"] = datetime.strptime(exp, "%Y-%m-%d %H:%M:%S").replace(tzinfo=KST)
    except Exception:
        _token_cache["expires"] = now + timedelta(hours=20)
    return _token_cache["token"]


def _headers(tr_id: str) -> dict:
    token = _authenticate()
    base = _get_env("KIS_OPENAPI_BASE_URL") or _PROD_URL
    return {
        "Content-Type": "application/json; charset=utf-8",
        "authorization": f"Bearer {token}",
        "appkey": _get_env("KIS_APP_KEY"),
        "appsecret": _get_env("KIS_APP_SECRET"),
        "tr_id": tr_id,
    }


def _account_parts():
    raw = _get_env("KIS_ACCOUNT_NO").replace("-", "")
    cano = raw[:8] if len(raw) >= 8 else raw
    prdt = raw[8:10] if len(raw) >= 10 else "01"
    return cano, prdt


def _place_kr_order(ticker: str, side: str, qty: int, price: int, order_type: str) -> dict:
    base = (_get_env("KIS_OPENAPI_BASE_URL") or _PROD_URL).rstrip("/")
    cano, prdt = _account_parts()
    tr_id = "TTTC0802U" if side == "buy" else "TTTC0801U"
    body = {
        "CANO": cano,
        "ACNT_PRDT_CD": prdt,
        "PDNO": ticker.zfill(6),
        "ORD_DVSN": order_type,
        "ORD_QTY": str(qty),
        "ORD_UNPR": str(price),
    }
    r = requests.post(
        f"{base}/uapi/domestic-stock/v1/trading/order-cash",
        headers=_headers(tr_id),
        json=body,
        timeout=8,
    )
    data = r.json()
    if data.get("rt_cd") != "0":
        return {"success": False, "message": data.get("msg1", "주문 실패"), "raw": data}
    output = data.get("output", {})
    return {
        "success": True,
        "order_id": output.get("ODNO", ""),
        "message": data.get("msg1", "주문 접수"),
        "raw": data,
    }


def _place_us_order(excd: str, ticker: str, side: str, qty: int, price: float, order_type: str) -> dict:
    base = (_get_env("KIS_OPENAPI_BASE_URL") or _PROD_URL).rstrip("/")
    cano, prdt = _account_parts()
    tr_id = "TTTT1002U" if side == "buy" else "TTTT1006U"
    body = {
        "CANO": cano,
        "ACNT_PRDT_CD": prdt,
        "OVRS_EXCG_CD": excd,
        "PDNO": ticker,
        "ORD_DVSN": order_type,
        "ORD_QTY": str(qty),
        "OVRS_ORD_UNPR": str(price),
    }
    r = requests.post(
        f"{base}/uapi/overseas-stock/v1/trading/order",
        headers=_headers(tr_id),
        json=body,
        timeout=8,
    )
    data = r.json()
    if data.get("rt_cd") != "0":
        return {"success": False, "message": data.get("msg1", "주문 실패"), "raw": data}
    output = data.get("output", {})
    return {
        "success": True,
        "order_id": output.get("ODNO", ""),
        "message": data.get("msg1", "주문 접수"),
        "raw": data,
    }


def _get_balance(market: str = "kr") -> dict:
    base = (_get_env("KIS_OPENAPI_BASE_URL") or _PROD_URL).rstrip("/")
    cano, prdt = _account_parts()
    if market == "us":
        tr_id = "TTTS3012R"
        params = {
            "CANO": cano,
            "ACNT_PRDT_CD": prdt,
            "OVRS_EXCG_CD": "NASD",
            "TR_CRCY_CD": "USD",
            "CTX_AREA_FK200": "",
            "CTX_AREA_NK200": "",
        }
        r = requests.get(
            f"{base}/uapi/overseas-stock/v1/trading/inquire-balance",
            headers=_headers(tr_id),
            params=params,
            timeout=8,
        )
    else:
        tr_id = "TTTC8434R"
        params = {
            "CANO": cano,
            "ACNT_PRDT_CD": prdt,
            "AFHR_FLPR_YN": "N",
            "OFL_YN": "",
            "INQR_DVSN": "02",
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "01",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
        }
        r = requests.get(
            f"{base}/uapi/domestic-stock/v1/trading/inquire-balance",
            headers=_headers(tr_id),
            params=params,
            timeout=8,
        )
    return r.json()


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        self._cors()
        try:
            from urllib.parse import parse_qs, urlparse
            qs = parse_qs(urlparse(self.path).query)
            market = (qs.get("market", ["kr"])[0]).lower()
            data = _get_balance(market)
            self._json(200, data)
        except Exception as e:
            self._json(500, {"error": str(e)})

    def do_POST(self):
        self._cors()
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length > 0 else {}

            ticker = str(body.get("ticker", "")).strip()
            side = str(body.get("side", "")).lower()
            qty = int(body.get("qty", 0))
            price = body.get("price", 0)
            order_type = str(body.get("order_type", "00"))
            market = str(body.get("market", "kr")).lower()
            excd = str(body.get("excd", "NAS"))

            if not ticker:
                return self._json(400, {"success": False, "message": "ticker 필수"})
            if side not in ("buy", "sell"):
                return self._json(400, {"success": False, "message": "side는 buy 또는 sell"})
            if qty <= 0:
                return self._json(400, {"success": False, "message": "수량은 1 이상"})

            if market == "us":
                result = _place_us_order(excd, ticker, side, qty, float(price), order_type)
            else:
                result = _place_kr_order(ticker, side, qty, int(price), order_type)

            self._json(200, result)
        except Exception as e:
            self._json(500, {"success": False, "message": str(e)})

    def _cors(self):
        pass

    def _json(self, code: int, data: dict):
        body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)
