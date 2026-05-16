"""
estate_sector_pulse.py — Sector Pulse read-through endpoint

GET /api/estate/sector-pulse → gh-pages 의 estate_sector_pulse.json read-through

SectorPulse.tsx (market/ 폴더) 가 consume.
estate_hero_briefing / estate_policy_narrative 패턴 그대로.
"""
from __future__ import annotations

import json
import logging
import os
from http.server import BaseHTTPRequestHandler

import requests

_logger = logging.getLogger(__name__)

SOURCE_URL_ENV = "ESTATE_SECTOR_PULSE_SOURCE_URL"
TIMEOUT_SEC = 5
CACHE_MAX_AGE = 3600   # 주 1회 갱신, 1h cache 충분


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
            _logger.error("sector_pulse: %s missing", SOURCE_URL_ENV)
            self._err(503, "config_missing", f"{SOURCE_URL_ENV} not configured")
            return

        try:
            r = requests.get(source_url, timeout=TIMEOUT_SEC)
        except requests.RequestException as e:
            _logger.error("sector_pulse: source fetch failed: %s", e)
            self._err(503, "source_fetch_failed", "upstream unavailable")
            return

        if r.status_code != 200:
            _logger.error("sector_pulse: source returned %d", r.status_code)
            self._err(503, "source_non_200", f"upstream {r.status_code}")
            return

        try:
            payload = r.json()
        except (ValueError, json.JSONDecodeError) as e:
            _logger.error("sector_pulse: source not valid JSON: %s", e)
            self._err(503, "source_invalid_json", "upstream returned non-JSON")
            return

        if not isinstance(payload, dict):
            self._err(503, "source_schema_invalid", "expected JSON object")
            return
        if not payload.get("generated_at") or not isinstance(payload.get("sectors"), list):
            _logger.error("sector_pulse: missing required fields (generated_at/sectors)")
            self._err(503, "source_schema_invalid", "missing required fields")
            return

        self._json(200, payload, cache_control=f"public, max-age={CACHE_MAX_AGE}")
