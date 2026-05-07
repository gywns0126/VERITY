"""estate_constitution.json SSOT 분리 — 단위 테스트.

검증:
  - JSON 파일 존재 + 파싱 OK
  - 필수 키 (layer_weights / extreme_thresholds / pir_baseline / cycle_analogs)
  - layer_weights 합 = 1.0
  - estate_brain.LAYER_WEIGHTS = constitution 값 정합
  - estate_brain.EXTREME_* threshold = constitution 값 정합
  - constitution 부재 시 fallback default
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

CONSTITUTION_PATH = _REPO_ROOT / "data" / "estate_constitution.json"


class TestJsonFile:
    def test_exists(self):
        assert CONSTITUTION_PATH.exists()

    def test_parseable(self):
        with open(CONSTITUTION_PATH, encoding="utf-8") as f:
            data = json.load(f)
        assert data["version"] == "v0.2"

    def test_required_keys(self):
        with open(CONSTITUTION_PATH, encoding="utf-8") as f:
            data = json.load(f)
        for k in ("layer_weights", "extreme_thresholds", "pir_baseline",
                  "cycle_analogs", "lead_time_table",
                  "redevelopment_stage_avg_months", "seoul_region_income_factors"):
            assert k in data, f"missing {k}"

    def test_layer_weights_sum_one(self):
        with open(CONSTITUTION_PATH, encoding="utf-8") as f:
            data = json.load(f)
        weights = {k: v for k, v in data["layer_weights"].items() if not k.startswith("_")}
        assert sum(weights.values()) == pytest.approx(1.0, abs=1e-9)

    def test_cycle_analogs_3_patterns(self):
        with open(CONSTITUTION_PATH, encoding="utf-8") as f:
            data = json.load(f)
        names = {a["name"] for a in data["cycle_analogs"]}
        assert names == {"Shock-Recovery", "Debt-Deflation Drag", "Rate-Shock Rebound"}

    def test_seoul_region_factors_5(self):
        with open(CONSTITUTION_PATH, encoding="utf-8") as f:
            data = json.load(f)
        factors = {k: v for k, v in data["seoul_region_income_factors"].items()
                   if not k.startswith("_")}
        assert set(factors.keys()) == {"center", "northeast", "northwest", "southwest", "southeast"}


class TestEstateBrainLoadsFromJson:
    def test_layer_weights_match(self):
        from api.intelligence import estate_brain as eb
        eb._reset_constitution_cache()
        with open(CONSTITUTION_PATH, encoding="utf-8") as f:
            json_weights = json.load(f)["layer_weights"]
        loaded = eb._layer_weights()
        for k in ("L4_neighbor", "L2_jeonse", "L3_cap_rate", "L1_pir"):
            assert loaded[k] == json_weights[k]

    def test_extreme_thresholds_match(self):
        from api.intelligence import estate_brain as eb
        eb._reset_constitution_cache()
        with open(CONSTITUTION_PATH, encoding="utf-8") as f:
            et = json.load(f)["extreme_thresholds"]
        thr = eb._extreme_thresholds()
        assert thr["pir_z"] == et["pir_z_threshold"]
        assert thr["jeonse_ratio"] == et["jeonse_ratio_pct"]
        assert thr["cap_treasury"] == et["cap_treasury_bp"]
        assert thr["kb_gap"] == et["kb_actual_gap_pct"]


class TestFallbackOnMissing:
    def test_returns_defaults_when_no_json(self, monkeypatch, tmp_path):
        from api.intelligence import estate_brain as eb
        monkeypatch.setattr(eb, "_constitution_path", lambda: str(tmp_path / "nonexistent.json"))
        eb._reset_constitution_cache()
        weights = eb._layer_weights()
        # fallback = _DEFAULT_LAYER_WEIGHTS
        assert weights["L4_neighbor"] == 0.45
        assert weights["L2_jeonse"] == 0.275
        # 함수 종료 후 캐시 리셋 (다른 테스트 영향 X)
        eb._reset_constitution_cache()

    def test_thresholds_fallback(self, monkeypatch, tmp_path):
        from api.intelligence import estate_brain as eb
        monkeypatch.setattr(eb, "_constitution_path", lambda: str(tmp_path / "missing.json"))
        eb._reset_constitution_cache()
        thr = eb._extreme_thresholds()
        assert thr["pir_z"] == 1.0
        assert thr["jeonse_ratio"] == 50.0
        eb._reset_constitution_cache()
