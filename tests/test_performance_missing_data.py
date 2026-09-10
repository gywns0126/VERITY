"""Regression coverage for missing prices, empty grades, and honest cohort denominators."""
from datetime import datetime

import pytest

from api.intelligence import backtest_archive as archive
from api.intelligence import periodic_report as periodic


def rec(ticker, price=100, grade="BUY", **extra):
    return {"ticker": ticker, "price": price, "recommendation": "WATCH",
            "verity_brain": {"grade": grade}, **extra}


def evaluate(monkeypatch, tmp_path, start, entry, end, now=None):
    snapshots = {
        "2026-09-01": {"recommendations": start},
        "2026-09-02": {"recommendations": entry},
        "2026-09-08": {"recommendations": end},
    }
    monkeypatch.setattr(archive, "BACKTEST_PATH", str(tmp_path / "backtest_stats.json"))
    monkeypatch.setattr(archive, "now_kst", lambda: now or datetime(2026, 9, 8))
    monkeypatch.setattr(archive, "list_available_dates", lambda: sorted(snapshots))
    monkeypatch.setattr(archive, "load_snapshot", snapshots.get)
    result = archive.evaluate_past_recommendations([7])
    assert result["_corrections_meta"]["delisted_return_pct"] is None
    return result["periods"]["7d"]


def test_missing_exit_is_unresolved_not_a_delisting(monkeypatch, tmp_path):
    start = [rec("A"), rec("B")]
    row = evaluate(monkeypatch, tmp_path, start, start, [rec("A", 110)])
    assert row["cohort_size"] == 2
    assert row["evaluated_count"] == row["unresolved_count"] == 1
    assert row["coverage_pct"] == 50
    assert row["delisted_count"] is None
    assert row["listing_status_checked"] is False
    assert row["unresolved"] == [{"ticker": "B", "name": "?", "reason": "missing_evaluation_price"}]
    assert row["evaluation_status"] == "partial"
    assert row["avg_return_net"] is row["hit_rate"] is row["sharpe"] is None
    assert row["observed"]["avg_return_net"] == 9.27
    assert row["observed"]["min_return"] != -50


def test_missing_entry_is_in_denominator(monkeypatch, tmp_path):
    row = evaluate(monkeypatch, tmp_path, [rec("A"), rec("B")], [rec("A")], [rec("A", 110), rec("B", 120)])
    assert row["skipped_no_t_plus_1"] == 1
    assert row["unresolved"][0]["reason"] == "missing_entry_price"
    assert row["cohort_size"] == row["evaluated_count"] + row["unresolved_count"]
    assert row["avg_return"] is None


def test_complete_cohort_keeps_existing_cost_math(monkeypatch, tmp_path):
    row = evaluate(monkeypatch, tmp_path, [rec("A")], [rec("A", 100)], [rec("A", 110)])
    assert row["evaluation_status"] == "complete"
    assert row["avg_return"] == 10
    assert row["avg_return_net"] == 9.27
    assert row["unresolved_count"] == 0


@pytest.mark.parametrize("bad", [None, 0, -1, float("nan"), float("inf"), "NaN", "bad", True])
def test_invalid_exit_prices_cannot_create_returns(monkeypatch, tmp_path, bad):
    row = evaluate(monkeypatch, tmp_path, [rec("A")], [rec("A")], [rec("A", bad)])
    assert row["evaluated_count"] == 0
    assert row["unresolved_count"] == 1
    assert row["observed"]["avg_return_net"] is None


def test_last_available_snapshot_sets_actual_evaluation_window(monkeypatch, tmp_path):
    row = evaluate(monkeypatch, tmp_path, [rec("A")], [rec("A")], [rec("A", 110)], datetime(2026, 9, 11))
    assert row["evaluation_date"] == "2026-09-08"
    assert row["snapshot_date"] == "2026-09-01"
    assert row["avg_return"] == 10


