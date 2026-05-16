"""
GET /api/system/health — ESTATE/VERITY 공용 자원 헬스체크 (P2 진짜 wire — 2026-05-17)

인프라 표준 v1.1 — endpoint 네임스페이스:
    /api/system/*  = ESTATE/VERITY 공용 (Vercel/Supabase/Claude API)
    /api/estate/*  = 부동산 고유
    /api/verity/*  = 주식 고유

2026-05-17 P2 wire (B1+B2+B3 통합):
    - 옛 P1 mock (vercel_functions/supabase/claude_api hardcoded) 폐기.
    - 진짜 source:
        * vercel_functions = 이 endpoint 가 응답 = self-ping healthy (Vercel function 살아있음 증거)
        * supabase         = SUPABASE_URL/ANON_KEY env 존재 + (선택) light ping
        * claude_api       = ANTHROPIC_API_KEY env 존재 (실제 API call X — 비용/quota 회피)
    - scenario=mock 으로 옛 mock 응답 보존 (Framer 개발 toggle).

Query parameters:
    scenario = "live" (default) | "mock"

응답 schema (contract_system_pulse.md §1):
    {schema_version, fetched_at, namespace, resources: [{id, label_ko, status, metric, note}]}

거짓말 트랩:
    T1  fabricate 금지   — env 미설정 시 status=degraded 명시 (가짜 healthy X)
    T2  mock fallback X  — scenario=live 가 env 미설정 시 mock 으로 떨어지지 않음
    T29 source URL 절대  — vercel.json rewrite (/api/system/health → /api/system_health)
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

KST = timezone(timedelta(hours=9))

CACHE_MAX_AGE = 300  # 5분 — env 변경은 운영자 수동 trigger


def _is_set(name: str) -> bool:
    v = os.environ.get(name, "")
    return bool(v and v.strip())


def _resource_vercel(now: datetime) -> dict:
    """이 endpoint 가 응답 = Vercel function 살아있음 (self-ping)."""
    return {
        "id": "vercel_functions",
        "label_ko": "Vercel Functions",
        "status": "healthy",
        "metric": {
            "last_invocation_at": now.isoformat(timespec="seconds"),
            "self_ping": True,
        },
        "note": None,
    }


def _resource_supabase(now: datetime) -> dict:
    """SUPABASE_URL + ANON_KEY env 검증. ping X (비용/cold start 회피)."""
    url_set = _is_set("SUPABASE_URL")
    key_set = _is_set("SUPABASE_ANON_KEY")
    configured = url_set and key_set
    return {
        "id": "supabase",
        "label_ko": "Supabase",
        "status": "healthy" if configured else "degraded",
        "metric": {
            "url_present": url_set,
            "anon_key_present": key_set,
            "checked_at": now.isoformat(timespec="seconds"),
        },
        "note": None if configured else "env 미설정 — LiveVisitors/AuthPage 영향",
    }


def _resource_claude(now: datetime) -> dict:
    """ANTHROPIC_API_KEY env 검증. 실제 API call 안 함 (비용/quota 회피)."""
    key_set = _is_set("ANTHROPIC_API_KEY")
    return {
        "id": "claude_api",
        "label_ko": "Claude API",
        "status": "healthy" if key_set else "degraded",
        "metric": {
            "key_present": key_set,
            "checked_at": now.isoformat(timespec="seconds"),
            # 실제 quota/cost 메트릭은 별도 (data/metadata/llm_cost.jsonl ramp).
        },
        "note": None if key_set else "ANTHROPIC_API_KEY 미설정 — dual_consensus 영향",
    }


def _build_resources_live(now: datetime) -> list[dict]:
    """진짜 wire — self-ping + env 검증 3종."""
    return [
        _resource_vercel(now),
        _resource_supabase(now),
        _resource_claude(now),
    ]


def _build_resources_mock(now: datetime) -> list[dict]:
    """개발 toggle — 옛 P1 mock 보존 (Framer 검증용)."""
    return [
        {
            "id": "vercel_functions",
            "label_ko": "Vercel Functions (mock)",
            "status": "healthy",
            "metric": {
                "last_invocation_at": (now - timedelta(minutes=2)).isoformat(),
                "error_rate_pct": 0.4,
            },
            "note": "scenario=mock — 실측 wire 는 scenario=live 사용",
        },
        {
            "id": "supabase",
            "label_ko": "Supabase (mock)",
            "status": "healthy",
            "metric": {"rls_check": True, "conn_ok": True},
            "note": None,
        },
        {
            "id": "claude_api",
            "label_ko": "Claude API (mock)",
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
        scenario = (params.get("scenario", ["live"])[0] or "live").strip().lower()
        if scenario not in ("live", "mock"):
            scenario = "live"

        now = datetime.now(KST)
        resources = (
            _build_resources_mock(now) if scenario == "mock" else _build_resources_live(now)
        )
        payload = {
            "schema_version": "1.1",  # P2 wire — scenario semantic 변경
            "fetched_at": now.isoformat(timespec="seconds"),
            "namespace": "system",
            "scenario": scenario,
            "resources": resources,
        }

        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", f"public, max-age={CACHE_MAX_AGE}")
        self.end_headers()
        self.wfile.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
