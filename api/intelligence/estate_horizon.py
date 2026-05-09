"""
EstateHorizon V0 — "한국 부동산 어디까지 가나" 답하는 컴포넌트.

VERITY market_horizon 패턴 차용 (cycle stage + verdict + horizon 분포).
ESTATE 본성 정합:
  - 데이터 빈도: 월간/분기 (분/시간 단위 X — feedback_estate_density_first)
  - horizon 단위: 3m / 6m / 12m / 24m (1m 빠짐, 24m 추가 — 부동산 사이클 길음)

출력 3축:
  1. cycle_stage 5단계 (recovery / expansion / peak / contraction / depression)
  2. verdict 한 줄
  3. horizon return 분포 (한국 부동산 사이클 1997/2008/2014/2020/2022 lookup)

Source 출처 (feedback_master_rule_drift_audit 정합):
  - estate_brain.compute_lead_time_signals 의 5 신호 (Perplexity 2026-05-08 TVP-VAR)
  - estate_brain.classify_cycle_analog 의 3 historical 패턴 (KB·한국부동산원 1997/2008/2022)
  - 5단계 stage 분류 임계 = 자체 결정 (Perplexity Lead Time + KB 분포 근사)
  - horizon 분포 = 한국 KB 매매가격지수 1986-2024 분기 lookup (V0 hardcoded approximation)
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────
# 1) 5단계 stage 분류 (rule-based, Lead Time Signals 가중 합산)
# 자체 신호 명시 (feedback_source_attribution_discipline) — 임계는 calibration 큐잉
#
# 입력: estate_brain.compute_lead_time_signals 의 signals dict
#   - jeonse_3m_lead.verdict ∈ {strong_up, moderate_up, flat, down}
#   - jeonse_ratio_24m.verdict ∈ {ambivalent_overheated, supportive, balanced, reverse_lease_risk}
#   - construction_starts_lead.verdict ∈ {supply_tight_in_2y, neutral, supply_overhang_in_2y}
#   - unsold_units_lead.verdict ∈ {absorption, neutral, negative_pressure, negative_pressure_strong}
#   - rate_lead.verdict ∈ {supportive, neutral, tightening_pressure}
#
# 출력: 5단계 stage
STAGE_LABEL_KO: Dict[str, str] = {
    "recovery":    "회복기",
    "expansion":   "확장기",
    "peak":        "정점기",
    "contraction": "수축기",
    "depression":  "침체기",
    "unknown":     "데이터 부족",
}


def classify_estate_stage(lead_signals: Dict[str, Any]) -> str:
    """5단계 사이클 stage 분류.

    Rule (자체 결정 신호):
      - depression: 미분양 강압박 + 역전세 + 금리 긴축
      - contraction: 미분양 압박 + 전세 약세 또는 정점 과열 후 하락
      - peak: 전세가율 80%+ (ambivalent_overheated) + 미분양 흡수 한계
      - expansion: 전세 강세 + 미분양 흡수 + 공급 타이트
      - recovery: 전세 회복 + 미분양 absorption + 금리 supportive
    """
    if not lead_signals:
        return "unknown"

    j_lead = (lead_signals.get("jeonse_3m_lead") or {}).get("verdict")
    j_ratio = (lead_signals.get("jeonse_ratio_24m") or {}).get("verdict")
    unsold = (lead_signals.get("unsold_units_lead") or {}).get("verdict")
    construct = (lead_signals.get("construction_starts_lead") or {}).get("verdict")
    rate = (lead_signals.get("rate_lead") or {}).get("verdict")

    # 1) depression: 미분양 강압박 + 역전세 또는 전세 강하강
    if unsold == "negative_pressure_strong":
        if j_ratio == "reverse_lease_risk" or j_lead == "down":
            return "depression"

    # 2) contraction: 미분양 압박 + 전세 부진
    if unsold in ("negative_pressure", "negative_pressure_strong"):
        if j_lead in ("down", "flat"):
            return "contraction"

    # 3) peak: 전세가율 80%+ (ambivalent_overheated) — Perplexity 양날 신호
    #    + 미분양 absorption 정체 (neutral 또는 negative_pressure 시작)
    if j_ratio == "ambivalent_overheated":
        return "peak"

    # 4) expansion: 전세 강세 + (미분양 absorption 또는 공급 타이트 또는 금리 supportive)
    if j_lead == "strong_up" and unsold == "absorption":
        return "expansion"
    if j_lead == "strong_up" and (construct == "supply_tight_in_2y" or rate == "supportive"):
        return "expansion"

    # 5) recovery: 전세 회복 (moderate_up) + 미분양 흡수 또는 금리 지원
    if j_lead == "moderate_up" and unsold == "absorption":
        return "recovery"
    if j_lead == "moderate_up" and rate == "supportive":
        return "recovery"
    if j_lead == "flat" and unsold == "absorption":
        return "recovery"

    return "unknown"


# ────────────────────────────────────────────────────────────
# 2) Horizon return 분포 (KB 매매가격지수 1986-2024 분기 lookup)
# V0 hardcoded — V1 에서 actual KB historical series 동적 계산.
# 단위: percent (%) 매매가격지수 변화율. VERITY market_horizon 과 다름 (decimal X).
# horizon: 3m / 6m / 12m / 24m (한국 부동산 사이클 길음)

_ESTATE_HORIZON_LOOKUP: Dict[str, Dict[str, tuple]] = {
    "recovery": {
        "3m":  ( 0.8, -0.5,  2.0, -2.0,  4.0),   # median, p25, p75, p5, p95 (%)
        "6m":  ( 2.5,  0.0,  4.5, -2.0,  7.0),
        "12m": ( 6.0,  2.0,  9.5, -1.0, 14.0),
        "24m": (13.0,  6.0, 19.0,  2.0, 28.0),
    },
    "expansion": {
        "3m":  ( 1.5,  0.5,  3.0, -0.5,  5.5),
        "6m":  ( 3.5,  1.5,  6.0, -1.0,  9.0),
        "12m": ( 8.0,  4.0, 12.0,  0.0, 18.0),
        "24m": (16.0,  8.0, 24.0,  3.0, 35.0),
    },
    "peak": {
        "3m":  ( 0.5, -1.5,  2.0, -4.0,  3.5),
        "6m":  ( 0.0, -3.5,  3.0, -7.0,  5.5),
        "12m": (-2.0, -8.0,  4.0, -15.0,  9.0),
        "24m": (-5.0, -15.0,  6.0, -25.0, 14.0),
    },
    "contraction": {
        "3m":  (-1.0, -3.0,  0.5, -6.0,  2.0),
        "6m":  (-2.5, -6.0,  0.0, -12.0,  3.0),
        "12m": (-5.0, -12.0,  1.0, -22.0,  6.0),
        "24m": (-7.0, -18.0,  3.0, -30.0, 10.0),
    },
    "depression": {
        "3m":  (-2.0, -5.0, -0.5, -10.0,  1.5),
        "6m":  (-3.5, -8.0,  0.5, -15.0,  3.0),
        "12m": (-4.0, -12.0,  3.0, -22.0,  7.0),
        "24m": ( 2.0, -10.0, 14.0, -25.0, 25.0),  # 평균회귀 시작
    },
    "unknown": {
        "3m":  ( 0.5, -1.5,  2.0, -4.0,  4.0),
        "6m":  ( 1.5, -3.0,  4.0, -7.0,  7.5),
        "12m": ( 3.5, -4.0,  9.0, -12.0, 14.0),
        "24m": ( 8.0, -5.0, 18.0, -18.0, 28.0),
    },
}


def horizon_returns(stage: str) -> Dict[str, Dict[str, float]]:
    table = _ESTATE_HORIZON_LOOKUP.get(stage, _ESTATE_HORIZON_LOOKUP["unknown"])
    out: Dict[str, Dict[str, float]] = {}
    for h, (med, p25, p75, p5, p95) in table.items():
        out[h] = {"median_pct": med, "p25_pct": p25, "p75_pct": p75, "p5_pct": p5, "p95_pct": p95}
    return out


# ────────────────────────────────────────────────────────────
# 3) Verdict 한 줄

def _dominant_signal_label(lead_signals: Dict[str, Any]) -> Optional[str]:
    """가장 우세한 lead signal 한 줄 라벨 (verdict 보강용)."""
    if not lead_signals:
        return None

    # 우선순위: 미분양 압박 > 전세 추세 > 금리 > 공급
    unsold = (lead_signals.get("unsold_units_lead") or {}).get("verdict")
    if unsold == "negative_pressure_strong":
        return "미분양 강압박"
    if unsold == "negative_pressure":
        return "미분양 압박"
    if unsold == "absorption":
        return "미분양 흡수"

    j_lead = (lead_signals.get("jeonse_3m_lead") or {}).get("verdict")
    if j_lead == "strong_up":
        return "전세 강세"
    if j_lead == "moderate_up":
        return "전세 회복"
    if j_lead == "down":
        return "전세 약세"

    j_ratio = (lead_signals.get("jeonse_ratio_24m") or {}).get("verdict")
    if j_ratio == "ambivalent_overheated":
        return "전세가율 80%+ 과열"
    if j_ratio == "reverse_lease_risk":
        return "역전세 위험"

    rate = (lead_signals.get("rate_lead") or {}).get("verdict")
    if rate == "tightening_pressure":
        return "금리 긴축"
    if rate == "supportive":
        return "금리 지원"

    return None


def build_verdict(
    stage: str,
    horizon_12m_med: Optional[float],
    dominant: Optional[str],
    analog_name: Optional[str] = None,
) -> str:
    parts: List[str] = [STAGE_LABEL_KO.get(stage, stage)]
    if dominant:
        parts.append(dominant)
    if horizon_12m_med is not None:
        sign = "+" if horizon_12m_med >= 0 else ""
        parts.append(f"12M median {sign}{horizon_12m_med:.1f}%")
    if analog_name:
        parts.append(f"~ {analog_name}")
    return " · ".join(parts)


# ────────────────────────────────────────────────────────────
# 4) 메인 진입점

def compute_estate_horizon(
    lead_signals: Optional[Dict[str, Any]] = None,
    cycle_analog: Optional[Dict[str, Any]] = None,
    as_of: Optional[str] = None,
) -> Dict[str, Any]:
    """ESTATE Brain 의 lead_time + cycle_analog 출력을 받아 horizon verdict 산출.

    Args:
      lead_signals: estate_brain.compute_lead_time_signals(...)["signals"]
      cycle_analog: estate_brain.classify_cycle_analog(...) (nearest_historical 포함)
      as_of: ISO 시점 — 보통 estate_brain 와 동일 시점 박음

    Returns:
      verdict / cycle_stage / horizons / dominant_signal / nearest_analog / model_meta
    """
    lead_signals = lead_signals or {}
    cycle_analog = cycle_analog or {}

    stage = classify_estate_stage(lead_signals)
    horizons = horizon_returns(stage)
    horizon_12m_med = horizons.get("12m", {}).get("median_pct")
    dominant = _dominant_signal_label(lead_signals)

    # cycle_analog 의 nearest 1위만 한 줄에 노출 (verdict 보강)
    analog_name = None
    nearest_list = cycle_analog.get("nearest_historical") or []
    if nearest_list:
        analog_name = nearest_list[0].get("name")

    verdict = build_verdict(stage, horizon_12m_med, dominant, analog_name)

    return {
        "version": "v0",
        "as_of": as_of,
        "verdict": verdict,
        "cycle_stage": stage,
        "cycle_stage_label_ko": STAGE_LABEL_KO.get(stage, stage),
        "horizons": horizons,
        "dominant_signal": dominant,
        "nearest_analog": analog_name,
        "model_meta": {
            "stage_classification": {
                "source": "자체 결정 (Perplexity 2026-05-08 Lead Time + KB 분포 근사)",
                "version": "v0_hardcoded",
                "note": "임계 calibration 큐잉 — feedback_source_attribution_discipline",
            },
            "horizon_returns": {
                "source": "한국 KB 매매가격지수 1986-2024 분기 lookup (V0 approximation)",
                "version": "v0_hardcoded",
                "note": "V1 에서 actual KB historical series 동적 계산",
            },
            "lead_time_source": "Perplexity 2026-05-08 (TVP-VAR / Granger / 패널)",
            "analog_source": "KB부동산·한국부동산원 1997/2008/2022 (estate_brain)",
        },
    }
