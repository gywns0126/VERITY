# -*- coding: utf-8 -*-
"""사전등록 반증 조건 검사 (2026-08-24 신설).

## 왜

PM 이 XE 매수 직후 "매매 결정이 별로였나" 라고 물었다. 하루치 −3.5% 는 이 종목 실현 일간
표준편차 6.25% 의 0.56σ 라 결정 품질의 증거가 아니다(|등락|≥3.5% 가 62일 중 37일).
그 시점에 값이 있는 일은 **무엇이 이 결정을 틀린 것으로 만들지를 미리 고정**하는 것뿐이고,
고정한 조건은 검사기가 없으면 장식이 된다.

## 여기서 고정하는 것

- 🚨 **C1 은 pct 가 아니라 shares 로 본다.** 희석이 일어나면 매도 없이도 pct 가 내려간다 —
  pct 하락을 매도로 읽으면 "아마존이 팔았다" 는 오답이 나온다.
- 결측은 `no_obs` 로 남기고 **0 으로 채우지 않는다**.
- 자동으로 못 보는 조건은 `manual` 로 **드러낸다**. 자동인 척하면 아무도 안 본다.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent


def _m():
    spec = importlib.util.spec_from_file_location(
        "fc", str(_ROOT / "scripts" / "watch" / "falsification_check.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


BASE = 65836948
CRIT = {"id": "C1", "label": "아마존 지분 이탈", "baseline": BASE}


def _obs(shares, pct=22.9, filer="Amazon.com, Inc."):
    return {"holdings_as_of": "2026-08-17",
            "holders": [{"filer": filer, "pct": pct, "shares": shares},
                        {"filer": "Ares Partners Holdco LLC", "pct": 12.3, "shares": 38263341}]}


def test_unchanged_holds():
    r = _m().check_c1(CRIT, _obs(BASE))
    assert r["state"] == "hold"
    assert r["delta_shares"] == 0


def test_small_decrease_is_watch_not_trip():
    """감소했으나 반증 임계(-20%) 미만 = 1차 경보이지 반증 성립이 아니다."""
    r = _m().check_c1(CRIT, _obs(int(BASE * 0.9)))
    assert r["state"] == "watch"
    assert -11 < r["delta_pct"] < -9


def test_large_decrease_trips():
    r = _m().check_c1(CRIT, _obs(int(BASE * 0.75)))
    assert r["state"] == "trip"


def test_exit_from_13g_list_trips():
    r = _m().check_c1(CRIT, _obs(BASE, filer="Someone Else LLC"))
    assert r["state"] == "trip"
    assert "이탈" in r["detail"]


def test_dilution_only_pct_drop_does_not_trip():
    """🚨 핵심 회귀 방지 — 주식수 그대로인데 pct 만 22.9 → 18.0 으로 내려간 경우.

    희석이다. 매도가 아니다. shares 기준이라 hold 로 남아야 한다.
    """
    r = _m().check_c1(CRIT, _obs(BASE, pct=18.0))
    assert r["state"] == "hold", "pct 하락을 매도로 읽었다 — 희석과 매도를 구분하지 못한다"
    assert r["pct_reported"] == 18.0


def test_missing_shares_is_not_zero():
    r = _m().check_c1(CRIT, _obs(None))
    assert r["state"] == "no_obs"


def test_no_observation_row():
    r = _m().check_c1(CRIT, None)
    assert r["state"] == "no_obs"
