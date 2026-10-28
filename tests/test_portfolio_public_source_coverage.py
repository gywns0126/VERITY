"""Selected-scope availability receipts; synthetic inputs, no collection or IO."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import socket

import pytest
from tests.test_portfolio_prepared_projection import engine as prepared_engine, _canonical, _seed


ROOT = Path(__file__).resolve().parents[1]
MODULES = (
    "api/intelligence/portfolio_public_sources.py",
    "vercel-api/api/portfolio_core/portfolio_public_sources.py",
)
KR = "KR:111111"
US = "US:SYNTH"
FILED = "2025-03-12"
GENERATED = "2025-06-04T15:00:00+09:00"
OBSERVED = "2025-06-03T12:00:00+09:00"


@pytest.fixture(params=MODULES)
def sources(request, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("coverage must not collect source data")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    spec = importlib.util.spec_from_file_location("coverage_sources_test", ROOT / request.param)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fact(**changes):
    return {"metric": "revenue", "value": 0, "unit": "KRW",
            "as_of": "2024", "source": "DART", **changes}


def filing(**changes):
    return {"title": "Synthetic annual filing", "date": FILED,
            "source_url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20250312000001",
            **changes}


def report(row):
    return {"stock_report_public.json": {
        "_meta": {"generated_at": GENERATED}, "stocks": {"111111": row}}}


def receipt(sources, docs, identifier=KR, filename="stock_report_public.json"):
    result = sources.project_public_source_coverage(docs, [identifier])
    return next(row for row in result["receipts"] if row["source_file"] == filename)


def collection(status):
    completed = status != "running"
    group_status = "failed" if status == "failed" else "success"
    groups = [{"corp_cls": "Y", "pblntf_ty": kind, "pages_attempted": 1,
               "pages_succeeded": int(group_status == "success"),
               "status": group_status, "total_pages": 0, "failure": None}
              for kind in ("B", "C", "D", "I")]
    if status == "partial":
        groups[0].update(status="failed", pages_succeeded=0)
    return {"schema_version": 1, "endpoint": "list.json", "status": status,
            "attempted_at": "2025-06-03T11:59:00+09:00",
            "completed_at": OBSERVED if completed else None,
            "successful_checked_at": OBSERVED if status == "success" else None,
            "scope": {"corp_cls": ["Y"], "pblntf_ty": ["B", "C", "D", "I"],
                      "requires_stock_code": True},
            "max_pages_per_group": 20, "groups_expected": 4,
            "groups_completed": sum(group["status"] == "success" for group in groups),
            "pages_attempted": 4,
            "pages_succeeded": sum(group["pages_succeeded"] for group in groups),
            "groups": groups}


@pytest.mark.parametrize("row,status,reason", [
    ({}, "not-collected", "company-payload-not-supplied"),
    ({"facts": [], "fin_series": [], "disclosures": []}, "empty", "explicit-empty-company-payload"),
    ({"facts": [fact()]}, "available", "payload-present"),
    ({"facts": [fact(), fact(unit="invalid")]}, "partial", "payload-partly-rejected"),
    ({"facts": [fact(unit="invalid")]}, "partial", "payload-rejected"),
    ({"fin_series": [{"year": 2024}]}, "partial", "payload-rejected"),
    ({"facts": [fact(source="untrusted")]}, "error", "company-payload-rejected"),
    ({"disclosures": {}}, "error", "company-payload-rejected"),
])
def test_distinguishes_evidence_states(sources, row, status, reason):
    result = receipt(sources, report(row))
    assert (result["status"], result["reason"]) == (status, reason)
    assert result["matched_rows"] == 1


def test_publication_fiscal_and_artifact_dates_are_separate(sources):
    result = receipt(sources, report({"facts": [fact()], "disclosures": [filing()]}))
    assert result["data_dates"] == ["2024"]  # No invented year-end date.
    assert result["publication_dates"] == [FILED]
    assert result["artifact_generated_at"] == GENERATED
    assert result["observed_at"] is None
    assert result["accepted_records"] == result["input_records"] == 2


def test_unknown_selected_company_stays_in_receipts_and_loaded_denominator(sources):
    docs = {"universe_search.json": {"stocks": [
        {"market": "KR", "ticker": "111111", "name": "Synthetic"},
        {"market": "US", "ticker": "SYNTH", "name": "Synthetic"},
        {"market": "US", "ticker": "OTHER", "name": "Unselected"}]},
        **report({"facts": [fact()]})}
    result = sources.project_public_source_coverage(docs, [KR, US, "US:UNKNOWN", KR])
    assert result["selected_companies"] == 3
    assert result["receipt_count"] == len(result["receipts"]) == 10
    assert result["loaded_sources"] == sorted(docs)
    assert sum(result["status_counts"].values()) == 10
    assert all(row["status"] == "not-collected" for row in result["receipts"]
               if row["company_id"] == "US:UNKNOWN")
    assert "US:OTHER" not in {row["company_id"] for row in result["receipts"]}
    assert result["scope"] == "selected-companies-in-loaded-sources"
    assert result["accuracy_verified"] is False


def test_empty_feed_does_not_claim_unknown_issuer_was_collected(sources):
    result = receipt(sources, {"us_disclosure_feed.json": {"items": []}},
                     "US:UNKNOWN", "us_disclosure_feed.json")
    assert result["status"] == "not-collected"
    assert result["reason"] == "no-company-row-in-loaded-scope"


@pytest.mark.parametrize("status,expected", [
    ("success", "available"), ("partial", "partial"), ("failed", "error"), ("running", "partial"),
])
def test_collection_receipt_is_feed_scoped_and_keeps_retained_filing(sources, status, expected):
    docs = {"public_disclosure_feed.json": {
        "_meta": {"generated_at": GENERATED, "source_collection": collection(status)},
        "items": [{"ticker": "111111", "name": "Synthetic", "disclosures": [filing()]}]}}
    result = receipt(sources, docs, filename="public_disclosure_feed.json")
    assert result["status"] == expected
    assert result["publication_dates"] == [FILED]
    assert result["collection_scope"] == "feed-query-groups"
    assert result["observed_at"] == (OBSERVED if status == "success" else None)
    assert result["artifact_generated_at"] == GENERATED
    assert result["accepted_records"] == 1


def test_invalid_collection_metadata_does_not_claim_observation_or_error(sources):
    docs = {"public_disclosure_feed.json": {
        "_meta": {"source_collection": {"status": "failed", "error": "private-canary"}},
        "items": [{"ticker": "111111", "disclosures": []}]}}
    result = receipt(sources, docs, filename="public_disclosure_feed.json")
    assert result["status"] == "empty"
    assert result["collection_status"] == "unknown"
    assert result["observed_at"] is None
    assert "private-canary" not in json.dumps(result)


def test_partial_feed_cannot_hide_invalid_selected_payload(sources):
    docs = {"public_disclosure_feed.json": {
        "_meta": {"source_collection": collection("partial")},
        "items": [{"ticker": "111111", "disclosures": "private-canary"}]}}
    result = receipt(sources, docs, filename="public_disclosure_feed.json")
    assert result["status"] == "error"
    assert result["reason"] == "company-payload-rejected"
    assert result["collection_status"] == "partial"


def test_malformed_loaded_source_is_error_and_does_not_reflect_values(sources):
    result = receipt(sources, {"stock_report_public.json": {"stocks": "private-canary"}})
    assert result["status"] == "error"
    assert result["reason"] == "source-shape-rejected"
    assert "private-canary" not in json.dumps(result)


@pytest.mark.parametrize("truncated,expected", [(False, "available"), (True, "partial")])
def test_existing_overview_excerpt_schema_and_dates(sources, truncated, expected):
    text = "Synthetic issuer makes components."
    docs = {"kr_business_overview_public.json": {
        "_meta": {"generated_at": GENERATED, "count": 1},
        "rows": {"111111": {"name": "Synthetic", "text": text, "chars": len(text),
                            "fiscal_year": "2024", "filed_at": "20250312",
                            "report": "Annual report", "url": filing()["source_url"],
                            "truncated": truncated}}}}
    result = receipt(sources, docs, filename="kr_business_overview_public.json")
    assert result["status"] == expected
    assert result["publication_dates"] == [FILED]
    assert result["data_dates"] == ["2024"]
    assert result["observed_at"] is None


@pytest.mark.parametrize("count", [0, 2, True, None])
def test_overview_metadata_is_not_repaired_to_claim_availability(sources, count):
    docs = {"kr_business_overview_public.json": {
        "_meta": {"generated_at": GENERATED, "count": count},
        "rows": {"111111": {"name": "Synthetic"}}}}
    result = receipt(sources, docs, filename="kr_business_overview_public.json")
    assert result["status"] == "error"
    assert result["reason"] == "source-shape-rejected"


def test_existing_projection_and_inputs_are_unchanged(sources):
    docs = {"universe_search.json": {"stocks": [
        {"ticker": "111111", "market": "KR", "name": "Synthetic"}]},
        **report({"name": "Synthetic", "facts": [fact()], "disclosures": [filing()]})}
    original = deepcopy(docs)
    before = sources.project_public_sources(docs)
    result = sources.project_public_source_coverage(docs, [KR, "US:UNKNOWN"])
    result["receipts"][0]["publication_dates"].append("2000-01-01")
    assert sources.project_public_sources(docs) == before
    assert docs == original
    assert len(before["companies"]) == 1


def test_unassessed_sources_are_explicit(sources):
    result = sources.project_public_source_coverage({"macro_snapshot.json": {}}, [])
    assert result["unassessed_loaded_sources"] == ["macro_snapshot.json"]
    assert result["receipts"] == []
    assert result["selected_companies"] == result["receipt_count"] == 0


@pytest.mark.parametrize("selection", ["KR:111111", ["KR:bad"], ["US:bad/identity"], [None],
                                       ["US:A"] * 31])
def test_selection_boundary_rejects_raw_or_invalid_identity(sources, selection):
    with pytest.raises(sources.PublicSourceError, match="public coverage selection rejected"):
        sources.project_public_source_coverage({}, selection)


def test_source_allowlist_is_preserved(sources):
    with pytest.raises(sources.PublicSourceError, match="public source set rejected"):
        sources.project_public_source_coverage({"private.json": {}}, [KR])


def sec_filing(**changes):
    return {"title": "Synthetic amended current report", "label": "8-K/A",
            "is_correction": True, "date": FILED, "filing_date": FILED,
            "report_date": "2024-12-31", "acceptance_datetime": "2025-03-12T23:15:00Z",
            "cik": "0000000123", "accession_number": "0000000001-25-000001",
            "primary_document": "report.htm",
            "source_url": "https://www.sec.gov/Archives/edgar/data/123/000000000125000001/report.htm",
            "item_codes": ["2.02", "8.01"], **changes}


def us_feed():
    groups = {"processed": ["SYNTH", "EMPTY"], "empty": ["EMPTY"],
              "unavailable": ["FAILED"], "unresolved": ["MISSING"],
              "unprocessed": ["DEFER"], "carry_forward": ["FAILED", "MISSING", "DEFER", "RETAINED"]}
    return {"_meta": {"generated_at": GENERATED, "source_collection": {
        "endpoint": "https://data.sec.gov/submissions/CIK{cik10}.json",
        "scope": "submissions.filings.recent; excludes ticker-map request and historical files",
        "status": "partial", "attempted_at": "2025-06-03T11:59:00+09:00",
        "completed_at": OBSERVED, "successful_checked_at": None,
        "requests": 3, "requests_succeeded": 2, "requests_failed": 1, "reused_cik_tickers": 0,
        "universe_n": 5, "processed_n": 2, "empty_n": 1, "unavailable_n": 1,
        "unresolved_n": 1, "deferred_n": 1, "universe_complete": False,
        "whole_market_coverage": False}},
        "_coverage": {"universe_n": 5, **{name + "_tickers": rows for name, rows in groups.items()}},
        "items": [{"ticker": ticker, "name": "Synthetic", "disclosures": [sec_filing()]}
                  for ticker in ("SYNTH", "FAILED", "MISSING", "DEFER", "RETAINED")]}


def test_sec_receipt_separates_checked_empty_error_deferred_and_retained(sources):
    feed = us_feed()
    expected = {"SYNTH": "available", "EMPTY": "empty", "FAILED": "error",
                "MISSING": "not-collected", "DEFER": "partial", "RETAINED": "partial",
                "UNKNOWN": "not-collected"}
    result = sources.project_public_source_coverage(
        {"us_disclosure_feed.json": feed}, ["US:" + ticker for ticker in expected])
    by_ticker = {row["company_id"][3:]: row for row in result["receipts"]
                 if row["source_file"] == "us_disclosure_feed.json"}
    assert {ticker: row["status"] for ticker, row in by_ticker.items()} == expected
    assert by_ticker["EMPTY"]["reason"] == "checked-empty-recent-filings"
    assert by_ticker["EMPTY"]["matched_rows"] == 0
    assert by_ticker["FAILED"]["accepted_records"] == 1  # Retained facts survive a failed refresh.
    assert by_ticker["SYNTH"]["data_dates"] == ["2024-12-31"]
    assert by_ticker["SYNTH"]["publication_dates"] == [FILED]
    for row in by_ticker.values():
        assert row["observed_at"] is None
        assert row["collection_checked_at"] is None
        assert row["collection_status"] == "partial"
        assert row["collection_completed_at"] == OBSERVED
        assert row["artifact_generated_at"] == GENERATED


def test_sec_complete_batch_clock_is_not_issuer_observation(sources):
    feed = us_feed()
    check = feed["_meta"]["source_collection"]
    check.update(status="success", successful_checked_at=OBSERVED, requests=2,
                 requests_failed=0, universe_n=2, unavailable_n=0, unresolved_n=0,
                 deferred_n=0, universe_complete=True)
    feed["_coverage"].update(universe_n=2, unavailable_tickers=[], unresolved_tickers=[],
                             unprocessed_tickers=[], carry_forward_tickers=[])
    feed["items"] = feed["items"][:1]
    result = receipt(sources, {"us_disclosure_feed.json": feed}, US, "us_disclosure_feed.json")
    assert result["status"] == "available"
    assert result["issuer_collection_status"] == "processed"
    assert result["collection_checked_at"] == OBSERVED
    assert result["observed_at"] is None


@pytest.mark.parametrize("corruption", ["counts", "overlap", "future", "inverted", "naive", "prior-success"])
def test_invalid_sec_receipt_cannot_certify_current_issuer_check(sources, corruption):
    feed = us_feed()
    check = feed["_meta"]["source_collection"]
    if corruption == "counts":
        check["processed_n"] = 99
    elif corruption == "overlap":
        feed["_coverage"]["unavailable_tickers"] = ["SYNTH"]
    elif corruption == "future":
        check["completed_at"] = "2100-01-01T00:00:00Z"
    elif corruption == "inverted":
        check["attempted_at"] = GENERATED
    elif corruption == "naive":
        check["completed_at"] = "2025-06-03T12:00:00"
    else:
        check["successful_checked_at"] = OBSERVED
    result = receipt(sources, {"us_disclosure_feed.json": feed}, US, "us_disclosure_feed.json")
    assert result["collection_status"] == result["issuer_collection_status"] == "unknown"
    assert result["collection_checked_at"] is result["observed_at"] is None
    assert result["status"] == "available"  # Only the actual payload is known.


def test_generated_at_alone_does_not_claim_sec_source_check(sources):
    feed = us_feed()
    del feed["_meta"]["source_collection"]
    result = receipt(sources, {"us_disclosure_feed.json": feed}, US, "us_disclosure_feed.json")
    assert result["observed_at"] is None
    assert "issuer_collection_status" not in result
    assert result["artifact_generated_at"] == GENERATED


def test_sources_are_traversed_once_for_thirty_selected_companies(sources, monkeypatch):
    class OnceList(list):
        calls = 0

        def __iter__(self):
            self.calls += 1
            assert self.calls == 1, "source container was traversed more than once"
            return super().__iter__()

    class OnceDict(dict):
        calls = 0

        def items(self):
            self.calls += 1
            assert self.calls == 1, "source container was traversed more than once"
            return super().items()

    def forbidden(*args, **kwargs):
        raise AssertionError("coverage must not reproject a full catalog")

    monkeypatch.setattr(sources, "project_public_sources", forbidden)
    rows = [{"market": "US", "ticker": f"T{i}", "name": "Synthetic", "facts": []}
            for i in range(2000)]
    values = [OnceList(rows), OnceList(), OnceList(rows), OnceList(), OnceList(), OnceDict()]
    documents = {name: {field: value} for (name, field, _, _), value in
                 zip(sources._COMPANY_COVERAGE_SOURCES, values)}
    documents["kr_business_overview_public.json"]["_meta"] = {"count": 0, "generated_at": GENERATED}
    result = sources.project_public_source_coverage(documents, [f"US:T{i}" for i in range(30)])
    assert result["selected_companies"] == 30
    assert all(value.calls == 1 for value in values)


def test_sec_amendment_item_codes_and_closed_filing_metadata_preserve_id(sources):
    raw = sec_filing(owner_id="private-canary", acceptance_time_note="private-canary")
    projected = sources._disclosure(raw, "SEC")
    assert projected["id"] == "SEC:123:000000000125000001:report.htm"
    assert projected["item_codes"] == ["2.02", "8.01"]
    assert tuple(projected["filing"]) == sources.PUBLIC_SEC_FILING_FIELDS
    assert projected["filing"] == {
        "form": "8-K/A", "is_correction": True, "cik": "123",
        "accession_number": "0000000001-25-000001", "primary_document": "report.htm",
        "filing_date": FILED, "report_date": "2024-12-31",
        "acceptance_datetime": "2025-03-12T23:15:00Z"}
    assert "private-canary" not in json.dumps(projected)
    assert sources._disclosure({key: value for key, value in raw.items()
                                if key not in ("cik", "accession_number")}, "SEC")["id"] == projected["id"]


@pytest.mark.parametrize("field,value", [
    ("cik", "456"), ("cik", 123), ("cik", True),
    ("accession_number", "0000000001-25-000002"),
    ("primary_document", "other.htm"), ("primary_document", "../report.htm"),
    ("filing_date", "2025-03-13"), ("filing_date", None),
    ("report_date", "2025-03-13"), ("report_date", 2024),
    ("acceptance_datetime", "2025-03-12T12:00:00"),
    ("acceptance_datetime", "2100-01-01T00:00:00Z"),
    ("is_correction", False), ("is_correction", 1), ("label", "Untrusted"),
])
def test_invalid_optional_filing_metadata_does_not_remove_legacy_document(sources, field, value):
    projected = sources._disclosure(sec_filing(**{field: value}), "SEC")
    assert projected is not None
    assert projected["id"] == "SEC:123:000000000125000001:report.htm"
    assert "filing" not in projected


def test_missing_primary_document_requires_exact_accession_index(sources):
    raw = sec_filing(primary_document="", report_date="", acceptance_datetime="",
                     source_url="https://www.sec.gov/Archives/edgar/data/123/000000000125000001/0000000001-25-000001-index.html")
    filing = sources._disclosure(raw, "SEC")["filing"]
    assert filing["primary_document"] is filing["report_date"] is filing["acceptance_datetime"] is None
    assert "filing" not in sources._disclosure(sec_filing(primary_document=""), "SEC")


@pytest.mark.parametrize("use_base", [False, True])
@pytest.mark.parametrize("mode", ["enrich", "date-conflict", "existing-filing", "duplicate-conflict"])
def test_report_feed_dedup_enriches_only_missing_nonconflicting_filing(sources, use_base, mode):
    if use_base and "_base_companies" not in (sources.project_public_sources.__kwdefaults__ or {}):
        pytest.skip("only the Vercel implementation supports a prepared base")
    original = sec_filing(title="Original report title")
    for key in ("is_correction", "cik", "accession_number", "primary_document",
                "filing_date", "report_date", "acceptance_datetime", "item_codes"):
        original.pop(key)
    if mode == "existing-filing":
        original = sec_filing(title="Original report title", report_date="2024-06-30")
    report_docs = {"us_stock_report_public.json": {"stocks": {
        "SYNTH": {"name": "Synthetic", "disclosures": [original]}}}}
    base = sources.project_public_sources(deepcopy(report_docs))["companies"]
    old_document = deepcopy(base[0]["documents"][0])
    feed_disclosures = [sec_filing()]
    if mode == "date-conflict":
        feed_disclosures[0].update(date="2025-03-13", filing_date="2025-03-13")
    elif mode == "duplicate-conflict":
        feed_disclosures.append(sec_filing(report_date="2024-09-30"))
    documents = {**report_docs, "us_disclosure_feed.json": {"items": [
        {"ticker": "SYNTH", "disclosures": feed_disclosures}]}}
    result = sources.project_public_sources(documents, **({"_base_companies": base} if use_base else {}))
    projected = result["companies"][0]["documents"]
    assert len(projected) == 1
    assert {key: projected[0][key] for key in old_document} == old_document
    if mode == "enrich":
        assert projected[0]["filing"] == sources._disclosure(sec_filing(), "SEC")["filing"]
    elif mode != "existing-filing":
        assert "filing" not in projected[0]


def legacy_sec_report():
    original = sec_filing(title="Original report title")
    for key in ("is_correction", "cik", "accession_number", "primary_document",
                "filing_date", "report_date", "acceptance_datetime", "item_codes"):
        original.pop(key)
    return {"universe_search.json": {"stocks": [
                {"ticker": "SYNTH", "market": "US", "name": "Synthetic"}]},
            "stock_report_public.json": {"stocks": {}},
            "us_stock_report_public.json": {"stocks": {
                "SYNTH": {"name": "Synthetic", "disclosures": [original]}}}}


def test_enrichment_copies_document_instead_of_mutating_original(sources, monkeypatch):
    originals = []
    disclose = sources._disclosure

    def capture(raw, source):
        projected = disclose(raw, source)
        if raw["title"] == "Original report title":
            originals.append(projected)
        return projected

    monkeypatch.setattr(sources, "_disclosure", capture)
    documents = {**legacy_sec_report(), "us_disclosure_feed.json": {
        "items": [{"ticker": "SYNTH", "disclosures": [sec_filing()]}]}}
    projected = sources.project_public_sources(documents)["companies"][0]["documents"][0]
    assert len(originals) == 1 and projected is not originals[0]
    assert "filing" not in originals[0]
    assert {key: projected[key] for key in originals[0]} == originals[0]
    assert projected["filing"]["form"] == "8-K/A"


@pytest.mark.parametrize("next_feed", ["remove", "change"])
def test_prepared_base_feed_add_then_remove_or_change_matches_cold(prepared_engine, next_feed):
    engine = prepared_engine
    documents = legacy_sec_report()
    helper, _sources, artifact, receipt, revision = _seed(engine, documents)
    expected_template = _canonical(helper.checked_base_projection(artifact, receipt, revision))
    artifact_before = _canonical(artifact)
    engine._reset_projection_cache_for_tests()

    def prepare(bundle, digest):
        return engine.prepare_public_index(bundle, digest * 64,
            prepared_business_index=artifact, publisher_receipt=receipt,
            base_source_revision=revision)

    added = {**documents, "us_disclosure_feed.json": {
        "items": [{"ticker": "SYNTH", "disclosures": [sec_filing()]}]}}
    first = prepare(added, "a")
    assert first["by_id"][US]["documents"][0]["filing"]["form"] == "8-K/A"
    template_after_add = _canonical(engine._PROJECTED_PUBLIC_INDEX._base_template)
    following = deepcopy(documents)
    if next_feed == "change":
        following["us_disclosure_feed.json"] = {"items": [{
            "ticker": "SYNTH", "disclosures": [sec_filing(report_date="2024-09-30")]}]}
    warm = _canonical(prepare(following, "b"))
    positions = [{"market": "US", "ticker": "SYNTH"}]
    warm_response = _canonical(engine.analyze_portfolio(
        positions, following, public_bundle_revision="b" * 64))
    assert _canonical(engine._PROJECTED_PUBLIC_INDEX._base_template) == expected_template
    engine._reset_projection_cache_for_tests()
    cold = _canonical(prepare(following, "b"))
    assert warm == cold
    assert _canonical(engine.analyze_portfolio(
        positions, following, public_bundle_revision="b" * 64)) == warm_response
    assert template_after_add == expected_template
    assert _canonical(artifact) == artifact_before
