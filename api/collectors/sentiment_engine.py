"""
통합 감성 엔진 — 뉴스 + 네이버 커뮤니티 + Reddit + StockTwits 가중 합산.
국장: 뉴스 40% + 커뮤니티 35% + Reddit 25%
미장: 뉴스 30% + StockTwits 35% + Reddit 35%
"""
import logging
from typing import Any, Dict, List, Optional

from api.collectors.naver_community import fetch_community_sentiment
from api.collectors.reddit_sentiment import fetch_reddit_sentiment
from api.collectors.stocktwits_sentiment import fetch_stocktwits_sentiment

logger = logging.getLogger(__name__)


def _is_us_ticker(ticker: str) -> bool:
    """yfinance 형식 기준 미장 여부 판별."""
    if not ticker:
        return False
    return not (ticker.endswith(".KS") or ticker.endswith(".KQ"))


def compute_social_sentiment(
    name: str,
    ticker_yf: str,
    stock_code: Optional[str] = None,
    existing_news: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    단일 종목에 대한 통합 소셜 감성 계산.

    Args:
        name: 종목 한글명 (예: "삼성전자")
        ticker_yf: yfinance 티커 (예: "005930.KS" or "AAPL")
        stock_code: KRX 종목코드 6자리 (예: "005930"), 국장에만 필요
        existing_news: 이미 수집된 뉴스 감성 dict (score/positive/negative)

    Returns:
        {score, news, community, reddit, trend, sources_used}
    """
    is_us = _is_us_ticker(ticker_yf)

    news_data = existing_news or {}
    news_score = news_data.get("score", 50)

    community_data: Dict[str, Any] = {}
    community_score = 50
    if not is_us and stock_code:
        try:
            community_data = fetch_community_sentiment(stock_code, pages=2)
            community_score = community_data.get("score", 50)
        except Exception as e:
            logger.warning(f"커뮤니티 감성 수집 실패 ({name}): {e}")

    reddit_data: Dict[str, Any] = {}
    reddit_score = 50
    base_ticker = ticker_yf.split(".")[0]
    if is_us or len(base_ticker) <= 5:
        try:
            reddit_data = fetch_reddit_sentiment(base_ticker, limit=20)
            reddit_score = reddit_data.get("score", 50)
        except Exception as e:
            logger.warning(f"Reddit 감성 수집 실패 ({name}): {e}")

    stocktwits_data: Dict[str, Any] = {}
    stocktwits_score = 50
    if is_us:
        try:
            stocktwits_data = fetch_stocktwits_sentiment(base_ticker)
            if not stocktwits_data.get("_error"):
                stocktwits_score = stocktwits_data.get("score", 50)
        except Exception as e:
            logger.warning(f"StockTwits 감성 수집 실패 ({name}): {e}")

    if is_us:
        combined = news_score * 0.30 + stocktwits_score * 0.35 + reddit_score * 0.35
    else:
        combined = news_score * 0.40 + community_score * 0.35 + reddit_score * 0.25

    combined = max(0, min(100, round(combined)))

    if combined >= 65:
        trend = "bullish"
    elif combined <= 35:
        trend = "bearish"
    else:
        trend = "neutral"

    sources = ["news"]
    if community_data:
        sources.append("naver_community")
    if reddit_data:
        sources.append("reddit")
    if stocktwits_data and not stocktwits_data.get("_error"):
        sources.append("stocktwits")

    result: Dict[str, Any] = {
        "score": combined,
        "news": {
            "score": news_score,
            "positive": news_data.get("positive", 0),
            "negative": news_data.get("negative", 0),
        },
        "community": {
            "score": community_score,
            "positive": community_data.get("positive", 0),
            "negative": community_data.get("negative", 0),
            "volume": community_data.get("volume", 0),
        },
        "reddit": {
            "score": reddit_score,
            "positive": reddit_data.get("positive", 0),
            "negative": reddit_data.get("negative", 0),
            "volume": reddit_data.get("volume", 0),
            "top_posts": reddit_data.get("top_posts", [])[:3],
        },
        "trend": trend,
        "sources_used": sources,
    }

    if is_us and stocktwits_data and not stocktwits_data.get("_error"):
        result["stocktwits"] = {
            "score": stocktwits_score,
            "bullish": stocktwits_data.get("bullish", 0),
            "bearish": stocktwits_data.get("bearish", 0),
            "volume": stocktwits_data.get("volume", 0),
            "label": stocktwits_data.get("label", "neutral"),
            "top_messages": stocktwits_data.get("top_messages", [])[:3],
        }

    return result


def batch_social_sentiment(
    stocks: List[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """
    종목 리스트에 대해 일괄 소셜 감성 수집.

    Args:
        stocks: [{"name": ..., "ticker": ..., "stock_code": ..., "sentiment": {...}}]

    Returns:
        {ticker: social_sentiment_dict}
    """
    results: Dict[str, Dict[str, Any]] = {}
    for stock in stocks:
        ticker = stock.get("ticker", "")
        name = stock.get("name", ticker)
        code = stock.get("stock_code") or stock.get("code")
        existing = stock.get("sentiment")
        try:
            results[ticker] = compute_social_sentiment(
                name=name,
                ticker_yf=ticker,
                stock_code=code,
                existing_news=existing,
            )
        except Exception as e:
            logger.error(f"소셜 감성 수집 오류 ({name}): {e}")
            results[ticker] = {"score": 50, "trend": "neutral", "sources_used": []}
    return results
