"""dart_fundamentals 단위 테스트 (Phase 2-A) — DART/yfinance mock."""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from api.collectors import dart_fundamentals as df


# ─────────────────────────────────────────────────────────────────────
# DART 데이터 추출
# ─────────────────────────────────────────────────────────────────────

class TestExtractPLBS:
    def test_extract_basic(self):
        data = {
            "list": [
                {"sj_div": "BS", "account_nm": "자산총계", "thstrm_amount": "1,000,000"},
                {"sj_div": "BS", "account_nm": "부채총계", "thstrm_amount": "400,000"},
                {"sj_div": "IS", "account_nm": "매출액", "thstrm_amount": "500,000"},
                {"sj_div": "IS", "account_nm": "영업이익", "thstrm_amount": "50,000"},
                {"sj_div": "IS", "account_nm": "당기순이익", "thstrm_amount": "30,000"},
            ]
        }
        out = df._extract_pl_bs_from_dart(data)
        assert out["total_assets"] == 1_000_000
        assert out["total_liabilities"] == 400_000
        assert out["equity"] == 600_000
        assert out["revenue"] == 500_000
        assert out["operating_profit"] == 50_000
        assert out["net_income"] == 30_000

    def test_extract_cashflow_by_account_id(self):
        # 2025 사업보고서 라벨 변형('영업활동 현금흐름' 공백·'투자활동순현금흐름' 순)은 한글 텍스트-only
        # 매칭이 놓침 → account_id(IFRS)로 복구되어야 함 (SK하이닉스·삼성전기 실증).
        # 소분해 '영업활동에서 창출된 현금'(ifrs-full_...InOperations)은 영업활동 총계를 오염시키면 안 됨.
        data = {
            "list": [
                {"sj_div": "CF", "account_nm": "영업활동에서 창출된 현금", "account_id": "ifrs-full_CashFlowsFromUsedInOperations", "thstrm_amount": "9,999"},
                {"sj_div": "CF", "account_nm": "영업활동 현금흐름", "account_id": "ifrs-full_CashFlowsFromUsedInOperatingActivities", "thstrm_amount": "1,000"},
                {"sj_div": "CF", "account_nm": "투자활동순현금흐름", "account_id": "ifrs-full_CashFlowsFromUsedInInvestingActivities", "thstrm_amount": "-500"},
                {"sj_div": "CF", "account_nm": "재무활동 현금흐름", "account_id": "ifrs-full_CashFlowsFromUsedInFinancingActivities", "thstrm_amount": "-200"},
            ]
        }
        out = df._extract_pl_bs_from_dart(data)
        assert out["operating_cashflow"] == 1_000   # 공백 라벨 → account_id 로 복구, 소분해(9,999) 오염 없음
        assert out["investing_cashflow"] == -500    # '순' 라벨 → account_id 로 복구
        assert out["financing_cashflow"] == -200
        assert out["free_cashflow"] == 500          # 영업 + 투자

    def test_extract_income_tax_by_account_id(self):
        # '법인세비용(수익)'(삼성·SK) 라벨변형은 account_nm 정확일치를 빠져나감 → account_id 로 복구.
        data = {
            "list": [
                {"sj_div": "IS", "account_nm": "법인세비용(수익)", "account_id": "ifrs-full_IncomeTaxExpenseContinuingOperations", "thstrm_amount": "3,000"},
            ]
        }
        out = df._extract_pl_bs_from_dart(data)
        assert out["income_tax"] == 3_000

    def test_extract_revenue_by_account_id(self):
        # top-line account_nm='매출'(LG화학류)은 구 substring 매칭을 빠져나가 revenue=0 → account_id 로 복구.
        # '기타수익(매출액)'(OtherRevenue)은 revenue 로 안 잡혀야(구버그 차바이오텍 240B 오채택).
        data = {"list": [
            {"sj_div": "IS", "account_nm": "매출", "account_id": "ifrs-full_Revenue", "thstrm_amount": "48,916,104"},
            {"sj_div": "IS", "account_nm": "기타수익(매출액)", "account_id": "ifrs-full_OtherRevenue", "thstrm_amount": "240,173"},
        ]}
        out = df._extract_pl_bs_from_dart(data)
        assert out["revenue"] == 48_916_104

    def test_extract_operating_profit_by_account_id(self):
        # 라벨변형(공백)이라 정확일치 미스 → account_id 로 op 확보. 중단영업이익은 op 로 안 잡혀야.
        data = {"list": [
            {"sj_div": "IS", "account_nm": "영업이익 ", "account_id": "dart_OperatingIncomeLoss", "thstrm_amount": "2,163,234"},
            {"sj_div": "IS", "account_nm": "중단영업이익(손실)", "account_id": "ifrs-full_ProfitLossFromDiscontinuedOperations", "thstrm_amount": "-2,609"},
        ]}
        out = df._extract_pl_bs_from_dart(data)
        assert out["operating_profit"] == 2_163_234

    def test_extract_handles_missing(self):
        data = {"list": []}
        out = df._extract_pl_bs_from_dart(data)
        assert out["total_assets"] == 0
        assert out["equity"] == 0


