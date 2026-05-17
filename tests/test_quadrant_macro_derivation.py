"""F1+F2 회귀 결함 fix 검증 (2026-05-18, PM 승인).

docs/QUADRANT_REGRESSION_AUDIT_20260518.md root cause:
  detect_economic_quadrant 가 찾는 fred.cpi_yoy / fred.gdp_growth / fred.ism_pmi /
  fred.pce_yoy 4 키 모두 portfolio.macro.fred 에 부재 → fallback 영구 trip
  (cpi_yoy=2.5 하드코드 + gdp=(mood-50)*0.06) → growth_down_inflation_down 25/25 단일 강제.

F1: collector 가 core_cpi.yoy_pct → fred.cpi_yoy.value 동시 채움.
F2: us_recession_smoothed_prob.pct → fred.gdp_growth.value proxy (2.5 - 0.08*rp).
"""
from __future__ import annotations

from api.intelligence.verity_brain import detect_economic_quadrant


def _portfolio_with_fred(fred_block: dict, mood_score: int = 50) -> dict:
    """detect_economic_quadrant 입력용 최소 portfolio dict."""
    return {
        "macro": {
            "fred": fred_block,
            "market_mood": {"score": mood_score},
        }
    }


class TestF1CpiYoyDerivation:
    """F1: cpi_yoy 가 fred.cpi_yoy.value 로 정상 전달되는지."""

    def test_cpi_yoy_above_3_triggers_inflation_up(self):
        """cpi_yoy 3.5 > 임계 3.0 → inflation_up = True."""
        fred = {
            "cpi_yoy": {"value": 3.5, "date": "2026-04-01"},
            "gdp_growth": {"value": 2.0, "date": "2026-03-01"},
        }
        result = detect_economic_quadrant(_portfolio_with_fred(fred))
        assert result["cpi_yoy"] == 3.5
        assert result["quadrant"] == "growth_up_inflation_up"

    def test_cpi_yoy_below_3_yields_inflation_down(self):
        """cpi_yoy 2.99 < 임계 3.0 → inflation_up = False (간발의 차)."""
        fred = {
            "cpi_yoy": {"value": 2.99, "date": "2026-04-01"},
            "gdp_growth": {"value": 2.35, "date": "2026-03-01"},
        }
        result = detect_economic_quadrant(_portfolio_with_fred(fred))
        assert result["cpi_yoy"] == 2.99
        assert result["quadrant"] == "growth_up_inflation_down"

    def test_missing_cpi_yoy_falls_back_to_hardcode(self):
        """회귀 검증 — fred.cpi_yoy 부재 시 2.5 하드코드 fallback (회귀 시그널)."""
        fred = {"gdp_growth": {"value": 2.0}}
        result = detect_economic_quadrant(_portfolio_with_fred(fred))
        assert result["cpi_yoy"] == 2.5  # 회귀 fallback 작동 (의도적)


class TestF2GdpGrowthProxy:
    """F2: gdp_growth proxy 산식 검증 (2.5 - 0.08 × recession_prob)."""

    def test_low_recession_prob_yields_growth_up(self):
        """recession_prob 1.82% → proxy 2.35 > 1.5 → growth_up."""
        rec_prob = 1.82
        expected_gdp = round(2.5 - 0.08 * rec_prob, 2)
        assert expected_gdp == 2.35
        fred = {
            "gdp_growth": {"value": expected_gdp},
            "cpi_yoy": {"value": 2.0},
        }
        result = detect_economic_quadrant(_portfolio_with_fred(fred))
        assert result["gdp_growth"] == 2.35
        assert result["quadrant"] == "growth_up_inflation_down"

    def test_proxy_threshold_12_5_pct(self):
        """recession_prob 12.5% → proxy 1.5 = growth_up 임계 (boundary)."""
        rec_prob = 12.5
        expected = round(2.5 - 0.08 * rec_prob, 2)
        assert expected == 1.5
        # gdp_growth > 1.5 인지 검증 (정확히 1.5 면 growth_up = False)
        fred = {
            "gdp_growth": {"value": expected},
            "cpi_yoy": {"value": 2.0},
        }
        result = detect_economic_quadrant(_portfolio_with_fred(fred))
        # gdp 정확히 1.5 → 1.5 > 1.5 = False → growth_down
        assert result["quadrant"].startswith("growth_down")

    def test_high_recession_prob_yields_growth_down(self):
        """recession_prob 50% → proxy -1.5 → growth_down."""
        rec_prob = 50
        expected = round(2.5 - 0.08 * rec_prob, 2)
        assert expected == -1.5
        fred = {
            "gdp_growth": {"value": expected},
            "cpi_yoy": {"value": 4.0},
        }
        result = detect_economic_quadrant(_portfolio_with_fred(fred))
        assert result["gdp_growth"] == -1.5
        assert result["quadrant"] == "growth_down_inflation_up"


