"""Offline-only US source lifecycle, with real tracked SEC parser/validation."""
import copy
from datetime import datetime, timedelta, timezone
import importlib.util
import json
import os
from pathlib import Path
import socket
from types import SimpleNamespace
import urllib.error

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("test_us_sources", ROOT / "api/collectors/company_structure_us_refresh.py")
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)
NOW = datetime(2026, 10, 22, tzinfo=timezone.utc)
TABLE = b'<table><tr><td>Name*</td><td></td><td>Jurisdiction of incorporation</td></tr><tr><td>Alpha Inc</td><td></td><td>Delaware</td></tr></table>'
INDEX = b'<table class="tableFile"><tr><th>Document</th><th>Type</th></tr><tr><td><a href="ex21.htm">ex21.htm</a></td><td>EX-21</td></tr></table>'


@pytest.fixture(autouse=True)
def _isolate_data_dir(monkeypatch):
    # Avoid root conftest's trading/config imports; fail on actual network/keys.
    monkeypatch.setattr(socket.socket, "connect", lambda *args: pytest.fail("real network attempted"))
    original = os.environ.get

    def get(key, *args):
        if key.endswith(("API_KEY", "ACCESS_TOKEN")):
            pytest.fail("credential read attempted")
        return original(key, *args)

    monkeypatch.setattr(os.environ, "get", get)
    yield


def submission(cik, ticker, accession=None):
    return {"cik": int(cik), "tickers": [ticker], "name": "Public Company Inc",
            "privateContact": "DO_NOT_PERSIST_PERSON", "filings": {"recent": {
                "form": ["10-K"], "filingDate": ["2026-03-01"], "reportDate": ["2025-12-31"],
                "accessionNumber": [accession or cik + "-26-000001"], "primaryDocument": ["annual.htm"]}}}


def catalog(tmp_path, count=1, cached=False):
    data = tmp_path / "data"
    data.mkdir(exist_ok=True)
    stocks, mapping = [], {}
    for i in range(1, count + 1):
        ticker, cik = f"T{i}", f"{i:010d}"
        stocks.append({"ticker": ticker, "market": "US", "name": "Company Inc"})
        mapping[ticker] = cik
        if cached:
            path = data / "sec_submissions_cache" / ("CIK" + cik + ".json")
            core.atomic_json(path, submission(cik, ticker))
            os.utime(path, (NOW.timestamp(), NOW.timestamp()))
    core.atomic_json(data / "universe_search.json", {"stocks": stocks})
    core.atomic_json(data / "sec_ticker_cik_map.json", mapping)
    return core.build_document(tmp_path, now=NOW)


def run(doc, tmp_path, replies=None, now=NOW, limit=100):
    helpers = core.load_helpers()
    pending, calls, saves, clock = iter(replies or []), [], [], [0.0]

    def transport(url, maximum):
        assert maximum == core.MAX_BYTES
        calls.append((url, clock[0]))
        result = next(pending)
        if isinstance(result, Exception):
            raise result
        return result

    def sleep(seconds):
        clock[0] += seconds

    helpers.get_public = transport
    result, summary = core.refresh(doc, source_dir=tmp_path, limit=limit, fetch_public=True, now=now,
                                  helpers=helpers, checkpoint=lambda d: saves.append(copy.deepcopy(d)),
                                  clock=lambda: clock[0], sleep=sleep)
    assert len(calls) == summary["requests"]
    assert all(b[1] - a[1] >= .5 for a, b in zip(calls, calls[1:]))
    assert "DO_NOT_PERSIST_PERSON" not in json.dumps((result, saves))
    return result, summary, calls, saves


