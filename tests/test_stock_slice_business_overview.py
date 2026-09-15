"""Opt-in business excerpt delivery; no default/US transfer regression."""
import importlib.util
import io
import json
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("slice_under_test", ROOT / "vercel-api/api/stock_slice.py")
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)
FILENAME = "kr_business_overview_public.json"


class BusinessOverviewContract(unittest.TestCase):
    def setUp(self):
        api._CACHE.clear()
        api._FNAME_TTL = None
        self.row = {"name": "테스트 기업", "text": "공식 사업보고서 발췌.", "fiscal_year": "2025",
                    "filed_at": "20260310", "source": "DART 사업보고서", "truncated": False,
                    "url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260310002820"}
        self.doc = {"_meta": {"generated_at": "2026-09-15T00:20:49+09:00"},
                    "rows": {"005930": self.row, "000660": {"text": "다른 기업 발췌."}}}

    def run_request(self, query, overview=None):
        loads = []
        payload = self.doc if overview is None else overview

        def load(filename):
            loads.append(filename)
            if filename == FILENAME:
                return payload
            if filename == "stock_report_public.json":
                return {"stocks": [{"ticker": "005930", "name": "테스트 기업"}]}
            return {}

        request = object.__new__(api.handler)
        request.path = "/api/stock_slice?" + query
        result = {}
        request._send = lambda code, body, cache=False: result.update(code=code, body=body, cache=cache)
        with patch.object(api, "_load", side_effect=load):
            request.do_GET()
        return result, loads

    def test_default_kr_never_loads_optional_file(self):
        result, loads = self.run_request("ticker=005930")
        self.assertEqual(result["code"], 200)
        self.assertEqual(set(loads), set(api.KR_SOURCES.values()))
        self.assertNotIn(FILENAME, loads)
        self.assertNotIn("business_overview", result["body"])

    def test_opt_in_selects_exact_issuer_and_preserves_original(self):
        result, loads = self.run_request("ticker=005930&overview=1")
        self.assertEqual(loads.count(FILENAME), 1)
        self.assertEqual(result["body"]["business_overview"], self.row)
        self.assertEqual(result["body"]["business_overview_as_of"], self.doc["_meta"]["generated_at"])
        self.assertEqual(result["body"]["report"]["ticker"], "005930")
        self.assertNotIn("rows", result["body"])
        self.assertTrue(result["cache"])

    def test_us_ignores_opt_in(self):
        result, loads = self.run_request("ticker=orcl&overview=1")
        self.assertEqual(result["body"]["ticker"], "ORCL")
        self.assertEqual(set(loads), set(api.US_SOURCES.values()))
        self.assertNotIn("business_overview", result["body"])

    def test_flag_must_be_exact_one(self):
        for flag in ["0", "true", "yes", "2", ""]:
            with self.subTest(flag=flag):
                _, loads = self.run_request("ticker=005930&overview=" + flag)
                self.assertNotIn(FILENAME, loads)

    def test_invalid_ticker_fetches_nothing(self):
        for query in ["overview=1", "ticker=..%2Fbad&overview=1", "ticker=%3Cscript%3E&overview=1"]:
            with self.subTest(query=query):
                result, loads = self.run_request(query)
                self.assertEqual(result["code"], 400)
                self.assertEqual(loads, [])

    def test_opt_in_does_not_mutate_default_sources(self):
        before = dict(api.KR_SOURCES)
        self.run_request("ticker=005930&overview=1")
        self.assertEqual(api.KR_SOURCES, before)
        _, loads = self.run_request("ticker=005930")
        self.assertNotIn(FILENAME, loads)

    def test_missing_or_malformed_row_stays_null(self):
        for doc in [{}, {"rows": []}, {"rows": {"000660": self.row}},
                    {"rows": {"005930": {"text": " "}}}, {"rows": {"005930": {"text": 17}}}]:
            with self.subTest(doc=doc):
                result, _ = self.run_request("ticker=005930&overview=1", doc)
                self.assertIsNone(result["body"]["business_overview"])
                self.assertEqual(result["code"], 200)

    def test_loader_failure_does_not_remove_report(self):
        with patch.object(api, "_load", side_effect=lambda f: None if f == FILENAME else
                          {"stocks": [{"ticker": "005930"}]}):
            request = object.__new__(api.handler)
            request.path = "/api/stock_slice?ticker=005930&overview=1"
            sent = []
            request._send = lambda code, body, cache=False: sent.append(body)
            request.do_GET()
        self.assertEqual(sent[0]["report"]["ticker"], "005930")
        self.assertIsNone(sent[0]["business_overview"])

    def test_optional_source_uses_two_hour_cache(self):
        self.assertEqual(api._ttl_for(FILENAME), 7200)
        self.assertEqual(api._ttl_for("stock_flow_5d.json"), 1800)

    def test_malformed_optional_metadata_does_not_break_report(self):
        result, _ = self.run_request("ticker=005930&overview=1", {"_meta": "invalid", "rows": self.doc["rows"]})
        self.assertEqual(result["code"], 200)
        self.assertEqual(result["body"]["business_overview"], self.row)
        self.assertIsNone(result["body"]["business_overview_as_of"])

    def test_metadata_date_never_substitutes_filing_date(self):
        result, _ = self.run_request("ticker=005930&overview=1")
        self.assertEqual(result["body"]["business_overview"]["filed_at"], "20260310")
        self.assertNotEqual(result["body"]["business_overview"]["filed_at"], result["body"]["business_overview_as_of"])

    def test_loader_reuses_valid_cache(self):
        api._CACHE[FILENAME] = (api.time.time(), self.doc)
        with patch.object(api.requests, "get", side_effect=AssertionError("network not expected")):
            self.assertIs(api._load(FILENAME), self.doc)

    def test_rows_are_not_attached_to_regular_report(self):
        result, _ = self.run_request("ticker=005930&overview=1")
        self.assertNotIn("business_overview", result["body"]["report"])
        self.assertEqual(len(result["body"]["business_overview"]["text"]), len(self.row["text"]))

    def test_real_handler_serializes_only_selected_record(self):
        result, _ = self.run_request("ticker=005930&overview=1")
        response = object.__new__(api.handler)
        response.wfile = io.BytesIO()
        headers = []
        response.send_response = lambda status: headers.append(("status", status))
        response.send_header = lambda key, value: headers.append((key, value))
        response.end_headers = lambda: None
        response._send(200, result["body"], cache=True)
        body = json.loads(response.wfile.getvalue())
        self.assertEqual(body["business_overview"], self.row)
        self.assertNotIn("다른 기업", response.wfile.getvalue().decode())
        self.assertTrue(any(k == "Cache-Control" and "s-maxage=1800" in v for k, v in headers if isinstance(v, str)))


if __name__ == "__main__":
    unittest.main()
