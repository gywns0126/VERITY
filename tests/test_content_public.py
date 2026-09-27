"""Offline only: python3 -B tests/test_content_public.py."""

from copy import deepcopy
from email.message import Message
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError


SPEC = importlib.util.spec_from_file_location(
    "content_public", Path(__file__).resolve().parents[1] / "vercel-api" / "content_public.py")
public = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(public)
CHECKED = "2026-09-27T05:00:00+00:00"


def dossier(ticker="CAT"):
    # Structural fixture of report_evidence.analysis_prompt's public dossier.
    # Deliberately withheld latest quarter and mixed cash units must survive.
    return {
        "version": "evidence-report-v7", "ticker": ticker, "name": "Example",
        "market": "KR" if ticker.isdigit() else "US", "generated": "2099-01-01 12:00 KST",
        "summary": [{"observation": "비교 보류", "question": "원문 확인", "source": None}],
        "business_profile": {"available": False, "summary": "원문 미확보"},
        "annual_basis": "확정 여부 미확인",
        "comparison": {"usable": False, "reason": "보고 통화가 다르므로 비교 보류"},
        "reader": {"current": None, "observations": ["최신 분기 기간 확인 불가로 보류"],
                   "cash_notes": ["기간·통화·공시번호 불일치: 차감하지 않음"],
                   "cash_rows": [["OCF", "USD 1,000 million"], ["Capex", "미수신"]]},
        "reading": {"cards": [{"checklist": "현재 상태: 원문 미검증"}]},
        "annual_core": [["FY2025", "$1,000M", "—", "$200M"]],
        "recent_events": [],
        "news": {"items": [], "status": "unavailable", "note": "사건 부재 아님",
                 "fetched_at": "2026-09-27T05:00:00+00:00", "window_days": 7,
                 "window_start": "2026-09-20 14:00 KST", "window_end": "2026-09-27 14:00 KST",
                 "shown": 0, "matched": 0, "received": 3, "duplicates": 0, "eligible": 0},
        "issues": [{"question": "누락을 0으로 간주하지 않음"}],
        "gaps": ["분기 누락", "뉴스 빈 목록은 사건 부재 아님"],
        "sections": [{"id": "CF1", "note": "자체계산 · 동일 기간만 비교",
                      "rows": [["FY2025", "USD 1,000 million", {"url": "https://www.sec.gov/example", "text": "원문"}]],
                      "shown": 1, "total": 7}],
        "coverage": [{"id": "R", "status": "수신", "published": "2026-09-22",
                      "artifact_url": public.BLOB + "stock_report_public.json", "reason": "원문 검증 아님"}],
        "translation_coverage": {"note": "비공식 번역"},
    }


def export(data=None):
    return ("OUTSIDE_INSTRUCTIONS_DO_NOT_INCLUDE\n" + public._START + "\n"
            + json.dumps(data if data is not None else dossier(), ensure_ascii=False)
            + "\n" + public._END + "\nAFTER_INSTRUCTIONS_DO_NOT_INCLUDE").encode()


def news(n=12):
    return {"updated_at": "2026-09-26T09:00:00+09:00", "news_refreshed_at": "2026-09-27T07:00:00+09:00",
            "recommendations": [{"private_data": "NEVER_RETURN"}],
            **{key: [{"title": f"{key} headline {i}", "time": "Sun, 27 Sep 2026 05:57:01 +0900",
                      "link": "https://www.yna.co.kr/view/example", "source": "연합뉴스", "category": "kr_rss",
                      "composite_score": .91, "private_data": "NEVER_RETURN"} for i in range(n)]
               for key in ("headlines", "us_headlines", "bloomberg_google_headlines")}}


def briefing():
    return {"date": "2026-09-27", "generated_at": "2026-09-27T13:43:29+09:00", "session": "휴장",
            "recap_as_of": "20260922", "disclaimer": "자체계산 예상 창 · 매매의견 아님",
            "sections": [{"title": "시장", "as_of": "20260922", "note": "이전 거래일; 등락률 단위 %",
                          "recap": {"date": "09/22", "kospi": .15, "kospi_close": 7017.91},
                          "items": [{"name": "지수", "text": "코스피 7,017.91 (+0.15%)"}]},
                         {"title": "예상 일정", "note": "자체계산 ±7일, 확정 아님",
                          "items": [{"ticker": "259960", "date": "2026-09-27", "name": "Example"} for _ in range(12)]}]}


