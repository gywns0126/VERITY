"""
VERITY 종목 검색 자동완성 API
GET /api/search?q=삼성 → 매칭되는 종목 최대 10개 반환 (즉시 응답)
"""
from http.server import BaseHTTPRequestHandler
import json
import os
from urllib.parse import parse_qs, urlparse

STOCKS_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "krx_stocks.json")
_cache = None


def _load():
    global _cache
    if _cache is None:
        with open(STOCKS_PATH, "r", encoding="utf-8") as f:
            _cache = json.load(f)
    return _cache


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
        limit = int(params.get("limit", ["10"])[0])

        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "s-maxage=3600, stale-while-revalidate=86400")
        self.end_headers()

        if not q or len(q) < 1:
            self.wfile.write(json.dumps([], ensure_ascii=False).encode())
            return

        stocks = _load()
        q_lower = q.lower()
        results = []

        exact_name = [s for s in stocks if s["name"].lower() == q_lower]
        exact_ticker = [s for s in stocks if s["ticker"] == q]

        starts_name = [s for s in stocks if s["name"].lower().startswith(q_lower) and s not in exact_name]
        starts_ticker = [s for s in stocks if s["ticker"].startswith(q) and s not in exact_ticker]

        contains_name = [s for s in stocks
                         if q_lower in s["name"].lower()
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
