"""industry_themes_pulse_builder 산식 검증.

검증:
  - _normalize_theme: alias 매핑 + 정규화
  - _classify: STRONG_SIGNAL / SIGNAL / MENTION 임계
  - _direction_label: positive / negative / neutral
  - aggregate_themes: frequency / sentiment / verdict 합성, raw_labels / evidences 추적
"""
from __future__ import annotations

import importlib.util
import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BUILDER_PATH = os.path.join(_REPO_ROOT, "api", "builders", "industry_themes_pulse_builder.py")

_spec = importlib.util.spec_from_file_location("itpb", _BUILDER_PATH)
itpb = importlib.util.module_from_spec(_spec)
sys.modules["itpb"] = itpb
_spec.loader.exec_module(itpb)


class TestNormalizeTheme:
    @pytest.mark.parametrize("raw,expected", [
        ("AI capex", "AI capex"),
        ("ai capex", "AI capex"),
        ("AI Investment", "AI capex"),
        ("Gen AI", "AI capex"),
        ("Data center", "data center buildout"),
        ("destocking", "destocking"),
        ("Inventory destocking", "destocking"),
        ("FX headwind", "FX headwind"),
        ("Dollar Strength", "FX headwind"),
        ("Tariff impact", "tariff impact"),
        ("Tariffs", "tariff impact"),
        ("Cloud growth", "cloud growth"),
    ])
    def test_alias_mapping(self, raw, expected):
        assert itpb._normalize_theme(raw) == expected

    def test_unknown_theme_returns_normalized(self):
        # alias 없는 theme = lowercase + 공백 정리만
        assert itpb._normalize_theme("Some Novel Theme") == "some novel theme"

    def test_empty_input(self):
        assert itpb._normalize_theme("") == ""
        assert itpb._normalize_theme(None) == ""

    def test_strips_trailing_punct(self):
        assert itpb._normalize_theme("AI capex.") == "AI capex"


class TestClassify:
    def test_strong_signal(self):
        assert itpb._classify(0.6, 0.8) == "STRONG_SIGNAL"
        assert itpb._classify(0.5, -0.7) == "STRONG_SIGNAL"  # abs

    def test_signal(self):
        assert itpb._classify(0.4, 0.6) == "SIGNAL"
        assert itpb._classify(0.3, -0.5) == "SIGNAL"

    def test_mention_low_freq(self):
        assert itpb._classify(0.2, 0.8) == "MENTION"

    def test_mention_low_sentiment(self):
        assert itpb._classify(0.6, 0.3) == "MENTION"


class TestDirectionLabel:
    @pytest.mark.parametrize("sent,expected", [
        (0.5, "positive"),
        (0.16, "positive"),
        (0.15, "neutral"),
        (0.0, "neutral"),
        (-0.15, "neutral"),
        (-0.16, "negative"),
        (-0.8, "negative"),
    ])
    def test_thresholds(self, sent, expected):
        assert itpb._direction_label(sent) == expected


