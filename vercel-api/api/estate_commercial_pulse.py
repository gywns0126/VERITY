"""
estate_commercial_pulse.py — Commercial Pulse (오피스 + 중대형 상가 deep dive)

GET /api/estate/commercial-pulse
→ ESTATE_SECTOR_PULSE_SOURCE_URL read-through + commercial-only 추출 + 비교 메트릭

SectorPulse 와 차별:
  - SectorPulse: 4섹터 (아파트/오피스/상가/오피스텔) cross-comparison (시장 진단)
  - CommercialPulse: 오피스 + 중대형 상가 deep dive (commercial 트랙 분석)
    + YoY spread / yield spread / 종합 verdict / 컨텐츠 source attribution

데이터 source = SectorPulse 와 동일 (R-ONE) — 신규 cron/builder 없음.
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
CACHE_MAX_AGE = 3600

COMMERCIAL_SECTOR_KEYS = ("office", "retail_mid_large")

VERDICT_PRIORITY = {"BEARISH": 0, "UNAVAILABLE": 1, "NEUTRAL": 2, "BULLISH": 3}


def _extract_commercial(payload: dict) -> list[dict]:
    out = []
    for s in payload.get("sectors", []):
        if not isinstance(s, dict):
            continue
        if s.get("key") in COMMERCIAL_SECTOR_KEYS:
            out.append(s)
    return out


def _compute_yoy_spread(sectors: list[dict]) -> dict | None:
    by = {s.get("key"): s for s in sectors}
    o = by.get("office")
    r = by.get("retail_mid_large")
    if not o or not r:
        return None
    oy = o.get("yoy_change_pct")
    ry = r.get("yoy_change_pct")
    if oy is None or ry is None:
        return {"office_yoy_pct": oy, "retail_yoy_pct": ry, "spread_pct": None,
                "reason": "missing_yoy_in_one_or_both"}
    return {
        "office_yoy_pct": oy,
        "retail_yoy_pct": ry,
        "spread_pct": round(oy - ry, 2),
    }


def _compute_yield_spread(sectors: list[dict]) -> dict | None:
    by = {s.get("key"): s for s in sectors}
    o = by.get("office")
    r = by.get("retail_mid_large")
    if not o or not r:
        return None
    oy = o.get("yield_pct")
    ry = r.get("yield_pct")
    if oy is None or ry is None:
        return {"office_yield_pct": oy, "retail_yield_pct": ry, "spread_pct": None,
                "reason": "missing_yield_in_one_or_both"}
    return {
        "office_yield_pct": oy,
        "retail_yield_pct": ry,
        "spread_pct": round(oy - ry, 2),
    }


def _aggregate_verdict(sectors: list[dict]) -> str:
    """commercial 종합 verdict — 두 섹터 verdict 보수 합성.
    BEARISH any → BEARISH. 둘 다 UNAVAILABLE → UNAVAILABLE. 둘 다 BULLISH → BULLISH. 그 외 NEUTRAL.
    """
    if not sectors:
        return "UNAVAILABLE"
    vs = [s.get("verdict") for s in sectors if isinstance(s, dict)]
    if all(v == "UNAVAILABLE" for v in vs):
        return "UNAVAILABLE"
    if any(v == "BEARISH" for v in vs):
        return "BEARISH"
    if all(v == "BULLISH" for v in vs):
        return "BULLISH"
    return "NEUTRAL"


def _data_partial_flag(sectors: list[dict]) -> bool:
    """yield_pct 결측 또는 verdict=UNAVAILABLE 면 partial."""
    for s in sectors:
        if not isinstance(s, dict):
            continue
        if s.get("verdict") == "UNAVAILABLE":
            return True
        if s.get("yield_pct") is None:
            return True
    return False


def _has_stale_flag(sectors: list[dict]) -> bool:
    """섹터 중 하나라도 builder Fix A carry-forward(직전 good 값 유지) = stale 이면 True.

    [[project_estate_commercial_v0_design]] Fix A — R-ONE transient fetch 실패 시 직전 값을
    stale 마킹. per-sector stale 은 sectors 패스스루로 이미 전달되나, UI 가 쉽게 읽도록 최상위 노출.
    data_partial(결측)과 직교: stale 은 "값은 있으나 직전 것" = 다른 정직성 신호.
    """
    return any(isinstance(s, dict) and s.get("stale") is True for s in sectors)


def _build_response(payload: dict) -> dict:
    sectors = _extract_commercial(payload)
    return {
        "schema_version": "v0.1",
        "generated_at": payload.get("generated_at"),
        "commercial_verdict": _aggregate_verdict(sectors),
        "data_partial": _data_partial_flag(sectors),
        "has_stale": _has_stale_flag(sectors),
        "sectors": sectors,
        "yoy_spread": _compute_yoy_spread(sectors),
        "yield_spread": _compute_yield_spread(sectors),
        "source_pulse_overall_verdict": payload.get("overall_verdict"),
    }


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
            self._err(503, "config_missing", f"{SOURCE_URL_ENV} not configured")
            return
        try:
            r = requests.get(source_url, timeout=TIMEOUT_SEC)
        except requests.RequestException as e:
            _logger.error("commercial_pulse: source fetch failed: %s", e)
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
        if not isinstance(payload, dict) or not payload.get("generated_at") or not isinstance(payload.get("sectors"), list):
            self._err(503, "source_schema_invalid", "missing required fields")
            return

        body = _build_response(payload)
        self._json(200, body, cache_control=f"public, max-age={CACHE_MAX_AGE}")
