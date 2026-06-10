"""_compute_capital_flow NaN 가드 회귀 검증.

배경: yfinance 가 NaN close 를 반환하면 change_pct=NaN 이 전파된다.
  무-ndigits round() 두 곳 — _to_score(round(50+chg*8)) 과 kr10_yoy adj
  (round(float(kr10_yoy)*4)) — 가 `round(NaN)` → ValueError("cannot convert
  float NaN to integer") 로 capital_flow 스코어링 전체를 죽인다.

  round(x, 3) (ndigits 有) 은 NaN 을 안전 반환하므로 _avg / usd_chg 경로는
  크래시 클래스가 아니다 — 이 회귀는 무-ndigits round 두 지점만 커버.

검증:
  - 전 자산 change_pct=NaN → ValueError 없이 dict 반환, 점수 중립 50
  - 일부 NaN + 일부 정상 → NaN 만 제외하고 정상값으로 평균
  - kr10_yoy=NaN → bond adj 스킵 (ValueError 없음)
  - 정상 입력 동작 불변 (회귀 baseline)
"""
from __future__ import annotations

import math

import pytest

# 2026-06-11 flaky fix: 기존엔 importlib 로 macro_data.py 를 별 이름("macro_data_under_test")으로
#   새로 exec → 무거운 collector 의 이중 module 로드 = 풀suite 에서 sys.modules 오염/import-order
#   fragility 로 간헐 실패. 표준 cached import 로 교체(단일 module, robust). _compute_capital_flow 동일.
from api.collectors import macro_data as md

_NAN = float("nan")
_ASSET_KEYS = [
    "gold", "silver", "copper", "wti_oil",  # commodities
    "us_10y", "us_2y",                        # bonds
    "sp500", "nasdaq",                        # equities
]


def _data(changes: dict, **extra) -> dict:
    """change_pct 매핑 → _compute_capital_flow 입력 dict."""
    out = {k: {"change_pct": v} for k, v in changes.items()}
    out.update(extra)
    return out


def test_all_nan_returns_neutral_no_crash():
    """전 자산 NaN → ValueError 없이 중립 50 점수."""
    data = _data({k: _NAN for k in _ASSET_KEYS})
    res = md._compute_capital_flow(data)  # ValueError 면 여기서 터짐
    for sector in ("commodities", "bonds", "equities"):
        assert res[sector]["score"] == 50
        # change_pct 는 전부 무효 → _avg 가 0 반환
        assert res[sector]["change_pct"] == 0


def test_mixed_nan_excluded_from_average():
    """NaN/None 섞인 입력 → 유효값만 평균. round(NaN) 누수 없음."""
    data = _data({
        "gold": 2.0, "silver": _NAN, "copper": None, "wti_oil": 4.0,  # avg=3.0
        "us_10y": _NAN, "us_2y": _NAN,                                  # 전부 무효→0
        "sp500": 1.0, "nasdaq": 1.0,                                    # avg=1.0
    })
    res = md._compute_capital_flow(data)
    assert res["commodities"]["change_pct"] == 3.0
    assert res["commodities"]["score"] == round(50 + 3.0 * 8)  # 74
    assert res["bonds"]["change_pct"] == 0
    assert res["bonds"]["score"] == 50
    assert res["equities"]["change_pct"] == 1.0


def test_kr10y_yoy_nan_skips_bond_adjustment():
    """kr10_yoy=NaN → bond adj round(NaN) 회피, ValueError 없음."""
    data = _data(
        {k: 0.0 for k in _ASSET_KEYS},
        ecos={"korea_gov_10y": {"value": 3.2, "yoy_pp": _NAN}},
    )
    res = md._compute_capital_flow(data)  # 가드 없으면 ValueError
    # NaN adj 스킵 → bond 가산 note 부재
    notes = res.get("ecos_adjustments") or []
    assert not any("KR10Y_yoy" in n for n in notes)


def test_normal_input_unchanged_baseline():
    """정상 입력 동작 불변 — 순수 버그 픽스 회귀 baseline."""
    data = _data({
        "gold": 1.0, "silver": 1.0, "copper": 1.0, "wti_oil": 1.0,  # avg=1.0
        "us_10y": -0.5, "us_2y": -0.5,                               # avg=-0.5
        "sp500": 2.0, "nasdaq": 2.0,                                 # avg=2.0
    })
    res = md._compute_capital_flow(data)
    assert res["commodities"]["score"] == round(50 + 1.0 * 8)   # 58
    assert res["bonds"]["score"] == round(50 + (-0.5) * 8)      # 46
    assert res["equities"]["score"] == round(50 + 2.0 * 8)      # 66
    # 점수 어디에도 NaN 누수 없음
    for sector in ("commodities", "bonds", "equities"):
        assert not math.isnan(res[sector]["score"])
