"""
ESTATE Brain v0.2 — 한국 부동산 단지 단위 종합 판단 엔진

Source 출처 (feedback_master_rule_drift_audit 정합):
  - Perplexity 호출 결과 (2026-05-08, 사용자 직접) — 4 layer 가중치 + 3 cycle analog
  - Perplexity 호출 결과 (2026-05-08 추가) — 데이터 access + macro lead time + 재건축 6단계
  - plan: docs/ESTATE_BRAIN_V0_PLAN.md (283줄, commit b6a2732)

핵심 구조 (plan v0.2):
  4 Layer Valuation (L4 실거래 0.45 + L2 전세가율 0.275 + L3 Cap Rate 0.175 + L1 PIR 0.125)
  + 고평가 4중 신호 카운터 (PIR z-score / 전세가율 / Cap-국고채 / KB-실거래 괴리)
  + Cycle Analog 분류 (Shock-Recovery 1997 / Debt-Deflation Drag 2008 / Rate-Shock Rebound 2022)
  + Lead Time Signals (전세 1-3M / 미분양 3-6M / 착공 26-30M / 호가 1M / 금리 3-18M 비선형)
  + Redevelopment Stage (6 enum: district_designation → completion + 가격 phase)

VERITY 광범위 패턴 이식 X (feedback_estate_density_first 정합).
가중치/임계는 `data/estate_constitution.json` SSOT (V0 분리, commit 21 박힘).
JSON 부재 시 코드 default fallback.
"""
from __future__ import annotations

import json
import math
import os
from typing import Any, Dict, List, Literal, Optional, Tuple

# ────────────────────────────────────────────────────────────
# Constitution loader (verity_brain v5 _load_constitution 패턴 정합)

_CONSTITUTION_CACHE: Optional[Dict[str, Any]] = None


def _constitution_path() -> str:
    # api/intelligence/estate_brain.py → repo_root/data/estate_constitution.json
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(here, "..", "..", "data", "estate_constitution.json"))


def _load_constitution() -> Dict[str, Any]:
    global _CONSTITUTION_CACHE
    if _CONSTITUTION_CACHE is not None:
        return _CONSTITUTION_CACHE
    try:
        with open(_constitution_path(), "r", encoding="utf-8") as f:
            _CONSTITUTION_CACHE = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        _CONSTITUTION_CACHE = {}
    return _CONSTITUTION_CACHE


def _reset_constitution_cache() -> None:
    """테스트 전용 — constitution JSON 변경 후 재로드."""
    global _CONSTITUTION_CACHE
    _CONSTITUTION_CACHE = None


# ────────────────────────────────────────────────────────────
# Source: Perplexity 2026-05-08 한국 실무 가중치 (plan v0.2 §4 Layer Valuation)
# constitution JSON 부재 시 fallback (V0 default = JSON 의 동일값).
_DEFAULT_LAYER_WEIGHTS: Dict[str, float] = {
    "L4_neighbor": 0.45,
    "L2_jeonse":   0.275,
    "L3_cap_rate": 0.175,
    "L1_pir":      0.10,
}


def _layer_weights() -> Dict[str, float]:
    const = _load_constitution()
    weights = const.get("layer_weights")
    if not isinstance(weights, dict):
        return _DEFAULT_LAYER_WEIGHTS
    return {k: weights.get(k, _DEFAULT_LAYER_WEIGHTS[k]) for k in _DEFAULT_LAYER_WEIGHTS}


# legacy export — backward compat (테스트 / 외부 import)
LAYER_WEIGHTS: Dict[str, float] = _layer_weights()


def _extreme_thresholds() -> Dict[str, float]:
    const = _load_constitution()
    et = const.get("extreme_thresholds") or {}
    return {
        "pir_z":          float(et.get("pir_z_threshold", 1.0)),
        "jeonse_ratio":   float(et.get("jeonse_ratio_pct", 50.0)),
        "cap_treasury":   float(et.get("cap_treasury_bp", 100)),
        "kb_gap":         float(et.get("kb_actual_gap_pct", 10.0)),
    }


