"""
NewsAPI 미국 뉴스 수집기
- Google News RSS 보완: 본문 snippet 포함, 소스 다양성
- 종목별 뉴스 + 시장 전반 뉴스
"""
import logging
import requests
from datetime import datetime, timedelta
from typing import Dict, List

from api.mocks import mockable

logger = logging.getLogger(__name__)

_BASE = "https://newsapi.org/v2"
_SESSION = requests.Session()


def _get(endpoint: str, params: dict, api_key: str, timeout: int = 10) -> dict:
    params["apiKey"] = api_key
    try:
        r = _SESSION.get(f"{_BASE}/{endpoint}", params=params, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.warning("NewsAPI %s failed: %s", endpoint, e)
        return {}


@mockable("newsapi.us_stock_news")
def get_us_stock_news(ticker: str, name: str, api_key: str,
                      days: int = 3, max_articles: int = 20) -> List[Dict]:
    """종목 관련 미국 뉴스 (본문 snippet 포함)."""
    if not api_key:
        return []

    from_d = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S")
    query = f'"{name}" OR "{ticker}" stock'

    data = _get("everything", {
        "q": query,
        "language": "en",
        "sortBy": "relevancy",
        "pageSize": min(max_articles, 100),
        "from": from_d,
    }, api_key)

    articles = data.get("articles", [])
    results = []
    for a in articles[:max_articles]:
        results.append({
            "title": a.get("title", ""),
            "description": (a.get("description") or "")[:300],
            "url": a.get("url", ""),
            "source": a.get("source", {}).get("name", ""),
            "published_at": a.get("publishedAt", ""),
        })
    return results


@mockable("newsapi.market_news")
def get_market_news(api_key: str, query: str = "US stock market",
                    max_articles: int = 10) -> List[Dict]:
    """시장 전반 뉴스."""
    if not api_key:
        return []

    from_d = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
    data = _get("everything", {
        "q": query,
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": min(max_articles, 50),
        "from": from_d,
    }, api_key)

    articles = data.get("articles", [])
    results = []
    for a in articles[:max_articles]:
        results.append({
            "title": a.get("title", ""),
            "description": (a.get("description") or "")[:300],
            "url": a.get("url", ""),
            "source": a.get("source", {}).get("name", ""),
            "published_at": a.get("publishedAt", ""),
        })
    return results
