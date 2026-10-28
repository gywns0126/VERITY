from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json

import pytest
import requests

from api.builders import us_disclosure_feed_builder as builder


class _Response:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class _Session:
    def get(self, url, **_kwargs):
        if "0000000001" in url:
            return _Response({
                "cik": "0000000001",
                "filings": {
                    "recent": {
                        "form": ["8-K"],
                        "filingDate": ["2026-09-04"],
                        "primaryDocDescription": ["Current report"],
                        "primaryDocument": ["report.htm"],
                        "accessionNumber": ["0000000001-26-000001"],
                        "items": ["3.02, 8.01"],
                    }
                }
            })
        return _Response({"cik": "0000000002", "filings": {"recent": {"form": []}}})


def test_feed_reports_processed_empty_and_unresolved(monkeypatch, tmp_path):
    monkeypatch.setattr(builder, "_universe", lambda: ["AAA", "BBB", "CCC"])
    monkeypatch.setattr(builder, "_name_map", lambda: {"AAA": "Alpha"})
    monkeypatch.setattr(builder, "OUTPUT_PATH", str(tmp_path / "feed.json"))
    monkeypatch.setattr(builder, "MAX_SECONDS", 999)
    monkeypatch.setattr(builder, "_now_kst", lambda: datetime(2026, 9, 5, tzinfo=timezone.utc))
    monkeypatch.setattr(builder.time, "sleep", lambda _seconds: None)

    import requests
    from api.builders import us_insider_trades_public_builder as insider_builder

    monkeypatch.setattr(requests, "Session", _Session)
    monkeypatch.setattr(
        insider_builder,
        "_ticker_cik_map",
        lambda _session: {"AAA": "0000000001", "BBB": "0000000002"},
    )

    result = builder.build_feed(window_days=90)

    assert result["_meta"]["processed_n"] == 2
    assert result["_meta"]["unresolved_n"] == 1
    assert result["_coverage"]["processed_tickers"] == ["AAA", "BBB"]
    assert result["_coverage"]["unresolved_tickers"] == ["CCC"]
    assert [row["ticker"] for row in result["items"]] == ["AAA"]
    disclosure = result["items"][0]["disclosures"][0]
    assert disclosure["item_codes"] == ["3.02", "8.01"]
    assert disclosure["source_url"].endswith("/000000000126000001/report.htm")
    assert result["_coverage"]["empty_tickers"] == ["BBB"]
    receipt = result["_meta"]["source_collection"]
    assert receipt["requests"] == receipt["requests_succeeded"] == 2
    assert receipt["requests_failed"] == receipt["deferred_n"] == 0
    assert receipt["processed_n"] == 2 and receipt["unresolved_n"] == 1
    assert receipt["status"] == "partial" and receipt["successful_checked_at"] is None


def _payload(*forms, cik=1):
    return {"cik": cik, "filings": {"recent": {
        "form": list(forms),
        "filingDate": ["2026-09-04"] * len(forms),
        "reportDate": ["2026-06-30"] * len(forms),
        "acceptanceDateTime": ["2026-09-04T21:15:30.000Z"] * len(forms),
        "primaryDocDescription": [""] * len(forms),
        "primaryDocument": [f"report{i}.htm" for i in range(len(forms))],
        "accessionNumber": [f"0000000001-26-{i + 1:06d}" for i in range(len(forms))],
        "items": ["2.02, 8.01"] * len(forms),
    }}}


def _previous(*tickers):
    return {"items": [{"ticker": ticker, "name": ticker, "latest": "2026-09-01",
                       "disclosures": [{"label": "8-K", "date": "2026-09-01",
                           "title": "Previous", "source_url": "https://www.sec.gov/Archives/edgar/data/1/000000000126000099/report.htm"}]}
                      for ticker in tickers]}


