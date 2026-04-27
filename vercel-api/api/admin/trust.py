"""
GET /api/admin/trust — Report Readiness 탭 (와이어프레임 §6).

반환:
  8개 조건 체크리스트 + verdict + recommendation + 최근 PDF 이력
"""
from __future__ import annotations

import os
from http.server import BaseHTTPRequestHandler

from api.admin._common import (
    fetch_portfolio,
    get_observability,
    authorize,
    write_response,
    write_options,
    headers_to_dict,
)


def _recent_pdfs(portfolio: dict) -> list:
    """recommendations 와 같은 portfolio 키에서 PDF 메타데이터 추출.

    실제 파일 시스템 접근은 Vercel Function 에서 어려우므로,
    portfolio 의 reports_meta 키 또는 빈 리스트.
    """
    meta = portfolio.get("reports_meta") if isinstance(portfolio, dict) else None
    if isinstance(meta, list):
        return meta[-10:]
    return []


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        write_options(self)

    def do_GET(self):
        ok, reason = authorize(headers_to_dict(self))
        if not ok:
            write_response(self, 401, {"error": "unauthorized", "reason": reason})
            return

        portfolio = fetch_portfolio()
        if not portfolio:
            write_response(self, 503, {"error": "portfolio_unavailable"})
            return

        obs = get_observability(portfolio)
        trust = obs.get("trust") or {}

        write_response(self, 200, {
            "verdict": trust.get("verdict"),
            "recommendation": trust.get("recommendation"),
            "satisfied": trust.get("satisfied"),
            "total": trust.get("total", 8),
            "conditions": trust.get("conditions", {}),
            "details": trust.get("details", {}),
            "blocking_reasons": trust.get("blocking_reasons", []),
            "recent_pdfs": _recent_pdfs(portfolio),
            "checked_at": obs.get("checked_at"),
        })
