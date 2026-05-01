"""R-multiple 기반 부분 익절 — Phase 1.2 단위 테스트."""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from api.trade_planner import build_trade_plan_v0
from api.vams.engine import (
    check_partial_exit,
    check_stop_loss,
    execute_partial_sell,
)


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────

def _stock_for_plan(price=100_000, atr_14d=2_000, ma20=None, bb_lower=None, bb_upper=None, rsi=40):
    """trade_plan 산출용 stock dict."""
    return {
        "price": price,
        "name": "테스트",
        "currency": "KRW",
        "technical": {
            "atr_14d": atr_14d,
            "bb_lower": bb_lower if bb_lower is not None else price * 0.95,
            "bb_upper": bb_upper if bb_upper is not None else price * 1.05,
            "ma20": ma20 if ma20 is not None else price,
            "rsi": rsi,
        },
    }


def _make_holding(buy_price=100_000, current_price=100_000, quantity=100, trade_plan=None):
    """VAMS holding fixture — exit_targets 부착."""
    plan = trade_plan or build_trade_plan_v0(
        _stock_for_plan(buy_price), {"recommendation": "BUY"}
    )
    return {
        "ticker": "005930",
        "name": "테스트",
        "currency": "KRW",
        "buy_price": buy_price,
        "buy_price_original": buy_price,
        "current_price": current_price,
        "highest_price": max(buy_price, current_price),
        "quantity": quantity,
        "total_cost": buy_price * quantity,
        "buy_date": datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d"),
        "exit_targets": plan["exit_targets"],
        "exit_history": [],
        "trailing_active": False,
        "realized_pnl_partial": 0,
        "stop_loss_pct_individual": plan["stop_loss"]["stop_loss_pct"],
        "asset_class": "kr_equity",
    }


def _portfolio():
    return {"vams": {"cash": 0, "holdings": [], "total_realized_pnl": 0}}


def _profile():
    return {
        "stop_loss_pct": -8.0, "trailing_stop_pct": 5.0,
        "max_hold_days": 21, "impact_coeff_bps": 20,
    }


# ─────────────────────────────────────────────────────────────────────
# trade_planner exit_targets
# ─────────────────────────────────────────────────────────────────────

class TestExitTargetsBuild:
    def test_targets_present_for_buy(self):
        plan = build_trade_plan_v0(_stock_for_plan(), {"recommendation": "BUY"})
        et = plan["exit_targets"]
        assert et is not None
        assert "target_1" in et
        assert "target_2" in et
        assert "target_3" in et

    def test_target_1_at_one_r(self):
        # price=100,000 / ATR 2,000 / mult 2.5 → stop=95,000 → 1R=5,000
        # target_1 price = 100,000 + 5,000 = 105,000
        plan = build_trade_plan_v0(_stock_for_plan(), {"recommendation": "BUY"})
        assert plan["exit_targets"]["target_1"]["price"] == 105_000
        assert plan["exit_targets"]["target_1"]["r_multiple"] == 1.0
        assert plan["exit_targets"]["target_1"]["exit_pct"] == 50

    def test_target_2_at_two_r(self):
        plan = build_trade_plan_v0(_stock_for_plan(), {"recommendation": "BUY"})
        # 1R=5,000 → 2R=10,000 → target_2 = 110,000
        assert plan["exit_targets"]["target_2"]["price"] == 110_000
        assert plan["exit_targets"]["target_2"]["r_multiple"] == 2.0
        assert plan["exit_targets"]["target_2"]["exit_pct"] == 30

    def test_target_3_trailing(self):
        plan = build_trade_plan_v0(_stock_for_plan(), {"recommendation": "BUY"})
        t3 = plan["exit_targets"]["target_3"]
        assert t3["method"] == "trailing_stop"
        assert t3["trail_pct"] == 5.0

    def test_deprecated_exit_target_synced(self):
        plan = build_trade_plan_v0(_stock_for_plan(), {"recommendation": "BUY"})
        # 단일 exit_target.price 는 target_1.price 와 동일 (backward compat)
        assert plan["exit_target"]["price"] == plan["exit_targets"]["target_1"]["price"]
        assert plan["exit_target"]["deprecated"] is True


