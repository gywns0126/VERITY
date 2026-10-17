"""dart_fundamentals 단위 테스트 (Phase 2-A) — DART/yfinance mock."""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from api.collectors import dart_fundamentals as df


# ─────────────────────────────────────────────────────────────────────
# DART 데이터 추출
# ─────────────────────────────────────────────────────────────────────

class TestExtractPLBS:
    _request = {"ticker": "084010", "corp_code": "00123456",
                "bsns_year": "2025", "reprt_code": "11011", "fs_div": "CFS"}

    @staticmethod
    def _sga_row(name, amount, **changes):
        row = {
            "sj_div": "IS", "account_nm": name, "thstrm_amount": amount,
            "corp_code": "00123456", "bsns_year": "2025",
            "rcept_no": "20260318000780", "reprt_code": "11011",
            "thstrm_nm": "제 25 기", "currency": "KRW",
        }
        row.update(changes)
        return row

    def test_split_sga_sums_same_filing_rows_and_preserves_inputs(self):
        selling = self._sga_row("판매비 (주23,24)", "22,821,576,676")
        administrative = self._sga_row("관리비 (주23,24)", "50,293,694,325")
        sources = {}
        out = df._extract_pl_bs_from_dart(
            {"list": [selling, administrative]}, source_rows=sources, request_context=self._request)
        assert out["sga"] == 73_115_271_001
        assert sources["sga"] == [
            {**selling, "request_context": self._request},
            {**administrative, "request_context": self._request},
        ]
        assert sources["sga"][0] is not selling
        assert "stock_code" not in sources["sga"][0]
        assert "fs_div" not in sources["sga"][0]
        assert "thstrm_dt" not in sources["sga"][0]

    def test_reported_sga_total_precedes_split_in_any_order(self):
        selling = self._sga_row("판매비", "22,821,576,676")
        administrative = self._sga_row("관리비", "50,293,694,325")
        total = self._sga_row("판매비와관리비", "70,000,000,000")
        for rows in ([total, selling, administrative], [selling, administrative, total]):
            sources = {}
            out = df._extract_pl_bs_from_dart(
                {"list": rows}, source_rows=sources, request_context=self._request)
            assert out["sga"] == 70_000_000_000
            assert sources["sga"] == {**total, "request_context": self._request}

    @pytest.mark.parametrize("name", ["판매비와 관리비", "판매비 와 관리비", "판매비와\u00a0관리비",
                                      " 판매비와 관리비 (주 23,24) "])
    def test_sga_total_whitespace_variant_keeps_original_source(self, name):
        # Annual 460860 primary table label/value; API identity is a synthetic
        # unit fixture, not a claim that the historical raw response was saved.
        total = self._sga_row(name, "214,066,943,596")
        parts = [self._sga_row("판매비", "1"), self._sga_row("관리비", "2")]
        sources = {}
        result = df._extract_pl_bs_from_dart({"list": parts + [total]},
            source_rows=sources, request_context=self._request)
        assert result["sga"] == 214_066_943_596
        assert sources["sga"] == {**total, "request_context": self._request}
        assert total["account_nm"] == name

    def test_split_sga_requires_both_unique_rows_and_same_identity(self):
        selling = self._sga_row("판매비", "22,821,576,676")
        administrative = self._sga_row("관리비", "50,293,694,325")
        for rows in (
            [selling],
            [selling, administrative, administrative],
            [selling, self._sga_row("관리비", "50,293,694,325", bsns_year="2024")],
            [selling, self._sga_row("관리비", "50,293,694,325", reprt_code="11012")],
            [selling, self._sga_row("관리비", "50,293,694,325", thstrm_nm="제 24 기")],
            [selling, self._sga_row("관리비", "50,293,694,325", rcept_no="20260318000781")],
            [selling, self._sga_row("관리비", "50,293,694,325", currency="USD")],
            [self._sga_row("판매비", "22,821,576,676", currency="USD"),
             self._sga_row("관리비", "50,293,694,325", currency="USD")],
            [selling, self._sga_row("관리비", "50,293,694,325", fs_div="OFS")],
            [selling, self._sga_row("관리비", "50,293,694,325", stock_code="000001")],
            [self._sga_row("판매비", "22,821,576,676", thstrm_dt="2025.01.01 ~ 2025.12.31"), administrative],
            [self._sga_row("판매비", "22,821,576,676", thstrm_dt="2025.01.01 ~ 2025.12.31"),
             self._sga_row("관리비", "50,293,694,325", thstrm_dt="2024.01.01 ~ 2024.12.31")],
            [self._sga_row("판매비", "22,821,576,676", thstrm_dt="2025.99.01 ~ 2025.12.31"),
             self._sga_row("관리비", "50,293,694,325", thstrm_dt="2025.99.01 ~ 2025.12.31")],
            [selling, self._sga_row("관리비", "50,293,694,325", rcept_no=None)],
            [selling, self._sga_row("관리비", "-")],
        ):
            sources = {}
            out = df._extract_pl_bs_from_dart(
                {"list": rows}, source_rows=sources, request_context=self._request)
            assert out["sga"] == 0
            assert "sga" not in sources

    def test_split_sga_requires_matching_request_context(self):
        rows = [self._sga_row("판매비", "1"), self._sga_row("관리비", "2")]
        for context in (None, {**self._request, "corp_code": "87654321"},
                        {**self._request, "bsns_year": "2024"},
                        {**self._request, "reprt_code": "11012"}):
            sources = {}
            out = df._extract_pl_bs_from_dart(
                {"list": rows}, source_rows=sources, request_context=context)
            assert out["sga"] == 0
            assert "sga" not in sources

    def test_split_sga_accepts_raw_zero_without_treating_it_as_missing(self):
        selling = self._sga_row("판매비", 0)
        administrative = self._sga_row("관리비", "50,293,694,325")
        sources = {}
        out = df._extract_pl_bs_from_dart(
            {"list": [selling, administrative]}, source_rows=sources, request_context=self._request)
        assert out["sga"] == 50_293_694_325
        assert [row["thstrm_amount"] for row in sources["sga"]] == [0, "50,293,694,325"]

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

    @pytest.mark.parametrize("amount", ["0", "99379167000"])
    @pytest.mark.parametrize("reverse", [False, True])
    def test_ifrs_operating_total_outranks_exact_label_fallback(self, amount, reverse):
        total = {"sj_div": "CIS", "account_nm": "III. 영업이익(손실)",
                 "account_id": "ifrs-full_ProfitLossFromOperatingActivities", "thstrm_amount": amount}
        fallback = {"sj_div": "IS", "account_nm": "영업이익",
                    "account_id": "issuer_CustomOperatingIncome", "thstrm_amount": "999"}
        rows = [total, fallback]
        if reverse:
            rows.reverse()
        sources = {}
        out = df._extract_pl_bs_from_dart({"list": rows}, source_rows=sources)
        assert out["operating_profit"] == int(amount)
        assert sources["operating_profit"] == total
        assert "_conflicts" not in sources

    @pytest.mark.parametrize("reverse", [False, True])
    def test_ifrs_and_dart_operating_totals_conflict_at_same_tier(self, reverse):
        totals = [
            {"sj_div": "CIS", "account_nm": "III. 영업이익(손실)",
             "account_id": "ifrs-full_ProfitLossFromOperatingActivities", "thstrm_amount": "0"},
            {"sj_div": "IS", "account_nm": "영업이익",
             "account_id": "dart_OperatingIncomeLoss", "thstrm_amount": "200"},
        ]
        fallback = {"sj_div": "IS", "account_nm": "영업이익", "thstrm_amount": "100"}
        rows = totals + [fallback]
        if reverse:
            rows.reverse()
        sources = {}
        out = df._extract_pl_bs_from_dart({"list": rows}, source_rows=sources)
        assert out["operating_profit"] is None
        assert "operating_profit" not in sources
        assert sources["_conflicts"]["operating_profit"] == [r for r in rows if r in totals]

    @pytest.mark.parametrize("reverse", [False, True])
    def test_equal_ifrs_and_dart_operating_totals_keep_source(self, reverse):
        rows = [
            {"sj_div": "CIS", "account_nm": "III. 영업이익(손실)",
             "account_id": "ifrs-full_ProfitLossFromOperatingActivities", "thstrm_amount": "200"},
            {"sj_div": "IS", "account_nm": "영업이익",
             "account_id": "dart_OperatingIncomeLoss", "thstrm_amount": "200"},
        ]
        if reverse:
            rows.reverse()
        sources = {}
        out = df._extract_pl_bs_from_dart({"list": rows}, source_rows=sources)
        assert out["operating_profit"] == 200
        assert sources["operating_profit"] == rows[0]
        assert "_conflicts" not in sources

    @pytest.mark.parametrize("aid", [
        "ifrs-full_ProfitLossFromOperatingActivitiesOther",
        "ifrs-full_ProfitLossFromOperatingActivitiesContinuingOperations",
        "ifrs_ProfitLossFromOperatingActivities",
        "ifrs-full_ProfitLossFromDiscontinuedOperations",
    ])
    def test_similar_ifrs_operating_ids_are_not_totals(self, aid):
        row = {"sj_div": "CIS", "account_nm": "영업이익", "account_id": aid,
               "thstrm_amount": "999"}
        sources = {}
        out = df._extract_pl_bs_from_dart({"list": [row]}, source_rows=sources)
        assert out["operating_profit"] == 0
        assert "operating_profit" not in sources

    def test_extract_handles_missing(self):
        data = {"list": []}
        out = df._extract_pl_bs_from_dart(data)
        assert out["total_assets"] == 0
        assert out["equity"] == 0

    @pytest.mark.parametrize("aid", ["ifrs-full_ProfitLoss", "ifrs_ProfitLoss"])
    @pytest.mark.parametrize("amount", ["0", "-500", "500"])
    @pytest.mark.parametrize("reverse", [False, True])
    def test_total_net_priority_preserves_zero_sign_and_source(self, aid, amount, reverse):
        total = {"sj_div": "CIS", "account_nm": "분기순손익", "account_id": aid,
                 "thstrm_amount": amount}
        owner = {"sj_div": "IS", "account_nm": "지배기업 소유주에게 귀속되는 당기순이익",
                 "account_id": "ifrs-full_ProfitLossAttributableToOwnersOfParent", "thstrm_amount": "999"}
        other = {"sj_div": "CIS", "account_nm": "당기순이익으로 재분류되지 않는 항목",
                 "thstrm_amount": "777"}
        fallback = {"sj_div": "IS", "account_nm": "당기순이익", "thstrm_amount": "123"}
        rows = [fallback, owner, other, total]
        if reverse:
            rows.reverse()
        sources = {}
        result = df._extract_pl_bs_from_dart({"list": rows}, source_rows=sources)
        assert result["net_income"] == int(amount)
        assert sources["net_income"] == total

    @pytest.mark.parametrize("reverse", [False, True])
    def test_conflicting_standardized_net_totals_are_unknown_and_flagged(self, reverse):
        rows = [{"sj_div": sj, "account_nm": "당기순이익", "account_id": aid,
                 "thstrm_amount": value} for sj, aid, value in (
                     ("IS", "ifrs-full_ProfitLoss", "100"),
                     ("CIS", "ifrs_ProfitLoss", "200"))]
        if reverse:
            rows.reverse()
        sources = {}
        result = df._extract_pl_bs_from_dart({"list": rows}, source_rows=sources)
        assert result["net_income"] is None
        assert "net_income" not in sources
        assert sources["_conflicts"]["net_income"] == rows
        assert df._extract_pl_bs_from_dart({"list": rows})["net_income"] is None

    def test_duplicate_equal_standardized_totals_do_not_create_conflict(self):
        row = {"sj_div": "IS", "account_nm": "당기순이익", "account_id": "ifrs-full_ProfitLoss",
               "thstrm_amount": "-100"}
        sources = {}
        assert df._extract_pl_bs_from_dart({"list": [row, dict(row)]}, source_rows=sources)["net_income"] == -100
        assert "_conflicts" not in sources

    @pytest.mark.parametrize("name,aid", [
        ("당기순이익으로 재분류되는 항목", ""),
        ("당기순이익으로 재분류되지 않는 항목", ""),
        ("비지배주주에게 귀속되는 당기순이익", ""),
        ("기본주당기순이익", ""),
        ("당기순이익", "ifrs-full_BasicEarningsLossPerShare"),
        ("당기순이익", "ifrs-full_ProfitLossAttributableToOwnersOfParent"),
        ("당기순이익", "ifrs-full_ProfitLossFromContinuingOperations"),
    ])
    def test_related_income_concepts_are_not_total_net_fallback(self, name, aid):
        sources = {}
        result = df._extract_pl_bs_from_dart({"list": [{
            "sj_div": "IS", "account_nm": name, "account_id": aid,
            "thstrm_amount": "199032927011"}]}, source_rows=sources)
        assert result["net_income"] == 0  # Existing missing-value contract.
        assert "net_income" not in sources

    @pytest.mark.parametrize("name", ["당기순이익", "당기순이익(손실)", "당기순손실",
                                      "분기순이익", "반기순손익", "연결 당기순이익 (주 3,4)"])
    def test_exact_net_label_fallback_and_source_still_work(self, name):
        row = {"sj_div": "IS", "account_nm": name, "thstrm_amount": "-100"}
        sources = {}
        assert df._extract_pl_bs_from_dart({"list": [row]}, source_rows=sources)["net_income"] == -100
        assert sources["net_income"] == row

    @pytest.mark.parametrize("amount", ["0", "-500", "500"])
    @pytest.mark.parametrize("reverse", [False, True])
    def test_canonical_op_outranks_custom_exact_fallback(self, amount, reverse):
        canonical = {"sj_div": "CIS", "account_nm": "Ⅴ.영업이익",
                     "account_id": "dart_OperatingIncomeLoss", "thstrm_amount": amount}
        fallback = {"sj_div": "IS", "account_nm": "영업이익",
                    "account_id": "issuer_CustomOperatingIncome", "thstrm_amount": "999"}
        rows = [canonical, fallback]
        if reverse:
            rows.reverse()
        sources = {}
        out = df._extract_pl_bs_from_dart({"list": rows}, source_rows=sources)
        assert out["operating_profit"] == int(amount)
        assert sources["operating_profit"] == canonical
        assert "_conflicts" not in sources

    @pytest.mark.parametrize("reverse", [False, True])
    def test_conflicting_canonical_op_cannot_be_rescued_by_fallback(self, reverse):
        totals = [{"sj_div": sj, "account_nm": "영업이익",
                   "account_id": "dart_OperatingIncomeLoss", "thstrm_amount": amount}
                  for sj, amount in [("IS", "0"), ("CIS", "200")]]
        fallback = {"sj_div": "IS", "account_nm": "영업이익", "thstrm_amount": "100"}
        rows = totals + [fallback]
        if reverse:
            rows.reverse()
        sources = {}
        out = df._extract_pl_bs_from_dart({"list": rows}, source_rows=sources)
        assert out["operating_profit"] is None
        assert "operating_profit" not in sources
        assert sources["_conflicts"]["operating_profit"] == [r for r in rows if r in totals]
        assert df._extract_pl_bs_from_dart({"list": rows})["operating_profit"] is None

    @pytest.mark.parametrize("field,labels,aid", [
        ("net_income", ("당기순이익", "당기순이익(손실)"), "ifrs-full_ProfitLoss"),
        ("operating_profit", ("영업이익", "영업이익(손실)"), "dart_OperatingIncomeLoss"),
    ])
    @pytest.mark.parametrize("canonical", [False, True])
    @pytest.mark.parametrize("reverse", [False, True])
    def test_conflicting_exact_fallbacks_only_matter_without_canonical(
            self, field, labels, aid, canonical, reverse):
        rows = [{"sj_div": "IS", "account_nm": name, "thstrm_amount": amount}
                for name, amount in zip(labels, ("100", "200"))]
        total = {"sj_div": "CIS", "account_nm": labels[0],
                 "account_id": aid, "thstrm_amount": "0"}
        if canonical:
            rows.append(total)
        if reverse:
            rows.reverse()
        sources = {}
        out = df._extract_pl_bs_from_dart({"list": rows}, source_rows=sources)
        if canonical:
            assert out[field] == 0 and sources[field] == total
            assert "_conflicts" not in sources
        else:
            assert out[field] is None and field not in sources
            assert sources["_conflicts"][field] == rows

    @pytest.mark.parametrize("field,aid,label", [
        ("operating_profit", "dart_OperatingIncomeLoss", "영업이익"),
        ("net_income", "", "당기순이익"),
    ])
    def test_equal_duplicate_income_candidates_keep_zero_and_source(self, field, aid, label):
        row = {"sj_div": "IS", "account_nm": label, "account_id": aid, "thstrm_amount": "0"}
        sources = {}
        out = df._extract_pl_bs_from_dart({"list": [row, dict(row)]}, source_rows=sources)
        assert out[field] == 0 and sources[field] == row
        assert "_conflicts" not in sources

    @pytest.mark.parametrize("field,label", [
        ("revenue", "Ⅰ.매출액"), ("revenue", "I. 영업수익 (주 3,4)"),
        ("operating_profit", "Ⅴ.영업이익"), ("operating_profit", "V.영업이익(손실)"),
        ("net_income", "IX.당기순이익(손실)"), ("net_income", "Ⅸ．반기순손익"),
    ])
    def test_idless_roman_exact_totals_preserve_original_rows(self, field, label):
        row = {"sj_div": "CIS", "account_nm": label, "thstrm_amount": "-100"}
        sources = {}
        assert df._extract_pl_bs_from_dart({"list": [row]}, source_rows=sources)[field] == -100
        assert sources[field] == row and row["account_nm"] == label

    @pytest.mark.parametrize("field,label,aid", [
        ("revenue", "기타Ⅰ.매출액", ""), ("revenue", "Ⅰ.매출액", "issuer_Custom"),
        ("operating_profit", "Ⅴ.중단영업이익(손실)", ""),
        ("operating_profit", "Ⅴ.계속영업이익(손실)", ""),
        ("operating_profit", "Ⅴ.주당영업이익", ""),
        ("operating_profit", "영업이익", "ifrs-full_ProfitLossFromDiscontinuedOperations"),
        ("net_income", "IX.지배기업소유주귀속당기순이익", ""),
        ("net_income", "IX.비지배지분당기순이익", ""),
        ("net_income", "IX.계속영업당기순이익", ""),
        ("net_income", "IX.중단영업당기순이익", ""),
        ("net_income", "IX.기본주당순이익", ""),
        ("net_income", "IX.당기순이익재분류항목", ""),
    ])
    def test_total_normalization_never_removes_semantic_qualifiers(self, field, label, aid):
        row = {"sj_div": "CIS", "account_nm": label, "account_id": aid, "thstrm_amount": "999"}
        sources = {}
        assert df._extract_pl_bs_from_dart({"list": [row]}, source_rows=sources)[field] == 0
        assert field not in sources

    @pytest.mark.parametrize("reverse", [False, True])
    @pytest.mark.parametrize("amount", ["0", "48,183,071,752"])
    def test_verified_combined_sga_alias_precedes_split_without_merging_bad_debt(self, reverse, amount):
        # Verified HTML label/value, synthetic API fixture; not historical execution evidence.
        total = self._sga_row("판매 및 일반관리비 (주 3,4)", amount)
        rows = [total, self._sga_row("판매비", "1"), self._sga_row("관리비", "2"),
                self._sga_row("대손상각비", "2,072,674,155")]
        if reverse:
            rows.reverse()
        sources = {}
        out = df._extract_pl_bs_from_dart({"list": rows}, source_rows=sources, request_context=self._request)
        assert out["sga"] == int(amount.replace(",", ""))
        assert sources["sga"] == {**total, "request_context": self._request}

    @pytest.mark.parametrize("name", ["기타판매비와관리비", "판매비와관리비중감가상각비",
                                      "판매및일반관리비율", "중단영업판매및일반관리비"])
    def test_combined_sga_aliases_are_exact_not_substrings(self, name):
        sources = {}
        out = df._extract_pl_bs_from_dart({"list": [self._sga_row(name, "999")]}, source_rows=sources)
        assert out["sga"] == 0 and "sga" not in sources


