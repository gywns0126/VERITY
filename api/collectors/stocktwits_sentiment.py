"""
미장 애널리스트 감성 수집기 — yfinance 기반 Analyst Consensus.

StockTwits 공개 API 차단(2025~) 이후 대체:
yfinance recommendations_summary에서 strongBuy/buy/hold/sell/strongSell 분포를
0~100 감성 점수로 변환.

소셜 잡담보다 기관 애널리스트 컨센서스가 투자 판단에 더 유효.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List

import yfinance as yf


def fetch_stocktwits_sentiment(
    ticker: str,
) -> Dict[str, Any]:
    """
    yfinance 애널리스트 컨센서스 기반 감성 점수.

    Returns:
        {score, bullish, bearish, total, volume, label,
         breakdown, top_messages}
    """
    try:
        t = yf.Ticker(ticker)
        rec = t.recommendations_summary
        if rec is None or len(rec) == 0:
            return _default()

        latest = rec.iloc[0]
        strong_buy = int(latest.get("strongBuy", 0))
        buy = int(latest.get("buy", 0))
        hold = int(latest.get("hold", 0))
        sell = int(latest.get("sell", 0))
        strong_sell = int(latest.get("strongSell", 0))

        total = strong_buy + buy + hold + sell + strong_sell
        if total == 0:
            return _default()

        bullish = strong_buy + buy
        bearish = sell + strong_sell

        weighted = (strong_buy * 100 + buy * 75 + hold * 50 + sell * 25 + strong_sell * 0)
        score = round(weighted / total)
        score = max(0, min(100, score))

        if score >= 65:
            label = "bullish"
        elif score <= 35:
            label = "bearish"
        else:
            label = "neutral"

        return {
            "score": score,
            "bullish": bullish,
            "bearish": bearish,
            "total": total,
            "volume": total,
            "label": label,
            "breakdown": {
                "strong_buy": strong_buy,
                "buy": buy,
                "hold": hold,
                "sell": sell,
                "strong_sell": strong_sell,
            },
            "top_messages": [],
        }

    except Exception as e:
        return _default(error=str(e)[:60])


def batch_stocktwits_sentiment(
    tickers: List[str],
    delay: float = 0.5,
) -> Dict[str, Dict[str, Any]]:
    """복수 미장 티커 일괄 애널리스트 감성 수집."""
    results: Dict[str, Dict[str, Any]] = {}
    for ticker in tickers:
        results[ticker] = fetch_stocktwits_sentiment(ticker)
        time.sleep(delay)
    return results


def _default(error: str = "") -> Dict[str, Any]:
    return {
        "score": 50,
        "bullish": 0,
        "bearish": 0,
        "total": 0,
        "volume": 0,
        "label": "neutral",
        "breakdown": {},
        "top_messages": [],
        "_error": error,
    }
