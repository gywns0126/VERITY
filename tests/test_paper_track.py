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


def _run(analyzed, tmp, exposure=0.5):
    pt._fetch_moderation_exposure = lambda: exposure  # S1 종속 주입
    return pt.run_paper_track(analyzed, str(tmp))


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


def test_e3_liquidity_and_e4_pollution_skip(tmp_path):
    s = _run([_rec(avg_vol=1000), _rec(tk="000660", name="a,b오염"), _rec(tk="035420", critical=True)], tmp_path)
    assert s["pending"] == 0 and s["entered_today"] == 0


def test_e5_max_two_entries(tmp_path):
    recs = [_rec(tk=f"00000{i}", brain=60 + i) for i in range(1, 5)]
    s = _run(recs, tmp_path)
    assert s["pending"] == 2  # brain 상위 2건만


def test_s1_halt_when_moderation_unavailable(tmp_path):
    s = _run([_rec()], tmp_path, exposure=None)
    assert s["pending"] == 0
    assert "s1_moderation_unavailable_entries_halted" in s["flags"]


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
