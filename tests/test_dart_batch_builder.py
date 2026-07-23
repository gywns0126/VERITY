"""dart_batch_builder 단위 테스트 — 증분 freshness 판정."""
from __future__ import annotations

from api.builders.dart_batch_builder import _is_fresh_dart


class TestIsFreshDart:
    BASE = {"source": "DART", "report_date": "2025", "total_assets": 1000}

    def test_cashflow_present_is_fresh(self):
        rec = {**self.BASE, "operating_cashflow": 500, "investing_cashflow": -200, "financing_cashflow": -100}
        assert _is_fresh_dart(rec, "2025") is True

    def test_all_cashflow_zero_is_stale(self):
        # 자산은 있는데 현금흐름 3종 전부 0 = CF 파싱 미스 → 재추출 강제 (2026-07 account_id fix 소급)
        rec = {**self.BASE, "operating_cashflow": 0, "investing_cashflow": 0, "financing_cashflow": 0}
        assert _is_fresh_dart(rec, "2025") is False

    def test_missing_cashflow_keys_is_stale(self):
        assert _is_fresh_dart(dict(self.BASE), "2025") is False

    def test_partial_cashflow_is_fresh(self):
        rec = {**self.BASE, "investing_cashflow": -200}
        assert _is_fresh_dart(rec, "2025") is True

    def test_wrong_year_is_stale(self):
        rec = {**self.BASE, "report_date": "2024", "operating_cashflow": 500}
        assert _is_fresh_dart(rec, "2025") is False

    def test_no_assets_is_stale(self):
        rec = {"source": "DART", "report_date": "2025", "total_assets": 0, "operating_cashflow": 500}
        assert _is_fresh_dart(rec, "2025") is False
