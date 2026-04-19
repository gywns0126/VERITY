"""
Finnhub 미국 시장 데이터 수집기
- 애널리스트 컨센서스 (네이버 컨센서스 대체)
- 실적 서프라이즈 (최근 4분기)
- 내부자 심리 (MSPR)
- 기관 보유 비중
- 기업 뉴스
"""
import time
import logging
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Union

from api.mocks import mockable

logger = logging.getLogger(__name__)

_BASE = "https://finnhub.io/api/v1"
_SESSION = requests.Session()
_LAST_CALL = 0.0
_MIN_INTERVAL = 1.0  # 무료 60req/min → ~1req/sec 안전 마진


def _get(endpoint: str, params: dict, api_key: str, timeout: int = 12) -> Optional[Union[dict, list]]:
    global _LAST_CALL
    elapsed = time.time() - _LAST_CALL
    if elapsed < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - elapsed)
    _LAST_CALL = time.time()

    params["token"] = api_key
    try:
        r = _SESSION.get(f"{_BASE}/{endpoint}", params=params, timeout=timeout)
        if r.status_code == 429:
            logger.warning("Finnhub rate limited, sleeping 5s")
            time.sleep(5)
            r = _SESSION.get(f"{_BASE}/{endpoint}", params=params, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.warning("Finnhub %s failed: %s", endpoint, e)
        return None


@mockable("finnhub.analyst_consensus")
def get_analyst_consensus(ticker: str, api_key: str) -> Dict:
    """애널리스트 추천 요약 + 목표가."""
    result = {"buy": 0, "hold": 0, "sell": 0, "target_mean": 0, "target_high": 0, "target_low": 0, "upside_pct": 0}

    rec = _get("stock/recommendation", {"symbol": ticker}, api_key)
    if rec and isinstance(rec, list) and len(rec) > 0:
        latest = rec[0]
        result["buy"] = latest.get("buy", 0) + latest.get("strongBuy", 0)
        result["hold"] = latest.get("hold", 0)
        result["sell"] = latest.get("sell", 0) + latest.get("strongSell", 0)

    pt = _get("stock/price-target", {"symbol": ticker}, api_key)
    if pt and isinstance(pt, dict):
        result["target_mean"] = pt.get("targetMean", 0)
        result["target_high"] = pt.get("targetHigh", 0)
        result["target_low"] = pt.get("targetLow", 0)
        current = pt.get("lastUpdatedPrice", 0)
        if current and result["target_mean"]:
            result["upside_pct"] = round((result["target_mean"] / current - 1) * 100, 1)

    return result


@mockable("finnhub.earnings_surprises")
def get_earnings_surprises(ticker: str, api_key: str) -> List[Dict]:
    """최근 4분기 실적 서프라이즈."""
    data = _get("stock/earnings", {"symbol": ticker}, api_key)
    if not data or not isinstance(data, list):
        return []
    results = []
    for item in data[:4]:
        actual = item.get("actual")
        estimate = item.get("estimate")
        surprise = item.get("surprisePercent", 0)
        results.append({
            "period": item.get("period", ""),
            "actual": actual,
            "estimate": estimate,
            "surprise_pct": round(surprise, 2) if surprise else 0,
        })
    return results


@mockable("finnhub.insider_sentiment")
def get_insider_sentiment(ticker: str, api_key: str) -> Dict:
    """내부자 심리 (Monthly Share Purchase Ratio)."""
    result = {"mspr": 0, "positive_count": 0, "negative_count": 0, "net_shares": 0}
    now = datetime.utcnow()
    from_d = (now - timedelta(days=90)).strftime("%Y-%m-%d")
    to_d = now.strftime("%Y-%m-%d")

    data = _get("stock/insider-sentiment", {"symbol": ticker, "from": from_d, "to": to_d}, api_key)
    if not data or not isinstance(data, dict):
        return result

    items = data.get("data", [])
    if not items:
        return result

    total_mspr = 0
    pos = 0
    neg = 0
    for row in items:
        m = row.get("mspr", 0) or 0
        total_mspr += m
        ch = row.get("change", 0) or 0
        if ch > 0:
            pos += 1
        elif ch < 0:
            neg += 1
        result["net_shares"] += int(ch)

    result["mspr"] = round(total_mspr, 4)
    result["positive_count"] = pos
    result["negative_count"] = neg
    return result


@mockable("finnhub.institutional_ownership")
def get_institutional_ownership(ticker: str, api_key: str) -> Dict:
    """기관 보유 현황 요약."""
    result = {"total_holders": 0, "total_shares": 0, "change_pct": 0}
    data = _get("institutional/ownership", {"symbol": ticker, "limit": 20}, api_key)
    if not data or not isinstance(data, dict):
        return result
    holders = data.get("ownership", [])
    result["total_holders"] = len(holders)
    total = sum(h.get("share", 0) for h in holders)
    change = sum(h.get("change", 0) for h in holders)
    result["total_shares"] = total
    if total > 0 and change:
        result["change_pct"] = round(change / total * 100, 2)
    return result


@mockable("finnhub.peer_companies")
def get_peer_companies(ticker: str, api_key: str) -> List[str]:
    """동종 업종 종목 리스트."""
    data = _get("stock/peers", {"symbol": ticker}, api_key)
    if not data or not isinstance(data, list):
        return []
    return [p for p in data if p != ticker][:10]


@mockable("finnhub.basic_financials")
def get_basic_financials(ticker: str, api_key: str) -> Dict:
    """핵심 재무 메트릭 (52주 수익률, beta, 10일 평균 거래량, 공매도 등)."""
    result = {
        "52w_high": None, "52w_low": None, "52w_return": None,
        "beta": None, "10d_avg_volume": None, "market_cap": None,
        "short_pct_outstanding": None, "short_pct_float": None,
    }
    data = _get("stock/metric", {"symbol": ticker, "metric": "all"}, api_key)
    if not data or not isinstance(data, dict):
        return result
    m = data.get("metric", {})
    result["52w_high"] = m.get("52WeekHigh")
    result["52w_low"] = m.get("52WeekLow")
    result["52w_return"] = m.get("52WeekPriceReturnDaily")
    result["beta"] = m.get("beta")
    result["10d_avg_volume"] = m.get("10DayAverageTradingVolume")
    result["market_cap"] = m.get("marketCapitalization")
    result["short_pct_outstanding"] = m.get("shortPercentOutstanding")
    result["short_pct_float"] = m.get("shortPercentFloat")
    return result


@mockable("finnhub.company_news")
def get_company_news(ticker: str, api_key: str, days: int = 7) -> List[Dict]:
    """최근 기업 뉴스."""
    now = datetime.utcnow()
    from_d = (now - timedelta(days=days)).strftime("%Y-%m-%d")
    to_d = now.strftime("%Y-%m-%d")

    data = _get("company-news", {"symbol": ticker, "from": from_d, "to": to_d}, api_key)
    if not data or not isinstance(data, list):
        return []
    results = []
    for item in data[:10]:
        results.append({
            "title": item.get("headline", ""),
            "url": item.get("url", ""),
            "source": item.get("source", ""),
            "datetime": item.get("datetime", 0),
            "summary": (item.get("summary", "") or "")[:200],
        })
    return results
