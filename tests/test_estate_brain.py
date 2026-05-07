"""ESTATE Brain V0.2 — 단위 테스트.

산식 검증 9 case:
  1. PIR layer (절대 fallback + z-score)
  2. 전세가율 layer (4 verdict bands)
  3. Cap Rate layer (정상 / compressed 역전)
  4. Neighbor gap (거품 / 정렬)
  5. Valuation 가중평균 + 4중 신호 카운터
  6. Cycle Analog nearest match
  7. Lead Time Signals 5 신호
  8. Redevelopment Stage 재건축 vs 재개발 가격 phase
  9. compute_estate_brain orchestrator integration
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from api.intelligence import estate_brain as eb


class TestLayerPIR:
    def test_pir_absolute_fallback_low(self):
        # 12억 / 1억 = 12 < 15 → score 100, low
        out = eb.compute_layer_pir(price_won=12e8, annual_income_won=1e8)
        assert out["value"] == 12.0
        assert out["score"] == 100.0
        assert out["verdict"] == "low"

    def test_pir_absolute_fallback_high(self):
        # 30억 / 1억 = 30 > 25 → score 0, high
        out = eb.compute_layer_pir(price_won=30e8, annual_income_won=1e8)
        assert out["score"] == 0.0
        assert out["verdict"] == "high"

    def test_pir_z_score_extreme_high(self):
        # PIR=22, MA=18, σ=2 → z=+2 → score 0, high
        out = eb.compute_layer_pir(
            price_won=22e8, annual_income_won=1e8,
            ma_10yr=18, sigma_10yr=2,
        )
        assert out["z_score"] == 2.0
        assert out["score"] == 0.0
        assert out["verdict"] == "high"

    def test_pir_z_score_balanced(self):
        # z=0 → score 50, balanced
        out = eb.compute_layer_pir(
            price_won=18e8, annual_income_won=1e8,
            ma_10yr=18, sigma_10yr=2,
        )
        assert out["score"] == 50.0
        assert out["verdict"] == "balanced"

    def test_pir_zero_income_returns_none(self):
        assert eb.compute_layer_pir(price_won=10e8, annual_income_won=0) is None


class TestLayerJeonseRatio:
    def test_very_high(self):
        out = eb.compute_layer_jeonse_ratio(jeonse_won=7.5e8, sale_won=10e8)
        assert out["value"] == 75.0
        assert out["verdict"] == "very_high"
        assert out["score"] == 100.0

    def test_balanced(self):
        # 60% → 50 + ((60-55)/15)*50 = 50 + 16.67 ≈ 66.7
        out = eb.compute_layer_jeonse_ratio(jeonse_won=6e8, sale_won=10e8)
        assert out["verdict"] == "balanced"
        assert 65 <= out["score"] <= 70

    def test_low(self):
        # 52% → 30 + ((52-50)/5)*20 = 30 + 8 = 38
        out = eb.compute_layer_jeonse_ratio(jeonse_won=5.2e8, sale_won=10e8)
        assert out["verdict"] == "low"
        assert out["score"] == pytest.approx(38, abs=0.5)

    def test_bubble(self):
        # 45% → 50-45=5, score = 30 - (5/15)*30 = 30 - 10 = 20
        out = eb.compute_layer_jeonse_ratio(jeonse_won=4.5e8, sale_won=10e8)
        assert out["verdict"] == "bubble"
        assert out["score"] == pytest.approx(20, abs=0.5)


class TestLayerCapRate:
    def test_attractive(self):
        # NOI 5천만, 매매 10억, cap=5%, treasury 3% → spread +2pp → score 100
        out = eb.compute_layer_cap_rate(
            noi_annual_won=5e7, sale_won=10e8, treasury_10y_pct=3.0,
        )
        assert out["value"] == 5.0
        assert out["spread_pp"] == 2.0
        assert out["verdict"] == "attractive"
        assert out["score"] == 100.0

    def test_compressed(self):
        # cap 1.5%, treasury 3.5% → spread -2.0pp (≤ -1.0) → compressed
        out = eb.compute_layer_cap_rate(
            noi_annual_won=1.5e7, sale_won=10e8, treasury_10y_pct=3.5,
        )
        assert out["spread_pp"] == -2.0
        assert out["verdict"] == "compressed"
        assert out["score"] == 0.0

    def test_jeonse_to_noi_conversion(self):
        # 5억 전세 × 5.25% = 2,625만
        noi = eb.jeonse_to_noi_annual(jeonse_won=5e8)
        assert noi == pytest.approx(2625e4, abs=1)


class TestLayerNeighborGap:
    def test_kb_lagging_bubble(self):
        # actual=9억, kb=10억 → gap=-10 → kb_lagging_bubble
        out = eb.compute_layer_neighbor_gap(
            recent_actual_avg_won=9e8, kb_price_won=10e8,
        )
        assert out["gap_pct"] == -10.0
        assert out["verdict"] == "kb_lagging_bubble"
        assert out["score"] == 0.0

    def test_actual_outpacing(self):
        # actual=11억, kb=10억 → gap=+10 → actual_outpacing
        out = eb.compute_layer_neighbor_gap(
            recent_actual_avg_won=11e8, kb_price_won=10e8,
        )
        assert out["gap_pct"] == 10.0
        assert out["verdict"] == "actual_outpacing"
        assert out["score"] == 100.0

    def test_aligned(self):
        out = eb.compute_layer_neighbor_gap(
            recent_actual_avg_won=10.3e8, kb_price_won=10e8,
        )
        assert out["verdict"] == "aligned"


class TestValuation:
    def test_weighted_score_full_layers(self):
        layers = {
            "L1_pir":      {"score": 50, "verdict": "balanced", "value": 18},
            "L2_jeonse":   {"score": 80, "verdict": "balanced", "value": 65},
            "L3_cap_rate": {"score": 70, "verdict": "balanced"},
            "L4_neighbor": {"score": 60, "verdict": "aligned", "gap_pct": 2},
        }
        v = eb.compute_valuation(layers)
        # 60×0.45 + 80×0.275 + 70×0.175 + 50×0.10 = 27 + 22 + 12.25 + 5 = 66.25
        assert v["weighted_score"] == pytest.approx(66.2, abs=0.1)
        assert v["primary_anchor_pct"] == 60
        assert v["extreme_signals_count"] == 0

    def test_extreme_signals_count_3(self):
        layers = {
            "L1_pir":      {"score": 0, "verdict": "high", "value": 30, "z_score": 1.5},
            "L2_jeonse":   {"score": 0, "verdict": "bubble", "value": 45},  # <50%
            "L3_cap_rate": {"score": 0, "verdict": "compressed", "spread_pp": -1.5},
            "L4_neighbor": {"score": 50, "verdict": "aligned", "gap_pct": 5},
        }
        v = eb.compute_valuation(layers)
        assert v["extreme_signals_count"] == 3
        assert "pir_z_extreme" in v["extreme_signals"]
        assert "jeonse_ratio_below_50" in v["extreme_signals"]
        assert "cap_treasury_inverted" in v["extreme_signals"]

    def test_partial_layers_renormalized(self):
        # L4 만 있을 때 weighted_score = L4 score (재정규화)
        layers = {
            "L1_pir": None,
            "L2_jeonse": None,
            "L3_cap_rate": None,
            "L4_neighbor": {"score": 75, "verdict": "aligned", "gap_pct": 5},
        }
        v = eb.compute_valuation(layers)
        assert v["weighted_score"] == 75.0


class TestCycleAnalog:
    def test_nearest_rate_shock(self):
        target = {"drop_pct": -20, "duration_months": 60, "shape": "W"}
        out = eb.classify_cycle_analog(target)
        assert out["nearest_historical"][0]["name"] == "Rate-Shock Rebound"
        assert out["current_phase"] == "Rate-Shock Rebound"

    def test_nearest_imf_shock(self):
        target = {"drop_pct": -18, "duration_months": 50, "shape": "V"}
        out = eb.classify_cycle_analog(target)
        assert out["nearest_historical"][0]["name"] == "Shock-Recovery"

    def test_explicit_phase_overrides(self):
        target = {"drop_pct": -20, "duration_months": 60, "shape": "W"}
        out = eb.classify_cycle_analog(target, current_phase_label="custom_phase")
        assert out["current_phase"] == "custom_phase"
        # nearest 는 여전히 정렬됨
        assert len(out["nearest_historical"]) == 3


class TestLeadTimeSignals:
    def test_jeonse_3m_moderate_up(self):
        out = eb.compute_lead_time_signals(jeonse_3m_change_pct=1.5)
        sig = out["signals"]["jeonse_3m_lead"]
        assert sig["verdict"] == "moderate_up"
        assert sig["lead_months"] == 2

    def test_unsold_negative_pressure_strong(self):
        out = eb.compute_lead_time_signals(unsold_units_yoy_pct=35)
        assert out["signals"]["unsold_units_lead"]["verdict"] == "negative_pressure_strong"

    def test_construction_supply_tight(self):
        out = eb.compute_lead_time_signals(construction_starts_yoy_pct=-15)
        sig = out["signals"]["construction_starts_lead"]
        assert sig["verdict"] == "supply_tight_in_2y"
        assert sig["lead_months"] == 28

    def test_jeonse_ratio_overheated(self):
        out = eb.compute_lead_time_signals(jeonse_ratio_pct=82)
        assert out["signals"]["jeonse_ratio_24m"]["verdict"] == "ambivalent_overheated"

    def test_horizon_constant(self):
        out = eb.compute_lead_time_signals(jeonse_3m_change_pct=0)
        assert out["forward_return_horizon_weeks"] == 26


class TestRedevelopmentStage:
    def test_reconstruction_union_setup_max_uplift(self):
        out = eb.classify_redevelopment_stage(
            stage="union_setup", project_type="reconstruction",
        )
        assert out["price_phase"] == "max_uplift"
        assert out["stage_label_ko"] == "조합설립 인가"

    def test_redevelopment_management_plan_max_uplift(self):
        out = eb.classify_redevelopment_stage(
            stage="management_plan", project_type="redevelopment",
        )
        assert out["price_phase"] == "max_uplift"
        assert out["stage_label_ko"] == "관리처분 인가"

    def test_reconstruction_management_plan_post_peak(self):
        # 재건축은 조합설립이 최대 — 관리처분은 post_peak
        out = eb.classify_redevelopment_stage(
            stage="management_plan", project_type="reconstruction",
        )
        assert out["price_phase"] == "post_peak_consolidation"

    def test_relocation_rental_spillover(self):
        out = eb.classify_redevelopment_stage(
            stage="relocation", project_type="redevelopment",
            months_in_stage=3,
        )
        assert out["price_phase"] == "rental_market_spillover"
        # 평균 30M, 진행 3M → 27M 남음
        assert out["months_to_next_stage_estimated"] == 27

    def test_invalid_stage_returns_none(self):
        assert eb.classify_redevelopment_stage(
            stage="foo", project_type="reconstruction",
        ) is None


class TestOrchestrator:
    def test_full_input_v02_schema(self):
        out = eb.compute_estate_brain(
            complex_id="강남구_은마",
            as_of="2026-05-08T03:00:00+09:00",
            price_won=22e8,
            annual_income_won=1e8,
            pir_ma_10yr=18,
            pir_sigma_10yr=2,
            jeonse_won=11e8,  # 50% ratio
            treasury_10y_pct=3.2,
            recent_actual_avg_won=20e8,
            kb_price_won=22e8,  # gap = -9.1% (aligned)
            target_cycle={"drop_pct": -20, "duration_months": 60, "shape": "W"},
            jeonse_3m_change_pct=1.2,
            unsold_units_yoy_pct=18,
            redevelopment_stage="management_plan",
            project_type="redevelopment",
            months_in_stage=4,
            valuation_announcement_pending=True,
        )
        assert out["version"] == "v0.2"
        assert out["complex_id"] == "강남구_은마"
        assert out["valuation"]["primary_anchor_pct"] is not None
        assert out["cycle_analog"]["current_phase"] == "Rate-Shock Rebound"
        assert out["redevelopment_stage"]["price_phase"] == "max_uplift"
        assert out["redevelopment_stage"]["monitoring"]["valuation_announcement_pending"] is True
        # lead time wired
        assert "jeonse_3m_lead" in out["cycle_analog"]["lead_time_signals"]
        assert out["model_meta"]["version"] == "v0_hardcoded"

    def test_minimal_input_partial_layers(self):
        # 가격만 있을 때 — L1 만 계산, 나머지 None
        out = eb.compute_estate_brain(
            complex_id="test",
            as_of="2026-05-08",
            price_won=15e8,
            annual_income_won=1e8,
        )
        assert out["valuation"]["layers"]["L1_pir"] is not None
        assert out["valuation"]["layers"]["L2_jeonse"] is None
        assert out["valuation"]["layers"]["L3_cap_rate"] is None
        assert out["valuation"]["layers"]["L4_neighbor"] is None
        assert out["redevelopment_stage"] is None
