"""
estate_hero_briefing.py — HeroBriefing JSON read-through endpoint (P2 Step 5)

GET /api/estate/hero-briefing → gh-pages 의 estate_hero_briefing.json read-through

흐름:
    1. ESTATE_HERO_BRIEFING_SOURCE_URL 환경변수 (gh-pages JSON URL) 읽음
    2. requests.get(timeout=5s) — Vercel maxDuration 일치
    3. 200 + JSON 유효 + 필수 필드 → 200 응답 + Cache-Control: public, max-age=300
    4. 어떤 단계든 실패 → 503 (mock fallback X — T2)

거짓말 트랩:
    T1·T9 fabricate·silent X — 모든 실패 _logger.error + 503
    T2    mock fallback X — 실패 시 명시 503, 가짜 JSON 반환 X
    T3    가짜 URL X — source URL 은 환경변수, default 없음
"""
from __future__ import annotations

import json
import logging
import os
from http.server import BaseHTTPRequestHandler

import requests

_logger = logging.getLogger(__name__)

SOURCE_URL_ENV = "ESTATE_HERO_BRIEFING_SOURCE_URL"
TIMEOUT_SEC = 5
CACHE_MAX_AGE = 300


class handler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def _json(self, status, payload, cache_control=None):
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        if cache_control:
            self.send_header("Cache-Control", cache_control)
        self.end_headers()
        self.wfile.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))

    def _err(self, status, code, message):
        self._json(status, {"error": code, "message": message})

    def do_GET(self):
        source_url = (os.environ.get(SOURCE_URL_ENV, "") or "").strip()
        if not source_url:
            _logger.error("hero_briefing: %s missing", SOURCE_URL_ENV)
            self._err(503, "config_missing", f"{SOURCE_URL_ENV} not configured")
            return

        try:
            r = requests.get(source_url, timeout=TIMEOUT_SEC)
        except requests.RequestException as e:
            _logger.error("hero_briefing: source fetch failed: %s", e)
            self._err(503, "source_fetch_failed", "upstream unavailable")
            return

        if r.status_code != 200:
            _logger.error("hero_briefing: source returned %d", r.status_code)
            self._err(503, "source_non_200", f"upstream {r.status_code}")
            return

        try:
            payload = r.json()
        except (ValueError, json.JSONDecodeError) as e:
            _logger.error("hero_briefing: source not valid JSON: %s", e)
            self._err(503, "source_invalid_json", "upstream returned non-JSON")
            return

        # 최소 schema 검증 — HeroBriefing 컴포넌트 필수 필드
        if not isinstance(payload, dict):
            _logger.error("hero_briefing: payload not object")
            self._err(503, "source_schema_invalid", "expected JSON object")
            return
        if not payload.get("generated_at") or not isinstance(payload.get("policy"), dict):
            _logger.error("hero_briefing: missing required fields")
            self._err(503, "source_schema_invalid", "missing required fields")
            return

        self._json(200, payload, cache_control=f"public, max-age={CACHE_MAX_AGE}")
