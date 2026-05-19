"""GET /api/estate/corp-disposals endpoint — 단위 테스트.

검증:
  - _is_property_disposal: 부동산 키워드 ∩ 처분 키워드, 자기주식 제외
  - _filter_disposals: 매칭 row 만 추출 + 필드 정리
"""
from __future__ import annotations

import importlib.util
import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_EP_PATH = os.path.join(_REPO_ROOT, "vercel-api", "api", "estate_corp_disposals.py")

_spec = importlib.util.spec_from_file_location("ep_estate_corp_disposals", _EP_PATH)
ep = importlib.util.module_from_spec(_spec)
sys.modules["ep_estate_corp_disposals"] = ep
_spec.loader.exec_module(ep)


class TestIsPropertyDisposal:
    @pytest.mark.parametrize("report_nm,expected", [
        ("주요사항보고서(유형자산 양도결정)", True),
        ("주요사항보고서(토지 매각 결정)", True),
        ("주요사항보고서(부동산 양도결정)", True),
        ("주요사항보고서(본사 매각 결정)", True),
        ("주요사항보고서(건물 매각결정)", True),
        ("주요사항보고서(사업장 처분 결정)", True),
        ("주요사항보고서(지점 폐쇄 양도결정)", True),
    ])
    def test_property_disposal_match(self, report_nm, expected):
        assert ep._is_property_disposal(report_nm) is expected

    @pytest.mark.parametrize("report_nm", [
        "자기주식처분결과보고서",
        "주요사항보고서(자기주식처분결정)",
        "주식양도결의",
        "주요사항보고서(영업양수도결정)",
        "정기공시 (사업보고서)",
        "감사보고서",
        "",
    ])
    def test_non_property_disposal(self, report_nm):
        assert ep._is_property_disposal(report_nm) is False


class TestFilterDisposals:
    def test_extract_matched_rows(self):
        rows = [
            {"rcept_dt": "20251015", "report_nm": "주요사항보고서(유형자산 양도결정)",
             "rcept_no": "20251015000001", "flr_nm": "샘플전자"},
            {"rcept_dt": "20251020", "report_nm": "자기주식처분결과보고서",
             "rcept_no": "20251020000001", "flr_nm": "샘플전자"},
            {"rcept_dt": "20251025", "report_nm": "주요사항보고서(토지 매각 결정)",
             "rcept_no": "20251025000001", "flr_nm": "샘플전자"},
        ]
        out = ep._filter_disposals(rows)
        assert len(out) == 2
        assert out[0]["report_nm"] == "주요사항보고서(유형자산 양도결정)"
        assert out[1]["report_nm"] == "주요사항보고서(토지 매각 결정)"
        for row in out:
            assert set(row.keys()) == {"rcept_dt", "report_nm", "rcept_no", "flr_nm"}

    def test_empty_input(self):
        assert ep._filter_disposals([]) == []

    def test_no_matches(self):
        rows = [
            {"rcept_dt": "20251015", "report_nm": "정기공시 (사업보고서)", "rcept_no": "x", "flr_nm": "y"},
            {"rcept_dt": "20251020", "report_nm": "자기주식처분결과보고서", "rcept_no": "z", "flr_nm": "y"},
        ]
        assert ep._filter_disposals(rows) == []