def test_no_recommendations_is_not_zero_performance(monkeypatch, tmp_path):
    row = evaluate(monkeypatch, tmp_path, [rec("A", grade="WATCH")], [rec("A")], [rec("A")])
    assert row["evaluation_status"] == "no_recommendations"
    assert row["cohort_size"] == 0
    assert row["avg_return"] is row["hit_rate"] is None


def test_us_holding_krw_price_cannot_fill_native_price():
    snap = {"recommendations": [], "vams": {"holdings": [
        {"ticker": "MSFT", "current_price": 700000, "currency": "USD"},
        {"ticker": "005930", "current_price": 100000},
    ]}}
    assert archive._get_price_map_from_snapshot(snap) == {"005930": 100000}


def test_no_strong_buy_sample_never_suggests_weight_change():
    snaps = [{"recommendations": [rec("A", grade="WATCH"), rec("B", grade="AVOID")]},
             {"recommendations": [rec("A", 90), rec("B", 80)]}]
    result = periodic._analyze_brain_accuracy(snaps)
    assert result["evaluation_status"] == "insufficient_groups"
    assert "STRONG_BUY" not in result["grades"]
    assert "평균 0%" not in result["insight"]
    assert "가중치 조정" not in result["insight"]
    assert "판정 불가" in result["insight"]


def test_missing_periodic_price_does_not_become_zero_return():
    snaps = [{"recommendations": [rec("A", grade="STRONG_BUY"), rec("B", grade="AVOID")]},
             {"recommendations": [rec("B", 90)]}]
    result = periodic._analyze_brain_accuracy(snaps)
    assert result["grades"] == {}
    assert "STRONG_BUY" not in result["observed_grades"]
    assert result["unresolved_count"] == result["evaluated_count"] == 1
    assert result["evaluation_status"] == "partial"
    performance = periodic._measure_recommendation_performance(snaps)
    assert performance["cohort_size"] == 1  # Brain grade has precedence over legacy WATCH.
    assert performance["evaluated_count"] == 0
    assert performance["unresolved_count"] == 1
    assert performance["avg_return_pct"] is performance["hit_rate_pct"] is None


def test_observed_flat_price_remains_measured_zero():
    snaps = [{"recommendations": [rec("A", grade="STRONG_BUY"), rec("B", grade="AVOID")]},
             {"recommendations": [rec("A"), rec("B", 90)]}]
    result = periodic._analyze_brain_accuracy(snaps)
    assert result["grades"]["STRONG_BUY"]["avg_return"] == 0
    assert result["grades"]["STRONG_BUY"]["count"] == 1
    assert result["evaluation_status"] == "observed"
    assert "가중치 조정 검토 필요" not in result["insight"]


@pytest.mark.parametrize("adjustment_status,expected", [("frozen_2026_05_23", "frozen"), ("error", "error"), ("ok", "closed")])
def test_verification_preserves_coverage_without_misleading_ci(monkeypatch, tmp_path, adjustment_status, expected):
    row = evaluate(monkeypatch, tmp_path, [rec("A"), rec("B")], [rec("A"), rec("B")], [rec("A", 110)])
    monkeypatch.setattr(archive, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(archive, "evaluate_past_recommendations", lambda: {"periods": {"14d": row}})
    import api.quant.alpha.factor_decay as decay
    monkeypatch.setattr(decay, "analyze_factor_decay", lambda: {})
    monkeypatch.setattr(decay, "compute_ic_weight_adjustments", lambda: {
        "status": adjustment_status, "adjustments": {"prediction": {"multiplier": 0.0}},
    })
    report = archive.generate_verification_report()
    assert report["performance"]["sample_14d"] == 1
    assert report["performance"]["hit_rate_14d"] is report["performance"]["hit_rate_14d_ci95"] is None
    assert report["evaluation_coverage"]["14d"]["unresolved_count"] == 1
    assert report["evaluation_coverage"]["14d"]["cohort_size"] == 2
    assert report["feedback_loop_status"] == expected
