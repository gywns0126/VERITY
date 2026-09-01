# -*- coding: utf-8 -*-
"""paper_track — 사전등록 규칙 가상 집행 계약 (E1/E2/E3/E5/S1/X1/X2/X3 + 상태 영속)."""
import json
import os

import api.execution.paper_track as pt


def _rec(tk="005930", final="BUY", aligned=True, price=10_000.0, brain=70, avg_vol=200_000,
         badge=None, critical=False, name=None):
    return {
        "ticker": tk, "name": name or f"종목{tk}", "current_price": price,
        "recommendation": badge or final,
        "display_verdict": {"final": final, "aligned": aligned, "gates": []},
        "verity_brain": {"brain_score": brain, "position_guide": {"recommended_pct": 3},
                          "red_flags": {"has_critical": critical}},
        "trends": {"1m": {"avg_volume": avg_vol}},
    }


def _run(analyzed, tmp, exposure=0.5, source_as_of=None):
    pt._fetch_moderation_exposure = lambda: exposure  # S1 종속 주입
    return pt.run_paper_track(analyzed, str(tmp), source_as_of=source_as_of)


def test_entry_signal_creates_pending_and_fills_next_run(tmp_path, monkeypatch):
    s = _run([_rec()], tmp_path)
    assert s["pending"] == 1 and s["entered_today"] == 1 and not s["positions"]
    # 다음 run (다른 날짜로) — 밴드 내 체결
    st = json.load(open(tmp_path / "exec_paper_state.json"))
    st["last_date"] = "2000-01-01"
    json.dump(st, open(tmp_path / "exec_paper_state.json", "w"))
    s2 = _run([_rec(price=10_100.0)], tmp_path)
    assert "005930" in s2["positions"] and s2["pending"] == 0
    assert s2["positions"]["005930"]["buy_price"] == 10_100.0


def test_e2_band_cancels_far_fill(tmp_path):
    _run([_rec(price=10_000.0)], tmp_path)
    st = json.load(open(tmp_path / "exec_paper_state.json")); st["last_date"] = "2000-01-01"
    json.dump(st, open(tmp_path / "exec_paper_state.json", "w"))
    s2 = _run([_rec(price=10_350.0)], tmp_path)  # +3.5% > 2% 밴드
    # 체결 취소(추격 금지). 신호가 여전히 유효하면 새 ref_price 로 재주문 — 등록 E2 정합.
    assert not s2["positions"] and s2["entered_today"] == 1


def test_pending_buy_rechecks_full_entry_condition(tmp_path):
    _run([_rec(price=10_000.0, avg_vol=200_000)], tmp_path)
    st = json.load(open(tmp_path / "exec_paper_state.json"))
    st["last_date"] = "2000-01-01"
    json.dump(st, open(tmp_path / "exec_paper_state.json", "w"))
    s = _run([_rec(price=10_000.0, avg_vol=1)], tmp_path)
    assert not s["positions"]
    assert s["pending"] == 0
    assert "target_temporarily_ineligible" in s["flags"]


def test_missing_rank_target_does_not_create_stale_order(tmp_path):
    first = _run([
        _rec(tk="005930", brain=70),
        _rec(tk="000660", brain=69),
        _rec(tk="035420", brain=68),
    ], tmp_path)
    assert first["pending"] == 2
    st = json.load(open(tmp_path / "exec_paper_state.json"))
    st["last_date"] = "2000-01-01"
    st["pending"] = []
    json.dump(st, open(tmp_path / "exec_paper_state.json", "w"))
    second = _run([_rec(tk="035420", brain=68)], tmp_path)
    assert second["pending"] == 1
    assert second["targets"][0]["ticker"] == "005930"
    pending = json.load(open(tmp_path / "exec_paper_state.json"))["pending"]
    assert [row["ticker"] for row in pending] == ["035420"]


def test_e3_liquidity_and_e4_pollution_skip(tmp_path):
    s = _run([_rec(avg_vol=1000), _rec(tk="000660", name="a,b오염"), _rec(tk="035420", critical=True)], tmp_path)
    assert s["pending"] == 0 and s["entered_today"] == 0


def test_e5_max_two_entries(tmp_path):
    recs = [_rec(tk=f"00000{i}", brain=60 + i) for i in range(1, 5)]
    s = _run(recs, tmp_path)
    assert s["pending"] == 2  # 목표 포트폴리오를 하루 2건씩 구성


def test_paper_exposure_falls_back_when_moderation_unavailable(tmp_path):
    s = _run([_rec()], tmp_path, exposure=None)
    assert s["pending"] == 1
    assert s["target_exposure_pct"] == 50.0
    assert "paper_exposure_fallback_50pct" in s["flags"]


def test_x2_avoid_immediate_exit(tmp_path):
    _run([_rec()], tmp_path)
    st = json.load(open(tmp_path / "exec_paper_state.json"))
    st["last_date"] = "2000-01-01"; st["positions"] = {"005930": {"qty": 10, "buy_price": 10_000.0, "buy_date": "2000-01-01", "missing_days": 0}}
    st["pending"] = []; st["cash"] = 100000.0
    json.dump(st, open(tmp_path / "exec_paper_state.json", "w"))
    s = _run([_rec(final="AVOID", aligned=False, badge="AVOID", price=9_000.0)], tmp_path)
    assert not s["positions"] and s["trades_total"] >= 1


