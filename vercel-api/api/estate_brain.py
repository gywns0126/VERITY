"""
GET /api/estate/brain — ESTATE Brain V0.2 (P2 read-through + 개발 mock toggle)

Plan v0.2: docs/ESTATE_BRAIN_V0_PLAN.md (commit b6a2732)
Core 산식: api/intelligence/estate_brain.py (commit 94ce0d0)
Builder cron: api/builders/estate_brain_builder.py (KST 10:00 평일)
  → data/estate_brain_snapshots.json → publish-data → gh-pages
  → 이 endpoint 가 ESTATE_BRAIN_SOURCE_URL 로 read-through

흐름 (estate_change_feed P2 read-through 정합):
    1. scenario=live (default) → ESTATE_BRAIN_SOURCE_URL fetch
    2. scenario=mock           → 결정적 mock (개발 toggle, scenario 별 차별화 보존)
    3. live fetch 실패         → 503 (T2 — mock fallback X). 컴포넌트가 명시 에러 렌더.

Query parameters:
    complex_id  단지 ID (예: 강남구_대치동_은마_1979) — clustering make_complex_id 산출
    gu          (대안) 구 단위 aggregate. complex_id 없을 때 fallback.
    scenario    "live" (default) | "mock_balanced" | "mock_high_pir" | "mock_redev_uplift"

거짓말 트랩 (estate_change_feed 패턴 정합):
    T1·T9 fabricate·silent X — fetch 실패 시 503 with error_code
    T2    live 실패 시 mock 으로 fall-back 하지 않음 (mock 는 명시 query 만)
    T29   source URL 절대 — env 가 절대 URL
"""
from __future__ import annotations

import json
import logging
import math
import os
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

import requests

_logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))

SOURCE_URL_ENV = "ESTATE_BRAIN_SOURCE_URL"
TIMEOUT_SEC = 5
CACHE_MAX_AGE = 300  # 5분 — builder 1회/일 + 빠른 dispatch 회복

LAYER_WEIGHTS = {
    "L4_neighbor": 0.45, "L2_jeonse": 0.275,
    "L3_cap_rate": 0.175, "L1_pir": 0.10,
}

MOCK_SCENARIOS = ("mock_balanced", "mock_high_pir", "mock_redev_uplift")


# ─────────────────────────────────────────────────
# Live fetch (P2 read-through)
# ─────────────────────────────────────────────────

def _fetch_live(source_url: str) -> tuple[int, dict | None, str | None]:
    try:
        r = requests.get(source_url, timeout=TIMEOUT_SEC)
    except requests.RequestException as e:
        _logger.error("estate_brain: source fetch failed: %s", e)
        return 503, None, "source_fetch_failed"
    if r.status_code != 200:
        _logger.error("estate_brain: source non-200: %s", r.status_code)
        return 503, None, "source_non_200"
    try:
        payload = r.json()
    except ValueError as e:
        _logger.error("estate_brain: source invalid json: %s", e)
        return 503, None, "source_invalid_json"
    return 200, payload, None


def _extract_target(
    snapshots: dict,
    complex_id: str | None,
    gu: str | None,
) -> tuple[int, dict | None, str | None]:
    """snapshots.json → 단지 또는 구 aggregate brain 추출.

    snapshots schema (estate_brain_builder):
      { schema_version, generated_at, macro, gu_aggregates: {gu: brain},
        complexes: {complex_id: brain}, diagnostics }
    """
    if complex_id:
        complexes = snapshots.get("complexes") or {}
        target = complexes.get(complex_id)
        if not target:
            return 404, None, "complex_id_not_in_watchlist"
        return 200, target, None
    if gu:
        gu_aggregates = snapshots.get("gu_aggregates") or {}
        target = gu_aggregates.get(gu)
        if not target:
            return 404, None, "gu_not_in_aggregates"
        return 200, target, None
    return 400, None, "missing_complex_id_or_gu"


# ─────────────────────────────────────────────────
# Mock (개발 toggle — scenario=mock_*)
# ─────────────────────────────────────────────────

def _seeded(seed_str: str, idx: int) -> float:
    s = sum(ord(c) for c in seed_str) + idx * 137
    x = math.sin(s * 12.9898) * 43758.5453
    return abs(x - math.floor(x))


