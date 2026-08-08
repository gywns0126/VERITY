# -*- coding: utf-8 -*-
"""kr_price_axes 백테스트 엔진 계약 테스트.

가격 파생 축은 펀더멘털 축에 없던 함정이 둘 더 있다:
  ① T 종가로 계산한 신호로 T 종가에 사는 것 (거래 불가능한 수익률)
  ② 신호 시점 이후 봉을 stock dict 에 섞어 넣는 것 (look-ahead)
여기에 v1.1 과 공통인 상폐·겹침 함정을 더해 고정한다.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

pytest.importorskip("pandas")

from api.quant.backtest import kr_price_axes as pa  # noqa: E402


def _series(n: int = 300, start: int = 20200102, base: float = 10000.0):
    """단조 상승 합성 시계열 — 인덱스 검증용 (값이 날짜와 1:1 대응)."""
    d = [start + i for i in range(n)]           # 날짜 정합은 불필요, 순서만 쓴다
    c = [base + i for i in range(n)]
    return {"d": d, "o": list(c), "h": [x * 1.01 for x in c],
            "l": [x * 0.99 for x in c], "c": c, "v": [100000.0] * n}


# ── ① T+1 진입 ─────────────────────────────────────────────────────────────
def test_entry_lag_is_one_day():
    """🚨 사전등록 고정값. 0 이면 T 종가 신호로 T 종가에 사는 셈이 된다."""
    assert pa.ENTRY_LAG == 1


def test_forward_return_requires_exact_entry_day():
    """T+1 에 거래가 없으면 진입 불가 — 다른 날 가격으로 대체하지 않는다."""
    s = _series(50)
    missing = s["d"][10]
    s2 = {k: [v for i, v in enumerate(vals) if i != 10] for k, vals in s.items()}
    assert pa.forward_return(s2, missing, s["d"][30], delisted=False, haircut=False) is None


def test_forward_return_uses_entry_day_close():
    s = _series(50)
    r = pa.forward_return(s, s["d"][10], s["d"][30], delisted=False, haircut=False)
    assert r is not None
    expected = s["c"][30] / s["c"][10] - 1.0
    assert r[0] == pytest.approx(expected)
    assert r[1] == "normal"


# ── ② look-ahead ───────────────────────────────────────────────────────────
def test_build_stock_never_sees_future_bars():
    """신호 인덱스 i 이후 봉이 stock dict 에 들어가면 안 된다."""
    s = _series(300)
    i = 200
    st = pa.build_stock("005930", s, i)
    assert st is not None
    assert st["price"] == s["c"][i]
    assert max(st["price_history"]) == s["c"][i]        # 상승 시계열 → 최대 = 현재
    assert st["high_52w"] == s["c"][i]
    assert len(st["price_history"]) <= pa.LOOKBACK


def test_build_stock_momentum_offsets_are_backward():
    s = _series(300)
    i = 280
    st = pa.build_stock("005930", s, i)
    for key, back in pa.MOM_OFFSETS.items():
        assert st[key] == s["c"][i - back], key


def test_build_stock_none_when_too_short():
    s = _series(300)
    assert pa.build_stock("005930", s, 5) is None


def test_build_stock_offsets_none_beyond_history():
    """12개월 전 봉이 없으면 None — 없는 값을 지어내지 않는다."""
    s = _series(60)
    st = pa.build_stock("005930", s, 59)
    assert st["price_12m"] is None and st["price_1m"] is not None


# ── ③ 상폐 처리 ────────────────────────────────────────────────────────────
def test_delisted_scenarios_conservative_is_worse():
    s = _series(50)
    entry = s["d"][10]
    far = s["d"][-1] + 999
    opt = pa.forward_return(s, entry, far, delisted=True, haircut=False)
    con = pa.forward_return(s, entry, far, delisted=True, haircut=True)
    assert opt[1] == "delisted" and con[1] == "delisted"
    assert con[0] < opt[0]
    assert con[0] == pytest.approx(s["c"][-1] * pa.DELIST_HAIRCUT / s["c"][10] - 1.0)


def test_plain_gap_is_dropped_not_scored():
    """소멸 확정이 아닌 공백은 관측을 버린다 — 결측 ≠ 실패."""
    s = _series(50)
    far = s["d"][-1] + 999
    assert pa.forward_return(s, s["d"][10], far, delisted=False, haircut=False) is None


# ── ④ OHLC 0 방어 ──────────────────────────────────────────────────────────
def test_zero_high_low_replaced_by_close(tmp_path):
    """FSC 일부 종목은 시가/고가/저가가 0 이다. 그대로 두면 ATR·볼린저가 폭주한다."""
    import json
    candles = [[20200102 + i, 0, 0, 0, 10000 + i, 5000] for i in range(30)]
    (tmp_path / "005930.json").write_text(
        json.dumps({"t": "005930", "c": candles}), encoding="utf-8")
    px = pa.load_ohlcv(str(tmp_path))
    s = px["005930"]
    assert s["h"] == s["c"] and s["l"] == s["c"] and s["o"] == s["c"]


def test_nonpositive_close_row_dropped(tmp_path):
    import json
    candles = [[20200102 + i, 1, 1, 1, (0 if i == 5 else 10000 + i), 1] for i in range(30)]
    (tmp_path / "005930.json").write_text(
        json.dumps({"t": "005930", "c": candles}), encoding="utf-8")
    s = pa.load_ohlcv(str(tmp_path))["005930"]
    assert len(s["d"]) == 29 and all(c > 0 for c in s["c"])


# ── ⑤ 사전등록 상수 고정 ───────────────────────────────────────────────────
def test_prereg_constants_locked():
    assert pa.AXES == ("technical", "momentum", "volatility", "mean_reversion")
    assert pa.HORIZONS == (20, 60)
    assert pa.BONFERRONI_T == 2.73        # 8검정. 🚨 낮추면 다른 검정이 된다
    assert pa.LOOKBACK == 252             # 운영 period="1y"
    assert pa.SCENARIOS == ("optimistic", "conservative")


def test_bonferroni_stricter_than_fundamental_run():
    """검정이 6 → 8 로 늘었으므로 임계도 엄격해져야 한다."""
    assert pa.BONFERRONI_T > 2.64


# ── ⑥ 운영 함수를 그대로 부르는지 ──────────────────────────────────────────
def test_scores_come_from_production_functions():
    """산식을 자체 구현하지 않았는지 — 직접 구현하면 다른 산식 검정이 된다."""
    src = open(pa.__file__, encoding="utf-8").read()
    for fn in ("compute_momentum_score", "compute_volatility_score",
               "compute_mean_reversion_score", "analyze_technical_from_ohlcv"):
        assert fn in src, fn
    # 지표를 자체 계산하지 않았는지 (RSI/MACD 재구현 금지)
    assert "rolling(" not in src and "ewm(" not in src


def test_axis_scores_are_real_numbers():
    s = _series(300)
    st = pa.build_stock("005930", s, 280)
    got = pa.score_axes(st, [st], {})
    assert set(got) == set(pa.AXES)
    assert all(v is None or 0 <= v <= 100 for v in got.values()), got