class TestComputeRatios:
    def test_basic_ratios(self):
        pl_bs = {
            "total_assets": 1_000_000, "total_liabilities": 400_000, "equity": 600_000,
            "revenue": 500_000, "operating_profit": 50_000, "net_income": 30_000,
        }
        r = df._compute_ratios(pl_bs)
        assert r["debt_ratio"] == round(400_000 / 600_000 * 100, 2)
        assert r["roe"] == round(30_000 / 600_000 * 100, 2)
        assert r["op_margin"] == round(50_000 / 500_000 * 100, 2)

    def test_zero_equity_returns_none(self):
        pl_bs = {"total_assets": 100, "total_liabilities": 100, "equity": 0,
                 "revenue": 0, "operating_profit": 0, "net_income": 0}
        r = df._compute_ratios(pl_bs)
        assert r["debt_ratio"] is None
        assert r["roe"] is None

    def test_zero_revenue_no_op_margin(self):
        pl_bs = {"total_assets": 1_000, "total_liabilities": 500, "equity": 500,
                 "revenue": 0, "operating_profit": 100, "net_income": 50}
        r = df._compute_ratios(pl_bs)
        assert r["op_margin"] is None
        assert r["debt_ratio"] is not None  # equity > 0

    def test_magnitude_gate_impossible_ratios_dropped(self):
        # 산술/물리 불가능 = 파싱 오염 → None. gp>rev(gross_margin>100%)·cur_l≈0·eq≈0.
        r = df._compute_ratios({"equity": 1e11, "total_assets": 1e12, "net_income": 1e10,
                                "revenue": 240e9, "gross_profit": 363e9,   # gp>rev
                                "current_assets": 1e11, "current_liabilities": 1e6,  # 100000배
                                "operating_profit": 300e9, "total_liabilities": 29e9})
        assert r["gross_margin"] is None          # gp>rev 불가
        assert r["op_margin"] is None             # op>rev 불가
        assert r["current_ratio"] is None         # >100배 분모붕괴
        r2 = df._compute_ratios({"equity": 1, "total_assets": 1e12, "total_liabilities": 29e9,
                                 "net_income": 1e10, "revenue": 1e12, "operating_profit": 1e11})
        assert r2["debt_ratio"] is None           # 자본≈0 → >5000%

    def test_magnitude_gate_keeps_real_extremes(self):
        # roa 극단(일회성 처분이익)은 실제값 — 게이트 안 함(garbage 아님).
        r = df._compute_ratios({"equity": 365e9, "total_assets": 365e9, "net_income": 1799e9,
                                "revenue": 0, "operating_profit": 0})
        assert r["roa"] is not None and r["roa"] > 100


# ─────────────────────────────────────────────────────────────────────
# yfinance fallback
# ─────────────────────────────────────────────────────────────────────

class TestYfFallback:
    @patch("yfinance.Ticker")
    def test_yf_returns_full_fields(self, mock_yf):
        mock_t = MagicMock()
        mock_t.info = {
            "trailingPE": 12.5, "priceToBook": 1.2, "returnOnEquity": 0.15,
            "debtToEquity": 30.0, "operatingMargins": 0.20,
        }
        mock_yf.return_value = mock_t

        out = df._yf_fallback_for_ticker("005930")
        assert out["per"] == 12.5
        assert out["pbr"] == 1.2
        assert out["roe"] == 15.0  # 0.15 * 100
        assert out["op_margin"] == 20.0

    @patch("yfinance.Ticker")
    def test_yf_empty_info_returns_nones(self, mock_yf):
        mock_t = MagicMock()
        mock_t.info = {}
        mock_yf.return_value = mock_t
        out = df._yf_fallback_for_ticker("999999")
        # 두 suffix 모두 시도하지만 모두 빈 info → 결과 모두 None
        assert all(v is None for v in out.values())


# ─────────────────────────────────────────────────────────────────────
# Single ticker fetch (DART + yfinance 결합)
# ─────────────────────────────────────────────────────────────────────

