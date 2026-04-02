"""
뉴스 감성 분석 모듈 v2 (Sprint 3)
- 다중 쿼리 (주가/실적/공시)로 헤드라인 폭 확대
- 헤드라인별 1표 방식으로 감성 왜곡 방지
- 가중 키워드 (강한 긍정/부정 구분)
- 최근성 가중 (상위 결과에 더 높은 가중)
"""
import re
import time
import requests
from typing import List, Dict, Tuple

NAVER_NEWS_URL = "https://search.naver.com/search.naver"

STRONG_POSITIVE = [
    "신고가", "호실적", "깜짝실적", "흑자전환", "대규모수주", "목표가상향",
    "투자의견상향", "자사주매입", "배당확대", "점유율확대",
]
POSITIVE_WORDS = [
    "상승", "급등", "돌파", "최고", "수주", "계약", "성장", "확대", "개선",
    "반등", "회복", "낙관", "매수", "매출증가", "이익증가", "인수합병",
    "신사업", "혁신", "수출호조", "호재", "강세", "기대감",
]
STRONG_NEGATIVE = [
    "상장폐지", "자본잠식", "분식회계", "감사의견거절", "횡령", "배임",
    "실적악화", "폭락", "대규모적자",
]
NEGATIVE_WORDS = [
    "하락", "급락", "저점", "최저", "적자", "감소", "리스크", "우려", "경고",
    "하향", "목표가하향", "매도", "손실", "부진", "소송", "공매도",
    "대규모매도", "외국인매도", "기관매도", "하회", "둔화", "악재", "약세",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept-Language": "ko-KR,ko;q=0.9",
}


def fetch_news_headlines(query: str, count: int = 10) -> List[str]:
    """네이버 뉴스 검색에서 헤드라인 수집"""
    try:
        params = {"where": "news", "query": query, "sort": "1", "start": "1"}
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


def _score_headline(title: str) -> Tuple[float, str]:
    """
    헤드라인 1개의 감성을 판정 (1표 방식).
    강한 키워드(±2), 일반 키워드(±1). 최종 합산으로 pos/neg/neutral 판정.
    """
    weight = 0
    for w in STRONG_POSITIVE:
        if w in title:
            weight += 2
    for w in POSITIVE_WORDS:
        if w in title:
            weight += 1
    for w in STRONG_NEGATIVE:
        if w in title:
            weight -= 2
    for w in NEGATIVE_WORDS:
        if w in title:
            weight -= 1

    if weight > 0:
        return weight, "positive"
    elif weight < 0:
        return weight, "negative"
    return 0, "neutral"


def analyze_sentiment(headlines: List[str]) -> Dict:
    """헤드라인 목록에서 감성 점수 계산 (헤드라인별 1표 + 최근성 가중)"""
    if not headlines:
        return {
            "score": 50, "positive": 0, "negative": 0, "neutral": 0,
            "headline_count": 0, "top_headlines": [], "detail": [],
        }

    pos_count = 0
    neg_count = 0
    neutral_count = 0
    weighted_sum = 0.0
    total_weight = 0.0
    detail = []

    for i, title in enumerate(headlines):
        recency = 1.0 + (len(headlines) - i) * 0.1
        weight, label = _score_headline(title)
        weighted_sum += weight * recency
        total_weight += recency

        if label == "positive":
            pos_count += 1
        elif label == "negative":
            neg_count += 1
        else:
            neutral_count += 1

        detail.append({"title": title, "label": label, "weight": weight})

    if total_weight == 0:
        score = 50
    else:
        raw = (weighted_sum / total_weight)
        score = int(max(0, min(100, 50 + raw * 10)))

    return {
        "score": score,
        "positive": pos_count,
        "negative": neg_count,
        "neutral": neutral_count,
        "headline_count": len(headlines),
        "top_headlines": [h["title"] for h in detail[:5]],
        "detail": detail[:5],
    }


def get_stock_sentiment(name: str) -> Dict:
    """종목명으로 다중 쿼리 뉴스 감성 분석"""
    all_headlines = []
    seen = set()
    for query in [f"{name} 주가", f"{name} 실적", f"{name} 공시"]:
        for h in fetch_news_headlines(query, count=8):
            if h not in seen:
                seen.add(h)
                all_headlines.append(h)
        time.sleep(0.3)

    result = analyze_sentiment(all_headlines[:15])
    return result
