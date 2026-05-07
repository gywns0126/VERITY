"""GET /api/estate/brain endpoint — 단위 테스트.

검증:
  - generator: scenario 별 결정적 mock + schema 정합 (estate_brain V0.2)
  - balanced / high_pir / redev_uplift 각 시나리오의 차별화 동작
  - extreme_signals_count 계산
  - redev_uplift 시 redevelopment_stage 노출 / 다른 시나리오는 None
"""
from __future__ import annotations

import importlib.util
import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_EP_PATH = os.path.join(_REPO_ROOT, "vercel-api", "api", "estate_brain.py")

_spec = importlib.util.spec_from_file_location("ep_estate_brain", _EP_PATH)
ep = importlib.util.module_from_spec(_spec)
sys.modules["ep_estate_brain"] = ep
_spec.loader.exec_module(ep)


class TestSchema:
    def test_balanced_full_schema(self):
        out = ep._generate_brain("강남구_역삼동_래미안_2015", "balanced")
        assert out["version"] == "v0.2"
        assert out["complex_id"] == "강남구_역삼동_래미안_2015"
        assert out["scenario"] == "balanced"
        for k in ("L1_pir", "L2_jeonse", "L3_cap_rate", "L4_neighbor"):
            assert out["valuation"]["layers"][k] is not None
        assert out["valuation"]["weighted_score"] is not None
        assert out["model_meta"]["source"] == "v0_mock"
        assert out["cycle_analog"]["forward_return_horizon_weeks"] == 26

    def test_redev_uplift_includes_stage(self):
        out = ep._generate_brain("강남구_은마_1979", "redev_uplift")
        assert out["redevelopment_stage"] is not None
        assert out["redevelopment_stage"]["price_phase"] == "max_uplift"
        assert out["redevelopment_stage"]["project_type"] == "redevelopment"

    def test_balanced_excludes_redev(self):
        out = ep._generate_brain("test_id", "balanced")
        assert out["redevelopment_stage"] is None

    def test_deterministic_same_seed(self):
        a = ep._generate_brain("X", "balanced")
        b = ep._generate_brain("X", "balanced")
        # as_of 는 wall clock 이라 다를 수 있음 → valuation layer 만 비교
        assert a["valuation"]["layers"]["L1_pir"] == b["valuation"]["layers"]["L1_pir"]


class TestHighPirScenario:
    def test_high_pir_triggers_extreme_signals(self):
        # high_pir 는 PIR + 전세가율 + cap rate + neighbor gap 모두 거품 영역으로 박힘
        out = ep._generate_brain("test", "high_pir")
        # 최소 2개 이상 (4 신호 중 3+ 가까이) extreme
        assert out["valuation"]["extreme_signals_count"] >= 2

    def test_high_pir_layers_consistent(self):
        out = ep._generate_brain("test", "high_pir")
        layers = out["valuation"]["layers"]
        # PIR 22 이상 (high z)
        assert layers["L1_pir"]["value"] >= 22.0
        # 전세가율 50 미만 (bubble)
        assert layers["L2_jeonse"]["value"] < 50
        # cap rate 1.8 이하 (compressed 가능)
        assert layers["L3_cap_rate"]["value"] <= 2.0


class TestValidScenarios:
    def test_valid_list_complete(self):
        assert "balanced" in ep.VALID_SCENARIOS
        assert "high_pir" in ep.VALID_SCENARIOS
        assert "redev_uplift" in ep.VALID_SCENARIOS

    def test_layer_weights_sum_one(self):
        s = sum(ep.LAYER_WEIGHTS.values())
        assert s == pytest.approx(1.0, abs=1e-9)
