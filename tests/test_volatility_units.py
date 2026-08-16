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


# ── 🚨 2026-08-17 결측 축 재정규화 (PM 승인) ────────────────────────────────
# 실측 배경: 운영 풀 56종목에서 beta 가 0/56, volatility_20d 가 34/56 였다.
# 종전에는 못 잰 축에 중립 50 을 채우고 고정 가중으로 합산해, beta(.25)+idio(.15)
# = 40% 가 전 종목 동일값인 채로 가중을 먹었다. 그 결과 값이 있는 34종목조차
# 표준편차 7.42 (범위 29~59) 로 50 쪽에 눌려 있었다 → 교정 후 12.38 (15~65).

def test_unmeasured_axes_reported():
    """못 잰 하위축은 이름으로 신고한다 — 중립 50 을 관측처럼 보이게 두지 않는다."""
    r = compute_volatility_score({"volatility_20d": 0.02})
    assert set(r["unmeasured_axes"]) == {"vol_trend", "beta", "idiosyncratic"}
    r2 = compute_volatility_score({"volatility_20d": 0.02, "volatility_60d": 0.03, "beta": 1.0})
    assert r2["unmeasured_axes"] == []


def test_renormalization_excludes_unmeasured_weight():
    """측정된 축만으로 재정규화 — 결측 축의 중립 50 이 총점을 50 쪽으로 끌지 않는다."""
    r = compute_volatility_score({"volatility_20d": 0.008})   # 초저변동 → rv 90
    # realized_vol 만 측정 → 재정규화하면 총점 = rv 그 자체
    assert r["components"]["realized_vol"] == 90
    assert r["volatility_score"] == 90, "결측 축 중립값이 총점을 희석하면 회귀"


def test_renormalization_widens_dispersion():
    """🚨 핵심 회귀: 같은 입력 집합의 총점 분산이 고정가중 대비 넓어진다."""
    import statistics
    vols = [0.008, 0.015, 0.025, 0.040, 0.070]
    W = {"realized_vol": 0.35, "vol_trend": 0.25, "beta": 0.25, "idiosyncratic": 0.15}
    new, old = [], []
    for v in vols:
        r = compute_volatility_score({"volatility_20d": v})
        new.append(r["volatility_score"])
        old.append(round(sum(r["components"][k] * W[k] for k in W)))
    assert statistics.pstdev(new) > statistics.pstdev(old) * 1.5, (
        f"재정규화가 변별을 넓히지 못함: 옛 {statistics.pstdev(old):.2f} → 새 {statistics.pstdev(new):.2f}")


def test_all_axes_unmeasured_is_neutral_with_report():
    """전 축 미측정 = 중립 50 이되, unmeasured_axes 가 4축 전부를 신고한다."""
    r = compute_volatility_score({})
    assert r["volatility_score"] == 50
    assert len(r["unmeasured_axes"]) == 4