_thr = _extreme_thresholds()
EXTREME_PIR_Z_THRESHOLD = _thr["pir_z"]
EXTREME_JEONSE_RATIO_PCT = _thr["jeonse_ratio"]
EXTREME_CAP_TREASURY_BP = _thr["cap_treasury"]
EXTREME_KB_GAP_PCT = _thr["kb_gap"]

# Source: Perplexity 2026-05-08 (plan v0.2 §3 cycle analog)
CYCLE_ANALOGS: List[Dict[str, Any]] = [
    {
        "name": "Shock-Recovery",
        "trigger": "환율·금리 25%",
        "year_label": "1997 IMF",
        "drop_seoul_pct": -18.2,
        "drop_nationwide_pct": -15.1,
        "shape": "V",
        "recovery_months": 50,
    },
    {
        "name": "Debt-Deflation Drag",
        "trigger": "가계부채 + 공급과잉",
        "year_label": "2008 GFC",
        "drop_seoul_pct": -12.0,
        "drop_gangnam3_pct": -10.0,
        "shape": "U",
        "recovery_months": 108,  # 9년+
    },
    {
        "name": "Rate-Shock Rebound",
        "trigger": "기준금리 0.5→3.5%",
        "year_label": "2022~",
        "drop_seoul_pct": -20.0,
        "drop_outskirts_pct": -30.0,
        "shape": "W",
        "recovery_months": 60,  # 진행 중 (3-6년 추정)
    },
]

# Source: Perplexity 2026-05-08 (plan v0.2 §V0.2 Macro lead time table)
LEAD_TIME_TABLE: Dict[str, Dict[str, Any]] = {
    "jeonse_price":        {"lead_months": 2,  "confidence": 5, "direction": "+"},
    "jeonse_ratio_high":   {"lead_months": 24, "confidence": 4, "direction": "ambivalent"},
    "construction_starts": {"lead_months": 28, "confidence": 4, "direction": "+"},
    "unsold_units":        {"lead_months": 4,  "confidence": 4, "direction": "-"},
    "asking_price":        {"lead_months": 1,  "confidence": 4, "direction": "+"},
    "social_sentiment":    {"lead_months": 2,  "confidence": 3, "direction": "+"},
    "rate_change":         {"lead_months": 6,  "confidence": 2, "direction": "-"},  # 5-6M 피크
}
FORWARD_RETURN_HORIZON_WEEKS = 26  # 6개월 (전세 lead 1-3M + 가격 반응 2-3M)

# Source: Perplexity 2026-05-08 (plan v0.2 §V0.2 재건축/재개발 6단계)
REDEVELOPMENT_STAGES: List[str] = [
    "district_designation",  # 정비구역 지정
    "union_setup",           # 조합설립 인가 (재건축 최대 상승)
    "business_plan",         # 사업시행 인가
    "management_plan",       # 관리처분 인가 (재개발 최대 상승, P값)
    "relocation",            # 이주·철거
    "completion",            # 준공·입주
]
STAGE_LABEL_KO: Dict[str, str] = {
    "district_designation": "정비구역 지정",
    "union_setup":          "조합설립 인가",
    "business_plan":        "사업시행 인가",
    "management_plan":      "관리처분 인가",
    "relocation":           "이주·철거",
    "completion":           "준공·입주",
}
# Source: 국토부 118 사업장 평균 (plan v0.2 §V0.2)
STAGE_AVG_MONTHS: Dict[str, int] = {
    "district_designation": 28,  # → union_setup 27.9M
    "union_setup":          31,  # → business_plan 31.3M
    "business_plan":        21,  # → management_plan 20.9M
    "management_plan":       9,  # → relocation 6-12M mid
    "relocation":           30,  # → completion 24-36M mid
    "completion":            0,
}


# ────────────────────────────────────────────────────────────
# Helpers (verity_brain 패턴 정합 — 함수 기반)

