"""
VERITY 종목 검색 자동완성 API
GET /api/search?q=삼성 → 매칭되는 종목 최대 10개 반환 (즉시 응답)
"""
from http.server import BaseHTTPRequestHandler
import json
import os
import re
import threading
from time import monotonic
from urllib.parse import parse_qs, urlparse

STOCKS_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "krx_stocks.json")
US_STOCKS_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "us_stocks.json")
_cache = None
_us_cache = None
_catalog_rows = []
_catalog_retry_at = 0.0
_catalog_lock = threading.Lock()
CATALOG_TTL_SECONDS = 300
CATALOG_DEADLINE_SECONDS = 3


def _public_kr_rows(document):
    from api.portfolio_core.portfolio_public_sources import safe_public_text
    rows = document.get("stocks") if type(document) is dict else None
    if type(rows) not in (list, dict):
        raise ValueError("invalid-public-search-catalog")
    selected, rejected = {}, set()
    entries = rows.items() if type(rows) is dict else ((None, row) for row in rows)
    for hint, row in entries:
        if type(row) is not dict:
            continue
        ticker = row.get("ticker")
        if type(ticker) is not str or not re.fullmatch(r"[0-9]{6}", ticker):
            continue
        name, market = row.get("name"), row.get("market")
        if (set(row) != {"ticker", "name", "market"}
                or hint is not None and hint != ticker
                or type(market) is not str or market not in {"KR", "KOSPI", "KOSDAQ", "KONEX"}
                or type(name) is not str or not 0 < len(name) <= 160
                or safe_public_text(name, 160) != name
                or re.search(r"[\x00-\x1f\x7f-\x9f<>]", name)):
            rejected.add(ticker)
            continue
        public = {"ticker": ticker, "name": name, "market": market}
        if ticker in selected and selected[ticker] != public:
            rejected.add(ticker)
        else:
            selected[ticker] = public
    public_rows = [row for ticker, row in selected.items() if ticker not in rejected]
    if not public_rows:
        raise ValueError("empty-public-search-catalog")
    return public_rows


def _public_catalog():
    global _catalog_rows, _catalog_retry_at
    if monotonic() < _catalog_retry_at or not _catalog_lock.acquire(blocking=False):
        return _catalog_rows
    try:
        if monotonic() < _catalog_retry_at:
            return _catalog_rows
        try:
            # Fixed public URL only; no environment credentials or checkpoint reads.
            from api.portfolio_core.member_map_refresh_store import read_public_catalog
            started = monotonic()
            rows = _public_kr_rows(read_public_catalog())
            if monotonic() - started >= CATALOG_DEADLINE_SECONDS:
                raise ValueError("public-search-catalog-deadline")
            _catalog_rows = rows
        except Exception:
            pass  # Retain the last good projection; never expose error/body content.
        finally:
            _catalog_retry_at = monotonic() + CATALOG_TTL_SECONDS
        return _catalog_rows
    finally:
        _catalog_lock.release()


def _safe_int(raw, default: int, lo: int = 1, hi: int = 100) -> int:
    try:
        v = int(raw)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, v))


def _load():
    global _cache
    if _cache is None:
        with open(STOCKS_PATH, "r", encoding="utf-8") as f:
            _cache = json.load(f)
    return _cache


def _load_us():
    global _us_cache
    if _us_cache is None:
        with open(US_STOCKS_PATH, "r", encoding="utf-8") as f:
            _us_cache = json.load(f)
    return _us_cache


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        q = params.get("q", [""])[0].strip()
        limit = _safe_int(params.get("limit", ["10"])[0], 10, 1, 100)
        market = params.get("market", ["all"])[0].strip().lower()
        if market not in ("all", "kr", "us"):
            market = "all"

        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "s-maxage=300, stale-while-revalidate=300")
        self.end_headers()

        if not q or len(q) < 1:
            self.wfile.write(json.dumps([], ensure_ascii=False).encode())
            return

        kr_stocks = _load()
        if market == "us":
            stocks = _load_us()
        elif market == "kr":
            stocks = kr_stocks
        else:
            stocks = kr_stocks + _load_us()
        if market != "us":
            existing = {row["ticker"] for row in stocks}
            stocks = stocks + [row for row in _public_catalog() if row["ticker"] not in existing]
        q_lower = q.lower()
        q_upper = q.upper()
        results = []

        def _name_kr(s):
            return (s.get("name_kr") or "").lower()

        exact_name = [s for s in stocks if s["name"].lower() == q_lower or _name_kr(s) == q_lower]
        exact_ticker = [s for s in stocks if s["ticker"] == q or s["ticker"] == q_upper]

        starts_name = [s for s in stocks
                       if (s["name"].lower().startswith(q_lower) or _name_kr(s).startswith(q_lower))
                       and s not in exact_name]
        starts_ticker = [s for s in stocks if s["ticker"].startswith(q_upper) and s not in exact_ticker]

        contains_name = [s for s in stocks
                         if (q_lower in s["name"].lower() or q_lower in _name_kr(s))
                         and s not in exact_name and s not in starts_name]

        for group in [exact_name, exact_ticker, starts_name, starts_ticker, contains_name]:
            for s in group:
                if s not in results:
                    results.append(s)
                if len(results) >= limit:
                    break
            if len(results) >= limit:
                break

        self.wfile.write(json.dumps(results[:limit], ensure_ascii=False).encode())
