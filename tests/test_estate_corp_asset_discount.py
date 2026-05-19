"""GET /api/estate/corp-asset-discount commercial cross-link — 단위 테스트.

검증: _build_commercial_market 로 sector_pulse payload → commercial cross-link 합성.
network 의존 _fetch_commercial_market 는 별도 검증 (env 부재 시 None 반환).
"""
from __future__ import annotations

import importlib.util
import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_EP_PATH = os.path.join(_REPO_ROOT, "vercel-api", "api", "estate_corp_asset_discount.py")

_spec = importlib.util.spec_from_file_location("ep_corp_asset_discount", _EP_PATH)
ep = importlib.util.module_from_spec(_spec)
sys.modules["ep_corp_asset_discount"] = ep
_spec.loader.exec_module(ep)


def _payload(sectors):
    return {
        "schema_version": "v0",
        "generated_at": "2026-05-19T00:00:00+09:00",
        "sectors": sectors,
    }


class TestBuildCommercialMarket:
    def test_extracts_office_retail_only(self):
        out = ep._build_commercial_market(_payload([
            {"key": "residential_apt", "verdict": "BULLISH"},
            {"key": "office", "name": "오피스", "verdict": "NEUTRAL", "yoy_change_pct": 1.89, "yield_pct": 1.8},
            {"key": "retail_mid_large", "name": "중대형 상가", "verdict": "NEUTRAL", "yoy_change_pct": -0.24, "yield_pct": 0.99},
            {"key": "officetel", "verdict": "BULLISH"},
        ]))
        assert {s["key"] for s in out["sectors"]} == {"office", "retail_mid_large"}
        assert out["verdict"] == "NEUTRAL"
        assert out["generated_at"] == "2026-05-19T00:00:00+09:00"

    def test_bearish_any_dominates(self):
        out = ep._build_commercial_market(_payload([
            {"key": "office", "verdict": "BULLISH"},
            {"key": "retail_mid_large", "verdict": "BEARISH"},
        ]))
        assert out["verdict"] == "BEARISH"

    def test_all_bullish(self):
        out = ep._build_commercial_market(_payload([
            {"key": "office", "verdict": "BULLISH"},
            {"key": "retail_mid_large", "verdict": "BULLISH"},
        ]))
        assert out["verdict"] == "BULLISH"

    def test_all_unavailable(self):
        out = ep._build_commercial_market(_payload([
            {"key": "office", "verdict": "UNAVAILABLE"},
            {"key": "retail_mid_large", "verdict": "UNAVAILABLE"},
        ]))
        assert out["verdict"] == "UNAVAILABLE"

    def test_no_commercial_sectors_returns_none(self):
        out = ep._build_commercial_market(_payload([
            {"key": "residential_apt", "verdict": "BULLISH"},
            {"key": "officetel", "verdict": "BULLISH"},
        ]))
        assert out is None

    def test_invalid_payload_returns_none(self):
        assert ep._build_commercial_market(None) is None
        assert ep._build_commercial_market({"sectors": "not-a-list"}) is None
        assert ep._build_commercial_market({}) is None

    def test_sector_fields_preserved(self):
        out = ep._build_commercial_market(_payload([
            {"key": "office", "name": "오피스", "verdict": "NEUTRAL",
             "yoy_change_pct": 1.89, "yield_pct": 1.8},
            {"key": "retail_mid_large", "name": "중대형 상가", "verdict": "NEUTRAL",
             "yoy_change_pct": -0.24, "yield_pct": 0.99},
        ]))
        office = next(s for s in out["sectors"] if s["key"] == "office")
        assert office["name"] == "오피스"
        assert office["yoy_change_pct"] == 1.89
        assert office["yield_pct"] == 1.8


class TestFetchCommercialMarketNoEnv:
    def test_returns_none_when_env_missing(self, monkeypatch):
        monkeypatch.delenv("ESTATE_SECTOR_PULSE_SOURCE_URL", raising=False)
        assert ep._fetch_commercial_market() is None

    def test_returns_none_when_env_empty(self, monkeypatch):
        monkeypatch.setenv("ESTATE_SECTOR_PULSE_SOURCE_URL", "")
        assert ep._fetch_commercial_market() is None
