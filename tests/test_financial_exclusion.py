"""Stage 1.5 금융업(industry) 제외 단위 테스트 (2026-06-07, funnel Phase A.2).

PM 결정 = industry 기준 (은행/보험/여신). 자산경량 금융(데이터/거래소)은 유지.
증권(Capital Markets)/자산운용(Asset Management)은 본 경계 밖.
"""
from __future__ import annotations

from api.analyzers.stock_filter import exclude_financial_sector


def _stk(name, industry, **kw):
    d = {"name": name, "ticker": name, "industry": industry}
    d.update(kw)
    return d


class TestFinancialExclusion:
    def test_banks_excluded(self):
        stocks = [
            _stk("JB금융지주", "Banks - Regional"),
            _stk("BAC", "Banks - Diversified"),
            _stk("JPM", "Banks - Diversified"),
        ]
        assert exclude_financial_sector(stocks) == []

    def test_insurance_excluded(self):
        assert exclude_financial_sector([_stk("BRK-B", "Insurance - Diversified")]) == []

    def test_credit_services_excluded(self):
        assert exclude_financial_sector([_stk("SOFI", "Credit Services")]) == []

    def test_financial_data_exchange_kept(self):
        # 에프앤가이드 류 = 자산경량, 팩터 왜곡 없음 → 유지 (sector 통째 제외였으면 빠졌을 것)
        out = exclude_financial_sector([_stk("에프앤가이드", "Financial Data & Stock Exchanges")])
        assert len(out) == 1

    def test_capital_markets_kept_out_of_boundary(self):
        # 증권/자산운용 = 본 경계 밖 (PM 결정 = 은행/보험/여신만)
        out = exclude_financial_sector([
            _stk("증권사", "Capital Markets"),
            _stk("운용사", "Asset Management"),
        ])
        assert len(out) == 2

    def test_nonfinancial_kept(self):
        out = exclude_financial_sector([_stk("삼성전자", "Semiconductors")])
        assert len(out) == 1

    def test_empty_industry_kept_conservative(self):
        # yfinance industry 미제공 = 통과 (결손 데이터로 과제외 회피)
        out = exclude_financial_sector([_stk("미상장소형주", "")])
        assert len(out) == 1

    def test_core_financial_still_excluded(self):
        # 금융 제외는 코어도 적용 (팩터 왜곡은 코어 무관)
        out = exclude_financial_sector([_stk("코어은행", "Banks - Regional", is_core=True)])
        assert out == []

    def test_mixed_pool(self):
        stocks = [
            _stk("삼성전자", "Semiconductors"),
            _stk("JB금융지주", "Banks - Regional"),
            _stk("에프앤가이드", "Financial Data & Stock Exchanges"),
            _stk("BRK-B", "Insurance - Diversified"),
        ]
        out = exclude_financial_sector(stocks)
        names = {s["name"] for s in out}
        assert names == {"삼성전자", "에프앤가이드"}
