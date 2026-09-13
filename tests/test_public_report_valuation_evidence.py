"""KR report evidence regression: isolated fixtures, no production IO or collectors.

Run with unittest to avoid unrelated repository-wide pytest import fixtures.
"""
import copy
import io
import json
import os
import tempfile
import types
import unittest
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from unittest.mock import patch

from api.builders import stock_report_public_builder as builder


class PublicValuationEvidenceTests(unittest.TestCase):
    def build_fixture(self):
        """Execute the actual main attachment path with explicitly isolated inputs/outputs."""
        fixtures = {
            "recommendations.json": [{"ticker": "000660", "name": "Rich fixture", "market": "KOSPI",
                "market_cap": 1272.8e12, "per": 99, "eps": 123, "company_tagline": "Preserve business"}],
            "dart_fundamentals_kr.json": {"fundamentals": {"000660": {
                "net_income": 42.9e12, "report_date": "2025", "reprt_code": "11011", "fs_div": "CFS"}}},
            "krx_mktcap.json": {"_meta": {"bas_dd": "20260911", "generated_at": "2099-01-01"}, "map": {
                "000660": {"mktcap": 1323.7e12}, "466410": {"mktcap": 428e8},
                "000010": {"mktcap": 100e8}}},
        }
        modules = {
            "api.builders.cross_sector_peer": types.SimpleNamespace(GICS_KO={},
                compute_gics_medians=lambda rows: {}, kr_ksic_gics=lambda value: None,
                normalize_gics=lambda value: None, write_medians=lambda *args: 0),
            "api.collectors.ftc_group_equity": types.SimpleNamespace(lookup_official_shareholders=lambda code: None),
            "api.collectors.dart_corp_code": types.SimpleNamespace(get_corp_code=lambda ticker: None),
            "api.collectors.dividend_ksd": types.SimpleNamespace(load_dividends_ledger_for_report=lambda: {}),
            "api.analyzers.dart_business_overview": types.SimpleNamespace(_cut_at_sentence=lambda text, limit: (text, False)),
        }
        with tempfile.TemporaryDirectory(prefix="report-evidence-test-") as directory, ExitStack() as stack:
            stack.enter_context(patch.dict("sys.modules", modules))
            stack.enter_context(patch.object(builder, "_ROOT", directory))
            for name in ["OUTPUT_PATH", "BIZ_OVERVIEW_PATH", "BIZ_OVERVIEW_PUBLIC_PATH"]:
                stack.enter_context(patch.object(builder, name, os.path.join(directory, name + ".json")))
            stack.enter_context(patch.object(builder, "_load_json",
                side_effect=lambda name, default: copy.deepcopy(fixtures.get(os.path.basename(name), default))))
            stack.enter_context(patch.object(builder, "_load_catalyst_by_ticker", return_value={}))
            stack.enter_context(patch.object(builder, "_load_real_estate_history", return_value={}))
            stack.enter_context(patch.object(builder, "_load_fin_series", return_value={"000010": [
                {"year": 2024, "net": 10e8}, {"year": 2025, "net": 20e8}]}))
            stack.enter_context(patch.object(builder, "_load_panel_facts", return_value={"466410": {
                "net_income_ttm": 59.4e8, "quarter_end": "2026-06-30", "equity": 700e8}}))
            stack.enter_context(patch.object(builder, "_save_person_link_cache"))
            no_network = stack.enter_context(patch.object(builder, "_naver_news_total", side_effect=AssertionError("No network")))
            real_open = open

            def isolated_open(file, *args, **kwargs):
                target = os.path.abspath(os.fspath(file))
                if os.path.commonpath([target, directory]) != directory:
                    raise AssertionError(f"Non-fixture IO: {target}")
                return real_open(file, *args, **kwargs)

            stack.enter_context(patch("builtins.open", side_effect=isolated_open))
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(builder.main(), 0)
            no_network.assert_not_called()
            with open(builder.OUTPUT_PATH, encoding="utf-8") as source:
                result = json.load(source)
            return {s["ticker"]: s for s in result["stocks"]}

    def test_main_aligns_header_and_fact_to_actual_valuation_cap(self):
        row = self.build_fixture()["000660"]
        self.assertEqual(row["facts"]["시가총액"], "1323.7조")
        self.assertEqual(row["header"]["market_cap"], "1323.7조")
        self.assertEqual(row["facts"]["PER"], "30.9")
        self.assertEqual(row["facts"]["EPS"], "123원")
        self.assertEqual(row["business"], "Preserve business")

    def test_main_publishes_ttm_input_and_financial_period(self):
        row = self.build_fixture()["466410"]
        self.assertEqual(row["facts"]["PER"], "7.2")
        self.assertIn("순이익 59억", row["facts_calc"]["PER"])
        self.assertIn("최근 12개월(TTM)", row["facts_calc"]["PER"])
        self.assertIn("2026-06-30", row["facts_calc"]["PER"])
        self.assertNotIn("None", json.dumps(row))

    def test_main_uses_market_basis_not_generation_time(self):
        for row in self.build_fixture().values():
            self.assertIn("2026-09-11", row["facts_calc"]["PER"])
            self.assertIn("2026-09-11", row["facts_note"]["시가총액"])
            self.assertNotIn("2099", row["facts_calc"]["PER"])

    def test_main_preserves_annual_fallback_period_and_badge(self):
        row = self.build_fixture()["000010"]
        self.assertIn("2025년 연간", row["facts_calc"]["PER"])
        self.assertEqual(row["facts_note"]["PER"], "자체계산")
        self.assertEqual(row["facts"]["PER"], "5")
        self.assertNotIn("header", row)


