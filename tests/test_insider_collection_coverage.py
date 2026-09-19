"""Network-free integration contracts for the public insider collection ledger.

These exercise ``main()`` with a fake DART module and a fake requests.Session.
They deliberately do not import the real config module: a test must never read a
credential merely to validate collection-state transitions.
"""
from __future__ import annotations

import importlib
import json
import sys
from datetime import datetime, timezone, timedelta
from types import ModuleType, SimpleNamespace

import pytest


KST = timezone(timedelta(hours=9))
NOW = datetime(2026, 9, 20, 9, 30, tzinfo=KST)


class _Response:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def json(self):
        return self.payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _Session:
    def __init__(self, scripted):
        self.scripted = list(scripted)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if not self.scripted:
            raise AssertionError("unexpected network call")
        item = self.scripted.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _stock(ticker="000001", net=7):
    return {
        "ticker": ticker,
        "name": f"old-{ticker}",
        "net_change": net,
        "buy_n": 1,
        "sell_n": 0,
        "total": 1,
        "trades": [{"date": "2026-09-01", "change": net}],
        "collected_at": "2026-09-01",
    }


def _row(change=10, date="2026-09-19"):
    return {
        "rcept_dt": date,
        "rcept_no": "202609190001",
        "repror": "tester",
        "isu_exctv_ofcps": "director",
        "isu_exctv_rgist_at": "registered",
        "sp_stock_lmp_irds_cnt": str(change),
        "sp_stock_lmp_cnt": "1000",
        "sp_stock_lmp_rate": "0.1",
        "sp_stock_lmp_irds_rate": "0.1",
    }


@pytest.fixture
def run_main(monkeypatch, tmp_path):
    """Return a runner with all boundary dependencies replaced before main()."""
    fake_config = ModuleType("api.config")
    fake_config.DART_API_KEY = "test-key"
    fake_corp = ModuleType("api.collectors.dart_corp_code")
    monkeypatch.setitem(sys.modules, "api.config", fake_config)
    monkeypatch.setitem(sys.modules, "api.collectors.dart_corp_code", fake_corp)

    # The builder itself has no config import at module load today.  Keeping this
    # import after fake modules are installed also protects a future import shape.
    builder = importlib.import_module("api.builders.insider_trades_public_builder")
    output = tmp_path / "insider_trades.json"

    def run(*, universe, scripted=(), previous=None, raw_existing=None, corp_codes=None,
            corp_code_fn=None, monotonic=None, key="test-key", max_calls=20, max_seconds=999):
        if raw_existing is not None:
            output.write_bytes(raw_existing)
        elif previous is not None:
            output.write_text(json.dumps(previous, ensure_ascii=False), encoding="utf-8")
        elif output.exists():
            output.unlink()
        session = _Session(scripted)
        fake_config.DART_API_KEY = key
        fake_corp.get_corp_code = corp_code_fn or (lambda ticker: (corp_codes or {}).get(ticker, f"C{ticker}"))
        fake_requests = SimpleNamespace(Session=lambda: session)
        monkeypatch.setitem(sys.modules, "requests", fake_requests)
        monkeypatch.setattr(builder, "OUTPUT_PATH", str(output))
        monkeypatch.setattr(builder, "_ordered_universe", lambda: list(universe))
        monkeypatch.setattr(builder, "_now_kst", lambda: NOW)
        monkeypatch.setattr(builder, "MAX_CALLS", max_calls)
        monkeypatch.setattr(builder, "MAX_SECONDS", max_seconds)
        sleeps = []
        session.sleeps = sleeps
        monkeypatch.setattr(builder.time, "sleep", lambda seconds: sleeps.append(seconds))
        if monotonic is not None:
            monkeypatch.setattr(builder.time, "monotonic", monotonic)
        # Also cover producers that later move imports to module scope.
        if hasattr(builder, "requests"):
            monkeypatch.setattr(builder, "requests", fake_requests)
        if hasattr(builder, "DART_API_KEY"):
            monkeypatch.setattr(builder, "DART_API_KEY", key)
        if hasattr(builder, "get_corp_code"):
            monkeypatch.setattr(builder, "get_corp_code", fake_corp.get_corp_code)
        code = builder.main()
        try:
            doc = json.loads(output.read_text(encoding="utf-8")) if output.exists() else None
        except json.JSONDecodeError:
            doc = None
        return code, doc, session, output, builder

    return run


def _coverage(doc):
    assert doc["coverage"]["schema_version"] == 1
    return doc["coverage"]


