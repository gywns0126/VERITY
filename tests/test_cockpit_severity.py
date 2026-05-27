"""cockpit_severity — 3-tier 룰 unit test.

회귀 가드: RED/YELLOW/GREEN transition. 자기 산식 룰 박힘 ([[feedback_methodology_pre_registration]] 사전등록).
"""
from __future__ import annotations

import pytest

from api.observability.cockpit_severity import evaluate


def test_evaluate_all_green_when_inputs_clean():
    """모든 입력 정상 → GREEN."""
    inputs = {
        "kis_lock_commits_24h": 0,
        "operator_deadman": {"trigger": "ok"},
        "data_health": {"core_sources_ok": True},
        "fred_age_h": 1.0,
        "dispatch_chain_ratio": 1.0,
        "open_p0_aged_24h": [],
        "pre_registration_pending": [],
        "feature_drift_warning": False,
        "brain_anomaly_24h": 0,
    }
    severity, reasons = evaluate(inputs)
    assert severity == "GREEN"
    assert reasons == []


def test_red_when_kis_lock_3_or_more():
    """KIS lock commits 24h ≥ 3 → RED (RULE 1 위반 시그널)."""
    inputs = {"kis_lock_commits_24h": 3}
    severity, reasons = evaluate(inputs)
    assert severity == "RED"
    assert any("KIS" in r for r in reasons)


def test_red_when_operator_deadman_maintenance():
    """operator_deadman trigger=maintenance → RED."""
    inputs = {"operator_deadman": {"trigger": "maintenance"}}
    severity, reasons = evaluate(inputs)
    assert severity == "RED"
    assert any("maintenance" in r for r in reasons)


def test_red_when_core_sources_not_ok():
    """data_health.core_sources_ok=False → RED."""
    inputs = {"data_health": {"core_sources_ok": False}}
    severity, reasons = evaluate(inputs)
    assert severity == "RED"


def test_red_when_p0_aged_24h():
    """P0 postmortem 24h+ 미박힘 → RED."""
    inputs = {"open_p0_aged_24h": [{"id": "p0-foo"}]}
    severity, reasons = evaluate(inputs)
    assert severity == "RED"


def test_yellow_when_kis_lock_2():
    """KIS lock = 2 → YELLOW (임박)."""
    inputs = {"kis_lock_commits_24h": 2}
    severity, reasons = evaluate(inputs)
    assert severity == "YELLOW"


def test_yellow_when_fred_stale():
    """fred_age_h > 6h → YELLOW."""
    inputs = {"fred_age_h": 8.5}
    severity, reasons = evaluate(inputs)
    assert severity == "YELLOW"
    assert any("FRED" in r for r in reasons)


def test_yellow_when_dispatch_chain_low():
    """dispatch_chain_ratio < 80% → YELLOW."""
    inputs = {"dispatch_chain_ratio": 0.5}
    severity, reasons = evaluate(inputs)
    assert severity == "YELLOW"


def test_yellow_when_pre_registration_pending():
    """pre_registration_pending ≥ 1 → YELLOW (Phase 1 P1-c 보장 위반)."""
    inputs = {"pre_registration_pending": [{"commit": "abc123"}]}
    severity, reasons = evaluate(inputs)
    assert severity == "YELLOW"


def test_yellow_when_brain_anomaly_3():
    """brain anomaly 24h ≥ 3 → YELLOW."""
    inputs = {"brain_anomaly_24h": 4}
    severity, reasons = evaluate(inputs)
    assert severity == "YELLOW"


def test_red_overrides_yellow():
    """RED + YELLOW 동시 → RED 우선."""
    inputs = {
        "kis_lock_commits_24h": 3,  # RED
        "fred_age_h": 8.0,          # YELLOW
    }
    severity, reasons = evaluate(inputs)
    assert severity == "RED"
    # RED reasons 만 박혀야 함 (YELLOW evaluate 안 함)
    assert all("KIS" in r for r in reasons)


def test_dispatch_chain_zero_not_yellow():
    """dispatch_chain_ratio=0 = 측정 시작 전 또는 정확히 0 — YELLOW 미박힘 검증 (None 처리)."""
    inputs = {"dispatch_chain_ratio": None}
    severity, reasons = evaluate(inputs)
    assert severity == "GREEN"
    assert reasons == []
