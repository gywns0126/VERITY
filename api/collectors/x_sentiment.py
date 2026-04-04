"""
X(트위터) 시장 감성 분석기
주요 경제 인사·인플루언서 트윗을 수집하여 시장 정서 파악.

전략: RSS/Nitter 없이 검색 기반 수집 (API 키 불필요)
→ 네이버/구글 뉴스에서 "트위터 머스크" 등 2차 보도를 수집
→ 직접 X API 호출 없이도 주요 발언 포착 가능
"""
import re
import time
import requests
from typing import List, Dict, Optional
from bs4 import BeautifulSoup

TRACKED_FIGURES = {
    "elonmusk": {"name": "일론 머스크", "weight": 3, "keywords": ["테슬라", "SpaceX", "도지", "AI"]},
    "powell": {"name": "제롬 파월", "weight": 5, "keywords": ["금리", "인플레이션", "연준", "FOMC"]},
    "yellen": {"name": "재닛 옐런", "weight": 4, "keywords": ["재무부", "부채한도", "달러"]},
    "cathiewood": {"name": "캐시 우드", "weight": 2, "keywords": ["ARK", "혁신", "테슬라", "비트코인"]},
    "jimcramer": {"name": "짐 크레이머", "weight": 1, "keywords": ["CNBC", "매수", "매도"]},
    "michaelburry": {"name": "마이클 버리", "weight": 3, "keywords": ["공매도", "버블", "붕괴"]},
    "warenbuffett": {"name": "워런 버핏", "weight": 4, "keywords": ["버크셔", "가치투자", "현금"]},
}

MARKET_KEYWORDS_KR = [
    "트위터 주식", "트위터 시장", "트위터 경제", "X 머스크 발언",
    "파월 발언", "파월 금리", "옐런 발언", "캐시우드",
    "버핏 투자", "마이클버리", "짐크레이머",
]

STRONG_POS = ["강세", "매수", "상승", "호재", "낙관", "회복", "서프라이즈"]
STRONG_NEG = ["폭락", "매도", "공매도", "버블", "붕괴", "위기", "경고", "긴축"]
MILD_POS = ["성장", "투자", "확대", "기대", "수요", "신고가"]
MILD_NEG = ["우려", "하락", "둔화", "리스크", "약세", "축소", "인플레"]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept-Language": "ko-KR,ko;q=0.9",
}
NAVER_SEARCH = "https://search.naver.com/search.naver"


def _search_naver_news(query: str, count: int = 5) -> List[Dict]:
    """네이버 뉴스에서 키워드 검색 → 제목+요약 수집"""
    try:
        params = {"where": "news", "query": query, "sort": "1", "start": "1"}
        resp = requests.get(NAVER_SEARCH, params=params, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        html = resp.text

        titles = re.findall(r'"title":"([^"]{5,150})"', html)
        cleaned = []
        for t in titles[:count]:
            t = re.sub(r"<[^>]+>", "", t).replace("\\", "").strip()
            if len(t) >= 10:
                cleaned.append(t)
        return [{"text": t, "source": "naver_news"} for t in cleaned]
    except Exception:
        return []


def _score_tweet(text: str) -> tuple:
    """텍스트 감성 점수 (-5 ~ +5)"""
    score = 0
    for w in STRONG_POS:
        if w in text:
            score += 2
    for w in MILD_POS:
        if w in text:
            score += 1
    for w in STRONG_NEG:
        if w in text:
            score -= 2
    for w in MILD_NEG:
        if w in text:
            score -= 1

    if score > 0:
        return score, "positive"
    elif score < 0:
        return score, "negative"
    return 0, "neutral"


def _identify_figure(text: str) -> Optional[str]:
    """텍스트에서 추적 인물 식별"""
    text_lower = text.lower()
    for handle, info in TRACKED_FIGURES.items():
        name = info["name"]
        if name in text or handle in text_lower:
            return handle
        for kw in info["keywords"]:
            if kw in text and name[:2] in text:
                return handle
    return None


def collect_x_sentiment(max_items: int = 30) -> Dict:
    """
    X 시장 감성 수집.
    네이버 뉴스에서 주요 인사 발언 관련 보도를 수집하여 감성 분석.
    """
    all_items = []
    seen = set()

    for query in MARKET_KEYWORDS_KR:
        items = _search_naver_news(query, count=4)
        for item in items:
            text = item["text"]
            if text not in seen:
                seen.add(text)
                figure = _identify_figure(text)
                weight = TRACKED_FIGURES[figure]["weight"] if figure else 1
                score, label = _score_tweet(text)
                all_items.append({
                    "text": text,
                    "figure": TRACKED_FIGURES[figure]["name"] if figure else None,
                    "score": score,
                    "label": label,
                    "weight": weight,
                })
        time.sleep(0.3)

    all_items.sort(key=lambda x: abs(x["score"]) * x["weight"], reverse=True)
    all_items = all_items[:max_items]

    pos = sum(1 for i in all_items if i["label"] == "positive")
    neg = sum(1 for i in all_items if i["label"] == "negative")
    neutral = len(all_items) - pos - neg

    weighted_sum = sum(i["score"] * i["weight"] for i in all_items)
    total_weight = sum(i["weight"] for i in all_items) or 1
    raw = weighted_sum / total_weight
    composite_score = int(max(0, min(100, 50 + raw * 8)))

    figure_mentions = {}
    for item in all_items:
        if item["figure"]:
            fig = item["figure"]
            if fig not in figure_mentions:
                figure_mentions[fig] = {"count": 0, "sentiment": 0}
            figure_mentions[fig]["count"] += 1
            figure_mentions[fig]["sentiment"] += item["score"]

    key_figures = []
    for name, data in sorted(figure_mentions.items(), key=lambda x: x[1]["count"], reverse=True)[:5]:
        mood = "긍정" if data["sentiment"] > 0 else "부정" if data["sentiment"] < 0 else "중립"
        key_figures.append({"name": name, "mentions": data["count"], "mood": mood})

    return {
        "score": composite_score,
        "positive": pos,
        "negative": neg,
        "neutral": neutral,
        "tweet_count": len(all_items),
        "tweets": [i["text"] for i in all_items[:10]],
        "key_figures": key_figures,
        "top_signals": [
            {"text": i["text"][:60], "figure": i["figure"], "label": i["label"]}
            for i in all_items[:5]
        ],
    }