def _mock_layer_pir(seed: str, scenario: str) -> dict:
    base = 18 + _seeded(seed, 1) * 4
    if scenario == "mock_high_pir":
        base = 22 + _seeded(seed, 1) * 4
    z = (base - 18) / 2
    if z >= 1.0:
        verdict, score = "high", max(0.0, 50 - z * 50)
    elif z <= -1.0:
        verdict, score = "low", min(100.0, 50 - z * 50)
    else:
        verdict, score = "balanced", 50 - z * 50
    return {"value": round(base, 2), "10yr_ma": 18.0, "z_score": round(z, 2),
            "score": round(max(0, min(100, score)), 1), "verdict": verdict}


def _mock_layer_jeonse(seed: str, scenario: str) -> dict:
    if scenario == "mock_high_pir":
        ratio = 45 + _seeded(seed, 2) * 5
    else:
        ratio = 55 + _seeded(seed, 2) * 15
    if ratio >= 70:
        verdict, score = "very_high", 100.0
    elif ratio >= 55:
        verdict, score = "balanced", 50 + ((ratio - 55) / 15) * 50
    elif ratio >= 50:
        verdict, score = "low", 30 + ((ratio - 50) / 5) * 20
    else:
        verdict, score = "bubble", max(0.0, 30 - ((50 - ratio) / 15) * 30)
    return {"value": round(ratio, 1), "score": round(score, 1), "verdict": verdict}


def _mock_layer_cap(seed: str, scenario: str) -> dict:
    cap = 1.5 + _seeded(seed, 3) * 1.5
    treasury = 3.2
    if scenario == "mock_high_pir":
        cap = 1.0 + _seeded(seed, 3) * 0.8
    spread = cap - treasury
    score = max(0.0, min(100.0, 50 + spread * 50))
    if spread <= -1.0:
        verdict = "compressed"
    elif spread >= 1.0:
        verdict = "attractive"
    else:
        verdict = "balanced"
    return {"value": round(cap, 2), "treasury_10y": treasury,
            "spread_pp": round(spread, 2), "score": round(score, 1), "verdict": verdict}


def _mock_layer_neighbor(seed: str, scenario: str) -> dict:
    kb = 12e8 + _seeded(seed, 4) * 10e8
    actual_pct = -8 + _seeded(seed, 5) * 16
    if scenario == "mock_high_pir":
        actual_pct = -12 - _seeded(seed, 5) * 5
    actual = kb * (1 + actual_pct / 100)
    score = max(0.0, min(100.0, 50 + actual_pct * 5))
    if actual_pct <= -10:
        verdict = "kb_lagging_bubble"
    elif actual_pct >= 10:
        verdict = "actual_outpacing"
    else:
        verdict = "aligned"
    return {"kb_price": round(kb), "actual": round(actual),
            "gap_pct": round(actual_pct, 1), "score": round(score, 1), "verdict": verdict}


def _mock_compute_valuation(layers: dict) -> dict:
    weighted, total_w, signals = 0.0, 0.0, []
    for k, layer in layers.items():
        if not layer:
            continue
        w = LAYER_WEIGHTS.get(k, 0)
        weighted += layer["score"] * w
        total_w += w
    weighted_score = round(weighted / total_w, 1) if total_w > 0 else None

    pir = layers.get("L1_pir")
    if pir and pir.get("verdict") == "high":
        signals.append("pir_z_extreme")
    j = layers.get("L2_jeonse")
    if j and j["value"] < 50:
        signals.append("jeonse_ratio_below_50")
    c = layers.get("L3_cap_rate")
    if c and c["verdict"] == "compressed":
        signals.append("cap_treasury_inverted")
    n = layers.get("L4_neighbor")
    if n and n["verdict"] == "kb_lagging_bubble":
        signals.append("kb_actual_gap_extreme")

    return {
        "primary_anchor_pct": n["score"] if n else None,
        "layers": layers,
        "weighted_score": weighted_score,
        "extreme_signals": signals,
        "extreme_signals_count": len(signals),
    }


