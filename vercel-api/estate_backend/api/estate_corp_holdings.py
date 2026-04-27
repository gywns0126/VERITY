"""
GET /api/estate/corp-holdings?ticker=005930[&limit=8]

단일 회사 부동산 자산 시계열 — TERMINAL StockDashboard 부동산 탭 강화용.
estate_corp_holdings 테이블에서 직전 N 분기 (default 8) 반환.

응답 예:
{
  "ticker": "005930",
  "company_name": "삼성전자",
  "snapshots": [
    {
      "period": "2025-FY",
      "total_property_krw": ...,
      "property_to_asset_pct": 12.34,
      "investment_property_krw": ...,
      "land_krw": ..., "buildings_krw": ...,
      "revaluation_flag": false,
      "qoq_change_pct": -1.2
    }
  ]
}
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

_TICKER_RE = re.compile(r"^\d{6}$")

_FIELDS = ",".join([
    "corp_code", "ticker", "company_name", "period", "bsns_year", "reprt_code",
    "total_property_krw", "prev_property_krw", "total_assets_krw",
    "property_to_asset_pct", "qoq_change_pct", "yoy_change_pct",
    "land_krw", "buildings_krw", "structures_krw",
    "construction_in_progress_krw", "investment_property_krw",
    "right_of_use_assets_krw",
    "book_value_total_krw", "fair_value_total_krw",
    "revaluation_flag", "revaluation_amount_krw",
])


def _fetch(ticker: str, limit: int) -> list[dict] | None:
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_ANON_KEY", "")
    if not url or not key:
        return None

    try:
        r = requests.get(
            f"{url}/rest/v1/estate_corp_holdings",
            headers={"apikey": key, "Authorization": f"Bearer {key}"},
            params={
                "select": _FIELDS,
                "ticker": f"eq.{ticker}",
                "order": "period.desc",
                "limit": str(limit),
            },
            timeout=5,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        _logger.warning("corp_holdings fetch 실패 ticker=%s: %s", ticker, e)
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
        ticker = params.get("ticker", [""])[0].strip()
        limit_s = params.get("limit", ["8"])[0].strip() or "8"

        if not ticker or not _TICKER_RE.match(ticker):
            self._err(400, "invalid_ticker", "ticker=6자리 숫자(KRX) 필수")
            return
        try:
            limit = max(1, min(40, int(limit_s)))
        except ValueError:
            limit = 8

        rows = _fetch(ticker, limit)
        if rows is None:
            self._err(503, "supabase_unavailable", "DB 조회 실패")
            return
        if not rows:
            self._err(404, "no_data", f"ticker={ticker} 데이터 없음")
            return

        meta = rows[0]
        body = {
            "ticker": meta.get("ticker"),
            "corp_code": meta.get("corp_code"),
            "company_name": meta.get("company_name"),
            "snapshots": rows,
        }
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "public, max-age=3600")
        self.end_headers()
        self.wfile.write(json.dumps(body, ensure_ascii=False).encode("utf-8"))

    def _err(self, status: int, code: str, message: str):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps({"error": code, "message": message}).encode("utf-8"))
