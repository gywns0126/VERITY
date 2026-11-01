"""Offline listing fixtures and runner contract tests; never call live services."""
from copy import deepcopy
from datetime import date, timedelta
import hashlib
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
    result = delta.collect_dart_delta(UNIVERSE, {"items": []}, None, CHECKED, "not-a-real-key", transport=transport, window_days=1)
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
    cursor = {"source": "DART", "through_date": "2026-10-12", "ids": [
        "DART:20261012000002", "DART:20261008000025"]}
    transport = FixtureTransport(dart_page([dart_row(2), dart_row(1)]))
    result = delta.collect_dart_delta(UNIVERSE, PREVIOUS, cursor, CHECKED, "key", transport=transport, window_days=1)
    assert result["status"] == "success"
    assert len(result["records"]) == 1 and result["duplicates"] == 1
    assert set(result["cursor"]["ids"]) == {
        "DART:20261012000001", "DART:20261012000002", "DART:20261008000025"}


def test_dart_legacy_boundary_ids_survive_empty_013_replay():
    old_id = "DART:20261008000025"
    cursor = {"source": "DART", "through_date": "2026-10-12", "ids": [old_id], "checked_at": CHECKED}
    checked = "2026-10-14T15:00:00+00:00"  # Oct 15 in Korea
    result = delta.collect_dart_delta(UNIVERSE, PREVIOUS, cursor, checked, "key",
        transport=FixtureTransport(b'{"status":"013"}'))
    assert result["status"] == "partial" and result["error"] is None
    assert result["catchup_phase"] == "replayed" and result["coverage"]["historical_gap"] is True
    assert result["cursor"]["ids"] == [old_id]
    assert result["cursor"]["checked_at"] == checked
    assert result["next_cursor"] == result["cursor"]


def test_dart_same_boundary_id_union_overflow_retains_prior_checkpoint():
    cursor = {"source": "DART", "through_date": "2026-10-12",
              "ids": [f"DART:20261008{number:06d}" for number in range(1000)], "checked_at": CHECKED}
    result = delta.collect_dart_delta(UNIVERSE, PREVIOUS, cursor, CHECKED, "key",
        transport=FixtureTransport(dart_page([dart_row(1)])), window_days=1)
    assert result["status"] == "partial" and result["error"] == "record_limit"
    assert result["next_cursor"] is None and result["cursor"] == cursor
    assert result["feed"] == PREVIOUS and result["coverage"]["pages_succeeded"] == 1


def test_dart_catchup_exhausts_one_chronological_day_without_false_success():
    cursor = {"source": "DART", "through_date": "2026-10-12",
              "ids": ["DART:20261008000025"], "checked_at": CHECKED}
    checked = "2026-10-14T15:00:00+00:00"  # Oct 15 in Korea
    transport = FixtureTransport(dart_page([dart_row(1)]))
    result = delta.collect_dart_delta(UNIVERSE, {"items": []}, cursor, checked, "key", transport=transport,
                                      window_days=90)
    assert result["status"] == "partial" and result["complete"] is False and result["error"] is None
    assert result["coverage"]["historical_gap"] is True
    assert result["catchup_phase"] == "replayed"
    assert result["next_cursor"] == result["cursor"]
    assert result["cursor"]["through_date"] == "2026-10-12"
    assert set(result["cursor"]["ids"]) == {"DART:20261008000025", "DART:20261012000001"}
    assert transport.calls[0][1]["params"]["bgn_de"] == "20261012"
    assert transport.calls[0][1]["params"]["end_de"] == "20261012"
    row13 = {**dart_row(1), "rcept_no": "20261013000001", "rcept_dt": "20261013"}
    advance = FixtureTransport(dart_page([row13]))
    next_result = delta.collect_dart_delta(UNIVERSE, result["feed"], result["cursor"], checked, "key",
        transport=advance, window_days=90, catchup_phase="replayed")
    assert next_result["status"] == "partial" and next_result["catchup_phase"] == "advanced"
    assert next_result["cursor"]["through_date"] == "2026-10-13"
    assert next_result["cursor"]["ids"] == ["DART:20261013000001"]
    assert advance.calls[0][1]["params"]["bgn_de"] == "20261013"
    assert advance.calls[0][1]["params"]["end_de"] == "20261013"


