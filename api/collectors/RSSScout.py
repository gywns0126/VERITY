"""
RSSScout — 로이터/CNBC/야후 파이낸스 RSS 속보 스캔

- 제목만 사용(본문 미요청). mapping.json 티커 + raw_data 종목명 매칭,
  또는 BREAKING·EXCLUSIVE·URGENT·HALT 키워드 시 수집.
- data/raw_data.json 의 news_flash 에 병합(링크 기준 중복 제거).
- 보유 종목 + 제목에 BREAKING 이 동시에 있으면 텔레그램 속보 전송.
- 지정학·재난 키워드(영·한)가 신규 헤드라인에 있으면 텔레그램(링크 dedupe, RSS_GEO_TAIL_TELEGRAM).

선택: data/rss_en_aliases.json — {"005930": ["Samsung", "Samsung Electronics"]}
"""
from __future__ import annotations

import json
import os
import re
import sys
from calendar import timegm
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

import feedparser
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from api.config import (
    DATA_DIR,
    KST,
    PORTFOLIO_PATH,
    RSS_GEO_TAIL_DEDUPE_HOURS,
    RSS_GEO_TAIL_TELEGRAM,
    now_kst,
)
from api.notifications.telegram import send_message

MAPPING_PATH = os.path.join(DATA_DIR, "mapping.json")
RAW_DATA_PATH = os.path.join(DATA_DIR, "raw_data.json")
ALIASES_PATH = os.path.join(DATA_DIR, "rss_en_aliases.json")

FEEDS: List[Tuple[str, str]] = [
    ("Reuters", "http://feeds.reuters.com/reuters/businessNews"),
    ("CNBC", "https://www.cnbc.com/id/100003114/device/rss/rss.html"),
    ("Yahoo Finance", "https://finance.yahoo.com/news/rssindex"),
]

HIGH_INTENSITY = frozenset(
    x.upper() for x in ("BREAKING", "EXCLUSIVE", "URGENT", "HALT")
)

NEWS_FLASH_MAX = 200
NEWS_FLASH_PATH = os.path.join(DATA_DIR, "news_flash.json")
USER_AGENT = (
    "VERITY-RSSScout/1.0 (+https://github.com; lightweight headline scanner)"
)

_GEO_EN = (
    "earthquake",
    "tsunami",
    "wildfire",
    "airstrike",
    "air strike",
    "ballistic missile",
    "military invasion",
    "terrorist attack",
    "declaration of war",
    "armed conflict",
    "military strike",
)
_GEO_KO = (
    "지진",
    "쓰나미",
    "대형 산불",
    "미사일",
    "전쟁",
    "침공",
    "테러",
    "비상사태",
    "긴급 대피",
)


def _geo_tail_match_title(title: str) -> bool:
    t = title or ""
    cf = t.casefold()
    for p in _GEO_EN:
        if p.casefold() in cf:
            return True
    for p in _GEO_KO:
        if p in t:
            return True
    return False


def _prune_geo_sent(sent: Dict[str, Any], hours: int) -> Dict[str, str]:
    cutoff = now_kst() - timedelta(hours=max(1, hours))
    out: Dict[str, str] = {}
    for link, ts_s in (sent or {}).items():
        if not link:
            continue
        try:
            s = str(ts_s).strip()
            if s.endswith("Z"):
                s = s[:-1] + "+00:00"
            ts = datetime.fromisoformat(s)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=KST)
            if ts >= cutoff:
                out[str(link)] = str(ts_s)
        except (ValueError, TypeError):
            continue
    return out