@pytest.fixture
def source(monkeypatch, tmp_path):
    """Only synthetic inputs and exact mock URLs; no production reads or network."""
    from api.builders import us_insider_trades_public_builder as insider_builder

    path = tmp_path / "feed.json"
    monkeypatch.setattr(builder, "OUTPUT_PATH", str(path))
    monkeypatch.setattr(builder, "MAX_SECONDS", 999)
    monkeypatch.setattr(builder, "_now_kst", lambda: datetime(2026, 9, 5, tzinfo=timezone.utc))
    sleeps = []
    monkeypatch.setattr(builder.time, "sleep", sleeps.append)
    monkeypatch.setattr(requests.sessions.Session, "request",
                        lambda *_args, **_kwargs: pytest.fail("unexpected network request"))

    def configure(order, cik_map, responses, previous=None, on_get=None):
        calls = []
        monkeypatch.setattr(builder, "_universe", lambda: list(order))
        monkeypatch.setattr(builder, "_name_map", lambda: {ticker: f"Issuer {ticker}" for ticker in order})
        monkeypatch.setattr(insider_builder, "_ticker_cik_map", lambda _session: cik_map)
        if previous is not None:
            path.write_text(json.dumps(previous), encoding="utf-8")

        class Session:
            def get(self, url, **kwargs):
                calls.append((url, kwargs))
                if on_get:
                    on_get(url)
                response = responses[url]
                if isinstance(response, Exception):
                    raise response
                return response

        monkeypatch.setattr(requests, "Session", Session)
        return calls, sleeps, path

    return configure


@pytest.mark.parametrize("form", ["8-K", "8-K/A", "6-K", "6-K/A", "20-F", "20-F/A", "40-F", "40-F/A"])
def test_forms_preserve_identity_dates_and_existing_projection(source, form):
    from api.intelligence.portfolio_public_sources import project_public_sources

    payload = _payload(form)
    before = deepcopy(payload)
    calls, sleeps, _path = source(["ADR"], {"ADR": "0000000001"}, {
        builder.SEC_SUBMISSIONS.format(cik10="0000000001"): _Response(payload),
    })
    result = builder.build_feed()
    disclosure = result["items"][0]["disclosures"][0]
    assert disclosure["label"] == form
    assert disclosure["title"].startswith(form + " ")
    assert disclosure["is_correction"] is form.endswith("/A")
    assert disclosure["id"] == "SEC:1:000000000126000001"
    assert disclosure["cik"] == "1"
    assert disclosure["accession_number"] == "0000000001-26-000001"
    assert disclosure["primary_document"] == "report0.htm"
    assert disclosure["filing_date"] == disclosure["date"] == "2026-09-04"
    assert disclosure["report_date"] == "2026-06-30"
    assert disclosure["acceptance_datetime"] == "2026-09-04T21:15:30.000Z"
    assert "source_available_at" not in disclosure and "first_seen" not in disclosure
    assert disclosure["item_codes"] == (["2.02", "8.01"] if form.startswith("8-K") else [])
    assert result["_meta"]["generated_at"] != disclosure["acceptance_datetime"]
    assert result["_meta"]["max_per_ticker"] == 5
    assert result["_meta"]["source_collection"]["status"] == "success"
    assert len(calls) == 1 and calls[0][1]["timeout"] == 15
    assert calls[0][1]["allow_redirects"] is False
    assert calls[0][1]["headers"]["User-Agent"]
    assert sleeps == [builder.SEC_DELAY]
    assert payload == before
    projected = project_public_sources({
        "universe_search.json": {"stocks": [{"market": "US", "ticker": "ADR", "name": "Issuer ADR"}]},
        "us_disclosure_feed.json": result,
    })
    company = next(row for row in projected["companies"] if row["ticker"] == "ADR")
    document = company["documents"][0]
    assert document["as_of"] == disclosure["date"]
    assert document["url"] == disclosure["source_url"]
    assert document["source"] == "SEC"