def test_dart_bootstrap_ninety_day_window_starts_at_oldest_day_without_false_success():
    checked = "2026-10-14T15:00:00+00:00"  # Oct 15 in Korea
    transport = FixtureTransport(b'{"status":"013"}')
    result = delta.collect_dart_delta(UNIVERSE, {"items": []}, None, checked, "key",
        transport=transport, window_days=90)
    first_day = (date(2026, 10, 15) - timedelta(days=89)).isoformat()
    assert result["status"] == "partial" and result["complete"] is False
    assert result["catchup_phase"] == "replayed" and result["cursor"]["through_date"] == first_day
    assert result["cursor"]["checked_at"] == checked
    assert transport.calls[0][1]["params"]["bgn_de"] == first_day.replace("-", "")
    assert transport.calls[0][1]["params"]["end_de"] == first_day.replace("-", "")


@pytest.mark.parametrize("unmapped_ticker", ["", "00499K"])
def test_dart_pages_unmapped_and_unique_denominator(unmapped_ticker):
    transport = FixtureTransport(dart_page([dart_row(1)], page_size=1, total=2),
                                 dart_page([dart_row(2, ticker=unmapped_ticker)], page=2, page_size=1, total=2))
    result = delta.collect_dart_delta(UNIVERSE, PREVIOUS, None, CHECKED, "key", page_size=1, transport=transport, window_days=1)
    assert result["status"] == "success" and result["requests"] == 2
    assert result["unmapped"] == 1 and result["coverage"]["total_records"] == 2
    assert result["complete"] and result["coverage"]["listing_records"] == 2
    assert set(result["next_cursor"]["ids"]) == {"DART:20261012000001", "DART:20261012000002"}
    duplicate = FixtureTransport(dart_page([dart_row()], page_size=1, total=2),
                                 dart_page([dart_row()], page=2, page_size=1, total=2))
    result = delta.collect_dart_delta(UNIVERSE, PREVIOUS, None, CHECKED, "key", page_size=1, transport=duplicate, window_days=1)
    assert result["error"] == "incomplete_unique_records" and result["duplicates"] == 1
    assert result["feed"] == PREVIOUS and result["next_cursor"] is None


@pytest.mark.parametrize("ticker", ["123456", "00499K"])
@pytest.mark.parametrize("mapped", [False, True])
def test_dart_listing_code_mapping_remains_explicit(ticker, mapped):
    universe = {ticker: "Example"} if mapped else {}
    result = delta.collect_dart_delta(universe, PREVIOUS, None, CHECKED, "key",
        transport=FixtureTransport(dart_page([dart_row(ticker=ticker)])), window_days=1)
    assert result["status"] == "success" and result["complete"]
    assert result["unmapped"] == (0 if mapped else 1)
    assert [r["ticker"] for r in result["records"]] == ([ticker] if mapped else [])
    assert result["coverage"]["listing_records"] == result["coverage"]["total_records"] == 1
    assert result["next_cursor"]["ids"] == ["DART:20261012000001"]
    if not mapped:
        assert result["feed"] == PREVIOUS


@pytest.mark.parametrize("ticker", ["      ", "00499k", "A12345", "00499K ", "12345", "1234567",
                                    "１２３４５６", None, 0, 123456, False, [], {}])
def test_dart_malformed_stock_code_keeps_prior_cursor_and_feed(ticker):
    cursor = {"source": "DART", "through_date": "2026-10-12", "ids": []}
    transport = FixtureTransport(dart_page([dart_row(1)], page_size=1, total=2),
        dart_page([dart_row(2, ticker=ticker)], page=2, page_size=1, total=2))
    result = delta.collect_dart_delta(UNIVERSE, PREVIOUS, cursor, CHECKED, "key",
        page_size=1, transport=transport, window_days=1)
    assert result["status"] == "partial" and result["error"] == "invalid_stock_code"
    assert not result["complete"] and result["next_cursor"] is None
    assert result["cursor"] == cursor and result["feed"] == PREVIOUS
    assert result["requests"] == 2 and result["coverage"]["pages_succeeded"] == 1


