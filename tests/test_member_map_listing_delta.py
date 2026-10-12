"""Offline listing fixtures and runner contract tests; never call live services."""
from copy import deepcopy
import json

import pytest

from api.collectors import member_map_listing_delta as delta
from api.intelligence.portfolio_public_sources import project_public_sources

CHECKED = "2026-10-11T15:12:00+00:00"  # Oct 12 in Korea
CATALOG = {"stocks": [{"market": "US", "ticker": "EXM", "name": "Example"},
                       {"market": "US", "ticker": "EXM.B", "name": "Example B"},
                       {"market": "KR", "ticker": "123456", "name": "Example Korea"}]}
ISSUERS = {"123": [{"ticker": "EXM", "name": "Example"}]}
UNIVERSE = {"123456": "Example Korea"}
PREVIOUS = {"_meta": {"generated_at": "2026-10-10T00:00:00+00:00", "source": "SEC"},
            "items": [{"ticker": "KEEP", "name": "Retained", "latest": "2026-10-10",
                       "disclosures": [{"title": "Retained", "label": "8-K", "date": "2026-10-10",
                           "source_url": "https://www.sec.gov/Archives/edgar/data/99/000000009926000001/"}]}]}


def sec_entry(number=1, cik=123, stamp="2026-10-11T14:00:00-04:00", form="8-K"):
    accession = f"0000000123-26-{number:06d}"
    return (f"<entry><title>{form} - Example ({cik:010d}) (Filer)</title>"
            f'<category term="{form}"/><id>urn:tag:sec.gov,2008:accession-number={accession}</id>'
            f"<updated>{stamp}</updated><link rel=\"alternate\" "
            f'href="https://www.sec.gov/Archives/edgar/data/{cik}/{accession.replace("-", "")}/{accession}-index.htm"/>'
            "<summary type=\"html\">&lt;b&gt;Filed: 1999-01-01&lt;/b&gt;</summary></entry>")


def atom(*entries):
    return ('<feed xmlns="http://www.w3.org/2005/Atom">' + "".join(entries) + "</feed>").encode()


def dart_row(number=1, ticker="123456", stamp="20261012"):
    return {"rcept_no": f"20261012{number:06d}", "rcept_dt": stamp,
            "stock_code": ticker, "report_nm": "공시 원문", "flr_nm": "제출인"}


def dart_page(rows, *, page=1, page_size=None, total=None):
    page_size = page_size or 100
    total = total or len(rows)
    return json.dumps({"status": "000", "page_no": page, "page_count": page_size,
                       "total_count": total, "total_page": (total + page_size - 1) // page_size,
                       "list": rows}, ensure_ascii=False).encode()


class FixtureTransport:
    def __init__(self, *responses):
        self.responses = iter(responses)
        self.calls = []

    def __call__(self, endpoint, **kwargs):
        self.calls.append((endpoint, kwargs))
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch):
    def rejected(*args, **kwargs):
        pytest.fail("Unexpected live network request")
    monkeypatch.setattr(delta.requests, "get", rejected)


def test_catalog_official_join_without_static_tickers():
    index = {"0": {"ticker": "EXM", "cik_str": 123},
             "1": {"ticker": "EXM-B", "cik_str": 123},
             "2": {"ticker": "OUTSIDE", "cik_str": 987}}
    assert delta.build_issuer_map(CATALOG, index) == {"123": [
        {"ticker": "EXM", "name": "Example"}, {"ticker": "EXM.B", "name": "Example B"}]}
    assert delta.build_kr_universe(CATALOG) == UNIVERSE


def test_atom_dates_ignore_summary_html_and_validate_links():
    row = delta.parse_sec_atom(atom(sec_entry()))[0]
    assert row["date"] == "2026-10-11"
    assert row["source_reported_at"] == "2026-10-11T14:00:00-04:00"
    assert "observed_at" not in row
    assert row["source_date_field"] == "atom.updated"
    with pytest.raises(delta.ListingError):
        delta.parse_sec_atom(atom(sec_entry().replace("www.sec.gov", "www.sec.gov.evil.test")))


