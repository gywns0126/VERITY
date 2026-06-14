"""ic_crosscheck — self IC 엔진 ↔ alphalens 교차검증 로직 테스트 (D9 step 2).

2026-06-14 신설. 메인 테스트 suite 는 alphalens/가격레이크 무의존(cron CI 통과 보장):
순수 로직(팩터 산출/self IC 시계열/graceful degrade)만 합성 데이터로 검증.
실 alphalens 수렴은 alphalens 설치 시에만 (skip if absent).
"""
import numpy as np
import pandas as pd
import pytest

from scripts import ic_crosscheck as cc


def _synth_panel(n_tickers=20, n_days=60, seed=0):
    rng = np.random.RandomState(seed)
    dates = pd.bdate_range("2025-01-01", periods=n_days)
    cols = [f"T{i:03d}" for i in range(n_tickers)]
    # 랜덤워크 close
    rets = rng.normal(0, 0.02, size=(n_days, n_tickers))
    close = pd.DataFrame(100 * np.cumprod(1 + rets, axis=0), index=dates, columns=cols)
    return close


def test_compute_factor_momentum():
    close = _synth_panel()
    mom = cc._compute_factor(close, "momentum", 5)
    # 5일 모멘텀 = pct_change(5)
    expected = close.iloc[5] / close.iloc[0] - 1
    pd.testing.assert_series_equal(mom.iloc[5], expected, check_names=False)


def test_compute_factor_reversal_is_negated_momentum():
    close = _synth_panel()
    mom = cc._compute_factor(close, "momentum", 5)
    rev = cc._compute_factor(close, "reversal", 5)
    pd.testing.assert_frame_equal(rev, -mom)


def test_compute_factor_invalid():
    with pytest.raises(ValueError):
        cc._compute_factor(_synth_panel(), "nonsense", 5)


def test_self_ic_series_runs():
    close = _synth_panel(n_tickers=30, n_days=80)
    fac = cc._compute_factor(close, "momentum", 10)
    ics = cc._self_ic_series(fac, close, horizon=5)
    assert isinstance(ics, list)
    assert len(ics) > 10
    assert all(isinstance(x, float) and np.isfinite(x) for x in ics)
    assert all(-1.0 <= x <= 1.0 for x in ics)


def test_self_ic_perfect_predictor():
    # 팩터가 forward return 과 동일 랭크 → 횡단면 IC ≈ 1
    from api.quant.alpha.ic_backtest import cross_sectional_ic
    rng = np.random.RandomState(1)
    fwd = pd.Series(rng.normal(size=20), index=[f"T{i}" for i in range(20)])
    perfect_factor = fwd.copy()  # 동일 랭크
    ic = cross_sectional_ic(perfect_factor, fwd)
    assert ic is not None and ic > 0.99


def test_alphalens_graceful_when_absent(monkeypatch):
    # alphalens import 실패 시 (None, 메시지) 반환 — 크래시 금지
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.startswith("alphalens"):
            raise ImportError("simulated absent")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    close = _synth_panel()
    fac = cc._compute_factor(close, "momentum", 5)
    mean, err = cc._alphalens_mean_ic(fac, close, 5)
    assert mean is None
    assert err is not None and "alphalens" in err


@pytest.mark.skipif(
    pytest.importorskip("alphalens", reason="alphalens 미설치 — cross-check skip") is None,
    reason="alphalens 미설치",
)
def test_alphalens_converges_on_synthetic():
    # alphalens 설치 시: 합성 패널에서 self ↔ alphalens IC 가 수렴해야 함
    close = _synth_panel(n_tickers=40, n_days=120, seed=3)
    fac = cc._compute_factor(close, "momentum", 20)
    from api.intelligence.ic_stats import newey_west_tstat
    self_ics = cc._self_ic_series(fac, close, horizon=5)
    self_mean = newey_west_tstat(self_ics, horizon_days=5).get("mean_ic")
    al_mean, err = cc._alphalens_mean_ic(fac, close, 5)
    if al_mean is None:
        pytest.skip(f"alphalens 산출 불가: {err}")
    assert abs(self_mean - al_mean) < cc.DIVERGENCE_TOL
