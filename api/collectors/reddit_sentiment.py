"""
Reddit 감성 수집 (인증 불필요 JSON API).
영문 종목(미장) 대상. r/wallstreetbets, r/stocks, r/investing.
"""
import time
from typing import Any, Dict, List

import requests

SUBREDDITS = ["wallstreetbets", "stocks", "investing"]
REDDIT_SEARCH = "https://www.reddit.com/r/{sub}/search.json"
HEADERS = {"User-Agent": "VERITY-StockBot/1.0"}
_TIMEOUT = 12

BULLISH_KW = [
    "buy", "bullish", "moon", "calls", "long", "undervalued", "breakout",
    "rocket", "squeeze", "yolo", "dip", "upside", "strong", "beat",
    "earnings beat", "upgrade", "growth",
]
BEARISH_KW = [
    "sell", "bearish", "puts", "short", "overvalued", "crash", "dump",
    "bag", "loss", "drill", "downside", "weak", "miss", "downgrade",
    "earnings miss", "recession", "bubble",
]


def fetch_reddit_sentiment(
    ticker: str,
    limit: int = 30,
    delay: float = 1.5,
) -> Dict[str, Any]:
    """
    Reddit에서 ticker 관련 최근 게시물 검색 → 감성 점수.
    Returns: {score, positive, negative, volume, top_posts}
    """
    all_posts: List[Dict[str, Any]] = []

    for sub in SUBREDDITS:
        try:
            resp = requests.get(
                REDDIT_SEARCH.format(sub=sub),
                params={
                    "q": ticker,
                    "sort": "new",
                    "t": "week",
                    "limit": limit,
                    "restrict_sr": "on",
                },
                headers=HEADERS,
                timeout=_TIMEOUT,
            )
            if resp.status_code == 200:
                data = resp.json().get("data", {})
                children = data.get("children", [])
                for child in children:
                    d = child.get("data", {})
                    all_posts.append({
                        "title": d.get("title", ""),
                        "score": d.get("score", 0),
                        "upvote_ratio": d.get("upvote_ratio", 0.5),
                        "num_comments": d.get("num_comments", 0),
                        "subreddit": sub,
                    })
        except Exception:
            pass
        time.sleep(delay)

    if not all_posts:
        return {"score": 50, "positive": 0, "negative": 0, "volume": 0, "top_posts": []}

    pos_count = 0
    neg_count = 0
    for post in all_posts:
        tl = post["title"].lower()
        p = sum(1 for kw in BULLISH_KW if kw in tl)
        n = sum(1 for kw in BEARISH_KW if kw in tl)
        weight = 1 + (post["upvote_ratio"] - 0.5) * 2
        if p > n:
            pos_count += weight
        elif n > p:
            neg_count += weight

    total = pos_count + neg_count
    if total < 0.1:
        score = 50
    else:
        score = round(50 + (pos_count - neg_count) / total * 40)
        score = max(0, min(100, score))

    top_sorted = sorted(all_posts, key=lambda x: x["score"], reverse=True)[:5]
    top_posts = [
        {"title": p["title"], "score": p["score"], "sub": p["subreddit"]}
        for p in top_sorted
    ]

    return {
        "score": score,
        "positive": round(pos_count),
        "negative": round(neg_count),
        "volume": len(all_posts),
        "top_posts": top_posts,
    }


def batch_reddit_sentiment(
    tickers: List[str],
    limit: int = 20,
) -> Dict[str, Dict[str, Any]]:
    """복수 영문 티커 일괄 수집."""
    results: Dict[str, Dict[str, Any]] = {}
    for ticker in tickers:
        results[ticker] = fetch_reddit_sentiment(ticker, limit=limit)
        time.sleep(2)
    return results
