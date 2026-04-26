"""
GET /api/estate/market-report             → 최신 (월 미지정)
GET /api/estate/market-report?month=YYYY-MM  → 특정 월

응답: estate_market_reports 의 단일 row (parsed JSONB 포함)
"""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler
import json
import logging
import os
import re
from urllib.parse import parse_qs, urlparse

import requests

_logger = logging.getLogger(__name__)

_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


def _fetch_report(month: str | None) -> dict | None:
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    anon = os.environ.get("SUPABASE_ANON_KEY", "")
    if not url or not anon:
        return None

    params = {
        "select": "month,parsed,claude_analysis,citations,model,source,created_at",
        "source": "eq.perplexity",
        "order": "month.desc",
        "limit": "1",
    }
    if month:
        params["month"] = f"eq.{month}"

    try:
        r = requests.get(
            f"{url}/rest/v1/estate_market_reports",
            headers={"apikey": anon, "Authorization": f"Bearer {anon}"},
            params=params,
            timeout=5,
        )
        r.raise_for_status()
        rows = r.json()
        return rows[0] if rows else None
    except Exception as e:
        _logger.warning("market_report fetch 실패: %s", e)
        return None


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        params = parse_qs(urlparse(self.path).query)
        month = params.get("month", [""])[0].strip()

        if month and not _MONTH_RE.match(month):
            self._err(400, "invalid_month_format", "month=YYYY-MM 필수")
            return

        report = _fetch_report(month or None)
        if report is None:
            self._err(404, "no_report", f"리포트 없음 (month={month or 'latest'})")
            return

        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "public, max-age=3600")  # 1시간 캐시
        self.end_headers()
        self.wfile.write(json.dumps(report, ensure_ascii=False).encode("utf-8"))

    def _err(self, status: int, code: str, message: str):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps({"error": code, "message": message}).encode("utf-8"))
