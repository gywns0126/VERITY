"""Offline cooperative deadline and diagnostic boundaries; no provider calls."""
from pathlib import Path
import subprocess
import sys
import time
import os

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


def test_timeout_stops_late_side_effects_and_does_not_return_late_result(tmp_path):
    late = tmp_path / "late-result"
    def slow():
        time.sleep(0.3)
        late.write_text("must not reach this")
        return {"late": True}
    started = time.monotonic()
    value, error = builder._safe_call(slow, "fixture", 0.1)
    assert value is None and error == "timeout_0.1s"
    assert time.monotonic() - started < 1
    time.sleep(0.4)
    assert not late.exists()


@pytest.mark.parametrize("timeout", [True, False])
def test_process_group_cleanup_precedes_child_reaping(monkeypatch, timeout):
    calls = []
    killpg, waitpid = os.killpg, os.waitpid
    def cleanup(pid, sig):
        calls.append(("group", pid))
        return killpg(pid, sig)
    def reap(pid, options):
        calls.append(("reap", pid))
        return waitpid(pid, options)
    monkeypatch.setattr(os, "killpg", cleanup)
    monkeypatch.setattr(os, "waitpid", reap)
    result, error = builder._safe_call(
        (lambda: time.sleep(1)) if timeout else (lambda: {"ok": True}), "fixture", 0.1
    )
    assert calls[0][0] == "group" and calls[1] == ("reap", calls[0][1])
    assert len(calls) == 2
    assert error == "timeout_0.1s" if timeout else result == {"ok": True}


@pytest.mark.parametrize("timeout", [True, False])
def test_collector_threads_cannot_delay_interpreter_exit(timeout):
    script = """
from concurrent.futures import ThreadPoolExecutor
import time
from api.builders.macro_collect_builder import _safe_call
def collect():
    pool = ThreadPoolExecutor(max_workers=1)
    pool.submit(time.sleep, 30)
    if TIMEOUT:
        time.sleep(30)
    return {"ok": True}
result, error = _safe_call(collect, "fixture", 0.2)
assert (error == "timeout_0.2s") if TIMEOUT else (result == {"ok": True} and error is None)
""".replace("TIMEOUT", str(timeout))
    started = time.monotonic()
    completed = subprocess.run([sys.executable, "-c", script], cwd=Path(__file__).resolve().parents[1],
                               capture_output=True, text=True, timeout=4)
    assert completed.returncode == 0, completed.stderr
    assert time.monotonic() - started < 3


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
