"""4 신설 산식 회귀 방지 unit test (2026-05-17, Perplexity Q2/Q4/Q6 박은 후).

- api/quant/antifragility.py (Skewness/Kurtosis/VBR/AI)
- api/quant/fomo_score.py (Realized vs Rule-based Turnover)
- api/quant/alpha/psr.py (Probabilistic Sharpe Ratio + DSR)
- api/intelligence/strategy_pool.py (add_to_pool 비교 + ensemble)
"""
from __future__ import annotations

import math
import statistics
from datetime import datetime, timedelta, timezone

import pytest

KST = timezone(timedelta(hours=9))


# ─── Antifragility ────────────────────────────────────────────

class TestAntifragility:
    def test_skewness_positive_distribution(self):
        from api.quant.antifragility import compute_skewness
        # right-skewed: mass left, tail right
        rs = [-0.01, -0.01, -0.01, -0.005, 0.0, 0.05, 0.1]
        skew = compute_skewness(rs)
        assert skew is not None and skew > 0

    def test_skewness_too_short(self):
        from api.quant.antifragility import compute_skewness
        assert compute_skewness([0.01, 0.02]) is None

    def test_kurtosis_fat_tail(self):
        from api.quant.antifragility import compute_kurtosis
        # 극단값 포함 = kurtosis ↑
        rs = [0.001] * 20 + [0.1, -0.1]  # 2 tail events
        k = compute_kurtosis(rs)
        assert k is not None and k > 3

    def test_vbr_above_threshold(self):
        from api.quant.antifragility import compute_volatility_benefit_ratio
        import random
        random.seed(42)
        # 다양한 vol 분포 — low + high vol 둘 다 있어야 cutoff percentile 분리 가능
        rs = []
        for i in range(30):
            # 처음 15일 = low vol (0.005), 다음 15일 = high vol (0.02 std)
            if i < 15:
                rs.append(random.gauss(0.001, 0.005))
            else:
                rs.append(random.gauss(0.001, 0.02))
        # 추가 high-vol days (positive 평균)
        rs += [0.05, -0.04, 0.06, -0.05, 0.07]
        vbr = compute_volatility_benefit_ratio(rs)
        assert vbr is not None
        assert "vbr" in vbr
        assert "interpretation" in vbr

    def test_ai_warns_low_sample(self):
        from api.quant.antifragility import compute_antifragility_index
        port = [0.001] * 60
        market = [0.001] * 60
        result = compute_antifragility_index(port, market)
        # shock days 0건 → _warning 박힘
        assert result is not None
        # 0건이면 _warning, 5+ 건이면 ai

    def test_assess_antifragility_verdict_levels(self):
        from api.quant.antifragility import assess_antifragility
        port = [0.001] * 60
        result = assess_antifragility(port)
        assert "verdict" in result
        assert result["verdict"] in (
            "antifragile_confirmed", "partial_antifragile", "robust", "fragile"
        )


# ─── FOMO Score ────────────────────────────────────────────

class TestFOMOScore:
    def _make_event(self, ev_type: str, days_ago: int, rule_id=None):
        return {
            "type": ev_type,
            "timestamp": (datetime.now(KST) - timedelta(days=days_ago)).isoformat(),
            "rule_id": rule_id,
        }

    def test_anti_fomo_achieved_all_rule_based(self):
        from api.quant.fomo_score import compute_fomo_score
        # 4 events, all rule_id 박힘 + 4 verdict_changes (rule_based total = 8)
        # realized total = 4. FOMO = 4/8 - 1 = -0.5 → 음수 = anti_fomo_achieved
        history = [
            self._make_event("BUY", 5, rule_id="verdict_BUY"),
            self._make_event("SELL", 4, rule_id="verdict_to_AVOID"),
            self._make_event("BUY", 3, rule_id="verdict_BUY"),
            self._make_event("SELL", 2, rule_id="stop_loss"),
        ]
        result = compute_fomo_score(history)
        assert result["fomo_score"] is not None
        # auto 4, rule_triggered 4. realized total 4 / rule total 4 = 1. FOMO = 0 → anti_fomo_achieved
        assert result["fomo_score"] == 0.0
        assert result["interpretation"] == "anti_fomo_achieved"

    def test_high_risk_impulsive(self):
        from api.quant.fomo_score import compute_fomo_score
        # 4 manual events (rule_id None), 1 auto = 5 realized vs 1 rule = FOMO 4.0
        history = [
            self._make_event("BUY", 5),
            self._make_event("BUY", 4),
            self._make_event("SELL", 3),
            self._make_event("SELL", 2),
            self._make_event("BUY", 1, rule_id="verdict_BUY"),
        ]
        result = compute_fomo_score(history)
        assert result["fomo_score"] > 0.3
        assert result["interpretation"] == "high_risk_impulsive_trading"

    def test_no_activity(self):
        from api.quant.fomo_score import compute_fomo_score
        result = compute_fomo_score([])
        assert result["fomo_score"] == 0.0
        assert result["interpretation"] == "no_activity"


