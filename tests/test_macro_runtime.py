"""Offline cooperative deadline and diagnostic boundaries; no provider calls."""
from threading import Event

import pytest

from api.builders import macro_collect_builder as builder
from api.utils import macro_runtime as runtime


def test_deadline_caps_http_timeout_and_resets_after_scope(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(runtime.time, "monotonic", lambda: clock[0])
    assert runtime.request_timeout(20) == 20
    with runtime.collection_budget(5):
        assert runtime.request_timeout(20) == 5
        clock[0] = 103.0
        assert runtime.request_timeout(20) == 2
        with runtime.collection_budget(100):
            assert runtime.request_timeout(20) == 2
        clock[0] = 105.0
        with pytest.raises(runtime.CollectionDeadline):
            runtime.request_timeout(20)
    assert runtime.request_timeout(20) == 20


def test_expired_stage_starts_no_new_request(monkeypatch, capsys):
    called = []
    with runtime.collection_budget(0):
        with pytest.raises(runtime.CollectionDeadline):
            runtime.timed_source("fred:test", lambda: called.append("request"))
    assert called == []
    log = capsys.readouterr().err
    assert "phase=start" in log and "outcome=deadline" in log
    assert "elapsed_ms=" in log


def test_outer_call_propagates_budget_into_worker_and_redacts_exception(capsys):
    value, error = builder._safe_call(lambda: runtime.request_timeout(20), "fixture", 10)
    assert error is None
    assert 0 < value <= 8
    assert runtime.request_timeout(20) == 20

    def fail():
        raise RuntimeError("https://example.invalid?api_key=DO_NOT_LOG")

    value, error = builder._safe_call(fail, "fixture", 10)
    assert value is None
    assert error == "exception:RuntimeError"
    assert "DO_NOT_LOG" not in capsys.readouterr().err


def test_timeout_discards_late_result_but_does_not_claim_force_cancellation():
    started, release, finished = Event(), Event(), Event()

    def slow():
        started.set()
        try:
            release.wait(timeout=2)
            return {"late": True}
        finally:
            finished.set()

    try:
        value, error = builder._safe_call(slow, "fixture", 0.02)
        assert started.is_set()
        assert value is None and error == "timeout_0.02s"
        assert not finished.is_set()  # Running work is not misreported as killed.
    finally:
        release.set()
        assert finished.wait(timeout=2)


def test_cross_asset_each_asset_honors_remaining_budget(monkeypatch):
    from types import SimpleNamespace
    from api.quant import cross_asset_corr as corr
    from api.collectors import yfinance_safe
    clock = [0.0]
    created, requested = [], []
    monkeypatch.setattr(runtime.time, "monotonic", lambda: clock[0])

    def history(**kwargs):
        requested.append(kwargs["timeout"])
        clock[0] = 2.0
        return SimpleNamespace(empty=True)

    def ticker(name):
        created.append(name)
        return SimpleNamespace(history=history)

    monkeypatch.setattr(yfinance_safe, "yf_ticker", ticker)
    with runtime.collection_budget(1):
        assert corr.compute_cross_asset_corr()["available"] is False
    assert len(created) == 1
    assert requested == [1]
