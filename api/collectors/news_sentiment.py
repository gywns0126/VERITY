"""
뉴스 감성 분석 모듈
네이버 뉴스에서 종목 관련 기사를 수집하고 감성 점수를 계산
"""
import re
import time
import requests
from typing import List, Dict

NAVER_NEWS_URL = "https://search.naver.com/search.naver"

POSITIVE_WORDS = [
    "상승", "급등", "돌파", "신고가", "최고", "호실적", "깜짝실적", "흑자전환",
    "수주", "대규모", "계약", "성장", "확대", "개선", "반등", "회복", "낙관",
    "목표가상향", "투자의견상향", "매수", "매출증가", "이익증가", "배당확대",
    "자사주매입", "인수합병", "신사업", "혁신", "수출호조", "점유율확대",
]

NEGATIVE_WORDS = [
    "하락", "급락", "폭락", "저점", "최저", "적자", "실적악화", "감소",
    "리스크", "우려", "경고", "하향", "목표가하향", "매도", "손실", "부진",
    "소송", "배임", "횡령", "상장폐지", "감사의견", "자본잠식", "분식",
    "공매도", "대규모매도", "외국인매도", "기관매도", "하회", "둔화",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept-Language": "ko-KR,ko;q=0.9",
}


def fetch_news_headlines(query: str, count: int = 10) -> List[str]:
    """네이버 뉴스 검색에서 헤드라인 수집 (SPA 대응: JSON 내 title 추출)"""
    try:
        params = {
            "where": "news",
            "query": query,
            "sort": "1",
            "start": "1",
        }
        resp = requests.get(NAVER_NEWS_URL, params=params, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        html = resp.text

        titles = re.findall(r'"title":"([^"]{5,120})"', html)
        cleaned = []
        skip_words = ["네이버", "검색", "뉴스", "더보기", "관련"]
        for t in titles:
            t = re.sub(r"<[^>]+>", "", t)
            t = t.replace("\\", "")
            if any(sw == t for sw in skip_words):
                continue
            if len(t) < 8:
                continue
            cleaned.append(t)
        return cleaned[:count]
    except Exception:
        return []


def analyze_sentiment(headlines: List[str]) -> Dict:
    """헤드라인 목록에서 감성 점수 계산"""
    if not headlines:
        return {"score": 50, "positive": 0, "negative": 0, "headline_count": 0, "top_headlines": []}

    pos_count = 0
    neg_count = 0
    for title in headlines:
        for w in POSITIVE_WORDS:
            if w in title:
                pos_count += 1
        for w in NEGATIVE_WORDS:
            if w in title:
                neg_count += 1

    total = pos_count + neg_count
    if total == 0:
        score = 50
    else:
        score = round((pos_count / total) * 100)

    return {
        "score": score,
        "positive": pos_count,
        "negative": neg_count,
        "headline_count": len(headlines),
        "top_headlines": headlines[:3],
    }


def get_stock_sentiment(name: str) -> Dict:
    """종목명으로 뉴스 감성 분석"""
    headlines = fetch_news_headlines(f"{name} 주가")
    result = analyze_sentiment(headlines)
    time.sleep(0.5)
    return result
