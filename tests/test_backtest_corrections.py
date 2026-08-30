"""Sprint 11 결함 1 — backtest 보정 단위 테스트.

slippage tier + survivorship + tx_cost 산식이 의도대로 적용되는지 확인.
"""
from __future__ import annotations

from api.intelligence.backtest_archive import (
    DELISTED_RETURN_PCT,
    TX_COST_PCT,
    _slippage_pct,
)


def test_verification_report_exposes_sample_and_ci(monkeypatch, tmp_path):
    import api.intelligence.backtest_archive as mod

    monkeypatch.setattr(mod, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(
        mod,
        "evaluate_past_recommendations",
        lambda: {
            "periods": {
                "7d": {"hit_rate": 50.0, "avg_return": 1.0, "sharpe": 0.2, "total_recs": 2, "hits": 1},
                "14d": {"hit_rate": 75.0, "avg_return": 2.0, "sharpe": 0.4, "total_recs": 4, "hits": 3},
                "30d": {"hit_rate": None, "avg_return": None, "sharpe": None, "total_recs": 0, "hits": 0},
            },
            "_corrections_meta": {},
        },
    )
    report = mod.generate_verification_report()
    perf = report["performance"]
    assert perf["hit_rate_14d"] == 75.0
    assert perf["sample_14d"] == 4
    assert perf["hits_14d"] == 3
    assert perf["hit_rate_14d_ci95"] == [30.1, 95.4]
    assert perf["hit_rate_30d_ci95"] is None


class TestSlippageTier:
    def test_large_cap(self):
        # 시총 10조+ → 0.1% (KOSPI 대형)
        assert _slippage_pct(10_000_000_000_000) == 0.1
        assert _slippage_pct(50_000_000_000_000) == 0.1

    def test_mid_cap(self):
        # 시총 1-10조 → 0.3% (KOSDAQ 중형)
        assert _slippage_pct(1_000_000_000_000) == 0.3
        assert _slippage_pct(5_000_000_000_000) == 0.3
        assert _slippage_pct(9_999_999_999_999) == 0.3

    def test_small_cap(self):
        # 시총 1조 미만 → 0.7% (소형주)
        assert _slippage_pct(999_999_999_999) == 0.7
        assert _slippage_pct(100_000_000_000) == 0.7

    def test_unknown_or_zero(self):
        # 시총 미상 → 보수적 0.7%
        assert _slippage_pct(None) == 0.7
        assert _slippage_pct(0) == 0.7
        assert _slippage_pct(-1) == 0.7


class TestConstants:
    def test_tx_cost_round_trip(self):
        # VAMS 수수료 0.015% × 2 왕복 = 0.03%
        assert TX_COST_PCT == 0.03

    def test_delisted_conservative(self):
        # 상장폐지 보수 처리 — distress midpoint
        # 실제 분포는 -30 ~ -100% (관리종목→상폐 시점 따라)
        assert DELISTED_RETURN_PCT == -50.0
        assert -100 < DELISTED_RETURN_PCT < 0


class TestNetReturnCalculation:
    """gross_ret - slippage - tx_cost = net_ret 산식 검증."""

    def test_large_cap_5pct_gain(self):
        # 시총 10조+ 종목 5% 상승 → net = 5 - 0.1 - 0.03 = 4.87%
        gross = 5.0
        slip = _slippage_pct(10_000_000_000_000)
        net = gross - slip - TX_COST_PCT
        assert net == 4.87

    def test_small_cap_5pct_gain(self):
        # 시총 1조 미만 5% 상승 → net = 5 - 0.7 - 0.03 = 4.27%
        gross = 5.0
        slip = _slippage_pct(500_000_000_000)
        net = gross - slip - TX_COST_PCT
        assert abs(net - 4.27) < 0.001

    def test_breakeven_eaten_by_costs(self):
        # 0.5% 상승 (소형주) → net = 0.5 - 0.7 - 0.03 = -0.23% (실제로는 손실)
        gross = 0.5
        slip = _slippage_pct(500_000_000_000)
        net = gross - slip - TX_COST_PCT
        assert net < 0  # 비용에 먹힘

    def test_net_always_lower_than_gross(self):
        for gross in [-10.0, -1.0, 0.0, 1.0, 5.0, 20.0]:
            for cap in [None, 100_000_000_000, 5_000_000_000_000, 20_000_000_000_000]:
                slip = _slippage_pct(cap)
                net = gross - slip - TX_COST_PCT
                assert net < gross  # 항상 net < gross (보수적)
