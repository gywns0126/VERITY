"""
estate_policy_narrative.py — Weekly Policy Narrative read-through endpoint

GET /api/estate/policy-narrative → gh-pages 의 estate_policy_narrative.json read-through

PolicyPulse SECTION 4 ("WEEKLY BRIEF · 7D") 가 consume.
estate_hero_briefing 패턴 그대로 (T1·T2 트랩 정합 — silent fabricate / mock fallback X).
"""
from __future__ import annotations

import json
import logging
import os
from http.server import BaseHTTPRequestHandler

import requests

_logger = logging.getLogger(__name__)

SOURCE_URL_ENV = "ESTATE_POLICY_NARRATIVE_SOURCE_URL"
TIMEOUT_SEC = 5
# 주 1회 갱신이라 cache 보수적 (1h) — 굳이 5분 fresh 의미 없음
CACHE_MAX_AGE = 3600


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
            _logger.error("policy_narrative: %s missing", SOURCE_URL_ENV)
            self._err(503, "config_missing", f"{SOURCE_URL_ENV} not configured")
            return

        try:
            r = requests.get(source_url, timeout=TIMEOUT_SEC)
        except requests.RequestException as e:
            _logger.error("policy_narrative: source fetch failed: %s", e)
            self._err(503, "source_fetch_failed", "upstream unavailable")
            return

        if r.status_code != 200:
            _logger.error("policy_narrative: source returned %d", r.status_code)
            self._err(503, "source_non_200", f"upstream {r.status_code}")
            return

        try:
            payload = r.json()
        except (ValueError, json.JSONDecodeError) as e:
            _logger.error("policy_narrative: source not valid JSON: %s", e)
            self._err(503, "source_invalid_json", "upstream returned non-JSON")
            return

        if not isinstance(payload, dict):
            _logger.error("policy_narrative: payload not object")
            self._err(503, "source_schema_invalid", "expected JSON object")
            return
        if not payload.get("generated_at") or not payload.get("verdict"):
            _logger.error("policy_narrative: missing required fields (generated_at/verdict)")
            self._err(503, "source_schema_invalid", "missing required fields")
            return

        self._json(200, payload, cache_control=f"public, max-age={CACHE_MAX_AGE}")