@pytest.mark.parametrize("second,error", [
    (b'{"status":"020","message":"key=SECRET"}', "dart-quota-exceeded"),
    (b"{", "invalid_json"),
    (dart_page([dart_row(2)], page=2, page_size=1, total=3), "pagination_changed"),
    (RuntimeError("key=SECRET"), "collection_failure"),
])
def test_dart_failure_preserves_snapshot(second, error):
    cursor = {"source": "DART", "through_date": "2026-10-12", "ids": []}
    transport = FixtureTransport(dart_page([dart_row()], page_size=1, total=2), second)
    result = delta.collect_dart_delta(UNIVERSE, PREVIOUS, cursor, CHECKED, "SECRET", page_size=1, transport=transport, window_days=1)
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
        page_size=1, transport=FixtureTransport(dart_page([dart_row()], page_size=1, total=2)), window_days=1)
    assert result["error"] == "page_limit" and result["feed"] == PREVIOUS
    assert len(result["records"]) == 1 and result["cursor"] is None and result["next_cursor"] is None
    result = delta.collect_dart_delta(UNIVERSE, PREVIOUS, None, CHECKED, "key",
        transport=FixtureTransport(b'{"status":"013"}'), window_days=1)
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


def continuation_source(day="20261030", total=1062, mapped=True):
    calls = []
    rows = [{"rcept_no": f"{day}{i:06d}", "rcept_dt": day,
             "stock_code": "123456" if mapped else "", "report_nm": "Synthetic filing", "flr_nm": "Issuer"}
            for i in range(1, total + 1)]
    def fetch(endpoint, **kwargs):
        assert endpoint == delta.DART_LIST
        params = kwargs["params"]
        assert "corp_cls" not in params and "corp_code" not in params and params["page_count"] == "100"
        assert params["bgn_de"] == params["end_de"] == day
        page = int(params["page_no"]); calls.append(page)
        return dart_page(rows[(page-1)*100:page*100], page=page, page_size=100, total=len(rows))
    return fetch, calls, rows


@pytest.mark.parametrize("mapped", [True, False])
def test_dart_v2_1062_resume_two_sweeps_preserves_denominator_and_legacy_ids(mapped):
    from api.collectors.member_map_live_refresh import apply_result
    from api.collectors.member_map_refresh_store import validate_state, validate_dart_bundle
    stamp = "2026-10-30T08:30:32+00:00"
    prior = {"cursor": {"source": "DART", "through_date": "2026-10-30", "checked_at": stamp,
                        "ids": [f"DART:20261030{i:06d}" for i in range(1, 996)]},
             "last_success_at": stamp, "feed": {"items": []}}
    cp = None
    fetch, calls, _ = continuation_source(mapped=mapped)
    for index, expected in enumerate((list(range(1, 11)), [1, 10, 11], list(range(1, 11)), [1, 10, 11])):
        calls.clear(); now = f"2026-11-01T06:{index*2:02d}:00+00:00"
        result = delta.collect_dart_continuation(UNIVERSE, prior["feed"], prior["cursor"], now, "synthetic", cp, transport=fetch)
        assert calls == expected and result["requests"] <= 10 and len(result["records"]) <= 1000
        assert result["coverage"]["listing_records"] <= 1000 and result["coverage"]["total_records"] == 1062
        assert result["status"] == "partial" and result["error"] is None
        prior = apply_result("DART", prior, result, now); cp = json.loads(json.dumps(result["dart_checkpoint"]))
        validate_state("DART", prior); validate_dart_bundle(prior, cp)
        assert prior["last_success_at"] == stamp
    assert cp["pending"] is None and len(cp["committed"]["ids"]) == 1062
    assert prior["cursor"]["id_count"] == 1062 and "ids" not in prior["cursor"]
    assert bool(prior["feed"]["items"]) == mapped