def test_universe_cik_dedupe_and_dry_cli_no_transport(tmp_path, monkeypatch):
    catalog(tmp_path)
    core.atomic_json(tmp_path / "data/universe_search.json", {"stocks": [
        {"ticker": t, "market": m} for t, m in (("T1", "US"), ("ALIAS", "US"), ("MISSING", "US"), ("KR", "KR"))]})
    core.atomic_json(tmp_path / "data/sec_ticker_cik_map.json", {"T1": "0000000001", "ALIAS": "0000000001"})
    doc = core.build_document(tmp_path, now=NOW)
    assert doc["issuers"]["0000000001"]["tickerAliases"] == ["ALIAS", "T1"]
    monkeypatch.setattr(core, "load_helpers", lambda: pytest.fail("dry imported helpers"))
    _, summary = core.refresh(doc, source_dir=tmp_path, now=NOW)
    assert summary["requestedTickers"] == 3 and summary["requestedCiks"] == 1
    assert summary["requests"] == 0 and summary["sourceGap"] == 1
    assert summary["unmapped"] == {"MISSING": "source-gap:cik-missing"}
    cli = core._module(ROOT / "scripts/member-map/refresh-us-company-structure.py", "test_us_cli")
    store = tmp_path / "not-written.json"
    assert cli.run(cli.parse_args(["--source-dir", str(tmp_path), "--store", str(store)])) == 0
    assert not store.exists()
    with pytest.raises(SystemExit):
        cli.parse_args(["--url", "https://evil.invalid"])


def test_local_submissions_two_gets_and_checkpoint_before_get(tmp_path):
    doc = catalog(tmp_path, cached=True)
    result, summary, calls, saved = run(doc, tmp_path, [INDEX, TABLE])
    issuer = result["issuers"]["0000000001"]
    assert summary["success"] == 1 and len(calls) == 2
    assert issuer["exhibit"]["rows"][0]["name"] == "Alpha Inc"
    assert issuer["exhibit"]["rows"][0]["ownershipPct"] is None
    assert issuer["exhibit"]["rows"][0]["directOwnership"] == "unspecified"
    assert issuer["lastSuccessAt"] == issuer["metadataCheckedAt"] == NOW.isoformat()
    assert saved[0]["requestBudget"]["ciks"] == ["0000000001"]
    before_get = next(d for d in saved if d["requestBudget"]["requests"] == 1)
    assert "exhibit" not in before_get["issuers"]["0000000001"]


def test_missing_submissions_online_bootstrap_and_minimal_metadata(tmp_path):
    doc = catalog(tmp_path)
    result, summary, calls, saved = run(doc, tmp_path, [json.dumps(submission("0000000001", "T1")).encode(), INDEX, TABLE])
    assert summary["requests"] == 3 and summary["success"] == 1
    assert calls[0][0] == "https://data.sec.gov/submissions/CIK0000000001.json"
    issuer = result["issuers"]["0000000001"]
    assert issuer["metadataSource"] == "sec-submissions"
    assert issuer["filingMetadata"]["filed_date"] == "2026-03-01"
    assert issuer["metadataCheckedAt"] == NOW.isoformat()
    assert "tickers" not in json.dumps(issuer)
    core.atomic_json(tmp_path / "store.json", result)
    assert core.read_json(tmp_path / "store.json", maximum=None) == result


def test_same_accession_reuses_exhibit_and_stale_metadata_only_get(tmp_path):
    doc, _, _, _ = run(catalog(tmp_path), tmp_path, [json.dumps(submission("0000000001", "T1")).encode(), INDEX, TABLE])
    old = copy.deepcopy(doc["issuers"]["0000000001"])
    later = NOW + timedelta(days=8)
    result, summary, calls, _ = run(doc, tmp_path, [json.dumps(submission("0000000001", "T1")).encode()], now=later)
    assert summary["cached"] == 1 and len(calls) == 1
    issuer = result["issuers"]["0000000001"]
    assert issuer["exhibit"] == old["exhibit"] and issuer["lastSuccessAt"] == old["lastSuccessAt"]
    assert issuer["metadataCheckedAt"] == later.isoformat()
    _, again, calls, _ = run(result, tmp_path, [], now=later)
    assert again["requests"] == 0


def test_http_stop_errors_and_prior_exhibit_retention(tmp_path):
    doc = catalog(tmp_path, 2, cached=True)
    first, _, _, _ = run(doc, tmp_path, [INDEX, TABLE], limit=1)
    later = NOW + timedelta(days=8)
    # Keep old issuer first here to exercise failure retention deterministically.
    first["currentCiks"] = ["0000000001"]
    for code in (403, 429):
        error = urllib.error.HTTPError("https://www.sec.gov/", code, "blocked", {}, None)
        result, summary, calls, _ = run(first, tmp_path, [error], now=later)
        assert summary["stopReason"] == "HTTP" + str(code) and len(calls) == 1
        assert summary["exitCode"] == summary["sourceError"] == 1
        assert summary["retained"] == 1
        assert result["issuers"]["0000000001"]["exhibit"] == first["issuers"]["0000000001"]["exhibit"]
        assert result["issuers"]["0000000001"]["lastSuccessAt"] == NOW.isoformat()
    result, summary, _, _ = run(first, tmp_path, [TimeoutError()], now=later)
    assert summary["error"] == summary["retained"] == 1
    assert summary["exitCode"] == 1 and summary["stopReason"] == "source-error"


