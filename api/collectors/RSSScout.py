"""
RSSScout — CNBC 뉴스 + SEC/Fed 공식 발표 RSS 헤드라인 스캔

- SEC/Fed는 정부 공식 발표이며, 3피드 성공은 독립 경제보도 3곳의 확인이 아니다.
- query clock은 조회 시각이며 기사 최신성·기존 행 재검증을 뜻하지 않는다.

- 제목만 사용(본문 미요청). mapping.json 티커 + raw_data 종목명 매칭,
  또는 BREAKING·EXCLUSIVE·URGENT·HALT 키워드 시 수집.
- data/raw_data.json 의 news_flash 에 병합(링크 기준 중복 제거).
- 보유 종목 + 제목에 BREAKING 이 동시에 있으면 텔레그램 속보 전송.
- 지정학·재난 키워드 텔레그램 발화 폐기 (2026-05-14, false positive 메타포 양산).
  진짜 disaster 알림 = api/collectors/geo_trigger.py 의 USGS 구조화 API (별도).

선택: data/rss_en_aliases.json — {"005930": ["Samsung", "Samsung Electronics"]}
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import tempfile
from calendar import timegm
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.request import BaseHandler

import feedparser
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from api.config import (
    DATA_DIR,
    KST,
    PORTFOLIO_PATH,
    now_kst,
)
from api.notifications.telegram import send_message

MAPPING_PATH = os.path.join(DATA_DIR, "mapping.json")
RAW_DATA_PATH = os.path.join(DATA_DIR, "raw_data.json")
ALIASES_PATH = os.path.join(DATA_DIR, "rss_en_aliases.json")

FEEDS: List[Tuple[str, str]] = [
    # SEC 자체 발표: 목록 https://www.sec.gov/about/rss-feeds · 조건 https://www.sec.gov/about/privacy-information#website-dissemination
    ("SEC 공식 발표", "https://www.sec.gov/news/pressreleases.rss"),
    ("CNBC", "https://www.cnbc.com/id/100003114/device/rss/rss.html"),
    # Fed 자체 발표: 목록 https://www.federalreserve.gov/feeds/feeds.htm · 조건 https://www.federalreserve.gov/disclaimer.htm
    ("Fed 공식 발표", "https://www.federalreserve.gov/feeds/press_all.xml"),
]

HIGH_INTENSITY = frozenset(
    x.upper() for x in ("BREAKING", "EXCLUSIVE", "URGENT", "HALT")
)

NEWS_FLASH_MAX = 200
NEWS_FLASH_PATH = os.path.join(DATA_DIR, "news_flash.json")
RECEIPT_PATH = os.path.join(DATA_DIR, "metadata", "rss_source_receipt.json")
USER_AGENT = (
    "VERITY-RSSScout/1.0 (+https://github.com; lightweight headline scanner)"
)

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


class _ResponseStatus(BaseHandler):
    """Retain terminal HTTP status before feedparser replaces it with redirect status."""
    status: Optional[int] = None

    def http_response(self, request, response):
        self.status = response.getcode()
        return response

    https_response = http_response


def _parse_feeds(evidence: Optional[List[Dict[str, Any]]] = None) -> Tuple[List[Dict[str, str]], int]:
    """(헤드라인 행, 조회 성공 피드 수) 를 돌려준다.

    🚨 두 번째 값이 가드의 근거다. feedparser 는 네트워크 실패에도 예외 대신
    빈 entries 를 돌려주므로, 산출 행수만 보면 "새 기사 없음"(정상)과
    "피드 전량 실패"(사고)가 구분되지 않는다. 증분 피드라 0건 자체는 정상일 수
    있으니 가드는 행수가 아니라 조회 성공 수에 걸어야 한다.
    [[feedback_silent_total_failure_guard]]
    """
    out: List[Dict[str, str]] = []
    ok_feeds = 0
    for source, url in FEEDS:
        result = {"source": source, "url": url, "started_at": now_kst().isoformat(),
                  "outcome": "transport_error", "entries": 0, "usable_entries": 0,
                  "entries_without_source_date": 0}
        if evidence is not None:
            evidence.append(result)
        response_status = _ResponseStatus()
        try:
            parsed = feedparser.parse(url, agent=USER_AGENT, handlers=[response_status])
        except Exception as e:
            result["error_type"] = type(e).__name__
            result["finished_at"] = now_kst().isoformat()
            sys.stderr.write(
                f"[RSSScout] outcome=transport_error feed_source={source} err={type(e).__name__} logged=True\n"
            )
            continue
        entries = getattr(parsed, "entries", []) or []
        status = response_status.status or getattr(parsed, "status", None)
        result.update(http_status=status, entries=len(entries),
                      finished_at=now_kst().isoformat())
        # A recognized RSS/Atom document is required even for a legitimate empty feed.
        # feedparser can return entries from malformed XML or HTTP error bodies.
        if not isinstance(status, int) or not 200 <= status < 300:
            result["outcome"] = "http_error"
        elif getattr(parsed, "bozo", False) or not getattr(parsed, "version", ""):
            result["outcome"] = "parse_error"
            error = getattr(parsed, "bozo_exception", None)
            if error is not None:
                result["error_type"] = type(error).__name__
        else:
            result["outcome"] = "success" if entries else "success_empty"
        if result["outcome"] not in {"success", "success_empty"}:
            sys.stderr.write(
                f"[RSSScout] outcome={result['outcome']} feed_source={source} logged=True\n"
            )
            continue
        ok_feeds += 1
        for entry in entries:
            title = (entry.get("title") or "").strip()
            link = (entry.get("link") or "").strip()
            if not title or not link:
                continue
            result["usable_entries"] += 1
            if not (getattr(entry, "published_parsed", None) or
                    getattr(entry, "updated_parsed", None)):
                result["entries_without_source_date"] += 1
            out.append(
                {
                    "source": source,
                    "title": title,
                    "published_at": _entry_published_iso(entry),
                    "link": link,
                }
            )
    return out, ok_feeds


def _asset_evidence(disposition: str) -> Dict[str, Any]:
    """Hash actual persisted bytes, never a reserialized approximation or mtime."""
    try:
        with open(NEWS_FLASH_PATH, "rb") as stream:
            payload = stream.read()
        rows = json.loads(payload)
        if not isinstance(rows, list):
            raise ValueError("not a list")
    except (OSError, ValueError):
        return {"path": "data/news_flash.json", "disposition": disposition,
                "status": "missing_or_invalid", "sha256": None}
    return {"path": "data/news_flash.json", "disposition": disposition,
            "status": "bound", "sha256": hashlib.sha256(payload).hexdigest(),
            "rows": len(rows)}


def _save_receipt(started_at: str, feeds: List[Dict[str, Any]],
                  new_rows: int, disposition: str) -> None:
    successes = sum(f["outcome"] in {"success", "success_empty"} for f in feeds)
    receipt = {
        "schema_version": 1, "producer": "RSSScout",
        "clock_kind": "source_query_attempt", "started_at": started_at,
        "finished_at": now_kst().isoformat(),
        "run_id": os.environ.get("GITHUB_RUN_ID"),
        "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        "input_commit": os.environ.get("GITHUB_SHA"),
        "scope": {"kind": "configured_rss_feed_query", "expected_feeds": len(FEEDS),
                  "successful_feeds": successes,
                  "asset_scope": "filtered incremental headlines; retained rows not revalidated"},
        "outcome": ("complete" if successes == len(FEEDS) else
                    "partial_failure" if successes else "all_feed_failure"),
        "new_rows": new_rows, "feeds": feeds,
        "new_rows_scope": "selected before retention limit; not a full-file refresh",
        "asset": _asset_evidence(disposition),
        "source_freshness_verified": False,
        "article_timestamp_policy": "unchanged; query clock is not article publication time",
    }
    directory = os.path.dirname(RECEIPT_PATH)
    os.makedirs(directory, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=directory,
                                         delete=False) as stream:
            name = stream.name
            json.dump(receipt, stream, ensure_ascii=False, indent=2)
        os.replace(name, RECEIPT_PATH)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)


def verify_receipt(expected_receipt_sha: Optional[str] = None, *,
                   committed: bool = False) -> str:
    """Exact byte binding for the pair committed by this run; no freshness promotion."""
    with open(RECEIPT_PATH, "rb") as stream:
        payload = stream.read()
    digest = hashlib.sha256(payload).hexdigest()
    receipt = json.loads(payload)
    if expected_receipt_sha and digest != expected_receipt_sha:
        raise ValueError("receipt changed during delivery")
    if os.environ.get("GITHUB_RUN_ID") and (
        receipt.get("run_id") != os.environ["GITHUB_RUN_ID"] or
        receipt.get("run_attempt") != os.environ.get("GITHUB_RUN_ATTEMPT")
    ):
        raise ValueError("receipt belongs to another attempt")
    asset = _asset_evidence(receipt["asset"]["disposition"])
    if asset["status"] != "bound" or asset["sha256"] != receipt["asset"]["sha256"]:
        raise ValueError("receipt/output hash mismatch or missing output")
    if committed:
        # Fixed paths at HEAD avoid putting a self-referential output commit in receipt.
        # Consumers fetch both paths at the logged output commit, then exact-match SHA.
        import subprocess
        for path, expected in [("data/metadata/rss_source_receipt.json", digest),
                               ("data/news_flash.json", asset["sha256"])]:
            saved = subprocess.run(["git", "show", "HEAD:" + path], check=True,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout
            if hashlib.sha256(saved).hexdigest() != expected:
                raise ValueError("committed receipt/output mismatch")
    return digest


def run_rss_scout() -> int:
    """신규 반영 건수를 돌려준다. 피드 전량 실패는 -1 (호출부가 실패 종료)."""
    started_at = now_kst().isoformat()
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

    flash_raw = _load_json(NEWS_FLASH_PATH, [])
    existing: List[Dict[str, Any]] = flash_raw if isinstance(flash_raw, list) else []

    seen_links: Set[str] = set()
    for row in existing:
        if isinstance(row, dict) and row.get("link"):
            seen_links.add(str(row["link"]))

    new_rows: List[Dict[str, str]] = []
    breaking_alerts: List[Tuple[str, str]] = []

    feeds: List[Dict[str, Any]] = []
    headlines, ok_feeds = _parse_feeds(feeds)
    if ok_feeds == 0:
        # 전량 실패. news_flash.json 을 건드리지 않고 실패로 종료한다 —
        # 여기서 정상 종료하면 mtime 만 신선해져 신선도 보드가 통과시킨다.
        sys.stderr.write(
            f"[RSSScout] outcome=total_fail feeds={len(FEEDS)} ok=0 — 산출 미갱신·실패 종료\n"
        )
        _save_receipt(started_at, feeds, 0, "preserved_after_failure")
        return -1

    for h in headlines:
        link = h["link"]
        if link in seen_links:
            continue
        title = h["title"]
        title_cf = title.casefold()
        title_upper = title.upper()

        display_hit = _title_matches_terms(title_cf, watch_terms)
        high = _has_high_intensity(title_upper)
        if display_hit is None and not high:
            continue

        new_rows.append(h)
        seen_links.add(link)

        if _has_breaking(title_upper) and holding_terms:
            hname = _title_matches_terms(title_cf, holding_terms)
            if hname:
                breaking_alerts.append((hname, title))

    if not new_rows:
        _save_receipt(started_at, feeds, 0, "unchanged_no_new_rows")
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

    _save_raw_data(raw)
    _save_receipt(started_at, feeds, len(new_rows), "atomically_replaced")

    for stock_label, news_title in breaking_alerts:
        msg = (
            f"<b>[배리티 속보]</b> 사장님, 지금 {_escape_html(stock_label)} "
            f"관련 긴급 뉴스가 떴습니다! {_escape_html(news_title)}"
        )
        send_message(msg)

    return len(new_rows)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--verify-receipt":
        args = sys.argv[2:]
        expected = next((arg for arg in args if arg != "--committed"), None)
        print(verify_receipt(expected, committed="--committed" in args))
        sys.exit(0)
    n = run_rss_scout()
    if n < 0:
        sys.stderr.write("[RSSScout] 피드 전량 실패 — exit 1\n")
        sys.exit(1)
    print(f"[RSSScout] 신규 헤드라인 {n}건 반영 (raw_data.news_flash)")
