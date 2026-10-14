"""Profiling is observable without altering collection/pipeline contracts."""
import pytest

from api.analyzers import stock_filter
from api.collectors import stock_data


def test_profile_preserves_return_identity_and_records_stage_counts():
    metrics = {}
    records = [{"ticker": "A", "price": 100}]
    result = stock_filter._profile_call(metrics, "test_filter", lambda rows: rows, records)
    assert result is records
    row = metrics["pipeline_profile"]["stages"][0]
    assert row["status"] == "ok"
    assert row["input_n"] == row["output_n"] == 1
    assert row["elapsed_s"] >= 0
    assert records == [{"ticker": "A", "price": 100}]


def test_profile_preserves_exceptions_and_records_failure():
    metrics = {}

    def fail():
        raise ValueError("fixture")

    with pytest.raises(ValueError, match="fixture"):
        stock_filter._profile_call(metrics, "test_stage", fail)
    assert metrics["pipeline_profile"]["stages"][0]["error_type"] == "ValueError"


def test_dispatch_optional_metrics_keeps_candidate_list(monkeypatch):
    candidates = [{"ticker": "A"}]
    monkeypatch.setattr(stock_filter, "UNIVERSE_RAMP_UP_STAGE", 0)
    monkeypatch.setattr(stock_filter, "run_filter_pipeline", lambda **kwargs: candidates)
    monkeypatch.setattr(stock_filter, "_log_w1_runtime", lambda **kwargs: None)
    metrics = {}
    assert stock_filter.run_filter_pipeline_with_ramp_up(_metrics=metrics) is candidates
    profile = metrics["pipeline_profile"]
    assert profile["elapsed_s"] >= 0
    assert profile["quarterly_snapshot_cache"]["file_reads"] == 0


def test_yahoo_measurement_keeps_existing_wrapper_parameters(monkeypatch):
    from api.collectors import yfinance_safe
    called = []
    payload = {"price": 100}

    def wrapper(fn, **kwargs):
        called.append(kwargs)
        return fn()

    monkeypatch.setattr(yfinance_safe, "safe_yf_call", wrapper)
    metrics = {}
    assert stock_data._measured_stock_call(lambda: payload, label="A.history", metrics=metrics, kind="history") is payload
    assert called == [{"label": "A.history", "metrics": metrics}]
    assert metrics["yf_history_calls"] == 1
    assert metrics["yf_history_failed"] == 0
    assert metrics["yf_history_elapsed_s"] >= 0
    assert stock_data._measured_stock_call(lambda: None, label="A.info", metrics=metrics, kind="info") is None
    assert metrics["yf_info_failed"] == 1