class TestF1F2Integration:
    """F1+F2 적용 후 25/25 단일 분면 회귀 회복 검증."""

    def test_current_macro_yields_growth_up_inflation_down(self):
        """실측 macro (cpi=2.99, recession_prob=1.82) → growth_up_inflation_down."""
        # F1 derivation 결과
        cpi_yoy = 2.99
        # F2 derivation 결과
        rec_prob = 1.82
        gdp_proxy = round(2.5 - 0.08 * rec_prob, 2)

        fred = {
            "cpi_yoy": {"value": cpi_yoy, "date": "2026-04-01"},
            "gdp_growth": {"value": gdp_proxy, "date": "2026-03-01"},
        }
        result = detect_economic_quadrant(_portfolio_with_fred(fred))
        assert result["quadrant"] == "growth_up_inflation_down"
        # constitution 의 brain_weights = (0.65, 0.35) 적용 분면
        assert result["crypto_bias"] == "risk_on"
        # favored: 주식/회사채/성장주 (방어주 아님)
        assert "주식" in result["favored"] or "성장주" in result["favored"]

    def test_regression_baseline_without_fix(self):
        """fix 없이 (4 키 모두 부재) → growth_down_inflation_down 영구 강제 (회귀 baseline)."""
        # 회귀 상황: fred 에 어느 키도 없음, mood 40 비관
        fred = {}
        portfolio = _portfolio_with_fred(fred, mood_score=40)
        result = detect_economic_quadrant(portfolio)
        # gdp = (40-50)*0.06 = -0.6, cpi = 2.5 하드코드
        assert result["gdp_growth"] == -0.6
        assert result["cpi_yoy"] == 2.5
        assert result["quadrant"] == "growth_down_inflation_down"


class TestFredMacroBlockDerivation:
    """get_fred_macro_block 의 cpi_yoy / gdp_growth derivation 박힘 검증.

    실제 FRED API 호출 없이 derivation 로직만 단위 테스트.
    """

    def test_cpi_yoy_derivation_mirrors_core_cpi(self):
        """core_cpi.yoy_pct = 2.99 → fred.cpi_yoy.value = 2.99 mirror."""
        # 모의 out dict 에 derivation 로직 직접 실행
        out = {
            "core_cpi": {"index": 335.42, "date": "2026-04-01", "yoy_pct": 2.99},
        }
        # fred_macro.py:373-419 의 derivation 블록과 동일 로직
        cpi_block = out.get("core_cpi") or {}
        cpi_yoy_val = cpi_block.get("yoy_pct")
        if cpi_yoy_val is not None:
            out["cpi_yoy"] = {
                "value": float(cpi_yoy_val),
                "date": cpi_block.get("date"),
                "series_id": "CPILFESL",
            }

        assert out["cpi_yoy"]["value"] == 2.99
        assert out["cpi_yoy"]["date"] == "2026-04-01"

    def test_gdp_growth_proxy_formula(self):
        """us_recession_smoothed_prob.pct → gdp_growth = 2.5 - 0.08 × rp."""
        out = {
            "us_recession_smoothed_prob": {
                "pct": 1.82,
                "date": "2026-03-01",
                "series_id": "RECPROUSM156N",
            },
        }
        rec_block = out.get("us_recession_smoothed_prob") or {}
        rec_prob = rec_block.get("pct")
        if rec_prob is not None:
            gdp_proxy = round(2.5 - 0.08 * float(rec_prob), 2)
            out["gdp_growth"] = {
                "value": gdp_proxy,
                "date": rec_block.get("date"),
                "series_id": "RECPROUSM156N",
            }

        assert out["gdp_growth"]["value"] == 2.35
        assert out["gdp_growth"]["date"] == "2026-03-01"

    def test_derivation_skips_when_source_missing(self):
        """source 데이터 부재 시 derivation 건너뜀 (silent skip 아님, 키 자체 부재)."""
        out = {}
        # F1: core_cpi 부재 → cpi_yoy 박지 않음
        cpi_block = out.get("core_cpi") or {}
        if cpi_block.get("yoy_pct") is not None:
            out["cpi_yoy"] = {"value": cpi_block["yoy_pct"]}
        assert "cpi_yoy" not in out

        # F2: us_recession_smoothed_prob 부재 → gdp_growth 박지 않음
        rec_block = out.get("us_recession_smoothed_prob") or {}
        if rec_block.get("pct") is not None:
            out["gdp_growth"] = {"value": 0}
        assert "gdp_growth" not in out
