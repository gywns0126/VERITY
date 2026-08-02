"""중용 3층 빌더 단위테스트 — PREREG_MODERATION_PORTFOLIO (상수 승인 2026-08-02). 합성 데이터, 파일 IO 없음."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.portfolio.moderation_portfolio import (  # noqa: E402
    MAX_POS,
    exclude_extremes,
    final_weights,
    layer2_sleeve,
    layer3_scale,
    ledoit_wolf_cc,
)

rng = np.random.default_rng(42)


def _rec(tk, **kw):
    base = {"ticker": tk, "name": tk, "currency": "KRW", "per": 12.0, "pbr": 1.2,
            "debt_ratio": 80.0, "current_ratio": 1.5, "drop_from_high_pct": -20.0,
            "market_cap": 1e12, "dart_disclosure_events": {"severity": 1}}
    base.update(kw)
    return base


def test_lw_delta_bounds_and_diag_preserved():
    X = rng.normal(0, 0.02, size=(200, 6))
    sigma, delta = ledoit_wolf_cc(X)
    S = np.cov(X.T, bias=True)
    assert 0.0 <= delta <= 1.0
    assert np.allclose(np.diag(sigma), np.diag(S), rtol=1e-8)   # 상수상관 타깃 = 대각 보존
    assert np.allclose(sigma, sigma.T, atol=1e-12)


def test_layer2_lowvol_gets_more_weight():
    T, d = 250, 12
    vols = np.full(d, 0.03)
    vols[0] = 0.008                                             # 저변동 자산
    X = rng.normal(0, 1, size=(T, d)) * vols
    w, sigma, meta = layer2_sleeve(X)
    assert abs(w.sum() - 1.0) < 1e-9
    assert w[0] == w.max()                                      # 최소분산 성분이 저변동에 가중
    assert meta["method"].startswith("LW")


def test_layer2_short_history_falls_back_equal_weight():
    X = rng.normal(0, 0.02, size=(30, 8))                       # T<60
    w, _, meta = layer2_sleeve(X)
    assert np.allclose(w, 1.0 / 8)
    assert "fallback" in meta["method"]


def test_layer3_quarter_kelly_binds_at_20pct_vol():
    """연 20% 변동성 → g_vol=0.6, g_kelly=0.25·0.04/0.04=0.25 → gross 0.25 (quarter_kelly)."""
    d = 4
    w = np.full(d, 0.25)
    daily_var = (0.20 ** 2) / 252
    sigma = np.eye(d) * daily_var * d                            # w'Σw = daily_var 정합
    out = layer3_scale(w, sigma)
    assert abs(out["portfolio_vol_annual"] - 0.20) < 0.005
    assert abs(out["gross_pre_cap"] - 0.25) < 0.01
    assert out["bind"] == "quarter_kelly"


def test_layer3_no_leverage_cap_at_low_vol():
    """연 ~9% 변동성 → g_vol>1, g_kelly>1 → gross=1.0 (no_leverage)."""
    d = 4
    w = np.full(d, 0.25)
    daily_var = (0.09 ** 2) / 252
    sigma = np.eye(d) * daily_var * d
    out = layer3_scale(w, sigma)
    assert out["gross_pre_cap"] == 1.0
    assert out["bind"] == "no_leverage"


def test_final_weights_total_cap_excess_to_cash():
    """총자산 10% 상한 — gross 후 적용, 초과분 재배분 없이 현금."""
    w_sleeve = np.array([0.5, 0.3, 0.2])
    out = final_weights(w_sleeve, gross=0.9)
    assert np.allclose(out, [MAX_POS, MAX_POS, MAX_POS])         # 0.45/0.27/0.18 → 전부 0.10
    assert out.sum() < 0.9                                       # 초과분 = 현금 (레버리지 없음)


def test_exclusions_asymmetric_and_missing_safe():
    recs = [_rec(f"t{i:02d}", per=10 + i, pbr=1.0 + i * 0.05, debt_ratio=50 + i * 10,
                 current_ratio=3.0 - i * 0.1, drop_from_high_pct=-5 - i * 3,
                 market_cap=1e12 - i * 4e10) for i in range(20)]
    recs[19]["dart_disclosure_events"] = {"severity": 3}         # sev3 → E1
    recs[5]["per"] = 999.0                                       # PER 극단 (PBR 은 평범) → 비대칭 생존
    missing = _rec("miss", per=None, pbr=None, debt_ratio=None, current_ratio=None,
                   drop_from_high_pct=None, market_cap=None)
    recs.append(missing)

    keep, excluded = exclude_extremes(recs)
    ex = {e["ticker"]: e["reason"] for e in excluded}
    assert "t19" in ex and "E1" in ex["t19"]                     # sev3
    assert "t05" not in ex                                       # PER 단독 = 배제 아님(AND 조건)
    assert any("E2" in r for r in ex.values())                   # 최심 낙폭 존재
    assert any("E4" in r for r in ex.values())                   # 최소 시총 존재
    assert "miss" in [r["ticker"] for r in keep]                 # 결측 = 벌하지 않음


def test_exclusions_small_sample_rule_off():
    recs = [_rec(f"s{i}") for i in range(4)]                     # 유효표본 <5 → 전 룰 미적용
    keep, excluded = exclude_extremes(recs)
    assert len(keep) == 4 and excluded == []


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as e:
                fails += 1
                print(f"FAIL {name}: {e}")
    sys.exit(1 if fails else 0)
