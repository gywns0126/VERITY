"""AutoTrader 주문 계획 + 안전장치 + 실행 테스트 (MockBroker 기반, 네트워크 0)."""
from datetime import datetime, timedelta, timezone

import pytest

from api.trading.auto_trader import (
    TradeOrder,
    activate_killswitch,
    apply_safety_limits,
    deactivate_killswitch,
    execute,
    is_killswitch_active,
    plan_orders,
    run_auto_trade_cycle,
)
from api.trading.mock_kis_broker import MockHolding, MockKISBroker

KST = timezone(timedelta(hours=9))


def _trading_hour(now=None):
    """한국 정규장 안의 시각 하나 만들어줌 (월-금 11:00)."""
    n = now or datetime.now(KST)
    d = n
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d.replace(hour=11, minute=0, second=0, microsecond=0)


def _portfolio(recs=None, holdings=None, fx=1350):
    return {
        "macro": {"usd_krw": {"value": fx}},
        "recommendations": recs or [],
        "vams": {"holdings": holdings or []},
    }


def _rec(ticker="005930", action="STRONG_BUY", safety=80, t_score=75,
         price=70000, rec="STRONG_BUY", currency="KRW", name=None):
    return {
        "ticker": ticker, "name": name or ticker,
        "recommendation": rec, "safety_score": safety,
        "price": price, "currency": currency,
        "timing": {"action": action, "timing_score": t_score, "reasons": ["r1"]},
    }


class TestPlanOrders:
    def test_strong_buy_creates_order(self, monkeypatch):
        monkeypatch.setenv("AUTO_TRADE_MAX_PER_STOCK_KRW", "300000")
        broker = MockKISBroker(initial_cash=10_000_000,
                               price_map={"005930": 70000})
        portfolio = _portfolio(recs=[_rec()])

        orders, blocks = plan_orders(portfolio, broker)

        assert len(orders) == 1
        assert orders[0].side == "BUY"
        assert orders[0].ticker == "005930"
        assert orders[0].qty == 4
        assert blocks == []

    def test_low_safety_blocks_buy(self, monkeypatch):
        monkeypatch.setenv("AUTO_TRADE_MIN_SAFETY_SCORE", "70")
        broker = MockKISBroker(price_map={"005930": 70000})
        portfolio = _portfolio(recs=[_rec(safety=50)])
        orders, blocks = plan_orders(portfolio, broker)
        assert orders == []
        assert any("안심점수" in b["reason"] for b in blocks)

    def test_low_timing_blocks_buy(self, monkeypatch):
        monkeypatch.setenv("AUTO_TRADE_MIN_TIMING_SCORE", "70")
        broker = MockKISBroker(price_map={"005930": 70000})
        portfolio = _portfolio(recs=[_rec(t_score=55)])
        orders, blocks = plan_orders(portfolio, broker)
        assert orders == []
        assert any("타이밍점수" in b["reason"] for b in blocks)

    def test_held_stock_sell_signal_creates_sell(self, monkeypatch):
        broker = MockKISBroker(
            initial_cash=0, price_map={"005930": 72000},
        )
        broker.holdings_kr["005930"] = MockHolding(
            ticker="005930", qty=10, avg_price=70000, currency="KRW", market="KR",
        )
        portfolio = _portfolio(
            recs=[_rec(action="STRONG_SELL", rec="WATCH")],
            holdings=[{"ticker": "005930", "currency": "KRW"}],
        )
        orders, _ = plan_orders(portfolio, broker)
        assert len(orders) == 1
        assert orders[0].side == "SELL"
        assert orders[0].qty == 10

    def test_overseas_blocked_by_default(self):
        broker = MockKISBroker(price_map={"TSLA": 250.0})
        portfolio = _portfolio(recs=[_rec(ticker="TSLA", price=250, currency="USD")])
        orders, blocks = plan_orders(portfolio, broker)
        assert orders == []
        assert any("해외주식" in b["reason"] for b in blocks)

    def test_overseas_allowed_creates_order(self, monkeypatch):
        monkeypatch.setenv("AUTO_TRADE_ALLOW_OVERSEAS", "true")
        monkeypatch.setenv("AUTO_TRADE_MAX_PER_STOCK_KRW", "500000")
        broker = MockKISBroker(initial_cash=10_000_000, price_map={"TSLA": 250.0})
        portfolio = _portfolio(
            recs=[_rec(ticker="TSLA", price=250, currency="USD")],
            fx=1350,
        )
        orders, _ = plan_orders(portfolio, broker)
        assert len(orders) == 1
        assert orders[0].market == "US"

    def test_held_stock_buy_signal_skipped(self):
        broker = MockKISBroker(price_map={"005930": 70000})
        portfolio = _portfolio(
            recs=[_rec()],
            holdings=[{"ticker": "005930", "currency": "KRW"}],
        )
        broker.holdings_kr["005930"] = MockHolding(
            ticker="005930", qty=5, avg_price=65000,
        )
        orders, _ = plan_orders(portfolio, broker)
        assert orders == []


