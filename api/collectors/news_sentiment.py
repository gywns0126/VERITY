"""
뉴스 감성 분석 모듈 v3 (미장 확장)
- 다중 쿼리 (주가/실적/공시)로 헤드라인 폭 확대
- 헤드라인별 1표 방식으로 감성 왜곡 방지
- 가중 키워드 (강한 긍정/부정 구분)
- 최근성 가중 (상위 결과에 더 높은 가중)
- v2.1: 기사 URL 함께 수집 → top_headline_links 저장
- v3: 영문 뉴스(Google News RSS) + 영문 키워드 사전 추가
"""
import re
import time
import requests
from typing import List, Dict, Tuple, Optional
from bs4 import BeautifulSoup

NAVER_NEWS_URL = "https://search.naver.com/search.naver"

# ── 한국어 감성 사전 ──
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

# ── 영문 감성 사전 ──
STRONG_POSITIVE_EN = [
    "all-time high", "record high", "beat expectations", "blowout earnings",
    "massive buyback", "upgrade", "price target raised", "dividend hike",
    "market share gains", "blockbuster",
]
POSITIVE_WORDS_EN = [
    "rally", "surge", "breakout", "bullish", "growth", "beat", "gains",
    "rebound", "recovery", "optimistic", "buy", "revenue growth", "profit",
    "acquisition", "innovation", "strong demand", "outperform", "upside",
]
STRONG_NEGATIVE_EN = [
    "delisting", "fraud", "bankruptcy", "sec investigation", "crash",
    "massive loss", "default", "accounting scandal", "class action",
]
NEGATIVE_WORDS_EN = [
    "decline", "plunge", "drop", "bearish", "loss", "miss", "warning",
    "downgrade", "sell", "lawsuit", "risk", "weak", "slowdown",
    "short selling", "underperform", "downside", "layoffs", "recession",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept-Language": "ko-KR,ko;q=0.9",
}