def test_mixed_filings_cutoff_deduplication_sort_and_shared_cap(source):
    forms = ["6-K", "20-F", "40-F", "8-K", "6-K/A", "20-F/A", "40-F/A", "8-K/A", "10-K", "S-1", "6-K"]
    payload = _payload(*forms)
    recent = payload["filings"]["recent"]
    recent["filingDate"] = ["2026-06-01", "2026-06-07", "2026-07-01", "2026-07-02",
                            "2026-07-03", "2026-07-04", "2026-07-05", "2026-07-06",
                            "2026-09-04", "2026-09-04", "2026-07-03"]
    recent["accessionNumber"][-1] = recent["accessionNumber"][4]
    source(["ADR"], {"ADR": "1"}, {
        builder.SEC_SUBMISSIONS.format(cik10="0000000001"): _Response(payload),
    })
    discs = builder.build_feed()["items"][0]["disclosures"]
    assert [row["label"] for row in discs] == ["8-K/A", "40-F/A", "20-F/A", "6-K/A", "8-K"]
    assert len({row["id"] for row in discs}) == len(discs) == 5


@pytest.mark.parametrize("response,processed,empty", [
    (_Response(_payload("6-K")), True, False),
    (_Response(_payload()), True, True),
    (_Response({}, status_code=503), False, False),
    (_Response({}, status_code=302), False, False),
    (requests.ConnectionError("fixture failure"), False, False),
    (_Response(ValueError("fixture invalid json")), False, False),
])
def test_shared_cik_reuses_success_empty_and_failure_per_run(source, response, processed, empty):
    calls, sleeps, _path = source(["ADR", "ADR.B"], {"ADR": "1", "ADR.B": "0000000001"}, {
        builder.SEC_SUBMISSIONS.format(cik10="0000000001"): response,
    })
    result = builder.build_feed()
    receipt = result["_meta"]["source_collection"]
    assert len(calls) == receipt["requests"] == 1
    assert receipt["reused_cik_tickers"] == 1
    assert receipt["requests_succeeded"] == int(processed)
    assert receipt["requests_failed"] == int(not processed)
    assert receipt["processed_n"] == 2 * int(processed)
    assert receipt["unavailable_n"] == 2 * int(not processed)
    assert receipt["empty_n"] == 2 * int(empty)
    assert sleeps == [builder.SEC_DELAY]
    if processed and not empty:
        rows = {row["ticker"]: row for row in result["items"]}
        a, b = [rows[ticker]["disclosures"][0] for ticker in ("ADR", "ADR.B")]
        assert a["id"] == b["id"] and a["filer"] != b["filer"]
        assert a is not b
    builder.build_feed()
    assert len(calls) == 2  # Cache must not outlive this run.


@pytest.mark.parametrize("payload", [None, [], {}, {"filings": []}, {"filings": {}},
    {"filings": {"recent": {}}}, {"filings": {"recent": {"form": "6-K"}}},
    {"filings": {"recent": {"form": ["6-K"], "filingDate": [], "accessionNumber": []}}},
])
def test_malformed_submissions_preserve_prior_and_report_failure(source, payload):
    prior = _previous("ADR")
    _calls, _sleeps, path = source(["ADR"], {"ADR": "1"}, {
        builder.SEC_SUBMISSIONS.format(cik10="0000000001"): _Response(payload),
    }, previous=prior)
    before = path.read_bytes()
    result = builder.build_feed()
    assert result["items"] == prior["items"]
    assert result["_coverage"]["processed_tickers"] == []
    assert result["_coverage"]["unavailable_tickers"] == ["ADR"]
    assert result["_coverage"]["carry_forward_tickers"] == ["ADR"]
    assert result["_meta"]["source_collection"]["requests_failed"] == 1
    assert path.read_bytes() == before


@pytest.mark.parametrize("field,value", [("filingDate", ""), ("filingDate", "2026-02-30"),
    ("filingDate", "2026-09-06"),
    ("accessionNumber", ""), ("accessionNumber", "not-an-accession")])
