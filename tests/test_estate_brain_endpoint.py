"""GET /api/estate/brain endpoint — 단위 테스트 (P2 read-through + 개발 mock).

검증:
  - mock_balanced / mock_high_pir / mock_redev_uplift 결정적 + schema 정합
  - read-through: snapshots.json → gu_aggregates / complexes 추출
  - 404: complex_id not in watchlist / gu not in aggregates
  - 503: env 미설정 / fetch 실패
  - LAYER_WEIGHTS 합 1.0
"""
from __future__ import annotations

import importlib.util
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_EP_PATH = os.path.join(_REPO_ROOT, "vercel-api", "api", "estate_brain.py")

_spec = importlib.util.spec_from_file_location("ep_estate_brain", _EP_PATH)
ep = importlib.util.module_from_spec(_spec)
sys.modules["ep_estate_brain"] = ep
_spec.loader.exec_module(ep)


class TestMockGenerator:
    def test_balanced_full_schema(self):
        out = ep._generate_mock("강남구_역삼동_래미안_2015", "mock_balanced")
        assert out["version"] == "v0.2"
        assert out["scenario"] == "mock_balanced"
        for k in ("L1_pir", "L2_jeonse", "L3_cap_rate", "L4_neighbor"):
            assert out["valuation"]["layers"][k] is not None
        assert out["model_meta"]["source"] == "v0_mock"
        assert out["redevelopment_stage"] is None

    def test_redev_uplift_includes_stage(self):
        out = ep._generate_mock("test_id", "mock_redev_uplift")
        assert out["redevelopment_stage"] is not None
        assert out["redevelopment_stage"]["price_phase"] == "max_uplift"

    def test_high_pir_signals(self):
        out = ep._generate_mock("test", "mock_high_pir")
        assert out["valuation"]["extreme_signals_count"] >= 2
        assert out["valuation"]["layers"]["L1_pir"]["value"] >= 22.0
        assert out["valuation"]["layers"]["L2_jeonse"]["value"] < 50

    def test_deterministic(self):
        a = ep._generate_mock("X", "mock_balanced")
        b = ep._generate_mock("X", "mock_balanced")
        assert a["valuation"]["layers"]["L1_pir"] == b["valuation"]["layers"]["L1_pir"]


class TestExtractTarget:
    def test_complex_id_hit(self):
        snapshots = {
            "complexes": {"강남구_대치동_은마_1979": {"version": "v0.2"}},
            "gu_aggregates": {},
        }
        s, t, err = ep._extract_target(snapshots, "강남구_대치동_은마_1979", None)
        assert s == 200 and t == {"version": "v0.2"} and err is None

    def test_complex_id_miss_404(self):
        snapshots = {"complexes": {}, "gu_aggregates": {}}
        s, t, err = ep._extract_target(snapshots, "missing_id", None)
        assert s == 404 and err == "complex_id_not_in_watchlist"

    def test_gu_aggregate_hit(self):
        snapshots = {"complexes": {}, "gu_aggregates": {"강남구": {"version": "v0.2"}}}
        s, t, err = ep._extract_target(snapshots, None, "강남구")
        assert s == 200 and t == {"version": "v0.2"}

    def test_gu_miss_404(self):
        snapshots = {"complexes": {}, "gu_aggregates": {}}
        s, t, err = ep._extract_target(snapshots, None, "강남구")
        assert s == 404 and err == "gu_not_in_aggregates"

    def test_no_id_returns_400(self):
        snapshots = {"complexes": {}, "gu_aggregates": {}}
        s, t, err = ep._extract_target(snapshots, None, None)
        assert s == 400 and err == "missing_complex_id_or_gu"


class TestFetchLive:
    def test_fetch_failure_503(self):
        import requests as req
        with patch.object(ep.requests, "get", side_effect=req.RequestException("net")):
            s, p, err = ep._fetch_live("https://example/x.json")
        assert s == 503 and err == "source_fetch_failed"

    def test_non_200_503(self):
        mock = MagicMock(); mock.status_code = 404
        with patch.object(ep.requests, "get", return_value=mock):
            s, p, err = ep._fetch_live("https://example/x.json")
        assert s == 503 and err == "source_non_200"

    def test_invalid_json_503(self):
        mock = MagicMock(); mock.status_code = 200
        mock.json.side_effect = ValueError("bad")
        with patch.object(ep.requests, "get", return_value=mock):
            s, p, err = ep._fetch_live("https://example/x.json")
        assert s == 503 and err == "source_invalid_json"

    def test_normal_200(self):
        mock = MagicMock(); mock.status_code = 200
        mock.json.return_value = {"foo": "bar"}
        with patch.object(ep.requests, "get", return_value=mock):
            s, p, err = ep._fetch_live("https://example/x.json")
        assert s == 200 and p == {"foo": "bar"} and err is None


class TestConstants:
    def test_layer_weights_sum_one(self):
        assert sum(ep.LAYER_WEIGHTS.values()) == pytest.approx(1.0, abs=1e-9)

    def test_mock_scenarios(self):
        assert ep.MOCK_SCENARIOS == ("mock_balanced", "mock_high_pir", "mock_redev_uplift")

    def test_source_env_name(self):
        assert ep.SOURCE_URL_ENV == "ESTATE_BRAIN_SOURCE_URL"
