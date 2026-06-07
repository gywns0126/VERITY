"""Hard Floor 룰 단위 테스트 (Phase 2-A)."""
from __future__ import annotations

from api.analyzers.hard_floor import (
    apply_hard_floor,
    filter_hard_floor,
    is_kr_preferred,
    is_kr_foreign,
    is_spac,
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


# ── Stage 1 확장 (2026-06-07) ──

_GOOD = {"market_cap": 100_000_000_000, "avg_trading_value_30d": 5_000_000_000}


class TestHelperPredicates:
    def test_preferred_detection(self):
        assert is_kr_preferred("005935") is True   # 구형 우선주
        assert is_kr_preferred("005930") is False  # 보통주
        assert is_kr_preferred("047040") is False  # 대우건설 (이름 '우' 보통주, 끝자리 0)
        assert is_kr_preferred("") is False        # 빈 ticker graceful

    def test_foreign_detection(self):
        assert is_kr_foreign("900110") is True     # 외국주권 (첫자리 9)
        assert is_kr_foreign("005930") is False
        assert is_kr_foreign("") is False

    def test_spac_detection(self):
        assert is_spac("하나금융25호스팩") is True
        assert is_spac("미래에셋대우 기업인수목적") is True
        assert is_spac("삼성전자") is False
        assert is_spac("") is False


class TestRule4Preferred:
    def test_kr_preferred_cut(self):
        s = {"currency": "KRW", "ticker": "005935", "name": "삼성전자우", **_GOOD}
        apply_hard_floor(s)
        assert s["hard_floor_metadata"]["passes"] is False
        assert any("preferred" in r for r in s["hard_floor_metadata"]["reasons"])

    def test_kr_common_passes(self):
        s = {"currency": "KRW", "ticker": "005930", "name": "삼성전자", **_GOOD}
        apply_hard_floor(s)
        assert s["hard_floor_metadata"]["passes"] is True

    def test_us_ticker_not_preferred_filtered(self):
        # US 심볼은 끝자리 규칙 미적용 (BRK-B 류 정상 통과)
        s = {"currency": "USD", "ticker": "BRK-B", "name": "Berkshire",
             "market_cap": 900_000_000_000, "avg_trading_value_30d": 500_000_000}
        apply_hard_floor(s)
        assert s["hard_floor_metadata"]["passes"] is True


class TestRule5Foreign:
    def test_kr_foreign_cut(self):
        s = {"currency": "KRW", "ticker": "900110", "name": "이스트아시아홀딩스", **_GOOD}
        apply_hard_floor(s)
        assert s["hard_floor_metadata"]["passes"] is False
        assert any("foreign" in r for r in s["hard_floor_metadata"]["reasons"])


class TestRule6Spac:
    def test_spac_cut(self):
        s = {"currency": "KRW", "ticker": "123450", "name": "엔에이치스팩30호", **_GOOD}
        apply_hard_floor(s)
        assert s["hard_floor_metadata"]["passes"] is False
        assert any("spac" in r for r in s["hard_floor_metadata"]["reasons"])


class TestStructuralOverridesCore:
    def test_core_preferred_still_cut(self):
        # 구조적 제외는 코어도 적용 (보통주 아닌 instrument)
        s = {"currency": "KRW", "is_core": True, "ticker": "005935", "name": "삼성전자우", **_GOOD}
        apply_hard_floor(s)
        assert s["hard_floor_metadata"]["passes"] is False

    def test_core_common_still_immune_to_quality(self):
        # 보통주 코어 = 품질 floor 면제 유지 (회귀 방지)
        s = {"currency": "KRW", "is_core": True, "ticker": "005930", "name": "삼성전자",
             "market_cap": 100_000_000, "avg_trading_value_30d": 50_000_000}
        apply_hard_floor(s)
        assert s["hard_floor_metadata"]["passes"] is True


class TestUsThresholdUpdate:
    def test_us_cap_below_500m_now_cut(self):
        # 옛 $100M~신 $500M 구간 = 이제 cut
        s = {"currency": "USD", "ticker": "XYZ", "name": "Mid", "market_cap": 300_000_000,
             "avg_trading_value_30d": 50_000_000}
        apply_hard_floor(s)
        assert s["hard_floor_metadata"]["passes"] is False

    def test_us_tv_below_10m_now_cut(self):
        # 옛 $1M~신 $10M 구간 = 이제 cut
        s = {"currency": "USD", "ticker": "XYZ", "name": "Thin", "market_cap": 5_000_000_000,
             "avg_trading_value_30d": 5_000_000}
        apply_hard_floor(s)
        assert s["hard_floor_metadata"]["passes"] is False

    def test_us_above_both_passes(self):
        s = {"currency": "USD", "ticker": "XYZ", "name": "Liquid", "market_cap": 600_000_000,
             "avg_trading_value_30d": 12_000_000}
        apply_hard_floor(s)
        assert s["hard_floor_metadata"]["passes"] is True