def test_invalid_supported_filing_identity_is_failure_not_empty(source, field, value):
    payload = _payload("6-K")
    payload["filings"]["recent"][field] = [value]
    source(["ADR"], {"ADR": "1"}, {
        builder.SEC_SUBMISSIONS.format(cik10="0000000001"): _Response(payload),
    }, previous=_previous("ADR"))
    result = builder.build_feed()
    assert result["_coverage"]["unavailable_tickers"] == ["ADR"]
    assert result["_coverage"]["empty_tickers"] == []
    assert len(result["items"]) == 1


def test_missing_optional_facts_use_filing_index_without_invented_times(source):
    payload = _payload("20-F/A")
    recent = payload["filings"]["recent"]
    for field in ("primaryDocument", "reportDate", "acceptanceDateTime", "items"):
        recent.pop(field)
    # No historical submissions files may be fetched by this bounded builder.
    payload["filings"]["files"] = [{"name": "CIK0000000001-submissions-001.json"}]
    calls, _sleeps, _path = source(["ADR"], {"ADR": "1"}, {
        builder.SEC_SUBMISSIONS.format(cik10="0000000001"): _Response(payload),
    })
    disclosure = builder.build_feed()["items"][0]["disclosures"][0]
    assert disclosure["source_url"].endswith("/000000000126000001/0000000001-26-000001-index.html")
    assert disclosure["acceptance_datetime"] == disclosure["report_date"] == ""
    assert "source_available_at" not in disclosure and "first_seen" not in disclosure
    assert len(calls) == 1


def test_receipt_partitions_failure_empty_unresolved_and_budget_deferred(source, monkeypatch):
    clock = {"seconds": 0}
    monkeypatch.setattr(builder.time, "monotonic", lambda: clock["seconds"])
    monkeypatch.setattr(builder, "MAX_SECONDS", 1)
    prior = _previous("FAIL", "FAIL.B", "MISS", "EMPTY", "DEFER", "KEEP", "EXPIRED")
    prior["items"][-1]["latest"] = "2026-01-01"

    def on_get(url):
        if "0000000002" in url:
            clock["seconds"] = 2

    calls, _sleeps, _path = source(["FAIL", "FAIL.B", "MISS", "EMPTY", "DEFER"],
        {"FAIL": "1", "FAIL.B": "1", "EMPTY": "2", "DEFER": "3"}, {
            builder.SEC_SUBMISSIONS.format(cik10="0000000001"): _Response({}, 503),
            builder.SEC_SUBMISSIONS.format(cik10="0000000002"): _Response(_payload(cik=2)),
        }, previous=prior, on_get=on_get)
    result = builder.build_feed()
    coverage, receipt = result["_coverage"], result["_meta"]["source_collection"]
    assert coverage["processed_tickers"] == coverage["empty_tickers"] == ["EMPTY"]
    assert coverage["unavailable_tickers"] == ["FAIL", "FAIL.B"]
    assert coverage["unresolved_tickers"] == ["MISS"]
    assert coverage["unprocessed_tickers"] == ["DEFER"]
    assert coverage["carry_forward_tickers"] == ["DEFER", "FAIL", "FAIL.B", "KEEP", "MISS"]
    assert {row["ticker"] for row in result["items"]} == set(coverage["carry_forward_tickers"])
    assert len(calls) == receipt["requests"] == 2
    assert receipt["requests_succeeded"] == receipt["requests_failed"] == 1
    assert receipt["reused_cik_tickers"] == 1
    assert receipt["processed_n"] + receipt["unavailable_n"] + receipt["unresolved_n"] + receipt["deferred_n"] == receipt["universe_n"] == 5
    assert receipt["status"] == "partial" and receipt["universe_complete"] is False
    assert receipt["successful_checked_at"] is None


