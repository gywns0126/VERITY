"""Public Vercel source reuse and response-cache boundaries; no network calls."""
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import io
import json
from pathlib import Path
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "vercel-api/api" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Response:
    def __init__(self, payload=None, status=200, headers=None):
        self.status_code = status
        self.headers = headers or {"ETag": '"published-v1"'}
        self.payload = payload

    def json(self):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


def invoke(module, path):
    request = module.handler.__new__(module.handler)
    request.path = path
    request.wfile = io.BytesIO()
    request.headers_seen = {}
    request.send_response = lambda code: setattr(request, "status_seen", code)
    request.send_header = lambda key, value: request.headers_seen.__setitem__(key, value)
    request.end_headers = lambda: None
    request.do_GET()
    return request.status_seen, request.headers_seen, json.loads(request.wfile.getvalue())


class PublicSourceCacheTests(unittest.TestCase):
    def setUp(self):
        self.forensics = load("us_forensics")
        self.financials = load("us_financials")
        self.doc = {"stocks": [{"ticker": "AAPL", "value": 1}, {"ticker": "MSFT", "value": 2}],
                    "_meta": {"generated_at": "2026-10-14T12:00:00Z"}}

    def test_two_tickers_share_one_forensic_download_and_original_date(self):
        module = self.forensics
        with patch.object(module.requests, "get", return_value=Response(self.doc)) as get:
            first = module._fetch_one("insider", module.SOURCES["insider"], "AAPL")
            second = module._fetch_one("insider", module.SOURCES["insider"], "MSFT")
        self.assertEqual(get.call_count, 1)
        self.assertNotIn("?", get.call_args.args[0])
        self.assertEqual((first[1]["value"], second[1]["value"]), (1, 2))
        self.assertEqual(second[2]["generated_at"], self.doc["_meta"]["generated_at"])

    def test_forensic_expiry_revalidates_without_parsing_304_body(self):
        module, now = self.forensics, [0]
        filename = module.SOURCES["insider"]
        with patch.object(module.time, "monotonic", side_effect=lambda: now[0]), \
                patch.object(module.requests, "get", side_effect=[Response(self.doc), Response(ValueError("no body"), 304)]) as get:
            first = module._load_source(filename)
            now[0] = module.SOURCE_CACHE_TTL + 1
            second = module._load_source(filename)
        self.assertIs(first, second)
        self.assertEqual(get.call_count, 2)
        self.assertEqual(get.call_args.kwargs["headers"], {"If-None-Match": '"published-v1"'})

    def test_forensic_error_after_expiry_is_unavailable_and_retried(self):
        module, now = self.forensics, [0]
        filename = module.SOURCES["insider"]
        with patch.object(module.time, "monotonic", side_effect=lambda: now[0]), \
                patch.object(module.requests, "get", side_effect=[Response(self.doc), Response(None, 503), Response(self.doc)]) as get:
            module._load_source(filename)
            now[0] = module.SOURCE_CACHE_TTL + 1
            self.assertEqual(module._fetch_one("insider", filename, "AAPL")[3], "unavailable")
            self.assertEqual(module._fetch_one("insider", filename, "AAPL")[3], "ok")
        self.assertEqual(get.call_count, 3)

    def test_forensic_concurrent_requests_download_once(self):
        module = self.forensics
        entered, release = threading.Event(), threading.Event()
        def get(*args, **kwargs):
            entered.set()
            self.assertTrue(release.wait(2))
            return Response(self.doc)
        with patch.object(module.requests, "get", side_effect=get) as network, ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(module._load_source, module.SOURCES["insider"]) for _ in range(8)]
            self.assertTrue(entered.wait(2))
            release.set()
            results = [future.result(timeout=2) for future in futures]
        self.assertEqual(network.call_count, 1)
        self.assertTrue(all(result == self.doc for result in results))

    def test_forensic_source_base_change_does_not_reuse_other_source(self):
        module = self.forensics
        filename = module.SOURCES["insider"]
        with patch.object(module.requests, "get", return_value=Response(self.doc)) as get:
            module._load_source(filename)
            with patch.dict(module.os.environ, {module.SOURCE_BASE_ENV: "https://example.invalid/source"}):
                module._load_source(filename)
        self.assertEqual(get.call_count, 2)
        self.assertTrue(get.call_args.args[0].startswith("https://example.invalid/source/"))

    def test_malformed_forensic_snapshot_is_unavailable_not_cached(self):
        module = self.forensics
        filename = module.SOURCES["insider"]
        with patch.object(module.requests, "get", side_effect=[Response({"stocks": ["invalid"]}), Response(self.doc)]) as network:
            self.assertEqual(module._fetch_one("insider", filename, "AAPL")[3], "unavailable")
            self.assertEqual(module._fetch_one("insider", filename, "AAPL")[3], "ok")
        self.assertEqual(network.call_count, 2)

    def test_forensic_response_coverage_and_partial_failure_cache_boundary(self):
        module = self.forensics
        with patch.object(module.requests, "get", return_value=Response(self.doc)):
            code, headers, body = invoke(module, "/api/us_forensics?ticker=AAPL")
        self.assertEqual(code, 200)
        self.assertEqual(body["coverage"], {"source_connected_n": 6, "source_total_n": 6, "record_present_n": 6})
        self.assertIn("s-maxage=300", headers["Cache-Control"])
        with patch.object(module, "_fetch_one", side_effect=lambda key, filename, ticker:
                          (key, None, None, "unavailable" if key == "insider" else "ok")):
            code, headers, body = invoke(module, "/api/us_forensics?ticker=AAPL")
        self.assertEqual(code, 200)
        self.assertEqual(body["coverage"]["source_connected_n"], 5)
        self.assertEqual(body["sources"]["insider"]["data_state"], "source_unavailable")
        self.assertEqual(headers["Cache-Control"], "no-store")

    def test_forensic_invalid_and_total_failure_are_not_cached(self):
        module = self.forensics
        code, headers, _ = invoke(module, "/api/us_forensics?ticker=bad%20ticker")
        self.assertEqual((code, headers["Cache-Control"]), (400, "no-store"))
        with patch.object(module.requests, "get", return_value=Response(None, 503)):
            code, headers, body = invoke(module, "/api/us_forensics?ticker=AAPL")
        self.assertEqual((code, headers["Cache-Control"]), (503, "no-store"))
        self.assertEqual(body["coverage"] if "coverage" in body else len(body["sources"]), 6)
        self.assertEqual(len(module._SOURCE_CACHE), 0)

    def test_financial_repeat_and_expiry_refresh_changed_payload(self):
        module, now = self.financials, [0]
        with patch.object(module.time, "monotonic", side_effect=lambda: now[0]), \
                patch.object(module.requests, "get", side_effect=[Response({"as_of": "old"}), Response({"as_of": "new"})]) as get:
            self.assertEqual(module._fetch_json("AAPL.json"), ({"as_of": "old"}, 200))
            self.assertEqual(module._fetch_json("AAPL.json"), ({"as_of": "old"}, 200))
            self.assertEqual(get.call_count, 1)
            now[0] = module.SOURCE_CACHE_TTL + 1
            self.assertEqual(module._fetch_json("AAPL.json"), ({"as_of": "new"}, 200))
        self.assertEqual(get.call_count, 2)
        self.assertNotIn("?", get.call_args.args[0])
        self.assertIn("If-None-Match", get.call_args.kwargs["headers"])

    def test_financial_conditional_304_keeps_original_date(self):
        module, now = self.financials, [0]
        with patch.object(module.time, "monotonic", side_effect=lambda: now[0]), \
                patch.object(module.requests, "get", side_effect=[Response({"as_of": "original"}), Response(ValueError("no body"), 304)]):
            module._fetch_json("AAPL.json")
            now[0] = module.SOURCE_CACHE_TTL + 1
            self.assertEqual(module._fetch_json("AAPL.json"), ({"as_of": "original"}, 200))

    def test_financial_failures_not_cached_and_recovery(self):
        module = self.financials
        with patch.object(module.requests, "get", side_effect=[Response(None, 404), Response(None, 503), Response(ValueError("bad JSON")), Response({"as_of": "ok"})]) as get:
            self.assertEqual(module._fetch_json("AAPL.json"), (None, 404))
            self.assertEqual(module._fetch_json("AAPL.json"), (None, 503))
            self.assertEqual(module._fetch_json("AAPL.json"), (None, 503))
            self.assertEqual(module._fetch_json("AAPL.json"), ({"as_of": "ok"}, 200))
        self.assertEqual(get.call_count, 4)

    def test_financial_cache_is_bounded_across_tickers(self):
        module = self.financials
        with patch.object(module.requests, "get", return_value=Response({"as_of": "original"})):
            for index in range(module.SOURCE_CACHE_LIMIT + 10):
                module._fetch_json(f"T{index}.json")
        self.assertEqual(len(module._SOURCE_CACHE), module.SOURCE_CACHE_LIMIT)
        self.assertFalse(any(url.endswith("/T0.json") for url in module._SOURCE_CACHE))

    def test_financial_concurrent_requests_download_once(self):
        module = self.financials
        entered, release = threading.Event(), threading.Event()
        def get(*args, **kwargs):
            entered.set()
            self.assertTrue(release.wait(2))
            return Response({"as_of": "original"})
        with patch.object(module.requests, "get", side_effect=get) as network, ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(module._fetch_json, "AAPL.json") for _ in range(8)]
            self.assertTrue(entered.wait(2))
            release.set()
            results = [future.result(timeout=2) for future in futures]
        self.assertEqual(network.call_count, 1)
        self.assertTrue(all(result == ({"as_of": "original"}, 200) for result in results))

    def test_nonobject_source_not_cached(self):
        for module, call in (
                (self.forensics, lambda: self.forensics._load_source(self.forensics.SOURCES["insider"])),
                (self.financials, lambda: self.financials._fetch_json("AAPL.json"))):
            with patch.object(module.requests, "get", side_effect=[Response(None), Response(self.doc)]) as network:
                first = call()
                self.assertIn(first, (None, (None, 503)))
                second = call()
                self.assertEqual(second, self.doc if module is self.forensics else (self.doc, 200))
            self.assertEqual(network.call_count, 2)

    def test_financial_response_success_and_missing_boundaries(self):
        module = self.financials
        with patch.object(module.requests, "get", return_value=Response({"ticker": "AAPL", "as_of": "original"})):
            code, headers, body = invoke(module, "/api/us_financials?ticker=AAPL")
        self.assertEqual((code, body["as_of"]), (200, "original"))
        self.assertIn("s-maxage=300", headers["Cache-Control"])
        with patch.object(module.requests, "get", return_value=Response(None, 404)):
            code, headers, body = invoke(module, "/api/us_financials?ticker=MSFT")
        self.assertEqual((code, headers["Cache-Control"], body["status"]), (404, "no-store", "not_found"))


if __name__ == "__main__":
    unittest.main()
