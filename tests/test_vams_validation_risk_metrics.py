"""VAMS validation risk_metrics wire — 2026-05-29.

risk_metrics.py wrapper (5/17 박힘, dead code) → VAMS validation 박음.
informational only — pass=None, overall verdict 영향 0.
Phase 2 Stress (9월) / Attribution (12-1월) sprint 박을 때 pass wire.

[[feedback_metavalidation_decompose]] — 자체 Sharpe (log) vs empyrical Sharpe (simple) cross.
[[project_data_audit_2026_05_27]] — dead code 4건 중 1건 회수.
"""
from __future__ import annotations

from api.vams.validation import (
    _daily_log_returns,
    _daily_simple_returns,
    compute_validation_report,
)


def test_simple_returns_basic():
    """simple returns = (b - a) / a."""
    series = [100.0, 110.0, 99.0]
    out = _daily_simple_returns(series)
    assert len(out) == 2
    assert abs(out[0] - 0.10) < 1e-9
    assert abs(out[1] - (-0.10)) < 1e-9


def test_simple_returns_skip_invalid():
    """0 / 음수 박은 부분 skip."""
    series = [100.0, 0.0, 110.0, -1.0, 120.0]
    out = _daily_simple_returns(series)
    # (0,0)→skip, (0,110)→skip (a=0), (110,-1)→skip, (-1,120)→skip
    assert out == []


def test_log_vs_simple_returns_diff():
    """log returns ≠ simple returns 박음 — cross-validation 의미 확보."""
    series = [100.0, 110.0]
    log = _daily_log_returns(series)
    simple = _daily_simple_returns(series)
    assert log[0] != simple[0]


def test_validation_report_new_keys_insufficient_data():
    """snapshots 없을 때도 신 4 키 박혀 있어야 (overall=INSUFFICIENT_DATA)."""
    # 빈 snapshots_dir 박음 (실재 X 디렉토리)
    report = compute_validation_report(
        portfolio={},
        history=[],
        snapshots_dir="/tmp/__verity_nonexistent_snapshots__",
    )
    assert report["overall"] == "INSUFFICIENT_DATA"
    metrics = report["metrics"]
    # 신 4 키 박혀 있어야
    for k in ("sortino", "calmar", "alpha_beta", "capture_ratios"):
        assert k in metrics, f"신 키 박혀 있지 X: {k}"
        assert metrics[k]["pass"] is None, f"{k} pass=None 박혀 있어야 (informational)"
        assert "note" in metrics[k], f"{k} note 박혀 있어야"


def test_validation_report_sharpe_cross_field():
    """sharpe 박은 dict 에 empyrical_cross_simple 박혀 있어야."""
    report = compute_validation_report(
        portfolio={},
        history=[],
        snapshots_dir="/tmp/__verity_nonexistent_snapshots__",
    )
    assert "empyrical_cross_simple" in report["metrics"]["sharpe"]


def test_overall_verdict_unaffected_by_informational_metrics():
    """신 4 informational 키 박혀도 overall 영향 0 박혀야."""
    report = compute_validation_report(
        portfolio={},
        history=[],
        snapshots_dir="/tmp/__verity_nonexistent_snapshots__",
    )
    # pass=None 박힌 박은 computed 박은 부분에서 자동 제외
    metrics = report["metrics"]
    info_keys = ["sortino", "calmar", "alpha_beta", "capture_ratios"]
    for k in info_keys:
        assert metrics[k]["pass"] is None
    # overall 박은 부분 = INSUFFICIENT_DATA (snapshots 없음) — 신 키 영향 0
    assert report["overall"] == "INSUFFICIENT_DATA"