def test_dart_v2_same_count_middle_page_change_fails_verification():
    cursor = {"source": "DART", "through_date": "2026-10-30", "ids": [], "checked_at": "2026-10-30T01:00:00Z"}
    fetch, calls, rows = continuation_source()
    cp = None
    for index in range(4):
        if index == 2:
            rows[450] = {**rows[450], "rcept_no": "20261030999999"}
        result = delta.collect_dart_continuation(UNIVERSE, {"items": []}, cursor, f"2026-11-01T06:{index*2:02d}:00Z",
                                               "synthetic", cp, transport=fetch)
        cp = result["dart_checkpoint"]
    assert result["error"] == "pagination_changed" and not result["dart_sealed"]
    assert result["cursor"] == cursor and cp["committed"]["ids"] == []
    assert cp["pending"]["phase"] == "scan" and cp["pending"]["next_page"] == 1
    assert len(cp["pending"]["observed"]) == 1063  # retain observations across the changed pass


def test_dart_v2_guard_change_resets_without_skipping_date():
    cursor = {"source": "DART", "through_date": "2026-10-30", "ids": ["DART:20261029000001"], "checked_at": "2026-10-30T01:00:00Z"}
    fetch, calls, rows = continuation_source()
    first = delta.collect_dart_continuation(UNIVERSE, {"items": []}, cursor, "2026-11-01T06:00:00Z", "synthetic", None, transport=fetch)
    rows[0] = {**rows[0], "rcept_no": "20261030999999"}; calls.clear()
    result = delta.collect_dart_continuation(UNIVERSE, {"items": []}, cursor, "2026-11-01T06:02:00Z", "synthetic", first["dart_checkpoint"], transport=fetch)
    assert calls == [1] and result["error"] == "pagination_changed"
    assert result["cursor"] == cursor and result["dart_checkpoint"]["pending"]["date"] == "2026-10-30"
    assert result["dart_checkpoint"]["committed"]["ids"] == cursor["ids"]


def test_dart_v2_current_day_needs_verify_and_midnight_does_not_fake_current_success():
    cursor = {"source": "DART", "through_date": "2026-10-30", "ids": [], "checked_at": "2026-10-30T01:00:00Z"}
    fetch, _, _ = continuation_source(total=1)
    scan = delta.collect_dart_continuation(UNIVERSE, {"items": []}, cursor, "2026-10-30T14:58:00Z", "synthetic", None, transport=fetch)
    assert scan["status"] == "partial" and not scan["dart_sealed"]
    current = delta.collect_dart_continuation(UNIVERSE, {"items": []}, cursor, "2026-10-30T14:59:00Z", "synthetic", scan["dart_checkpoint"], transport=fetch)
    assert current["status"] == "success" and current["dart_sealed"]
    rolled = delta.collect_dart_continuation(UNIVERSE, {"items": []}, cursor, "2026-10-30T15:00:00Z", "synthetic", scan["dart_checkpoint"], transport=fetch)
    assert rolled["status"] == "partial" and rolled["dart_sealed"]


def test_dart_v2_013_two_sweeps_keep_legacy_boundary_ids():
    cursor = {"source": "DART", "through_date": "2026-10-30", "ids": ["DART:20261029000001"], "checked_at": "2026-10-30T01:00:00Z"}
    scan = delta.collect_dart_continuation(UNIVERSE, {"items": []}, cursor, "2026-11-01T06:00:00Z", "synthetic", None, transport=lambda *a, **k: b'{"status":"013"}')
    verified = delta.collect_dart_continuation(UNIVERSE, {"items": []}, cursor, "2026-11-01T06:02:00Z", "synthetic", scan["dart_checkpoint"], transport=lambda *a, **k: b'{"status":"013"}')
    assert verified["dart_sealed"] and verified["dart_checkpoint"]["committed"]["ids"] == cursor["ids"]
    assert verified["status"] == "partial"


