"""
GET /api/estate/health — ESTATE 부동산 고유 자원 헬스체크 (P1 Mock)

인프라 표준 v1.1 — endpoint 네임스페이스:
    /api/system/*  = ESTATE/VERITY 공용
    /api/estate/*  = 부동산 고유 (LANDEX/정책)
    /api/verity/*  = 주식 고유

P1 단계 — mock 응답만. P2 wire 시 실제 cron 메트릭 수집 (별도 phase).

Query parameters:
    scenario = "healthy" (default) | "degraded"

P3-4 closure (2026-05-06): korea_kr_worker (영구 blocked) → data_go_kr_policy 로 교체.
data.go.kr 정공법 swap 으로 차단 회피 (commit 0beb222). 양 시나리오에서 정상 자원.

응답 schema = contract_system_pulse.md §1 Resource schema (id/label_ko/status/metric/note).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

KST = timezone(timedelta(hours=9))


def _build_resources(scenario: str, now: datetime) -> list[dict]:
    """ESTATE 자원 3종 mock — landex_cron / policy_cron / data_go_kr_policy."""
    if scenario == "degraded":
        return [
            {
                "id": "landex_cron",
                "label_ko": "LANDEX Snapshot cron",
                "status": "degraded",
                "metric": {"last_success_at": (now - timedelta(hours=30)).isoformat()},
                "note": "last success >= 24h ago",
            },
            {
                "id": "policy_cron",
                "label_ko": "정책 수집 cron",
                "status": "degraded",
                "metric": {
                    "last_success_at": (now - timedelta(hours=26)).isoformat(),
                    "last_run_failed": True,
                },
                "note": "last run failed",
            },
            {
                "id": "data_go_kr_policy",
                "label_ko": "data.go.kr 정책브리핑 API",
                "status": "degraded",
                "metric": {
                    "last_status_code": 503,
                    "last_success_at": (now - timedelta(hours=28)).isoformat(),
                },
                "note": "API 응답 비정상 (5xx)",
            },
        ]
    # default: healthy
    return [
        {
            "id": "landex_cron",
            "label_ko": "LANDEX Snapshot cron",
            "status": "healthy",
            "metric": {"last_success_at": (now - timedelta(hours=12)).isoformat()},
            "note": None,
        },
        {
            "id": "policy_cron",
            "label_ko": "정책 수집 cron",
            "status": "healthy",
            "metric": {"last_success_at": (now - timedelta(hours=8)).isoformat()},
            "note": None,
        },
        {
            "id": "data_go_kr_policy",
            "label_ko": "data.go.kr 정책브리핑 API",
            "status": "healthy",
            "metric": {
                "last_status_code": 200,
                "last_success_at": (now - timedelta(hours=8)).isoformat(),
            },
            "note": None,
        },
    ]


class handler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_GET(self):
        params = parse_qs(urlparse(self.path).query)
        scenario = (params.get("scenario", ["healthy"])[0] or "healthy").strip().lower()
        if scenario not in ("healthy", "degraded"):
            scenario = "healthy"

        now = datetime.now(KST)
        payload = {
            "schema_version": "1.0",
            "fetched_at": now.isoformat(timespec="seconds"),
            "namespace": "estate",
            "scenario": scenario,
            "resources": _build_resources(scenario, now),
        }

        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "public, max-age=300")
        self.end_headers()
        self.wfile.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
