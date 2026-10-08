"""Network-free transfer/fallback regression tests for the existing slice API."""
import importlib.util
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, Event
from unittest.mock import Mock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("slice_transfer", ROOT / "vercel-api/api/stock_slice.py")
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)
PRIMARY = api.US_SOURCES["report"]
SMALLCAP = api.US_SOURCES["report_smallcap"]


@pytest.fixture(autouse=True)
def clean_cache():
    api._CACHE.clear()
    api._VALIDATORS.clear()
    api._RETRY_AFTER.clear()
    api._FNAME_TTL = None


def report(ticker="MSFT", date="2026-10-06T10:00:00+09:00"):
    return {"_meta": {"generated_at": date}, "stocks": [{"ticker": ticker, "facts": {"PER": 12}}]}


def response(code=200, doc=None, headers=None):
    return Mock(status_code=code, headers=headers or {}, json=Mock(return_value=doc))


def request(ticker="MSFT"):
    handler = object.__new__(api.handler)
    handler.path = "/api/stock_slice?ticker=" + ticker
    sent = {}
    handler._send = lambda code, body, cache=False: sent.update(code=code, body=body, cache=cache)
    handler.do_GET()
    return sent


def test_primary_hit_never_downloads_smallcap():
    doc = report()
    with patch.object(api, "_load", return_value=doc) as load:
        got = request("msft")
    load.assert_called_once_with(PRIMARY)
    assert got == {"code": 200, "cache": True, "body": {
        "status": "ok", "ticker": "MSFT", "market": "US",
        "report": doc["stocks"][0], "report_as_of": doc["_meta"]["generated_at"]}}


@pytest.mark.parametrize("primary", [None, {}, {"stocks": []}, report("OTHER")])
def test_fallback_preserves_actual_source_date(primary):
    fallback = report("SMALL", "2026-10-05T01:00:00+09:00")
    with patch.object(api, "_load", side_effect=[primary, fallback]) as load:
        got = request("SMALL")
    assert [c.args[0] for c in load.call_args_list] == [PRIMARY, SMALLCAP]
    assert got["body"]["report"] == fallback["stocks"][0]
    assert got["body"]["report_as_of"] == fallback["_meta"]["generated_at"]


def test_missing_report_has_no_misleading_source_date():
    with patch.object(api, "_load", side_effect=[report("OTHER"), report("OTHER2")]):
        got = request()
    assert got["body"]["report"] is None
    assert got["body"]["report_as_of"] is None


def test_warm_cache_avoids_network():
    doc = report()
    api._CACHE[PRIMARY] = (api.time.time(), doc)
    with patch.object(api.requests, "get") as get:
        assert api._load(PRIMARY) is doc
    get.assert_not_called()


def test_etag_304_reuses_body_without_changing_source_date():
    doc = report()
    unchanged = response(304)
    with patch.object(api.requests, "get", side_effect=[response(doc=doc, headers={"ETag": '"v1"'}), unchanged]) as get:
        assert api._load(PRIMARY) is doc
        api._CACHE[PRIMARY] = (0, doc)
        assert api._load(PRIMARY) is doc
    assert get.call_args.kwargs["headers"] == {"If-None-Match": '"v1"'}
    unchanged.json.assert_not_called()
    assert doc["_meta"]["generated_at"] == "2026-10-06T10:00:00+09:00"
    assert api._CACHE[PRIMARY][0] > 0


def test_changed_source_replaces_body_and_old_validators():
    old, new = report(), report(date="2026-10-07T01:00:00+09:00")
    api._CACHE[PRIMARY] = (0, old)
    api._VALIDATORS[PRIMARY] = {"If-None-Match": '"v1"'}
    with patch.object(api.requests, "get", return_value=response(doc=new)):
        assert api._load(PRIMARY) is new
    assert api._VALIDATORS[PRIMARY] == {}


@pytest.mark.parametrize("failure", [response(503), response(429), response(doc=None),
                                      ValueError("bad JSON"), api.requests.Timeout("timeout")])
def test_failed_refresh_keeps_last_good_and_cools_down(failure):
    doc = report()
    api._CACHE[PRIMARY] = (0, doc)
    effect = failure if isinstance(failure, Exception) else None
    with patch.object(api.requests, "get", side_effect=effect, return_value=failure) as get:
        with patch.object(api.time, "monotonic", return_value=100):
            assert api._load(PRIMARY) is doc
            assert api._load(PRIMARY) is doc
        assert get.call_count == 1
        with patch.object(api.time, "monotonic", return_value=131):
            assert api._load(PRIMARY) is doc
        assert get.call_count == 2
    assert api._CACHE[PRIMARY] == (0, doc)


def test_cold_failure_cooldown_then_recovers():
    doc = report()
    with patch.object(api.requests, "get", side_effect=[response(503), response(doc=doc)]) as get:
        with patch.object(api.time, "monotonic", return_value=100):
            assert api._load(PRIMARY) is None
            assert api._load(PRIMARY) is None
        with patch.object(api.time, "monotonic", return_value=131):
            assert api._load(PRIMARY) is doc
    assert get.call_count == 2
    assert PRIMARY not in api._RETRY_AFTER


def test_304_without_cached_body_is_not_a_success():
    with patch.object(api.requests, "get", return_value=response(304)):
        assert api._load(PRIMARY) is None
    assert PRIMARY not in api._CACHE
    assert PRIMARY in api._RETRY_AFTER


def test_simultaneous_cold_requests_share_one_fetch():
    doc = report()
    start = Barrier(6)
    entered, release = Event(), Event()

    def fetch(*args, **kwargs):
        entered.set()
        assert release.wait(3)
        return response(doc=doc)

    def load():
        start.wait(timeout=3)
        return api._load(PRIMARY)

    with patch.object(api.requests, "get", side_effect=fetch) as get:
        with ThreadPoolExecutor(max_workers=6) as pool:
            futures = [pool.submit(load) for _ in range(6)]
            try:
                assert entered.wait(3)
            finally:
                release.set()
            assert all(f.result(timeout=3) is doc for f in futures)
    assert get.call_count == 1


def test_unrelated_sources_can_still_load_in_parallel():
    start = Barrier(2)

    def fetch(*args, **kwargs):
        start.wait(timeout=3)
        return response(doc=report())

    with patch.object(api.requests, "get", side_effect=fetch):
        with ThreadPoolExecutor(max_workers=2) as pool:
            assert all(pool.map(api._load, [PRIMARY, SMALLCAP]))