def test_dart_v2_catalog_change_restarts_pass_and_bad_proof_cannot_advance():
    cursor = {"source": "DART", "through_date": "2026-10-30", "ids": [], "checked_at": "2026-10-30T01:00:00Z"}
    fetch, calls, _ = continuation_source()
    scan = delta.collect_dart_continuation(UNIVERSE, {"items": []}, cursor, "2026-11-01T06:00:00Z", "synthetic", None, transport=fetch)
    calls.clear()
    restarted = delta.collect_dart_continuation({"123456": "Changed catalog"}, {"items": []}, cursor,
        "2026-11-01T06:02:00Z", "synthetic", scan["dart_checkpoint"], transport=fetch)
    assert calls == list(range(1, 11)) and restarted["dart_checkpoint"]["pending"]["phase"] == "scan"
    for proofs in (scan["dart_pages"] * 2, [dict(scan["dart_pages"][0], page_no=2)],
                   [dict(scan["dart_pages"][0], rows=scan["dart_pages"][0]["rows"] * 2)]):
        with pytest.raises(delta.ListingError):
            delta.dart_replay_pages(None, cursor, "2026-11-01T06:00:00Z", scan["dart_catalog"], proofs)


@pytest.mark.parametrize("bad_version", ["2", 2.0, True])
def test_dart_v2_checkpoint_version_is_strict_integer(bad_version):
    with pytest.raises(delta.ListingError):
        delta.validate_dart_checkpoint({"version": bad_version, "committed": None, "pending": None})


def test_dart_v2_new_proof_day_binding_does_not_reject_legacy_ids():
    cursor = {"source": "DART", "through_date": "2026-10-30", "ids": ["DART:20261029000001"],
              "checked_at": "2026-10-30T01:00:00Z"}
    now, catalog = "2026-11-01T06:00:00Z", "a" * 64
    proof = {"queried_date": "2026-10-29", "page_no": 1, "total_count": 1, "rows": [["DART:20261029000002", "b" * 64]]}
    with pytest.raises(delta.ListingError):
        delta.dart_replay_pages(None, cursor, now, catalog, [proof])
    proof["queried_date"] = "2026-10-30"
    cp, sealed, error = delta.dart_replay_pages(None, cursor, now, catalog, [proof])
    assert cp["committed"]["ids"] == cursor["ids"] and not sealed and error is None
    assert cp["pending"]["baseline"] == {"DART:20261029000002": "b" * 64}
    cp["pending"]["baseline"] = {"DART:20261030000002": "b" * 64}  # Unobserved ID remains invalid.
    with pytest.raises(delta.ListingError): delta.validate_dart_checkpoint(cp)


@pytest.mark.parametrize("pair", [[["invalid-key"], "b" * 64], [True, "b" * 64], ["DART:20261030000001", None]])
def test_dart_v2_malformed_proof_pairs_are_fixed_errors(pair):
    with pytest.raises(delta.ListingError, match="invalid_pagination"):
        delta.dart_replay_pages(None, None, "2026-10-31T06:00:00Z", "a" * 64,
                               [{"queried_date": "2026-10-30", "page_no": 1, "total_count": 1, "rows": [pair]}])


# Frozen public fields from dart_catalyst_alerts.jsonl, 2026-10-30 entries
# 22954..22958 and 22965..22966. Receipt identity is not the reported date.
REPORTED_DATE_ROWS = [
    {"rcept_no": receipt, "rcept_dt": "20261030", "stock_code": ticker, "report_nm": title, "flr_nm": filer}
    for receipt, ticker, title, filer in [
        ("20261029000666", "114840", "주식등의대량보유상황보고서(일반)", "MarubeniCorporation"),
        ("20261029000668", "006370", "[기재정정]주요사항보고서(유형자산양도결정)", "대구백화점"),
        ("20261029000669", "429270", "주요사항보고서(유상증자결정)", "시지트로닉스"),
        ("20261029000671", "163730", "임원ㆍ주요주주특정증권등소유상황보고서", "안인주"),
        ("20261029000672", "179530", "[기재정정]주요사항보고서(전환사채권발행결정)", "애드바이오텍"),
        ("20261029000673", "179530", "[기재정정]주요사항보고서(전환사채권발행결정)", "애드바이오텍"),
        ("20261029000674", "179530", "주요사항보고서(전환사채권발행결정)", "애드바이오텍"),
    ]
]


