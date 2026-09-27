"""Facts failures remain observable without blocking independent sources."""
import io
import json
import socket
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pytest

from api.intelligence import ticker_facts as tf
from api.intelligence import us_filing_probe


@pytest.fixture
def isolated(monkeypatch):
    monkeypatch.setattr(tf, "resolve_ticker", lambda q: (q, q))
    monkeypatch.setattr(tf, "_fetch_json", lambda *a, **k: None)
    monkeypatch.setattr(tf, "_load_local", lambda *a: None)
    monkeypatch.setattr(tf, "_us_realtime", lambda *a: None)
    monkeypatch.setattr(tf, "_us_quote", lambda *a: None)
    monkeypatch.setattr(tf, "_realtime", lambda *a: None)
    monkeypatch.setattr(tf, "_dart_recent_filings", lambda *a: None)
    monkeypatch.setattr(tf, "_daily_bars", lambda *a: None)
    monkeypatch.setattr(tf, "past_decisions_section", lambda *a: (None, None))
    monkeypatch.setattr(us_filing_probe, "probe", lambda *a, **k: None)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    return monkeypatch


def test_registry_is_fully_accounted_for_with_explicit_failures(isolated):
    result = tf.collect("JEPQ", include_private=False)
    rows = result["coverage"]["sources"]
    expected = ({p for p, _ in tf.CORE_FILES} | set(tf.SCAN_FILES) |
                {p for p, _, _ in tf.LOCAL_FILES} |
                {"private:" + p for p, _ in tf.PRIVATE_FILES})
    assert expected <= {r["source"] for r in rows}
    assert len(rows) == len({r["source"] for r in rows})
    coverage = result["coverage"]
    assert sum(coverage[s] for s in ("hit", "no_record", "unavailable", "skipped")) == coverage["total"]
    assert coverage["checked"] == coverage["applicable"]
    assert result["_meta"]["status"] == "empty"


def test_record_date_beats_document_generated_at(isolated):
    etf = {"ticker": "JEPQ", "as_of": "2026-09-01", "top_holdings": [{"ticker": "NVDA"}]}
    isolated.setattr(tf, "_fetch_json", lambda url, *a, **k:
                    {"_meta": {"generated_at": "2026-09-27"}, "etfs": [etf]}
                    if url.endswith("/us_etf.json") else {})
    result = tf.collect("JEPQ", include_private=False)
    section = next(s for s in result["sections"] if s["source"] == "us_etf.json")
    assert section["as_of"] == "2026-09-01"
    assert tf._meta_as_of({"_meta": {"generated_at": "2026-09-27"}}) == ""
    rows = {r["source"]: r for r in result["coverage"]["sources"]}
    assert rows["us_etf.json"]["status"] == "hit"
    assert rows["us_etf.json"]["as_of"] == "2026-09-01"
    assert rows["us_quarterly_public.json"]["status"] == "no_record"
    assert rows["sec:submissions+companyfacts"]["status"] == "skipped"
    assert not any("미국 상장사가 아닐" in x for x in result["missing"])


def test_us_never_calls_kr_live_sources(isolated):
    def prohibited(*a):
        pytest.fail("US query reached KR-only live source")
    for fn in ("_realtime", "_daily_bars", "_dart_recent_filings"):
        isolated.setattr(tf, fn, prohibited)
    tf.collect("JEPQ", include_private=False)


def test_unknown_session_is_not_intraday_or_false_price_missing(isolated):
    isolated.setattr(tf, "_us_realtime", lambda *a: {"현재가": 60, "_asof": "2026-09-27T20:00:00+09:00"})
    result = tf.collect("JEPQ")
    section = next(s for s in result["sections"] if s["source"] == "railway:us_quotes")
    assert "장중" not in section["label"]
    assert section["as_of"] == ""
    assert section["observed_at"]
    assert "판정 불가" in section["data"]["기준"]
    assert not any("가격 축이 하나도" in m for m in result["missing"])


def test_single_bad_provider_does_not_destroy_successful_sections(isolated):
    def bad(*a):
        raise ValueError("invalid provider payload")
    isolated.setattr(tf, "_us_realtime", bad)
    isolated.setattr(tf, "_us_quote", lambda *a: {"현재가": 60, "_as_of": "2026-09-25"})
    result = tf.collect("JEPQ")
    assert result["_meta"]["status"] == "partial"
    assert any(s["source"] == "yahoo:chart" for s in result["sections"])
    assert any(r["reason"] == "ValueError" for r in result["coverage"]["sources"])


