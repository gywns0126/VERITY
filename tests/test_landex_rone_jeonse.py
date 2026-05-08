"""R-ONE 전세지수·전세가율 어댑터 + estate_brain helper — 단위 테스트.

검증:
  - REB_STAT_WEEKLY_JEONSE 미설정 → fetch None (R-ONE 키만 있어도 statId gate)
  - 정상 응답 파싱 (전세지수 + 전세가율 schema)
  - compute_jeonse_3m_change_pct 13주 cumulative 변화율
  - latest_jeonse_ratio_pct 단일값 추출
  - compute_unsold_yoy_pct 12개월 YoY
"""
from __future__ import annotations

import importlib.util
import os
import sys
import types
from unittest.mock import MagicMock, patch

import pytest


def _load_rone(monkeypatch, env: dict | None = None):
    for k in (
        "R_ONE_API_KEY", "REB_API_KEY",
        "REB_STAT_WEEKLY_APT_INDEX", "REB_STAT_MONTHLY_UNSOLD",
        "REB_STAT_WEEKLY_JEONSE", "REB_STAT_WEEKLY_JEONSE_RATIO", "REB_STAT_MONTHLY_JEONSE_RATIO",
    ):
        monkeypatch.delenv(k, raising=False)
    if env:
        for k, v in env.items():
            monkeypatch.setenv(k, v)

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sources_dir = os.path.join(repo_root, "vercel-api", "api", "landex", "_sources")

    pkg_name = "vercel_landex_jeonse_test"
    pkg = types.ModuleType(pkg_name)
    pkg.__path__ = [sources_dir]
    monkeypatch.setitem(sys.modules, pkg_name, pkg)

    lawd_spec = importlib.util.spec_from_file_location(
        f"{pkg_name}._lawd", os.path.join(sources_dir, "_lawd.py"),
    )
    lawd_mod = importlib.util.module_from_spec(lawd_spec)
    monkeypatch.setitem(sys.modules, f"{pkg_name}._lawd", lawd_mod)
    lawd_spec.loader.exec_module(lawd_mod)

    rone_spec = importlib.util.spec_from_file_location(
        f"{pkg_name}.rone", os.path.join(sources_dir, "rone.py"),
    )
    rone_mod = importlib.util.module_from_spec(rone_spec)
    monkeypatch.setitem(sys.modules, f"{pkg_name}.rone", rone_mod)
    rone_spec.loader.exec_module(rone_mod)
    return rone_mod


class TestStatIdGate:
    def test_jeonse_index_no_stat_id_returns_none(self, monkeypatch):
        # default DEFAULT_STAT_WEEKLY_JEONSE 박혀있어서 명시적 unset (rone_adapter 패턴 정합)
        rone = _load_rone(monkeypatch, env={
            "R_ONE_API_KEY": "abc",
            "REB_STAT_WEEKLY_JEONSE": "",
        })
        assert rone.fetch_weekly_jeonse_index("강남구") is None

    def test_jeonse_ratio_no_stat_id_returns_none(self, monkeypatch):
        # 월간 ratio default = "" (사용자 검증 대기). env 박지 않으면 None.
        rone = _load_rone(monkeypatch, env={"R_ONE_API_KEY": "abc"})
        assert rone.fetch_monthly_jeonse_ratio("강남구") is None

    def test_jeonse_index_unknown_gu_returns_none(self, monkeypatch):
        rone = _load_rone(monkeypatch, env={
            "R_ONE_API_KEY": "abc",
            "REB_STAT_WEEKLY_JEONSE": "TEST_JEONSE_ID",
        })
        assert rone.fetch_weekly_jeonse_index("부산해운대구") is None


class TestParseJeonseIndex:
    def _mock_response(self, rows):
        mock = MagicMock()
        mock.raise_for_status = MagicMock()
        mock.json.return_value = {
            "SttsApiTblData": [{
                "head": [{"list_total_count": str(len(rows))}],
                "row": rows,
            }],
        }
        return mock

    def test_normal_parse(self, monkeypatch):
        rone = _load_rone(monkeypatch, env={
            "R_ONE_API_KEY": "abc",
            "REB_STAT_WEEKLY_JEONSE": "TEST_JEONSE_ID",
        })
        rows = [
            {"ITM_ID": "10001", "WRTTIME_IDTFR_ID": "202615",
             "WRTTIME_DESC": "2026-04-13", "DTA_VAL": "98.5"},
            {"ITM_ID": "10001", "WRTTIME_IDTFR_ID": "202616",
             "WRTTIME_DESC": "2026-04-20", "DTA_VAL": "99.1"},
            {"ITM_ID": "10001", "WRTTIME_IDTFR_ID": "202617",
             "WRTTIME_DESC": "2026-04-27", "DTA_VAL": "99.8"},
        ]
        with patch.object(rone.requests, "get", return_value=self._mock_response(rows)):
            out = rone.fetch_weekly_jeonse_index("강남구", weeks=3)
        assert out is not None
        assert out["source"] == "rone_weekly_jeonse"
        assert len(out["series"]) == 3
        assert out["series"][-1]["index"] == 99.8
        assert out["as_of_week"] == "202617"


