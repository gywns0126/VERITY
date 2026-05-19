"""macro_industry_align 산식 검증.

검증:
  - _tilt_for: mapping 조회 + 없는 경우 0.0
  - _classify_tilt: STRONG_TILT / TILT / NEUTRAL 임계
  - compute_alignment: macro themes → sector_scores, favored/disfavored 추출
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MOD_PATH = os.path.join(_REPO_ROOT, "api", "intelligence", "macro_industry_align.py")

_spec = importlib.util.spec_from_file_location("mia", _MOD_PATH)
mia = importlib.util.module_from_spec(_spec)
sys.modules["mia"] = mia
_spec.loader.exec_module(mia)


@pytest.fixture
def fake_mapping():
    """단순 fixture mapping — 4 sector × 2 category. 산식 검증용."""
    return {
        "sectors": ["Energy", "Financials", "Real Estate", "Utilities"],
        "mappings": {
            "policy": {
                "positive": {  # rate cut
                    "Real Estate": 0.8, "Utilities": 0.6,
                    "Energy": 0.0, "Financials": -0.4,
                },
                "negative": {  # rate hike
                    "Financials": 0.6, "Energy": 0.1,
                    "Utilities": -0.5, "Real Estate": -0.7,
                },
            },
            "inflation": {
                "positive": {  # rising
                    "Energy": 0.8, "Financials": 0.4,
                    "Real Estate": 0.3, "Utilities": -0.3,
                },
                "negative": {
                    "Energy": -0.5, "Financials": -0.3,
                    "Real Estate": -0.2, "Utilities": 0.3,
                },
            },
        },
        "_thresholds": {"strong_tilt": 0.5, "tilt": 0.2},
    }


class TestTiltFor:
    def test_existing(self, fake_mapping):
        assert mia._tilt_for(fake_mapping, "policy", "positive", "Real Estate") == 0.8
        assert mia._tilt_for(fake_mapping, "policy", "negative", "Real Estate") == -0.7
        assert mia._tilt_for(fake_mapping, "inflation", "positive", "Energy") == 0.8

    def test_missing_category(self, fake_mapping):
        assert mia._tilt_for(fake_mapping, "unknown", "positive", "Energy") == 0.0

    def test_missing_direction(self, fake_mapping):
        assert mia._tilt_for(fake_mapping, "policy", "neutral", "Energy") == 0.0

    def test_missing_sector(self, fake_mapping):
        assert mia._tilt_for(fake_mapping, "policy", "positive", "NoSuchSector") == 0.0


class TestClassifyTilt:
    def test_strong(self):
        assert mia._classify_tilt(0.6, 0.5, 0.2) == "STRONG_TILT"
        assert mia._classify_tilt(-0.7, 0.5, 0.2) == "STRONG_TILT"

    def test_tilt(self):
        assert mia._classify_tilt(0.3, 0.5, 0.2) == "TILT"
        assert mia._classify_tilt(-0.4, 0.5, 0.2) == "TILT"

    def test_neutral(self):
        assert mia._classify_tilt(0.1, 0.5, 0.2) == "NEUTRAL"
        assert mia._classify_tilt(0.0, 0.5, 0.2) == "NEUTRAL"


class TestComputeAlignment:
    def test_single_dovish_policy_theme(self, fake_mapping):
        # rate cut high conviction → Real Estate strong favored
        themes = [{"category": "policy", "direction": "positive", "conviction": "high"}]
        out = mia.compute_alignment(themes, mapping=fake_mapping)
        re_sector = next(s for s in out["sectors"] if s["sector"] == "Real Estate")
        # contribution = 1.0 × 0.8 = 0.8 → score = 0.8 / 1 = 0.8 → STRONG_TILT
        assert re_sector["score"] == 0.8
        assert re_sector["tier"] == "STRONG_TILT"
        # Financials = -0.4 → TILT
        fin = next(s for s in out["sectors"] if s["sector"] == "Financials")
        assert fin["score"] == -0.4
        assert fin["tier"] == "TILT"
        # favored + disfavored
        assert "Real Estate" in out["favored"]
        assert "Financials" in out["disfavored"]

    def test_two_themes_averaged(self, fake_mapping):
        # 2 themes same sector → average
        themes = [
            {"category": "policy", "direction": "positive", "conviction": "high"},  # RE +0.8
            {"category": "inflation", "direction": "positive", "conviction": "high"},  # RE +0.3
        ]
        out = mia.compute_alignment(themes, mapping=fake_mapping)
        re_sector = next(s for s in out["sectors"] if s["sector"] == "Real Estate")
        # contributions: (1.0 × 0.8) + (1.0 × 0.3) = 1.1, count=2 → avg 0.55 → STRONG_TILT
        assert re_sector["score"] == 0.55
        assert re_sector["contribution_count"] == 2
        assert re_sector["tier"] == "STRONG_TILT"

    def test_neutral_theme_no_contribution(self, fake_mapping):
        # neutral direction = score 0, contribution 0
        themes = [{"category": "policy", "direction": "neutral", "conviction": "high"}]
        out = mia.compute_alignment(themes, mapping=fake_mapping)
        for s in out["sectors"]:
            assert s["score"] == 0.0
            assert s["contribution_count"] == 0
            assert s["tier"] == "NEUTRAL"

    def test_conviction_weight_applied(self, fake_mapping):
        # low conviction × full tilt → small score
        themes = [{"category": "policy", "direction": "positive", "conviction": "low"}]
        out = mia.compute_alignment(themes, mapping=fake_mapping)
        re_sector = next(s for s in out["sectors"] if s["sector"] == "Real Estate")
        # contribution = 0.3 × 0.8 = 0.24 → score = 0.24 / 1 = 0.24 → TILT (>=0.2)
        assert re_sector["score"] == 0.24
        assert re_sector["tier"] == "TILT"

    def test_low_tilt_below_threshold_is_neutral(self, fake_mapping):
        # mid conviction × small tilt → below 0.2
        themes = [{"category": "policy", "direction": "negative", "conviction": "mid"}]
        out = mia.compute_alignment(themes, mapping=fake_mapping)
        energy = next(s for s in out["sectors"] if s["sector"] == "Energy")
        # contribution = 0.6 × 0.1 = 0.06 → NEUTRAL
        assert energy["score"] == 0.06
        assert energy["tier"] == "NEUTRAL"

    def test_empty_themes(self, fake_mapping):
        out = mia.compute_alignment([], mapping=fake_mapping)
        assert out["macro_themes_count"] == 0
        assert out["favored"] == []
        assert out["disfavored"] == []

    def test_sorted_descending(self, fake_mapping):
        # rate cut + inflation rising → Real Estate top, Utilities mixed
        themes = [
            {"category": "policy", "direction": "positive", "conviction": "high"},
            {"category": "inflation", "direction": "positive", "conviction": "high"},
        ]
        out = mia.compute_alignment(themes, mapping=fake_mapping)
        scores = [s["score"] for s in out["sectors"]]
        # descending
        assert all(scores[i] >= scores[i + 1] for i in range(len(scores) - 1))


class TestProductionMappingLoad:
    """real mapping file 의 schema 검증."""

    def test_load_default_mapping(self):
        m = mia.load_mapping()
        assert "sectors" in m
        assert isinstance(m["sectors"], list)
        assert len(m["sectors"]) == 11  # GICS 11 sector
        assert "mappings" in m
        # 8 macro 카테고리
        cats = list(m["mappings"].keys())
        for expected in ("policy", "growth", "inflation", "labor", "fx",
                         "credit", "geopolitical", "sector_rotation"):
            assert expected in cats

    def test_thresholds_present(self):
        m = mia.load_mapping()
        th = m.get("_thresholds")
        assert th["strong_tilt"] == 0.5
        assert th["tilt"] == 0.2

    def test_all_categories_have_positive_negative(self):
        m = mia.load_mapping()
        for cat, dirs in m["mappings"].items():
            assert "positive" in dirs and "negative" in dirs, f"{cat} missing direction"