def fetch_news_with_links(query: str, count: int = 10) -> List[Dict[str, str]]:
    """네이버 뉴스 검색에서 헤드라인 + 기사 URL 수집.

    Returns:
        [{"title": str, "url": str}, ...]
    """
    skip_words = {"네이버", "검색", "뉴스", "더보기", "관련"}
    try:
        params = {"where": "news", "query": query, "sort": "1", "start": "1"}
        resp = requests.get(NAVER_NEWS_URL, params=params, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        html = resp.text
        soup = BeautifulSoup(html, "html.parser")

        results: List[Dict[str, str]] = []
        seen: set = set()

        # 방법 1: BeautifulSoup — a.news_tit 선택자 (네이버 뉴스 검색 표준 마크업)
        for a in soup.select("a.news_tit"):
            title = (a.get("title") or a.text).strip()
            title = re.sub(r"<[^>]+>", "", title).replace("\\", "").strip()
            url = a.get("href", "")
            if title and len(title) >= 8 and url and title not in seen and title not in skip_words:
                seen.add(title)
                results.append({"title": title, "url": url})

        # 방법 2: JSON 임베드 regex fallback (네이버 SSR JSON 구조 대응)
        if not results:
            raw_titles = re.findall(r'"title":"([^"]{5,120})"', html)
            raw_links  = re.findall(r'"link":"(https?://[^"]+)"', html)
            for t, l in zip(raw_titles, raw_links):
                t = re.sub(r"<[^>]+>", "", t).replace("\\", "").strip()
                if t and len(t) >= 8 and t not in skip_words and t not in seen:
                    seen.add(t)
                    results.append({"title": t, "url": l})

        return results[:count]
    except Exception:
        return []


def fetch_news_headlines(query: str, count: int = 10) -> List[str]:
    """하위 호환 래퍼 — 제목만 반환."""
    return [item["title"] for item in fetch_news_with_links(query, count)]


def _fetch_google_news_rss(query: str, count: int = 10) -> List[Dict[str, str]]:
    """Google News RSS로 영문 헤드라인 + URL 수집."""
    try:
        url = f"https://news.google.com/rss/search?q={requests.utils.quote(query)}&hl=en-US&gl=US&ceid=US:en"
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        import xml.etree.ElementTree as ET
        root = ET.fromstring(resp.content)
        results: List[Dict[str, str]] = []
        for item in root.iter("item"):
            title_el = item.find("title")
            link_el = item.find("link")
            if title_el is not None and title_el.text:
                title = re.sub(r"<[^>]+>", "", title_el.text).strip()
                link = link_el.text.strip() if link_el is not None and link_el.text else ""
                if title and len(title) >= 8:
                    results.append({"title": title, "url": link})
            if len(results) >= count:
                break
        return results
    except Exception:
        return []


def _score_headline_en(title: str) -> Tuple[float, str]:
    """영문 헤드라인 감성 판정."""
    weight = 0
    lower = title.lower()
    for w in STRONG_POSITIVE_EN:
        if w in lower:
            weight += 2
    for w in POSITIVE_WORDS_EN:
        if w in lower:
            weight += 1
    for w in STRONG_NEGATIVE_EN:
        if w in lower:
            weight -= 2
    for w in NEGATIVE_WORDS_EN:
        if w in lower:
            weight -= 1
    if weight > 0:
        return weight, "positive"
    elif weight < 0:
        return weight, "negative"
    return 0, "neutral"


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


def analyze_sentiment(headlines: List, lang: str = "kr") -> Dict:
    """헤드라인 목록에서 감성 점수 계산 (헤드라인별 1표 + 최근성 가중).

    Args:
        headlines: str 리스트 또는 {"title": str, "url": str} dict 리스트 모두 허용.
        lang: 'kr' | 'en' — 감성 사전 분기
    """
    if not headlines:
        return {
            "score": 50, "positive": 0, "negative": 0, "neutral": 0,
            "headline_count": 0, "top_headlines": [], "top_headline_links": [], "detail": [],
        }

    pos_count = 0
    neg_count = 0
    neutral_count = 0
    weighted_sum = 0.0
    total_weight = 0.0
    detail = []

    for i, h in enumerate(headlines):
        # str / dict 양쪽 지원
        if isinstance(h, dict):
            title = h.get("title", "")
            url   = h.get("url", "")
        else:
            title = str(h)
            url   = ""

        recency = 1.0 + (len(headlines) - i) * 0.1
        score_fn = _score_headline_en if lang == "en" else _score_headline
        weight, label = score_fn(title)
        weighted_sum += weight * recency
        total_weight += recency

        if label == "positive":
            pos_count += 1
        elif label == "negative":
            neg_count += 1
        else:
            neutral_count += 1

        source_type = ""
        if isinstance(h, dict):
            source_type = h.get("source_type", "")
        detail.append({"title": title, "url": url, "label": label, "weight": weight, "source_type": source_type})

    if total_weight == 0:
        score = 50
    else:
        raw = (weighted_sum / total_weight)
        score = int(max(0, min(100, 50 + raw * 10)))

    top5 = detail[:5]
    return {
        "score": score,
        "positive": pos_count,
        "negative": neg_count,
        "neutral": neutral_count,
        "headline_count": len(headlines),
        "top_headlines": [h["title"] for h in top5],
        "top_headline_links": [{"title": h["title"], "url": h["url"]} for h in top5],
        "detail": top5,
    }


def _merge_newsapi(ticker: str, name: str, items: List[Dict[str, str]], seen: set) -> List[Dict[str, str]]:
    """NewsAPI 결과를 기존 수집 항목에 병합 (API 키가 있을 때만)."""
    try:
        from api.config import NEWS_API_KEY
        if not NEWS_API_KEY:
            return items
        from api.collectors.newsapi_client import get_us_stock_news
        api_articles = get_us_stock_news(ticker, name, NEWS_API_KEY, days=3, max_articles=15)
        for a in api_articles:
            title = a.get("title", "")
            if title and title not in seen:
                seen.add(title)
                items.append({
                    "title": title,
                    "url": a.get("url", ""),
                    "source": a.get("source", ""),
                    "description": a.get("description", ""),
                    "source_type": "newsapi",
                })
    except Exception:
        pass
    return items


def get_stock_sentiment(name: str, market: str = "KR", ticker: str = "") -> Dict:
    """종목명으로 다중 쿼리 뉴스 감성 분석 (제목 + URL 포함).

    Args:
        name: 종목명 (KR) 또는 영문 사명/티커 (US)
        market: 'KR' | 'US' 등 — US 계열이면 Google News RSS + 영문 사전 사용
        ticker: US 종목 티커 (NewsAPI 병합에 사용)
    """
    is_us = market.upper() not in ("KR", "KOSPI", "KOSDAQ")

    all_items: List[Dict[str, str]] = []
    seen: set = set()

    if is_us:
        for query in [f"{name} stock", f"{name} earnings", f"{name} SEC filing"]:
            for item in _fetch_google_news_rss(query, count=8):
                if item["title"] not in seen:
                    seen.add(item["title"])
                    item["source_type"] = "google_rss"
                    all_items.append(item)
            time.sleep(0.3)

        all_items = _merge_newsapi(ticker or name, name, all_items, seen)

        result = analyze_sentiment(all_items[:25], lang="en")
        result["detail"] = [
            {**d, "source": next((a.get("source", "") for a in all_items if a.get("title") == d["title"]), "")}
            for d in result.get("detail", [])
        ]
        return result
    else:
        for query in [f"{name} 주가", f"{name} 실적", f"{name} 공시"]:
            for item in fetch_news_with_links(query, count=8):
                if item["title"] not in seen:
                    seen.add(item["title"])
                    item["source_type"] = "naver"
                    all_items.append(item)
            time.sleep(0.3)
        return analyze_sentiment(all_items[:15], lang="kr")
