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


class TestREBAptPriceIndex:
    """KOSIS REB 공동주택 매매 실거래가격지수 (DT_KAB_11672_S13, 2006~ 월).

    2026-05-10 정정 — 옛 KB 1986~ tblId=101Y014 가정 폐기 (KOSIS 부재).
    """

    def test_no_key_returns_none(self, monkeypatch):
        kosis = _load_kosis(monkeypatch)
        assert kosis.fetch_reb_apt_price_index(region_nm="전국") is None

    def test_invalid_region_nm_returns_none(self, monkeypatch):
        kosis = _load_kosis(monkeypatch, env={"KOSIS_API_KEY": "abc"})
        assert kosis.fetch_reb_apt_price_index(region_nm="강남구") is None

    def test_normal_parse_monthly_series(self, monkeypatch):
        kosis = _load_kosis(monkeypatch, env={"KOSIS_API_KEY": "abc"})
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        # objL1=ALL 호출이라 9 권역 mixed 응답. region_nm 필터로 1개만 통과.
        mock_resp.json.return_value = [
            {"PRD_DE": "200601", "DT": "58.17", "C1_NM": "전국"},
            {"PRD_DE": "200601", "DT": "60.00", "C1_NM": "서울"},  # 다른 권역 mixed
            {"PRD_DE": "200602", "DT": "58.60", "C1_NM": "전국"},
            {"PRD_DE": "202602", "DT": "128.86", "C1_NM": "전국"},
        ]
        with patch.object(kosis.requests, "get", return_value=mock_resp):
            out = kosis.fetch_reb_apt_price_index(region_nm="전국")
        assert out is not None
        assert out["source"] == "KOSIS_REB_APT"
        assert out["n_points"] == 3  # 서울 row 제외
        assert out["series"][0]["month"] == "200601"
        assert out["series"][-1]["month"] == "202602"
        assert out["region_nm"] == "전국"

    def test_default_stat_id_dt_kab_11672(self, monkeypatch):
        kosis = _load_kosis(monkeypatch, env={"KOSIS_API_KEY": "abc"})
        assert kosis._reb_apt_index_stat_id() == "DT_KAB_11672_S13"

    def test_env_override_stat_id_new_name(self, monkeypatch):
        kosis = _load_kosis(monkeypatch, env={
            "KOSIS_API_KEY": "abc",
            "KOSIS_REB_APT_INDEX_STAT_ID": "CUSTOM_REB",
        })
        assert kosis._reb_apt_index_stat_id() == "CUSTOM_REB"

    def test_env_override_stat_id_legacy_alias(self, monkeypatch):
        """옛 env 이름 KOSIS_KB_INDEX_STAT_ID 도 backward compat."""
        kosis = _load_kosis(monkeypatch, env={
            "KOSIS_API_KEY": "abc",
            "KOSIS_KB_INDEX_STAT_ID": "LEGACY_VALUE",
        })
        assert kosis._reb_apt_index_stat_id() == "LEGACY_VALUE"

    def test_kosis_error_response_returns_none(self, monkeypatch):
        kosis = _load_kosis(monkeypatch, env={"KOSIS_API_KEY": "abc"})
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"err": "21", "errMsg": "통계표 부재"}
        with patch.object(kosis.requests, "get", return_value=mock_resp):
            assert kosis.fetch_reb_apt_price_index(region_nm="전국") is None

    def test_empty_rows_returns_none(self, monkeypatch):
        kosis = _load_kosis(monkeypatch, env={"KOSIS_API_KEY": "abc"})
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = []
        with patch.object(kosis.requests, "get", return_value=mock_resp):
            assert kosis.fetch_reb_apt_price_index(region_nm="전국") is None

    def test_sort_ascending(self, monkeypatch):
        kosis = _load_kosis(monkeypatch, env={"KOSIS_API_KEY": "abc"})
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = [
            {"PRD_DE": "201001", "DT": "80.0", "C1_NM": "전국"},
            {"PRD_DE": "200601", "DT": "58.0", "C1_NM": "전국"},
            {"PRD_DE": "201501", "DT": "100.0", "C1_NM": "전국"},
        ]
        with patch.object(kosis.requests, "get", return_value=mock_resp):
            out = kosis.fetch_reb_apt_price_index(region_nm="전국")
        months = [s["month"] for s in out["series"]]
        assert months == ["200601", "201001", "201501"]

    def test_kb_alias_still_works(self, monkeypatch):
        """fetch_kb_house_price_index = fetch_reb_apt_price_index alias 보장."""
        kosis = _load_kosis(monkeypatch, env={"KOSIS_API_KEY": "abc"})
        assert kosis.fetch_kb_house_price_index is kosis.fetch_reb_apt_price_index

    def test_9_regions_enum(self, monkeypatch):
        """KOSIS_REB_REGION_CODES 9 권역 keys 보존."""
        kosis = _load_kosis(monkeypatch)
        assert set(kosis.KOSIS_REB_REGION_CODES.keys()) == {
            "전국", "수도권", "지방", "서울", "인천", "경기",
            "광역시", "지방광역시", "지방도",
        }


