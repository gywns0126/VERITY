"""macro_themes_brief 산식 검증.

검증:
  - _parse_brief_json: markdown wrapper 제거 + 첫{~마지막}
  - _validate_theme: 필수 필드 + invalid silent drop + fallback (category/direction/conviction)
  - compute_macro_verdict: BULLISH / BEARISH / NEUTRAL / MIXED / UNAVAILABLE
  - _iso_week_label: ISO week 형식
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from datetime import datetime, timezone, timedelta

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MOD_PATH = os.path.join(_REPO_ROOT, "api", "intelligence", "macro_themes_brief.py")

_spec = importlib.util.spec_from_file_location("mtb", _MOD_PATH)
mtb = importlib.util.module_from_spec(_spec)
sys.modules["mtb"] = mtb
_spec.loader.exec_module(mtb)


class TestParseBriefJson:
    def test_plain_json(self):
        s = '{"themes": [{"theme": "x"}]}'
        out = mtb._parse_brief_json(s)
        assert out == {"themes": [{"theme": "x"}]}

    def test_markdown_wrapper(self):
        s = '```json\n{"themes": []}\n```'
        out = mtb._parse_brief_json(s)
        assert out == {"themes": []}

    def test_text_before_after(self):
        s = 'Here is the JSON:\n{"a": 1, "themes": []}\nThanks.'
        out = mtb._parse_brief_json(s)
        assert out == {"a": 1, "themes": []}

    def test_invalid_returns_none(self):
        assert mtb._parse_brief_json("not json") is None
        assert mtb._parse_brief_json("{ broken") is None

    def test_empty(self):
        assert mtb._parse_brief_json("") is None


class TestValidateTheme:
    def test_full_valid(self):
        out = mtb._validate_theme({
            "theme": "Fed Q3 cut",
            "category": "policy",
            "direction": "positive",
            "conviction": "high",
            "evidence": "GS sees Fed cutting in September",
            "sources": ["Goldman Sachs"],
        })
        assert out["theme"] == "Fed Q3 cut"
        assert out["category"] == "policy"
        assert out["direction"] == "positive"
        assert out["conviction"] == "high"
        assert out["sources"] == ["Goldman Sachs"]

    def test_invalid_category_fallback(self):
        out = mtb._validate_theme({
            "theme": "X", "category": "nonsense",
            "direction": "positive", "conviction": "high",
            "evidence": "y", "sources": [],
        })
        assert out["category"] == "policy"  # fallback

    def test_invalid_direction_fallback_neutral(self):
        out = mtb._validate_theme({
            "theme": "X", "category": "policy",
            "direction": "bullish", "conviction": "high",  # bullish not in enum
            "evidence": "y", "sources": [],
        })
        assert out["direction"] == "neutral"

    def test_invalid_conviction_fallback_mid(self):
        out = mtb._validate_theme({
            "theme": "X", "category": "policy",
            "direction": "positive", "conviction": "extreme",
            "evidence": "y", "sources": [],
        })
        assert out["conviction"] == "mid"

    def test_missing_theme_returns_none(self):
        assert mtb._validate_theme({"category": "policy"}) is None
        assert mtb._validate_theme({"theme": ""}) is None

    def test_too_long_theme_returns_none(self):
        assert mtb._validate_theme({"theme": "x" * 100}) is None

    def test_non_dict_returns_none(self):
        assert mtb._validate_theme(None) is None
        assert mtb._validate_theme("string") is None
        assert mtb._validate_theme([]) is None

    def test_evidence_truncated_to_240(self):
        out = mtb._validate_theme({
            "theme": "x", "category": "policy",
            "direction": "positive", "conviction": "high",
            "evidence": "z" * 500, "sources": [],
        })
        assert len(out["evidence"]) == 240

    def test_sources_capped_to_5(self):
        out = mtb._validate_theme({
            "theme": "x", "category": "policy",
            "direction": "positive", "conviction": "high",
            "evidence": "y", "sources": [f"src{i}" for i in range(10)],
        })
        assert len(out["sources"]) == 5


class TestComputeMacroVerdict:
    def _t(self, direction, conviction):
        return {"direction": direction, "conviction": conviction}

    def test_empty_unavailable(self):
        assert mtb.compute_macro_verdict([]) == "UNAVAILABLE"

    def test_all_positive_high_bullish(self):
        themes = [self._t("positive", "high")] * 3
        assert mtb.compute_macro_verdict(themes) == "BULLISH"

    def test_all_negative_high_bearish(self):
        themes = [self._t("negative", "high")] * 3
        assert mtb.compute_macro_verdict(themes) == "BEARISH"

    def test_mixed_strong_both(self):
        # 2+ positive high + 2+ negative high → MIXED
        themes = [
            self._t("positive", "high"), self._t("positive", "high"),
            self._t("negative", "high"), self._t("negative", "high"),
        ]
        assert mtb.compute_macro_verdict(themes) == "MIXED"

    def test_slight_positive_low_conviction_neutral(self):
        themes = [
            self._t("positive", "low"),  # +0.3 weight
            self._t("neutral", "high"),  # 1.0 weight, score 0
        ]
        # score = 0.3 / 1.3 ≈ 0.23 < 0.30 → NEUTRAL
        assert mtb.compute_macro_verdict(themes) == "NEUTRAL"

    def test_above_bullish_threshold(self):
        themes = [
            self._t("positive", "high"),  # +1.0, weight 1.0
            self._t("neutral", "mid"),   # 0, weight 0.6
        ]
        # avg = 1.0 / 1.6 = 0.625 → BULLISH
        assert mtb.compute_macro_verdict(themes) == "BULLISH"


class TestIsoWeekLabel:
    def test_format(self):
        dt = datetime(2026, 5, 20, 12, 0, tzinfo=mtb.KST)
        label = mtb._iso_week_label(dt)
        assert label.startswith("2026-W")
        assert len(label) == 8  # YYYY-WNN

    def test_year_boundary(self):
        # 2026-01-01 ISO week — check format consistency
        dt = datetime(2026, 1, 1, 12, 0, tzinfo=mtb.KST)
        label = mtb._iso_week_label(dt)
        assert "-W" in label


class TestSystemPromptIntegrity:
    def test_system_prompt_mentions_macro(self):
        assert "macro" in mtb._SYSTEM_PROMPT.lower()
        assert "JSON" in mtb._SYSTEM_PROMPT

    def test_query_template_has_categories(self):
        q = mtb._query_template()
        for cat in mtb.VALID_CATEGORIES:
            assert cat in q
        assert "direction" in q
        assert "conviction" in q