def test_catalog_bad_names_are_row_local_with_identity_preserved_and_reason_counts():
    catalog = {"stocks": [
        {"market": "US", "ticker": "LONG", "name": "x" * 161, "name_ko": "Valid alternate"},
        {"market": "US", "ticker": "CTRL", "name": "Bad\x00name"},
        {"market": "US", "ticker": "TYPE", "name": 123, "name_ko": "x" * 161},
        {"market": "US", "ticker": "OK", "name": "Unaffected"},
        {"market": "US", "ticker": "invalid ticker", "name": "Cannot invent identity"},
        None]}
    original = deepcopy(catalog)
    index = {str(i): {"ticker": ticker, "cik_str": i + 100}
             for i, ticker in enumerate(("LONG", "CTRL", "TYPE", "OK"))}
    coverage = {}
    mapping = delta.build_issuer_map(catalog, index, coverage=coverage)
    assert mapping == {"100": [{"ticker": "LONG", "name": "Valid alternate"}],
                       "101": [{"ticker": "CTRL", "name": "CTRL"}],
                       "102": [{"ticker": "TYPE", "name": "TYPE"}],
                       "103": [{"ticker": "OK", "name": "Unaffected"}]}
    assert catalog == original
    report = coverage["catalog"]
    assert report["rows_total"] == 6 and report["rows_mapped"] == 4 and report["rows_excluded"] == 2
    assert report["reasons"] == {"invalid_name": 3, "name_ko_fallback": 1,
        "invalid_name_ko": 1, "ticker_name_fallback": 2, "invalid_identity": 1, "invalid_row": 1}
    assert coverage["sec_index"]["rows_mapped"] == 4


def test_kr_fallback_and_bad_official_index_rows_do_not_abort_valid_mapping():
    coverage = {}
    assert delta.build_kr_universe({"stocks": [{"market": "KR", "ticker": "123456", "name": "x" * 161}]},
                                   coverage=coverage) == {"123456": "123456"}
    assert coverage["catalog"]["reasons"]["ticker_name_fallback"] == 1
    mapping = delta.build_issuer_map(CATALOG, {"0": None,
        "1": {"ticker": "EXM", "cik_str": "wrong"}, "2": {"ticker": "EXM", "cik_str": 123}}, coverage=coverage)
    assert mapping == ISSUERS
    assert coverage["sec_index"]["reasons"] == {"invalid_row": 1, "invalid_cik": 1}


@pytest.mark.parametrize("body", [b"<html>blocked</html>", b"<feed", b'<!DOCTYPE feed [<!ENTITY x "foo">]><feed/>'])
def test_atom_rejects_non_atom_truncation_and_entities(body):
    with pytest.raises(delta.ListingError):
        delta.parse_sec_atom(body)


def test_sec_merge_preserves_other_companies_and_consumer_contract():
    before = deepcopy(PREVIOUS)
    transport = FixtureTransport(atom(sec_entry(3), sec_entry(2, cik=999), sec_entry(1)))
    cursor = {"source": "SEC", "anchor_id": "SEC:123:000000012326000001"}
    result = delta.collect_sec_delta(ISSUERS, PREVIOUS, cursor, CHECKED, transport=transport)
    assert result["status"] == "success" and result["complete"]
    assert result["unmapped"] == 1 and result["requests"] == 1
    assert result["cursor"] == result["next_cursor"]
    assert PREVIOUS == before
    assert {item["ticker"] for item in result["feed"]["items"]} == {"EXM", "KEEP"}
    projected = project_public_sources({"universe_search.json": CATALOG,
                                       "us_disclosure_feed.json": result["feed"]})
    # Existing projection accepts the generated document URL/date/title.
    assert any(c["ticker"] == "EXM" and c["documents"] for c in projected["companies"])
    record = result["records"][0]
    assert record["observed_at"] == CHECKED
    endpoint, kwargs = transport.calls[0]
    assert endpoint == delta.SEC_LATEST and kwargs["timeout"] <= 10
    assert kwargs["params"]["action"] == "getcurrent" and "CIK" not in kwargs["params"]
    assert kwargs["headers"]["User-Agent"]


def test_sec_cursor_boundary_duplicate_and_record_limit():
    anchor = delta.parse_sec_atom(atom(sec_entry(1)))[0]["id"]
    cursor = {"source": "SEC", "anchor_id": anchor}
    transport = FixtureTransport(atom(sec_entry(3), sec_entry(3), sec_entry(1), sec_entry(2)))
    result = delta.collect_sec_delta(ISSUERS, PREVIOUS, cursor, CHECKED, transport=transport)
    assert result["status"] == "success" and len(result["records"]) == 1
    assert result["duplicates"] == 1
    result = delta.collect_sec_delta(ISSUERS, PREVIOUS, cursor, CHECKED,
        transport=FixtureTransport(atom(sec_entry(3), sec_entry(2), sec_entry(1))), max_records=1)
    assert result["status"] == "partial" and result["error"] == "record_limit"
    assert result["feed"] == PREVIOUS and result["cursor"] == cursor
    assert result["next_cursor"] is None and len(result["records"]) == 1


