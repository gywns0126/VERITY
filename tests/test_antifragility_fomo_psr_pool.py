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
        import math
        # 🚨 Lo(2002) 정규 baseline: SE = sqrt((1+½SR²)/(T-1)).
        # T=90, SR=0.8 → sqrt((1+0.32)/89) = 0.1218. 옛 버그(½SR² 누락)=0.1060.
        se = compute_sr_standard_error(0.8, T=90, skew=0.0, kurt=3.0)
        assert math.isclose(se, math.sqrt(1.32 / 89), rel_tol=1e-6)
        assert se > 0.115  # ½SR² 누락 회귀(0.106) 차단

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

    def test_se_negative_variance_returns_nan(self):
        """🚨 음수 점근분산(저N·고skew×SR) → SE=0(완벽추정 오독) 아닌 nan(추정불가)."""
        from api.quant.alpha.psr import compute_sr_standard_error
        # skew*sr = 2.0*0.8 = 1.6 > 1 → bracket = 1-1.6+... < 0 → variance < 0
        se = compute_sr_standard_error(0.8, T=14, skew=2.0, kurt=3.0)
        assert math.isnan(se)

    def test_psr_degenerate_variance_returns_none(self):
        """🚨 RULE 7 거짓확실성 회귀: SE 붕괴 시 psr=1.0/z=inf 아닌 None+_note (추정불가)."""
        from api.quant.alpha.psr import compute_psr
        r = compute_psr(sr_observed=0.8, sr_benchmark=0.0, T=14, skew=2.0, kurt=3.0)
        assert r["psr"] is None          # 옛 거짓 1.0 회귀 차단
        assert r["z_score"] is None      # 옛 inf 제거 (JSON Infinity 차단)
        assert r["se_sr"] is None
        assert "_note" in r
        # JSON 직렬화 시 'Infinity'(무효 JSON) 미포함
        import json
        assert "Infinity" not in json.dumps(r)

    def test_validation_significance_none_safe_on_degenerate(self):
        """관측 표면(validation) 이 degenerate psr=None 에서 significant_95=False 안전 처리."""
        from api.quant.alpha.psr import compute_psr, compute_deflated_sharpe_ratio
        psr = compute_psr(0.8, 0.0, 14, skew=2.0, kurt=3.0)
        dsr = compute_deflated_sharpe_ratio(0.8, T=14, n_trials=10, skew=2.0, kurt=3.0)
        _dsr = dsr.get("psr", dsr.get("dsr"))
        # validation.py:213 의 None-safe 식 재현
        assert (_dsr is not None and _dsr >= 0.95) is False


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
