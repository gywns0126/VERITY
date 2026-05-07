"""KOSIS 권역 중위소득 어댑터 — 단위 테스트.

검증:
  - 키/statId 부재 → None (fail-closed)
  - 정상 응답 파싱 (DT 만원 → 원 변환 + as_of)
  - 서울 5대 권역 매핑 (25구 → center/NE/NW/SW/SE)
  - KOSIS 에러 응답 (`err` / `RESULT.CODE != INFO-000`) → None
"""
from __future__ import annotations

import importlib.util
import os
import sys
import types
from unittest.mock import MagicMock, patch

import pytest


def _load_kosis(monkeypatch, env: dict | None = None):
    for k in ("KOSIS_API_KEY", "KOSIS_OPEN_API_KEY", "KOSIS_INCOME_STAT_ID"):
        monkeypatch.delenv(k, raising=False)
    if env:
        for k, v in env.items():
            monkeypatch.setenv(k, v)

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sources_dir = os.path.join(repo_root, "vercel-api", "api", "landex", "_sources")

    pkg_name = "vercel_landex_kosis_test"
    pkg = types.ModuleType(pkg_name)
    pkg.__path__ = [sources_dir]
    monkeypatch.setitem(sys.modules, pkg_name, pkg)

    spec = importlib.util.spec_from_file_location(
        f"{pkg_name}.kosis", os.path.join(sources_dir, "kosis.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, f"{pkg_name}.kosis", mod)
    spec.loader.exec_module(mod)
    return mod


class TestKeyGate:
    def test_no_key_returns_none(self, monkeypatch):
        kosis = _load_kosis(monkeypatch)
        assert kosis.fetch_seoul_median_income(2024) is None

    def test_key_but_no_stat_id_returns_none(self, monkeypatch):
        kosis = _load_kosis(monkeypatch, env={"KOSIS_API_KEY": "abc"})
        assert kosis.fetch_seoul_median_income(2024) is None


class TestRegionMapping:
    def test_southeast_includes_gangnam_4(self, monkeypatch):
        kosis = _load_kosis(monkeypatch)
        for gu in ("서초구", "강남구", "송파구", "강동구"):
            assert kosis.get_seoul_region(gu) == "southeast"

    def test_center_includes_3(self, monkeypatch):
        kosis = _load_kosis(monkeypatch)
        for gu in ("종로구", "중구", "용산구"):
            assert kosis.get_seoul_region(gu) == "center"

    def test_unknown_gu_returns_none(self, monkeypatch):
        kosis = _load_kosis(monkeypatch)
        assert kosis.get_seoul_region("부산해운대구") is None

    def test_all_25_gu_mapped(self, monkeypatch):
        kosis = _load_kosis(monkeypatch)
        # 25개 모두 매핑 + 5 권역 모두 존재 (분포 검증)
        assert len(kosis.SEOUL_REGION_MAP) == 25
        regions = set(kosis.SEOUL_REGION_MAP.values())
        assert regions == {"center", "northeast", "northwest", "southwest", "southeast"}


class TestParseResponse:
    def test_normal_response_parses(self, monkeypatch):
        kosis = _load_kosis(monkeypatch, env={
            "KOSIS_API_KEY": "abc",
            "KOSIS_INCOME_STAT_ID": "MyStatId",
        })
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = [
            {"PRD_DE": "2024", "DT": "6500", "UNIT_NM": "만원",
             "ITM_NM": "가구당 평균소득", "C1_NM": "서울특별시"},
        ]
        with patch.object(kosis.requests, "get", return_value=mock_resp):
            out = kosis.fetch_seoul_median_income(2024)
        assert out is not None
        assert out["value_won"] == 65_000_000
        assert out["year"] == 2024
        assert out["source"] == "KOSIS"
        assert "collected_at" in out

    def test_empty_list_returns_none(self, monkeypatch):
        kosis = _load_kosis(monkeypatch, env={
            "KOSIS_API_KEY": "abc",
            "KOSIS_INCOME_STAT_ID": "MyStatId",
        })
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = []
        with patch.object(kosis.requests, "get", return_value=mock_resp):
            assert kosis.fetch_seoul_median_income(2024) is None

    def test_err_response_returns_none(self, monkeypatch):
        kosis = _load_kosis(monkeypatch, env={
            "KOSIS_API_KEY": "abc",
            "KOSIS_INCOME_STAT_ID": "MyStatId",
        })
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"err": "INVALID_KEY"}
        with patch.object(kosis.requests, "get", return_value=mock_resp):
            assert kosis.fetch_seoul_median_income(2024) is None

    def test_result_code_non_ok_returns_none(self, monkeypatch):
        kosis = _load_kosis(monkeypatch, env={
            "KOSIS_API_KEY": "abc",
            "KOSIS_INCOME_STAT_ID": "MyStatId",
        })
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"RESULT": {"CODE": "ERR-001"}}
        with patch.object(kosis.requests, "get", return_value=mock_resp):
            assert kosis.fetch_seoul_median_income(2024) is None

    def test_dt_with_comma_parsed(self, monkeypatch):
        kosis = _load_kosis(monkeypatch, env={
            "KOSIS_API_KEY": "abc",
            "KOSIS_INCOME_STAT_ID": "MyStatId",
        })
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = [
            {"PRD_DE": "2024", "DT": "6,500.5", "UNIT_NM": "만원"},
        ]
        with patch.object(kosis.requests, "get", return_value=mock_resp):
            out = kosis.fetch_seoul_median_income(2024)
        assert out["value_won"] == 65_005_000
