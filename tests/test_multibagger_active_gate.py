"""멀티배거 active gate B 계약 — PREREG_MULTIBAGGER_ACTIVE_GATE_2026_08_22 (PM 승인).

이 배선의 최대 위험은 **손절에 번지는 것**이다.
2026-08-21 전향 검정(US 28년·비중첩 창 5개)에서 유일하게 유의했던 축이 **하방 회피**이고
(상방 10배 선별은 5가설 중 4개가 검출하한 미달), 손절이 그 하방을 잡는 장치다.
멀티배거 신호로 손절을 유예하면 **유일하게 작동하는 것을 끄는 셈**이 된다.

🚨 그래서 이 파일이 고정하는 1순위는 "익절만 유예되고 손절은 그대로인가" 다.
   값(180일/+50%)은 고정하지 않는다 — 임계 조정은 별도 사전등록 사안이고,
   여기서 값을 고정하면 정당한 재등록까지 막는다.
"""
import inspect

import pytest

from api.analyzers.multi_bagger_signals import detect_hold_pnl_threshold
from api.vams import engine


def _holding(**kw):
    # 실제 portfolio.json 보유 레코드의 필수 필드를 맞춘다 — 픽스처가 얇으면
    # 로직이 아니라 KeyError 로 실패해 계약을 못 잰다.
    h = {"ticker": "005930", "name": "삼성전자", "quantity": 100,
         "buy_price": 10000.0, "current_price": 15000.0, "highest_price": 15000.0,
         "total_cost": 1_000_000.0, "currency": "KRW", "entry_currency": "KRW",
         "entry_fx_rate": 1.0, "buy_date": "2025-01-01", "asset_class": "equity",
         "realized_pnl_partial": 0.0, "return_pct": 50.0,
         "exit_targets": {"target_1": {"price": 11000.0, "exit_pct": 30},
                          "target_2": {"price": 13000.0, "exit_pct": 50}},
         "exit_history": [], "trailing_active": False}
    h.update(kw)
    return h


def _pf():
    return {"vams": {"holdings": [], "cash": 10_000_000.0, "initial_capital": 10_000_000.0,
                     "total_value": 10_000_000.0, "trades": []}}


# ── 🚨 1순위: 손절 미접촉 ────────────────────────────────────────────

def test_stop_loss_never_reads_the_multibagger_signal():
    """손절 경로가 멀티배거 신호를 읽으면 즉시 실패.

    소스를 직접 본다 — 런타임 테스트는 경로 하나를 놓칠 수 있다.
    """
    src = inspect.getsource(engine.check_stop_loss)
    for bad in ("multi_bagger", "multibagger", "hold_pnl_threshold", "defer"):
        assert bad not in src, (
            f"check_stop_loss 가 '{bad}' 를 참조한다 — 손절 유예는 이 등록의 금지 사항이다. "
            "하방 회피가 오늘 유일하게 유의한 축이고, 손절이 그것을 잡는 장치다."
        )


def test_deferred_holding_still_stops_out():
    """신호가 켜져 있어도 손절은 정상 발동해야 한다."""
    h = _holding(hold_days=400, unrealized_pnl_pct=120.0,
                 buy_price=10000.0, current_price=5000.0, highest_price=20000.0)
    assert detect_hold_pnl_threshold(h).get("triggered") is True, "전제: 신호가 켜진 상태"
    hit, reason = engine.check_stop_loss(h)
    assert hit is True, f"신호가 켜졌다고 손절이 막혔다 — {reason}"


# ── 유예 동작 ──────────────────────────────────────────────────────

def test_first_target_is_deferred_when_signal_fires():
    pf = _pf()
    h = _holding(hold_days=400, unrealized_pnl_pct=120.0)
    res = engine.check_partial_exit(pf, h, [])
    ids = [r.get("target_id") for r in res]
    assert "target_1" not in ids, "신호가 켜졌는데 첫 익절이 실행됐다"
    assert h.get("multibagger_defer"), "유예 사실이 자기신고되지 않았다"


def test_second_target_is_not_deferred():
    """🚨 유예는 **한 단계**다. 전량 보유 유예는 이 등록 밖이다."""
    pf = _pf()
    h = _holding(hold_days=400, unrealized_pnl_pct=120.0)
    res = engine.check_partial_exit(pf, h, [])
    assert "target_2" in [r.get("target_id") for r in res], "target_2 까지 막히면 과잉 개입"


def test_no_defer_when_signal_is_off():
    """실측 기준선(보유 42일·+25.1%)에서는 유예가 없어야 한다."""
    pf = _pf()
    h = _holding(hold_days=42, unrealized_pnl_pct=25.1)
    res = engine.check_partial_exit(pf, h, [])
    assert "target_1" in [r.get("target_id") for r in res], "미발동인데 익절이 막혔다"
    assert not h.get("multibagger_defer")


def test_signal_failure_is_fail_open():
    """신호 평가가 깨져도 익절은 계속돼야 한다 (fail-open)."""
    pf = _pf()
    h = _holding(hold_days="깨진값", unrealized_pnl_pct=None)
    res = engine.check_partial_exit(pf, h, [])
    assert "target_1" in [r.get("target_id") for r in res], "신호 결측이 익절을 막았다"


def test_defer_is_self_reported_with_basis():
    """RULE 12 — 왜 안 팔았는지가 산출물에 남아야 사후 감사가 된다."""
    pf = _pf()
    h = _holding(hold_days=400, unrealized_pnl_pct=120.0)
    engine.check_partial_exit(pf, h, [])
    d = h.get("multibagger_defer") or {}
    assert d.get("target_deferred") == "target_1"
    assert d.get("reason") and d.get("basis") and d.get("at")


# 🚨 임계 값(180일/+50%)은 이 파일에 고정하지 않는다 — 정당한 재등록까지 막지 않기 위해.
#   위 테스트들은 전부 "신호가 켜졌다/꺼졌다" 라는 **동작**만 보고 값을 단정하지 않는다.
