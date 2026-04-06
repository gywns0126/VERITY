"""
네이버 금융 종목토론 게시판 스크래핑 → 커뮤니티 감성 점수.
news_sentiment.py와 동일한 인터페이스(score, positive, negative, volume).
"""
import re
import time
from typing import Any, Dict, List

import requests
from bs4 import BeautifulSoup

DISCUSSION_URL = "https://finance.naver.com/item/board.naver"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept-Language": "ko-KR,ko;q=0.9",
}

POSITIVE_KW = [
    "매수", "상승", "기대", "좋다", "추천", "반등", "강세", "호재",
    "돌파", "배당", "실적", "갈만", "올라", "사자", "수주", "계약",
    "성장", "저평가", "대박", "기회", "지지", "바닥", "모아",
]
NEGATIVE_KW = [
    "매도", "하락", "폭락", "손절", "위험", "물타", "악재", "고점",
    "팔자", "떨어", "개미", "물렸", "하한", "주의", "적자", "망",
    "탈출", "패닉", "손해", "빠져", "상폐", "사기", "하방",
]


def fetch_community_sentiment(
    stock_code: str,
    pages: int = 3,
    delay: float = 0.3,
) -> Dict[str, Any]:
    """
    네이버 종목토론에서 최근 게시글 제목을 긁어 감성 점수 산출.
    Returns: {score, positive, negative, volume, titles_sample}
    """
    titles: List[str] = []
    for page in range(1, pages + 1):
        try:
            resp = requests.get(
                DISCUSSION_URL,
                params={"code": stock_code, "page": page},
                headers=HEADERS,
                timeout=8,
            )
            resp.encoding = "euc-kr"
            soup = BeautifulSoup(resp.text, "html.parser")
            rows = soup.select("table.type2 tr")
            for row in rows:
                subj = row.select_one("td.title a")
                if subj:
                    titles.append(subj.get_text(strip=True))
        except Exception:
            pass
        if page < pages:
            time.sleep(delay)

    if not titles:
        return {"score": 50, "positive": 0, "negative": 0, "volume": 0, "titles_sample": []}

    pos_count = 0
    neg_count = 0
    for t in titles:
        tl = t.lower()
        p = sum(1 for kw in POSITIVE_KW if kw in tl)
        n = sum(1 for kw in NEGATIVE_KW if kw in tl)
        if p > n:
            pos_count += 1
        elif n > p:
            neg_count += 1

    total = pos_count + neg_count
    if total == 0:
        score = 50
    else:
        score = round(50 + (pos_count - neg_count) / total * 40)
        score = max(0, min(100, score))

    return {
        "score": score,
        "positive": pos_count,
        "negative": neg_count,
        "volume": len(titles),
        "titles_sample": titles[:5],
    }


def batch_community_sentiment(
    stock_codes: List[str],
    pages: int = 2,
    delay: float = 0.4,
) -> Dict[str, Dict[str, Any]]:
    """복수 종목 일괄 수집. key = 종목코드."""
    results: Dict[str, Dict[str, Any]] = {}
    for code in stock_codes:
        results[code] = fetch_community_sentiment(code, pages=pages)
        time.sleep(delay)
    return results
