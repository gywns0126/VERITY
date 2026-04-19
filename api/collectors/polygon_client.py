"""
Polygon.io 미국 시장 데이터 수집기
- 옵션 플로우 (Put/Call ratio, IV, OI)
- 공매도 (Short Interest)
- 장전/장후 시세
"""
import time
import logging
import requests
from typing import Dict, Optional

from api.mocks import mockable

logger = logging.getLogger(__name__)

_BASE = "https://api.polygon.io"
_SESSION = requests.Session()
_LAST_CALL = 0.0
_MIN_INTERVAL_FREE = 12.0   # 무료 5req/min → 12s
_MIN_INTERVAL_PAID = 0.05


def _get(path: str, params: dict, api_key: str, tier: str = "free", timeout: int = 12) -> Optional[dict]:
    global _LAST_CALL
    interval = _MIN_INTERVAL_FREE if tier == "free" else _MIN_INTERVAL_PAID
    elapsed = time.time() - _LAST_CALL
    if elapsed < interval:
        time.sleep(interval - elapsed)
    _LAST_CALL = time.time()

    params["apiKey"] = api_key
    try:
        r = _SESSION.get(f"{_BASE}{path}", params=params, timeout=timeout)
        if r.status_code == 429:
            logger.warning("Polygon rate limited, sleeping 15s")
            time.sleep(15)
            r = _SESSION.get(f"{_BASE}{path}", params=params, timeout=timeout)
        if r.status_code == 403:
            logger.info("Polygon 403 for %s (tier=%s) — may need higher plan", path, tier)
            return None
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.warning("Polygon %s failed: %s", path, e)
        return None


@mockable("polygon.options_flow")
def get_options_flow(ticker: str, api_key: str, tier: str = "free") -> Dict:
    """옵션 시장 개요: Put/Call ratio, 총 OI, 평균 IV."""
    result = {
        "put_call_ratio": None, "total_oi": 0,
        "avg_iv": None, "iv_percentile": None,
        "total_volume": 0,
    }
    if not api_key:
        return result

    data = _get(f"/v3/snapshot/options/{ticker}", {}, api_key, tier)
    if not data or data.get("status") != "OK":
        # 대체: 개별 체인에서 집계
        data = _get(f"/v3/reference/options/contracts", {"underlying_ticker": ticker, "limit": 100, "expired": "false"}, api_key, tier)
        if not data:
            return result
        contracts = data.get("results", [])
        puts = sum(1 for c in contracts if c.get("contract_type") == "put")
        calls = sum(1 for c in contracts if c.get("contract_type") == "call")
        if calls > 0:
            result["put_call_ratio"] = round(puts / calls, 3)
        result["total_oi"] = sum(c.get("open_interest", 0) for c in contracts)
        return result

    results_list = data.get("results", [])
    if not results_list:
        return result

    total_put_oi = 0
    total_call_oi = 0
    total_put_vol = 0
    total_call_vol = 0
    iv_sum = 0.0
    iv_count = 0

    for opt in results_list:
        details = opt.get("details", {})
        day = opt.get("day", {})
        greeks = opt.get("greeks", {})

        oi = opt.get("open_interest", 0) or 0
        vol = day.get("volume", 0) or 0
        iv = greeks.get("implied_volatility")

        if details.get("contract_type") == "put":
            total_put_oi += oi
            total_put_vol += vol
        else:
            total_call_oi += oi
            total_call_vol += vol

        if iv is not None:
            iv_sum += iv
            iv_count += 1

    total_call = total_call_oi or 1
    result["put_call_ratio"] = round(total_put_oi / total_call, 3)
    result["total_oi"] = total_put_oi + total_call_oi
    result["total_volume"] = total_put_vol + total_call_vol
    if iv_count > 0:
        result["avg_iv"] = round(iv_sum / iv_count * 100, 1)

    return result


@mockable("polygon.short_interest")
def get_short_interest(ticker: str, api_key: str, tier: str = "free") -> Dict:
    """공매도 정보."""
    result = {"short_pct": None, "days_to_cover": None, "short_ratio": None}
    if not api_key:
        return result

    # Polygon의 short interest는 유료 엔드포인트
    # Ticker Details v3에서 share_class_shares_outstanding 참조 가능
    data = _get(f"/v3/reference/tickers/{ticker}", {}, api_key, tier)
    if not data or not isinstance(data, dict):
        return result
    ref = data.get("results", {})
    shares_out = ref.get("share_class_shares_outstanding") or ref.get("weighted_shares_outstanding")

    # Short volume from daily (최근 5일 평균)
    import datetime
    today = datetime.date.today()
    from_d = (today - datetime.timedelta(days=7)).strftime("%Y-%m-%d")
    to_d = today.strftime("%Y-%m-%d")
    vol_data = _get(f"/v2/aggs/ticker/{ticker}/range/1/day/{from_d}/{to_d}", {}, api_key, tier)
    if vol_data and vol_data.get("results"):
        avg_vol = sum(bar.get("v", 0) for bar in vol_data["results"]) / len(vol_data["results"])
    else:
        avg_vol = 0

    # short_pct는 전용 데이터 필요 — 여기서는 stub으로 남김
    if shares_out and avg_vol > 0:
        result["short_ratio"] = round(shares_out / avg_vol / 1000, 2) if avg_vol else None

    return result


@mockable("polygon.pre_after_market")
def get_pre_after_market(ticker: str, api_key: str, tier: str = "free") -> Dict:
    """장전/장후 시세."""
    result = {
        "pre_price": None, "pre_change_pct": None, "pre_volume": None,
        "after_price": None, "after_change_pct": None, "after_volume": None,
    }
    if not api_key:
        return result

    data = _get(f"/v2/snapshot/locale/us/markets/stocks/tickers/{ticker}", {}, api_key, tier)
    if not data or not isinstance(data, dict):
        return result

    snap = data.get("ticker", {})
    prev_close = snap.get("prevDay", {}).get("c", 0)

    pre = snap.get("preMarket", {})
    if pre and pre.get("price"):
        result["pre_price"] = pre["price"]
        result["pre_volume"] = pre.get("volume")
        if prev_close:
            result["pre_change_pct"] = round((pre["price"] / prev_close - 1) * 100, 2)

    after = snap.get("afterHours", {})
    if after and after.get("price"):
        result["after_price"] = after["price"]
        result["after_volume"] = after.get("volume")
        if prev_close:
            result["after_change_pct"] = round((after["price"] / prev_close - 1) * 100, 2)

    return result
