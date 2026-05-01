"""Hard Floor 룰 단위 테스트 (Phase 2-A)."""
from __future__ import annotations

from api.analyzers.hard_floor import (
    apply_hard_floor,
    filter_hard_floor,
    HARD_FLOOR_MIN_MARKET_CAP_KR,
    HARD_FLOOR_MIN_MARKET_CAP_US,
    HARD_FLOOR_MIN_TRADING_VALUE_KR,
    HARD_FLOOR_MIN_TRADING_VALUE_US,
)


class TestRule1Penny:
    def test_kr_penny_cut(self):
        s = {"currency": "KRW", "market_cap": 1_000_000_000, "avg_trading_value_30d": 200_000_000}
        apply_hard_floor(s)
        assert s["hard_floor_metadata"]["passes"] is False
        assert any("penny_stock" in r for r in s["hard_floor_metadata"]["reasons"])

    def test_kr_penny_at_threshold_passes(self):
        s = {"currency": "KRW", "market_cap": HARD_FLOOR_MIN_MARKET_CAP_KR,
             "avg_trading_value_30d": HARD_FLOOR_MIN_TRADING_VALUE_KR}
        apply_hard_floor(s)
        assert s["hard_floor_metadata"]["passes"] is True

    def test_us_penny_cut(self):
        s = {"currency": "USD", "market_cap": 50_000_000, "avg_trading_value_30d": 5_000_000}
        apply_hard_floor(s)
        assert s["hard_floor_metadata"]["passes"] is False


class TestRule2Alert:
    def test_managed_stock_cut(self):
        s = {"currency": "KRW", "market_cap": 100_000_000_000,
             "avg_trading_value_30d": 5_000_000_000, "is_managed": True, "sect_tp": "관리종목"}
        apply_hard_floor(s)
        assert s["hard_floor_metadata"]["passes"] is False
        assert any("managed" in r for r in s["hard_floor_metadata"]["reasons"])

    def test_suspended_cut(self):
        s = {"currency": "KRW", "market_cap": 100_000_000_000,
             "avg_trading_value_30d": 5_000_000_000, "is_suspended": True}
        apply_hard_floor(s)
        assert s["hard_floor_metadata"]["passes"] is False
        assert any("suspended" in r for r in s["hard_floor_metadata"]["reasons"])


class TestRule3LowTradingValue:
    def test_kr_low_tv_cut(self):
        s = {"currency": "KRW", "market_cap": 100_000_000_000,
             "avg_trading_value_30d": 50_000_000}
        apply_hard_floor(s)
        assert s["hard_floor_metadata"]["passes"] is False
        assert any("low_trading_value" in r for r in s["hard_floor_metadata"]["reasons"])

    def test_us_low_tv_cut(self):
        s = {"currency": "USD", "market_cap": 5_000_000_000,
             "avg_trading_value_30d": 500_000}
        apply_hard_floor(s)
        assert s["hard_floor_metadata"]["passes"] is False


class TestCoreImmunity:
    def test_core_penny_immune(self):
        s = {"currency": "KRW", "is_core": True, "market_cap": 100_000_000,
             "avg_trading_value_30d": 50_000_000}
        apply_hard_floor(s)
        assert s["hard_floor_metadata"]["passes"] is True
        assert "core_immune" in s["hard_floor_metadata"]["reasons"]

    def test_core_managed_immune(self):
        s = {"currency": "KRW", "is_core": True, "market_cap": 100_000_000_000,
             "avg_trading_value_30d": 5_000_000_000, "is_managed": True}
        apply_hard_floor(s)
        assert s["hard_floor_metadata"]["passes"] is True

    def test_core_suspended_NOT_immune(self):
        # 거래정지는 코어라도 cut (안전 우선)
        s = {"currency": "KRW", "is_core": True, "market_cap": 100_000_000_000,
             "avg_trading_value_30d": 5_000_000_000, "is_suspended": True}
        apply_hard_floor(s)
        assert s["hard_floor_metadata"]["passes"] is False


class TestFilterHelper:
    def test_filter_keeps_passing_only(self):
        stocks = [
            {"currency": "KRW", "market_cap": 100_000_000_000, "avg_trading_value_30d": 5_000_000_000},
            {"currency": "KRW", "market_cap": 1_000_000, "avg_trading_value_30d": 10_000},  # cut
            {"currency": "USD", "market_cap": 50_000_000, "avg_trading_value_30d": 500_000},  # cut
        ]
        result = filter_hard_floor(stocks)
        assert len(result) == 1
        assert result[0]["market_cap"] == 100_000_000_000

    def test_metadata_includes_applied_rules(self):
        s = {"currency": "KRW", "market_cap": 1_000_000_000, "avg_trading_value_30d": 50_000_000}
        apply_hard_floor(s)
        meta = s["hard_floor_metadata"]
        assert "rule_1_penny_stock" in meta["applied_rules"]
        assert "rule_2_alert_status" in meta["applied_rules"]
        assert "rule_3_low_trading_value" in meta["applied_rules"]
        assert "computed_at" in meta
