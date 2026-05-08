"""BIS FRED 어댑터 — 단위 테스트.

검증:
  - csv parse 정합 (1975Q1~)
  - YYYY-MM-DD → YYYYQN 변환
  - 빈 값 / 잘못된 row skip
  - HTTP 실패 → None
"""
from __future__ import annotations

import importlib.util
import os
import sys
import types
from unittest.mock import MagicMock, patch

import pytest


def _load_bis(monkeypatch):
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sources_dir = os.path.join(repo, "vercel-api", "api", "landex", "_sources")
    pkg_name = "vercel_landex_bis_test"
    pkg = types.ModuleType(pkg_name)
    pkg.__path__ = [sources_dir]
    monkeypatch.setitem(sys.modules, pkg_name, pkg)

    spec = importlib.util.spec_from_file_location(
        f"{pkg_name}.bis", os.path.join(sources_dir, "bis.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, f"{pkg_name}.bis", mod)
    spec.loader.exec_module(mod)
    return mod


SAMPLE_CSV = """DATE,QKRR628BIS
1975-01-01,33.6504
1975-04-01,33.4567
1975-07-01,33.8123
1975-10-01,34.1245
1976-01-01,.
2025-10-01,105.7143
"""


class TestDateToQuarter:
    def test_q1(self, monkeypatch):
        bis = _load_bis(monkeypatch)
        assert bis._date_to_quarter("2025-01-01") == "2025Q1"
        assert bis._date_to_quarter("2025-02-15") == "2025Q1"
        assert bis._date_to_quarter("2025-03-31") == "2025Q1"

    def test_q2_q3_q4(self, monkeypatch):
        bis = _load_bis(monkeypatch)
        assert bis._date_to_quarter("2025-04-01") == "2025Q2"
        assert bis._date_to_quarter("2025-07-01") == "2025Q3"
        assert bis._date_to_quarter("2025-10-01") == "2025Q4"

    def test_invalid(self, monkeypatch):
        bis = _load_bis(monkeypatch)
        assert bis._date_to_quarter("not-a-date") is None
        assert bis._date_to_quarter("") is None


class TestFetch:
    def _resp(self, body, status=200):
        m = MagicMock()
        m.status_code = status
        m.text = body
        if status >= 400:
            m.raise_for_status.side_effect = Exception(f"HTTP {status}")
        return m

    def test_normal_csv_parse(self, monkeypatch):
        bis = _load_bis(monkeypatch)
        with patch.object(bis.requests, "get", return_value=self._resp(SAMPLE_CSV)):
            out = bis.fetch_bis_korea_real_rppi()
        assert out is not None
        # 5 valid rows (빈 점 1개 skip)
        assert out["n_points"] == 5
        assert out["series"][0]["date"] == "1975-01-01"
        assert out["series"][0]["quarter"] == "1975Q1"
        assert out["series"][0]["index"] == pytest.approx(33.6504)
        assert out["series"][-1]["quarter"] == "2025Q4"
        assert out["as_of"] == "2025Q4"
        assert out["unit"] == "index_2010_100_real"

    def test_http_failure_returns_none(self, monkeypatch):
        import requests as req
        bis = _load_bis(monkeypatch)
        with patch.object(bis.requests, "get",
                          side_effect=req.RequestException("net err")):
            assert bis.fetch_bis_korea_real_rppi() is None

    def test_empty_body_returns_none(self, monkeypatch):
        bis = _load_bis(monkeypatch)
        with patch.object(bis.requests, "get", return_value=self._resp("")):
            assert bis.fetch_bis_korea_real_rppi() is None

    def test_header_only_returns_none(self, monkeypatch):
        bis = _load_bis(monkeypatch)
        with patch.object(bis.requests, "get",
                          return_value=self._resp("DATE,QKRR628BIS\n")):
            assert bis.fetch_bis_korea_real_rppi() is None

    def test_dot_values_skipped(self, monkeypatch):
        # FRED csv 결측 = "." — skip
        bis = _load_bis(monkeypatch)
        body = "DATE,QKRR628BIS\n2024-01-01,.\n2024-04-01,100.0\n"
        with patch.object(bis.requests, "get", return_value=self._resp(body)):
            out = bis.fetch_bis_korea_real_rppi()
        assert out["n_points"] == 1
        assert out["series"][0]["quarter"] == "2024Q2"

    def test_sort_ascending_by_date(self, monkeypatch):
        # 입력 순서 무관하게 시간 정렬
        bis = _load_bis(monkeypatch)
        body = "DATE,QKRR628BIS\n2025-01-01,90\n1975-01-01,33\n2000-04-01,60\n"
        with patch.object(bis.requests, "get", return_value=self._resp(body)):
            out = bis.fetch_bis_korea_real_rppi()
        assert [s["quarter"] for s in out["series"]] == ["1975Q1", "2000Q2", "2025Q1"]