@pytest.mark.parametrize("exc,reason", [
    (urllib.error.URLError(socket.gaierror(-2, "name resolution failed")), "dns_error"),
    (urllib.error.HTTPError("https://test/?key=SECRET", 429, "SECRET", {}, None), "http_429"),
    (TimeoutError("SECRET"), "timeout"),
], ids=["dns", "rate-limit", "timeout"])
def test_network_failures_are_classified_and_redacted(monkeypatch, exc, reason):
    def fail(*a, **k):
        raise exc
    monkeypatch.setattr(tf.urllib.request, "urlopen", fail)
    trace = []
    token = tf._FETCH_TRACE.set(trace)
    try:
        assert tf._fetch_json("https://example.com/data?key=SECRET", headers={"apikey": "SECRET"}) is None
    finally:
        tf._FETCH_TRACE.reset(token)
    assert trace == [{"source": "example.com/data", "status": "unavailable", "reason": reason}]
    assert "SECRET" not in json.dumps(trace)


def test_no_cache_bypasses_fresh_file(monkeypatch, tmp_path):
    monkeypatch.setattr(tf, "_CACHE_DIR", str(tmp_path))
    (tmp_path / "test").write_text('{"old":true}')
    monkeypatch.setattr(tf.urllib.request, "urlopen", lambda *a, **k: io.BytesIO(b'{"fresh":true}'))
    assert tf._fetch_json("https://example.com/data", "test") == {"old": True}
    token = tf._BYPASS_CACHE.set(True)
    try:
        assert tf._fetch_json("https://example.com/data", "test") == {"fresh": True}
    finally:
        tf._BYPASS_CACHE.reset(token)


def test_trace_isolated_between_parallel_requests(monkeypatch):
    def collect(query, include_private):
        tf._trace_fetch("https://example.com/" + query, "received")
        return {"ticker": query, "sections": [], "missing": [], "_meta": {}}
    monkeypatch.setattr(tf, "_collect", collect)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(tf.collect, ["JEPQ", "AAPL"]))
    for result in results:
        assert [x["source"] for x in result["_meta"]["fetch_diagnostics"]] == ["example.com/" + result["ticker"]]
    assert tf._FETCH_TRACE.get() is None


def test_session_does_not_relabel_old_trade_as_intraday(monkeypatch):
    monkeypatch.setattr(tf, "_now", lambda: datetime.fromtimestamp(2000, timezone.utc))
    meta = {"currentTradingPeriod": {"regular": {"start": 1900, "end": 2100, "gmtoffset": -14400}}}
    label = tf._us_session_label(meta, datetime.fromtimestamp(1000, timezone.utc))
    assert "이전 세션" in label
    assert "장중 체결가" not in label


def test_yahoo_short_volume_array_is_not_a_fatal_error(monkeypatch):
    doc = {"chart": {"result": [{"meta": {"regularMarketPrice": 61, "regularMarketTime": 2000},
            "timestamp": [1000, 2000], "indicators": {"quote": [{"close": [60, 61], "volume": []}]}}]}}
    monkeypatch.setattr(tf, "_fetch_json", lambda *a, **k: doc)
    assert tf._us_quote("JEPQ")["최근 5봉 [일,종가,거래량]"][-1][2] is None


def test_render_keeps_denominator_diagnostics_and_unknown_dates(isolated):
    result = tf.collect("JEPQ", include_private=False)
    result["sections"].append({"source": "test", "label": "test", "as_of": "", "data": {"x": 1}})
    result["_meta"]["fetch_diagnostics"] = [{"source": "test/file", "status": "unavailable", "reason": "dns_error"}]
    text = tf.render_text(result)
    assert "소스 조회" in text and "조인 0/" in text
    assert "자료 기준일 미상" in text
    assert "dns_error" in text


def test_unresolved_does_not_claim_absence(isolated):
    isolated.setattr(tf, "resolve_ticker", lambda q: ("", ""))
    result = tf.collect("not a ticker")
    assert result["_meta"]["status"] == "unresolved"
    assert "유니버스에 없음" not in " ".join(result["missing"])


def test_sec_primary_and_exhibit_use_distinct_cache_keys(monkeypatch):
    seen = {}
    def fetch(url, cache_key, ttl, as_json=True):
        seen.setdefault(cache_key, url.rsplit("/", 1)[-1])
        return seen[cache_key]
    monkeypatch.setattr(us_filing_probe, "_fetch", fetch)
    primary = us_filing_probe._doc_text("1", "0000000001-26-000001", "primary.htm")
    exhibit = us_filing_probe._doc_text("1", "0000000001-26-000001", "ex99.htm")
    assert primary == "primary.htm"
    assert exhibit == "ex99.htm"
    assert len(seen) == 2


