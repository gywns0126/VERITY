"""BIS FRED URL + column 정합 검증 — 2026-05-10 deprecated URL fix 회귀 가드.

배경: FRED 가 옛 `/series/{id}/downloaddata/{id}.csv` 를 *malformed redirect*
(Location: https://https://...) 로 폐기 → requests NameResolutionError. 새 URL
`/graph/fredgraph.csv?id={id}` + 컬럼 `observation_date` 가 정답.

본 테스트는 *코드 contract* 보호 (fetch 결과는 mock 으로 검증, 실 네트워크 X).
"""
from __future__ import annotations

import csv
import importlib.util
import io
import os
import sys
import types
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
SOURCES_DIR = ROOT / "vercel-api" / "api" / "landex" / "_sources"


@pytest.fixture(scope="module")
def bis_module():
    pkg_name = "test_estate_50y_sources_bis"
    pkg = types.ModuleType(pkg_name)
    pkg.__path__ = [str(SOURCES_DIR)]
    sys.modules[pkg_name] = pkg
    spec = importlib.util.spec_from_file_location(
        f"{pkg_name}.bis", str(SOURCES_DIR / "bis.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[f"{pkg_name}.bis"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_url_is_graph_endpoint_not_deprecated_downloaddata(bis_module):
    """URL contract — 옛 deprecated 경로 사용 금지."""
    url = bis_module.FRED_KOREA_REAL_RPPI_URL
    assert "/graph/fredgraph.csv" in url, f"URL must use /graph/ endpoint, got: {url}"
    assert "/downloaddata/" not in url, f"Deprecated /downloaddata/ path detected: {url}"
    assert "id=QKRR628BIS" in url


def test_csv_columns_accept_both_legacy_and_new(bis_module):
    """observation_date(신) 와 DATE(옛) 둘 다 허용 — FRED 변경 양방향 안전."""
    assert "observation_date" in bis_module.CSV_DATE_COLUMNS
    assert "DATE" in bis_module.CSV_DATE_COLUMNS


def _make_response(body: str, status: int = 200):
    class _R:
        def __init__(self, text, code):
            self.text = text
            self.status_code = code
        def raise_for_status(self):
            if self.status_code >= 400:
                from requests import HTTPError
                raise HTTPError(f"HTTP {self.status_code}")
    return _R(body, status)


def test_parses_new_observation_date_column(bis_module):
    """신 column `observation_date` 를 정상 파싱."""
    csv_body = "observation_date,QKRR628BIS\n1975-01-01,63.2453\n2025-10-01,105.71\n"
    with patch.object(bis_module.requests, "get", return_value=_make_response(csv_body)):
        result = bis_module.fetch_bis_korea_real_rppi()
    assert result is not None
    assert result["n_points"] == 2
    assert result["series"][0]["date"] == "1975-01-01"
    assert result["series"][0]["quarter"] == "1975Q1"
    assert result["series"][-1]["quarter"] == "2025Q4"
    assert result["as_of"] == "2025Q4"


def test_parses_legacy_DATE_column_backcompat(bis_module):
    """옛 `DATE` column 도 여전히 처리 (FRED 가 다시 바꿔도 안전)."""
    csv_body = "DATE,QKRR628BIS\n1975-01-01,33.65\n"
    with patch.object(bis_module.requests, "get", return_value=_make_response(csv_body)):
        result = bis_module.fetch_bis_korea_real_rppi()
    assert result is not None
    assert result["series"][0]["date"] == "1975-01-01"


def test_skips_dot_placeholder_values(bis_module):
    """FRED `.` placeholder (관측 없음) skip — 빈 시리즈로 누락 X."""
    csv_body = "observation_date,QKRR628BIS\n1975-01-01,.\n1975-04-01,65.3\n"
    with patch.object(bis_module.requests, "get", return_value=_make_response(csv_body)):
        result = bis_module.fetch_bis_korea_real_rppi()
    assert result is not None
    assert result["n_points"] == 1
    assert result["series"][0]["index"] == 65.3