class Response:
    def __init__(self, raw=b"body", url=None, status=200, encoding=None):
        self.raw, self.url, self.status = raw, url or public._company_url("CAT"), status
        self.headers = Message()
        if encoding:
            self.headers["Content-Encoding"] = encoding
        self.read_limits = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def geturl(self):
        return self.url

    def read(self, limit):
        self.read_limits.append(limit)
        return self.raw[:limit]


class PublicTests(unittest.TestCase):
    def setUp(self):
        public._CACHE.clear()
        guard = patch.object(public, "build_opener", side_effect=AssertionError("LIVE NETWORK FORBIDDEN"))
        guard.start()
        self.addCleanup(guard.stop)
        clock = patch.object(public, "_stamp", return_value=CHECKED)
        clock.start()
        self.addCleanup(clock.stop)

    def company(self, data=None, raw=None, ticker="CAT"):
        with patch.object(public, "_fetch_bytes", return_value=raw if raw is not None else export(data)):
            return public.load_company(ticker)

    def source(self, kind, data):
        with patch.object(public, "_fetch_bytes", return_value=json.dumps(data, ensure_ascii=False).encode()):
            return public.load_public(kind)

    def test_exact_dossier_gates_units_coverage_and_no_outer_prompt(self):
        data = dossier()
        result = self.company(data)
        self.assertEqual(result["dossier"], data)
        self.assertEqual(result["source_response_checked_at"], CHECKED)
        self.assertEqual(result["retrieved_at"], CHECKED)
        self.assertEqual(result["freshness"], "unknown")
        for flag in ("original_checked", "latest_revision_verified", "breaking_eligible"):
            self.assertIs(result[flag], False)
        self.assertNotIn("OUTSIDE_INSTRUCTIONS", json.dumps(result))
        self.assertNotIn("AFTER_INSTRUCTIONS", json.dumps(result))

    def test_top_whitelist_and_nested_private_fail_closed(self):
        data = dossier()
        data.update(prompt_rules=["EXECUTE_ME"], private_data="PRIVATE", prompt_url="https://evil.test")
        self.assertEqual(self.company(data)["dossier"], dossier())
        public._CACHE.clear()
        data["reader"]["access_token"] = "SECRET"
        with self.assertRaisesRegex(public.PublicSourceError, "source_field_not_public"):
            self.company(data)

    def test_actual_build_report_export_kr_and_us_fixtures(self):
        fixture_spec = importlib.util.spec_from_file_location(
            "public_export_contract_fixtures", Path(__file__).with_name("test_report_evidence.py"))
        fixtures = importlib.util.module_from_spec(fixture_spec)
        fixture_spec.loader.exec_module(fixtures)
        for kr in (True, False):
            with self.subTest(kr=kr):
                ticker, source_data, _ = fixtures.fixture(kr=kr)
                # Existing builder fixture fetch is dictionary-only: no live calls.
                report = fixtures.build(source_data, ticker)
                self.assertIsInstance(report["news"], dict)
                raw = fixtures.analysis_prompt(report).encode("utf-8")
                result = self.company(raw=raw, ticker=ticker)
                expected = {key: value for key, value in report.items()
                            if key not in ("prompt_rules", "disclaimer", "source_line")}
                self.assertEqual(result["dossier"], expected)
                self.assertEqual(result["dossier"]["news"], report["news"])
                self.assertEqual(result["dossier"]["annual_basis"], report["annual_basis"])
                self.assertEqual(result["freshness"], "unknown")

    def test_valid_tickers_fixed_exact_endpoint(self):
        for ticker in ("005930", "CAT", "BRK.B", "BRK-B", "A1"):
            with self.subTest(ticker=ticker), patch.object(public, "_fetch_bytes", return_value=export(dossier(ticker))) as fetch:
                self.assertEqual(public.load_company(ticker)["ticker"], ticker)
                fetch.assert_called_once_with(public._company_url(ticker), 512 * 1024)

    def test_invalid_arguments_never_fetch(self):
        with patch.object(public, "_fetch_bytes") as fetch:
            for ticker in (None, True, {}, "cat", " CAT", "CAT\n", "12345", "１２３４５６", "A" * 11, "https://x", "CAT&url=http://127.0.0.1"):
                with self.subTest(ticker=ticker), self.assertRaises(ValueError):
                    public.load_company(ticker)
            for kind in (None, {}, "macro", "masters", "News", "https://x"):
                with self.assertRaises(ValueError):
                    public.load_public(kind)
            fetch.assert_not_called()

    def test_invalid_export_markers(self):
        for raw in (b"{}", export() + ("\n" + public._START).encode(),
                    export().replace(public._END.encode(), b"WRONG"),
                    (public._END + "\n{}\n" + public._START).encode()):
            with self.subTest(raw=raw[:20]), self.assertRaises(public.PublicSourceError):
                self.company(raw=raw)

    def test_wrong_ticker_and_missing_dossier_shape(self):
        for data in (dossier("AAPL"), {"ticker": "CAT"}, [], {**dossier(), "sections": [{}]},
                     {**dossier(), "reader": []}, {**dossier(), "market": "KR"},
                     {**dossier(), "news": []}, {**dossier(), "news": {"items": []}}):
            with self.subTest(data=str(data)[:30]), self.assertRaises(public.PublicSourceError):
                self.company(data)

    def test_malformed_decode_json_duplicate_and_nonfinite_are_source_errors(self):
        invalid = [b"\xff", export().replace(b'"ticker": "CAT"', b'"ticker":"CAT", "ticker":"CAT"'),
                   export().replace(b'"recent_events": []', b'"recent_events": [NaN]'),
                   export().replace(b'"recent_events": []', b'"recent_events": [1e999]'),
                   export().replace(b'"recent_events": []', b'"recent_events": [oops]')]
        for raw in invalid:
            with self.subTest(raw=raw[:15]), self.assertRaises(public.PublicSourceError) as caught:
                self.company(raw=raw)
            self.assertNotIsInstance(caught.exception, ValueError)

    def test_company_response_size_even_with_injected_fetch(self):
        with self.assertRaisesRegex(public.PublicSourceError, "response_too_large"):
            self.company(raw=b" " * (public.MAX_COMPANY_BYTES + 1))

    def test_output_overflow_fails_no_partial_facts(self):
        data = dossier()
        data["gaps"] = ["가" * 65000]
        with self.assertRaisesRegex(public.PublicSourceError, "output_too_large"):
            self.company(data)
        self.assertFalse(public._CACHE)

    def test_nested_depth_limit(self):
        data = dossier()
        nested = None
        for _ in range(35):
            nested = [nested]
        data["reader"]["nested"] = nested
        with self.assertRaisesRegex(public.PublicSourceError, "source_structure_too_large"):
            self.company(data)

    def test_cache_preserves_checked_time_and_defensive_copy(self):
        with patch.object(public, "_fetch_bytes", return_value=export()) as fetch, patch.object(public.time, "monotonic", return_value=100):
            first = public.load_company("CAT")
            first["dossier"]["gaps"].clear()
            with patch.object(public, "_stamp", return_value="LATER"):
                cached = public.load_company("CAT")
            self.assertEqual(cached["retrieved_at"], CHECKED)
            self.assertEqual(cached["source_response_checked_at"], CHECKED)
            self.assertEqual(cached["dossier"]["gaps"], dossier()["gaps"])
            self.assertEqual(fetch.call_count, 1)

    def test_expired_cache_failure_never_returns_old_success(self):
        with patch.object(public.time, "monotonic", return_value=100):
            self.company()
        with patch.object(public.time, "monotonic", return_value=400), patch.object(public, "_fetch_bytes", side_effect=TimeoutError("secret")):
            with self.assertRaisesRegex(public.PublicSourceError, "^public_source_unavailable$"):
                public.load_company("CAT")
        self.assertNotIn(("company", "CAT"), public._CACHE)
        with patch.object(public, "_stamp", return_value="NEW_CHECK"):
            self.assertEqual(self.company()["retrieved_at"], "NEW_CHECK")

    def test_cache_bounded_lru(self):
        for i in range(17):
            self.company(dossier("A" + str(i)), ticker="A" + str(i))
        self.assertEqual(len(public._CACHE), 16)
        self.assertNotIn(("company", "A0"), public._CACHE)

    def test_lock_contention_bounded_and_no_stale(self):
        lock = Mock()
        lock.acquire.return_value = False
        with patch.object(public, "_LOCK", lock), patch.object(public, "_fetch_bytes") as fetch:
            with self.assertRaisesRegex(public.PublicSourceError, "reader_busy"):
                public.load_company("CAT")
            lock.acquire.assert_called_once_with(timeout=1)
            fetch.assert_not_called()
            lock.release.assert_not_called()

    def test_upstream_failures_are_sanitized_and_release_lock(self):
        for exc in (TimeoutError("SECRET"), ValueError("SECRET"), OSError("SECRET")):
            with patch.object(public, "_fetch_bytes", side_effect=exc), self.assertRaisesRegex(public.PublicSourceError, "^public_source_unavailable$"):
                public.load_company("CAT")
        self.assertEqual(self.company()["status"], "available")

    def test_news_three_categories_exact_times_counts_and_projection(self):
        data = news()
        result = self.source("news", data)
        self.assertEqual(result["items_in_feed"], 36)
        self.assertEqual(result["items_displayed"], 30)
        self.assertEqual(result["items_omitted"], 6)
        self.assertEqual(result["limit_per_group"], 10)
        self.assertEqual(len(result["categories"]), 3)
        for group in result["categories"]:
            self.assertEqual(group["items_in_feed"], 12)
            self.assertEqual(group["items_displayed"], 10)
            self.assertEqual(group["items"][0]["time"], data[group["category"]][0]["time"])
        self.assertNotIn("NEVER_RETURN", json.dumps(result))
        self.assertNotIn("composite_score", json.dumps(result))

    def test_briefing_notes_units_asof_and_denominators(self):
        data = briefing()
        result = self.source("briefing", data)
        self.assertEqual(result["items_in_feed"], 13)
        self.assertEqual(result["items_displayed"], 11)
        self.assertEqual(result["metadata"]["recap_as_of"], "20260922")
        self.assertEqual(result["metadata"]["disclaimer"], data["disclaimer"])
        for i, group in enumerate(result["sections"]):
            self.assertEqual(group["note"], data["sections"][i]["note"])
            self.assertEqual(group["items"], data["sections"][i]["items"][:10])
        self.assertEqual(result["sections"][0]["recap"], data["sections"][0]["recap"])
        self.assertEqual(result["freshness"], "unknown")

    def test_empty_feed_distinct_from_malformed(self):
        self.assertEqual(self.source("news", news(0))["items_in_feed"], 0)
        self.assertEqual(self.source("briefing", {"sections": []})["items_in_feed"], 0)
        for kind, data in (("news", {}), ("news", []), ("briefing", {}), ("briefing", {"sections": [{}]})):
            public._CACHE.clear()
            with self.assertRaises(public.PublicSourceError):
                self.source(kind, data)

    def test_unsupported_nested_public_fields_and_unsafe_links_fail(self):
        for value in ("javascript:alert(1)", "https://user:pass@example.test/x", {"private_data": "x"}):
            data = news(1)
            data["headlines"][0]["link"] = value
            with self.assertRaises(public.PublicSourceError):
                self.source("news", data)

    def test_public_input_and_output_caps(self):
        with patch.object(public, "_fetch_bytes", return_value=b" " * (public.MAX_PUBLIC_BYTES + 1)), self.assertRaisesRegex(public.PublicSourceError, "response_too_large"):
            public.load_public("news")
        data = news(1)
        data["headlines"][0]["title"] = "가" * 65000
        with self.assertRaisesRegex(public.PublicSourceError, "output_too_large"):
            self.source("news", data)

    def test_fetch_seam_refuses_nonfixed_urls_before_network(self):
        for url in ("http://127.0.0.1/", public.REPORT_URL, public._company_url("CAT") + "&url=x",
                    public.BLOB + "private.json", public._company_url("CAT").replace("https:", "http:")):
            with self.assertRaisesRegex(public.PublicSourceError, "source_not_allowed"):
                public._fetch_bytes(url, 100)

    def test_fetch_request_timeout_bytes_and_no_redirect_handler(self):
        response = Response()
        opener = Mock()
        opener.open.return_value = response
        with patch.object(public, "build_opener", return_value=opener) as build:
            self.assertEqual(public._fetch_bytes(public._company_url("CAT"), 100), b"body")
        self.assertEqual(response.read_limits, [101])
        self.assertEqual(opener.open.call_args.kwargs["timeout"], 20)
        request = opener.open.call_args.args[0]
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(request.full_url, public._company_url("CAT"))
        self.assertTrue(any(isinstance(arg, public._NoRedirect) for arg in build.call_args.args))
        self.assertNotIn("Authorization", dict(request.header_items()))
        with self.assertRaises(HTTPError):
            public._NoRedirect().redirect_request(request, None, 302, "", {}, "http://127.0.0.1")

    def test_fetch_non200_redirect_compression_and_byte_limit(self):
        for response in (Response(status=500), Response(url="https://evil.test"),
                         Response(encoding="gzip"), Response(raw=b"x" * 101)):
            opener = Mock()
            opener.open.return_value = response
            with patch.object(public, "build_opener", return_value=opener), self.assertRaises(public.PublicSourceError):
                public._fetch_bytes(public._company_url("CAT"), 100)


if __name__ == "__main__":
    unittest.main()