class ValuationEvidenceEdgeTests(unittest.TestCase):
    def apply(self, pin=None, cap_as_of=None):
        val = {"mktcap": 100e8, "PER": 10,
               "_per_in": pin if pin is not None else {"mktcap": 100e8, "net_income": 10e8}}
        row = {"facts": {"EPS": "123원"}, "facts_note": {"EPS": "keep"},
               "facts_calc": {"PER": "old evidence", "BPS": "keep"},
               "header": {"market_cap": "old cap", "other": "keep"}}
        builder._apply_cap_per_facts(row, val, cap_as_of)
        return row

    def test_ttm_never_uses_other_annual_income_when_both_keys_exist(self):
        row = self.apply({"mktcap": 100e8, "net_income": 999e8, "net_income_ttm": 10e8,
                          "basis": "ttm", "quarter_end": "2026-06-30"})
        self.assertIn("순이익 10억", row["facts_calc"]["PER"])
        self.assertNotIn("999억", row["facts_calc"]["PER"])

    def test_missing_ttm_is_not_backfilled_from_annual_or_per(self):
        row = self.apply({"mktcap": 100e8, "net_income": 10e8, "basis": "ttm"})
        self.assertNotIn("PER", row["facts_calc"])
        self.assertEqual(row["facts_note"]["PER"], "자체계산 · 계산 근거 미확인")
        self.assertEqual(row["facts"]["PER"], "10")

    def test_missing_zero_negative_and_nonfinite_inputs_are_not_explanations(self):
        for value in [None, "", "bad", 0, -10, float("nan"), float("inf")]:
            with self.subTest(value=value):
                row = self.apply({"mktcap": 100e8, "net_income": value})
                self.assertNotIn("PER", row["facts_calc"])
                self.assertIn("미확인", row["facts_note"]["PER"])

    def test_mismatched_numerator_does_not_publish_contradictory_evidence(self):
        row = self.apply({"mktcap": 101e8, "net_income": 10e8})
        self.assertNotIn("PER", row["facts_calc"])

    def test_valid_market_dates_normalize_without_a_clock_fallback(self):
        for value in ["20260911", "2026-09-11", 20260911]:
            with self.subTest(value=value):
                self.assertIn("시총 2026-09-11 기준", self.apply(cap_as_of=value)["facts_calc"]["PER"])
        for value in [None, "", "2026-02-30", "2026-09-11T12:00:00", "generated yesterday"]:
            with self.subTest(value=value):
                self.assertIn("시총 기준일 미확인", self.apply(cap_as_of=value)["facts_calc"]["PER"])

    def test_missing_period_does_not_imply_current_year_or_annual(self):
        result = self.apply()["facts_calc"]["PER"]
        self.assertIn("결산연도 미확인", result)
        self.assertIn("공시기간 미확인", result)
        self.assertNotIn("연간", result)

    def test_annual_and_interim_codes_remain_distinct(self):
        for code, label in [("11011", "연간"), ("11013", "1분기 공시"),
                            ("11012", "반기 공시"), ("11014", "3분기 공시")]:
            with self.subTest(code=code):
                val = builder._valuation_map({"000001": {"net_income": 10e8, "report_date": "2025",
                    "reprt_code": code}}, {"000001": {"mktcap": 100e8}})["000001"]
                result = self.apply(val["_per_in"])["facts_calc"]["PER"]
                self.assertIn("2025년 " + label, result)

    def test_ttm_missing_end_is_explicit(self):
        result = self.apply({"basis": "ttm", "mktcap": 100e8, "net_income_ttm": 10e8})["facts_calc"]["PER"]
        self.assertIn("최근 12개월(TTM) · 종료일 미확인", result)

    def test_valuation_precedence_and_numeric_outputs_do_not_change(self):
        fund = {"000001": {"net_income": 20e8, "revenue": 50e8, "total_assets": 100e8, "debt_ratio": 100}}
        caps = {"000001": {"mktcap": 100e8, "shares": 1e6}}
        annual = {"000001": [{"year": 2025, "net": 10e8}]}
        panel = {"000001": {"net_income_ttm": 5e8, "equity": 10e8}}
        before = copy.deepcopy((fund, caps, annual, panel))
        value = builder._valuation_map(fund, caps, annual, panel)["000001"]
        self.assertEqual((fund, caps, annual, panel), before)
        self.assertEqual({k: value[k] for k in ["PER", "PBR", "PSR", "BPS"]},
                         {"PER": 5, "PBR": 2, "PSR": 2, "BPS": 5000})

    def test_panel_precedes_annual_fallback_without_changing_values(self):
        value = builder._valuation_map({}, {"000001": {"mktcap": 100e8}},
            {"000001": [{"year": 2025, "net": 10e8}]},
            {"000001": {"net_income_ttm": 5e8, "equity": 50e8}})["000001"]
        self.assertEqual(value["PER"], 20)
        self.assertEqual(value["PBR"], 2)
        self.assertEqual(value["_per_in"]["basis"], "ttm")

    def test_unrelated_display_fields_and_input_are_preserved(self):
        row = self.apply()
        self.assertEqual(row["facts"]["EPS"], "123원")
        self.assertEqual(row["facts_note"]["EPS"], "keep")
        self.assertEqual(row["facts_calc"]["BPS"], "keep")
        self.assertEqual(row["header"]["other"], "keep")

    def test_no_calculated_per_does_not_rewrite_existing_per(self):
        row = {"facts": {"PER": "20"}, "header": None}
        builder._apply_cap_per_facts(row, {"mktcap": 100e8})
        self.assertEqual(row["facts"]["PER"], "20")
        self.assertIsNone(row["header"])
        self.assertNotIn("PER", row["facts_calc"])


if __name__ == "__main__":
    unittest.main()
