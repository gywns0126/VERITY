"""
GET /api/estate/brain — ESTATE Brain V0.2 schema (P1 Mock)

Plan v0.2: docs/ESTATE_BRAIN_V0_PLAN.md (commit b6a2732)
Core 산식: api/intelligence/estate_brain.py (commit 94ce0d0, project root, cron worker용)
입력 collectors:
  - vercel-api/api/landex/_clustering.py (RTMS 단지명, commit 84c5e41)
  - vercel-api/api/landex/_sources/molit.py (RTMS 실거래)
  - vercel-api/api/landex/_sources/kosis.py (KOSIS 권역 중위소득, V0 statId 환경변수 명세)
  - vercel-api/api/landex/_sources/rone.py (전세지수·전세가율·미분양)
  - api/collectors/ecos_macro.py (ECOS 기준금리·국고채 10y)

Query parameters:
    complex_id  단지 ID (예: 강남구_역삼동_래미안강남_2015) — clustering make_complex_id 산출
    gu          (대안) 구 단위 brain. complex_id 없을 때 fallback.
    scenario    "balanced" (default) | "high_pir" | "redev_uplift"
                결정적 mock — V1 cron 적재 결과 read-through 로 swap

응답 schema (estate_brain.compute_estate_brain V0.2):
  { version, as_of, complex_id, valuation, cycle_analog,
    redevelopment_stage, regional_split, model_meta }

T2 정합 (memory `feedback_estate_density_first` + `feedback_master_rule_drift_audit`):
  source 필드 = "v0_mock" 명시 (V1 wire 시 "cron_read_through"). 출처 mismatch 방지.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

KST = timezone(timedelta(hours=9))

LAYER_WEIGHTS = {
    "L4_neighbor": 0.45, "L2_jeonse": 0.275,
    "L3_cap_rate": 0.175, "L1_pir": 0.10,
}

VALID_SCENARIOS = ("balanced", "high_pir", "redev_uplift")


def _seeded(seed_str: str, idx: int) -> float:
    s = sum(ord(c) for c in seed_str) + idx * 137
    x = math.sin(s * 12.9898) * 43758.5453
    return abs(x - math.floor(x))


def _layer_pir(seed: str, scenario: str) -> dict:
    base = 18 + _seeded(seed, 1) * 4  # 18-22
    if scenario == "high_pir":
        base = 22 + _seeded(seed, 1) * 4  # 22-26
    z = (base - 18) / 2
    if z >= 1.0:
        verdict, score = "high", max(0.0, 50 - z * 50)
    elif z <= -1.0:
        verdict, score = "low", min(100.0, 50 - z * 50)
    else:
        verdict, score = "balanced", 50 - z * 50
    return {"value": round(base, 2), "10yr_ma": 18.0, "z_score": round(z, 2),
            "score": round(max(0, min(100, score)), 1), "verdict": verdict}


def _layer_jeonse(seed: str, scenario: str) -> dict:
    if scenario == "high_pir":
        ratio = 45 + _seeded(seed, 2) * 5  # 45-50 (bubble territory)
    else:
        ratio = 55 + _seeded(seed, 2) * 15  # 55-70
    if ratio >= 70:
        verdict, score = "very_high", 100.0
    elif ratio >= 55:
        verdict, score = "balanced", 50 + ((ratio - 55) / 15) * 50
    elif ratio >= 50:
        verdict, score = "low", 30 + ((ratio - 50) / 5) * 20
    else:
        verdict, score = "bubble", max(0.0, 30 - ((50 - ratio) / 15) * 30)
    return {"value": round(ratio, 1), "score": round(score, 1), "verdict": verdict}


def _layer_cap_rate(seed: str, scenario: str) -> dict:
    cap = 1.5 + _seeded(seed, 3) * 1.5  # 1.5-3.0%
    treasury = 3.2
    if scenario == "high_pir":
        cap = 1.0 + _seeded(seed, 3) * 0.8  # 1.0-1.8 → compressed
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


def _layer_neighbor(seed: str, scenario: str) -> dict:
    kb = 12e8 + _seeded(seed, 4) * 10e8  # 12억-22억
    actual_pct = -8 + _seeded(seed, 5) * 16  # -8% ~ +8%
    if scenario == "high_pir":
        actual_pct = -12 - _seeded(seed, 5) * 5  # -17% ~ -12% (bubble)
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


def _compute_valuation(layers: dict) -> dict:
    weighted = 0.0
    total_w = 0.0
    signals = []
    for key, layer in layers.items():
        if layer is None:
            continue
        w = LAYER_WEIGHTS.get(key, 0)
        weighted += layer["score"] * w
        total_w += w
    weighted_score = round(weighted / total_w, 1) if total_w > 0 else None

    pir = layers.get("L1_pir")
    if pir and pir.get("verdict") == "high":
        signals.append("pir_z_extreme")
    jeonse = layers.get("L2_jeonse")
    if jeonse and jeonse["value"] < 50:
        signals.append("jeonse_ratio_below_50")
    cap = layers.get("L3_cap_rate")
    if cap and cap["verdict"] == "compressed":
        signals.append("cap_treasury_inverted")
    nbr = layers.get("L4_neighbor")
    if nbr and nbr["verdict"] == "kb_lagging_bubble":
        signals.append("kb_actual_gap_extreme")

    return {
        "primary_anchor_pct": nbr["score"] if nbr else None,
        "layers": layers,
        "weighted_score": weighted_score,
        "extreme_signals": signals,
        "extreme_signals_count": len(signals),
    }


def _cycle_analog_block(scenario: str) -> dict:
    return {
        "current_phase": "Rate-Shock Rebound",
        "nearest_historical": [
            {"name": "Rate-Shock Rebound", "year_label": "2022~",
             "shape": "W", "distance": 0.18},
            {"name": "Shock-Recovery", "year_label": "1997 IMF",
             "shape": "V", "distance": 0.62},
            {"name": "Debt-Deflation Drag", "year_label": "2008 GFC",
             "shape": "U", "distance": 1.05},
        ],
        "lead_time_signals": {
            "jeonse_3m_lead":         {"value_pct": 1.2, "lead_months": 2, "verdict": "moderate_up"},
            "jeonse_ratio_24m":       {"value_pct": 58.0, "lead_months": 24, "verdict": "balanced"},
            "construction_starts_lead": {"value_yoy_pct": -12.0, "lead_months": 28, "verdict": "supply_tight_in_2y"},
            "unsold_units_lead":      {"value_yoy_pct": 18.0, "lead_months": 4, "verdict": "negative_pressure"},
            "rate_lead":              {"rate_change_pp": -0.25, "lead_months": 6, "verdict": "neutral",
                                       "non_linear_warning": "TVP-VAR 비선형 — 전세가율 교호작용 V1 calibration"},
        },
        "forward_return_horizon_weeks": 26,
    }


def _redev_block(scenario: str) -> dict | None:
    if scenario != "redev_uplift":
        return None
    return {
        "stage": "management_plan",
        "stage_label_ko": "관리처분 인가",
        "project_type": "redevelopment",
        "months_in_stage": 4,
        "months_to_next_stage_estimated": 5,
        "price_phase": "max_uplift",
        "monitoring": {
            "valuation_announcement_pending": True,
            "general_subscription_announced": False,
        },
    }


def _generate_brain(complex_id: str, scenario: str) -> dict:
    seed = f"{complex_id}-{scenario}-2026-05"
    layers = {
        "L1_pir":      _layer_pir(seed, scenario),
        "L2_jeonse":   _layer_jeonse(seed, scenario),
        "L3_cap_rate": _layer_cap_rate(seed, scenario),
        "L4_neighbor": _layer_neighbor(seed, scenario),
    }
    valuation = _compute_valuation(layers)
    return {
        "version": "v0.2",
        "as_of": datetime.now(KST).isoformat(timespec="seconds"),
        "complex_id": complex_id,
        "scenario": scenario,
        "valuation": valuation,
        "cycle_analog": _cycle_analog_block(scenario),
        "redevelopment_stage": _redev_block(scenario),
        "regional_split": {"core": "강남3구·마용성", "non_core": "수도권 외곽"},
        "model_meta": {
            "factor_weights": "REF Perplexity 2026-05-08 (한국 실무 가중치)",
            "analog_source": "KB부동산·한국부동산원 1997/2008/2022",
            "lead_time_source": "Perplexity 2026-05-08 (TVP-VAR/Granger/패널)",
            "redev_source": "국토부 118 사업장 평균 + 처리기한제 2025.7~",
            "version": "v0_hardcoded",
            "source": "v0_mock",  # T2 — V1 cron wire 시 "cron_read_through"
        },
    }


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            qs = parse_qs(urlparse(self.path).query)
            complex_id = (qs.get("complex_id", [""])[0] or "").strip()
            gu = (qs.get("gu", [""])[0] or "").strip()
            scenario = (qs.get("scenario", ["balanced"])[0] or "balanced").strip()

            if scenario not in VALID_SCENARIOS:
                self._json(400, {"error": "invalid_scenario",
                                 "allowed": list(VALID_SCENARIOS)})
                return

            if not complex_id and not gu:
                self._json(400, {"error": "missing_complex_id_or_gu",
                                 "hint": "?complex_id=강남구_역삼동_래미안강남_2015 또는 ?gu=강남구"})
                return

            target = complex_id or f"{gu}_aggregate"
            payload = _generate_brain(target, scenario)
            self._json(200, payload)
        except Exception as e:
            self._json(500, {"error": "internal", "detail": str(e)[:200]})

    def _json(self, status: int, body: dict):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(json.dumps(body, ensure_ascii=False).encode("utf-8"))