def test_new_universe_initializes_coverage_without_zero_filling_stocks(run_main):
    code, doc, session, _, _ = run_main(
        universe=[{"ticker": "000001", "name": "one"}, {"ticker": "000002", "name": "two"}],
        scripted=[_Response({"status": "000", "list": [_row(12)]})], max_calls=1,
    )

    assert code == 0 and len(session.calls) == 1
    coverage = _coverage(doc)
    assert coverage["universe_count"] == 2 and coverage["attempted_this_run"] == 1
    entry = coverage["by_ticker"]["000001"]
    assert entry["state"] == "ok" and entry["in_universe"] is True
    assert entry["attempted_this_run"] is True and entry["dart_status"] == "000"
    assert entry["last_success_state"] == "ok" and entry["last_success_at"] == NOW.isoformat()
    assert entry["last_success_row_count"] == 1 and entry["last_attempt_at"] == NOW.isoformat()
    assert coverage["by_ticker"]["000002"]["state"] == "not_collected"
    assert coverage["by_ticker"]["000002"]["skip_reason"] == "budget_exhausted"
    assert coverage["by_ticker"]["000002"]["attempted_this_run"] is False
    assert [s["ticker"] for s in doc["stocks"]] == ["000001"]
    assert coverage["counts"]["ok"] == 1 and coverage["counts"]["not_collected"] == 1


@pytest.mark.parametrize("payload", [
    {"status": "013"},
    {"status": "000", "list": []},
])
def test_authoritative_empty_removes_old_stock_but_retains_coverage(run_main, payload):
    previous = {"stocks": [_stock()], "coverage": {"schema_version": 1, "by_ticker": {}, "counts": {}}}
    code, doc, _, _, _ = run_main(
        universe=[{"ticker": "000001", "name": "one"}], scripted=[_Response(payload)], previous=previous,
    )

    entry = _coverage(doc)["by_ticker"]["000001"]
    assert code == 0 and doc["stocks"] == []
    assert entry["state"] == "empty" and entry["dart_status"] == payload["status"]
    assert entry["last_success_state"] == "empty" and entry["last_success_row_count"] == 0
    assert entry["attempted_this_run"] is True and entry["last_attempt_at"] == NOW.isoformat()


@pytest.mark.parametrize("payload", [
    {"status": "000"},
    {"status": "000", "list": None},
    {"status": "000", "list": {}},
    {"status": "000", "list": ["not-a-row"]},
])
def test_malformed_success_payload_fails_and_preserves_prior_stock(run_main, payload):
    previous = {"stocks": [_stock(net=88)]}
    code, doc, _, _, _ = run_main(
        universe=[{"ticker": "000001", "name": "one"}], scripted=[_Response(payload)], previous=previous,
    )

    entry = _coverage(doc)["by_ticker"]["000001"]
    assert code == 0 and doc["stocks"][0]["net_change"] == 88
    assert entry["state"] == "failed" and entry["failure_reason"]
    assert entry["attempted_this_run"] is True


def test_http_failure_with_013_body_is_not_an_authoritative_empty(run_main):
    previous = {"stocks": [_stock(net=88)]}
    code, doc, _, _, _ = run_main(
        universe=[{"ticker": "000001", "name": "one"}],
        scripted=[_Response({"status": "013"}, status_code=503)], previous=previous,
    )

    entry = _coverage(doc)["by_ticker"]["000001"]
    assert code == 0 and doc["stocks"][0]["net_change"] == 88
    assert entry["state"] == "failed" and "dart_status" not in entry


def test_request_exception_counts_as_attempt_and_keeps_last_success(run_main):
    prior = {"stocks": [_stock()], "coverage": {"schema_version": 1, "by_ticker": {
        "000001": {"state": "ok", "last_success_at": "2026-09-01", "last_success_state": "ok", "last_success_row_count": 1},
    }, "counts": {"ok": 1}}}
    code, doc, session, _, _ = run_main(
        universe=[{"ticker": "000001", "name": "one"}], scripted=[TimeoutError("down")], previous=prior,
    )

    entry = _coverage(doc)["by_ticker"]["000001"]
    assert code == 0 and len(session.calls) == 1 and doc["stocks"][0]["ticker"] == "000001"
    assert entry["state"] == "failed" and entry["attempted_this_run"] is True
    assert entry["last_success_at"] == "2026-09-01" and entry["last_success_row_count"] == 1


def test_021_is_one_non_authoritative_failure_then_next_ticker_continues(run_main):
    code, doc, session, _, _ = run_main(
        universe=[{"ticker": "000001", "name": "one"}, {"ticker": "000002", "name": "two"}],
        scripted=[_Response({"status": "021"}), _Response({"status": "000", "list": [_row()]})],
    )

    coverage = _coverage(doc)["by_ticker"]
    assert code == 0 and len(session.calls) == 2 and 60 not in session.sleeps
    assert coverage["000001"]["state"] == "failed"
    assert coverage["000001"]["failure_reason"] == "dart_status"
    assert coverage["000001"]["dart_status"] == "021"
    assert coverage["000002"]["state"] == "ok"


