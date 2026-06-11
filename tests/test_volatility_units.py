"""🚨 volatility 팩터 단위(분수→연환산%) 회귀.

배경: producer(backtester pct_change().std())=일간 분수(~0.02). 옛 코드 line 52
  `vol_20*sqrt(252) if vol_20<1 else vol_20` 가 *100 누락 → 0.16~0.95 출력이 전부
  임계(<=15 연환산% 가정)에 걸려 realized_vol=90 상수 = 전 종목 동일 = 죽은 팩터.
fix: *sqrt(252)*100 으로 연환산% 정규화 → 임계와 단위 정합 → 종목별 차등 점수 복원.
이 테스트 = 상수 90 회귀 차단(분수 입력 → 차등 점수 검증).
"""
from __future__ import annotations

import pytest

from api.quant.factors.volatility import compute_volatility_score


@pytest.mark.parametrize(
    "vol_20d, expected_rv",
    [
        (0.008, 90),   # 연 12.7% → 초저변동
        (0.010, 75),   # 연 15.9% → 저변동 (옛 버그=90)
        (0.020, 55),   # 연 31.7% → 중변동 (옛 버그=90)
        (0.030, 35),   # 연 47.6% → 고변동 (옛 버그=90)
        (0.060, 15),   # 연 95.2% → 초고변동 (옛 버그=90)
    ],
)
def test_realized_vol_differentiates_by_unit(vol_20d, expected_rv):
    """일간 분수 입력 → 연환산% 임계로 차등 점수 (옛 버그는 전부 90 상수)."""
    r = compute_volatility_score({"volatility_20d": vol_20d})
    assert r["components"]["realized_vol"] == expected_rv


def test_realized_vol_not_constant_across_universe():
    """🚨 핵심 회귀: 서로 다른 변동성 종목이 서로 다른 realized_vol (상수 90 아님)."""
    vols = [0.008, 0.015, 0.025, 0.040, 0.070]
    scores = [
        compute_volatility_score({"volatility_20d": v})["components"]["realized_vol"]
        for v in vols
    ]
    assert len(set(scores)) > 1, f"realized_vol 이 상수 = 죽은 팩터 회귀: {scores}"
    assert scores == sorted(scores, reverse=True)  # 저변동일수록 고점수(단조)


def test_idiosyncratic_differentiates_by_unit():
    """idio 컴포넌트도 *100 정합 — beta=1.0 vol=0.02 → 연 idio ~26% → 40 (옛 버그=85)."""
    r = compute_volatility_score({"volatility_20d": 0.020, "beta": 1.0})
    assert r["components"]["idiosyncratic"] == 40


def test_signal_string_shows_real_percent():
    """signals '연 변동성 N%' 가 실제값(16~95%) 노출 (옛 버그=0.2% 헛값)."""
    r = compute_volatility_score({"volatility_20d": 0.060})
    sig = " ".join(r["signals"])
    assert "95." in sig or "초고변동" in sig  # 0.06*sqrt(252)*100 ≈ 95.2%
