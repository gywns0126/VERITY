"""Publishing an old cache must not undo the missing-price measurement repair."""
from copy import deepcopy

from scripts.upload_operator_data_to_supabase import guard_legacy_performance


def test_cached_portfolio_cannot_republish_synthetic_performance():
    source = {
        "recommendations": [{"ticker": "AAA", "price": 123}],
        "vams": {"holdings": [{"ticker": "BBB", "qty": 2}]},
        "trade_plan_meta": {"status": "unchanged"},
        "backtest_stats": {"periods": {"14d": {"avg_return_net": -50}},
                           "_corrections_meta": {"version": "1.0"}},
        "verification_report": {"performance": {"avg_return_14d": -50},
                                "_corrections_meta": {"version": "1.0", "delisted_return_pct": -50}},
        "brain_accuracy": {"grades": {"WATCH": {"avg_return": 0}}, "insight": "old"},
        "brain_quality": {"score": 70, "status": "ok", "period": "weekly"},
    }
    before = deepcopy(source)
    published = guard_legacy_performance(source, "_operator/portfolio_full.json")
    assert source == before  # Preserve the original for historical audit.
    for key in ("recommendations", "vams", "trade_plan_meta"):
        assert published[key] == before[key]
    assert published["backtest_stats"]["periods"] == {}
    assert published["verification_report"]["performance"]["avg_return_14d"] is None
    assert published["verification_report"]["_corrections_meta"]["delisted_return_pct"] is None
    assert published["brain_accuracy"]["grades"] == {}
    assert published["brain_quality"]["score"] is None
    assert published["brain_quality"]["status"] == "no_data"
    assert guard_legacy_performance(published, "_operator/portfolio_full.json") == published


def test_recomputed_metrics_and_other_payloads_are_preserved():
    meta = {"version": "2.0-missing-price-unresolved"}
    source = {
        "backtest_stats": {"periods": {"14d": {"avg_return": None}}, "_corrections_meta": meta},
        "verification_report": {"performance": {"avg_return_14d": None}, "_corrections_meta": meta},
        "brain_accuracy": {"grades": {}, "evaluation_status": "partial", "unresolved_count": 25},
        "brain_quality": {"score": None, "status": "no_data"},
    }
    assert guard_legacy_performance(source, "_operator/portfolio_full.json") == source
    assert guard_legacy_performance(source["verification_report"], "_operator/verification_report.json") == source["verification_report"]
    assert guard_legacy_performance(source, "_operator/history.json") == source


def test_standalone_legacy_report_is_invalidated():
    source = {"performance": {"hit_rate_14d": 50}, "factor_health": {"healthy": ["a"]},
              "feedback_loop_status": "closed", "_corrections_meta": {"version": "1.0"}}
    result = guard_legacy_performance(source, "_operator/verification_report.json")
    assert result["performance"]["hit_rate_14d"] is None
    assert result["factor_health"] == source["factor_health"]
    assert result["feedback_loop_status"] == "unverified"
