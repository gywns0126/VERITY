"""Regression tests for bounded US collection lanes and offline review replay."""
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
from types import SimpleNamespace
import urllib.error

import pytest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "company_structure_refresh_lanes", ROOT / "api/collectors/company_structure_us_refresh.py")
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)
parser_spec = importlib.util.spec_from_file_location(
    "company_structure_refresh_lanes_parser", ROOT / "api/intelligence/company_structure_sec.py")
parser = importlib.util.module_from_spec(parser_spec)
parser_spec.loader.exec_module(parser)

NOW = datetime(2026, 10, 22, tzinfo=timezone.utc)
TABLE = b"<table><tr><td>Name</td><td>Jurisdiction</td></tr><tr><td>Child Inc</td><td>Delaware</td></tr></table>"
INDEX = b"<table class='tableFile'><tr><th>Document</th><th>Type</th></tr><tr><td><a href='ex21.htm'>ex21.htm</a></td><td>EX-21</td></tr></table>"


@pytest.fixture(autouse=True)
def forbid_network_and_credentials(monkeypatch):
    monkeypatch.setattr(socket.socket, "connect", lambda *args: pytest.fail("real network attempted"))
    original = os.environ.get

    def guarded_get(key, *args):
        if key.endswith(("API_KEY", "ACCESS_TOKEN")):
            pytest.fail("credential read attempted")
        return original(key, *args)

    monkeypatch.setattr(os.environ, "get", guarded_get)


def submission(cik, ticker, accession=None, *, filed="2026-03-01", period="2025-12-31"):
    return {"cik": int(cik), "tickers": [ticker], "name": "Public Company Inc",
            "filings": {"recent": {"form": ["10-K"], "filingDate": [filed],
                "reportDate": [period], "accessionNumber": [accession or f"{cik}-26-000001"],
                "primaryDocument": ["annual.htm"]}}}


def catalog(tmp_path, count=1):
    data = tmp_path / "data"
    data.mkdir(exist_ok=True)
    stocks, mapping = [], {}
    cache = data / "sec_submissions_cache"
    cache.mkdir(exist_ok=True)
    for number in range(1, count + 1):
        ticker, cik = f"T{number}", f"{number:010d}"
        stocks.append({"ticker": ticker, "market": "US", "name": "Public Company Inc"})
        mapping[ticker] = cik
        path = cache / f"CIK{cik}.json"
        core.atomic_json(path, submission(cik, ticker))
        os.utime(path, (NOW.timestamp(), NOW.timestamp()))
    core.atomic_json(data / "universe_search.json", {"stocks": stocks})
    core.atomic_json(data / "sec_ticker_cik_map.json", mapping)
    return core.build_document(tmp_path, now=NOW)


def helpers(calls, parse_status="parsed", parser_calls=None, fail=None):
    parser_calls = [] if parser_calls is None else parser_calls

    def get_public(url, maximum):
        calls.append(url)
        if fail:
            failure = fail(url)
            if failure:
                raise failure
        assert maximum == core.MAX_BYTES
        return INDEX if url.endswith("-index.html") else TABLE

    def find_exhibit(index, *, cik, accession, form):
        assert index == INDEX
        assert form == "10-K"
        return (f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
                f"{accession.replace('-', '')}/ex21.htm")

    def latest_metadata(ticker, cik, body):
        recent = body["filings"]["recent"]
        i = recent["form"].index("10-K")
        accession = recent["accessionNumber"][i]
        return {"issuer_id": "US:" + ticker, "issuer_name": body["name"], "cik": cik,
                "accession": accession, "filed_date": recent["filingDate"][i],
                "period_end": recent["reportDate"][i], "form": recent["form"][i],
                "primary_document": recent["primaryDocument"][i],
                "url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
                       f"{accession.replace('-', '')}/annual.htm"}

    def parse_exhibit(raw, metadata):
        parser_calls.append((raw, copy.deepcopy(metadata)))
        value = {"schema": "sec-company-subsidiaries-v1", "cik": metadata["cik"],
                 "accession": metadata["accession"], "filedDate": metadata["filedDate"],
                 "periodEnd": metadata["periodEnd"], "url": metadata["url"],
                 "documentSha256": hashlib.sha256(raw).hexdigest(),
                 "parserRevision": parser.PARSER_REVISION, "status": parse_status,
                 "rows": [] if parse_status == "needs-review" else [{
                     "name": "Child Inc", "jurisdiction": "Delaware",
                     "ownershipPct": None, "directOwnership": "unspecified"}]}
        if parse_status == "needs-review":
            value["reviewReason"] = "fixture-review-hold"
        return value

    return SimpleNamespace(get_public=get_public, find_exhibit=find_exhibit,
                           latest_metadata=latest_metadata, parse_exhibit=parse_exhibit)


