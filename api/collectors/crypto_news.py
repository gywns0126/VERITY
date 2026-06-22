"""코인 뉴스 — 크립토 RSS 헤드라인 팩트만.

🚨 RULE 6 (LLM narrative STOP): title/link/source/time 만. 요약·sentiment narrative·LLM 호출 0.
소스: Cointelegraph RSS + Google News(bitcoin OR crypto) 집계 피드. dedupe.
실패 시 빈 리스트(builder가 last-good 유지). 스키마 실호출 검증 완료(2026-06).
news_headlines.collect_bloomberg_google_news_rss 패턴 재사용.
"""
from __future__ import annotations

import re
import urllib.parse
from typing import Any, Dict, List

import feedparser
import requests

_TIMEOUT = 15
_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Verity-Terminal/1.0"

_FEEDS = [
    ("Cointelegraph", "https://cointelegraph.com/rss"),
    ("Google News", "https://news.google.com/rss/search?q="
        + urllib.parse.quote("bitcoin OR crypto OR ethereum") + "&hl=en-US&gl=US&ceid=US:en"),
]


def _parse_feed(name: str, url: str, max_items: int) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    try:
        resp = requests.get(url, headers={"User-Agent": _UA}, timeout=_TIMEOUT)
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        for ent in feed.entries:
            title = (ent.get("title") or "").strip()
            if not title or len(title) < 8:
                continue
            link = (ent.get("link") or "").strip()
            published = (ent.get("published") or ent.get("updated") or "").strip()
            src = name
            s = ent.get("source")
            if isinstance(s, dict):
                src = (s.get("title") or name).strip()
            elif hasattr(s, "title"):
                src = (getattr(s, "title", None) or name).strip()
            out.append({"title": title, "link": link, "source": src or name, "time": published})
            if len(out) >= max_items:
                break
    except Exception:  # noqa: BLE001
        pass
    return out


def collect_crypto_news(max_per: int = 20) -> List[Dict[str, Any]]:
    """다중 크립토 RSS → dedupe 헤드라인 리스트(팩트만)."""
    items: List[Dict[str, Any]] = []
    seen = set()
    for name, url in _FEEDS:
        for it in _parse_feed(name, url, max_per):
            key = re.sub(r"[^a-z0-9가-힣]", "", it["title"].lower())[:60]
            if not key or key in seen:
                continue
            seen.add(key)
            items.append(it)
    return items