class TestParseJeonseRatio:
    """R-ONE 사양: 매매가격대비 전세가격 비율 = 월간(MM)만 존재 (실측 2026-05-08)."""

    def test_normal_parse_ratio_field(self, monkeypatch):
        rone = _load_rone(monkeypatch, env={
            "R_ONE_API_KEY": "abc",
            "REB_STAT_MONTHLY_JEONSE_RATIO": "TEST_RATIO_ID",
        })
        rows = [
            {"ITM_ID": "100001", "WRTTIME_IDTFR_ID": "202603",
             "WRTTIME_DESC": "2026-03-01", "DTA_VAL": "52.3"},
            {"ITM_ID": "100001", "WRTTIME_IDTFR_ID": "202604",
             "WRTTIME_DESC": "2026-04-01", "DTA_VAL": "53.1"},
        ]
        mock = MagicMock()
        mock.raise_for_status = MagicMock()
        mock.json.return_value = {
            "SttsApiTblData": [{
                "head": [{"list_total_count": "2"}],
                "row": rows,
            }],
        }
        with patch.object(rone.requests, "get", return_value=mock):
            out = rone.fetch_monthly_jeonse_ratio("강남구", months=2)
        assert out is not None
        assert out["source"] == "rone_monthly_jeonse_ratio"
        assert out["series"][-1]["ratio_pct"] == 53.1
        assert out["as_of_month"] == "202604"

    def test_legacy_alias_delegates_to_monthly(self, monkeypatch):
        """fetch_weekly_jeonse_ratio (deprecated) → fetch_monthly_jeonse_ratio 위임 검증."""
        rone = _load_rone(monkeypatch, env={
            "R_ONE_API_KEY": "abc",
            "REB_STAT_WEEKLY_JEONSE_RATIO": "LEGACY_FALLBACK_ID",  # fallback env
        })
        rows = [
            {"ITM_ID": "100001", "WRTTIME_IDTFR_ID": "202604",
             "WRTTIME_DESC": "2026-04-01", "DTA_VAL": "53.1"},
        ]
        mock = MagicMock()
        mock.raise_for_status = MagicMock()
        mock.json.return_value = {
            "SttsApiTblData": [{"head": [{"list_total_count": "1"}], "row": rows}],
        }
        with patch.object(rone.requests, "get", return_value=mock):
            out = rone.fetch_weekly_jeonse_ratio("강남구", weeks=2)
        assert out is not None
        assert out["source"] == "rone_monthly_jeonse_ratio"
        assert "as_of_month" in out


class TestJeonse3MChange:
    def test_13_weeks_cumulative_pct(self, monkeypatch):
        rone = _load_rone(monkeypatch)
        # 13주 시계열, 100 → 105 → +5%
        series = [{"week": f"2026{wk:02d}", "index": 100 + i * (5/12)}
                  for i, wk in enumerate(range(15, 28))]
        payload = {"series": series}
        out = rone.compute_jeonse_3m_change_pct(payload)
        assert out == pytest.approx(5.0, abs=0.05)

    def test_under_13_weeks_returns_none(self, monkeypatch):
        rone = _load_rone(monkeypatch)
        payload = {"series": [{"week": "202615", "index": 100}] * 5}
        assert rone.compute_jeonse_3m_change_pct(payload) is None

    def test_zero_first_returns_none(self, monkeypatch):
        rone = _load_rone(monkeypatch)
        series = [{"week": f"2026{i:02d}", "index": 0 if i == 15 else 100}
                  for i in range(15, 28)]
        payload = {"series": series}
        assert rone.compute_jeonse_3m_change_pct(payload) is None

    def test_none_payload_returns_none(self, monkeypatch):
        rone = _load_rone(monkeypatch)
        assert rone.compute_jeonse_3m_change_pct(None) is None


class TestLatestJeonseRatio:
    def test_latest_value(self, monkeypatch):
        rone = _load_rone(monkeypatch)
        payload = {"series": [
            {"week": "202615", "ratio_pct": 52.0},
            {"week": "202616", "ratio_pct": 52.5},
            {"week": "202617", "ratio_pct": 53.1},
        ]}
        assert rone.latest_jeonse_ratio_pct(payload) == 53.1

    def test_empty_returns_none(self, monkeypatch):
        rone = _load_rone(monkeypatch)
        assert rone.latest_jeonse_ratio_pct({"series": []}) is None
        assert rone.latest_jeonse_ratio_pct(None) is None


class TestUnsoldYoY:
    def test_yoy_change_pct(self, monkeypatch):
        rone = _load_rone(monkeypatch)
        series = [{"month": f"2025{m:02d}", "unsold": 100} for m in range(1, 13)] + [
            {"month": "202601", "unsold": 130},
        ]
        out = rone.compute_unsold_yoy_pct({"series": series})
        # 13개월 전 = 100 → 현재 130 → +30%
        assert out == 30.0

    def test_zero_prior_returns_sentinel_or_none(self, monkeypatch):
        rone = _load_rone(monkeypatch)
        series = [{"month": f"2025{m:02d}", "unsold": 0} for m in range(1, 13)] + [
            {"month": "202601", "unsold": 50},
        ]
        # 0 → 양수 = 적체 발생 sentinel
        assert rone.compute_unsold_yoy_pct({"series": series}) == 999.0

    def test_zero_to_zero_returns_none(self, monkeypatch):
        rone = _load_rone(monkeypatch)
        series = [{"month": f"2025{m:02d}", "unsold": 0} for m in range(1, 14)]
        assert rone.compute_unsold_yoy_pct({"series": series}) is None

    def test_under_13_months_returns_none(self, monkeypatch):
        rone = _load_rone(monkeypatch)
        series = [{"month": f"2025{m:02d}", "unsold": 100} for m in range(1, 6)]
        assert rone.compute_unsold_yoy_pct({"series": series}) is None