@pytest.mark.parametrize("responses,error", [
    ([atom(sec_entry(2)), atom()], "cursor_not_found"),
    ([atom(sec_entry(2)), atom(sec_entry(2))], "pagination_stalled"),
    ([atom(sec_entry(2)), RuntimeError("SECRET URL")], "collection_failure"),
])
def test_sec_incomplete_never_advances(responses, error):
    cursor = {"source": "SEC", "anchor_id": "SEC:123:000000012326000001"}
    result = delta.collect_sec_delta(ISSUERS, PREVIOUS, cursor, CHECKED,
                                   transport=FixtureTransport(*responses), page_size=1)
    assert result["status"] == "partial" and result["error"] == error
    assert result["feed"] == PREVIOUS and result["cursor"] == cursor
    assert result["next_cursor"] is None and not result["complete"]
    assert "SECRET" not in json.dumps(result)


def test_sec_page_cap_and_per_company_feed_cap():
    result = delta.collect_sec_delta(ISSUERS, PREVIOUS, None, CHECKED,
        transport=FixtureTransport(atom(sec_entry())), page_size=1, max_pages=1)
    assert result["status"] == "initialized" and result["feed"] == PREVIOUS
    result = delta.collect_sec_delta(ISSUERS, PREVIOUS,
        {"source": "SEC", "anchor_id": "SEC:123:000000012326000001"}, CHECKED,
        transport=FixtureTransport(atom(sec_entry(3), sec_entry(2), sec_entry(1))), max_per_ticker=1)
    assert len(result["records"]) == 2
    assert len(next(i for i in result["feed"]["items"] if i["ticker"] == "EXM")["disclosures"]) == 1


def test_sec_busy_bootstrap_then_incremental_success_without_historical_claim():
    # Three full pages, with more history beyond the budget: establish head once.
    transport = FixtureTransport(*(atom(*(sec_entry(n) for n in range(start, start - 100, -1)))
                                   for start in (400, 300, 200)))
    initialized = delta.collect_sec_delta(ISSUERS, PREVIOUS, None, CHECKED, transport=transport)
    assert initialized["status"] == "initialized" and not initialized["complete"]
    assert initialized["historical_gap"] and initialized["coverage"]["bounded"]
    assert not initialized["coverage"]["whole_market_coverage"]
    assert initialized["feed"] == PREVIOUS and initialized["requests"] == 3
    assert len(initialized["records"]) == 300
    assert initialized["next_cursor"]["anchor_id"] == "SEC:123:000000012326000400"
    result = delta.collect_sec_delta(ISSUERS, PREVIOUS, initialized["cursor"], CHECKED,
        transport=FixtureTransport(atom(sec_entry(401), sec_entry(400), sec_entry(399))))
    assert result["status"] == "success" and result["complete"]
    assert len(result["records"]) == 1 and result["historical_gap"]
    assert result["cursor"]["anchor_id"] == "SEC:123:000000012326000401"


def test_dart_date_only_and_kst_window_and_projection():
    transport = FixtureTransport(dart_page([dart_row()]))
    result = delta.collect_dart_delta(UNIVERSE, {"items": []}, None, CHECKED, "not-a-real-key", transport=transport)
    assert result["status"] == "success"
    record = result["records"][0]
    assert record["date"] == "2026-10-12" and record["date_precision"] == "date"
    assert record["observed_at"] == CHECKED and "source_reported_at" not in record
    endpoint, kwargs = transport.calls[0]
    assert endpoint == delta.DART_LIST
    assert kwargs["params"]["end_de"] == "20261012" and "corp_code" not in kwargs["params"]
    assert kwargs["params"]["crtfc_key"] == "not-a-real-key"
    assert "not-a-real-key" not in json.dumps(result)
    projected = project_public_sources({"public_disclosure_feed.json": result["feed"]})
    assert projected["companies"][0]["documents"][0]["as_of"] == "2026-10-12"


def test_dart_replays_same_day_no_receipt_order_assumption():
    cursor = {"source": "DART", "through_date": "2026-10-12", "ids": ["DART:20261012000002"]}
    transport = FixtureTransport(dart_page([dart_row(2), dart_row(1)]))
    result = delta.collect_dart_delta(UNIVERSE, PREVIOUS, cursor, CHECKED, "key", transport=transport)
    assert result["status"] == "success"
    assert len(result["records"]) == 1 and result["duplicates"] == 1
    assert set(result["cursor"]["ids"]) == {"DART:20261012000001", "DART:20261012000002"}


