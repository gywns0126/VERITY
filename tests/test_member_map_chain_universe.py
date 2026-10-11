"""Offline chain-universe routing; collectors and persistence are mocked.

Out of scope: public overview refresh and the US evidence adapter remain pending.
Full-universe completion also needs an error-retry policy; positive/no-hit freshness
refresh remains pending. A persisted no-hit is not a confirmed absence of customers.
"""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest


CORNER = [("111111", "Corner")]
MARKET = CORNER + [("222222", "Outside"), ("333333", "Later")]


def source(ticker="222222", *, snippets=None):
    return {"ticker": ticker, "corp_code": "12345678",
            "rcept_no": "20260319001329", "rcept_dt": "20260319",
            "report_nm": "사업보고서 (2025.12)", "plain_text_len": 100,
            "snippets": [] if snippets is None else snippets}


@pytest.fixture
def backfill(monkeypatch):
    path = Path(__file__).resolve().parents[1] / "scripts/kr_company_facts_backfill.py"
    spec = spec_from_file_location("chain_universe_backfill", path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    inputs = {
        module.CORNER_PATH: {"stocks": [{"ticker": t, "name": n} for t, n in CORNER]},
        module.LISTED_PATH: {t: {"name": n} for t, n in MARKET},
        module.MKTCAP_PATH: {"map": {}},
    }
    monkeypatch.setattr(module, "_load", lambda path, default=None: inputs.get(path, default))
    monkeypatch.setattr(module, "time", SimpleNamespace(time=lambda: 1000, sleep=Mock()))
    for name in ("run_chain", "run_overview", "run_dividends", "run_cb_bw",
                 "run_shareholders", "run_llm_axis"):
        monkeypatch.setattr(module, name, Mock(return_value={"todo": 1, "ok": 1}))
    monkeypatch.setattr(module, "build_universe", Mock(wraps=module.build_universe))
    return module


def invoke(module, monkeypatch, *args):
    monkeypatch.setattr(sys, "argv", ["backfill", "--year", "2025", *args])
    return module.main()


@pytest.mark.parametrize("universe", ["corner", "reco"])
def test_chain_uses_full_market_even_when_requested_universe_is_empty(backfill, monkeypatch, universe):
    assert invoke(backfill, monkeypatch, "--universe", universe, "--axes", "chain",
                  "--limit", "1", "--delay", "0.3", "--axis-budget", "42") == 0
    backfill.run_chain.assert_called_once_with(MARKET, "2025", 0.3, False, 1, deadline=1042)
    assert backfill.build_universe.call_args_list[1].args == ("market", 1, None)


def test_explicit_market_reuses_the_initial_universe(backfill, monkeypatch):
    backfill.build_universe.return_value = MARKET
    assert invoke(backfill, monkeypatch, "--universe", "market", "--axes", "chain") == 0
    backfill.build_universe.assert_called_once_with("market", None, None)
    assert backfill.run_chain.call_args.args[0] is MARKET


def test_ticker_outside_corner_is_not_lost_to_empty_universe_guard(backfill, monkeypatch):
    assert invoke(backfill, monkeypatch, "--axes", "chain", "--ticker", "222222",
                  "--limit", "2", "--dry-run", "--axis-budget", "0") == 0
    backfill.run_chain.assert_called_once_with([MARKET[1]], "2025", 0.15, True, 2, deadline=None)
    assert backfill.build_universe.call_args_list[1].args == ("market", 2, "222222")


def test_other_axes_keep_requested_universe_and_overview_keeps_market(backfill, monkeypatch):
    assert invoke(backfill, monkeypatch, "--axes", "chain,overview,dividends,cb_bw,shareholders,kam",
                  "--limit", "2") == 0
    assert backfill.run_chain.call_args.args[0] == MARKET
    backfill.run_overview.assert_called_once_with(
        MARKET, "2025", 0.15, False, 2, retry_exhausted=False, deadline=2500)
    for runner in (backfill.run_dividends, backfill.run_cb_bw, backfill.run_shareholders):
        runner.assert_called_once_with(CORNER, "2025", 0.15, False, 2)
    backfill.run_llm_axis.assert_called_once_with("kam", CORNER, "2025", 0.15, False, 2)


def test_llm_consent_guard_still_precedes_any_universe_or_collector(backfill, monkeypatch):
    assert invoke(backfill, monkeypatch, "--axes", "chain,business") == 2
    backfill.build_universe.assert_not_called()
    backfill.run_chain.assert_not_called()
    backfill.run_llm_axis.assert_not_called()


@pytest.mark.parametrize("expired", [False, True])
def test_real_chain_filters_existing_before_limit_and_preserves_delay_deadline(backfill, monkeypatch, expired):
    spec = spec_from_file_location("chain_runner", Path(backfill.__file__))
    runner = module_from_spec(spec)
    spec.loader.exec_module(runner)
    collector = ModuleType("api.collectors.ChainScout")
    positive = source(snippets=["synthetic"])
    collector.scout_major_customer_snippets = Mock(return_value=positive)
    collector.save_snippets_payload = Mock()
    monkeypatch.setitem(sys.modules, "api.collectors.ChainScout", collector)
    monkeypatch.setattr(runner, "_load", lambda path, default=None: (
        {"by_ticker": {"111111": {}}} if path.endswith("chain_snippets.json") else {"stocks": []}))
    clock = SimpleNamespace(time=lambda: 1000, sleep=Mock())
    monkeypatch.setattr(runner, "time", clock)
    result = runner.run_chain(MARKET, "2025", 0.3, False, limit=1,
                              deadline=999 if expired else 1042)
    assert result == {"todo": 1, "ok": 0 if expired else 1, "budget_stopped": 1 if expired else 0}
    if expired:
        collector.scout_major_customer_snippets.assert_not_called()
        collector.save_snippets_payload.assert_not_called()
        clock.sleep.assert_not_called()
    else:
        collector.scout_major_customer_snippets.assert_called_once_with("222222.KS")
        collector.save_snippets_payload.assert_called_once_with(positive)
        clock.sleep.assert_called_once_with(0.3)


@pytest.fixture
def chain_state(backfill, monkeypatch):
    spec = spec_from_file_location("no_hit_chain_runner", Path(backfill.__file__))
    runner = module_from_spec(spec)
    spec.loader.exec_module(runner)
    stored = {}
    collector = ModuleType("api.collectors.ChainScout")
    collector.scout_major_customer_snippets = Mock()
    collector.save_snippets_payload = Mock(side_effect=lambda row: stored.update({row["ticker"]: row}))
    monkeypatch.setitem(sys.modules, "api.collectors.ChainScout", collector)
    monkeypatch.setattr(runner, "_load", lambda path, default=None: (
        {"by_ticker": stored} if path.endswith("chain_snippets.json") else {"stocks": []}))
    monkeypatch.setattr(runner, "time", SimpleNamespace(time=lambda: 1000, sleep=Mock()))
    return runner, collector, stored


def test_no_hit_advances_next_run_without_counting_relationship_success(chain_state, monkeypatch):
    runner, collector, stored = chain_state
    collector.scout_major_customer_snippets.side_effect = lambda ticker: source(ticker.split(".")[0])
    for ticker, _ in MARKET:
        result = runner.run_chain(MARKET, "2025", 0, False, limit=1, deadline=1042)
        assert result == {"todo": 1, "ok": 0, "budget_stopped": 0, "no_hit": 1, "progressed": 1}
        assert stored[ticker]["snippets"] == []
        assert not {"confirmed", "relationships", "accepted"} & stored[ticker].keys()
    assert [call.args[0] for call in collector.scout_major_customer_snippets.call_args_list] == [
        ticker + ".KS" for ticker, _ in MARKET]
    assert runner.run_chain(MARKET, "2025", 0, False, limit=1) == {"todo": 0, "ok": 0}
    # The existing CLI stall guard must treat processed no-hit sources as progress.
    monkeypatch.setattr(runner, "build_universe", Mock(return_value=MARKET))
    monkeypatch.setattr(runner, "run_chain", Mock(return_value=result))
    assert invoke(runner, monkeypatch, "--axes", "chain") == 0


@pytest.mark.parametrize("change", [
    {"error": "fetch failed"}, {"ticker": "999999"}, {"rcept_no": None},
    {"corp_code": None}, {"corp_code": "1234567"}, {"corp_code": "１２３４５６７８"},
    {"rcept_no": "not-a-receipt"}, {"rcept_dt": "20260230", "rcept_no": "20260230001329"},
    {"rcept_dt": "2026-03-19"}, {"report_nm": ""}, {"report_nm": "분기보고서 (2025.12)"},
    {"plain_text_len": 0}, {"plain_text_len": True}, {"snippets": None},
])
def test_invalid_no_hit_source_never_persists_or_claims_progress(chain_state, change):
    runner, collector, stored = chain_state
    collector.scout_major_customer_snippets.return_value = {**source("111111"), **change}
    result = runner.run_chain(MARKET, "2025", 0, False, limit=1)
    assert result == {"todo": 1, "ok": 0, "budget_stopped": 0}
    assert stored == {}
    collector.save_snippets_payload.assert_not_called()


def test_error_with_snippets_is_not_persisted(chain_state):
    runner, collector, stored = chain_state
    collector.scout_major_customer_snippets.return_value = {
        **source("111111", snippets=["synthetic"]), "error": "fetch failed"}
    assert runner.run_chain(MARKET, "2025", 0, False, limit=1)["ok"] == 0
    assert stored == {}


def test_valid_source_date_need_not_equal_receipt_prefix(chain_state):
    runner, collector, stored = chain_state
    payload = {**source("111111"), "rcept_dt": "20260320"}
    collector.scout_major_customer_snippets.return_value = payload
    result = runner.run_chain(MARKET, "2025", 0, False, limit=1)
    assert result["ok"] == 0 and result["progressed"] == 1
    assert stored["111111"] == payload