def test_sec_no_cache_and_diagnostics_are_request_scoped(monkeypatch, tmp_path):
    monkeypatch.setattr(us_filing_probe, "_CACHE_DIR", str(tmp_path))
    (tmp_path / "test.json").write_text('{"old":true}')
    def fail(*a, **k):
        raise urllib.error.URLError(socket.gaierror(-2, "secret error text"))
    monkeypatch.setattr(us_filing_probe.urllib.request, "urlopen", fail)
    monkeypatch.setattr(us_filing_probe, "_probe", lambda q: us_filing_probe._fetch("https://data.sec.gov/test", "test.json", 3600))
    trace = []
    assert us_filing_probe.probe("AAPL") == {"old": True}
    assert us_filing_probe.probe("AAPL", no_cache=True, diagnostics=trace) is None
    assert trace[-1]["reason"] == "dns_error"
    assert "secret" not in json.dumps(trace)
    assert us_filing_probe._FETCH_TRACE.get() is None
    assert us_filing_probe._BYPASS_CACHE.get() is False


def test_sec_exhausted_budget_does_not_start_more_requests(monkeypatch):
    def prohibited(*a, **k):
        pytest.fail("deadline did not stop request")
    monkeypatch.setattr(us_filing_probe.urllib.request, "urlopen", prohibited)
    monkeypatch.setattr(us_filing_probe, "_PROBE_BUDGET_SECONDS", 0)
    monkeypatch.setattr(us_filing_probe, "_probe", lambda q: us_filing_probe._fetch("https://data.sec.gov/test", None, 0))
    trace = []
    assert us_filing_probe.probe("AAPL", diagnostics=trace) is None
    assert trace[-1]["reason"] == "budget_exhausted"


def test_sec_failure_is_memoized_inside_one_request(monkeypatch):
    attempts = []
    def fail(*a, **k):
        attempts.append(1)
        raise TimeoutError()
    monkeypatch.setattr(us_filing_probe.urllib.request, "urlopen", fail)
    def repeated(q):
        for _ in range(3):
            us_filing_probe._fetch("https://data.sec.gov/test", None, 0)
    monkeypatch.setattr(us_filing_probe, "_probe", repeated)
    us_filing_probe.probe("AAPL")
    assert len(attempts) == 1


def test_missing_public_local_file_can_use_explicit_allowlisted_fallback(monkeypatch, tmp_path):
    monkeypatch.setattr(tf, "_ROOT", str(tmp_path))
    calls = []
    def fetch(url, *a, **k):
        calls.append(url)
        return {"005930": "00126380"}
    monkeypatch.setattr(tf, "_fetch_json", fetch)
    origins = {}
    token = tf._LOCAL_ORIGINS.set(origins)
    try:
        assert tf._load_local("data/mapping.json") == {"005930": "00126380"}
        assert origins["data/mapping.json"] == calls[0]
        for forbidden in ("data/recommendations.json", "data/portfolio.json", "../.env", "data/analyst_reports.json"):
            assert tf._load_local(forbidden) is None
        assert len(calls) == 1
    finally:
        tf._LOCAL_ORIGINS.reset(token)


def test_local_file_precedes_remote_fallback(monkeypatch, tmp_path):
    monkeypatch.setattr(tf, "_ROOT", str(tmp_path))
    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "data/mapping.json").write_text('{"local": true}')
    monkeypatch.setattr(tf, "_fetch_json", lambda *a, **k: pytest.fail("existing file triggered network"))
    assert tf._load_local("data/mapping.json") == {"local": True}


def test_exhausted_collection_budget_stops_new_requests(monkeypatch):
    monkeypatch.setattr(tf.urllib.request, "urlopen", lambda *a, **k: pytest.fail("deadline ignored"))
    token = tf._REQUEST_DEADLINE.set(0)
    trace = []
    trace_token = tf._FETCH_TRACE.set(trace)
    try:
        assert tf._fetch_json("https://example.com/test") is None
        assert trace[-1]["reason"] == "budget_exhausted"
    finally:
        tf._REQUEST_DEADLINE.reset(token)
        tf._FETCH_TRACE.reset(trace_token)


def test_market_cap_uses_timestamped_quote_not_unknown_kis_value(isolated):
    isolated.setattr(tf, "_us_realtime", lambda *a: {"현재가": 999, "_asof": "collection-time"})
    isolated.setattr(tf, "_us_quote", lambda *a: {"현재가": 70, "_as_of": "2026-09-25T16:00:00-04:00"})
    isolated.setattr(us_filing_probe, "probe", lambda *a, **k: {"_capital": {"_basic": 100}, "자본구조": {}})
    used = []
    isolated.setattr(us_filing_probe, "market_cap_ladder", lambda cap, px: used.append(px) or ["fixture"])
    result = tf.collect("AAPL")
    assert used == [70]
    capital = next(s["data"]["자본구조"] for s in result["sections"] if s["source"].startswith("sec:"))
    assert any("2026-09-25T16:00:00-04:00" in k for k in capital)
