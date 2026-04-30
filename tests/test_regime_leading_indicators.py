"""Sprint 11 결함 6 — regime classify 의 leading indicator 검증.

베테랑 평가: 기존 _classify_regime 가 trailing signal 만 사용 → 후행적.
yield curve slope / copper-gold ratio 추가로 leading 신호 분리.
divergence_warning 으로 regime 전환 임박 시그널 노출.
"""
from __future__ import annotations

from api.intelligence.strategy_evolver import _classify_regime


def _base_portfolio(**overrides):
    """매크로 leading + trailing 모두 채운 mock portfolio."""
    p = {
        "macro": {
            "fear_greed": {"score": 50},
            "economic_quadrant": "EXPANSION",
            "vix": {"value": 18},
            "market_mood": {"score": 55},
            "us_10y": {"value": 4.3},
            "us_2y": {"value": 3.5},
            "yield_spread": {"value": 0.8, "signal": "정상"},
            "copper": {"change_pct": 1.0},
            "gold": {"change_pct": 1.0},
        },
        "market_summary": {
            "kospi": {"change_pct": 0.0},
            "sp500": {"change_pct": 0.0},
        },
    }
    if "macro" in overrides:
        p["macro"].update(overrides.pop("macro"))
    p.update(overrides)
    return p


class TestRegimeDiagnostics:
    def test_diagnostics_attached(self):
        """leading + trailing score 가 portfolio.regime_diagnostics 에 attach."""
        p = _base_portfolio()
        _classify_regime(p)
        diag = p.get("regime_diagnostics", {})
        assert "trailing_score" in diag
        assert "leading_score" in diag
        assert "trailing_count" in diag
        assert "leading_count" in diag
        assert diag["leading_count"] >= 2  # yield + copper/gold

    def test_yield_curve_normal(self):
        """yield_spread 1.0+ → leading 양수."""
        p = _base_portfolio(macro={"yield_spread": {"value": 1.5}})
        _classify_regime(p)
        diag = p.get("regime_diagnostics", {})
        assert diag["yield_spread_pp"] == 1.5
        assert diag["leading_score"] >= 0

    def test_yield_curve_inverted(self):
        """yield_spread < 0 (역전) → leading -2 (강신호)."""
        p = _base_portfolio(macro={"yield_spread": {"value": -0.3}})
        _classify_regime(p)
        diag = p.get("regime_diagnostics", {})
        assert diag["yield_spread_pp"] == -0.3
        # leading 평균이 음수 (yield -2 + copper/gold 0 = -1.0 average)
        assert diag["leading_score"] < 0

    def test_yield_curve_fallback_from_us_rates(self):
        """yield_spread 키 없으면 us_10y - us_2y 로 fallback."""
        macro = {
            "us_10y": {"value": 4.5},
            "us_2y": {"value": 3.0},
        }
        # yield_spread 키 명시적으로 제거
        p = _base_portfolio()
        p["macro"].pop("yield_spread", None)
        p["macro"]["us_10y"] = macro["us_10y"]
        p["macro"]["us_2y"] = macro["us_2y"]
        _classify_regime(p)
        diag = p.get("regime_diagnostics", {})
        assert diag["yield_spread_pp"] == 1.5  # 4.5 - 3.0

    def test_copper_gold_risk_on(self):
        """copper +2% vs gold -1% → diff=3.0 → leading +1 (risk-on)."""
        p = _base_portfolio(macro={
            "copper": {"change_pct": 2.0},
            "gold": {"change_pct": -1.0},
        })
        _classify_regime(p)
        diag = p.get("regime_diagnostics", {})
        # leading 시그널 2개 (yield 정상=0, copper/gold +1) → avg 0.5
        assert diag["leading_score"] > 0

    def test_copper_gold_risk_off(self):
        """gold +3% vs copper -1% → diff=-4.0 → leading -1 (risk-off)."""
        p = _base_portfolio(macro={
            "copper": {"change_pct": -1.0},
            "gold": {"change_pct": 3.0},
        })
        _classify_regime(p)
        diag = p.get("regime_diagnostics", {})
        assert diag["leading_score"] < 0

    def test_divergence_warning_triggered(self):
        """trailing bullish 인데 leading bearish → divergence warning."""
        p = _base_portfolio(
            macro={
                "fear_greed": {"score": 80},     # bull
                "vix": {"value": 12},             # bull
                "market_mood": {"score": 75},     # bull
                "yield_spread": {"value": -0.5},  # 역전 (bearish leading)
                "copper": {"change_pct": -2.0},   # risk-off
                "gold": {"change_pct": 2.0},
            },
            market_summary={
                "kospi": {"change_pct": 1.0},
                "sp500": {"change_pct": 1.5},
            },
        )
        _classify_regime(p)
        diag = p.get("regime_diagnostics", {})
        assert diag["trailing_score"] > 0  # bull
        assert diag["leading_score"] < 0   # bear
        assert diag["divergence_warning"] is True

    def test_no_divergence_when_aligned(self):
        """trailing/leading 같은 방향 → no warning."""
        p = _base_portfolio()  # 둘 다 중립
        _classify_regime(p)
        diag = p.get("regime_diagnostics", {})
        assert diag["divergence_warning"] is False


class TestRegimeReturn:
    def test_unknown_for_empty_portfolio(self):
        assert _classify_regime(None) == "unknown"
        assert _classify_regime({}) == "unknown"

    def test_bear_when_signals_negative(self):
        p = _base_portfolio(
            macro={
                "fear_greed": {"score": 20},
                "vix": {"value": 35},
                "market_mood": {"score": 25},
                "yield_spread": {"value": -0.5},
                "copper": {"change_pct": -3.0},
                "gold": {"change_pct": 2.0},
            },
            market_summary={
                "kospi": {"change_pct": -2.0},
                "sp500": {"change_pct": -1.5},
            },
        )
        assert _classify_regime(p) == "bear"

    def test_bull_when_signals_positive(self):
        p = _base_portfolio(
            macro={
                "fear_greed": {"score": 75},
                "vix": {"value": 14},
                "market_mood": {"score": 80},
                "yield_spread": {"value": 1.5},
                "copper": {"change_pct": 2.5},
                "gold": {"change_pct": 0.5},
            },
            market_summary={
                "kospi": {"change_pct": 1.5},
                "sp500": {"change_pct": 2.0},
            },
        )
        assert _classify_regime(p) == "bull"
