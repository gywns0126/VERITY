"""metadata 인프라 4개 모듈 회귀 테스트 — 골격 + 핵심 함수."""
import json
import os
import pytest

from api.metadata import user_actions, brain_learning, llm_cost, backtest_gap


@pytest.fixture(autouse=True)
def _clean_metadata_dir(monkeypatch, tmp_path):
    """각 테스트는 격리된 metadata 디렉토리 사용."""
    md = tmp_path / "metadata"
    md.mkdir()
    monkeypatch.setattr(user_actions, "_PATH", str(md / "user_actions.jsonl"))
    monkeypatch.setattr(brain_learning, "_PATH", str(md / "brain_learning.jsonl"))
    monkeypatch.setattr(llm_cost, "_PATH", str(md / "llm_cost.jsonl"))
    monkeypatch.setattr(backtest_gap, "_PATH", str(md / "backtest_gap.jsonl"))


# ── user_actions ────────────────────────────────────────

def test_user_action_agreement():
    ua = user_actions.log_action("005930", "buy", system_grade="BUY")
    assert ua["agreement"] == "agree"


def test_user_action_disagreement():
    ua = user_actions.log_action("035420", "buy", system_grade="AVOID")
    assert ua["agreement"] == "disagree_user_buy_system_avoid"


def test_user_action_no_signal():
    ua = user_actions.log_action("000660", "buy", system_grade=None)
    assert ua["agreement"] == "no_signal"


def test_user_action_summary_aggregates():
    user_actions.log_action("A", "buy", system_grade="BUY")
    user_actions.log_action("B", "buy", system_grade="AVOID")
    user_actions.log_action("C", "sell", system_grade="BUY")
    s = user_actions.summarize(days=1)
    assert s["total_actions"] == 3
    assert s["agreement_count"] == 1
    assert s["user_buy_system_avoid"] == 1
    assert s["user_sell_system_buy"] == 1


# ── brain_learning ──────────────────────────────────────

def test_brain_learning_logs_grade_distribution():
    portfolio = {
        "recommendations": [
            {"verity_brain": {"grade": "BUY", "vci": {"vci": 5}}},
            {"verity_brain": {"grade": "BUY", "vci": {"vci": -3}}},
            {"verity_brain": {"grade": "AVOID", "vci": {"vci": 35}}},
        ],
    }
    e = brain_learning.log_daily_signals(portfolio)
    assert e["grade_distribution"]["BUY"] == 2
    assert e["grade_distribution"]["AVOID"] == 1
    assert e["vci"]["count"] == 3
    assert e["vci"]["extreme_count"] == 1  # |35| >= 30


def test_brain_learning_empty_portfolio():
    e = brain_learning.log_daily_signals({})
    assert e["grade_distribution"] == {}
    assert e["vci"]["count"] == 0


# ── llm_cost ────────────────────────────────────────────

def test_llm_cost_estimate_known_model():
    cost = llm_cost.estimate_cost("claude-sonnet-4-6", 1_000_000, 1_000_000)
    # 단가 input $3 + output $15 = $18 per 1M
    assert cost == pytest.approx(18.0, rel=0.01)


def test_llm_cost_estimate_unknown_model():
    cost = llm_cost.estimate_cost("nonexistent-model", 1000, 500)
    assert cost == 0.0


def test_llm_cost_summary_aggregates():
    llm_cost.log_call("anthropic", "claude-sonnet-4-6", "report", 5000, 1500)
    llm_cost.log_call("google", "gemini-2.5-flash", "summary", 10000, 2000)
    s = llm_cost.summarize_cost(days=1)
    assert s["calls"] == 2
    assert s["total_usd"] > 0
    assert "anthropic" in s["by_provider"]
    assert "google" in s["by_provider"]


# ── backtest_gap ────────────────────────────────────────

def test_backtest_gap_calculates_slippage():
    e = backtest_gap.log_gap("005930", 70000, 70200)
    assert e["entry_slippage_pct"] == pytest.approx(0.286, abs=0.01)


def test_backtest_gap_no_exit():
    e = backtest_gap.log_gap("005930", 70000, 70200)
    assert e["exit_slippage_pct"] is None


def test_backtest_gap_summary_no_data():
    s = backtest_gap.summarize_gap(days=1)
    assert s["samples"] == 0


def test_backtest_gap_summary_aggregates():
    backtest_gap.log_gap("005930", 70000, 70200, backtest_return_pct=2.0, sim_return_pct=1.8)
    backtest_gap.log_gap("000660", 130000, 130100, backtest_return_pct=1.0, sim_return_pct=0.9)
    s = backtest_gap.summarize_gap(days=1)
    assert s["samples"] == 2
    assert s["avg_entry_slippage_pct"] is not None
    assert s["avg_return_gap_pct"] is not None
