"""2026-07-24 2차 산식 감사 — VCI median-centered robust z 재캘리.

옛 σ=15 고정 가정이 실측 gap 분포([-7,15], σ≈4.1, mean +2.9)와 3.6배 불일치 → 전 밴드 사장(0% 발화).
Perplexity grounding = robust MAD σ + median-centering(tilt 제거). 밴드 |z|≥1(mild)/≥2(strong).
test 는 gap_median/robust_sigma override 로 결정론.
"""
from __future__ import annotations

from api.intelligence.factors.vci import _compute_vci


def _sig(fact, sentiment, median=3.0, sigma=5.0):
    return _compute_vci(fact, sentiment, gap_median=median, robust_sigma=sigma)


def test_strong_contrarian_buy_at_2sigma():
    # gap = median + 2σ = 3 + 10 = 13 → robust z 2.0 → STRONG_CONTRARIAN_BUY
    assert _sig(63, 50)["signal"] == "STRONG_CONTRARIAN_BUY"  # gap 13


def test_mild_contrarian_buy_at_1sigma():
    # gap = median + 1σ = 3 + 5 = 8 → z 1.0 → CONTRARIAN_BUY
    assert _sig(58, 50)["signal"] == "CONTRARIAN_BUY"  # gap 8


def test_median_centering_removes_tilt():
    # gap = median(3) → z 0 → ALIGNED (옛 center 0 이면 gap 3 이 mild-buy 로 오판)
    assert _sig(53, 50)["signal"] == "ALIGNED"  # gap 3 = median


def test_downside_strong_sell():
    # gap = median - 2σ = 3 - 10 = -7 → z -2 → STRONG_CONTRARIAN_SELL
    assert _sig(43, 50)["signal"] == "STRONG_CONTRARIAN_SELL"  # gap -7


def test_mispricing_z_is_robust():
    r = _sig(63, 50)  # gap 13, median 3, σ 5 → z 2.0
    assert abs(r["mispricing_z"] - 2.0) < 0.01
    assert r["mispricing_signal"] == "extreme_undervalued"


def test_calibration_exposed():
    r = _sig(55, 50, median=4.0, sigma=4.45)
    assert r["gap_median"] == 4.0
    assert r["robust_sigma"] == 4.45


def test_default_calibration_loads():
    # override 없으면 _load_vci_calibration (실 portfolio 또는 기본 median0/σ5). 크래시 없이 signal 산출.
    r = _compute_vci(60, 50)
    assert "signal" in r and "robust_sigma" in r