def test_daily_budgets_reservations_and_next_day_progress(tmp_path, monkeypatch):
    doc = catalog(tmp_path, 102)
    replies = []
    for i in range(1, 67):
        replies.extend([json.dumps(submission(f"{i:010d}", f"T{i}")).encode(), INDEX, TABLE])
    result, summary, calls, _ = run(doc, tmp_path, replies)
    assert summary["requests"] == len(calls) == 198 and summary["success"] == 66
    assert summary["dailyCiks"] <= 100 and summary["stopReason"] == "daily-http-budget"
    assert summary["exitCode"] == summary["sourceError"] == summary["error"] == 0
    assert summary["budgetDeferred"] == summary["deferred"] == 36
    # A second run never resets the day's reservations.
    _, again, calls, _ = run(result, tmp_path)
    assert again["requests"] == 0 and again["dailyRequests"] == 198
    assert again["exitCode"] == again["sourceError"] == 0
    later = NOW + timedelta(days=1)
    selected = core._selection(result, later, 100)
    assert selected[0] == "0000000068"  # Failed/reserved 67 moves behind never attempted.
    with pytest.raises(ValueError):
        core._selection(doc, NOW, 101)
    doc["requestBudget"] = {"day": NOW.astimezone(core.KST).date().isoformat(), "requests": 201, "ciks": []}
    with pytest.raises(ValueError):
        run(doc, tmp_path)
    doc["requestBudget"] = {"day": NOW.astimezone(core.KST).date().isoformat(), "requests": 0,
                            "ciks": [f"{i:010d}" for i in range(1, 101)]}
    _, capped, calls, _ = run(doc, tmp_path)
    assert capped["dailyCiks"] == 100 and capped["attempted"] == 0 and calls == []
    assert capped["stopReason"] == "daily-cik-budget" and capped["exitCode"] == 0
    cli = core._module(ROOT / "scripts/member-map/refresh-us-company-structure.py", "test_us_budget_cli")
    store = tmp_path / "cli-store.json"
    monkeypatch.setattr(cli.core, "refresh", lambda document, **kwargs: (document, summary))
    args = cli.parse_args(["--source-dir", str(tmp_path), "--store", str(store), "--fetch-public"])
    assert cli.run(args) == 0
    assert core.read_json(store)["summary"]["stopReason"] == "daily-http-budget"
    failed_summary = {**summary, "sourceError": 1, "error": 1, "stopReason": "source-error", "exitCode": 1}
    monkeypatch.setattr(cli.core, "refresh", lambda document, **kwargs: (document, failed_summary))
    assert cli.run(args) == 1
    assert core.read_json(store)["summary"]["sourceError"] == 1  # Durable before job-error exit.


def test_transport_policy_size_no_redirect_and_url_restriction(monkeypatch):
    calls = []

    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def read(self, maximum):
            calls.append(maximum)
            return b"{}"

    def opener(handler):
        with pytest.raises(ValueError, match="sec-redirect-rejected"):
            handler.redirect_request(None)
        def open(request, timeout):
            assert timeout == 30 and "gywns0126@gmail.com" in request.get_header("User-agent")
            assert request.get_header("Accept-encoding") is None
            return Response()
        return SimpleNamespace(open=open)

    monkeypatch.setattr(core.urllib.request, "build_opener", opener)
    assert core.get_public("https://data.sec.gov/submissions/CIK0000000001.json") == b"{}"
    assert calls == [core.MAX_BYTES + 1]
    for url in ("http://data.sec.gov/submissions/CIK0000000001.json", "https://evil.invalid/", "https://www.sec.gov/a?url=evil"):
        with pytest.raises(ValueError):
            core.get_public(url)
    with pytest.raises(ValueError):
        core.get_public("https://data.sec.gov/submissions/CIK0000000001.json", core.MAX_BYTES + 1)


