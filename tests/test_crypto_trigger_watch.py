# -*- coding: utf-8 -*-
"""크립토 트리거 감시 계약 — 2026-08-22 신설.

## 왜

8/20~22 BTC +20% 급등 때 "무엇이 바뀌면 판단을 바꾸나" 가 사람 머릿속에만 있었다.
그걸 기계로 옮기면서 지켜야 하는 선이 두 개다:

🚨 **① 전이만 알린다.** 조건이 지속되는 동안 매일 울리면 알림이 잡음이 되고,
   잡음이 되면 아무도 안 본다(RULE 1 계열). 그래서 직전 CONFIRM_DAYS 일을 대조한다.

🚨 **② 부재를 0으로 읽지 않는다.** 수집 실패로 값이 없는 것과 값이 0인 것은 다른 사건이다.
   ETF 순유입이 없어서 None 인 걸 0 으로 읽으면 "순유출 아님" 으로 조용히 넘어간다.
   그리고 3종이 전부 부재면 **exit 1** — 발화 0 으로 끝내면 그게 침묵 실패다.

레짐 call 전이를 안 넣은 이유는 모듈 docstring 참조(60일에 23회 전환 = 2.6일마다 1회).
"""
from __future__ import annotations

import datetime
import importlib.util
import json
import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
_spec = importlib.util.spec_from_file_location(
    "ctw", os.path.join(_ROOT, "scripts", "audit", "crypto_trigger_watch.py"))
ctw = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ctw)

from api.builders.crypto_regime_synthesis import FNG_EXTREME_GREED  # noqa: E402
from api.config import CRYPTO_FUNDING_OVERHEAT  # noqa: E402


def _day(n):
    return (datetime.date(2026, 8, 22) - datetime.timedelta(days=n)).isoformat()


def _row(n, fng=50.0, funding=0.01, etf=1e8):
    return {"date": _day(n), "fng": fng, "funding_pct": funding, "etf_net_usd": etf}


def _titles(fired):
    return [t for t, _ in fired]


class TestThresholdsAreReused:
    """🚨 새 숫자 0개 — 임계는 전부 기존 상수여야 한다. 지어낸 값이 섞이면 두 정의가 갈라진다."""

    def test_fng_uses_existing_constant(self):
        assert FNG_EXTREME_GREED == 75

    def test_funding_uses_existing_constant(self):
        assert CRYPTO_FUNDING_OVERHEAT == 0.06

    def test_confirm_days_is_the_only_arbitrary_value(self):
        """유일한 임의값이고 1회 고정 — 바뀌면 이 테스트가 먼저 깨진다."""
        assert ctw.CONFIRM_DAYS == 3


class TestTransitionNotState:
    def test_fires_on_entry(self):
        hist = [_row(3), _row(2), _row(1)]
        fired = ctw.evaluate(_row(0, fng=76.0), hist)
        assert "FNG 과열 진입" in _titles(fired)

    def test_does_not_fire_while_sustained(self):
        """🚨 어제도 과열이었으면 오늘은 전이가 아니다 — 매일 울리면 잡음이 된다."""
        hist = [_row(3), _row(2), _row(1, fng=78.0)]
        fired = ctw.evaluate(_row(0, fng=76.0), hist)
        assert "FNG 과열 진입" not in _titles(fired)

    def test_refires_after_cooling_beyond_confirm_days(self):
        """CONFIRM_DAYS 를 넘겨 식었다가 다시 오르면 새 전이다."""
        hist = [_row(5, fng=80.0), _row(4), _row(3), _row(2), _row(1)]
        fired = ctw.evaluate(_row(0, fng=76.0), hist)
        assert "FNG 과열 진입" in _titles(fired)

    def test_below_threshold_never_fires(self):
        fired = ctw.evaluate(_row(0, fng=74.9), [_row(1)])
        assert "FNG 과열 진입" not in _titles(fired)


class TestFundingAndEtf:
    def test_funding_overheat_fires(self):
        fired = ctw.evaluate(_row(0, funding=0.07), [_row(1), _row(2)])
        assert "펀딩 과열 진입" in _titles(fired)

    def test_funding_at_threshold_fires(self):
        fired = ctw.evaluate(_row(0, funding=CRYPTO_FUNDING_OVERHEAT), [_row(1)])
        assert "펀딩 과열 진입" in _titles(fired)

    def test_etf_outflow_fires(self):
        fired = ctw.evaluate(_row(0, etf=-2.5e8), [_row(1), _row(2)])
        assert "ETF 순유출 전환" in _titles(fired)

    def test_etf_inflow_does_not_fire(self):
        fired = ctw.evaluate(_row(0, etf=4.9e8), [_row(1)])
        assert "ETF 순유출 전환" not in _titles(fired)


class TestAbsenceIsNotZero:
    """🚨 값 부재와 값 0 은 다른 사건이다. 섞으면 수집 실패가 '정상' 으로 위장된다."""

    def test_missing_fng_does_not_fire(self):
        fired = ctw.evaluate({"date": _day(0), "fng": None, "funding_pct": 0.01, "etf_net_usd": 1e8},
                             [_row(1)])
        assert "FNG 과열 진입" not in _titles(fired)

    def test_missing_etf_is_not_read_as_outflow(self):
        """None 을 0 으로 읽으면 '순유출 아님' 이 되어 조용히 넘어간다 — 반대로도 위험하다."""
        fired = ctw.evaluate({"date": _day(0), "fng": 50.0, "funding_pct": 0.01, "etf_net_usd": None},
                             [_row(1)])
        assert "ETF 순유출 전환" not in _titles(fired)

    def test_history_row_with_missing_value_does_not_suppress(self):
        """이력에 결측이 있어도 그걸 '이미 발화' 로 오독해 진짜 전이를 삼키면 안 된다."""
        hist = [{"date": _day(1), "fng": None, "funding_pct": None, "etf_net_usd": None}]
        fired = ctw.evaluate(_row(0, fng=80.0), hist)
        assert "FNG 과열 진입" in _titles(fired)


class TestBuybackReminder:
    def test_fires_at_d3_and_d0_only(self, monkeypatch):
        for delta, expect in ((3, True), (0, True), (2, False), (5, False), (-1, False)):
            target = ctw.BUYBACK_DATE - datetime.timedelta(days=delta)
            monkeypatch.setattr(ctw, "_now",
                                lambda t=target: datetime.datetime(t.year, t.month, t.day, tzinfo=ctw.KST))
            fired = ctw.evaluate(_row(0), [_row(1)])
            hit = any("바이백" in t for t in _titles(fired))
            assert hit is expect, f"D-{delta} 발화 {hit} (기대 {expect})"

    def test_date_is_external_not_estimated(self):
        """🚨 우리 추정이 아니라 외부 확정 날짜다 — 바꾸려면 출처가 바뀌어야 한다."""
        assert ctw.BUYBACK_DATE == datetime.date(2026, 9, 9)
