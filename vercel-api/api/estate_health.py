"""
GET /api/estate/health — ESTATE 부동산 고유 자원 헬스체크 (P1 Mock)

인프라 표준 v1.1 — endpoint 네임스페이스:
    /api/system/*  = ESTATE/VERITY 공용
    /api/estate/*  = 부동산 고유 (LANDEX/정책/korea.kr)
    /api/verity/*  = 주식 고유

P1 단계 — mock 응답만. P2 wire 시 실제 cron 메트릭 수집 (별도 phase).

Query parameters:
    scenario = "healthy" (default) | "degraded"

note: korea_kr_worker 는 양 시나리오 모두 status=blocked. P3-4 (Railway 우회) 완료
전까지 healthy 불가능. 운영자에게 P3-4 미해결 명시 (degraded 와 별도 톤).

응답 schema = contract_system_pulse.md §1 Resource schema (id/label_ko/status/metric/note).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

KST = timezone(timedelta(hours=9))


def _build_resources(scenario: str, now: datetime) -> list[dict]:
    """ESTATE 자원 3종 mock — landex_cron / policy_cron / korea_kr_worker."""
    # korea_kr 는 양 시나리오 공통 — P3-4 미해결로 영구 blocked
    korea_kr = {
        "id": "korea_kr_worker",
        "label_ko": "korea.kr 워커",
        "status": "blocked",
        "metric": {
            "last_fetch_at": None,
            "error_rate_pct": None,
        },
        "note": "P3-4 우회 인프라 미구축 (GitHub Actions runner ↔ korea.kr Connection reset)",
    }

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
            korea_kr,
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
        korea_kr,
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