def refresh(doc, tmp_path, *, now=NOW, limit=100, parse_status="parsed", cache=None,
            fail=None, defer_reviews=False, parser_calls=None):
    calls, saves, elapsed = [], [], [0.0]
    result, summary = core.refresh(
        doc, source_dir=tmp_path, limit=limit, fetch_public=True, now=now,
        helpers=helpers(calls, parse_status, parser_calls, fail), raw_cache_dir=cache,
        defer_reviews=defer_reviews, checkpoint=lambda value: saves.append(copy.deepcopy(value)),
        clock=lambda: elapsed[0], sleep=lambda seconds: elapsed.__setitem__(0, elapsed[0] + seconds))
    return result, summary, calls, saves


def clear_daily_budget(doc):
    doc["requestBudget"] = {"day": "2000-01-01", "requests": 0, "ciks": []}


def seed_review(tmp_path, *, count=1, cache=None):
    doc = catalog(tmp_path, count)
    parsed, summary, calls, _ = refresh(doc, tmp_path, parse_status="needs-review", cache=cache)
    assert summary["sourceGap"] == count
    assert len(calls) == count * 2
    for issuer in parsed["issuers"].values():
        if issuer.get("reviewExhibit"):
            issuer["reviewExhibit"]["parserRevision"] = "prior-parser-revision"
    return parsed


def test_selection_interleaves_four_fresh_with_one_backlog_and_classifies_deferred_by_state(tmp_path):
    doc = catalog(tmp_path, 13)
    stale = (NOW - timedelta(days=10)).isoformat()
    metadata_helper = helpers([]).latest_metadata
    for number, issuer in enumerate(doc["issuers"].values(), 1):
        cik, ticker = f"{number:010d}", f"T{number}"
        # Model an already observed filing and matching cache mtime. Otherwise
        # the unobserved filing itself correctly promotes every issuer to fresh.
        issuer["filingMetadata"] = metadata_helper(ticker, cik, submission(cik, ticker))
        issuer["metadataCheckedAt"] = NOW.isoformat()
        assert not core._new_local_submission(issuer, tmp_path, NOW)
    backlog_statuses = ("needs-review", "source-gap", "error", "HTTP503", "attempting")
    for number, status in enumerate(backlog_statuses, 7):
        issuer = doc["issuers"][f"{number:010d}"]
        issuer.update(attemptStatus=status, attemptedAt=stale, checkedAt=stale)
        if status == "needs-review":
            issuer["reviewExhibit"] = {"status": "needs-review", "parserRevision": "old"}

    # A deferred issuer with a last-good exhibit rejoins ordinary work; a
    # deferred issuer carrying an unresolved review remains in the backlog.
    good_deferred = doc["issuers"]["0000000012"]
    good_deferred.update(attemptStatus="budget-deferred", attemptedAt=stale,
                         checkedAt=stale, lastSuccessAt=stale,
                         exhibit={"status": "parsed"})
    review_deferred = doc["issuers"]["0000000013"]
    review_deferred.update(attemptStatus="budget-deferred", attemptedAt=stale,
                           checkedAt=stale, reviewExhibit={"status": "needs-review"})

    selected = core._selection(doc, NOW, 5, defer_reviews=True)
    fresh_ids = {f"{number:010d}" for number in range(1, 7)} | {"0000000012"}
    backlog_ids = {f"{number:010d}" for number in range(7, 12)} | {"0000000013"}
    assert len(selected) == 5
    assert len(set(selected) & fresh_ids) == 4
    assert len(set(selected) & backlog_ids) == 1

    _, summary, _, _ = refresh(doc, tmp_path, limit=5, defer_reviews=True)
    assert summary["refreshLanes"]["fresh"]["selected"] == 4
    assert summary["refreshLanes"]["backlog"]["selected"] == 1
    assert summary["refreshLanes"]["fresh"]["attempted"] == 4
    assert summary["refreshLanes"]["backlog"]["attempted"] == 1


