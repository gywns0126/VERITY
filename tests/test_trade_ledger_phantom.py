# -*- coding: utf-8 -*-
"""VAMS 원장 재생 — 유령 매도 배제 + 거래 정의 단일화 (2026-08-05).

사고: 2026-07-20 감사가 잡은 "dev-mode 사이클이 prod history 에 phantom 매도 기록"의
**잔존 기록**이 게이트 통계를 오염시키고 있었다. 버그는 ec7a66111 로 수정됐지만 원장에
남은 58건이 계속 집계됐다 — 리셋 후 SELL 70 = 실제 12 + 유령 58, 유령 손익 −1,396,639원.
실측 교정: 거래 78→20 · 승률 5.1%→20.0% · 실현손익 −1,815,620→−418,981원.

계약: ① 보유 0 상태 매도 = episode 아님(유령) ② 부분청산은 부모 episode 에 합산
③ 창(자본 리셋) 밖 청산 제외, 단 **보유 재생은 전 기간**(경계 전 매수가 경계 후 매도의 근거)
④ 원장 무삭제 — 집계 시점 배제만(감사 trail 보존) ⑤ simulation_stats·validation 공용 SoT.
"""
from api.vams.trade_ledger import episode_pnls, reconstruct


def _b(tk, d, q):
    return {"type": "BUY", "ticker": tk, "date": d, "quantity": q}


def _s(tk, d, pnl):
    return {"type": "SELL", "ticker": tk, "date": d, "pnl": pnl}


def _p(tk, d, qty, pnl):
    return {"type": "PARTIAL_SELL", "ticker": tk, "date": d, "sold_qty": qty, "partial_pnl": pnl}


def test_repeated_sell_of_same_position_is_phantom():
    """EQT 실사고형 — 9주 보유인데 매도가 반복 기록됐다."""
    h = [_b("EQT", "2026-07-01", 9), _s("EQT", "2026-07-06", -380),
         _s("EQT", "2026-07-07", -3748), _s("EQT", "2026-07-07", -1324)]
    r = reconstruct(h)
    assert len(r["episodes"]) == 1              # 첫 매도만 실제
    assert len(r["phantoms"]) == 2
    assert r["phantom_pnl"] == -5072           # 존재하지 않던 손실


def test_phantom_losses_do_not_enter_stats():
    h = [_b("A", "2026-06-01", 10), _s("A", "2026-06-10", +1000)]
    h += [_s("A", f"2026-06-{d}", -5000) for d in range(11, 21)]   # 유령 10건
    pnls, r = episode_pnls(h)
    assert pnls == [1000]                       # 승 1건만 남는다
    assert len(r["phantoms"]) == 10


def test_rebuy_after_sell_is_a_new_episode():
    """재진입은 정상 — 유령으로 오판하면 안 된다."""
    h = [_b("A", "2026-06-01", 10), _s("A", "2026-06-10", -100),
         _b("A", "2026-07-01", 10), _s("A", "2026-07-10", +200)]
    pnls, r = episode_pnls(h)
    assert pnls == [-100, 200] and not r["phantoms"]


def test_partial_exit_folds_into_parent_episode():
    h = [_b("A", "2026-06-01", 10), _p("A", "2026-06-05", 3, +30_000),
         _s("A", "2026-06-10", -10_000)]
    pnls, r = episode_pnls(h)
    assert pnls == [20_000]                     # 청산 −10,000 + 부분 +30,000
    assert r["episodes"][0]["partial_pnl"] == 30_000


def test_partial_pnl_falls_back_to_pnl_key():
    """원장 이벤트가 partial_pnl 대신 pnl 을 쓰는 경우도 잡는다(키 상이 이력)."""
    h = [_b("A", "2026-06-01", 10),
         {"type": "PARTIAL_SELL", "ticker": "A", "date": "2026-06-05",
          "sold_qty": 3, "pnl": 5_000},
         _s("A", "2026-06-10", -1_000)]
    assert episode_pnls(h)[0] == [4_000]


def test_open_position_partials_count_as_realized_money():
    """부분익절만 하고 보유 중 — 거래로는 안 세지만 돈은 실현됐다."""
    h = [_b("A", "2026-06-01", 10), _p("A", "2026-06-05", 3, +7_000)]
    r = reconstruct(h)
    assert r["episodes"] == [] and r["partial_realized"] == 7_000
    assert r["open_positions"]["A"] == 7


def test_window_excludes_old_episodes_but_keeps_position_replay():
    """🚨 창 밖 매수를 잘라내면 창 안 정상 매도가 유령으로 오판된다."""
    h = [_b("A", "2026-04-01", 10),          # 리셋 이전 매수
         _s("A", "2026-06-01", -500)]        # 리셋 이후 매도 = 정상 episode
    pnls, r = episode_pnls(h, since="2026-05-17")
    assert pnls == [-500]
    assert not r["phantoms"]


def test_pre_window_episode_is_excluded_and_counted():
    h = [_b("A", "2026-04-01", 10), _s("A", "2026-04-20", +900_000),
         _b("B", "2026-06-01", 5), _s("B", "2026-06-10", -5_000)]
    pnls, r = episode_pnls(h, since="2026-05-17")
    assert pnls == [-5_000]                   # 리셋 전 +90만이 새지 않는다
    assert r["excluded_pre_window"] == 1


def test_sell_without_pnl_is_ignored():
    h = [_b("A", "2026-06-01", 10), {"type": "SELL", "ticker": "A", "date": "2026-06-10"}]
    assert episode_pnls(h)[0] == []


def test_events_are_replayed_in_date_order():
    """원장이 시간순이 아니어도 재생 결과가 같아야 한다."""
    h = [_s("A", "2026-06-10", -100), _b("A", "2026-06-01", 10)]
    pnls, r = episode_pnls(h)
    assert pnls == [-100] and not r["phantoms"]


def test_name_key_fallback_when_ticker_missing():
    h = [{"type": "BUY", "name": "EQT", "date": "2026-06-01", "quantity": 5},
         {"type": "SELL", "name": "EQT", "date": "2026-06-10", "pnl": 100}]
    assert episode_pnls(h)[0] == [100]
