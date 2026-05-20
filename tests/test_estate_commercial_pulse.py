"""GET /api/estate/commercial-pulse endpoint — 단위 테스트.

검증:
  - _extract_commercial: office + retail_mid_large 만 추출
  - _aggregate_verdict: BEARISH > UNAVAILABLE > NEUTRAL > BULLISH 보수 합성
  - _compute_yoy_spread / _compute_yield_spread
  - _data_partial_flag: yield None or verdict UNAVAILABLE
  - _build_response 전체 schema
"""
from __future__ import annotations

import importlib.util
import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_EP_PATH = os.path.join(_REPO_ROOT, "vercel-api", "api", "estate_commercial_pulse.py")

_spec = importlib.util.spec_from_file_location("ep_commercial_pulse", _EP_PATH)
ep = importlib.util.module_from_spec(_spec)
sys.modules["ep_commercial_pulse"] = ep
_spec.loader.exec_module(ep)


def _payload(sectors_data):
    """test fixture builder."""
    return {
        "schema_version": "v0",
        "generated_at": "2026-05-19T00:00:00+09:00",
        "overall_verdict": "NEUTRAL",
        "sectors": sectors_data,
    }


class TestExtractCommercial:
    def test_filters_to_office_and_retail(self):
        payload = _payload([
            {"key": "residential_apt", "name": "아파트"},
            {"key": "office", "name": "오피스"},
            {"key": "retail_mid_large", "name": "중대형 상가"},
            {"key": "officetel", "name": "오피스텔"},
        ])
        out = ep._extract_commercial(payload)
        assert len(out) == 2
        assert {s["key"] for s in out} == {"office", "retail_mid_large"}

    def test_empty_input(self):
        assert ep._extract_commercial({"sectors": []}) == []

    def test_no_commercial_keys(self):
        payload = _payload([{"key": "residential_apt"}, {"key": "officetel"}])
        assert ep._extract_commercial(payload) == []


class TestAggregateVerdict:
    def test_all_unavailable(self):
        assert ep._aggregate_verdict([{"verdict": "UNAVAILABLE"}, {"verdict": "UNAVAILABLE"}]) == "UNAVAILABLE"

    def test_any_bearish_dominates(self):
        assert ep._aggregate_verdict([{"verdict": "BULLISH"}, {"verdict": "BEARISH"}]) == "BEARISH"
        assert ep._aggregate_verdict([{"verdict": "NEUTRAL"}, {"verdict": "BEARISH"}]) == "BEARISH"

    def test_all_bullish(self):
        assert ep._aggregate_verdict([{"verdict": "BULLISH"}, {"verdict": "BULLISH"}]) == "BULLISH"

    def test_mixed_neutral_bullish(self):
        assert ep._aggregate_verdict([{"verdict": "NEUTRAL"}, {"verdict": "BULLISH"}]) == "NEUTRAL"

    def test_empty(self):
        assert ep._aggregate_verdict([]) == "UNAVAILABLE"


class TestYoyAndYieldSpread:
    def test_yoy_spread_both_present(self):
        sectors = [
            {"key": "office", "yoy_change_pct": 1.89},
            {"key": "retail_mid_large", "yoy_change_pct": -0.5},
        ]
        out = ep._compute_yoy_spread(sectors)
        assert out["spread_pct"] == 2.39
        assert out["office_yoy_pct"] == 1.89
        assert out["retail_yoy_pct"] == -0.5

    def test_yoy_spread_missing(self):
        sectors = [
            {"key": "office", "yoy_change_pct": 1.89},
            {"key": "retail_mid_large", "yoy_change_pct": None},
        ]
        out = ep._compute_yoy_spread(sectors)
        assert out["spread_pct"] is None
        assert out["reason"] == "missing_yoy_in_one_or_both"

    def test_yield_spread_both_present(self):
        sectors = [
            {"key": "office", "yield_pct": 1.2},
            {"key": "retail_mid_large", "yield_pct": 0.8},
        ]
        out = ep._compute_yield_spread(sectors)
        assert out["spread_pct"] == 0.4

    def test_yield_spread_missing(self):
        sectors = [
            {"key": "office", "yield_pct": None},
            {"key": "retail_mid_large", "yield_pct": 0.8},
        ]
        out = ep._compute_yield_spread(sectors)
        assert out["spread_pct"] is None

    def test_spread_returns_none_when_sector_missing(self):
        assert ep._compute_yoy_spread([{"key": "office"}]) is None
        assert ep._compute_yield_spread([{"key": "retail_mid_large"}]) is None