def test_parser_revision_reviews_cannot_starve_unseen_fresh_issuers(tmp_path):
    doc = catalog(tmp_path, 16)
    old = (NOW - timedelta(days=8)).isoformat()
    for number in range(9, 17):
        issuer = doc["issuers"][f"{number:010d}"]
        issuer.update(attemptStatus="needs-review", attemptedAt=old, checkedAt=old,
                      reviewExhibit={"status": "needs-review", "parserRevision": "old"})
    selected = core._selection(doc, NOW, 5, defer_reviews=False)
    assert len(selected) == 5
    assert sum(doc["issuers"][cik]["attemptStatus"] == "not-attempted" for cik in selected) == 4
    assert sum(doc["issuers"][cik]["attemptStatus"] == "needs-review" for cik in selected) == 1


def test_deferred_review_revision_change_alone_does_not_bypass_source_check_ttl(tmp_path):
    cache = tmp_path / "raw-cache"
    doc = seed_review(tmp_path, cache=cache)
    issuer = doc["issuers"]["0000000001"]
    issuer.update(checkedAt=NOW.isoformat(), attemptedAt=NOW.isoformat())
    # The parser revision is old, but defer_reviews routes parser work to the
    # independent offline replay lane rather than forcing a source check.
    selected = core._selection(doc, NOW + timedelta(hours=1), 10,
                               source_dir=tmp_path, defer_reviews=True)
    assert "0000000001" not in selected


def test_deferred_same_accession_review_reuses_cache_without_http_and_retains_last_good(tmp_path):
    cache = tmp_path / "raw-cache"
    doc = seed_review(tmp_path, cache=cache)
    issuer = doc["issuers"]["0000000001"]
    good = {"status": "parsed", "accession": issuer["filingMetadata"]["accession"],
            "rows": [{"name": "Previously verified Inc", "jurisdiction": "Delaware"}]}
    issuer["exhibit"] = copy.deepcopy(good)
    issuer["lastSuccessAt"] = (NOW - timedelta(days=20)).isoformat()
    issuer["checkedAt"] = (NOW - timedelta(days=8)).isoformat()
    issuer["reviewExhibit"]["parserRevision"] = "prior-parser-revision"
    clear_daily_budget(doc)
    parser_calls = []
    now = NOW + timedelta(hours=1)
    result, summary, calls, _ = refresh(
        doc, tmp_path, now=now, cache=cache, defer_reviews=True,
        parser_calls=parser_calls)
    updated = result["issuers"]["0000000001"]
    assert calls == []
    assert parser_calls == []
    assert updated["reviewExhibit"]["parserRevision"] == "prior-parser-revision"
    assert updated["exhibit"] == good
    assert updated["lastSuccessAt"] == issuer["lastSuccessAt"]
    assert summary["requests"] == 0


def _replace_local_submission(tmp_path, cik, ticker, accession, *, filed="2026-10-21", period="2026-09-30", mtime):
    path = tmp_path / "data" / "sec_submissions_cache" / f"CIK{cik}.json"
    core.atomic_json(path, submission(cik, ticker, accession, filed=filed, period=period))
    os.utime(path, (mtime.timestamp(), mtime.timestamp()))