def test_needs_review_multiple_tables_identity_gap_and_size(tmp_path):
    doc = catalog(tmp_path, cached=True)
    result, summary, _, _ = run(doc, tmp_path, [INDEX, TABLE + TABLE])
    issuer = result["issuers"]["0000000001"]
    assert issuer["reviewExhibit"]["status"] == "needs-review"
    assert "lastSuccessAt" not in issuer and "exhibit" not in issuer
    assert issuer["attemptStatus"] == "needs-review"
    # Same accession's review result is also cached, without falsely claiming success.
    result["requestBudget"]["day"] = "2026-10-21"
    _, cached, calls, _ = run(result, tmp_path)
    assert cached["cached"] == 1 and calls == []
    bad = submission("0000000001", "OTHER")
    core.atomic_json(tmp_path / "data/sec_submissions_cache/CIK0000000001.json", bad)
    os.utime(tmp_path / "data/sec_submissions_cache/CIK0000000001.json", (NOW.timestamp(), NOW.timestamp()))
    _, gap, calls, _ = run(doc, tmp_path)
    assert gap["sourceGap"] == 1 and calls == []
    assert gap["lists"]["sourceGap"][0]["reason"] == "source-gap:representative-ticker-missing"
    # Oversized transport response never reaches the exhibit parser/store.
    core.atomic_json(tmp_path / "data/sec_submissions_cache/CIK0000000001.json", submission("0000000001", "T1"))
    os.utime(tmp_path / "data/sec_submissions_cache/CIK0000000001.json", (NOW.timestamp(), NOW.timestamp()))
    result, failed, _, _ = run(doc, tmp_path, [INDEX, b"x" * (core.MAX_BYTES + 1)])
    assert failed["error"] == 1 and "exhibit" not in result["issuers"]["0000000001"]
    assert failed["sourceError"] == failed["exitCode"] == 1 and failed["stopReason"] == "source-error"
    amended = submission("0000000001", "T1")
    recent = amended["filings"]["recent"]
    for key, value in (("form", "10-K/A"), ("filingDate", "2026-03-02"), ("reportDate", "2025-12-31"),
                       ("accessionNumber", "0000000001-26-000002"), ("primaryDocument", "amended.htm")):
        recent[key].append(value)
    with pytest.raises(ValueError, match="amendment-needs-review"):
        core.latest_metadata("T1", "0000000001", amended)


def test_20f_form_forwarded_ex81_jurisdiction_and_budget(tmp_path):
    doc = catalog(tmp_path)
    foreign = submission("0000000001", "T1")
    foreign["filings"]["recent"]["form"] = ["20-F"]
    index = (INDEX.replace(b"ex21.htm", b"ex81.htm").replace(b"EX-21", b"EX-8.1")
             .replace(b"<th>Type</th>", b"<th>Type</th><th>Description</th>")
             .replace(b"<td>EX-8.1</td>", b"<td>EX-8.1</td><td>List of subsidiaries</td>"))
    result, summary, calls, _ = run(doc, tmp_path, [json.dumps(foreign).encode(), index, TABLE])
    assert summary["success"] == 1 and summary["requests"] == len(calls) == 3
    exhibit = result["issuers"]["0000000001"]["exhibit"]
    assert exhibit["url"].endswith("/ex81.htm")
    assert exhibit["rows"][0]["jurisdiction"] == "Delaware"
    assert exhibit["rows"][0]["ownershipPct"] is None
    assert exhibit["rows"][0]["directOwnership"] == "unspecified"
    # The same accession still suppresses re-downloading the EX-8.1 body.
    _, repeated, calls, _ = run(result, tmp_path)
    assert repeated["requests"] == 0 and calls == []
    # Neither index nor body VIE disclosures can be promoted to subsidiaries.
    for index_body, exhibit_body in ((index.replace(b"List of subsidiaries", b"Subsidiaries and variable interest entities"), TABLE),
                                    (index, b"<p>Consolidated affiliated entities</p>" + TABLE)):
        review, summary, calls, _ = run(doc, tmp_path, [json.dumps(foreign).encode(), index_body, exhibit_body])
        item = review["issuers"]["0000000001"]
        assert item["attemptStatus"] == "needs-review" and "lastSuccessAt" not in item and "exhibit" not in item
        assert summary["success"] == 0 and summary["sourceGap"] == 1 and len(calls) <= 3
