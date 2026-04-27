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
    ua = user_actions.log_action(source="KIS_AUTO", ticker="005930", action="BUY", brain_grade="BUY")
    assert ua["agreement"] == "agree"
    assert ua["source"] == "KIS_AUTO"


def test_user_action_disagreement():
    ua = user_actions.log_action(source="VERCEL_MANUAL", ticker="035420", action="BUY", brain_grade="AVOID")
    assert ua["agreement"] == "disagree_user_buy_system_avoid"


def test_user_action_no_signal():
    ua = user_actions.log_action(source="KIS_AUTO", ticker="000660", action="BUY", brain_grade=None)
    assert ua["agreement"] == "no_signal"


def test_user_action_override():
    ua = user_actions.log_action(source="VERCEL_MANUAL", ticker="005930", action="OVERRIDE",
                                 reason="VAMS 거절을 수동으로 뒤집음")
    assert ua["agreement"] == "user_override"


def test_user_action_legacy_compat():
    """옛 호출 시그니처(quantity/system_grade/user_note) 호환."""
    ua = user_actions.log_action(source="KIS_AUTO", ticker="005930", action="BUY",
                                 quantity=10, system_grade="BUY", user_note="구버전 호출")
    assert ua["qty"] == 10
    assert ua["brain_grade"] == "BUY"
    assert ua["reason"] == "구버전 호출"


def test_user_action_summary_aggregates():
    user_actions.log_action(source="KIS_AUTO", ticker="A", action="BUY", brain_grade="BUY")
    user_actions.log_action(source="VERCEL_MANUAL", ticker="B", action="BUY", brain_grade="AVOID")
    user_actions.log_action(source="KIS_AUTO", ticker="C", action="SELL", brain_grade="BUY")
    s = user_actions.summarize(days=1)
    assert s["total_actions"] == 3
    assert s["agreement_count"] == 1
    assert s["user_buy_system_avoid"] == 1
    assert s["user_sell_system_buy"] == 1
    assert s["by_source"]["KIS_AUTO"] == 2
    assert s["by_source"]["VERCEL_MANUAL"] == 1


def test_user_action_source_filter():
    user_actions.log_action(source="KIS_AUTO", ticker="A", action="BUY", brain_grade="BUY")
    user_actions.log_action(source="VERCEL_MANUAL", ticker="B", action="BUY", brain_grade="AVOID")
    s_kis = user_actions.summarize(days=1, source_filter="KIS_AUTO")
    s_vrcl = user_actions.summarize(days=1, source_filter="VERCEL_MANUAL")
    assert s_kis["total_actions"] == 1
    assert s_vrcl["total_actions"] == 1
    assert s_vrcl["user_buy_system_avoid"] == 1


def test_user_action_invalid_source_warns():
    """잘못된 source 는 UNKNOWN 으로 기록 (raise X)."""
    ua = user_actions.log_action(source="INVALID", ticker="X", action="BUY", brain_grade="BUY")
    assert ua["source"] == "UNKNOWN"


def test_user_action_full_context():
    ua = user_actions.log_action(
        source="KIS_AUTO", ticker="005930", action="BUY",
        qty=10, price=72000.0,
        brain_grade="BUY", brain_score=68.5,
        regime="NORMAL", vams_profile="moderate",
        reason="Brain BUY + 매크로 정상",
    )
    assert ua["brain_score"] == 68.5
    assert ua["regime"] == "NORMAL"
    assert ua["vams_profile"] == "moderate"
    assert ua["price"] == 72000.0


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