def test_new_valid_local_filing_bypasses_ttl_and_fetches_new_accession(tmp_path):
    doc = catalog(tmp_path)
    old, _, _, _ = refresh(doc, tmp_path)
    issuer = old["issuers"]["0000000001"]
    assert issuer["exhibit"]["status"] == "parsed"
    old_accession = issuer["filingMetadata"]["accession"]
    changed_at = NOW + timedelta(minutes=30)
    _replace_local_submission(tmp_path, "0000000001", "T1", "0000000001-26-000002", mtime=changed_at)
    now = NOW + timedelta(hours=1)

    assert core._new_local_submission(issuer, tmp_path, now)
    selected = core._selection(old, now, 1, source_dir=tmp_path, defer_reviews=True)
    assert selected == ["0000000001"]
    clear_daily_budget(old)
    result, summary, calls, _ = refresh(old, tmp_path, now=now, defer_reviews=True)
    updated = result["issuers"]["0000000001"]
    assert updated["filingMetadata"]["accession"] != old_accession
    assert updated["exhibit"]["accession"] == "0000000001-26-000002"
    assert summary["success"] == 1
    assert summary["reviewReplayDeferred"] is True
    assert summary["refreshLanes"]["fresh"]["selected"] == 1
    assert summary["refreshLanes"]["fresh"]["attempted"] == 1
    assert len(calls) == 2
    assert all("/000000000126000002/" in url for url in calls)


def test_failure_on_changed_filing_retains_last_good_exhibit_and_success_clock(tmp_path):
    doc = catalog(tmp_path)
    good, _, _, _ = refresh(doc, tmp_path)
    issuer = good["issuers"]["0000000001"]
    old_exhibit = copy.deepcopy(issuer["exhibit"])
    old_success = issuer["lastSuccessAt"]
    _replace_local_submission(tmp_path, "0000000001", "T1", "0000000001-26-000002",
                              mtime=NOW + timedelta(minutes=30))
    clear_daily_budget(good)
    now = NOW + timedelta(hours=1)

    def fail_index(url):
        if url.endswith("-index.html"):
            return urllib.error.HTTPError(url, 503, "unavailable", {}, None)
        return None

    result, summary, calls, _ = refresh(good, tmp_path, now=now, defer_reviews=True, fail=fail_index)
    retained = result["issuers"]["0000000001"]
    assert len(calls) == 1
    assert retained["attemptStatus"] == "HTTP503"
    assert retained["exhibit"] == old_exhibit
    assert retained["lastSuccessAt"] == old_success
    assert summary["error"] == 1
    assert summary["retained"] == 1


def test_offline_replay_limit_checkpoints_and_continues_without_changing_request_budget(tmp_path):
    cache = tmp_path / "raw-cache"
    doc = seed_review(tmp_path, count=2, cache=cache)
    before_budget = copy.deepcopy(doc["requestBudget"])
    checkpoints = []
    parsed_calls = []
    parse_helpers = helpers([], "parsed", parsed_calls)
    replayed, summary = core.reparse_cached_reviews(
        doc, cache, now=NOW + timedelta(days=1), helpers=parse_helpers,
        limit=1, max_elapsed_seconds=120, clock=lambda: 0.0,
        checkpoint=lambda value: checkpoints.append(copy.deepcopy(value)))
    assert sum(item.get("attemptStatus") == "success" for item in replayed["issuers"].values()) == 1
    assert len(parsed_calls) == 1
    assert summary["stopReason"] == "replay-limit"
    assert summary["deferred"] == 1
    assert summary["cacheHits"] == 1
    assert checkpoints and checkpoints[-1] == replayed
    assert replayed["requestBudget"] == before_budget
    assert doc["requestBudget"] == before_budget
    assert sum(item.get("attemptStatus") == "needs-review" for item in replayed["issuers"].values()) == 1

    continued, _ = core.reparse_cached_reviews(
        replayed, cache, now=NOW + timedelta(days=1), helpers=parse_helpers,
        limit=1, max_elapsed_seconds=120, clock=lambda: 0.0)
    assert sum(item.get("attemptStatus") == "success" for item in continued["issuers"].values()) == 2
    assert continued["requestBudget"] == before_budget


def test_offline_replay_checkpoint_write_failure_propagates_and_stops_after_first_parse(tmp_path):
    cache = tmp_path / "raw-cache"
    doc = seed_review(tmp_path, count=2, cache=cache)
    before = copy.deepcopy(doc)
    parser_calls = []

    def fail_checkpoint(_value):
        raise OSError("checkpoint storage unavailable")

    with pytest.raises(OSError, match="checkpoint storage unavailable"):
        core.reparse_cached_reviews(
            doc, cache, now=NOW + timedelta(days=1),
            helpers=helpers([], "parsed", parser_calls), limit=2,
            max_elapsed_seconds=120, clock=lambda: 0.0,
            checkpoint=fail_checkpoint)

    assert len(parser_calls) == 1
    assert doc == before