class TestHousingPipeline:
    """국토교통부 주택건설 supply pipeline (DT_MLTM_5387/5373/5557)."""

    def test_housing_pipeline_regions_enum(self, monkeypatch):
        kosis = _load_kosis(monkeypatch)
        assert "전국" in kosis.HOUSING_PIPELINE_REGIONS
        assert "서울" in kosis.HOUSING_PIPELINE_REGIONS
        assert "기타광역시" in kosis.HOUSING_PIPELINE_REGIONS
        # 세종 + 17 광역 + 권역/합계 등
        assert len(kosis.HOUSING_PIPELINE_REGIONS) >= 22

    def test_housing_types_enum(self, monkeypatch):
        kosis = _load_kosis(monkeypatch)
        assert kosis.HOUSING_TYPES == frozenset(
            ["아파트", "연립", "다세대", "단독", "다가구"]
        )

    def test_region_aliases_normalize_total(self, monkeypatch):
        """전국 → ["총계", "합계"] alias — 통계표마다 macro 라벨 다름."""
        kosis = _load_kosis(monkeypatch)
        assert "총계" in kosis._REGION_ALIASES["전국"]
        assert "합계" in kosis._REGION_ALIASES["전국"]
        assert "수도권소계" in kosis._REGION_ALIASES["수도권"]

    def test_starts_no_key_returns_none(self, monkeypatch):
        kosis = _load_kosis(monkeypatch)
        assert kosis.fetch_housing_construction_starts(region_nm="서울") is None

    def test_starts_invalid_region_returns_none(self, monkeypatch):
        kosis = _load_kosis(monkeypatch, env={"KOSIS_API_KEY": "abc"})
        assert kosis.fetch_housing_construction_starts(region_nm="강남구") is None

    def test_starts_invalid_housing_type_returns_none(self, monkeypatch):
        kosis = _load_kosis(monkeypatch, env={"KOSIS_API_KEY": "abc"})
        assert kosis.fetch_housing_construction_starts(
            region_nm="서울", housing_type="oddtype",
        ) is None

    def test_starts_alias_filter_total_to_총계(self, monkeypatch):
        """전국 입력 시 응답의 C1_NM='총계' row 가 통과."""
        kosis = _load_kosis(monkeypatch, env={"KOSIS_API_KEY": "abc"})
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = [
            {"C1_NM": "총계", "C2_NM": "아파트", "PRD_DE": "202602", "DT": "15000.0"},
            {"C1_NM": "서울", "C2_NM": "아파트", "PRD_DE": "202602", "DT": "500.0"},  # 다른 region
            {"C1_NM": "총계", "C2_NM": "단독", "PRD_DE": "202602", "DT": "200.0"},  # 다른 type
        ]
        with patch.object(kosis.requests, "get", return_value=mock_resp):
            out = kosis.fetch_housing_construction_starts(
                region_nm="전국", housing_type="아파트",
            )
        assert out is not None
        assert out["n_points"] == 1
        assert out["series"][0]["value"] == 15000.0
        assert out["region_nm"] == "전국"
        assert out["housing_type"] == "아파트"
        assert out["source"] == "KOSIS_MLTM_HOUSING_STARTS"

    def test_subscription_apt_alias_total(self, monkeypatch):
        """분양 — 전국 → C1_NM='합계' alias."""
        kosis = _load_kosis(monkeypatch, env={"KOSIS_API_KEY": "abc"})
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = [
            {"C1_NM": "합계", "PRD_DE": "202603", "DT": "37224.0"},
            {"C1_NM": "수도권", "PRD_DE": "202603", "DT": "11285.0"},
        ]
        with patch.object(kosis.requests, "get", return_value=mock_resp):
            out = kosis.fetch_housing_subscription_apt(region_nm="전국")
        assert out is not None
        assert out["n_points"] == 1
        assert out["region_nm"] == "전국"  # alias 적용

    def test_subscription_apt_invalid_macro_region(self, monkeypatch):
        """분양은 macro region only — 서울 같은 시도 명은 None."""
        kosis = _load_kosis(monkeypatch, env={"KOSIS_API_KEY": "abc"})
        assert kosis.fetch_housing_subscription_apt(region_nm="서울") is None

    def test_permits_alias_filter(self, monkeypatch):
        """인허가 (DT_MLTM_1948) — 전국 alias '합계(가구수기준)' 안 됨, '총계' 매칭."""
        kosis = _load_kosis(monkeypatch, env={"KOSIS_API_KEY": "abc"})
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = [
            {"C1_NM": "총계", "C2_NM": "아파트", "PRD_DE": "202601", "DT": "13702.0"},
            {"C1_NM": "총계", "C2_NM": "아파트", "PRD_DE": "202602", "DT": "25929.0"},
            {"C1_NM": "서울", "C2_NM": "아파트", "PRD_DE": "202602", "DT": "1234.0"},  # 다른 region
        ]
        with patch.object(kosis.requests, "get", return_value=mock_resp):
            out = kosis.fetch_housing_construction_permits(
                region_nm="전국", housing_type="아파트",
            )
        assert out is not None
        assert out["n_points"] == 2
        assert out["series"][0]["value"] == 13702.0
        assert out["source"] == "KOSIS_MLTM_HOUSING_PERMITS"


