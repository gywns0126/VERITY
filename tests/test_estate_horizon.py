"""
EstateHorizon V0 — 5단계 stage 분류 + horizon 분포 + verdict 검증.
"""
from __future__ import annotations

import pytest


def _signals(**verdicts):
    """Lead time signals dict 빠르게 만들기."""
    out = {}
    if "j_lead" in verdicts:
        out["jeonse_3m_lead"] = {"verdict": verdicts["j_lead"]}
    if "j_ratio" in verdicts:
        out["jeonse_ratio_24m"] = {"verdict": verdicts["j_ratio"]}
    if "unsold" in verdicts:
        out["unsold_units_lead"] = {"verdict": verdicts["unsold"]}
    if "construct" in verdicts:
        out["construction_starts_lead"] = {"verdict": verdicts["construct"]}
    if "rate" in verdicts:
        out["rate_lead"] = {"verdict": verdicts["rate"]}
    return out


def test_classify_stage_recovery():
    from api.intelligence.estate_horizon import classify_estate_stage
    sig = _signals(j_lead="moderate_up", unsold="absorption")
    assert classify_estate_stage(sig) == "recovery"


def test_classify_stage_expansion():
    from api.intelligence.estate_horizon import classify_estate_stage
    sig = _signals(j_lead="strong_up", unsold="absorption")
    assert classify_estate_stage(sig) == "expansion"


def test_classify_stage_peak():
    from api.intelligence.estate_horizon import classify_estate_stage
    sig = _signals(j_ratio="ambivalent_overheated")
    assert classify_estate_stage(sig) == "peak"


def test_classify_stage_contraction():
    from api.intelligence.estate_horizon import classify_estate_stage
    sig = _signals(unsold="negative_pressure", j_lead="down")
    assert classify_estate_stage(sig) == "contraction"


def test_classify_stage_depression():
    from api.intelligence.estate_horizon import classify_estate_stage
    sig = _signals(unsold="negative_pressure_strong", j_ratio="reverse_lease_risk")
    assert classify_estate_stage(sig) == "depression"


def test_classify_stage_unknown_empty():
    from api.intelligence.estate_horizon import classify_estate_stage
    assert classify_estate_stage({}) == "unknown"


def test_horizon_returns_all_stages_have_4_horizons():
    from api.intelligence.estate_horizon import horizon_returns
    for stage in ["recovery", "expansion", "peak", "contraction", "depression", "unknown"]:
        h = horizon_returns(stage)
        assert set(h.keys()) == {"3m", "6m", "12m", "24m"}
        for row in h.values():
            assert "median_pct" in row
            assert "p25_pct" in row
            assert "p75_pct" in row


def test_horizon_returns_peak_negative_12m():
    """peak 단계는 12M median 이 음수여야 함 (정점 후 하락)."""
    from api.intelligence.estate_horizon import horizon_returns
    h = horizon_returns("peak")
    assert h["12m"]["median_pct"] < 0


def test_horizon_returns_expansion_positive_12m():
    """expansion 단계는 12M median 이 양수."""
    from api.intelligence.estate_horizon import horizon_returns
    h = horizon_returns("expansion")
    assert h["12m"]["median_pct"] > 0


def test_compute_estate_horizon_full():
    """end-to-end — peak 신호 + analog 박힌 입력."""
    from api.intelligence.estate_horizon import compute_estate_horizon
    out = compute_estate_horizon(
        lead_signals=_signals(j_ratio="ambivalent_overheated", unsold="neutral"),
        cycle_analog={"nearest_historical": [{"name": "Rate-Shock Rebound"}]},
        as_of="2026-05-08T22:00:00+09:00",
    )
    assert out["cycle_stage"] == "peak"
    assert out["cycle_stage_label_ko"] == "정점기"
    assert "정점기" in out["verdict"]
    assert "Rate-Shock Rebound" in out["verdict"]
    assert out["horizons"]["12m"]["median_pct"] < 0  # peak 후 하락 prior
    assert out["model_meta"]["stage_classification"]["version"] == "v0_hardcoded"


def test_compute_estate_horizon_empty_inputs():
    from api.intelligence.estate_horizon import compute_estate_horizon
    out = compute_estate_horizon(lead_signals={}, cycle_analog={})
    assert out["cycle_stage"] == "unknown"
    assert out["verdict"]  # 빈 문자열 X
    assert out["horizons"]["12m"]["median_pct"] is not None


def test_dominant_signal_priority():
    """우선순위: 미분양 강압박 > 전세 추세 > 금리. 미분양 강압박이 다른 신호 가려야 함."""
    from api.intelligence.estate_horizon import _dominant_signal_label
    sig = _signals(unsold="negative_pressure_strong", j_lead="strong_up", rate="supportive")
    assert _dominant_signal_label(sig) == "미분양 강압박"


def test_compute_uses_estate_brain_pipeline():
    """estate_brain.compute_lead_time_signals + classify_cycle_analog 산출이 그대로 들어가는지."""
    from api.intelligence.estate_brain import (
        compute_lead_time_signals,
        classify_cycle_analog,
    )
    from api.intelligence.estate_horizon import compute_estate_horizon

    lead = compute_lead_time_signals(
        jeonse_3m_change_pct=2.8,           # strong_up
        jeonse_ratio_pct=68,                 # supportive
        construction_starts_yoy_pct=-15,     # supply_tight_in_2y
        unsold_units_yoy_pct=-15,            # absorption
        rate_change_pp=-0.6,                 # supportive
    )
    analog = classify_cycle_analog(
        target={"drop_pct": -10, "duration_months": 24, "shape": "U"},
    )
    out = compute_estate_horizon(
        lead_signals=lead["signals"],
        cycle_analog=analog,
    )
    # strong_up + absorption + supply_tight → expansion
    assert out["cycle_stage"] == "expansion"
    assert out["horizons"]["12m"]["median_pct"] > 0
