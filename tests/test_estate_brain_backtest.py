"""ESTATE Brain V0.2 backtest core — 단위 테스트.

검증 6 그룹:
  ① compute_forward_return_pct (52w 기본 + 끝부분 None)
  ② compute_drop_from_peak_pct (peak→trough 산출)
  ③ validate_cycle_analog (plan 가정 vs 실측 정합 + tolerance)
  ④ detect_unsold_yoy_signal + compute_signal_hit_rate (12M YoY + hit)
  ⑤ compute_ic (Spearman rank, 정량 정합)
  ⑥ compute_quintile_spread (Q5-Q1)
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from api.intelligence import estate_brain_backtest as bt


class TestForwardReturn:
    def test_52w_horizon(self):
        # 100 → 110 (52주 후 +10%)
        series = [{"week": f"2024{wk:02d}", "index": 100 + wk * 0.2}
                  for wk in range(1, 105)]
        out = bt.compute_forward_return_pct(series, horizon_weeks=52)
        # 첫 시점 t=0 (100) → t=52 (100 + 52*0.2 = 110.4) → +10.4%
        assert out[0] == pytest.approx(10.4, abs=0.05)
        # 마지막 52주 None
        assert all(r is None for r in out[-52:])

    def test_zero_first_skipped(self):
        series = [{"week": "202401", "index": 0}, {"week": "202402", "index": 100}]
        out = bt.compute_forward_return_pct(series, horizon_weeks=1)
        assert out[0] is None

    def test_short_series_all_none(self):
        series = [{"week": "202401", "index": 100}]
        assert bt.compute_forward_return_pct(series, horizon_weeks=52) == [None]


class TestDropFromPeak:
    def test_typical_drop(self):
        # 100 → 90 → 110 → 88 (peak 110, trough 88, drop ≈ -20%)
        series = [{"index": v} for v in [100, 90, 110, 100, 88]]
        d = bt.compute_drop_from_peak_pct(series)
        assert d == pytest.approx(-20.0, abs=0.5)

    def test_monotonic_up_zero_drop(self):
        # peak = 마지막 = 110, trough = 첫 = 100 → drop = (100-110)/110 = -9.09%
        series = [{"index": v} for v in [100, 105, 110]]
        d = bt.compute_drop_from_peak_pct(series)
        assert d == pytest.approx(-9.09, abs=0.05)

    def test_empty_returns_none(self):
        assert bt.compute_drop_from_peak_pct([]) is None
        assert bt.compute_drop_from_peak_pct([{"index": 100}]) is None


class TestCycleAnalog:
    PLAN = {
        "Shock-Recovery": -18.2,
        "Debt-Deflation Drag": -12.0,
        "Rate-Shock Rebound": -20.0,
    }

    def test_within_tolerance(self):
        actual = {"1997": -18.5, "2008": -12.5, "2022": -19.0}
        result = bt.validate_cycle_analog(actual, self.PLAN, tolerance_pct=5.0)
        assert all(r["within_tolerance"] for r in result.values())
        assert result["Shock-Recovery"]["diff_pct"] == pytest.approx(-0.3, abs=0.01)

    def test_outside_tolerance(self):
        actual = {"1997": -10.0, "2008": -12.0, "2022": -20.0}  # 1997 너무 큰 차
        result = bt.validate_cycle_analog(actual, self.PLAN, tolerance_pct=5.0)
        assert result["Shock-Recovery"]["within_tolerance"] is False
        assert result["Debt-Deflation Drag"]["within_tolerance"] is True

    def test_unknown_period_skipped(self):
        actual = {"1997": -18.0, "9999": -50.0}
        result = bt.validate_cycle_analog(actual, self.PLAN)
        assert "Shock-Recovery" in result
        assert len(result) == 1

    def test_pattern_missing_in_plan(self):
        actual = {"1997": -18.0}
        plan = {}
        result = bt.validate_cycle_analog(actual, plan)
        assert result == {}


class TestUnsoldSignal:
    def test_yoy_30_pct_threshold_trigger(self):
        series = [{"unsold": 100}] * 12 + [{"unsold": 135}]
        # t=12 → yoy = (135-100)/100 = 35% ≥ 30
        assert bt.detect_unsold_yoy_signal(series, t_idx=12, threshold_yoy_pct=30) is True

    def test_yoy_below_threshold_no_trigger(self):
        series = [{"unsold": 100}] * 12 + [{"unsold": 120}]
        assert bt.detect_unsold_yoy_signal(series, t_idx=12, threshold_yoy_pct=30) is False

    def test_too_early_no_trigger(self):
        series = [{"unsold": 100}] * 5
        assert bt.detect_unsold_yoy_signal(series, t_idx=4, threshold_yoy_pct=30) is False

    def test_zero_prior_no_trigger(self):
        series = [{"unsold": 0}] * 12 + [{"unsold": 50}]
        assert bt.detect_unsold_yoy_signal(series, t_idx=12, threshold_yoy_pct=30) is False


class TestSignalHitRate:
    def test_negative_direction_full_hit(self):
        # 3 signal events → all -10% → 100% hit
        events = [True, False, True, True, False]
        rets = [-10.0, 5.0, -8.0, -12.0, 0.0]
        out = bt.compute_signal_hit_rate(events, rets, direction="negative", threshold_pct=-5.0)
        assert out["trigger_count"] == 3
        assert out["hit_count"] == 3
        assert out["hit_rate_pct"] == 100.0
        assert out["mean_return_pct"] == pytest.approx(-10.0, abs=0.5)

    def test_negative_partial_hit(self):
        events = [True, True, True, True]
        rets = [-10.0, -3.0, 2.0, -8.0]
        out = bt.compute_signal_hit_rate(events, rets, direction="negative", threshold_pct=-5.0)
        # -10/-8 hit (≤ -5). -3/2 miss
        assert out["hit_count"] == 2
        assert out["hit_rate_pct"] == 50.0

    def test_no_trigger_returns_none_rate(self):
        events = [False, False, False]
        rets = [-10.0, 5.0, -3.0]
        out = bt.compute_signal_hit_rate(events, rets)
        assert out["trigger_count"] == 0
        assert out["hit_rate_pct"] is None

    def test_positive_direction(self):
        events = [True, True, True]
        rets = [10.0, 3.0, 8.0]
        out = bt.compute_signal_hit_rate(events, rets, direction="positive", threshold_pct=5.0)
        assert out["hit_count"] == 2  # 10, 8 만 ≥ 5

    def test_invalid_direction_raises(self):
        with pytest.raises(ValueError):
            bt.compute_signal_hit_rate([True], [10.0], direction="bogus")


class TestIC:
    def test_perfect_positive(self):
        scores = list(range(25))
        rets = [s * 0.5 + 1 for s in scores]
        rho, p = bt.compute_ic(scores, rets)
        assert rho == pytest.approx(1.0, abs=0.001)
        assert p is not None and p < 0.001

    def test_perfect_negative(self):
        scores = list(range(25))
        rets = [-s for s in scores]
        rho, p = bt.compute_ic(scores, rets)
        assert rho == pytest.approx(-1.0, abs=0.001)

    def test_no_correlation(self):
        # 무작위 (시드 고정) — n=20, 약한 상관
        import random
        random.seed(42)
        scores = list(range(20))
        rets = list(range(20))
        random.shuffle(rets)
        rho, p = bt.compute_ic(scores, rets)
        assert abs(rho) < 0.5

    def test_too_few_samples(self):
        rho, p = bt.compute_ic([1, 2], [1, 2])
        assert rho is None and p is None

    def test_handles_none_values(self):
        scores = [1, 2, 3, None, 5]
        rets = [1, 2, None, 4, 5]
        rho, p = bt.compute_ic(scores, rets)
        # 3 valid pairs (1,1), (2,2), (5,5) — 완전 양의
        assert rho == pytest.approx(1.0, abs=0.001)


class TestQuintileSpread:
    def test_typical_5分위(self):
        # 25 종목 — score 와 return 완전 양의 상관 → Q5-Q1 양의 spread
        n = 25
        scores = list(range(n))
        rets = [s * 0.5 + 1 for s in scores]
        out = bt.compute_quintile_spread(scores, rets)
        assert out is not None
        assert out["q1_mean_return_pct"] < out["q5_mean_return_pct"]
        assert out["spread_pct"] > 5  # n=25, q_size=5 → Q5 mean ~12, Q1 ~2 → spread ~10
        assert out["q_size"] == 5
        assert out["n_total"] == 25

    def test_n_under_5_returns_none(self):
        out = bt.compute_quintile_spread([1, 2, 3], [1, 2, 3])
        assert out is None

    def test_negative_spread_flagged(self):
        # 역상관 → Q5 < Q1
        scores = list(range(20))
        rets = [-s for s in scores]
        out = bt.compute_quintile_spread(scores, rets)
        assert out["spread_pct"] < 0
