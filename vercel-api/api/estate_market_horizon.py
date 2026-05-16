"""
estate_market_horizon.py — 5축 종합 verdict read-through endpoint

GET /api/estate/market-horizon → gh-pages 의 estate_market_horizon.json read-through

EstateMarketHorizon.tsx (market/ 폴더) 가 consume.
estate_sector_pulse / estate_policy_narrative 패턴 그대로.
"""
from __future__ import annotations

import json
import logging
import os
from http.server import BaseHTTPRequestHandler

import requests

_logger = logging.getLogger(__name__)

SOURCE_URL_ENV = "ESTATE_MARKET_HORIZON_SOURCE_URL"
TIMEOUT_SEC = 5
CACHE_MAX_AGE = 1800  # 30분 (synthesizer 갱신 주기보다 짧게)


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
            _logger.error("market_horizon: %s missing", SOURCE_URL_ENV)
            self._err(503, "config_missing", f"{SOURCE_URL_ENV} not configured")
            return

        try:
            r = requests.get(source_url, timeout=TIMEOUT_SEC)
        except requests.RequestException as e:
            _logger.error("market_horizon: source fetch failed: %s", e)
            self._err(503, "source_fetch_failed", "upstream unavailable")
            return

        if r.status_code != 200:
            self._err(503, "source_non_200", f"upstream {r.status_code}")
            return

        try:
            payload = r.json()
        except (ValueError, json.JSONDecodeError):
            self._err(503, "source_invalid_json", "upstream returned non-JSON")
            return

        if not isinstance(payload, dict):
            self._err(503, "source_schema_invalid", "expected JSON object")
            return
        if not payload.get("generated_at") or not payload.get("verdict") or not isinstance(payload.get("axes"), dict):
            self._err(503, "source_schema_invalid", "missing required fields")
            return

        self._json(200, payload, cache_control=f"public, max-age={CACHE_MAX_AGE}")
