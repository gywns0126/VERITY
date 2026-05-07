"""ECOS estate_brain 입력 helper — 단위 테스트.

검증:
  - fetch_korea_policy_rate_series: 키 미설정 → []
  - compute_rate_change_pp: N개월 전 vs 최신 차이 (pp)
  - latest_treasury_10y_pct: macro_block → 단일값 추출
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


class TestFetchSeriesNoKey:
    def test_returns_empty_when_no_key(self, monkeypatch):
        from api.collectors import ecos_macro as ecos
        monkeypatch.setattr(ecos, "ECOS_API_KEY", "")
        assert ecos.fetch_korea_policy_rate_series(months=24) == []


class TestComputeRateChangePP:
    def test_six_months_back(self):
        from api.collectors import ecos_macro as ecos
        # 7 rows: 0.5 → 1.0 → 1.5 → 2.0 → 2.5 → 3.0 → 3.5
        # months_back=6 → latest 3.5 - prior(첫 row) 0.5 = 3.0
        rows = [{"DATA_VALUE": str(0.5 + i * 0.5), "TIME": f"20250{i+1}"}
                for i in range(7)]
        assert ecos.compute_rate_change_pp(rows, months_back=6) == 3.0

    def test_three_months_back(self):
        from api.collectors import ecos_macro as ecos
        rows = [{"DATA_VALUE": str(2.0 + i * 0.25), "TIME": f"20250{i+1}"}
                for i in range(7)]
        # latest = 3.5, prior 4 rows back = rows[-4] = 2.75 → 0.75
        assert ecos.compute_rate_change_pp(rows, months_back=3) == 0.75

    def test_insufficient_rows_returns_none(self):
        from api.collectors import ecos_macro as ecos
        rows = [{"DATA_VALUE": "3.0"}] * 3
        assert ecos.compute_rate_change_pp(rows, months_back=6) is None

    def test_empty_rows_returns_none(self):
        from api.collectors import ecos_macro as ecos
        assert ecos.compute_rate_change_pp([], months_back=6) is None
        assert ecos.compute_rate_change_pp(None, months_back=6) is None

    def test_invalid_value_returns_none(self):
        from api.collectors import ecos_macro as ecos
        rows = [{"DATA_VALUE": "abc"}] * 8
        assert ecos.compute_rate_change_pp(rows, months_back=6) is None


class TestLatestTreasury10y:
    def test_normal_block(self):
        from api.collectors import ecos_macro as ecos
        block = {
            "available": True,
            "korea_gov_10y": {"value": 3.21, "date": "2026-04-29"},
        }
        assert ecos.latest_treasury_10y_pct(block) == 3.21

    def test_missing_block_returns_none(self):
        from api.collectors import ecos_macro as ecos
        assert ecos.latest_treasury_10y_pct(None) is None
        assert ecos.latest_treasury_10y_pct({}) is None
        assert ecos.latest_treasury_10y_pct({"korea_gov_10y": None}) is None

    def test_invalid_value_returns_none(self):
        from api.collectors import ecos_macro as ecos
        block = {"korea_gov_10y": {"value": "not_a_number"}}
        assert ecos.latest_treasury_10y_pct(block) is None