class TestYtdToMonthlyNew:
    """월별 누계 (yearly-to-date) → 순수 월별 신규 변환."""

    def test_january_passthrough(self, monkeypatch):
        kosis = _load_kosis(monkeypatch)
        s = [{"month": "202601", "value": 13702.0}]
        out = kosis.ytd_to_monthly_new(s)
        assert out[0]["value"] == 13702.0

    def test_diff_for_subsequent_months(self, monkeypatch):
        kosis = _load_kosis(monkeypatch)
        s = [
            {"month": "202601", "value": 13702.0},
            {"month": "202602", "value": 25929.0},
            {"month": "202603", "value": 41880.0},
        ]
        out = kosis.ytd_to_monthly_new(s)
        assert out[0]["value"] == 13702.0
        assert out[1]["value"] == pytest.approx(12227.0)
        assert out[2]["value"] == pytest.approx(15951.0)

    def test_year_boundary_reset(self, monkeypatch):
        """다음 연도 1월 = reset (그대로 keep, 차분 X)."""
        kosis = _load_kosis(monkeypatch)
        s = [
            {"month": "202512", "value": 200000.0},  # 2025년 12월 누계 (= 그해 합계)
            {"month": "202601", "value": 13702.0},   # 2026년 1월 = reset
        ]
        out = kosis.ytd_to_monthly_new(s)
        assert out[0]["value"] == 200000.0
        assert out[1]["value"] == 13702.0  # 200000 - 13702 X, 그대로

    def test_empty_returns_empty(self, monkeypatch):
        kosis = _load_kosis(monkeypatch)
        assert kosis.ytd_to_monthly_new([]) == []

    def test_skips_invalid_month(self, monkeypatch):
        kosis = _load_kosis(monkeypatch)
        s = [
            {"month": "ABC", "value": 100.0},
            {"month": "202601", "value": 13702.0},
        ]
        out = kosis.ytd_to_monthly_new(s)
        assert len(out) == 1
        assert out[0]["value"] == 13702.0