def _clip(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def _safe_float(v: Any, default: Optional[float] = None) -> Optional[float]:
    if v is None:
        return default
    try:
        x = float(v)
        if math.isnan(x) or math.isinf(x):
            return default
        return x
    except (TypeError, ValueError):
        return default


# ────────────────────────────────────────────────────────────
# Layer 1 — PIR (거시 sanity)
# 산식: PIR = P_매매 / 권역 중위 연소득
# 신뢰도: 추세 이탈 폭 (현재 - 10yr MA) > 절대 수준 (plan v0.2)
# 임계: z = (PIR - MA) / σ. z >= +1 → 거품 신호 (extreme), z <= -1 → 저평가
# 점수화: z=+1 → 0점, z=-1 → 100점, z=0 → 50점 선형 clip

def compute_layer_pir(
    price_won: float,
    annual_income_won: float,
    ma_10yr: Optional[float] = None,
    sigma_10yr: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    if not (price_won and annual_income_won and annual_income_won > 0):
        return None
    pir = price_won / annual_income_won

    if ma_10yr is None or sigma_10yr is None or sigma_10yr <= 0:
        # MA/σ 부재 시 절대 fallback (서울 아파트 정상 15-25, plan v0.2)
        if pir <= 15:
            score = 100.0
            verdict = "low"
        elif pir >= 25:
            score = 0.0
            verdict = "high"
        else:
            # 15 → 100, 25 → 0 선형
            score = 100 - ((pir - 15) / 10) * 100
            verdict = "balanced"
        z_score = None
    else:
        z_score = (pir - ma_10yr) / sigma_10yr
        # z=+1 → 0, z=-1 → 100, 선형 clip
        score = _clip(50 - z_score * 50)
        if z_score >= EXTREME_PIR_Z_THRESHOLD:
            verdict = "high"
        elif z_score <= -EXTREME_PIR_Z_THRESHOLD:
            verdict = "low"
        else:
            verdict = "balanced"

    return {
        "value": round(pir, 2),
        "10yr_ma": ma_10yr,
        "z_score": round(z_score, 2) if z_score is not None else None,
        "score": round(score, 1),
        "verdict": verdict,
    }


# ────────────────────────────────────────────────────────────
# Layer 2 — 전세가율 (내재가치 하방)
# 산식: ratio = P_전세 / P_매매 × 100
# 임계 (서울 10yr 평균 ~60%, plan v0.2):
#   ≥70: 매매 저평가 (갭투자 과열 동시)
#   55-70: 균형
#   50-55: 약 하락
#   <50: 매매 거품 (2009 35-40% 박힘)

def compute_layer_jeonse_ratio(
    jeonse_won: float,
    sale_won: float,
) -> Optional[Dict[str, Any]]:
    if not (jeonse_won and sale_won and sale_won > 0):
        return None
    ratio_pct = (jeonse_won / sale_won) * 100

    if ratio_pct >= 70:
        score = 100.0
        verdict = "very_high"
    elif ratio_pct >= 55:
        # 55 → 50, 70 → 100 선형
        score = 50 + ((ratio_pct - 55) / 15) * 50
        verdict = "balanced"
    elif ratio_pct >= 50:
        # 50 → 30, 55 → 50 선형
        score = 30 + ((ratio_pct - 50) / 5) * 20
        verdict = "low"
    else:
        # <50% 거품 영역 (50 → 30, 35 → 0)
        score = _clip(30 - ((50 - ratio_pct) / 15) * 30, lo=0)
        verdict = "bubble"

    return {
        "value": round(ratio_pct, 1),
        "score": round(score, 1),
        "verdict": verdict,
    }


# ────────────────────────────────────────────────────────────
# Layer 3 — Cap Rate (수익성 상한)
# 산식: cap_rate = NOI / P_매매 × 100
#   전세 단지는 전월세 전환율 5.0-5.5% 적용 (plan v0.2)
# 임계: spread = cap_rate - treasury_10y
#   spread > 0 → 채권 대비 매력
#   spread < -1.0pp (100bp) → compressed (역전 = 비매력 거품)

def compute_layer_cap_rate(
    noi_annual_won: float,
    sale_won: float,
    treasury_10y_pct: float,
) -> Optional[Dict[str, Any]]:
    if not (noi_annual_won and sale_won and sale_won > 0):
        return None
    cap_rate = (noi_annual_won / sale_won) * 100
    spread_pp = cap_rate - treasury_10y_pct

    # spread +1.0pp → 100, 0 → 50, -1.0pp → 0
    score = _clip(50 + spread_pp * 50)
    if spread_pp <= -(EXTREME_CAP_TREASURY_BP / 100.0):
        verdict = "compressed"
    elif spread_pp >= 1.0:
        verdict = "attractive"
    else:
        verdict = "balanced"

    return {
        "value": round(cap_rate, 2),
        "treasury_10y": round(treasury_10y_pct, 2),
        "spread_pp": round(spread_pp, 2),
        "score": round(score, 1),
        "verdict": verdict,
    }


def jeonse_to_noi_annual(
    jeonse_won: float,
    conversion_rate_pct: float = 5.25,  # 전월세 전환율 5.0-5.5% mid
) -> float:
    """전세 보증금 → 연 NOI 환산 (plan v0.2 산식 §L3 Cap Rate)."""
    return jeonse_won * (conversion_rate_pct / 100)


# ────────────────────────────────────────────────────────────
# Layer 4 — 인근 실거래 vs KB시세 (Primary Anchor)
# 산식: gap_pct = (recent_actual_avg - kb_price) / kb_price × 100
#   양수: 실거래가 KB 위 → 매수 압력 (저평가 X)
#   음수: 실거래가 KB 밑 → 거품 신호 (KB가 늦게 반영)
# 임계 (plan v0.2): |gap| > 10% → 4중 신호 trigger

def compute_layer_neighbor_gap(
    recent_actual_avg_won: float,
    kb_price_won: float,
) -> Optional[Dict[str, Any]]:
    if not (recent_actual_avg_won and kb_price_won and kb_price_won > 0):
        return None
    gap_pct = ((recent_actual_avg_won - kb_price_won) / kb_price_won) * 100

    # gap=0 → 50, gap=+10 → 100 (저평가 신호 — 실거래가 위), gap=-10 → 0 (거품)
    score = _clip(50 + gap_pct * 5)
    if gap_pct <= -EXTREME_KB_GAP_PCT:
        verdict = "kb_lagging_bubble"
    elif gap_pct >= EXTREME_KB_GAP_PCT:
        verdict = "actual_outpacing"
    else:
        verdict = "aligned"

    return {
        "kb_price": kb_price_won,
        "actual": recent_actual_avg_won,
        "gap_pct": round(gap_pct, 1),
        "score": round(score, 1),
        "verdict": verdict,
    }


# ────────────────────────────────────────────────────────────
# Valuation orchestrator — 4 layer 가중평균 + 4중 신호 카운터

def compute_valuation(
    layers: Dict[str, Optional[Dict[str, Any]]],
) -> Dict[str, Any]:
    """4 layer dict (L1_pir / L2_jeonse / L3_cap_rate / L4_neighbor) → weighted_score + signals.

    None layer 는 가중치에서 제외 + 가중치 재정규화.
    """
    weighted_sum = 0.0
    weight_total = 0.0
    layer_keys = {
        "L1_pir": "L1_pir",
        "L2_jeonse": "L2_jeonse",
        "L3_cap_rate": "L3_cap_rate",
        "L4_neighbor": "L4_neighbor",
    }
    for key, weight_key in layer_keys.items():
        layer = layers.get(key)
        if layer is None or layer.get("score") is None:
            continue
        w = LAYER_WEIGHTS[weight_key]
        weighted_sum += layer["score"] * w
        weight_total += w

    weighted_score = round(weighted_sum / weight_total, 1) if weight_total > 0 else None

    # 고평가 4중 신호 카운터 (각 layer verdict 기반)
    signals: List[str] = []
    pir = layers.get("L1_pir")
    if pir and pir.get("verdict") == "high":
        signals.append("pir_z_extreme")
    jeonse = layers.get("L2_jeonse")
    if jeonse and jeonse.get("value") is not None and jeonse["value"] < EXTREME_JEONSE_RATIO_PCT:
        signals.append("jeonse_ratio_below_50")
    cap = layers.get("L3_cap_rate")
    if cap and cap.get("verdict") == "compressed":
        signals.append("cap_treasury_inverted")
    nbr = layers.get("L4_neighbor")
    if nbr and nbr.get("verdict") == "kb_lagging_bubble":
        signals.append("kb_actual_gap_extreme")

    # primary anchor = L4 score (Plan v0.2 — 실거래가 1차 기준)
    primary_anchor_pct = nbr["score"] if nbr and nbr.get("score") is not None else None

    return {
        "primary_anchor_pct": primary_anchor_pct,
        "layers": layers,
        "weighted_score": weighted_score,
        "extreme_signals": signals,
        "extreme_signals_count": len(signals),
    }


# ────────────────────────────────────────────────────────────
# Cycle Analog — 3 패턴 nearest 분류 (Plan v0.2 §3)
# 입력 features: trigger / drop_pct / shape (현재 또는 lookback 추정)
# 출력: 가장 가까운 패턴 + 거리

def _analog_distance(
    target: Dict[str, Any],
    historical: Dict[str, Any],
) -> float:
    """간단 정규화 유클리드 distance.
    축: drop_pct (단위 20%) / recovery_months (60M) / shape match (0/1)."""
    drop_diff = abs(_safe_float(target.get("drop_pct"), 0.0) -
                    _safe_float(historical.get("drop_seoul_pct"), 0.0)) / 20.0
    months_diff = abs(_safe_float(target.get("duration_months"), 0.0) -
                      _safe_float(historical.get("recovery_months"), 0.0)) / 60.0
    shape_diff = 0.0 if target.get("shape") == historical.get("shape") else 0.5
    return round(math.sqrt(drop_diff ** 2 + months_diff ** 2 + shape_diff ** 2), 3)


def classify_cycle_analog(
    target: Dict[str, Any],
    current_phase_label: Optional[str] = None,
) -> Dict[str, Any]:
    """target 예: {"drop_pct": -18, "duration_months": 36, "shape": "W"}

    current_phase_label = 사용자/외부에서 주는 hint (없으면 nearest 1위 사용).
    """
    ranked = sorted(
        [
            {**h, "distance": _analog_distance(target, h)}
            for h in CYCLE_ANALOGS
        ],
        key=lambda h: h["distance"],
    )
    nearest = ranked[0]
    return {
        "current_phase": current_phase_label or nearest["name"],
        "nearest_historical": [
            {"name": r["name"], "year_label": r["year_label"],
             "shape": r["shape"], "distance": r["distance"]}
            for r in ranked
        ],
    }


# ────────────────────────────────────────────────────────────
# Lead Time Signals — 5 신호 (Plan v0.2 §V0.2 Macro lead time)

def compute_lead_time_signals(
    jeonse_3m_change_pct: Optional[float] = None,
    jeonse_ratio_pct: Optional[float] = None,
    construction_starts_yoy_pct: Optional[float] = None,
    unsold_units_yoy_pct: Optional[float] = None,
    rate_change_pp: Optional[float] = None,
) -> Dict[str, Any]:
    out: Dict[str, Any] = {}

    # 전세가격 1-3M lead (★★★★★, +)
    if jeonse_3m_change_pct is not None:
        if jeonse_3m_change_pct > 1.0:
            verdict = "moderate_up"
        elif jeonse_3m_change_pct > 2.5:
            verdict = "strong_up"
        elif jeonse_3m_change_pct < -1.0:
            verdict = "down"
        else:
            verdict = "flat"
        out["jeonse_3m_lead"] = {
            "value_pct": round(jeonse_3m_change_pct, 2),
            "lead_months": LEAD_TIME_TABLE["jeonse_price"]["lead_months"],
            "verdict": verdict,
        }

    # 전세가율 24M (양날: 80%+ 단기+/24M-)
    if jeonse_ratio_pct is not None:
        if jeonse_ratio_pct >= 80:
            verdict = "ambivalent_overheated"  # 단기+, 24M 후 -
        elif jeonse_ratio_pct >= 65:
            verdict = "supportive"
        elif jeonse_ratio_pct < 50:
            verdict = "reverse_lease_risk"  # 역전세
        else:
            verdict = "balanced"
        out["jeonse_ratio_24m"] = {
            "value_pct": round(jeonse_ratio_pct, 1),
            "lead_months": LEAD_TIME_TABLE["jeonse_ratio_high"]["lead_months"],
            "verdict": verdict,
        }

    # 착공 26-30M lead (+, 공급↓)
    if construction_starts_yoy_pct is not None:
        if construction_starts_yoy_pct < -10:
            verdict = "supply_tight_in_2y"
        elif construction_starts_yoy_pct > 10:
            verdict = "supply_overhang_in_2y"
        else:
            verdict = "neutral"
        out["construction_starts_lead"] = {
            "value_yoy_pct": round(construction_starts_yoy_pct, 1),
            "lead_months": LEAD_TIME_TABLE["construction_starts"]["lead_months"],
            "verdict": verdict,
        }

    # 미분양 3-6M lead (-)
    if unsold_units_yoy_pct is not None:
        if unsold_units_yoy_pct > 30:
            verdict = "negative_pressure_strong"
        elif unsold_units_yoy_pct > 10:
            verdict = "negative_pressure"
        elif unsold_units_yoy_pct < -10:
            verdict = "absorption"
        else:
            verdict = "neutral"
        out["unsold_units_lead"] = {
            "value_yoy_pct": round(unsold_units_yoy_pct, 1),
            "lead_months": LEAD_TIME_TABLE["unsold_units"]["lead_months"],
            "verdict": verdict,
        }

    # 금리 3M~18M 비선형 (-, 시기별 역전)
    if rate_change_pp is not None:
        # 단순 verdict — 산식은 전세가율 교호작용 V1
        if rate_change_pp >= 0.5:
            verdict = "tightening_pressure"
        elif rate_change_pp <= -0.5:
            verdict = "supportive"
        else:
            verdict = "neutral"
        out["rate_lead"] = {
            "rate_change_pp": round(rate_change_pp, 2),
            "lead_months": LEAD_TIME_TABLE["rate_change"]["lead_months"],
            "verdict": verdict,
            "non_linear_warning": "TVP-VAR 비선형 — 전세가율 교호작용 V1 calibration",
        }

    return {
        "signals": out,
        "forward_return_horizon_weeks": FORWARD_RETURN_HORIZON_WEEKS,
    }


# ────────────────────────────────────────────────────────────
# Redevelopment Stage — 6 enum + 가격 phase (Plan v0.2 §V0.2)

ProjectType = Literal["reconstruction", "redevelopment"]


def classify_redevelopment_stage(
    stage: str,
    project_type: ProjectType,
    months_in_stage: int = 0,
    valuation_announcement_pending: bool = False,
    general_subscription_announced: bool = False,
) -> Optional[Dict[str, Any]]:
    if stage not in REDEVELOPMENT_STAGES:
        return None

    # 가격 phase 매핑 — Plan v0.2 표 (재건축: 조합설립 / 재개발: 관리처분 = 최대 상승)
    if stage == "district_designation":
        price_phase = "pre_signal"
    elif stage == "union_setup":
        price_phase = "max_uplift" if project_type == "reconstruction" else "moderate_uplift"
    elif stage == "business_plan":
        price_phase = "post_peak_consolidation" if project_type == "reconstruction" else "mid_uplift"
    elif stage == "management_plan":
        price_phase = "post_peak_consolidation" if project_type == "reconstruction" else "max_uplift"
    elif stage == "relocation":
        price_phase = "rental_market_spillover"  # +5M 내 주변 전세가 급등 (plan v0.2 실증)
    else:  # completion
        price_phase = "new_build_premium"

    avg_total = STAGE_AVG_MONTHS.get(stage, 0)
    months_to_next = max(0, avg_total - months_in_stage) if avg_total > 0 else 0

    return {
        "stage": stage,
        "stage_label_ko": STAGE_LABEL_KO[stage],
        "project_type": project_type,
        "months_in_stage": months_in_stage,
        "months_to_next_stage_estimated": months_to_next,
        "price_phase": price_phase,
        "monitoring": {
            "valuation_announcement_pending": valuation_announcement_pending,
            "general_subscription_announced": general_subscription_announced,
        },
    }


# ────────────────────────────────────────────────────────────
# Top-level orchestrator

def compute_estate_brain(
    complex_id: str,
    as_of: str,
    # L1
    price_won: Optional[float] = None,
    annual_income_won: Optional[float] = None,
    pir_ma_10yr: Optional[float] = None,
    pir_sigma_10yr: Optional[float] = None,
    # L2
    jeonse_won: Optional[float] = None,
    # L3
    treasury_10y_pct: Optional[float] = None,
    # L4
    recent_actual_avg_won: Optional[float] = None,
    kb_price_won: Optional[float] = None,
    # cycle
    target_cycle: Optional[Dict[str, Any]] = None,
    current_phase_label: Optional[str] = None,
    # lead time
    jeonse_3m_change_pct: Optional[float] = None,
    jeonse_ratio_pct: Optional[float] = None,
    construction_starts_yoy_pct: Optional[float] = None,
    unsold_units_yoy_pct: Optional[float] = None,
    rate_change_pp: Optional[float] = None,
    # redev
    redevelopment_stage: Optional[str] = None,
    project_type: Optional[ProjectType] = None,
    months_in_stage: int = 0,
    valuation_announcement_pending: bool = False,
    general_subscription_announced: bool = False,
    # regional
    regional_split: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """단지 단위 ESTATE Brain V0 산출 — schema 정합 plan v0.2 §V0 schema."""
    # 4 Layer
    l1 = compute_layer_pir(price_won or 0, annual_income_won or 0,
                            pir_ma_10yr, pir_sigma_10yr) if price_won else None
    if jeonse_won and price_won:
        l2 = compute_layer_jeonse_ratio(jeonse_won, price_won)
    else:
        l2 = None
    if jeonse_won and price_won and treasury_10y_pct is not None:
        noi = jeonse_to_noi_annual(jeonse_won)
        l3 = compute_layer_cap_rate(noi, price_won, treasury_10y_pct)
    else:
        l3 = None
    if recent_actual_avg_won and kb_price_won:
        l4 = compute_layer_neighbor_gap(recent_actual_avg_won, kb_price_won)
    else:
        l4 = None

    valuation = compute_valuation({
        "L1_pir":      l1,
        "L2_jeonse":   l2,
        "L3_cap_rate": l3,
        "L4_neighbor": l4,
    })

    cycle_analog = classify_cycle_analog(
        target_cycle or {"drop_pct": -20, "duration_months": 36, "shape": "W"},
        current_phase_label,
    )

    lead_time = compute_lead_time_signals(
        jeonse_3m_change_pct=jeonse_3m_change_pct,
        jeonse_ratio_pct=jeonse_ratio_pct,
        construction_starts_yoy_pct=construction_starts_yoy_pct,
        unsold_units_yoy_pct=unsold_units_yoy_pct,
        rate_change_pp=rate_change_pp,
    )
    cycle_analog["lead_time_signals"] = lead_time["signals"]
    cycle_analog["forward_return_horizon_weeks"] = lead_time["forward_return_horizon_weeks"]

    redev = None
    if redevelopment_stage and project_type:
        redev = classify_redevelopment_stage(
            stage=redevelopment_stage,
            project_type=project_type,
            months_in_stage=months_in_stage,
            valuation_announcement_pending=valuation_announcement_pending,
            general_subscription_announced=general_subscription_announced,
        )

    return {
        "version": "v0.2",
        "as_of": as_of,
        "complex_id": complex_id,
        "valuation": valuation,
        "cycle_analog": cycle_analog,
        "redevelopment_stage": redev,
        "regional_split": regional_split or {
            "core": "강남3구·마용성",
            "non_core": "수도권 외곽",
        },
        "model_meta": {
            "factor_weights": "REF Perplexity 2026-05-08 (한국 실무 가중치)",
            "analog_source": "KB부동산·한국부동산원 1997/2008/2022",
            "lead_time_source": "Perplexity 2026-05-08 (TVP-VAR/Granger/패널)",
            "redev_source": "국토부 118 사업장 평균 + 처리기한제 2025.7~",
            "version": "v0_hardcoded",
        },
    }