class TestDataPartialFlag:
    def test_all_complete(self):
        sectors = [
            {"verdict": "NEUTRAL", "yield_pct": 1.2},
            {"verdict": "BULLISH", "yield_pct": 0.8},
        ]
        assert ep._data_partial_flag(sectors) is False

    def test_one_unavailable_marks_partial(self):
        sectors = [
            {"verdict": "NEUTRAL", "yield_pct": 1.2},
            {"verdict": "UNAVAILABLE", "yield_pct": None},
        ]
        assert ep._data_partial_flag(sectors) is True

    def test_missing_yield_marks_partial(self):
        sectors = [
            {"verdict": "NEUTRAL", "yield_pct": None},
            {"verdict": "BULLISH", "yield_pct": 0.8},
        ]
        assert ep._data_partial_flag(sectors) is True


class TestBuildResponse:
    def test_full_schema(self):
        payload = _payload([
            {"key": "residential_apt", "verdict": "BULLISH"},
            {"key": "office", "verdict": "NEUTRAL", "yoy_change_pct": 1.89, "yield_pct": None},
            {"key": "retail_mid_large", "verdict": "UNAVAILABLE", "yoy_change_pct": None, "yield_pct": None},
        ])
        out = ep._build_response(payload)
        assert out["schema_version"] == "v0.1"
        assert out["commercial_verdict"] == "NEUTRAL"  # NEUTRAL + UNAVAILABLE → NEUTRAL (UNAVAILABLE 단독 X)
        assert out["data_partial"] is True
        assert out["has_stale"] is False  # stale 섹터 없음
        assert len(out["sectors"]) == 2
        assert out["yoy_spread"]["spread_pct"] is None  # retail YoY 부재
        assert out["source_pulse_overall_verdict"] == "NEUTRAL"


class TestHasStaleFlag:
    def test_no_stale(self):
        sectors = [
            {"verdict": "NEUTRAL", "yield_pct": 1.2},
            {"verdict": "BULLISH", "yield_pct": 0.8},
        ]
        assert ep._has_stale_flag(sectors) is False

    def test_one_stale(self):
        sectors = [
            {"verdict": "NEUTRAL", "yield_pct": 1.2, "stale": True, "stale_reason": "transient"},
            {"verdict": "BULLISH", "yield_pct": 0.8},
        ]
        assert ep._has_stale_flag(sectors) is True

    def test_stale_orthogonal_to_partial(self):
        """stale=True 인데 yield 존재 = 값 있는 stale → has_stale True, data_partial False."""
        sectors = [
            {"verdict": "NEUTRAL", "yield_pct": 0.99, "stale": True},
            {"verdict": "BULLISH", "yield_pct": 1.8},
        ]
        assert ep._has_stale_flag(sectors) is True
        assert ep._data_partial_flag(sectors) is False

    def test_build_response_surfaces_has_stale(self):
        payload = _payload([
            {"key": "office", "verdict": "BULLISH", "yoy_change_pct": 1.89, "yield_pct": 1.8},
            {"key": "retail_mid_large", "verdict": "NEUTRAL", "yoy_change_pct": -0.24,
             "yield_pct": 0.99, "stale": True, "stale_reason": "R-ONE transient", "as_of": "2026년 1분기"},
        ])
        out = ep._build_response(payload)
        assert out["has_stale"] is True
        # per-sector stale 패스스루 확인
        retail = next(s for s in out["sectors"] if s["key"] == "retail_mid_large")
        assert retail["stale"] is True and retail["as_of"] == "2026년 1분기"