def _escape_html(text: str) -> str:
    return (
        (text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _load_json(path: str, default: Any) -> Any:
    if not os.path.isfile(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return default


def _save_raw_data(data: Dict[str, Any]) -> None:
    tmp = RAW_DATA_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, RAW_DATA_PATH)


def _normalize_ticker(code: str) -> str:
    c = (code or "").strip()
    if c.isdigit():
        return c.zfill(6)
    return c


def _build_watch_terms(
    mapping_codes: Set[str],
    stocks: Dict[str, Any],
    aliases: Dict[str, List[str]],
) -> List[Tuple[str, str]]:
    """
    (매칭 문자열, 알림용 종목 표시명) — 매칭은 title.casefold() 기준.
    """
    terms: List[Tuple[str, str]] = []
    seen_m: Set[str] = set()

    def add_match(s: str, display: str) -> None:
        s = (s or "").strip()
        if len(s) < 2:
            return
        key = s.casefold()
        if key in seen_m:
            return
        seen_m.add(key)
        terms.append((s, display))

    for code in mapping_codes:
        t6 = _normalize_ticker(code)
        st = stocks.get(t6) or stocks.get(code)
        if not isinstance(st, dict):
            continue
        name = (st.get("name") or "").strip()
        ticker = (st.get("ticker") or t6).strip()
        t6 = _normalize_ticker(ticker)
        display = name or t6

        add_match(t6, display)
        nz = t6.lstrip("0") or "0"
        if len(nz) >= 3:
            add_match(nz, display)
        if name:
            add_match(name, display)
        for a in aliases.get(t6, []) or aliases.get(code, []) or []:
            add_match(str(a).strip(), display)

    terms.sort(key=lambda x: len(x[0]), reverse=True)
    return terms


def _load_holdings() -> List[Dict[str, Any]]:
    pf = _load_json(PORTFOLIO_PATH, {})
    return list(pf.get("vams", {}).get("holdings") or [])


def _holding_match_terms(
    holdings: List[Dict[str, Any]],
    aliases: Dict[str, List[str]],
) -> List[Tuple[str, str]]:
    terms: List[Tuple[str, str]] = []
    seen: Set[str] = set()

    def add(s: str, display: str) -> None:
        s = (s or "").strip()
        if len(s) < 2:
            return
        k = s.casefold()
        if k in seen:
            return
        seen.add(k)
        terms.append((s, display))

    for h in holdings:
        name = (h.get("name") or "").strip()
        t = _normalize_ticker(str(h.get("ticker") or ""))
        display = name or t
        if t:
            add(t, display)
            nz = t.lstrip("0") or "0"
            if len(nz) >= 3:
                add(nz, display)
        if name:
            add(name, display)
        ty = (h.get("ticker_yf") or "").split(".")[0].strip()
        if ty and ty.isdigit():
            t6 = _normalize_ticker(ty)
            add(t6, display)
            nz = t6.lstrip("0") or "0"
            if len(nz) >= 3:
                add(nz, display)
        for a in aliases.get(t, []) or []:
            add(str(a).strip(), display)

    terms.sort(key=lambda x: len(x[0]), reverse=True)
    return terms


def _needle_in_title(title_cf: str, needle: str) -> bool:
    """짧은 ASCII 키워드는 단어 경계로만 매칭(SK ↔ Sandisk 오탐 방지)."""
    n = needle.casefold().strip()
    if not n:
        return False
    if len(n) < 4 and n.isascii() and re.fullmatch(r"[a-z0-9.]+", n):
        return bool(
            re.search(
                r"(?<![a-z0-9])" + re.escape(n) + r"(?![a-z0-9])",
                title_cf,
                re.I,
            )
        )
    return n in title_cf


def _title_matches_terms(title_cf: str, terms: List[Tuple[str, str]]) -> Optional[str]:
    title_cf = title_cf.casefold()
    for needle, display in terms:
        if _needle_in_title(title_cf, needle):
            return display
    return None


def _has_high_intensity(title_upper: str) -> bool:
    return any(k in title_upper for k in HIGH_INTENSITY)


def _has_breaking(title_upper: str) -> bool:
    return "BREAKING" in title_upper


def _entry_published_iso(entry: Any) -> str:
    if getattr(entry, "published_parsed", None):
        try:
            ts = timegm(entry.published_parsed)
            dt = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(KST)
            return dt.isoformat()
        except (OverflowError, ValueError, TypeError):
            pass
    if getattr(entry, "updated_parsed", None):
        try:
            ts = timegm(entry.updated_parsed)
            dt = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(KST)
            return dt.isoformat()
        except (OverflowError, ValueError, TypeError):
            pass
    return now_kst().isoformat()


def _parse_feeds() -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for source, url in FEEDS:
        try:
            parsed = feedparser.parse(url, agent=USER_AGENT)
        except Exception:
            continue
        for entry in getattr(parsed, "entries", []) or []:
            title = (entry.get("title") or "").strip()
            link = (entry.get("link") or "").strip()
            if not title or not link:
                continue
            out.append(
                {
                    "source": source,
                    "title": title,
                    "published_at": _entry_published_iso(entry),
                    "link": link,
                }
            )
    return out


def run_rss_scout() -> int:
    mapping = _load_json(MAPPING_PATH, {})
    if not isinstance(mapping, dict):
        mapping = {}
    mapping_codes = {str(k).strip() for k in mapping.keys()}

    raw = _load_json(RAW_DATA_PATH, {})
    if not isinstance(raw, dict):
        raw = {}
    stocks = raw.get("stocks") or {}
    if not isinstance(stocks, dict):
        stocks = {}

    aliases = _load_json(ALIASES_PATH, {})
    if not isinstance(aliases, dict):
        aliases = {}

    watch_terms = _build_watch_terms(mapping_codes, stocks, aliases)
    holdings = _load_holdings()
    holding_terms = _holding_match_terms(holdings, aliases)

    sent_geo = _prune_geo_sent(
        raw.get("_rss_geo_tail_sent") if isinstance(raw.get("_rss_geo_tail_sent"), dict) else {},
        RSS_GEO_TAIL_DEDUPE_HOURS,
    )

    flash_raw = _load_json(NEWS_FLASH_PATH, [])
    existing: List[Dict[str, Any]] = flash_raw if isinstance(flash_raw, list) else []

    seen_links: Set[str] = set()
    for row in existing:
        if isinstance(row, dict) and row.get("link"):
            seen_links.add(str(row["link"]))

    new_rows: List[Dict[str, str]] = []
    breaking_alerts: List[Tuple[str, str]] = []

    headlines = _parse_feeds()
    for h in headlines:
        link = h["link"]
        if link in seen_links:
            continue
        title = h["title"]
        title_cf = title.casefold()
        title_upper = title.upper()

        display_hit = _title_matches_terms(title_cf, watch_terms)
        high = _has_high_intensity(title_upper)
        geo_hit = RSS_GEO_TAIL_TELEGRAM and _geo_tail_match_title(title)
        if display_hit is None and not high and not geo_hit:
            continue

        new_rows.append(h)
        seen_links.add(link)

        if _has_breaking(title_upper) and holding_terms:
            hname = _title_matches_terms(title_cf, holding_terms)
            if hname:
                breaking_alerts.append((hname, title))

    if not new_rows:
        return 0

    merged = new_rows + [x for x in existing if isinstance(x, dict)]
    merged.sort(
        key=lambda x: str(x.get("published_at") or ""),
        reverse=True,
    )
    merged = merged[:NEWS_FLASH_MAX]
    tmp_flash = NEWS_FLASH_PATH + ".tmp"
    with open(tmp_flash, "w", encoding="utf-8") as _f:
        import json as _json
        _json.dump(merged, _f, ensure_ascii=False, indent=2)
    os.replace(tmp_flash, NEWS_FLASH_PATH)
    raw.pop("news_flash", None)

    if RSS_GEO_TAIL_TELEGRAM:
        for h in new_rows:
            title = h.get("title") or ""
            link = h.get("link") or ""
            if not link or not _geo_tail_match_title(title):
                continue
            if link in sent_geo:
                continue
            msg = (
                f"<b>🌍 [지정학·재난 속보]</b>\n{_escape_html(title)}\n"
                f'<a href="{_escape_html(link)}">링크</a>'
            )
            if send_message(msg):
                sent_geo[link] = now_kst().isoformat()
    raw["_rss_geo_tail_sent"] = sent_geo

    _save_raw_data(raw)

    for stock_label, news_title in breaking_alerts:
        msg = (
            f"<b>[배리티 속보]</b> 사장님, 지금 {_escape_html(stock_label)} "
            f"관련 긴급 뉴스가 떴습니다! {_escape_html(news_title)}"
        )
        send_message(msg)

    return len(new_rows)


if __name__ == "__main__":
    n = run_rss_scout()
    print(f"[RSSScout] 신규 헤드라인 {n}건 반영 (raw_data.news_flash)")
