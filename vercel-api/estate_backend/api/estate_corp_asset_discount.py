"""
GET /api/estate/corp-asset-discount
    [?min_ratio=30]           — 부동산/총자산 비율 ≥ N% (default 20)
    [&revaluation=true|false] — 재평가 발생 종목만 (default 무관)
    [&period=2025-FY]         — 보고기간 (default 최신)
    [&limit=50]               — 결과 행 수 (default 50, max 200)

자산주 watchlist — 부동산 비중 높은 회사 + (옵션) 재평가 트리거.
estate_corp_holdings 단일 테이블 조회.

응답 예:
{
  "filters": {"min_ratio": 30, "revaluation_only": true, "period": "2025-FY"},
  "watchlist": [
    {
      "ticker": "...", "company_name": "...",
      "total_property_krw": ...,
      "property_to_asset_pct": 39.12,
      "revaluation_flag": true,
      "revaluation_amount_krw": ...,
      "hidden_value_krw": <fair-book>
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

_PERIOD_RE = re.compile(r"^\d{4}-(Q[1-3]|FY)$")

_FIELDS = ",".join([
    "corp_code", "ticker", "company_name", "period",
    "total_property_krw", "property_to_asset_pct",
    "investment_property_krw",
    "revaluation_flag", "revaluation_amount_krw",
    "book_value_total_krw", "fair_value_total_krw",
])


def _resolve_latest_period() -> str | None:
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_ANON_KEY", "")
    if not url or not key:
        return None
    try:
        r = requests.get(
            f"{url}/rest/v1/estate_corp_holdings",
            headers={"apikey": key, "Authorization": f"Bearer {key}"},
            params={"select": "period", "order": "period.desc", "limit": "1"},
            timeout=5,
        )
        r.raise_for_status()
        rows = r.json()
        return rows[0]["period"] if rows else None
    except Exception as e:
        _logger.warning("latest period 조회 실패: %s", e)
        return None


def _fetch(period: str, min_ratio: float, revaluation_only: bool,
           limit: int) -> list[dict] | None:
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_ANON_KEY", "")
    if not url or not key:
        return None

    params = [
        ("select", _FIELDS),
        ("period", f"eq.{period}"),
        ("property_to_asset_pct", f"gte.{min_ratio}"),
        ("order", "property_to_asset_pct.desc.nullslast"),
        ("limit", str(limit)),
    ]
    if revaluation_only:
        params.append(("revaluation_flag", "eq.true"))

    try:
        r = requests.get(
            f"{url}/rest/v1/estate_corp_holdings",
            headers={"apikey": key, "Authorization": f"Bearer {key}"},
            params=params,
            timeout=8,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        _logger.warning("corp_asset_discount fetch 실패: %s", e)
        return None


def _enrich(rows: list[dict]) -> list[dict]:
    """hidden_value_krw = fair - book (둘 다 있는 경우만)."""
    for r in rows:
        fv = r.get("fair_value_total_krw")
        bv = r.get("book_value_total_krw")
        if fv is not None and bv is not None:
            r["hidden_value_krw"] = fv - bv
        else:
            r["hidden_value_krw"] = None
    return rows


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        params = parse_qs(urlparse(self.path).query)
        min_ratio_s = params.get("min_ratio", ["20"])[0].strip() or "20"
        revaluation_s = params.get("revaluation", [""])[0].strip().lower()
        period = params.get("period", [""])[0].strip()
        limit_s = params.get("limit", ["50"])[0].strip() or "50"

        try:
            min_ratio = max(0.0, min(100.0, float(min_ratio_s)))
        except ValueError:
            self._err(400, "invalid_min_ratio", "min_ratio=0~100 float")
            return
        revaluation_only = revaluation_s in ("true", "1", "yes")
        if period and not _PERIOD_RE.match(period):
            self._err(400, "invalid_period", "period=YYYY-Q1|Q2|Q3|FY 형식")
            return
        try:
            limit = max(1, min(200, int(limit_s)))
        except ValueError:
            limit = 50

        if not period:
            period = _resolve_latest_period()
            if not period:
                self._err(503, "no_data", "데이터 없음 또는 DB 조회 실패")
                return

        rows = _fetch(period, min_ratio, revaluation_only, limit)
        if rows is None:
            self._err(503, "supabase_unavailable", "DB 조회 실패")
            return

        rows = _enrich(rows)
        body = {
            "filters": {
                "min_ratio": min_ratio,
                "revaluation_only": revaluation_only,
                "period": period,
                "limit": limit,
            },
            "watchlist": rows,
            "total_matches": len(rows),
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
