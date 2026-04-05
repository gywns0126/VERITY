"""
헤드라인 뉴스 수집 모듈
- 네이버 금융 주요 뉴스 (시장 전반)
- 호재/악재 자동 분류
- 공신력 × 긴급도 × 노이즈 최소화 기준 정렬
- Google News RSS: "Bloomberg Market" 검색 (블룸버그 웹 직접 스크래핑 없음)
"""
import requests
import re
import urllib.parse
from bs4 import BeautifulSoup

import feedparser


POSITIVE_KW = [
    "급등", "상한가", "사상최고", "최고치", "흑자전환", "호실적", "어닝서프라이즈",
    "순매수", "실적개선", "수주", "계약", "투자확대", "성장", "매출증가",
    "기관매수", "외국인매수", "반등", "돌파", "수혜", "기대감", "호재",
]

NEGATIVE_KW = [
    "급락", "하한가", "폭락", "적자", "적자전환", "하락", "손실",
    "실적부진", "악재", "매도", "공매도", "경고", "감사의견", "상폐",
    "상장폐지", "횡령", "배임", "분식", "리콜", "위반", "과징금",
    "하향", "리스크", "불안", "우려", "충격", "위기",
]

CREDIBLE_SOURCES = {
    "한국경제": 5, "매일경제": 5, "서울경제": 4, "조선비즈": 4,
    "이데일리": 4, "머니투데이": 4, "연합뉴스": 5, "뉴스핌": 3,
    "파이낸셜뉴스": 4, "헤럴드경제": 3, "아시아경제": 3, "ZDNet": 3,
    "전자신문": 3, "디지털타임스": 3, "블룸버그": 5, "로이터": 5,
}

GOOGLE_NEWS_UA = (
    "Mozilla/5.0 (compatible; VERITY/1.0; +https://github.com; headline RSS reader)"
)


def collect_headlines(max_items: int = 20) -> list:
    """네이버 금융 주요 뉴스 수집 + 호악재 분류 + 정렬"""
    raw = []
    raw.extend(_naver_market_news())
    raw.extend(_naver_economy_news())

    seen_titles = set()
    unique = []
    for item in raw:
        title_key = re.sub(r"[^가-힣a-zA-Z0-9]", "", item["title"])
        if title_key not in seen_titles:
            seen_titles.add(title_key)
            unique.append(item)

    for item in unique:
        item["sentiment"] = _classify_sentiment(item["title"])
        item["credibility"] = _score_credibility(item.get("source", ""))
        item["urgency"] = _score_urgency(item)
        item["composite_score"] = (
            item["credibility"] * 0.4
            + item["urgency"] * 0.3
            + (1.0 if item["sentiment"] != "neutral" else 0.3) * 0.3
        )

    unique.sort(key=lambda x: x["composite_score"], reverse=True)
    return unique[:max_items]


def _naver_market_news() -> list:
    """네이버 금융 - 시장 주요 뉴스"""
    items = []
    try:
        url = "https://finance.naver.com/news/mainnews.naver"
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=10)
        resp.encoding = "euc-kr"
        soup = BeautifulSoup(resp.text, "html.parser")
        articles = soup.select("div.mainNewsList dl")
        for dl in articles[:20]:
            dd = dl.select_one("dd.articleSubject a") or dl.select_one("dd a")
            if not dd:
                continue
            title = dd.text.strip()
            if not title or len(title) < 5:
                continue
            link = dd.get("href", "")
            if link and not link.startswith("http"):
                link = "https://finance.naver.com" + link
            source_tag = dl.select_one("span.press")
            source = source_tag.text.strip() if source_tag else ""
            time_tag = dl.select_one("span.wdate")
            pub_time = time_tag.text.strip() if time_tag else ""
            items.append({"title": title, "link": link, "source": source, "time": pub_time, "category": "market"})
    except Exception:
        pass

    if not items:
        try:
            url = "https://finance.naver.com/news/mainnews.naver"
            headers = {"User-Agent": "Mozilla/5.0"}
            resp = requests.get(url, headers=headers, timeout=10)
            resp.encoding = "euc-kr"
            soup = BeautifulSoup(resp.text, "html.parser")
            for a in soup.select("a"):
                href = a.get("href", "")
                title = a.text.strip()
                if title and len(title) > 15 and "news_read" in href:
                    link = href if href.startswith("http") else "https://finance.naver.com" + href
                    items.append({"title": title, "link": link, "source": "", "time": "", "category": "market"})
                    if len(items) >= 15:
                        break
        except Exception:
            pass

    return items


def _naver_economy_news() -> list:
    """네이버 금융 - 경제 뉴스 (인기순)"""
    items = []
    try:
        url = "https://finance.naver.com/news/news_list.naver?mode=RANK"
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=10)
        resp.encoding = "euc-kr"
        soup = BeautifulSoup(resp.text, "html.parser")
        for a in soup.select("a"):
            href = a.get("href", "")
            title = a.text.strip()
            if title and len(title) > 15 and ("news_read" in href or "article_id" in href):
                link = href if href.startswith("http") else "https://finance.naver.com" + href
                items.append({"title": title, "link": link, "source": "", "time": "", "category": "economy"})
                if len(items) >= 10:
                    break
    except Exception:
        pass
    return items


def _classify_sentiment(title: str) -> str:
    pos = sum(1 for kw in POSITIVE_KW if kw in title)
    neg = sum(1 for kw in NEGATIVE_KW if kw in title)
    if pos > neg:
        return "positive"
    if neg > pos:
        return "negative"
    return "neutral"


def _score_credibility(source: str) -> float:
    for name, score in CREDIBLE_SOURCES.items():
        if name in source:
            return score / 5.0
    return 0.5


def _score_urgency(item: dict) -> float:
    title = item.get("title", "")
    score = 0.5
    urgent_words = ["속보", "긴급", "급등", "급락", "폭락", "폭등", "사상최고", "사상최저", "역대", "최초"]
    for w in urgent_words:
        if w in title:
            score += 0.2
    return min(score, 1.0)


def collect_bloomberg_google_news_rss(max_items: int = 15) -> list:
    """
    Google News RSS — 검색어 'Bloomberg Market'.
    원문 사이트가 아닌 Google News 집계 피드만 사용.
    """
    q = urllib.parse.quote("Bloomberg Market")
    url = f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
    items = []
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": GOOGLE_NEWS_UA},
            timeout=15,
        )
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        for ent in feed.entries:
            title = (ent.get("title") or "").strip()
            if not title or len(title) < 8:
                continue
            link = (ent.get("link") or "").strip()
            published = (ent.get("published") or ent.get("updated") or "").strip()
            src = ""
            s = ent.get("source")
            if isinstance(s, dict):
                src = (s.get("title") or "").strip()
            elif hasattr(s, "title"):
                src = (getattr(s, "title", None) or "").strip()
            items.append({
                "title": title,
                "link": link,
                "source": src or "Google News",
                "time": published,
                "category": "bloomberg_google",
            })
            if len(items) >= max_items:
                break
    except Exception:
        pass
    return items