def test_x3_stop_queues_next_run_exit(tmp_path):
    _run([_rec()], tmp_path)
    st = json.load(open(tmp_path / "exec_paper_state.json"))
    st["last_date"] = "2000-01-01"; st["positions"] = {"005930": {"qty": 10, "buy_price": 10_000.0, "buy_date": "2000-01-01", "missing_days": 0}}
    st["pending"] = []
    json.dump(st, open(tmp_path / "exec_paper_state.json", "w"))
    s = _run([_rec(final="WATCH", aligned=False, badge="WATCH", price=8_900.0)], tmp_path)  # -11%
    assert s["pending"] == 1  # 익일 청산 큐


def test_watch_rank_enters_without_aligned_buy(tmp_path):
    s = _run([_rec(final="WATCH", aligned=False, badge="WATCH", brain=64)], tmp_path)
    assert s["pending"] == 1
    assert s["targets"][0]["ticker"] == "005930"
    assert s["_meta"]["score_system"]["name"] == "current Brain rank"


def test_rank_target_reports_candidate_denominator(tmp_path):
    rows = [
        _rec(tk="005930", final="WATCH", aligned=False, badge="WATCH", brain=65),
        _rec(tk="000660", final="WATCH", aligned=False, badge="WATCH", brain=64),
        _rec(tk="035420", final="CAUTION", aligned=False, badge="CAUTION", brain=90),
    ]
    s = _run(rows, tmp_path)
    assert s["denominator"]["kr_candidate_n"] == 3
    assert s["denominator"]["eligible_n"] == 2
    assert s["denominator"]["rejected"]["grade_below_watch"] == 1
    assert [x["ticker"] for x in s["targets"]] == ["005930", "000660"]


def test_empty_v0_state_migrates_to_forward_v1(tmp_path):
    old = {
        "version": "v0", "initialized": "2026-08-04", "cash": 10_000_000.0,
        "positions": {}, "pending": [], "last_date": "2026-09-01", "trades": 0,
        "realized_pnl": 0.0,
    }
    (tmp_path / "exec_paper_state.json").write_text(json.dumps(old), encoding="utf-8")
    s = _run([_rec(final="WATCH", aligned=False, badge="WATCH")], tmp_path)
    assert s["version"] == pt.TRACK_VERSION
    assert "migrated_empty_v0_to_v1" in s["flags"]
    assert s["pending"] == 1


def test_nonempty_v0_state_halts_without_mixing_epochs(tmp_path):
    old = {
        "version": "v0", "initialized": "2026-08-04", "cash": 9_000_000.0,
        "positions": {"005930": {"qty": 10, "buy_price": 100_000.0, "buy_date": "2026-08-20"}},
        "pending": [], "last_date": "2026-09-01", "trades": 1, "realized_pnl": 0.0,
    }
    (tmp_path / "exec_paper_state.json").write_text(json.dumps(old), encoding="utf-8")
    s = _run([_rec(final="WATCH", aligned=False, badge="WATCH", price=100_000.0)], tmp_path)
    assert s["status"] == "HALTED"
    assert s["real_orders"] == 0
    assert "v0_nonempty_migration_halted" in s["flags"]
    assert "manual_epoch_decision_required" in s["flags"]


def test_same_price_fingerprint_does_not_add_market_session(tmp_path):
    first = _run([_rec(final="WATCH", aligned=False, badge="WATCH")], tmp_path)
    assert first["market_sessions"] == 1
    st = json.load(open(tmp_path / "exec_paper_state.json"))
    st["last_date"] = "2000-01-01"
    json.dump(st, open(tmp_path / "exec_paper_state.json", "w"))
    second = _run([_rec(final="WATCH", aligned=False, badge="WATCH")], tmp_path)
    assert second["market_sessions"] == 1


def test_buy_fill_deducts_registered_cost(tmp_path):
    _run([_rec()], tmp_path)
    st = json.load(open(tmp_path / "exec_paper_state.json"))
    st["last_date"] = "2000-01-01"
    json.dump(st, open(tmp_path / "exec_paper_state.json", "w"))
    s = _run([_rec(price=10_000.0)], tmp_path)
    assert s["trades_total"] == 1
    assert s["cost_paid"] > 0
    assert s["cash"] < 10_000_000 - 490_000


def test_whole_share_constraint_selects_max_equal_weight_set(tmp_path):
    rows = [
        _rec(tk=f"{i:06d}", brain=100 - i, price=2_000_000.0 if i in (5, 9) else 100_000.0)
        for i in range(1, 12)
    ]
    s = _run(rows, tmp_path, exposure=0.5)
    assert s["target_holdings"] == 9
    assert s["denominator"]["signal_eligible_n"] == 11
    assert s["denominator"]["eligible_n"] == 9
    assert s["denominator"]["rejected"]["one_share_above_slot"] == 2
    assert s["denominator"]["slot_budget_krw"] == 555_556
    assert {"000005", "000009"}.isdisjoint({row["ticker"] for row in s["targets"]})
    assert s["targets"][-1]["signal_rank"] == 11


def test_price_snapshot_reports_source_time_and_clock_state(tmp_path):
    as_of = "2026-09-01T21:51:18+09:00"
    s = _run([_rec()], tmp_path, source_as_of=as_of)
    assert s["price_snapshot"]["as_of"] == as_of
    assert s["price_snapshot"]["source"] == "portfolio.recommendations.current_price"
    assert s["price_snapshot"]["holiday_calendar"] == "not_connected"
    assert s["targets"][0]["price_as_of"] == as_of
