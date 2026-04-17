"""
X(트위터) 시장 감성 분석기
주요 경제 인사·인플루언서 트윗을 수집하여 시장 정서 파악.

전략: RSS/Nitter 없이 검색 기반 수집 (API 키 불필요)
→ 네이버/구글 뉴스에서 "트위터 머스크" 등 2차 보도를 수집
→ 직접 X API 호출 없이도 주요 발언 포착 가능
"""
import re
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Optional

TRACKED_FIGURES = {
    # ── 중앙은행/정부 (최고 가중치) ──
    "powell": {"name": "제롬 파월", "weight": 5, "keywords": ["금리", "인플레이션", "연준", "FOMC", "Fed"]},
    "yellen": {"name": "재닛 옐런", "weight": 4, "keywords": ["재무부", "부채한도", "달러", "국채"]},
    "lagarde": {"name": "라가르드", "weight": 4, "keywords": ["ECB", "유럽", "유로", "금리"]},
    "trump": {"name": "트럼프", "weight": 5, "keywords": ["관세", "무역", "중국", "제재", "대통령"]},
    # ── 전설적 투자자 ──
    "warenbuffett": {"name": "워런 버핏", "weight": 4, "keywords": ["버크셔", "가치투자", "현금"]},
    "michaelburry": {"name": "마이클 버리", "weight": 3, "keywords": ["공매도", "버블", "붕괴", "빅숏"]},
    "raydalio": {"name": "레이 달리오", "weight": 3, "keywords": ["브릿지워터", "올웨더", "부채사이클"]},
    "larryfink": {"name": "래리 핑크", "weight": 3, "keywords": ["블랙록", "ETF", "토큰화", "ESG"]},
    "druckenmiller": {"name": "드러켄밀러", "weight": 3, "keywords": ["매크로", "포지션", "채권"]},
    "ackman": {"name": "빌 애크먼", "weight": 2, "keywords": ["퍼싱", "행동주의", "숏"]},
    # ── 테크/미디어 인플루언서 ──
    "elonmusk": {"name": "일론 머스크", "weight": 3, "keywords": ["테슬라", "SpaceX", "도지", "AI", "X"]},
    "cathiewood": {"name": "캐시 우드", "weight": 2, "keywords": ["ARK", "혁신", "테슬라", "비트코인"]},
    "jimcramer": {"name": "짐 크레이머", "weight": 1, "keywords": ["CNBC", "매수", "매도"]},
    # ── 한국 ──
    "leechangyong": {"name": "이창용", "weight": 5, "keywords": ["한은", "기준금리", "총재", "통화정책"]},
    "choiSW": {"name": "최상목", "weight": 4, "keywords": ["기재부", "경제부총리", "재정"]},
}

MARKET_KEYWORDS_KR = [
    "트위터 주식 시장",
    "X 머스크 발언", "X 트럼프 발언",
    "파월 금리 발언", "옐런 발언", "라가르드 금리",
    "캐시우드", "버핏 투자", "마이클버리",
    "드러켄밀러", "래리핑크 블랙록", "레이달리오", "빌애크먼",
    "트럼프 관세 무역",
    "이창용 한은 기준금리",
]

STRONG_POS = ["강세", "매수", "상승", "호재", "낙관", "회복", "서프라이즈", "금리 인하", "완화", "바닥"]
STRONG_NEG = ["폭락", "매도", "공매도", "버블", "붕괴", "위기", "경고", "긴축", "디폴트", "전쟁", "제재"]
MILD_POS = ["성장", "투자", "확대", "기대", "수요", "신고가", "반등", "돌파", "실적 호조"]
MILD_NEG = ["우려", "하락", "둔화", "리스크", "약세", "축소", "인플레", "관세", "규제", "과열"]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept-Language": "ko-KR,ko;q=0.9",
}
NAVER_SEARCH = "https://search.naver.com/search.naver"
GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"

MARKET_KEYWORDS_EN = [
    "Powell Fed rate", "Yellen treasury",
    "Trump tariff trade", "Lagarde ECB rate",
    "Elon Musk stock", "Buffett Berkshire",
    "Burry short", "Cathie Wood ARK",
    "Druckenmiller macro",
]


def _search_naver_news(query: str, count: int = 5) -> List[Dict]:
    """네이버 뉴스에서 키워드 검색 → 제목+요약 수집"""
    try:
        params = {"where": "news", "query": query, "sort": "1", "start": "1"}
        resp = requests.get(NAVER_SEARCH, params=params, headers=HEADERS, timeout=5)
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


def _search_google_news_rss(query: str, count: int = 5) -> List[Dict]:
    """Google News RSS에서 영문 키워드 검색 → 제목 수집"""
    try:
        params = {"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"}
        resp = requests.get(GOOGLE_NEWS_RSS, params=params, headers=HEADERS, timeout=5)
        resp.raise_for_status()
        titles = re.findall(r"<title>(.{10,200}?)</title>", resp.text)
        titles = [t for t in titles if t != "Google News"]
        return [{"text": t[:150], "source": "google_news"} for t in titles[:count]]
    except Exception:
        return []


_EN_POS = ["bullish", "rally", "surge", "beat", "upgrade", "cut rate", "easing", "buy"]
_EN_NEG = ["crash", "plunge", "tariff", "sanction", "sell-off", "recession", "war", "default", "downgrade"]


def _score_tweet(text: str) -> tuple:
    """텍스트 감성 점수 (-5 ~ +5)"""
    score = 0
    tl = text.lower()
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
    for w in _EN_POS:
        if w in tl:
            score += 2
    for w in _EN_NEG:
        if w in tl:
            score -= 2

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


def _fetch_task(fn, query, source_label, count):
    """병렬 워커가 실행하는 단위 작업."""
    try:
        return fn(query, count=count), source_label
    except Exception:
        return [], source_label


def collect_x_sentiment(max_items: int = 40) -> Dict:
    """
    X 시장 감성 수집.
    네이버 뉴스 + Google News RSS에서 주요 인사 발언 관련 보도를 병렬 수집하여 감성 분석.
    """
    tasks = []
    for q in MARKET_KEYWORDS_KR:
        tasks.append((_search_naver_news, q, "naver", 4))
    for q in MARKET_KEYWORDS_EN:
        tasks.append((_search_google_news_rss, q, "google", 3))

    raw_results: List[tuple] = []
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {
            executor.submit(_fetch_task, fn, q, src, cnt): src
            for fn, q, src, cnt in tasks
        }
        for future in as_completed(futures, timeout=20):
            try:
                items, src = future.result(timeout=6)
                raw_results.append((items, src))
            except Exception:
                pass

    all_items = []
    seen: set = set()
    for items, source_label in raw_results:
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
                    "source": source_label,
                })

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
