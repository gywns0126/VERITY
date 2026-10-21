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


def test_build_initializes_provider_modules_only_inside_children():
    script = """
import builtins, os, sys, types
import api.collectors
from api.builders import macro_collect_builder as builder
parent = os.getpid()
providers = {
    'api.collectors.macro_data': ('get_macro_indicators', lambda: {'worker': os.getpid()}),
    'api.collectors.yieldcurve': ('get_full_yield_curve_data', lambda **kw: {'worker': os.getpid()}),
    'api.collectors.global_events': ('collect_global_events', lambda: [{'worker': os.getpid()}]),
}
for name, (function, callback) in providers.items():
    module = types.ModuleType(name)
    setattr(module, function, callback)
    sys.modules[name] = module
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name in providers:
        assert os.getpid() != parent, 'provider initialized in supervisor'
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
builder._load_existing = lambda: {}
result = builder.build()
assert result['macro']['worker'] != parent
assert result['bonds']['worker'] != parent
assert result['global_events'][0]['worker'] != parent
assert result['diagnostics']['errors'] == []
"""
    completed = subprocess.run([sys.executable, "-c", script], cwd=Path(__file__).resolve().parents[1],
                               capture_output=True, text=True, timeout=5)
    assert completed.returncode == 0, completed.stderr


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


def test_bounded_sources_propagates_deadline_and_returns_completed_without_waiting():
    from threading import Event
    release = Event()
    started = time.monotonic()
    def slow():
        release.wait(2)
        return "late"
    try:
        with runtime.collection_budget(1):
            result = runtime.bounded_sources(
                {"slow": slow, "fast": lambda: runtime.request_timeout(5)},
                timeout=0.05, max_workers=2,
            )
        assert set(result) == {"fast"}
        assert 0 < result["fast"] <= 0.05
        assert time.monotonic() - started < 0.5
    finally:
        release.set()


def _mock_core_macro(monkeypatch):
    from api.collectors import macro_data as macro
    from api.quant import cross_asset_corr
    quote = lambda *a, **k: {"value": 4.0, "change_pct": 0, "source": "fixture",
                             "source_as_of": "2026-10-16", "fetched_at": "core-receipt",
                             "last_successful_at": "core-receipt", "stale": False}
    for name in ("_get_usd_krw", "_get_fx", "_get_commodity", "_get_index_change_fred", "_get_index_change"):
        monkeypatch.setattr(macro, name, quote)
    monkeypatch.setattr(macro, "_get_commodity_bundle", lambda: {})
    monkeypatch.setattr(macro, "get_fred_macro_block", lambda: {"available": True})
    monkeypatch.setattr(macro, "get_ecos_macro_block", lambda: {"available": True})
    monkeypatch.setattr(macro, "merge_ecos_into_fred", lambda *args: None)
    monkeypatch.setattr(cross_asset_corr, "compute_cross_asset_corr", lambda: {"available": False})
    return macro


def test_hanging_optional_macro_stage_returns_core_before_process_deadline(monkeypatch):
    macro = _mock_core_macro(monkeypatch)
    monkeypatch.setattr(macro, "_get_micro_signals", lambda: time.sleep(30))
    started = time.monotonic()
    # _safe_call provides a 1.2s cooperative budget; optional work reserves its
    # final second for returning core data, leaving ~0.2s for the hanging stage.
    result, error = builder._safe_call(macro.get_macro_indicators, "fixture", 3.2)
    assert error is None and time.monotonic() - started < 2
    assert result["usd_krw"]["value"] == 4.0
    assert result["usd_krw"]["fetched_at"] == "core-receipt"
    assert result["fred"]["available"]
    assert result["micro_signals"] == []
    assert result["micro_signals_meta"]["stale"]
    assert builder._has_stale_macro_row(result), "failed optional source must stay visible"


def test_optional_error_preserves_core_and_records_failure_without_secret(monkeypatch, capsys):
    macro = _mock_core_macro(monkeypatch)
    def fail():
        raise RuntimeError("https://fixture.invalid?key=DO_NOT_LOG")
    monkeypatch.setattr(macro, "_get_micro_signals", fail)
    result = macro.get_macro_indicators()
    assert result["usd_krw"]["fetched_at"] == "core-receipt"
    assert result["micro_signals_meta"]["status"] == "deadline_or_error"
    assert "DO_NOT_LOG" not in capsys.readouterr().err
    previous = {"macro": {"usd_krw": {"value": 1, "source": "fixture", "fetched_at": "old"}},
                "collector_meta": {"macro": {"last_successful_at": "old"}}}
    monkeypatch.setattr(builder, "_load_existing", lambda: previous)
    collected = {"macro": result, "bonds": {"available": True}, "global_events": []}
    monkeypatch.setattr(builder, "_safe_call", lambda fn, name, timeout_s: (collected[name], None))
    snapshot = builder.build()
    assert snapshot["macro"]["usd_krw"]["fetched_at"] == "core-receipt"
    assert snapshot["macro"]["usd_krw"]["value"] == 4.0
    assert snapshot["collector_meta"]["macro"]["stale"]
    assert not snapshot["collector_meta"]["macro"]["reused"]
    assert snapshot["collector_meta"]["macro"]["last_successful_at"] == "old"


def test_optional_work_does_not_start_without_core_return_margin(monkeypatch):
    macro = _mock_core_macro(monkeypatch)
    monkeypatch.setattr(macro, "_get_micro_signals", lambda: pytest.fail("no optional budget"))
    with runtime.collection_budget(0.5):
        result = macro.get_macro_indicators()
    assert result["usd_krw"]["fetched_at"] == "core-receipt"
    assert result["micro_signals_meta"]["stale"]


def test_hanging_us_sockets_return_partial_before_outer_process_deadline(monkeypatch):
    from api.collectors import bondus
    monkeypatch.setattr(bondus, "FRED_API_KEY", "fixture-key")
    monkeypatch.setattr(bondus, "_fetch_latest_point", lambda *a, **k: time.sleep(30))
    started = time.monotonic()
    result, error = builder._safe_call(bondus.get_us_bond_summary, "fixture", 2.2)
    assert error is None and time.monotonic() - started < 1.5
    assert result["available"] is False and result["stale"] and result["partial"]
    assert len(result["missing_tenors"]) == 11 and len(result["missing_credit"]) == 3
