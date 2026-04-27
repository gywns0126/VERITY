"""
GET /api/admin/drift — Drift & Explainability 탭 (와이어프레임 §5).

반환:
  feature 별 PSI 막대 + 어제/오늘 분포 + Brain Score 기여도 TOP 5↑/5↓
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
        drift = obs.get("drift") or {}
        explanation = obs.get("explanation") or {}

        # PSI bars — feature_drifts 를 정렬된 리스트로
        bars = []
        for feature, info in (drift.get("feature_drifts") or {}).items():
            if not isinstance(info, dict):
                continue
            bars.append({
                "feature": feature,
                "psi": info.get("psi"),
                "level": info.get("level"),
                "yesterday": info.get("yesterday"),
                "today": info.get("today"),
            })
        bars.sort(key=lambda b: b.get("psi") or 0, reverse=True)

        write_response(self, 200, {
            "level": drift.get("level"),
            "overall_drift_score": drift.get("overall_drift_score"),
            "drifted_features": drift.get("drifted_features", []),
            "comparable_count": drift.get("comparable_count", 0),
            "feature_psi_bars": bars,
            "explanation": {
                "avg_brain_score": explanation.get("avg_brain_score"),
                "positive_top5": explanation.get("positive_contributors", [])[:5],
                "negative_top5": explanation.get("negative_contributors", [])[:5],
                "vs_yesterday": explanation.get("vs_yesterday", {}),
            },
            "checked_at": obs.get("checked_at"),
        })