class TestAggregateThemes:
    def _brief(self, ticker, themes):
        return {"ticker": ticker, "industry_themes": themes}

    def test_simple_aggregation(self):
        briefs = [
            self._brief("MSFT", [
                {"theme": "AI capex", "direction": "positive", "conviction": "high", "evidence": "Azure AI demand strong"},
            ]),
            self._brief("META", [
                {"theme": "ai investment", "direction": "positive", "conviction": "high", "evidence": "AI infra spend +60%"},
            ]),
        ]
        out = itpb.aggregate_themes(briefs)
        assert out["universe_size"] == 2
        ai = next(t for t in out["themes"] if t["theme"] == "AI capex")
        assert ai["ticker_count"] == 2
        assert ai["frequency"] == 1.0
        assert ai["sentiment"] == 1.0
        assert ai["direction_label"] == "positive"
        assert ai["verdict"] == "STRONG_SIGNAL"
        assert len(ai["evidences"]) == 2

    def test_mixed_direction_weighted(self):
        # 3 tickers — 2 positive high + 1 negative low → weighted sentiment 계산
        briefs = [
            self._brief("A", [{"theme": "tariff impact", "direction": "negative", "conviction": "high", "evidence": "x"}]),
            self._brief("B", [{"theme": "Tariffs", "direction": "negative", "conviction": "high", "evidence": "y"}]),
            self._brief("C", [{"theme": "Tariff", "direction": "negative", "conviction": "mid", "evidence": "z"}]),
        ]
        out = itpb.aggregate_themes(briefs)
        # all 3 alias → "tariff impact"
        tariff = next(t for t in out["themes"] if t["theme"] == "tariff impact")
        assert tariff["ticker_count"] == 3
        assert tariff["frequency"] == 1.0
        # 2 × (-1.0 × 1.0) + 1 × (-1.0 × 0.6) = -2.6 / (1.0+1.0+0.6) = -1.0
        assert tariff["sentiment"] == -1.0
        assert tariff["verdict"] == "STRONG_SIGNAL"
        assert tariff["direction_label"] == "negative"

    def test_low_frequency_is_mention(self):
        # 5 tickers, 1 mentions → 0.2 < 0.3 SIGNAL threshold
        briefs = [self._brief(f"T{i}", []) for i in range(4)]
        briefs.append(self._brief("X", [{"theme": "AI capex", "direction": "positive", "conviction": "high", "evidence": "e"}]))
        out = itpb.aggregate_themes(briefs)
        ai = next(t for t in out["themes"] if t["theme"] == "AI capex")
        assert ai["frequency"] == 0.2
        assert ai["verdict"] == "MENTION"

    def test_neutral_sentiment_demoted(self):
        # all neutral → sentiment 0 → MENTION 강등
        briefs = [
            self._brief("A", [{"theme": "destocking", "direction": "neutral", "conviction": "high", "evidence": "x"}]),
            self._brief("B", [{"theme": "destocking", "direction": "neutral", "conviction": "high", "evidence": "y"}]),
        ]
        out = itpb.aggregate_themes(briefs)
        dest = next(t for t in out["themes"] if t["theme"] == "destocking")
        assert dest["sentiment"] == 0.0
        assert dest["verdict"] == "MENTION"

    def test_sort_by_frequency_then_sentiment(self):
        briefs = [
            self._brief("A", [
                {"theme": "AI capex", "direction": "positive", "conviction": "high", "evidence": "x"},
                {"theme": "destocking", "direction": "negative", "conviction": "high", "evidence": "x"},
            ]),
            self._brief("B", [
                {"theme": "AI capex", "direction": "positive", "conviction": "high", "evidence": "y"},
            ]),
        ]
        out = itpb.aggregate_themes(briefs)
        # AI capex freq=1.0, destocking freq=0.5 → AI 먼저
        assert out["themes"][0]["theme"] == "AI capex"
        assert out["themes"][1]["theme"] == "destocking"

    def test_empty_universe(self):
        out = itpb.aggregate_themes([])
        assert out["universe_size"] == 0
        assert out["themes"] == []

    def test_brief_without_themes_field(self):
        briefs = [self._brief("A", None)]
        out = itpb.aggregate_themes(briefs)
        assert out["universe_size"] == 1
        assert out["themes"] == []

    def test_raw_labels_preserved(self):
        briefs = [
            self._brief("A", [{"theme": "AI Capex", "direction": "positive", "conviction": "high", "evidence": "x"}]),
            self._brief("B", [{"theme": "ai investment", "direction": "positive", "conviction": "high", "evidence": "y"}]),
        ]
        out = itpb.aggregate_themes(briefs)
        ai = next(t for t in out["themes"] if t["theme"] == "AI capex")
        # raw_labels = sorted unique input variants
        assert "AI Capex" in ai["raw_labels"] and "ai investment" in ai["raw_labels"]

    def test_evidence_truncated_to_240_chars(self):
        long_evidence = "x" * 500
        briefs = [self._brief("A", [
            {"theme": "AI capex", "direction": "positive", "conviction": "high", "evidence": long_evidence}
        ])]
        out = itpb.aggregate_themes(briefs)
        ai = next(t for t in out["themes"] if t["theme"] == "AI capex")
        assert len(ai["evidences"][0]["evidence"]) == 240
