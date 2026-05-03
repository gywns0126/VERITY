"""
GET /api/system/health — ESTATE/VERITY 공용 자원 헬스체크 (P1 Mock)

인프라 표준 v1.1 — endpoint 네임스페이스:
    /api/system/*  = ESTATE/VERITY 공용 (Vercel/Supabase/Claude API)
    /api/estate/*  = 부동산 고유
    /api/verity/*  = 주식 고유

P1 단계 — mock 응답만. P2 wire 시 실제 메트릭 수집 (별도 phase).

Query parameters:
    scenario = "healthy" (default) | "degraded"

응답 schema (contract_system_pulse.md §1):
    {
      schema_version, fetched_at, namespace, resources: [
        {id, label_ko, status, metric, note}
      ]
    }

거짓말 트랩:
    T2: mock fallback 가시성 명시 — schema_version + namespace 필드로 source 명확
    T29: source URL 절대 URL 의무 — endpoint 자체 production domain only
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

KST = timezone(timedelta(hours=9))


def _build_resources(scenario: str, now: datetime) -> list[dict]:
    """공용 자원 3종 mock — vercel_functions / supabase / claude_api."""
    if scenario == "degraded":
        return [
            {
                "id": "vercel_functions",
                "label_ko": "Vercel Functions",
                "status": "degraded",
                "metric": {
                    "last_invocation_at": (now - timedelta(minutes=12)).isoformat(),
                    "error_rate_pct": 7.2,
                },
                "note": "error_rate >= 5% (12min ago)",
            },
            {
                "id": "supabase",
                "label_ko": "Supabase",
                "status": "healthy",
                "metric": {"rls_check": True, "conn_ok": True},
                "note": None,
            },
            {
                "id": "claude_api",
                "label_ko": "Claude API",
                "status": "degraded",
                "metric": {"quota_usage_pct": 85.2},
                "note": "quota >= 80%",
            },
        ]
    # default: healthy
    return [
        {
            "id": "vercel_functions",
            "label_ko": "Vercel Functions",
            "status": "healthy",
            "metric": {
                "last_invocation_at": (now - timedelta(minutes=2)).isoformat(),
                "error_rate_pct": 0.4,
            },
            "note": None,
        },
        {
            "id": "supabase",
            "label_ko": "Supabase",
            "status": "healthy",
            "metric": {"rls_check": True, "conn_ok": True},
            "note": None,
        },
        {
            "id": "claude_api",
            "label_ko": "Claude API",
            "status": "healthy",
            "metric": {"quota_usage_pct": 42.0},
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
            "namespace": "system",
            "scenario": scenario,  # P1 Mock 식별 (P2 wire 시 제거)
            "resources": _build_resources(scenario, now),
        }

        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        # P1 Mock — 운영자 수동 REFRESH 가정, 5분 캐시 (P0 §6 재진입 명세)
        self.send_header("Cache-Control", "public, max-age=300")
        self.end_headers()
        self.wfile.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