def test_mapping_time_is_included_in_pre_request_budget(run_main):
    clock = {"value": 0.0}

    def get_corp_code(_ticker):
        clock["value"] = 11.0
        return "C000001"

    code, doc, session, _, _ = run_main(
        universe=[{"ticker": "000001", "name": "one"}], corp_code_fn=get_corp_code,
        monotonic=lambda: clock["value"], max_seconds=10,
    )

    entry = _coverage(doc)["by_ticker"]["000001"]
    assert code == 0 and not session.calls
    assert entry["state"] == "not_collected" and entry["attempted_this_run"] is False
    assert entry["skip_reason"] == "budget_exhausted"


def test_020_marks_current_failed_and_marks_remaining_rate_limited(run_main):
    previous = {"stocks": [_stock("000001"), _stock("000002")]}
    code, doc, session, _, _ = run_main(
        universe=[{"ticker": "000001", "name": "one"}, {"ticker": "000002", "name": "two"}],
        scripted=[_Response({"status": "020"})], previous=previous,
    )

    coverage = _coverage(doc)
    assert code == 0 and len(session.calls) == 1
    assert coverage["by_ticker"]["000001"]["state"] == "failed"
    # An unqueried legacy stock must not be relabelled as an observed empty/new row.
    assert coverage["by_ticker"]["000002"]["state"] == "legacy_unverified"
    assert coverage["by_ticker"]["000002"]["skip_reason"] == "rate_limit"
    assert {s["ticker"] for s in doc["stocks"]} == {"000001", "000002"}


def test_missing_corp_code_is_a_non_attempt_skip(run_main):
    code, doc, session, _, _ = run_main(
        universe=[{"ticker": "000001", "name": "one"}], corp_codes={"000001": None},
    )

    entry = _coverage(doc)["by_ticker"]["000001"]
    assert code == 0 and not session.calls
    assert entry["state"] == "not_collected" and entry["skip_reason"] == "corp_code_unavailable"
    assert entry["attempted_this_run"] is False


def test_skip_preserves_known_state_and_last_success_fields(run_main):
    prior_entry = {
        "state": "failed", "failure_reason": "old failure", "last_success_at": "2026-09-01",
        "last_success_state": "ok", "last_success_row_count": 3,
    }
    previous = {"stocks": [_stock()], "coverage": {"schema_version": 1, "by_ticker": {"000001": prior_entry}, "counts": {"failed": 1}}}
    code, doc, session, _, _ = run_main(
        universe=[{"ticker": "000001", "name": "one"}], previous=previous, corp_codes={"000001": None},
    )

    entry = _coverage(doc)["by_ticker"]["000001"]
    assert code == 0 and not session.calls
    assert entry["state"] == "failed" and entry["attempted_this_run"] is False
    assert entry["last_success_at"] == "2026-09-01" and entry["last_success_row_count"] == 3


def test_legacy_stock_is_unverified_until_a_real_response(run_main):
    code, doc, _, _, _ = run_main(
        universe=[{"ticker": "000001", "name": "one"}, {"ticker": "000002", "name": "two"}],
        previous={"stocks": [_stock("000001")]}, corp_codes={"000001": None, "000002": None},
    )

    coverage = _coverage(doc)["by_ticker"]
    assert code == 0
    assert coverage["000001"]["state"] == "legacy_unverified"
    assert coverage["000002"]["state"] == "not_collected"
    assert coverage["000001"]["attempted_this_run"] is False


def test_corrupt_existing_json_returns_one_preserves_bytes_and_makes_no_calls(run_main):
    original = b"{not valid json"
    code, doc, session, output, _ = run_main(
        universe=[{"ticker": "000001", "name": "one"}],
        scripted=[_Response({"status": "000", "list": []})], raw_existing=original,
    )
    assert code == 1 and output.read_bytes() == original and not session.calls
    assert doc is None


def test_atomic_replace_failure_preserves_existing_bytes(run_main, monkeypatch):
    previous = {"stocks": [_stock()]}
    encoded = json.dumps(previous, ensure_ascii=False).encode()
    # Install the failure before main so there is no write of the old snapshot.
    builder = importlib.import_module("api.builders.insider_trades_public_builder")
    monkeypatch.setattr(builder.os, "replace", lambda *_: (_ for _ in ()).throw(OSError("disk full")))
    code, _, session, output, _ = run_main(
        universe=[{"ticker": "000001", "name": "one"}], scripted=[_Response({"status": "000", "list": [_row()]})],
        raw_existing=encoded,
    )
    assert code == 1 and output.read_bytes() == encoded and len(session.calls) == 1