@pytest.mark.parametrize("failed", [False, True])
def test_main_persists_current_empty_or_failed_coverage(source, failed):
    prior = _previous("ADR") if not failed else {"items": []}
    _calls, _sleeps, path = source(["ADR"], {"ADR": "1"}, {
        builder.SEC_SUBMISSIONS.format(cik10="0000000001"): _Response(_payload(), 503 if failed else 200),
    }, previous=prior)
    assert builder.main() == 0
    result = json.loads(path.read_text(encoding="utf-8"))
    assert result["items"] == []
    assert result["_coverage"]["processed_tickers"] == ([] if failed else ["ADR"])
    assert result["_coverage"]["unavailable_tickers"] == (["ADR"] if failed else [])
    assert result["_meta"]["source_collection"]["status"] == ("error" if failed else "success")


@pytest.mark.parametrize("cik", [2, "0000000002", None, True, "1.0"])
@pytest.mark.parametrize("form", [None, "6-K"])
def test_mismatched_or_invalid_payload_cik_is_failure_even_when_empty(source, cik, form):
    payload = _payload(*([form] if form else []), cik=cik)
    source(["ADR"], {"ADR": "1"}, {
        builder.SEC_SUBMISSIONS.format(cik10="0000000001"): _Response(payload),
    }, previous=_previous("ADR"))
    result = builder.build_feed()
    assert result["_coverage"]["unavailable_tickers"] == ["ADR"]
    assert result["_coverage"]["empty_tickers"] == []
    assert result["_coverage"]["carry_forward_tickers"] == ["ADR"]


@pytest.mark.parametrize("filename", ["../report.htm", "/report.htm", "dir/report.htm",
    "https://example.com/report.htm", "report.htm?key=value", "report.htm#fragment",
    "report%2f.htm", "report\\file.htm", "..", "a" * 201])
def test_unsafe_primary_document_is_failure_and_preserves_prior(source, filename):
    payload = _payload("6-K")
    payload["filings"]["recent"]["primaryDocument"] = [filename]
    source(["ADR"], {"ADR": "1"}, {
        builder.SEC_SUBMISSIONS.format(cik10="0000000001"): _Response(payload),
    }, previous=_previous("ADR"))
    result = builder.build_feed()
    assert result["_coverage"]["unavailable_tickers"] == ["ADR"]
    assert result["items"][0]["disclosures"][0]["title"] == "Previous"


def test_cofiler_accession_prefix_is_not_required_to_match_issuer():
    payload = _payload("6-K", cik="0000000123")
    payload["filings"]["recent"]["filingDate"] = ["2026-09-05"]
    row = builder._disclosures(payload, "0000000123", "2026-06-07", "2026-09-05")[0]
    assert row["id"] == "SEC:123:000000000126000001"
    assert row["source_url"].startswith("https://www.sec.gov/Archives/edgar/data/123/")
    assert row["filing_date"] == "2026-09-05"
    with pytest.raises(ValueError, match="future filing date"):
        builder._disclosures(payload, "0000000123", "2026-06-07", "2026-09-04")


def test_budget_before_first_request_is_deferred_not_failed(source, monkeypatch):
    calls, sleeps, _path = source(["ADR", "ADR.B"], {"ADR": "1", "ADR.B": "1"}, {},
                                 previous=_previous("ADR"))
    clock = iter([0, 2, 2])
    monkeypatch.setattr(builder.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(builder, "MAX_SECONDS", 1)
    result = builder.build_feed()
    receipt = result["_meta"]["source_collection"]
    assert calls == sleeps == []
    assert receipt["requests"] == receipt["requests_failed"] == receipt["processed_n"] == 0
    assert receipt["deferred_n"] == 2 and receipt["status"] == "partial"
    assert receipt["attempted_at"] is receipt["successful_checked_at"] is None
    assert result["_coverage"]["unprocessed_tickers"] == ["ADR", "ADR.B"]
    assert result["_coverage"]["carry_forward_tickers"] == ["ADR"]