# ─────────────────────────────────────────────────────────────────────
# check_partial_exit — 부분 청산 동작
# ─────────────────────────────────────────────────────────────────────

class TestPartialExitTrigger:
    def test_target_1_at_plus_1r_triggers_50pct(self):
        # 진입 100,000원 / 100주 / target_1=105,000원
        # 현재가 105,000원 → 50주 청산
        h = _make_holding(buy_price=100_000, current_price=105_000, quantity=100)
        portfolio = _portfolio()
        portfolio["vams"]["holdings"].append(h)
        history = []

        results = check_partial_exit(portfolio, h, history, profile=_profile())
        assert len(results) == 1
        assert results[0]["target_id"] == "target_1"
        assert results[0]["sold_qty"] == 50
        assert h["quantity"] == 50  # 잔여 50주
        assert any(e["target_id"] == "target_1" for e in h["exit_history"])

    def test_target_2_after_target_1_triggers_30pct(self):
        # target_1 이미 실행 (50주 매도) → 잔여 50주
        # 현재가 110,000원 (+2R) → 50주 × 30% = 15주 청산
        h = _make_holding(buy_price=100_000, current_price=110_000, quantity=100)
        portfolio = _portfolio()
        portfolio["vams"]["holdings"].append(h)
        history = []

        # 1R 도달 → target_1 실행
        h["current_price"] = 105_000
        check_partial_exit(portfolio, h, history, profile=_profile())
        assert h["quantity"] == 50

        # 2R 도달 → target_2 실행
        h["current_price"] = 110_000
        results = check_partial_exit(portfolio, h, history, profile=_profile())
        # target_1 은 이미 실행 — 재발동 X. target_2 만 실행.
        assert any(r["target_id"] == "target_2" for r in results)
        # 50주 × 30% = 15주
        target_2_result = next(r for r in results if r["target_id"] == "target_2")
        assert target_2_result["sold_qty"] == 15
        assert h["quantity"] == 35  # 잔여 35주
        assert h["trailing_active"] is True  # +2R 도달 → trailing 활성

    def test_no_partial_below_target_1(self):
        # 현재가 < target_1 → 청산 X
        h = _make_holding(buy_price=100_000, current_price=104_999, quantity=100)
        portfolio = _portfolio()
        portfolio["vams"]["holdings"].append(h)
        history = []
        results = check_partial_exit(portfolio, h, history, profile=_profile())
        assert results == []
        assert h["quantity"] == 100  # 변경 없음

    def test_target_1_executed_only_once(self):
        # target_1 이미 실행 후 같은 cycle 재호출 → 추가 실행 X
        h = _make_holding(buy_price=100_000, current_price=105_000, quantity=100)
        portfolio = _portfolio()
        portfolio["vams"]["holdings"].append(h)
        history = []
        check_partial_exit(portfolio, h, history, profile=_profile())
        results = check_partial_exit(portfolio, h, history, profile=_profile())
        assert results == []
        # exit_history 에 target_1 한 번만
        executed = [e for e in h["exit_history"] if e.get("status") == "executed"]
        assert len([e for e in executed if e["target_id"] == "target_1"]) == 1


# ─────────────────────────────────────────────────────────────────────
# 손절 vs 부분 익절 분기
# ─────────────────────────────────────────────────────────────────────

