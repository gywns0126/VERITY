"""Sprint 11 결함 2 — Brain Score Graham vs CANSLIM regime switching 검증.

베테랑 평가: Graham (저PER 가치) + CANSLIM (고성장 모멘텀) 가중평균 시 양쪽 어정쩡.
시장 사이클 따라 regime switching: bull=CANSLIM 우세, bear=Graham 우세.

regime_diagnostics 의 trailing/leading score 평균으로 판정.
"""
from __future__ import annotations

from api.intelligence.verity_brain import _compute_fact_score


def _base_stock():
    """fact_score 산출 가능한 최소 종목 dict."""
    return {
        "ticker": "TEST",
        "multi_factor": {"multi_score": 60},
        "consensus": {"consensus_score": 55},
        "prediction": {"up_probability": 60},
        "backtest": {},
        "timing": {"timing_score": 50},
        "commodity_margin": {},
        "market_cap": 5_000_000_000_000,  # 5조
        "per": 12.0, "pbr": 1.5, "roe": 0.15, "debt_ratio": 50.0,
        "operating_margin": 10.0,
        "revenue_growth": 18.0,
        "consensus_eps_growth_yoy_pct": 25.0,
    }


class TestRegimeSwitchApplied:
    def test_no_regime_diagnostics_means_default_weights(self):
        """regime_diagnostics 없으면 기본 가중치 그대로."""
        stock = _base_stock()
        portfolio = {}  # regime_diagnostics 미부착
        fs = _compute_fact_score(stock, portfolio=portfolio)
        rw = fs.get("regime_weighting") or {}
        assert rw.get("applied") is False or "regime_weighting" not in fs

    def test_bull_regime_canslim_dominant(self):
        """trailing+leading 모두 강한 양수 → bull → CANSLIM 1.5x, Graham 0.5x."""
        stock = _base_stock()
        portfolio = {
            "regime_diagnostics": {
                "trailing_score": 0.6,
                "leading_score": 0.5,
            }
        }
        fs = _compute_fact_score(stock, portfolio=portfolio)
        rw = fs.get("regime_weighting") or {}
        assert rw["applied"] is True
        assert rw["mode"] == "bull_canslim_dominant"
        # Graham 가중치는 줄고 CANSLIM 가중치는 늘어야
        assert rw["canslim_weight"] > rw["graham_weight"]

    def test_bear_regime_graham_dominant(self):
        """trailing+leading 모두 강한 음수 → bear → Graham 1.5x, CANSLIM 0.5x."""
        stock = _base_stock()
        portfolio = {
            "regime_diagnostics": {
                "trailing_score": -0.6,
                "leading_score": -0.5,
            }
        }
        fs = _compute_fact_score(stock, portfolio=portfolio)
        rw = fs.get("regime_weighting") or {}
        assert rw["applied"] is True
        assert rw["mode"] == "bear_graham_dominant"
        # Graham 가중치는 늘고 CANSLIM 가중치는 줄어야
        assert rw["graham_weight"] > rw["canslim_weight"]

    def test_mixed_regime_balanced(self):
        """trailing/leading 합산 ≈ 0 → mixed → 기본 가중치 유지."""
        stock = _base_stock()
        portfolio = {
            "regime_diagnostics": {
                "trailing_score": 0.0,
                "leading_score": 0.0,
            }
        }
        fs = _compute_fact_score(stock, portfolio=portfolio)
        rw = fs.get("regime_weighting") or {}
        assert rw["applied"] is True
        assert rw["mode"] == "mixed_balanced"
        # mixed 에선 graham/canslim 가중치 동일 (default 와 같음)
        assert abs(rw["graham_weight"] - rw["canslim_weight"]) < 0.001

    def test_leading_weighted_more(self):
        """trailing=0.5, leading=-0.5 → 평균 가중에서 leading 1.5x 적용 →
        regime_score = (0.5 + -0.5*1.5)/2.5 = -0.1 → mixed.
        leading 우세 — 베테랑 권고대로 선행 신호 가중."""
        stock = _base_stock()
        portfolio = {
            "regime_diagnostics": {
                "trailing_score": 0.5,
                "leading_score": -0.5,
            }
        }
        fs = _compute_fact_score(stock, portfolio=portfolio)
        rw = fs.get("regime_weighting") or {}
        # |regime_avg|=0.1 < 0.3 → mixed
        assert rw["mode"] == "mixed_balanced"

    def test_score_changes_with_regime(self):
        """동일 종목의 fact_score 가 regime 따라 *달라져야* — regime switch 효과 입증.
        방향성 (bull > bear or vice versa) 은 종목 특성 (Graham 점수 vs CANSLIM 점수)
        에 따라 갈리므로 단순 부등호로 단정 X. 핵심은 'regime 무시 X' 의 검증."""
        stock = _base_stock()

        bull_p = {"regime_diagnostics": {"trailing_score": 0.6, "leading_score": 0.5}}
        bear_p = {"regime_diagnostics": {"trailing_score": -0.6, "leading_score": -0.5}}
        mixed_p = {"regime_diagnostics": {"trailing_score": 0.0, "leading_score": 0.0}}

        bull_score = _compute_fact_score(stock, portfolio=bull_p)["score"]
        bear_score = _compute_fact_score(stock, portfolio=bear_p)["score"]
        mixed_score = _compute_fact_score(stock, portfolio=mixed_p)["score"]

        # bull / bear 둘 중 하나는 mixed 와 달라야 (regime switch 가 효과)
        assert bull_score != mixed_score or bear_score != mixed_score
        # 또는 bull ≠ bear (양극단 regime 이 다른 산출)
        assert bull_score != bear_score