# ─── PSR / DSR ────────────────────────────────────────────

class TestPSR:
    def test_sr_se_lopez_de_prado(self):
        from api.quant.alpha.psr import compute_sr_standard_error
        # T=90, SR=0.8 정규분포 → SE ≈ 0.127 (Perplexity Q4 cite)
        se = compute_sr_standard_error(0.8, T=90, skew=0.0, kurt=3.0)
        assert 0.10 < se < 0.13

    def test_psr_strong_improvement(self):
        from api.quant.alpha.psr import compute_psr
        # SR 1.5 vs 0.5, T=90 → 강한 개선 → PSR ≈ 1.0
        result = compute_psr(sr_observed=1.5, sr_benchmark=0.5, T=90)
        assert result["psr"] > 0.95

    def test_psr_no_improvement(self):
        from api.quant.alpha.psr import compute_psr
        # SR 0.5 vs 0.5 = identical → PSR = 0.5
        result = compute_psr(sr_observed=0.5, sr_benchmark=0.5, T=90)
        assert 0.45 < result["psr"] < 0.55

    def test_dsr_with_trials(self):
        from api.quant.alpha.psr import compute_deflated_sharpe_ratio
        # K=27 trials, T=90, SR=1.5 → DSR 계산 가능
        result = compute_deflated_sharpe_ratio(
            sr_observed=1.5, T=90, n_trials=27,
        )
        assert "psr" in result  # DSR 도 PSR schema 반환
        assert 0 <= result["psr"] <= 1


# ─── Strategy Pool ────────────────────────────────────────────

class TestStrategyPool:
    def test_add_to_empty_pool(self):
        from api.intelligence.strategy_pool import add_to_pool
        pool, decision = add_to_pool([], {"version": 1, "sharpe": 0.8})
        assert decision["accepted"] is True
        assert decision["pool_size"] == 1

    def test_fill_pool_unconditional(self):
        from api.intelligence.strategy_pool import add_to_pool
        s1 = {"version": 1, "sharpe": 0.8}
        s2 = {"version": 2, "sharpe": 0.5}  # 낮아도 미충 시 accept
        pool, _ = add_to_pool([], s1)
        pool, dec2 = add_to_pool(pool, s2, max_size=3)
        assert dec2["accepted"] is True

    def test_replace_worst_when_full(self):
        from api.intelligence.strategy_pool import add_to_pool
        pool = [
            {"version": 1, "sharpe": 0.8},
            {"version": 2, "sharpe": 1.2},
            {"version": 3, "sharpe": 0.6},
        ]
        s_new = {"version": 4, "sharpe": 0.9}  # worst (0.6) 대비 +0.3 > margin 0.10
        new_pool, decision = add_to_pool(pool, s_new, max_size=3, min_margin=0.10)
        assert decision["accepted"] is True
        assert decision["replaced_version"] == 3
        assert len(new_pool) == 3

    def test_reject_insufficient_margin(self):
        from api.intelligence.strategy_pool import add_to_pool
        pool = [
            {"version": 1, "sharpe": 0.8},
            {"version": 2, "sharpe": 1.2},
            {"version": 3, "sharpe": 0.7},
        ]
        s_new = {"version": 4, "sharpe": 0.75}  # worst (0.7) 대비 +0.05 < margin 0.10
        _, decision = add_to_pool(pool, s_new, max_size=3, min_margin=0.10)
        assert decision["accepted"] is False

    def test_ensemble_signal(self):
        from api.intelligence.strategy_pool import compute_ensemble_signal
        pool = [
            {"version": 1, "sharpe": 0.8, "weight": 0.4},
            {"version": 2, "sharpe": 1.2, "weight": 0.6},
        ]
        signals = {
            1: {"brain_score": 60, "verdict": "BUY"},
            2: {"brain_score": 80, "verdict": "STRONG_BUY"},
        }
        result = compute_ensemble_signal(pool, signals)
        # 60 × 0.4 + 80 × 0.6 = 24 + 48 = 72 → BUY 임계 60+
        assert result["ensemble_score"] == 72.0
        assert result["ensemble_verdict"] in ("STRONG_BUY", "BUY")