def test_dart_pages_unmapped_and_unique_denominator():
    transport = FixtureTransport(dart_page([dart_row(1)], page_size=1, total=2),
                                 dart_page([dart_row(2, ticker="")], page=2, page_size=1, total=2))
    result = delta.collect_dart_delta(UNIVERSE, PREVIOUS, None, CHECKED, "key", page_size=1, transport=transport)
    assert result["status"] == "success" and result["requests"] == 2
    assert result["unmapped"] == 1 and result["coverage"]["total_records"] == 2
    duplicate = FixtureTransport(dart_page([dart_row()], page_size=1, total=2),
                                 dart_page([dart_row()], page=2, page_size=1, total=2))
    result = delta.collect_dart_delta(UNIVERSE, PREVIOUS, None, CHECKED, "key", page_size=1, transport=duplicate)
    assert result["error"] == "incomplete_unique_records" and result["duplicates"] == 1
    assert result["feed"] == PREVIOUS and result["next_cursor"] is None


@pytest.mark.parametrize("second,error", [
    (b'{"status":"020","message":"key=SECRET"}', "dart-quota-exceeded"),
    (b"{", "invalid_json"),
    (dart_page([dart_row(2)], page=2, page_size=1, total=3), "pagination_changed"),
    (RuntimeError("key=SECRET"), "collection_failure"),
])
def test_dart_failure_preserves_snapshot(second, error):
    cursor = {"source": "DART", "through_date": "2026-10-11", "ids": []}
    transport = FixtureTransport(dart_page([dart_row()], page_size=1, total=2), second)
    result = delta.collect_dart_delta(UNIVERSE, PREVIOUS, cursor, CHECKED, "SECRET", page_size=1, transport=transport)
    assert result["status"] == "partial" and result["error"] == error
    assert result["feed"] == PREVIOUS and result["cursor"] == cursor and result["next_cursor"] is None
    assert "SECRET" not in json.dumps(result)


def test_dart_short_page_cap_empty_and_invalid_dates():
    incomplete = json.loads(dart_page([dart_row()], page_size=2, total=2))
    with pytest.raises(delta.ListingError, match="incomplete_page"):
        delta.parse_dart_list(incomplete)
    with pytest.raises(delta.ListingError, match="invalid_reported_date"):
        delta.parse_dart_list(json.loads(dart_page([dart_row(stamp="20260230")])))
    result = delta.collect_dart_delta(UNIVERSE, PREVIOUS, None, CHECKED, "key", max_pages=1,
        page_size=1, transport=FixtureTransport(dart_page([dart_row()], page_size=1, total=2)))
    assert result["error"] == "page_limit" and result["feed"] == PREVIOUS
    assert len(result["records"]) == 1 and result["cursor"] is None and result["next_cursor"] is None
    result = delta.collect_dart_delta(UNIVERSE, PREVIOUS, None, CHECKED, "key",
        transport=FixtureTransport(b'{"status":"013"}'))
    assert result["status"] == "success" and result["feed"] == PREVIOUS
    assert result["cursor"]["through_date"] == "2026-10-12"


def test_sec_legacy_directory_link_dedupes_atom_index_by_accession():
    previous = {"items": [{"ticker": "EXM", "name": "Example", "latest": "2026-10-11",
        "disclosures": [{"title": "8-K", "date": "2026-10-11", "label": "8-K",
            "source_url": "https://www.sec.gov/Archives/edgar/data/123/000000012326000002/"}]}]}
    result = delta.collect_sec_delta(ISSUERS, previous,
        {"source": "SEC", "anchor_id": "SEC:123:000000012326000001"}, CHECKED,
        transport=FixtureTransport(atom(sec_entry(2), sec_entry(1))))
    assert result["status"] == "success" and not result["records"]
    assert result["duplicates"] == 1 and result["feed"] == previous


def test_fixed_transport_rejects_arbitrary_url_redirect_body_limit(monkeypatch):
    with pytest.raises(delta.ListingError, match="endpoint_rejected"):
        delta.bounded_transport("https://evil.test", params={}, headers={})
    with pytest.raises(delta.ListingError, match="invalid_transport_limits"):
        delta.bounded_transport(delta.SEC_LATEST, params={}, headers={}, timeout=11)

    class Response:
        status_code = 302
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def iter_content(self, **kwargs):
            yield b"x" * 11

    response = Response()
    calls = []
    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return response
    monkeypatch.setattr(delta.requests, "get", fake_get)
    with pytest.raises(delta.ListingError, match="http_failure"):
        delta.bounded_transport(delta.DART_LIST, params={"crtfc_key": "key"}, headers={})
    assert calls[0][1]["allow_redirects"] is False
    response.status_code = 200
    with pytest.raises(delta.ListingError, match="body_limit"):
        delta.bounded_transport(delta.DART_LIST, params={}, headers={}, max_bytes=10)
