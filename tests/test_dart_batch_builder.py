"""dart_batch_builder 단위 테스트 — 증분 freshness 판정 (재수집 강제 가드)."""
from __future__ import annotations

from api.builders.dart_batch_builder import _is_fresh_dart


class TestIsFreshDart:
    # 완전한 최신 record: DART·당해연도·자산有·CF有·손익상세(sga/income_tax)有·순이익 정합
    BASE = {
        "source": "DART", "report_date": "2025", "total_assets": 1000,
        "operating_cashflow": 100, "investing_cashflow": -50, "financing_cashflow": -20,
        "sga": 50, "income_tax": 10, "net_income": 80, "pretax_income": 90,
    }

    def test_complete_record_is_fresh(self):
        assert _is_fresh_dart(dict(self.BASE), "2025") is True

    def test_all_cashflow_zero_is_stale(self):
        # 자산有·CF 3종 전부 0 = CF 파싱 미스 → 재추출 (2026-07 account_id fix 소급)
        rec = {**self.BASE, "operating_cashflow": 0, "investing_cashflow": 0, "financing_cashflow": 0}
        assert _is_fresh_dart(rec, "2025") is False

    def test_missing_income_tax_key_is_stale(self):
        # 손익상세(2026-05-20 확장) KEY 부재 = 확장 이전 수집 → 재추출
        rec = {k: v for k, v in self.BASE.items() if k != "income_tax"}
        assert _is_fresh_dart(rec, "2025") is False

    def test_missing_sga_key_is_stale(self):
        rec = {k: v for k, v in self.BASE.items() if k != "sga"}
        assert _is_fresh_dart(rec, "2025") is False

    def test_net_zero_but_pretax_nonzero_is_stale(self):
        # net=0 인데 법인세차감전≠0 = 적자기업 순이익 클램프/라벨 미스 잔재 → 재추출
        rec = {**self.BASE, "net_income": 0, "pretax_income": 90}
        assert _is_fresh_dart(rec, "2025") is False

    def test_net_zero_and_pretax_zero_is_fresh(self):
        # 손익 자체가 없는(무영업) 정상 0 → 재사용 (재수집으로도 안 채워짐)
        rec = {**self.BASE, "net_income": 0, "pretax_income": 0}
        assert _is_fresh_dart(rec, "2025") is True

    def test_wrong_year_is_stale(self):
        rec = {**self.BASE, "report_date": "2024"}
        assert _is_fresh_dart(rec, "2025") is False

    def test_no_assets_is_stale(self):
        rec = {**self.BASE, "total_assets": 0}
        assert _is_fresh_dart(rec, "2025") is False

    def test_non_dart_source_is_stale(self):
        rec = {**self.BASE, "source": "yfinance_fallback"}
        assert _is_fresh_dart(rec, "2025") is False

    def test_op_oparsing_eps_is_stale(self):
        # 매출 큰데 op 극소(EPS 5,287원 오치환 꼴) → 재추출 (op account_id 승격 소급)
        rec = {**self.BASE, "total_assets": int(1e12), "revenue": int(1e12), "operating_profit": 5287}
        assert _is_fresh_dart(rec, "2025") is False

    def test_op_zero_large_revenue_is_stale(self):
        rec = {**self.BASE, "total_assets": int(1e12), "revenue": int(1e12), "operating_profit": 0}
        assert _is_fresh_dart(rec, "2025") is False

    def test_revenue_zero_large_assets_is_stale(self):
        # 자산 큰데 매출 0 = top-line '매출' 누락 → 재추출 (LG화학류)
        rec = {**self.BASE, "total_assets": int(2e11), "revenue": 0, "operating_profit": int(1e11)}
        assert _is_fresh_dart(rec, "2025") is False

    def test_large_company_clean_op_is_fresh(self):
        rec = {**self.BASE, "total_assets": int(1e12), "revenue": int(1e12), "operating_profit": int(1e11)}
        assert _is_fresh_dart(rec, "2025") is True