def test_valid_all_empty_universe_saves_empty_stocks(run_main):
    code, doc, _, _, _ = run_main(
        universe=[{"ticker": "000001", "name": "one"}], previous={"stocks": [_stock()]},
        scripted=[_Response({"status": "000", "list": []})],
    )
    assert code == 0 and doc["stocks"] == []
    assert _coverage(doc)["by_ticker"]["000001"]["state"] == "empty"


def test_no_credentials_leaves_existing_file_unchanged_and_does_not_call(run_main):
    previous = {"stocks": [_stock()], "coverage": {"schema_version": 1, "by_ticker": {"000001": {"state": "ok"}}, "counts": {"ok": 1}}}
    code, doc, session, output, _ = run_main(
        universe=[{"ticker": "000001", "name": "one"}], previous=previous,
        scripted=[_Response({"status": "000", "list": []})], key="",
    )
    assert code == 0 and not session.calls
    assert json.loads(output.read_text(encoding="utf-8")) == previous and doc == previous


def test_failure_after_confirmed_empty_keeps_old_evidence_without_new_zero(run_main):
    prior = {"stocks": [], "coverage": {"schema_version": 1, "by_ticker": {
        "000001": {"state": "empty", "last_success_at": "2026-09-01T10:00:00+09:00",
                   "last_success_state": "empty", "last_success_row_count": 0},
    }}}
    _, doc, _, _, _ = run_main(
        universe=[{"ticker": "000001", "name": "one"}], previous=prior,
        scripted=[_Response({"status": "800"})],
    )
    entry = _coverage(doc)["by_ticker"]["000001"]
    assert entry["state"] == "failed" and entry["last_success_state"] == "empty"
    assert entry["last_success_at"] == "2026-09-01T10:00:00+09:00"
    assert doc["stocks"] == [] and doc["_meta"]["collected_today"] == 0


def test_exceptions_consume_budget_and_do_not_log_request_secrets(run_main, capsys):
    _, doc, session, _, _ = run_main(
        universe=[{"ticker": "000001", "name": "one"}, {"ticker": "000002", "name": "two"}],
        scripted=[TimeoutError("url?crtfc_key=must-not-log")], max_calls=1,
    )
    coverage = _coverage(doc)
    assert len(session.calls) == coverage["request_count"] == 1
    assert coverage["by_ticker"]["000002"]["state"] == "not_collected"
    assert coverage["by_ticker"]["000002"]["skip_reason"] == "budget_exhausted"
    assert "must-not-log" not in capsys.readouterr().err


def test_contradictory_013_with_rows_is_failure_not_empty(run_main):
    _, doc, _, _, _ = run_main(
        universe=[{"ticker": "000001", "name": "one"}], previous={"stocks": [_stock()]},
        scripted=[_Response({"status": "013", "list": [_row()]})],
    )
    entry = _coverage(doc)["by_ticker"]["000001"]
    assert entry["state"] == "failed" and entry["failure_reason"] == "conflicting_empty_response"
    assert doc["stocks"] == [_stock()] and "last_success_at" not in entry


@pytest.mark.parametrize("coverage", [
    None, {"schema_version": 2, "by_ticker": {}},
    {"schema_version": True, "by_ticker": {}},
    {"schema_version": 1, "by_ticker": {"000001": {}}},
])
def test_invalid_previous_coverage_preserved_before_requests(run_main, coverage):
    previous = {"stocks": [_stock()], "coverage": coverage}
    original = json.dumps(previous, ensure_ascii=False).encode()
    code, _, session, output, _ = run_main(
        universe=[{"ticker": "000001", "name": "one"}], raw_existing=original,
    )
    assert code == 1 and not session.calls and output.read_bytes() == original


def test_outside_universe_evidence_is_retained_but_not_counted(run_main):
    prior = {"stocks": [_stock("999999")], "coverage": {"schema_version": 1, "by_ticker": {
        "999999": {"state": "ok", "last_success_at": "2026-09-01", "last_success_state": "ok"},
    }}}
    _, doc, _, _, _ = run_main(
        universe=[{"ticker": "000001", "name": "one"}], previous=prior,
        scripted=[_Response({"status": "013"})],
    )
    coverage = _coverage(doc)
    outside = coverage["by_ticker"]["999999"]
    assert outside["in_universe"] is False and outside["attempted_this_run"] is False
    assert outside["last_success_at"] == "2026-09-01"
    assert coverage["universe_count"] == 1 and coverage["counts"] == {"empty": 1}
    assert doc["stocks"] == [_stock("999999")]


def test_missing_universe_never_rewrites_snapshot(run_main):
    original = json.dumps({"stocks": [_stock()]}).encode()
    code, _, session, output, _ = run_main(universe=[], raw_existing=original)
    assert code == 1 and not session.calls and output.read_bytes() == original