class TestStopVsPartial:
    def test_minus_1r_triggers_stop_no_partial(self):
        # ATR 2,000 / mult 2.5 → stop=-5%
        # 현재가 95,000 (≤ -5%) → 손절. 부분 익절 호출은 결과 없음.
        h = _make_holding(buy_price=100_000, current_price=95_000, quantity=100)
        should_sell, reason = check_stop_loss(h, _profile())
        assert should_sell is True
        assert "individual_atr" in reason or "profile_cap" in reason

    def test_after_target_1_drop_to_atr_stop_holds(self):
        # target_1 실행 (50주 청산) 후 가격 하락
        # 잔여 50주는 ATR stop 까지 보유 (트레일링은 +2R 후만)
        h = _make_holding(buy_price=100_000, current_price=105_000, quantity=100)
        portfolio = _portfolio()
        portfolio["vams"]["holdings"].append(h)
        history = []
        check_partial_exit(portfolio, h, history, profile=_profile())
        assert h["quantity"] == 50

        # 가격 하락 — highest=105,000 / 현재 102,000 (3% 하락)
        # trailing_active=False (target_2 아직) → trailing 발동 안 함
        h["current_price"] = 102_000
        h["highest_price"] = 105_000
        should_sell, reason = check_stop_loss(h, _profile())
        # 102,000 / 100,000 = +2% > -5% (ATR stop) → 손절 발동 안 함
        assert should_sell is False

    def test_trailing_inactive_before_target_2(self):
        # target_1 실행 후 highest=108,000 / 현재 102,000 (~5.5% 하락)
        # trailing_active=False → 손절 X
        h = _make_holding(buy_price=100_000, current_price=105_000, quantity=100)
        portfolio = _portfolio()
        portfolio["vams"]["holdings"].append(h)
        history = []
        check_partial_exit(portfolio, h, history, profile=_profile())

        h["highest_price"] = 108_000
        h["current_price"] = 102_000  # 고점 대비 -5.6%
        assert h["trailing_active"] is False
        should_sell, _ = check_stop_loss(h, _profile())
        # 트레일링 비활성 + ATR stop 95,000 미도달 → False
        assert should_sell is False

    def test_trailing_active_after_target_2(self):
        # target_1 + target_2 실행 후 trailing_active=True
        # 잔여 35주에 트레일링 적용
        h = _make_holding(buy_price=100_000, current_price=110_000, quantity=100)
        portfolio = _portfolio()
        portfolio["vams"]["holdings"].append(h)
        history = []
        # target_1 도달
        h["current_price"] = 105_000
        check_partial_exit(portfolio, h, history, profile=_profile())
        # target_2 도달 → trailing_active=True
        h["current_price"] = 110_000
        h["highest_price"] = 110_000
        check_partial_exit(portfolio, h, history, profile=_profile())
        assert h["trailing_active"] is True

        # 고점 110,000 / 현재 104,500 → -5% (trailing 임계 초과)
        h["highest_price"] = 110_000
        h["current_price"] = 104_500
        should_sell, reason = check_stop_loss(h, _profile())
        assert should_sell is True
        assert "트레일링" in reason


# ─────────────────────────────────────────────────────────────────────
# Backward compat — exit_targets 없는 legacy holding
# ─────────────────────────────────────────────────────────────────────

class TestLegacyHoldingCompat:
    def test_legacy_holding_no_partial_no_change(self):
        # exit_targets 없는 holding → check_partial_exit 무시
        h = {
            "ticker": "005930", "name": "Legacy",
            "buy_price": 100_000, "current_price": 110_000,
            "highest_price": 110_000, "quantity": 100,
            "total_cost": 10_000_000,
            "buy_date": datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d"),
            "currency": "KRW",
        }
        portfolio = _portfolio()
        portfolio["vams"]["holdings"].append(h)
        history = []
        results = check_partial_exit(portfolio, h, history, profile=_profile())
        assert results == []
        assert h["quantity"] == 100  # 변경 없음

    def test_legacy_holding_trailing_always_on(self):
        # legacy holding (exit_targets 없음) → 트레일링 즉시 작동 (기존 동작 유지)
        h = {
            "ticker": "005930", "name": "Legacy",
            "buy_price": 100_000, "current_price": 102_000,
            "highest_price": 110_000, "quantity": 100,
            "buy_date": datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d"),
            "currency": "KRW",
        }
        # highest 110,000 / current 102,000 → -7.27% > 5% trailing
        should_sell, reason = check_stop_loss(h, _profile())
        assert should_sell is True
        assert "트레일링" in reason
