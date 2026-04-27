"""
GET /api/admin/data_health — Data Health 탭 (와이어프레임 §3).

반환:
  소스별 표 (status, freshness, latency, missing_pct, success/failure 7d)
  + 7일 수집 추이 (jsonl 누적 후 의미 시작)
"""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler

from api.admin._common import (
    fetch_portfolio,
    get_observability,
    authorize,
    write_response,
    write_options,
    headers_to_dict,
)


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
        health = obs.get("data_health") or {}
        sources = health.get("sources") or {}

        # 표 형식 — 와이어프레임 §3
        rows = []
        for src, meta in sources.items():
            if not isinstance(meta, dict):
                continue
            rows.append({
                "source": src,
                "status": meta.get("status"),
                "freshness_minutes": meta.get("freshness_minutes"),
                "latency_ms_p50": meta.get("latency_ms_p50"),
                "missing_pct": meta.get("missing_pct"),
                "success_count_7d": meta.get("success_count_7d"),
                "failure_count_7d": meta.get("failure_count_7d"),
                "detail": meta.get("detail", ""),
            })

        # status 우선순위로 정렬: critical → warning → ok
        order = {"critical": 0, "warning": 1, "ok": 2, "unknown": 3}
        rows.sort(key=lambda r: order.get(r.get("status") or "unknown", 4))

        write_response(self, 200, {
            "rows": rows,
            "overall_status": health.get("overall_status"),
            "core_sources_ok": health.get("core_sources_ok"),
            "checked_at": obs.get("checked_at"),
        })
