"""ATR 기반 동적 손절 — Phase 1.1 단위 테스트."""
from __future__ import annotations

import pytest

from api.trade_planner import build_trade_plan_v0
from api.vams.engine import check_stop_loss


# ─────────────────────────────────────────────────────────────────────
# trade_planner.build_trade_plan_v0 — ATR 동적 손절
# ─────────────────────────────────────────────────────────────────────

def _make_stock(price, atr_14d=None, bb_lower=None, bb_upper=None, ma20=None, rsi=40):
    bb_lower = bb_lower if bb_lower is not None else price * 0.95
    bb_upper = bb_upper if bb_upper is not None else price * 1.05
    ma20 = ma20 if ma20 is not None else price
    return {
        "price": price,
        "name": "테스트",
        "currency": "KRW",
        "technical": {
            "atr_14d": atr_14d,
            "bb_lower": bb_lower,
            "bb_upper": bb_upper,
            "ma20": ma20,
            "rsi": rsi,
        },
    }


class TestAtrDynamicStop:
    def test_atr_present_uses_dynamic(self):
        # 가격 100,000원 / ATR 2,000원 / mult 2.5 → 5,000원 거리 = -5%
        stock = _make_stock(100_000, atr_14d=2_000)
        plan = build_trade_plan_v0(stock, {"recommendation": "BUY"})
        sl = plan["stop_loss"]
        assert sl["method"] == "atr_dynamic"
        assert sl["atr_value"] == 2_000
        assert sl["atr_multiplier"] == 2.5
        # ATR 2,000 × 2.5 = 5,000원 거리 → 95,000원
        assert sl["price"] == 95_000
        assert sl["stop_loss_pct"] == pytest.approx(-5.0, abs=0.01)

    def test_atr_absent_uses_fallback(self):
        stock = _make_stock(100_000, atr_14d=None)
        plan = build_trade_plan_v0(stock, {"recommendation": "BUY"})
        sl = plan["stop_loss"]
        assert sl["method"] == "fixed_fallback"
        assert sl["atr_value"] is None
        assert sl["atr_multiplier"] is None
        assert sl["stop_loss_pct"] == -5.0
        # -5% → 95,000원
        assert sl["price"] == 95_000

    def test_atr_zero_uses_fallback(self):
        stock = _make_stock(100_000, atr_14d=0)
        plan = build_trade_plan_v0(stock, {"recommendation": "BUY"})
        assert plan["stop_loss"]["method"] == "fixed_fallback"

    def test_low_volatility_vs_high_volatility(self):
        # 저변동 종목: ATR 1% (1,000원 / 100,000원)
        # 고변동 종목: ATR 5% (5,000원 / 100,000원)
        # → 고변동 종목의 손절 거리가 더 커야 함
        low_vol = _make_stock(100_000, atr_14d=1_000)
        high_vol = _make_stock(100_000, atr_14d=5_000)
        low_plan = build_trade_plan_v0(low_vol, {"recommendation": "BUY"})
        high_plan = build_trade_plan_v0(high_vol, {"recommendation": "BUY"})
        low_distance = 100_000 - low_plan["stop_loss"]["price"]
        high_distance = 100_000 - high_plan["stop_loss"]["price"]
        assert high_distance > low_distance
        # 5배 ATR 차이 → 5배 거리 차이 (선형)
        assert high_distance == pytest.approx(low_distance * 5, rel=0.01)

    def test_us_stock_atr_dynamic(self):
        # USD 종목도 동일 로직 적용
        stock = _make_stock(150.0, atr_14d=3.0)  # 150달러, ATR 3달러 (2%)
        stock["currency"] = "USD"
        plan = build_trade_plan_v0(stock, {"recommendation": "BUY"})
        sl = plan["stop_loss"]
        assert sl["method"] == "atr_dynamic"
        # ATR 3 × 2.5 = 7.5달러 거리 → 142.5 → round(142.5)=142
        assert sl["stop_loss_pct"] == pytest.approx(-5.0, abs=0.1)


# ─────────────────────────────────────────────────────────────────────
# vams.engine.check_stop_loss — individual 우선, 프로파일 상한
# ─────────────────────────────────────────────────────────────────────

def _make_holding(buy_price, current_price, individual_stop_pct=None, days_held=0):
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    buy_date = (datetime.now(ZoneInfo("Asia/Seoul")) - timedelta(days=days_held)).strftime("%Y-%m-%d")
    return {
        "buy_price": buy_price,
        "current_price": current_price,
        "highest_price": max(buy_price, current_price),
        "buy_date": buy_date,
        "stop_loss_pct_individual": individual_stop_pct,
    }


class TestVamsStopLossIndividual:
    def test_individual_present_uses_it(self):
        # individual -3% (보수적) vs profile -5% → individual 더 빨리 트리거
        # current = -4% → individual=-3% 도달, profile=-5% 미도달 → 매도
        holding = _make_holding(100_000, 96_000, individual_stop_pct=-3.0)
        profile = {"stop_loss_pct": -5.0, "trailing_stop_pct": 3.0, "max_hold_days": 14}
        should_sell, reason = check_stop_loss(holding, profile)
        assert should_sell is True
        assert "individual_atr" in reason

    def test_profile_cap_when_individual_more_loose(self):
        # individual -10% vs profile -8% → max(-8, -10) = -8 (profile 더 보수적)
        # current -9% → profile=-8% 도달
        holding = _make_holding(100_000, 91_000, individual_stop_pct=-10.0)
        profile = {"stop_loss_pct": -8.0, "trailing_stop_pct": 5.0, "max_hold_days": 21}
        should_sell, reason = check_stop_loss(holding, profile)
        assert should_sell is True
        assert "profile_cap" in reason

    def test_individual_loose_no_trigger_at_intermediate_drop(self):
        # individual -10% / profile -8% / 현재 -6% → 둘 다 미도달
        holding = _make_holding(100_000, 94_000, individual_stop_pct=-10.0)
        profile = {"stop_loss_pct": -8.0, "trailing_stop_pct": 5.0, "max_hold_days": 21}
        should_sell, _ = check_stop_loss(holding, profile)
        assert should_sell is False

    def test_no_individual_falls_back_to_profile(self):
        holding = _make_holding(100_000, 94_000, individual_stop_pct=None)
        profile = {"stop_loss_pct": -5.0, "trailing_stop_pct": 3.0, "max_hold_days": 14}
        should_sell, reason = check_stop_loss(holding, profile)
        # current = -6% → profile -5% 트리거
        assert should_sell is True
        assert "profile_default" in reason

    def test_no_trigger_when_within_threshold(self):
        # individual -8% / current -3% → 미도달
        holding = _make_holding(100_000, 97_000, individual_stop_pct=-8.0)
        profile = {"stop_loss_pct": -5.0, "trailing_stop_pct": 3.0, "max_hold_days": 14}
        should_sell, _ = check_stop_loss(holding, profile)
        # max(-5, -8) = -5, current -3 미도달
        assert should_sell is False
