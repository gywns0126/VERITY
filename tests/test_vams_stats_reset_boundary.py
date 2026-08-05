# -*- coding: utf-8 -*-
"""VAMS simulation_stats 측정 정화 — 자본 리셋 경계 + 부분청산 정의 (2026-08-05).

사고: 리셋(2026-05-17, 자본 1천만 재출발) **이전** 13건이 통계에 섞여 성과를 과대표시.
  옛 91거래·승률 12.1%·실현손익 −409,108원 ↔ 실제(리셋 후) 78거래·5.1%·−1,815,620원.
2차 피해: verification_trail 이 이 total_trades 를 "리셋 후 누적"으로 보고 N=252
  유의성 마일스톤을 계산 — 13건 과대계상.
3차: 같은 원장을 validation_report(게이트 판정)와 다르게 읽어 4.8배 괴리.

계약: ① 창 = reset_meta.reset_at 이후 ② 거래 1건 = 청산 episode(부분청산은 부모에 합산)
③ realized_pnl = 실제 돈(창 내 청산 raw + 창 내 부분청산 전액) ④ validation.py 와 일치.
"""
import api.main as M


def _hist():
    # 🚨 2026-08-05 유령 매도 가드 도입 후 — 모든 SELL 은 선행 BUY(수량 포함)가 있어야
    # 실제 청산으로 인정된다. 보유 0 매도는 phantom 으로 배제된다(trade_ledger SoT).
    return [
        {"type": "BUY", "ticker": "AAA", "date": "2026-04-01", "quantity": 10},
        {"type": "BUY", "ticker": "BBB", "date": "2026-05-01", "quantity": 10},
        {"type": "BUY", "ticker": "DDD", "date": "2026-06-20", "quantity": 10},
        {"type": "BUY", "ticker": "EEE", "date": "2026-07-10", "quantity": 10},
        # ── 리셋(2026-05-17) 이전 — 전부 제외돼야 한다 ──
        {"type": "SELL", "ticker": "AAA", "name": "이전승", "date": "2026-04-02", "pnl": 500_000},
        {"type": "SELL", "ticker": "BBB", "name": "이전패", "date": "2026-05-15", "pnl": -100_000},
        # ── 리셋 이후 ──
        {"type": "BUY", "ticker": "CCC", "date": "2026-05-20", "quantity": 10},
        {"type": "PARTIAL_SELL", "ticker": "CCC", "date": "2026-06-01", "sold_qty": 3, "partial_pnl": 30_000},
        # 청산 −10,000 인데 부분익절 +30,000 → episode 는 +20,000 = 승
        {"type": "SELL", "ticker": "CCC", "name": "합산승", "date": "2026-06-10", "pnl": -10_000},
        {"type": "SELL", "ticker": "DDD", "name": "패", "date": "2026-07-01", "pnl": -50_000},
        # 부분익절만 하고 아직 보유 중 — 거래로는 안 세지만 돈은 실현됐다
        {"type": "PARTIAL_SELL", "ticker": "EEE", "date": "2026-07-20", "sold_qty": 3, "partial_pnl": 7_000},
    ]


def _run(monkeypatch, history, reset_at="2026-05-17T14:12:07+09:00"):
    monkeypatch.setattr("api.vams.engine.load_history", lambda: history)
    pf = {"vams": {"total_asset": 10_000_000,
                   "reset_meta": ({"reset_at": reset_at} if reset_at else {})}}
    M._update_simulation_stats(pf)
    return pf["vams"]["simulation_stats"]


def test_pre_reset_trades_are_excluded(monkeypatch):
    s = _run(monkeypatch, _hist())
    assert s["total_trades"] == 2                  # CCC · DDD (AAA·BBB 제외)
    assert s["excluded_pre_reset_trades"] == 2
    assert s["window_start"] == "2026-05-17"


def test_partial_exit_folds_into_parent_episode(monkeypatch):
    """부분익절을 별건 '승'으로 세면 승률이 부풀려진다 — 부모에 합산해 1건."""
    s = _run(monkeypatch, _hist())
    assert s["win_count"] == 1                     # CCC: -10,000 + 30,000 = +20,000
    assert s["loss_count"] == 1                    # DDD
    assert s["win_rate"] == 50.0
    assert s["partial_exits_folded"] is True


def test_realized_pnl_counts_open_position_partials(monkeypatch):
    """돈 기준 — 미청산 종목(EEE)의 부분익절도 실현손익이다."""
    s = _run(monkeypatch, _hist())
    # 창 내 청산 raw(-10,000 -50,000) + 창 내 부분청산(30,000 + 7,000) = -23,000
    assert s["realized_pnl"] == -23_000


def test_pre_reset_partials_are_discarded_with_their_episode(monkeypatch):
    hist = [
        {"type": "BUY", "ticker": "XXX", "date": "2026-04-01", "quantity": 10},
        {"type": "PARTIAL_SELL", "ticker": "XXX", "date": "2026-04-10",
         "sold_qty": 3, "partial_pnl": 900_000},
        {"type": "SELL", "ticker": "XXX", "date": "2026-04-20", "pnl": -100_000},
        {"type": "BUY", "ticker": "YYY", "date": "2026-05-25", "quantity": 10},
        {"type": "SELL", "ticker": "YYY", "date": "2026-06-01", "pnl": -5_000},
    ]
    s = _run(monkeypatch, hist)
    assert s["total_trades"] == 1
    assert s["realized_pnl"] == -5_000             # 리셋 전 +90만이 새지 않는다


def test_legacy_without_reset_meta_counts_all(monkeypatch):
    """reset_meta 부재(구 데이터) = 전체 집계 + window_start=None 로 정직 표기."""
    s = _run(monkeypatch, _hist(), reset_at=None)
    assert s["window_start"] is None
    assert s["total_trades"] == 4                  # AAA·BBB·CCC·DDD
    assert s["excluded_pre_reset_trades"] == 0


def test_definition_field_is_emitted(monkeypatch):
    """산출물이 스스로 '무엇을 셌는지' 말해야 재발을 막는다."""
    s = _run(monkeypatch, _hist())
    assert "episode" in s["definition"]
    assert "유령" in s["definition"] or "trade_ledger" in s["definition"]
