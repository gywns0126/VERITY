# -*- coding: utf-8 -*-
"""소수량 포지션 익절 경로 (PREREG_SMALL_QTY_EXIT_2026_08_11 §2-1).

핵심: trailing_active 는 **가격 도달** 기준이다. 체결 여부에 묶으면 1주 포지션이
영구 미활성이 되어 이익 확정 경로가 0개가 된다.
"""
from api.vams.engine import check_partial_exit


def _holding(qty, price, buy=100.0):
    return {
        "ticker": "TEST", "name": "테스트", "currency": "KRW",
        "quantity": qty, "buy_price": buy, "current_price": price,
        "total_cost": buy * qty, "highest_price": price,
        "trailing_active": False, "exit_history": [], "realized_pnl_partial": 0,
        "exit_targets": {
            "target_1": {"price": 150.0, "r_multiple": 1.0, "exit_pct": 50.0},
            "target_2": {"price": 200.0, "r_multiple": 2.0, "exit_pct": 30.0},
            "target_3": {"method": "trailing_stop"},
        },
    }


def _pf(h):
    return {"vams": {"cash": 1_000_000.0, "holdings": [h], "total_asset": 5_000_000.0,
                     "total_realized_pnl": 0, "tier_pnl": {}}}


def test_single_share_activates_trailing_on_price_reach():
    """1주 — 분할은 불가하지만 target_2 가격 도달 시 트레일링은 켜져야 한다."""
    h = _holding(qty=1, price=210.0)          # target_2(200) 초과
    check_partial_exit(_pf(h), h, [], None)
    assert h["trailing_active"] is True, "1주 포지션의 유일한 이익 확정 경로다"
    # 분할 자체는 여전히 불가 — 감사 기록만
    assert any(x.get("status") == "skipped_too_small" for x in h["exit_history"])
    assert h["quantity"] == 1


def test_single_share_activates_at_first_reachable_profit_target():
    h = _holding(qty=1, price=160.0)          # target_1 초과, target_2 미달
    check_partial_exit(_pf(h), h, [], None)
    assert h["trailing_active"] is True
    assert h["quantity"] == 1


def test_normal_qty_still_executes_and_activates():
    h = _holding(qty=10, price=210.0)
    check_partial_exit(_pf(h), h, [], None)
    assert h["trailing_active"] is True
    assert any(x.get("status") == "executed" for x in h["exit_history"])
    assert h["quantity"] < 10                 # 실제로 팔렸다


def test_three_shares_target2_skip_still_activates():
    """3주 — target_2 는 floor(3×0.3)=0 이라 skip 되지만 활성은 돼야 한다(NEM 실사례)."""
    h = _holding(qty=3, price=210.0)
    check_partial_exit(_pf(h), h, [], None)
    assert h["trailing_active"] is True


def test_trail_pct_removed_from_plan():
    """죽은 파라미터 제거 (§2-2) — 값 변경이 아니라 산출물에서 뺀 것."""
    import inspect

    from api import trade_planner
    src = inspect.getsource(trade_planner)
    assert '"trail_pct": _cfg.R_MULTIPLE_TRAIL_PCT' not in src
