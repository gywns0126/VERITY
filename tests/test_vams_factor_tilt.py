"""Sprint 11 결함 4 — VAMS factor tilt 한도 검증.

베테랑 평가: sector 한도는 있지만 factor (momentum/quality/volatility/mean_reversion)
exposure 한도 부재. portfolio 가 7종목인데 모두 momentum 70+ 면 사실상 단일 factor
베팅. 분산 효과 깨짐.
"""
from __future__ import annotations

from api.vams.engine import _check_portfolio_exposure


def _holding(ticker, value, sector="Tech", **factor_overrides):
    """quant_factors 채운 holding mock. value = 시가 × 수량."""
    qf = {
        "momentum": 50, "quality": 50, "volatility": 50, "mean_reversion": 50,
        **factor_overrides,
    }
    return {
        "ticker": ticker,
        "current_price": value // 1000,
        "quantity": 1000,
        "sector": sector,
        "beta": 1.0,
        "multi_factor": {"quant_factors": qf},
    }


def _candidate(sector="Energy", **factor_overrides):
    qf = {
        "momentum": 50, "quality": 50, "volatility": 50, "mean_reversion": 50,
        **factor_overrides,
    }
    return {
        "ticker": "CAND",
        "sector": sector,
        "beta": 1.0,
        "multi_factor": {"quant_factors": qf},
    }


def _portfolio(holdings, total=10_000_000, cash=5_000_000):
    return {"vams": {"total_asset": total, "cash": cash, "holdings": holdings}}


class TestFactorTilt:
    def test_no_block_when_diversified(self):
        """다양한 factor 분포 → 매수 통과."""
        h = [
            _holding("A", 1_000_000, sector="Tech", momentum=80),
            _holding("B", 1_000_000, sector="Bio", quality=80),
            _holding("C", 1_000_000, sector="Auto", volatility=20),
        ]
        p = _portfolio(h)
        cand = _candidate(sector="Energy", momentum=75)
        r = _check_portfolio_exposure(p, cand)
        assert r["blocked"] is False

    def test_block_when_momentum_tilt_exceeds(self):
        """모든 holdings + cand 가 momentum 고-노출 → 한도 60% 초과 → block."""
        h = [
            _holding("A", 1_500_000, sector="Tech", momentum=80),    # 15%
            _holding("B", 2_000_000, sector="Bio", momentum=75),     # 20%
            _holding("C", 1_500_000, sector="Auto", momentum=85),    # 15%
            _holding("D", 1_000_000, sector="Bank", momentum=78),    # 10%
        ]
        # 누적 60% (홀딩만으로 한도)
        p = _portfolio(h)
        cand = _candidate(sector="Energy", momentum=80)
        r = _check_portfolio_exposure(p, cand)
        assert r["blocked"] is True
        assert "momentum" in r["reason"]

    def test_block_when_low_volatility_tilt_exceeds(self):
        """모든 holdings 가 volatility ≤30 → 새 매수 도 같은 tilt → block."""
        h = [
            _holding("A", 2_000_000, sector="Tech", volatility=20),  # 20%
            _holding("B", 2_000_000, sector="Bio", volatility=25),   # 20%
            _holding("C", 2_000_000, sector="Auto", volatility=15),  # 20%
        ]
        p = _portfolio(h)
        cand = _candidate(sector="Energy", volatility=10)  # 또 low vol
        r = _check_portfolio_exposure(p, cand)
        assert r["blocked"] is True
        assert "volatility" in r["reason"]

    def test_no_block_when_factor_neutral(self):
        """factor 가 30-70 사이면 tilt 카운트 안 함 → 통과."""
        h = [
            _holding("A", 2_000_000, momentum=50, quality=50),
            _holding("B", 2_000_000, momentum=55, quality=45),
        ]
        p = _portfolio(h)
        cand = _candidate(momentum=60)  # 중립
        r = _check_portfolio_exposure(p, cand)
        assert r["blocked"] is False

    def test_no_block_when_quant_factors_missing(self):
        """quant_factors 없는 holdings — graceful fallback (block X)."""
        h = [
            {"ticker": "A", "current_price": 1000, "quantity": 2000, "sector": "Tech",
             "beta": 1.0},  # multi_factor 없음
        ]
        p = _portfolio(h)
        cand = {"ticker": "CAND", "sector": "Energy", "beta": 1.0}
        r = _check_portfolio_exposure(p, cand)
        assert r["blocked"] is False