def test_offline_replay_held_result_is_not_retried_while_next_stale_review_continues(tmp_path):
    cache = tmp_path / "raw-cache"
    doc = seed_review(tmp_path, count=2, cache=cache)
    held_cik, next_cik = "0000000001", "0000000002"

    first_calls = []
    held, first_summary = core.reparse_cached_reviews(
        doc, cache, now=NOW + timedelta(days=1),
        helpers=helpers([], "needs-review", first_calls), limit=1,
        max_elapsed_seconds=120, clock=lambda: 0.0)
    assert first_summary["held"] == 1
    assert held["issuers"][held_cik]["attemptStatus"] == "needs-review"
    assert held["issuers"][held_cik]["reviewExhibit"]["parserRevision"] == parser.PARSER_REVISION
    assert held["issuers"][next_cik]["reviewExhibit"]["parserRevision"] == "prior-parser-revision"

    next_calls = []
    continued, second_summary = core.reparse_cached_reviews(
        held, cache, now=NOW + timedelta(days=1),
        helpers=helpers([], "parsed", next_calls), limit=1,
        max_elapsed_seconds=120, clock=lambda: 0.0)
    assert second_summary["eligible"] == 1
    assert second_summary["parsed"] == 1
    assert next_calls[0][1]["cik"] == next_cik
    assert continued["issuers"][held_cik]["attemptStatus"] == "needs-review"
    assert continued["issuers"][next_cik]["attemptStatus"] == "success"


@pytest.mark.parametrize(("argument", "value"), [
    ("limit", core.MAX_REPLAY_CIKS + 1),
    ("max_elapsed_seconds", core.MAX_REPLAY_SECONDS + 1),
])
def test_offline_replay_rejects_values_over_configured_bounds(tmp_path, argument, value):
    kwargs = {argument: value}
    expected = "sec-replay-limit-invalid" if argument == "limit" else "sec-replay-time-budget-invalid"
    with pytest.raises(ValueError, match=expected):
        core.reparse_cached_reviews(
            {"issuers": {}, "currentCiks": []}, tmp_path,
            **kwargs)


def test_offline_replay_zero_time_does_not_invoke_parser_or_mutate_input(tmp_path):
    cache = tmp_path / "raw-cache"
    doc = seed_review(tmp_path, cache=cache)
    before = copy.deepcopy(doc)
    parser_calls = []
    replayed, summary = core.reparse_cached_reviews(
        doc, cache, now=NOW + timedelta(days=1), helpers=helpers([], "parsed", parser_calls),
        limit=160, max_elapsed_seconds=0, clock=lambda: 0.0)
    assert parser_calls == []
    assert replayed == before
    assert doc == before
    assert summary["stopReason"] == "time-budget"
    assert summary["deferred"] == 1


def test_public_cli_defers_review_parsing_to_offline_lane(tmp_path, monkeypatch):
    doc = catalog(tmp_path)
    store = tmp_path / "sources.json"
    core.atomic_json(store, doc)
    cli = core._module(ROOT / "scripts/member-map/refresh-us-company-structure.py", "refresh_lanes_cli")
    received = {}

    def fake_refresh(document, **kwargs):
        received.update(kwargs)
        return copy.deepcopy(document), {"dryRun": False, "exitCode": 0}

    monkeypatch.setattr(cli.core, "refresh", fake_refresh)
    args = cli.parse_args(["--source-dir", str(tmp_path), "--store", str(store), "--fetch-public"])
    assert cli.run(args) == 0
    assert received.get("defer_reviews") is True


def test_workflow_runs_public_fetch_before_bounded_offline_replay():
    workflow = (ROOT / ".github/workflows/ownership_backfill.yml").read_text()
    fetch_at = workflow.index("--limit 800 --fetch-public")
    replay_at = workflow.index("--replay-cached")
    assert fetch_at < replay_at
