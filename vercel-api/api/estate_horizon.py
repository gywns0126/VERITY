"""
GET /api/estate/horizon — ESTATE 서울 종합 horizon V0 (P2 read-through)

Builder: api/builders/estate_brain_builder.py 가 estate_brain_snapshots.json 의
top-level "horizon" 키에 적재 (서울 25 gu lead_time 평균 → estate_horizon).

Source 산식: api/intelligence/estate_horizon.py (compute_estate_horizon)

흐름 (estate_brain endpoint 패턴 정합):
    1. ESTATE_BRAIN_SOURCE_URL fetch (snapshots.json read-through)
    2. payload["horizon"] 만 추출 + as_of/generated_at 메타 합쳐 반환
    3. fetch 실패 시 503 (T2 — mock fallback X)

거짓말 트랩 (estate_change_feed/estate_brain 패턴 정합):
    T1·T9 fabricate·silent X — fetch 실패 시 503 with error_code
    T2    live 실패 시 mock 으로 fall-back 하지 않음
    T29   source URL 절대
"""
from __future__ import annotations

import json
import logging
import os
from http.server import BaseHTTPRequestHandler

import requests

_logger = logging.getLogger(__name__)

SOURCE_URL_ENV = "ESTATE_BRAIN_SOURCE_URL"
TIMEOUT_SEC = 5
CACHE_MAX_AGE = 300


def _fetch_live(source_url: str) -> tuple[int, dict | None, str | None]:
    try:
        r = requests.get(source_url, timeout=TIMEOUT_SEC)
    except requests.RequestException as e:
        _logger.error("estate_horizon: source fetch failed: %s", e)
        return 503, None, "source_fetch_failed"
    if r.status_code != 200:
        _logger.error("estate_horizon: source non-200: %s", r.status_code)
        return 503, None, "source_non_200"
    try:
        return 200, r.json(), None
    except ValueError as e:
        _logger.error("estate_horizon: source invalid json: %s", e)
        return 503, None, "source_invalid_json"


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            source_url = (os.environ.get(SOURCE_URL_ENV) or "").strip()
            if not source_url:
                self._json(503, {"error": "source_url_unset",
                                 "env": SOURCE_URL_ENV})
                return

            status, payload, err = _fetch_live(source_url)
            if status != 200 or not payload:
                self._json(status, {"error": err or "source_failed"})
                return

            horizon = payload.get("horizon") or {}
            if not horizon or horizon.get("error"):
                self._json(503, {
                    "error": "horizon_unavailable",
                    "horizon_error": horizon.get("error"),
                    "generated_at": payload.get("generated_at"),
                })
                return

            out = {
                **horizon,
                "snapshot_meta": {
                    "generated_at": payload.get("generated_at"),
                    "schema_version": payload.get("schema_version"),
                },
            }
            self._json(200, out)
        except Exception as e:
            _logger.exception("estate_horizon: unexpected error")
            self._json(500, {"error": "internal_error", "detail": str(e)})

    def _json(self, status: int, body: dict) -> None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        if status == 200:
            self.send_header("Cache-Control",
                             f"public, s-maxage={CACHE_MAX_AGE}, stale-while-revalidate=60")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)