def _mock_cycle_block() -> dict:
    return {
        "current_phase": "Rate-Shock Rebound",
        "nearest_historical": [
            {"name": "Rate-Shock Rebound", "year_label": "2022~", "shape": "W", "distance": 0.18},
            {"name": "Shock-Recovery", "year_label": "1997 IMF", "shape": "V", "distance": 0.62},
            {"name": "Debt-Deflation Drag", "year_label": "2008 GFC", "shape": "U", "distance": 1.05},
        ],
        "lead_time_signals": {
            "jeonse_3m_lead":         {"value_pct": 1.2, "lead_months": 2, "verdict": "moderate_up"},
            "jeonse_ratio_24m":       {"value_pct": 58.0, "lead_months": 24, "verdict": "balanced"},
            "construction_starts_lead": {"value_yoy_pct": -12.0, "lead_months": 28, "verdict": "supply_tight_in_2y"},
            "unsold_units_lead":      {"value_yoy_pct": 18.0, "lead_months": 4, "verdict": "negative_pressure"},
            "rate_lead":              {"rate_change_pp": -0.25, "lead_months": 6, "verdict": "neutral"},
        },
        "forward_return_horizon_weeks": 26,
    }


def _mock_redev_block(scenario: str) -> dict | None:
    if scenario != "mock_redev_uplift":
        return None
    return {
        "stage": "management_plan", "stage_label_ko": "관리처분 인가",
        "project_type": "redevelopment", "months_in_stage": 4,
        "months_to_next_stage_estimated": 5, "price_phase": "max_uplift",
        "monitoring": {
            "valuation_announcement_pending": True,
            "general_subscription_announced": False,
        },
    }


def _generate_mock(complex_id: str, scenario: str) -> dict:
    seed = f"{complex_id}-{scenario}-2026-05"
    layers = {
        "L1_pir":      _mock_layer_pir(seed, scenario),
        "L2_jeonse":   _mock_layer_jeonse(seed, scenario),
        "L3_cap_rate": _mock_layer_cap(seed, scenario),
        "L4_neighbor": _mock_layer_neighbor(seed, scenario),
    }
    return {
        "version": "v0.2",
        "as_of": datetime.now(KST).isoformat(timespec="seconds"),
        "complex_id": complex_id,
        "scenario": scenario,
        "valuation": _mock_compute_valuation(layers),
        "cycle_analog": _mock_cycle_block(),
        "redevelopment_stage": _mock_redev_block(scenario),
        "regional_split": {"core": "강남3구·마용성", "non_core": "수도권 외곽"},
        "model_meta": {
            "factor_weights": "REF Perplexity 2026-05-08 (한국 실무 가중치)",
            "version": "v0_hardcoded",
            "source": "v0_mock",
        },
    }


# ─────────────────────────────────────────────────
# Handler
# ─────────────────────────────────────────────────

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            qs = parse_qs(urlparse(self.path).query)
            complex_id = (qs.get("complex_id", [""])[0] or "").strip()
            gu = (qs.get("gu", [""])[0] or "").strip()
            scenario = (qs.get("scenario", ["live"])[0] or "live").strip()

            if scenario in MOCK_SCENARIOS:
                target = complex_id or (f"{gu}_aggregate" if gu else "mock_default")
                self._json(200, _generate_mock(target, scenario))
                return

            if scenario != "live":
                self._json(400, {"error": "invalid_scenario",
                                 "allowed": ["live"] + list(MOCK_SCENARIOS)})
                return

            # Live read-through
            source_url = (os.environ.get(SOURCE_URL_ENV) or "").strip()
            if not source_url:
                self._json(503, {"error": "config_missing",
                                 "detail": f"{SOURCE_URL_ENV} 환경변수 미설정"})
                return

            status, snapshots, err = _fetch_live(source_url)
            if status != 200 or snapshots is None:
                self._json(status, {"error": err or "source_unavailable"})
                return

            if not (complex_id or gu):
                self._json(400, {"error": "missing_complex_id_or_gu",
                                 "hint": "?complex_id=강남구_대치동_은마_1979 또는 ?gu=강남구"})
                return

            t_status, target, t_err = _extract_target(snapshots, complex_id, gu)
            if t_status != 200 or target is None:
                self._json(t_status, {"error": t_err or "not_found"})
                return

            # 응답 정합 — snapshots 의 macro / generated_at 메타 노출
            response = {
                **target,
                "snapshot_meta": {
                    "generated_at": snapshots.get("generated_at"),
                    "schema_version": snapshots.get("schema_version"),
                    "diagnostics": snapshots.get("diagnostics"),
                },
            }
            self._json(200, response)

        except Exception as e:
            _logger.exception("estate_brain: handler error")
            self._json(500, {"error": "internal", "detail": str(e)[:200]})

    def _json(self, status: int, body: dict):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control",
                         f"public, max-age={CACHE_MAX_AGE}" if status == 200 else "no-store")
        self.end_headers()
        self.wfile.write(json.dumps(body, ensure_ascii=False).encode("utf-8"))
