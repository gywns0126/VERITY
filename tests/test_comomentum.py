"""
test_comomentum.py — CoMOM(Lou-Polk 2022) 코어 + FF3 파싱 정밀 검증.

공통성분 decile → 높은 CoMOM / 독립 → 0 근처 / FF3 잔차화가 팩터 제거 / leg 평균 / edge.
"""
import numpy as np
import pandas as pd
import pytest

from api.quant.alpha import comomentum as CM
from api.quant.alpha import ff3_factors as FF


@pytest.fixture
def flat_ff3():
    """60주 near-zero FF3 → 잔차 ≈ demeaned return (상관 통제 용이)."""
    idx = pd.date_range("2025-01-03", periods=60, freq="W-FRI")
    return pd.DataFrame({"mkt_rf": 0.0, "smb": 0.0, "hml": 0.0, "rf": 0.0}, index=idx)


def _returns(idx, d):
    return {t: pd.Series(v, index=idx) for t, v in d.items()}


def test_high_comom_common_factor(flat_ff3):
    idx = flat_ff3.index
    rng = np.random.default_rng(0)
    common = rng.normal(0, 0.03, len(idx))
    rets = {f"S{i}": common + rng.normal(0, 0.002, len(idx)) for i in range(5)}  # 강한 공통성분
    out = CM.compute_comom(_returns(idx, rets), {"momentum": {"top": list(rets), "bottom": []}}, flat_ff3)
    cw = out["momentum"]["comom_winner"]
    assert cw is not None and cw > 0.8  # 공통성분 지배 → 높은 crowding


def test_low_comom_independent(flat_ff3):
    idx = flat_ff3.index
    rng = np.random.default_rng(1)
    rets = {f"S{i}": rng.normal(0, 0.03, len(idx)) for i in range(6)}  # 독립
    out = CM.compute_comom(_returns(idx, rets), {"value": {"top": list(rets), "bottom": []}}, flat_ff3)
    cw = out["value"]["comom_winner"]
    assert cw is not None and abs(cw) < 0.4  # 독립 → 0 근처


def test_comom_averages_two_legs(flat_ff3):
    idx = flat_ff3.index
    rng = np.random.default_rng(2)
    cw_sig = rng.normal(0, 0.03, len(idx))
    cl_sig = rng.normal(0, 0.03, len(idx))
    top = {f"W{i}": cw_sig + rng.normal(0, 0.002, len(idx)) for i in range(4)}
    bot = {f"L{i}": cl_sig + rng.normal(0, 0.002, len(idx)) for i in range(4)}
    out = CM.compute_comom(_returns(idx, {**top, **bot}), {"mom": {"top": list(top), "bottom": list(bot)}}, flat_ff3)["mom"]
    assert out["comom"] is not None and out["n_winner"] == 4 and out["n_loser"] == 4
    assert abs(out["comom"] - 0.5 * (out["comom_winner"] + out["comom_loser"])) < 1e-6  # eq.3


def test_ff3_residual_removes_factor():
    """종목 = 2·Mkt-RF + noise → 잔차가 팩터 제거(분산↓) + noise 와 강상관."""
    idx = pd.date_range("2025-01-03", periods=60, freq="W-FRI")
    rng = np.random.default_rng(3)
    mkt = rng.normal(0, 0.02, 60)
    noise = rng.normal(0, 0.005, 60)
    ff3 = pd.DataFrame({"mkt_rf": mkt, "smb": 0.0, "hml": 0.0, "rf": 0.0}, index=idx)
    resid = CM.ff3_residual(pd.Series(2.0 * mkt + noise, index=idx), ff3)
    assert resid is not None
    assert resid.var() < (2.0 * mkt + noise).var()  # 팩터 제거
    assert np.corrcoef(resid.to_numpy(), noise)[0, 1] > 0.9  # 잔차 ≈ noise


def test_too_few_stocks_none(flat_ff3):
    idx = flat_ff3.index
    wr = _returns(idx, {"A": np.full(len(idx), 0.01), "B": np.full(len(idx), 0.01)})  # 2 < MIN_DECILE_N
    out = CM.compute_comom(wr, {"f": {"top": ["A", "B"], "bottom": []}}, flat_ff3)
    assert out["f"]["comom_winner"] is None and out["f"]["comom"] is None


def test_insufficient_overlap_none(flat_ff3):
    idx = flat_ff3.index[:10]  # 10주 < MIN_OVERLAP
    rng = np.random.default_rng(4)
    rets = {f"S{i}": rng.normal(0, 0.03, 10) for i in range(4)}
    out = CM.compute_comom(_returns(idx, rets), {"f": {"top": list(rets), "bottom": []}}, flat_ff3)
    assert out["f"]["comom_winner"] is None


def test_ff3_parse_pct_to_decimal():
    txt = ("junk\nThis file created...\n,Mkt-RF,SMB,HML,RF\n"
           "19260702,    1.58,   -0.62,   -0.86,    0.06\n"
           "19260710,    0.37,   -0.90,    0.31,    0.06\n\n"
           "  Annual Factors:\n,Mkt-RF\n1926,  9.9\n")
    df = FF._parse_ff3_csv(txt)
    assert len(df) == 2  # 주간 2행만 (annual 섹션 중단)
    assert abs(df.iloc[0]["mkt_rf"] - 0.0158) < 1e-9  # % → 소수
    assert list(df.columns) == ["mkt_rf", "smb", "hml", "rf"]
