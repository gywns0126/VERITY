"""Retired paid narrative endpoint. Cached and uncached requests never call a model."""
import json
import re
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse, quote


class handler(BaseHTTPRequestHandler):
    def _headers(self, status):
        self.send_response(status)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()

    def do_OPTIONS(self):
        self._headers(204)

    def do_GET(self):
        ticker = parse_qs(urlparse(self.path).query).get("ticker", [""])[0].strip().upper()
        self._headers(410)
        valid = re.fullmatch(r"(?:[0-9]{6}|[A-Z][A-Z0-9.\-]{0,9})", ticker)
        self.wfile.write(json.dumps({
            "error": "narrative_retired", "brief": None,
            "message": "AI 요약 생성은 기업 분석 자료로 통합되었습니다.",
            "report_url": "/api/fact_report?ticker=" + quote(ticker) if valid else None,
        }, ensure_ascii=False).encode("utf-8"))
