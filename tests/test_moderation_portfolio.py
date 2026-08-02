"""중용 3층 v0 단위테스트 — 등록본(PREREG_MODERATION_PORTFOLIO_2026_08_01) E1~E4 그대로. 합성 데이터."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.portfolio.moderation_portfolio import (  # noqa: E402
    MAX_POS,
    MIN_BREADTH,
    layer1_exclude,
    layer2_sleeve,
    layer3_exposure,
    panic_state,
)

rng = np.random.default_rng(7)


def _rec(tk, **kw):
    base = {"ticker": tk, "name": tk, "currency": "KRW", "pbr": 1.5, "roe": 10.0,
            "debt_ratio": 80.0, "f_score": None}
    base.update(kw)
    return base


def _feats(tks, ret=0.05, vol=0.015):
    return {tk: {"ret_6m": ret, "vol_60d": vol} for tk in tks}


def test_e1_valuetrap_needs_both_legs():
    """E1 = PBR 하위분위 AND (F<=2 | ROE<0). PBR 최하+ROE 양수(F없음) = 생존, PBR 최하+ROE<0 = 배제."""
    recs = [_rec(f"t{i:02d}", pbr=1.0 + i * 0.1) for i in range(20)]
    recs[0]["roe"] = -5.0                       # PBR 최하 + 적자 → E1
    recs[1]["roe"] = 12.0                       # PBR 하위권 + 흑자 → 생존
    keep, ex, flags = layer1_exclude(recs, _feats([r["ticker"] for r in recs]), panic_active=False)
    ex_tk = {e["ticker"] for e in ex}
    assert "t00" in ex_tk and any("E1" in e["reason"] for e in ex if e["ticker"] == "t00")
    assert "t01" not in ex_tk
    assert any("f_score_unavailable" in f for f in flags)


def test_e2_only_fires_in_panic():
    """E2 = 6M 상위분위 AND 패닉. 평시 = 승자 생존(등록: 하위 극단 배제 금지·승자도 평시 생존)."""
    tks = [f"m{i:02d}" for i in range(20)]
    recs = [_rec(tk) for tk in tks]
    feats = {tk: {"ret_6m": 0.02 * i, "vol_60d": 0.015} for i, tk in enumerate(tks)}
    keep_calm, ex_calm, flags_calm = layer1_exclude(recs, feats, panic_active=False)
    assert not any("E2" in e["reason"] for e in ex_calm)
    assert any("E2_dormant" in f for f in flags_calm)
    keep_panic, ex_panic, _ = layer1_exclude(recs, feats, panic_active=True)
    assert any("E2" in e["reason"] and e["ticker"] == "m19" for e in ex_panic)   # 최상위 모멘텀


def test_e3_highvol_and_e4_highdebt():
    tks = [f"v{i:02d}" for i in range(20)]
    recs = [_rec(tk, debt_ratio=50.0 + i * 5) for i, tk in enumerate(tks)]
    feats = {tk: {"ret_6m": 0.05, "vol_60d": 0.01 + 0.001 * i} for i, tk in enumerate(tks)}
    _, ex, _ = layer1_exclude(recs, feats, panic_active=False)
    assert any("E3" in e["reason"] and e["ticker"] == "v19" for e in ex)
    assert any("E4" in e["reason"] and e["ticker"] == "v19" for e in ex)
    assert not any(e["ticker"] == "v00" for e in ex)


def test_missing_fields_not_punished():
    recs = [_rec(f"x{i}") for i in range(10)]
    recs[3].update({"pbr": None, "roe": None, "debt_ratio": None})
    feats = _feats([r["ticker"] for r in recs])
    feats["x3"] = {"ret_6m": None, "vol_60d": None}
    keep, ex, _ = layer1_exclude(recs, feats, panic_active=False)
    assert "x3" in [r["ticker"] for r in keep]


def test_panic_state_insufficient_series():
    active, flag = panic_state([100.0] * 120)
    assert active is False and "insufficient" in flag


def test_panic_state_bear_highvol_fires():
    """합성 3.2년: 후반 2년 하락 + 최근 고변동 → 패닉 True."""
    n = 810
    px = [100.0]
    for i in range(1, n):
        drift = 0.0006 if i < 300 else -0.0012          # 24개월 누적 < 0
        shock = 0.004 if i < n - 70 else 0.025           # 최근 63일 고변동
        px.append(px[-1] * (1 + drift + shock * np.sin(i * 1.7)))
    active, flag = panic_state(px)
    assert flag == "" and active is True


def test_layer2_slsqp_cap_and_lowvol_tilt():
    T, d = 250, 12
    vols = np.full(d, 0.03)
    vols[0] = 0.008
    X = rng.normal(0, 1, size=(T, d)) * vols
    w, sigma, meta = layer2_sleeve(X)
    assert abs(w.sum() - 1.0) < 1e-9
    assert w[0] == w.max()                               # 저변동 틸트
    # 블렌드 상한: 0.5·cap + 0.5·(1/d)
    assert w.max() <= 0.5 * MAX_POS + 0.5 / d + 1e-9
    assert "cap_relaxed" not in meta                     # d=12 >= 10


def test_layer2_small_n_cap_relaxed():
    X = rng.normal(0, 0.02, size=(200, 8))
    w, _, meta = layer2_sleeve(X)
    assert "cap_relaxed" in meta                         # N=8<10 → cap=1/N
    assert abs(w.sum() - 1.0) < 1e-9


def test_layer3_registered_examples():
    """등록 §4 작동 예시: σ 12%→E=0.69 · 20%→0.25 · 8%→1.0."""
    d = 4
    w = np.full(d, 0.25)
    for vol_ann, e_expect, bind in ((0.12, 0.6944, "quarter_kelly"), (0.20, 0.25, "quarter_kelly"), (0.08, 1.0, "no_leverage")):
        sigma = np.eye(d) * (vol_ann ** 2 / 252) * d
        out = layer3_exposure(w, sigma)
        assert abs(out["exposure"] - e_expect) < 0.02, (vol_ann, out)
        assert out["bind"] == bind or e_expect == 1.0


def test_breadth_constant():
    assert MIN_BREADTH == 8


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