class TestSafetyLimits:
    def test_killswitch_blocks_all(self):
        activate_killswitch()
        assert is_killswitch_active()
        orders = [TradeOrder(side="BUY", ticker="005930", name="삼성", qty=1,
                             price=70000, market="KR")]
        passed, blocks = apply_safety_limits(orders, now=_trading_hour())
        assert passed == []
        assert all("킬스위치" in b["reason"] for b in blocks)
        deactivate_killswitch()

    def test_after_hours_blocks_kr(self, monkeypatch):
        monkeypatch.delenv("AUTO_TRADE_ALLOW_AFTER_HOURS", raising=False)
        night = _trading_hour().replace(hour=20)
        orders = [TradeOrder(side="BUY", ticker="005930", name="삼성", qty=1,
                             price=70000, market="KR")]
        passed, blocks = apply_safety_limits(orders, now=night)
        assert passed == []
        assert any("장외시간" in b["reason"] for b in blocks)

    def test_after_hours_allowed(self, monkeypatch):
        night = _trading_hour().replace(hour=20)
        orders = [TradeOrder(side="BUY", ticker="005930", name="삼성", qty=1,
                             price=70000, market="KR")]
        passed, _ = apply_safety_limits(
            orders, now=night, force_allow_after_hours=True,
        )
        assert len(passed) == 1

    def test_daily_limit_enforced(self, monkeypatch):
        monkeypatch.setenv("AUTO_TRADE_MAX_DAILY_BUY_KRW", "100000")
        orders = [
            TradeOrder(side="BUY", ticker="005930", name="삼성", qty=1,
                       price=70000, market="KR"),
            TradeOrder(side="BUY", ticker="000660", name="SK", qty=1,
                       price=50000, market="KR"),
        ]
        passed, blocks = apply_safety_limits(orders, now=_trading_hour())
        assert len(passed) == 1
        assert any("일일 매수 한도" in b["reason"] for b in blocks)


class TestExecute:
    def test_dry_run_no_actual_order(self):
        broker = MockKISBroker(initial_cash=10_000_000,
                               price_map={"005930": 70000})
        orders = [TradeOrder(side="BUY", ticker="005930", name="삼성", qty=3,
                             price=70000, market="KR")]

        results = execute(orders, broker, dry_run=True)

        assert len(results) == 1
        assert results[0]["status"] == "DRY_RUN"
        assert results[0]["success"] is True
        assert broker.cash == 10_000_000
        assert broker.holdings_kr == {}

    def test_live_mock_fills_order(self):
        broker = MockKISBroker(initial_cash=10_000_000,
                               price_map={"005930": 70000})
        orders = [TradeOrder(side="BUY", ticker="005930", name="삼성", qty=3,
                             price=70000, market="KR")]

        results = execute(orders, broker, dry_run=False)

        assert results[0]["status"] == "FILLED"
        assert broker.cash == 10_000_000 - 70000 * 3
        assert "005930" in broker.holdings_kr
        assert broker.holdings_kr["005930"].qty == 3

    def test_sell_generates_pnl(self):
        broker = MockKISBroker(initial_cash=0, price_map={"005930": 80000})
        broker.holdings_kr["005930"] = MockHolding(
            ticker="005930", qty=10, avg_price=70000,
        )
        orders = [TradeOrder(side="SELL", ticker="005930", name="삼성", qty=10,
                             price=80000, market="KR")]
        execute(orders, broker, dry_run=False)
        assert broker.cash == 80000 * 10
        assert "005930" not in broker.holdings_kr

    def test_history_persisted(self):
        broker = MockKISBroker(initial_cash=10_000_000,
                               price_map={"005930": 70000})
        orders = [TradeOrder(side="BUY", ticker="005930", name="삼성", qty=1,
                             price=70000, market="KR")]
        execute(orders, broker, dry_run=False)
        from api.trading.auto_trader import load_history
        h = load_history()
        assert len(h) == 1
        assert h[0]["ticker"] == "005930"


class TestIntegration:
    def test_full_cycle_master_off(self, monkeypatch):
        monkeypatch.delenv("AUTO_TRADE_ENABLED", raising=False)
        broker = MockKISBroker(initial_cash=10_000_000,
                               price_map={"005930": 70000})
        portfolio = _portfolio(recs=[_rec()])
        result = run_auto_trade_cycle(portfolio, broker=broker)
        assert result["master_enabled"] is False
        assert result["results"] == []

    def test_full_cycle_enabled_dry_run(self, monkeypatch):
        monkeypatch.setenv("AUTO_TRADE_ENABLED", "true")
        monkeypatch.setenv("AUTO_TRADE_DRY_RUN", "true")
        monkeypatch.setenv("AUTO_TRADE_ALLOW_AFTER_HOURS", "true")
        monkeypatch.setenv("AUTO_TRADE_MAX_PER_STOCK_KRW", "300000")
        monkeypatch.setenv("AUTO_TRADE_MAX_DAILY_BUY_KRW", "1000000")
        broker = MockKISBroker(initial_cash=10_000_000,
                               price_map={"005930": 70000})
        portfolio = _portfolio(recs=[_rec()])

        result = run_auto_trade_cycle(portfolio, broker=broker,
                                      now=_trading_hour())

        assert result["master_enabled"] is True
        assert result["dry_run"] is True
        assert len(result["results"]) == 1
        assert result["results"][0]["status"] == "DRY_RUN"
        assert broker.cash == 10_000_000

    def test_full_cycle_live_mock(self, monkeypatch):
        monkeypatch.setenv("AUTO_TRADE_ENABLED", "true")
        monkeypatch.setenv("AUTO_TRADE_DRY_RUN", "false")
        monkeypatch.setenv("AUTO_TRADE_ALLOW_AFTER_HOURS", "true")
        monkeypatch.setenv("AUTO_TRADE_MAX_PER_STOCK_KRW", "300000")
        monkeypatch.setenv("AUTO_TRADE_MAX_DAILY_BUY_KRW", "1000000")
        broker = MockKISBroker(initial_cash=10_000_000,
                               price_map={"005930": 70000})
        portfolio = _portfolio(recs=[_rec()])

        result = run_auto_trade_cycle(portfolio, broker=broker,
                                      now=_trading_hour())

        assert result["dry_run"] is False
        assert len(result["results"]) == 1
        assert result["results"][0]["status"] == "FILLED"
        assert "005930" in broker.holdings_kr
