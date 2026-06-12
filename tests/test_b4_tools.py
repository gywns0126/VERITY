"""B4 sprint 도구 묶음 tests — PBO/FDF/SQN/MC/IC 엔진.

진입 2026-06-12 ([[project_verity_backtest_sprint]] B4). 정답 잠금:
  - PBO: 순수 노이즈 ≈ 0.5 / 진짜 우월 전략 = 낮음 / 결정론
  - FDF: d=0 항등 / d=1 1차 차분 / 가중치 손계산
  - SQN: 손계산 정답 / 거짓확실성 None 경로
  - MC: 상수 수익률 닫힌해 / shape / 다 block 보고 / 결정론
  - IC: window 수 / 동결 강제 / perfect-signal IC=1
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from api.quant.alpha.pbo import cscv_pbo
from api.quant.alpha.fdf import frac_diff_ffd, get_ffd_weights, min_ffd_d
from api.quant.alpha.sqn import compute_sqn
from api.quant.alpha.mc_risk import (
    block_bootstrap_paths, evaluate_paths, gbm_forward_scenario, mc_risk_report,
)
from api.quant.alpha.ic_backtest import (
    FROZEN_COMPONENTS, cross_sectional_ic, run_ic_backtest, walk_forward_windows,
)


# ─── PBO ─────────────────────────────────────────────────────

class TestPBO:
    def test_pure_noise_pbo_near_half(self):
        """순수 노이즈 — IS best 의 OOS rank = uniform → PBO ≈ 0.5."""
        rng = np.random.default_rng(42)
        M = rng.standard_normal((320, 10)) * 0.01
        out = cscv_pbo(M, n_partitions=8)
        assert 0.3 <= out["pbo"] <= 0.7, out["pbo"]
        assert out["n_combinations"] == 70  # C(8,4)

    def test_genuine_superior_strategy_low_pbo(self):
        """한 전략에 진짜 edge (높은 평균) — IS best = OOS best 일관 → PBO 낮음."""
        rng = np.random.default_rng(7)
        M = rng.standard_normal((320, 10)) * 0.01
        M[:, 3] += 0.01  # 전략 3 에 강한 일관 edge
        out = cscv_pbo(M, n_partitions=8)
        assert out["pbo"] <= 0.2, out["pbo"]
        assert out["verdict"] == "robust"

    def test_deterministic(self):
        rng = np.random.default_rng(1)
        M = rng.standard_normal((200, 5)) * 0.01
        a = cscv_pbo(M, n_partitions=6)
        b = cscv_pbo(M, n_partitions=6)
        assert a == b

    def test_validation_errors(self):
        with pytest.raises(ValueError):
            cscv_pbo(np.zeros((100, 1)), n_partitions=4)   # N < 2
        with pytest.raises(ValueError):
            cscv_pbo(np.zeros((100, 3)), n_partitions=5)   # 홀수 S
        with pytest.raises(ValueError):
            cscv_pbo(np.zeros((10, 3)), n_partitions=16)   # T 부족

    def test_max_combinations_cap(self):
        rng = np.random.default_rng(3)
        M = rng.standard_normal((320, 4)) * 0.01
        out = cscv_pbo(M, n_partitions=8, max_combinations=20)
        assert out["n_combinations"] == 20


# ─── FDF ─────────────────────────────────────────────────────

class TestFDF:
    def test_d0_identity(self):
        w = get_ffd_weights(0.0)
        assert list(w) == [1.0]
        s = pd.Series([10.0, 11.0, 12.0, 13.0])
        out = frac_diff_ffd(s, 0.0)
        assert np.allclose(out.to_numpy(), s.to_numpy())

    def test_d1_first_difference(self):
        w = get_ffd_weights(1.0)
        assert np.allclose(w, [1.0, -1.0])
        s = pd.Series([10.0, 11.0, 13.0, 16.0])
        out = frac_diff_ffd(s, 1.0)
        assert math.isnan(out.iloc[0])
        assert np.allclose(out.iloc[1:].to_numpy(), [1.0, 2.0, 3.0])

    def test_weights_hand_computed_d05(self):
        """w0=1, w1=-0.5, w2=-w1(0.5-1)/2=-0.125, w3=-w2(0.5-2)/3=-0.0625."""
        w = get_ffd_weights(0.5, threshold=1e-4)
        assert np.allclose(w[:4], [1.0, -0.5, -0.125, -0.0625])

    def test_nan_head_equals_width_minus_1(self):
        # d=0.4 + 기본 threshold 1e-5 = 느린 감쇠 (window ~1458). 시계열이 window 보다
        # 길어야 NaN-head = width-1 성립 (짧으면 전부 NaN — 가드 정상). threshold 키워
        # window 축소 후 충분한 길이 부여.
        d, thr = 0.4, 1e-3
        w = get_ffd_weights(d, threshold=thr)
        s = pd.Series(np.linspace(100, 120, len(w) + 50))
        out = frac_diff_ffd(s, d, threshold=thr)
        assert out.isna().sum() == len(w) - 1

    def test_min_ffd_graceful_without_statsmodels(self):
        """statsmodels 유무 무관 — grid 산출 + adf_available 플래그 정직."""
        rng = np.random.default_rng(5)
        s = pd.Series(np.cumsum(rng.standard_normal(300)) + 100)
        out = min_ffd_d(s, d_grid=np.array([0.0, 0.5, 1.0]))
        assert len(out["grid"]) == 3
        assert isinstance(out["adf_available"], bool)
        if not out["adf_available"]:
            assert out["min_d"] is None

    def test_d_range_validation(self):
        with pytest.raises(ValueError):
            get_ffd_weights(1.5)


# ─── SQN ─────────────────────────────────────────────────────

class TestSQN:
    def test_hand_computed(self):
        """R=[2,-1,2,-1]: mean=.5, std=√3, SQN=.5/√3×2=0.5774."""
        out = compute_sqn([2.0, -1.0, 2.0, -1.0])
        assert out["n"] == 4
        assert abs(out["sqn"] - 0.5774) < 1e-3
        assert out["band"] == "below_poor"
        assert out["statistically_meaningful"] is False

    def test_band_good(self):
        """mean=.27, std≈1.005, n=100 → SQN≈2.686 → good."""
        rs = [1.27, -0.73] * 50
        out = compute_sqn(rs)
        assert out["band"] == "good", out
        assert out["statistically_meaningful"] is True
        assert out["sqn"] == out["sqn_100"]  # n=100 → 동일

    def test_false_certainty_paths(self):
        assert compute_sqn([])["sqn"] is None
        assert compute_sqn([1.0])["sqn"] is None
        out = compute_sqn([1.0] * 20)  # std=0
        assert out["sqn"] is None
        assert "std(R)=0" in out["_note"]

    def test_nan_filtered(self):
        out = compute_sqn([2.0, float("nan"), -1.0, None, 2.0, -1.0])
        assert out["n"] == 4


# ─── MC risk ─────────────────────────────────────────────────

class TestMCRisk:
    def test_constant_returns_closed_form(self):
        """상수 0.001 일별 → 모든 경로 final = 1.001^252, MDD=0, ruin=0."""
        real = np.full(300, 0.001)
        rng = np.random.default_rng(7)
        paths = block_bootstrap_paths(real, 252, 100, 10, rng)
        out = evaluate_paths(paths)
        expected = 1.001 ** 252
        assert abs(out["final_p50"] - expected) < 1e-2
        assert out["p_loss"] == 0.0
        assert out["p_ruin"] == 0.0
        assert out["mdd_worst"] == 0.0

    def test_bootstrap_shape_and_determinism(self):
        real = np.random.default_rng(0).standard_normal(500) * 0.01
        p1 = block_bootstrap_paths(real, 100, 50, 10, np.random.default_rng(3))
        p2 = block_bootstrap_paths(real, 100, 50, 10, np.random.default_rng(3))
        assert p1.shape == (50, 100)
        assert np.array_equal(p1, p2)

    def test_multi_block_report_mandatory(self):
        """사전등록 의무 — 다 block 동시 보고 + 짧은 history block skip 정직."""
        real = np.random.default_rng(1).standard_normal(400) * 0.01
        out = mc_risk_report(real, horizon_days=60, n_paths=200, blocks=(10, 30, 252))
        assert set(out["by_block"]) == {10, 30}      # 252×3 > 400 → skip
        assert out["blocks_skipped_short_history"] == [252]
        assert "비단조" in out["blocks_rationale"]
        assert out["method"] == "block_bootstrap_real_returns"

    def test_gbm_labeled_not_validation(self):
        out = gbm_forward_scenario(0.08, 0.2, horizon_days=60, n_paths=200)
        assert out["label"] == "forward_scenario_not_validation"

    def test_short_history_raises(self):
        with pytest.raises(ValueError):
            block_bootstrap_paths(np.zeros(20), 60, 10, 10, np.random.default_rng(0))


# ─── IC backtest 엔진 ────────────────────────────────────────

def _make_market(n_days=700, n_tickers=30, seed=2):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2021-01-04", periods=n_days)
    tickers = [f"T{i:02d}" for i in range(n_tickers)]
    rets = rng.standard_normal((n_days, n_tickers)) * 0.015
    prices = pd.DataFrame(100 * np.exp(np.cumsum(rets, axis=0)), index=dates, columns=tickers)
    return prices


class TestICBacktest:
    def test_walk_forward_window_count(self):
        dates = pd.bdate_range("2020-01-01", periods=441)
        ws = list(walk_forward_windows(dates))   # 252+126=378 ≤ 441, +63 → 2개
        assert len(ws) == 2
        train, test = ws[0]
        assert len(train) == 252 and len(test) == 126

    def test_frozen_components_enforced(self):
        prices = _make_market(450)
        with pytest.raises(ValueError, match="동결"):
            run_ic_backtest({"new_shiny_factor": prices * 0}, prices)

    def test_perfect_signal_strong_band(self):
        """score ≈ 실제 forward return (의도적 cheat + 미세 noise) → IC ≈ 1 → strong.

        noise 0 이면 IC 가 정확히 1.0 상수 → ic_std=0 → icir 정의 불가 (None).
        미세 noise = IC 에 변동 부여 → icir/t-stat 산출 경로 검증.
        """
        prices = _make_market(700)
        rng = np.random.default_rng(4)
        fwd = prices.shift(-21) / prices - 1.0
        scores = fwd + pd.DataFrame(
            rng.standard_normal(prices.shape) * 1e-4,
            index=prices.index, columns=prices.columns,
        )
        out = run_ic_backtest({"momentum": scores}, prices, apply_holdout=True)
        comp = out["components"]["momentum"]
        assert comp["ic_mean"] > 0.95
        assert comp["band"] == "strong"
        assert comp["significant_bonferroni"] is True
        assert out["freeze_date"] == "2026-06-12"

    def test_random_signal_not_strong(self):
        prices = _make_market(700)
        rng = np.random.default_rng(9)
        noise = pd.DataFrame(rng.standard_normal(prices.shape), index=prices.index,
                             columns=prices.columns)
        out = run_ic_backtest({"momentum": noise}, prices)
        comp = out["components"]["momentum"]
        assert comp["band"] != "strong"
        assert abs(comp["ic_mean"]) < 0.08  # 표본 IC 잡음 여유 (overlap window 상관)

    def test_holdout_isolation(self):
        prices = _make_market(700)
        fwd = prices.shift(-21) / prices - 1.0
        with_h = run_ic_backtest({"momentum": fwd}, prices, apply_holdout=True)
        without_h = run_ic_backtest({"momentum": fwd}, prices, apply_holdout=False)
        assert with_h["windows"] < without_h["windows"]
        assert with_h["holdout_applied"] is True

    def test_cross_sectional_ic_minimum_n(self):
        s = pd.Series([1.0, 2.0, 3.0])
        r = pd.Series([0.1, 0.2, 0.3])
        assert cross_sectional_ic(s, r) is None   # < MIN_CROSS_SECTION

    def test_frozen_list_matches_preregistration(self):
        """사전등록 8 component subset 그대로 (RULE 7 동결)."""
        assert FROZEN_COMPONENTS == [
            "momentum", "quant_volatility", "quant_momentum",
            "quant_mean_reversion", "technical_mean_reversion",
            "graham_value", "multi_factor", "moat_quality",
        ]