def canonical_digest(row):
    return hashlib.sha256(json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


@pytest.mark.parametrize("row", REPORTED_DATE_ROWS, ids=lambda r: r["rcept_no"])
def test_actual_reported_date_counterexamples_preserve_identity_and_date_in_digest(row):
    payload = dart_page([row])
    parsed = delta.parse_dart_list(json.loads(payload))["rows"][0]
    assert parsed["id"] == "DART:" + row["rcept_no"]
    assert parsed["date"] == "2026-10-30" and parsed["source_date_field"] == "rcept_dt"
    cursor = {"source": "DART", "through_date": "2026-10-30", "ids": [], "checked_at": "2026-10-30T01:00:00Z"}
    result = delta.collect_dart_continuation({row["stock_code"]: row["flr_nm"]}, {"items": []}, cursor,
        "2026-11-01T06:00:00Z", "synthetic", None, transport=lambda *a, **kw: payload)
    assert result["error"] is None and not result["dart_sealed"]
    assert result["dart_pages"] == [{"queried_date": "2026-10-30", "page_no": 1, "total_count": 1,
                                      "rows": [[parsed["id"], canonical_digest(parsed)]]}]
    assert result["records"][0]["date"] == "2026-10-30"
    changed = delta.parse_dart_list(json.loads(dart_page([{**row, "rcept_dt": "20261029"}])))["rows"][0]
    assert changed["id"] == parsed["id"] and canonical_digest(changed) != canonical_digest(parsed)
    assert delta.validate_dart_checkpoint(result["dart_checkpoint"]) == result["dart_checkpoint"]


def test_reported_date_1062_replay_resumes_legacy_900_row_checkpoint_without_migration():
    from api.collectors.member_map_live_refresh import apply_result
    from api.collectors.member_map_refresh_store import validate_state, validate_dart_bundle
    fetch, calls, rows = continuation_source()
    # Synthetic page placement exercises the former page-10 stop; no claim
    # about the seven real records' historical listing page/order.
    rows[900:907] = deepcopy(REPORTED_DATE_ROWS)
    universe = {**UNIVERSE, **{r["stock_code"]: r["flr_nm"] for r in REPORTED_DATE_ROWS}}
    stamp = "2026-10-30T08:30:32+00:00"
    cursor = {"source": "DART", "through_date": "2026-10-30", "checked_at": stamp,
              "ids": sorted("DART:" + r["rcept_no"] for r in rows[:995])}
    first = delta.collect_dart_continuation(universe, {"items": []}, cursor, "2026-11-01T06:00:00Z",
                                            "synthetic", None, transport=fetch)
    assert first["error"] is None
    cp, sealed, error = delta.dart_replay_pages(None, cursor, "2026-11-01T06:00:00Z", first["dart_catalog"], first["dart_pages"][:9])
    assert not sealed and error is None and len(cp["pending"]["rows"]) == 900 and cp["pending"]["next_page"] == 10
    # Exact old checkpoint shape: queried_date belongs only to transient proofs.
    assert cp["version"] == 2 and "queried_date" not in json.dumps(cp)
    before = deepcopy(cp)
    prior = {"cursor": cursor, "last_success_at": stamp, "feed": {"items": []}}
    for index, expected in enumerate(([1, 9, 10, 11], list(range(1, 11)), [1, 10, 11])):
        calls.clear(); now = f"2026-11-01T06:{(index+1)*2:02d}:00Z"
        result = delta.collect_dart_continuation(universe, prior["feed"], prior["cursor"], now, "synthetic", cp, transport=fetch)
        assert calls == expected and result["error"] is None and result["status"] == "partial"
        assert result["requests"] <= 10 and len(result["records"]) <= 1000
        assert result["coverage"]["total_records"] == 1062 and result["coverage"]["listing_records"] <= 1000
        assert all(p["queried_date"] == "2026-10-30" for p in result["dart_pages"])
        prior = apply_result("DART", prior, result, now); cp = json.loads(json.dumps(result["dart_checkpoint"]))
        validate_state("DART", prior); validate_dart_bundle(prior, cp)
        assert prior["last_success_at"] == stamp and delta.dart_aggregate_size(prior, cp) <= 4*1024*1024
    assert before["pending"]["next_page"] == 10 and len(before["pending"]["rows"]) == 900
    assert result["dart_sealed"] and cp["pending"] is None and len(cp["committed"]["ids"]) == 1062
    assert set(cursor["ids"]) <= set(cp["committed"]["ids"])
    assert all("DART:" + row["rcept_no"] in cp["committed"]["ids"] for row in REPORTED_DATE_ROWS)
    assert prior["cursor"]["id_count"] == 1062


@pytest.mark.parametrize("queried_date", [None, "2026-10-29", "20261030", True])
def test_proof_requires_exact_queried_date_without_accepting_old_nonempty_proofs(queried_date):
    cursor = {"source": "DART", "through_date": "2026-10-30", "ids": [], "checked_at": "2026-10-30T01:00:00Z"}
    proof = {"page_no": 1, "total_count": 1, "rows": [["DART:20261029000666", "b"*64]]}
    if queried_date is not None: proof["queried_date"] = queried_date
    before = deepcopy((cursor, proof))
    with pytest.raises(delta.ListingError, match="invalid_pagination"):
        delta.dart_replay_pages(None, cursor, "2026-11-01T06:00:00Z", "a"*64, [proof])
    assert (cursor, proof) == before


@pytest.mark.parametrize("mapped", [False, True])
@pytest.mark.parametrize("violation,error", [("reported_date", "date_outside_window"), ("duplicate", "incomplete_unique_records")])
def test_reported_date_and_real_duplicate_guards_still_reject_bad_page_ten(mapped, violation, error):
    fetch, calls, rows = continuation_source(mapped=mapped)
    rows[900:907] = [{**r, "stock_code": r["stock_code"] if mapped else ""} for r in REPORTED_DATE_ROWS]
    if violation == "reported_date": rows[900]["rcept_dt"] = "20261029"
    else: rows[901] = deepcopy(rows[900])
    universe = {**UNIVERSE, **{r["stock_code"]: r["flr_nm"] for r in REPORTED_DATE_ROWS}} if mapped else UNIVERSE
    cursor = {"source": "DART", "through_date": "2026-10-30", "ids": [], "checked_at": "2026-10-30T01:00:00Z"}
    result = delta.collect_dart_continuation(universe, {"items": []}, cursor, "2026-11-01T06:00:00Z", "synthetic", None, transport=fetch)
    assert result["error"] == error and not result["dart_sealed"] and result["next_cursor"] is None
    assert result["cursor"] == cursor and result["requests"] == 10
    assert len(result["dart_pages"]) == 9 and len(result["dart_checkpoint"]["pending"]["rows"]) == 900
    assert result["dart_checkpoint"]["committed"]["ids"] == cursor["ids"]


def test_queried_date_does_not_hide_tampered_guard_digest_or_mutate_retained_checkpoint():
    fetch, _, _ = continuation_source()
    cursor = {"source": "DART", "through_date": "2026-10-30", "ids": [], "checked_at": "2026-10-30T01:00:00Z"}
    first = delta.collect_dart_continuation(UNIVERSE, {"items": []}, cursor, "2026-11-01T06:00:00Z", "synthetic", None, transport=fetch)
    cp, proof = deepcopy(first["dart_checkpoint"]), deepcopy(first["dart_pages"][0])
    before = deepcopy(cp); proof["rows"][0][1] = "0"*64
    reset, sealed, error = delta.dart_replay_pages(cp, cursor, "2026-11-01T06:02:00Z", first["dart_catalog"], [proof])
    assert error == "pagination_changed" and not sealed and cp == before
    assert reset["pending"]["next_page"] == 1 and reset["committed"] == before["committed"]
    assert set(before["pending"]["observed"]) <= set(reset["pending"]["observed"])