class TestComputeRatios:
    def test_conflicting_operating_profit_keeps_margin_unknown(self):
        ratios = df._compute_ratios({"revenue": 1000, "operating_profit": None, "gross_profit": 300})
        assert ratios["op_margin"] is None
        assert ratios["gross_margin"] == 30

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
    def test_yuanta_2025_cfs_ifrs_operating_total_reaches_source_evidence(
            self, mock_corp, mock_dart, mock_yf):
        # Compact rows from the saved 2025 CFS API response, not a live request.
        common = {"rcept_no": "20260312000253", "reprt_code": "11011",
                  "bsns_year": "2025", "corp_code": "00117601", "currency": "KRW"}
        mock_corp.return_value = "00117601"
        mock_dart.return_value = {"status": "000", "list": [
            {**common, "sj_div": "BS", "account_nm": "자산총계",
             "account_id": "ifrs-full_Assets", "thstrm_amount": "20030123636000"},
            {**common, "sj_div": "CIS", "account_nm": "I. 영업수익",
             "account_id": "ifrs-full_Revenue", "thstrm_amount": "3461272611000"},
            {**common, "sj_div": "CIS", "account_nm": "III. 영업이익(손실)",
             "account_id": "ifrs-full_ProfitLossFromOperatingActivities",
             "thstrm_amount": "99379167000"},
            {**common, "sj_div": "CIS", "account_nm": "VIII. 당기순이익(손실)",
             "account_id": "ifrs-full_ProfitLoss", "thstrm_amount": "95631538000"},
        ]}
        mock_yf.return_value = {"per": None, "pbr": None, "roe": None,
                                "debt_ratio": None, "op_margin": None}

        out = df._fetch_one_dart_fundamentals("003470", "2025")
        assert (out["source"], out["fs_div"], out["report_date"]) == ("DART", "CFS", "2025")
        assert (out["revenue"], out["operating_profit"], out["net_income"]) == (
            3461272611000, 99379167000, 95631538000)
        assert out["op_margin"] == round(99379167000 / 3461272611000 * 100, 2)
        evidence = out["_source_evidence"]["operating_profit"]
        assert evidence["value"] == 99379167000
        assert evidence["inputs"][0]["concept"] == "ifrs-full_ProfitLossFromOperatingActivities"
        assert evidence["inputs"][0]["document_id"] == "20260312000253"
        assert evidence["inputs"][0]["raw_value"] == "99379167000"
        assert out["_source_evidence"]["op_margin"]["inputs"][0] == evidence["inputs"][0]
        mock_dart.assert_called_once_with("00117601", "2025", fs_div="CFS", reprt_code="11011")

    @patch("api.collectors.dart_fundamentals._yf_fallback_for_ticker")
    @patch("api.collectors.dart_fundamentals._get_fnltt_all_data")
    @patch("api.collectors.dart_corp_code.get_corp_code")
    def test_conflicting_op_stays_unknown_without_discarding_dart_record(self, mock_corp, mock_dart, mock_yf):
        mock_corp.return_value = "00123456"
        mock_dart.return_value = {"status": "000", "list": [
            {"sj_div": "BS", "account_nm": "자산총계", "thstrm_amount": "1000"},
            {"sj_div": "IS", "account_nm": "매출액", "thstrm_amount": "500"},
            *[{"sj_div": sj, "account_nm": "영업이익", "account_id": "dart_OperatingIncomeLoss",
               "thstrm_amount": amount} for sj, amount in [("IS", "100"), ("CIS", "200")]],
        ]}
        mock_yf.return_value = {"per": 12.5, "pbr": 1.2, "roe": 15.0,
                                "debt_ratio": 30.0, "op_margin": 20.0}
        out = df._fetch_one_dart_fundamentals("084010", "2025")
        assert out["source"] == "DART+yfinance" and out["revenue"] == 500
        assert out["operating_profit"] is None and out["op_margin"] is None
        assert (out["per"], out["pbr"]) == (12.5, 1.2)
        assert out["_source_evidence"]["operating_profit"]["inputs"] == [None]

    @patch("api.collectors.dart_fundamentals._yf_fallback_for_ticker")
    @patch("api.collectors.dart_fundamentals._get_fnltt_all_data")
    @patch("api.collectors.dart_corp_code.get_corp_code")
    def test_canonical_net_and_op_conflicts_block_yf_ratios(
            self, mock_corp, mock_dart, mock_yf):
        mock_corp.return_value = "00123456"
        row = TestExtractPLBS._sga_row
        mock_dart.return_value = {"status": "000", "list": [
            row("자산총계", "1,000,000,000,000", sj_div="BS"),
            row("매출액", "500,000,000,000"),
            row("영업이익", "100", account_id="dart_OperatingIncomeLoss"),
            row("영업이익", "200", sj_div="CIS", account_id="dart_OperatingIncomeLoss"),
            row("당기순이익", "300", account_id="ifrs-full_ProfitLoss"),
            row("당기순이익", "400", sj_div="CIS", account_id="ifrs_ProfitLoss"),
            row("법인세차감전순이익", "500"),
            row("영업활동현금흐름", "600", sj_div="CF"),
        ]}
        mock_yf.return_value = {"per": 12.5, "pbr": 1.2, "roe": 15.0,
                                "debt_ratio": 30.0, "op_margin": 20.0}

        out = df._fetch_one_dart_fundamentals("084010", "2025")
        assert out["source"] == "DART+yfinance"
        assert (out["operating_profit"], out["net_income"]) == (None, None)
        assert (out["op_margin"], out["roe"], out["roa"]) == (None, None, None)
        assert (out["per"], out["pbr"]) == (12.5, 1.2)
        assert out["_source_evidence"]["roe"]["value"] is None
        assert out["_source_evidence"]["op_margin"]["value"] is None

    @patch("api.collectors.dart_fundamentals._yf_fallback_for_ticker")
    @patch("api.collectors.dart_fundamentals._get_fnltt_all_data")
    @patch("api.collectors.dart_corp_code.get_corp_code")
    def test_split_sga_real_api_shape_reaches_fetch_evidence(self, mock_corp, mock_dart, mock_yf):
        mock_corp.return_value = "00123456"
        row = TestExtractPLBS._sga_row
        mock_dart.return_value = {"status": "000", "list": [
            row("자산총계", "100,000,000,000", sj_div="BS"),
            row("판매비", "22,821,576,676"),
            row("관리비", "50,293,694,325"),
        ]}
        mock_yf.return_value = {"per": None, "pbr": None, "roe": None,
                                "debt_ratio": None, "op_margin": None}

        out = df._fetch_one_dart_fundamentals("084010", "2025")
        assert out["sga"] == 73_115_271_001
        assert out["fs_div"] == "CFS"
        mock_dart.assert_called_once_with("00123456", "2025", fs_div="CFS", reprt_code="11011")
        evidence = out["_source_evidence"]["sga"]
        assert evidence["value"] == out["sga"]
        assert evidence["definition"] == "selling_plus_administrative_expense"
        assert [item["raw_value"] for item in evidence["inputs"]] == [
            "22,821,576,676", "50,293,694,325"]
        assert [item["concept"] for item in evidence["inputs"]] == ["판매비", "관리비"]
        for item in evidence["inputs"]:
            assert item["request_context"] == TestExtractPLBS._request
            assert item["ticker"] is None and item["fs_div"] is None
            assert item["start"] is None and item["end"] is None

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