class TestFetchOneFundamentals:
    @patch("api.collectors.dart_fundamentals._yf_fallback_for_ticker")
    @patch("api.collectors.dart_fundamentals._get_fnltt_all_data")
    @patch("api.collectors.dart_corp_code.get_corp_code")
    def test_dart_success_yf_complement(self, mock_corp, mock_dart, mock_yf):
        # 2026-05-20 fs_div 감사 리팩터: 코드가 DartScout._get_fnltt_data →
        # dart_fundamentals._get_fnltt_all_data (fnlttSinglAcntAll, status=000 체크) 로 변경.
        # 테스트도 신 함수 patch + status=000 응답으로 정합.
        mock_corp.return_value = "00126380"
        mock_dart.return_value = {
            "status": "000",
            "list": [
                {"sj_div": "BS", "account_nm": "자산총계", "thstrm_amount": "1000000"},
                {"sj_div": "BS", "account_nm": "부채총계", "thstrm_amount": "400000"},
                {"sj_div": "IS", "account_nm": "매출액", "thstrm_amount": "500000"},
                {"sj_div": "IS", "account_nm": "영업이익", "thstrm_amount": "50000"},
                {"sj_div": "IS", "account_nm": "당기순이익", "thstrm_amount": "30000"},
            ]
        }
        mock_yf.return_value = {"per": 12.5, "pbr": 1.2, "roe": None, "debt_ratio": None, "op_margin": None}

        out = df._fetch_one_dart_fundamentals("005930", "2024")
        assert out["debt_ratio"] is not None  # DART
        assert out["op_margin"] is not None  # DART
        assert out["per"] == 12.5  # yfinance complement
        assert out["pbr"] == 1.2
        assert out["source"] in ("DART+yfinance",)

    @patch("api.collectors.dart_fundamentals._yf_fallback_for_ticker")
    @patch("api.collectors.dart_corp_code.get_corp_code")
    def test_no_corp_code_yf_fallback(self, mock_corp, mock_yf):
        mock_corp.return_value = None
        mock_yf.return_value = {"per": 10.0, "pbr": 1.0, "roe": 12.0, "debt_ratio": 25.0, "op_margin": 18.0}
        out = df._fetch_one_dart_fundamentals("999999", "2024")
        assert out["per"] == 10.0
        assert out["source"] == "yfinance_fallback"

    @patch("api.collectors.dart_fundamentals._yf_fallback_for_ticker")
    @patch("api.collectors.dart_corp_code.get_corp_code")
    def test_complete_failure_returns_nones(self, mock_corp, mock_yf):
        mock_corp.return_value = None
        mock_yf.return_value = {"per": None, "pbr": None, "roe": None, "debt_ratio": None, "op_margin": None}
        out = df._fetch_one_dart_fundamentals("999999", "2024")
        assert out["source"] == "none"
        assert out["per"] is None


# ─────────────────────────────────────────────────────────────────────
# Batch
# ─────────────────────────────────────────────────────────────────────

class TestBatch:
    def test_empty_returns_empty(self):
        assert df.fetch_dart_fundamentals_batch([]) == {}

    @patch("api.collectors.dart_fundamentals._fetch_one_dart_fundamentals")
    def test_batch_calls_each_ticker(self, mock_one):
        mock_one.side_effect = lambda t, y, reprt="11011": {
            "per": 10.0, "pbr": 1.0, "roe": 12.0,
            "debt_ratio": 25.0, "op_margin": 18.0,
            "report_date": y, "source": "DART+yfinance",
        }
        out = df.fetch_dart_fundamentals_batch(["005930", "000660", "035420"])
        assert len(out) == 3
        assert all(out[t]["source"] == "DART+yfinance" for t in out)
        assert mock_one.call_count == 3

    @patch("api.collectors.dart_fundamentals._fetch_one_dart_fundamentals")
    def test_batch_handles_exception_gracefully(self, mock_one):
        def raise_for_one(t, y, reprt="11011"):
            if t == "999999":
                raise RuntimeError("DART API down")
            return {"per": 10.0, "pbr": 1.0, "roe": None, "debt_ratio": None,
                    "op_margin": None, "report_date": y, "source": "yfinance_fallback"}
        mock_one.side_effect = raise_for_one
        out = df.fetch_dart_fundamentals_batch(["005930", "999999"])
        assert len(out) == 2
        assert out["999999"]["source"] == "error"
        assert out["005930"]["source"] == "yfinance_fallback"


class TestParseInt:
    def test_handles_commas(self):
        assert df._parse_int("1,000,000") == 1_000_000

    def test_handles_none(self):
        assert df._parse_int(None) == 0

    def test_handles_empty_and_dash(self):
        assert df._parse_int("") == 0
        assert df._parse_int("-") == 0
