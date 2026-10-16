"""Peer selection and arithmetic boundaries, with no network or registry IO."""
from copy import deepcopy
from datetime import date
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "vercel-api" / "api"))
import report_peers as peers
from report_peers import normalized_peers, public_stock_mapping, build_peer_comparison
from report_reader import reader_financials
from report_us_financials import us_periods

NOW = date(2026, 10, 17)
URL = "https://example.org/filing/2026"


def period(**updates):
    row = dict(start="2026-04-01", end="2026-06-30", period_kind="quarter",
               currency="KRW", fs_div="CFS", filed="2026-08-14", accession="filing-1",
               accounting_standard="K-IFRS", source_url=URL,
               revenue=100, op=20, net=-5, ocf=0, capex=2)
    row.update(updates)
    row["metric_sources"] = {k: {"name": k, "start": row["start"], "end": row["end"],
        "currency": row["currency"], "fs_div": row["fs_div"],
        "accession": row["accession"], "source_url": URL} for k in ("revenue", "op", "net", "ocf", "capex")}
    return row


def stock(rows=None, **updates):
    return {"name": "Sample", "industry": "Steel", "financial_evidence": {
        "periods": rows if rows is not None else [period()]}, **updates}


def run(peer=None, target=None, reviewed=None, stocks=None, now=NOW):
    target = target or period()
    return normalized_peers("TARGET", stock([target]), reader_financials([target]),
        stocks if stocks is not None else {"PEER": stock([peer or period()])}, now, reviewed)


def test_exact_alignment_contract_and_provenance():
    result = run()
    assert (result["total"], result["qualified"], result["held"]) == (1, 1, 0)
    row = result["rows"][0]
    assert row["accounting_standard_comparability"] == "matched"
    assert row["numeric_period_alignment"] == "qualified"
    assert row["metrics"]["op_margin"]["value"] == 20
    assert row["metrics"]["net_margin"]["value"] == -5
    assert row["metrics"]["ocf"]["value"] == 0
    assert row["metrics"]["op_margin"]["source"]["denominator"]["source_url"] == URL
    assert result["basis"]["metrics"]["revenue"]["value"] == 100
    assert not row["ranking_allowed"] and not row["median_allowed"]
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("field,value", [
    ("start", "2026-04-02"), ("end", "2026-06-29"),
    ("period_kind", "ytd"), ("currency", "USD"), ("fs_div", "OFS")])
def test_each_alignment_dimension_holds_without_older_target_rollback(field, value):
    p = period(**{field: value})
    result = run(peer=p)
    assert result["held"] == 1
    assert field + "_mismatch" in result["rows"][0]["reasons"]
    assert result["basis"]["end"] == "2026-06-30"
    assert all(m["value"] is None for m in result["rows"][0]["metrics"].values())


def test_prior_common_period_does_not_replace_target_current():
    old = period(start="2025-04-01", end="2025-06-30", filed="2025-08-14")
    target = reader_financials([old, period()])
    result = normalized_peers("TARGET", stock(), target, {"PEER": stock([old])}, NOW)
    assert result["held"] == 1 and result["basis"]["end"] == "2026-06-30"
    assert "missing_exact_target_period" in result["rows"][0]["reasons"]
    assert result["rows"][0]["available_periods"][0]["end"] == old["end"]


@pytest.mark.parametrize("target_unknown,peer_unknown", [(True, False), (False, True), (True, True)])
def test_unknown_accounting_preserves_numbers_and_caveat(target_unknown, peer_unknown):
    target, peer = period(), period()
    if target_unknown:
        target.pop("accounting_standard")
    if peer_unknown:
        peer.pop("accounting_standard")
    result = run(peer, target)
    row = result["rows"][0]
    assert result["qualified"] == 1
    assert row["accounting_standard_comparability"] == "basis_unknown"
    assert row["metrics"]["revenue"]["value"] == 100 and row["caveats"]
    assert not row["ranking_allowed"] and not row["median_allowed"]


def test_known_accounting_mismatch_is_held_even_when_other_basis_matches():
    row = run(period(accounting_standard="US-GAAP"))["rows"][0]
    assert row["status"] == "held"
    assert row["numeric_period_alignment"] == "qualified"
    assert row["accounting_standard_comparability"] == "mismatch"
    assert "accounting_standard_mismatch" in row["reasons"]


@pytest.mark.parametrize("value", [None, "unknown", float("nan"), float("inf"), True, -1])
def test_invalid_revenue_is_not_zero_and_never_denominator(value):
    row = run(period(revenue=value))["rows"][0]
    assert row["metrics"]["revenue"]["value"] is None
    assert row["metrics"]["op_margin"]["value"] is None
    assert row["metrics"]["net_margin"]["value"] is None
    assert row["metrics"]["op"]["value"] == 20
    json.dumps(row, allow_nan=False)


def test_zero_revenue_is_preserved_and_negative_profit_margin_is_allowed():
    metrics = run(period(revenue=0))["rows"][0]["metrics"]
    assert metrics["revenue"]["value"] == 0 and metrics["op_margin"]["value"] is None
    assert run(period(op=-20))["rows"][0]["metrics"]["op_margin"]["value"] == -20


@pytest.mark.parametrize("field,value", [("source_url", "https://example.org/"),
    ("start", "2026-01-01"), ("currency", "USD"), ("fs_div", "OFS"),
    ("accession", "different-filing"), ("name", "")])
def test_metric_provenance_must_match_operands(field, value):
    peer = period()
    peer["metric_sources"]["op"][field] = value
    metrics = run(peer)["rows"][0]["metrics"]
    assert metrics["op"]["value"] is None and metrics["op_margin"]["value"] is None
    assert metrics["revenue"]["value"] == 100


DART_RECEIPT = "20260814003201"
DART_MAIN = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=" + DART_RECEIPT
DART_VIEWER = "https://dart.fss.or.kr/report/viewer.do?rcpNo=" + DART_RECEIPT + "&dcmNo=11536243&eleId=9"
SEC_ACCESSION = "0000018230-26-000046"
SEC_PATH = "https://www.sec.gov/Archives/edgar/data/18230/000001823026000046/"


def filing_period(url, accession):
    row = period(source_url=url, accession=accession)
    for source in row["metric_sources"].values():
        source["source_url"] = url
        source.pop("accession")  # The missing optional field must not bypass URL identity.
    return row


@pytest.mark.parametrize("wrong_url", [
    DART_VIEWER.replace(DART_RECEIPT, "20260814003202"),
    DART_VIEWER + "&rcpNo=" + DART_RECEIPT,
    DART_VIEWER.replace(DART_RECEIPT, ""),
    "https://elsewhere.example/report/viewer.do?rcpNo=" + DART_RECEIPT,
])
def test_wrong_dart_receipt_or_ambiguous_identity_rejects_metric(wrong_url):
    row = filing_period(DART_MAIN, DART_RECEIPT)
    row["metric_sources"]["op"]["source_url"] = wrong_url
    metrics = run(row)["rows"][0]["metrics"]
    assert metrics["op"]["value"] is None and metrics["op_margin"]["value"] is None
    assert metrics["op"]["reason"] == "mismatched_metric_document_identity"
    assert metrics["revenue"]["value"] == 100


@pytest.mark.parametrize("wrong_url", [
    SEC_PATH.replace("/18230/", "/99999/") + "financial.htm",
    SEC_PATH.replace("000001823026000046", "000001823026000047") + "financial.htm",
    SEC_PATH.replace("www.sec.gov", "www.sec.gov.evil.example") + "financial.htm",
])
def test_wrong_sec_issuer_or_accession_rejects_metric_without_source_accession(wrong_url):
    row = filing_period(SEC_PATH + SEC_ACCESSION + "-index.html", SEC_ACCESSION)
    row["metric_sources"]["op"]["source_url"] = wrong_url
    metrics = run(row)["rows"][0]["metrics"]
    assert metrics["op"]["value"] is None and metrics["op_margin"]["value"] is None
    assert metrics["op"]["reason"] == "mismatched_metric_document_identity"
    assert metrics["revenue"]["value"] == 100


@pytest.mark.parametrize("parent,metric,accession", [
    (DART_MAIN, DART_VIEWER, DART_RECEIPT),
    (DART_VIEWER, DART_MAIN, DART_RECEIPT),
    (SEC_PATH + SEC_ACCESSION + "-index.html", SEC_PATH + "cat-20260630.htm", SEC_ACCESSION),
    (SEC_PATH + "cat-20260630.htm", SEC_PATH.replace("www.sec.gov", "sec.gov").replace("/18230/", "/0000018230/") + SEC_ACCESSION + "-index.htm", SEC_ACCESSION),
])
def test_same_filing_allows_different_main_viewer_or_sec_document(parent, metric, accession):
    row = filing_period(parent, accession)
    source = row["metric_sources"]["op"]
    source.update(source_url=metric, account_id="ifrs-full_ProfitLossFromOperatingActivities")
    before = deepcopy(source)
    result = run(row)["rows"][0]
    assert result["metrics"]["op"]["value"] == 20
    assert result["metrics"]["op_margin"]["value"] == 20
    assert result["metrics"]["op"]["source"] == before
    assert row["metric_sources"]["op"] == before


@pytest.mark.parametrize("url,accession,wrong_accession", [
    (DART_MAIN, DART_RECEIPT, "20260814003202"),
    (SEC_PATH + "financial.htm", SEC_ACCESSION, "0000018230-26-000047"),
])
def test_row_accession_must_agree_with_its_own_url(url, accession, wrong_accession):
    row = filing_period(url, accession)
    row["accession"] = wrong_accession
    result = run(row)
    assert result["held"] == 1 and "no_sourced_income" in result["rows"][0]["reasons"]


@pytest.mark.parametrize("url", [URL + "?viewer=1", URL + "/other", URL.replace("example.org", "other.example")])
def test_other_https_requires_exact_document_url(url):
    row = period()
    row["metric_sources"]["op"]["source_url"] = url
    assert run(row)["rows"][0]["metrics"]["op"]["value"] is None


def test_matching_source_accession_cannot_override_wrong_url_and_account_id_is_accepted():
    row = filing_period(DART_MAIN, DART_RECEIPT)
    source = row["metric_sources"]["op"]
    source.pop("name")
    source["account_id"] = "ifrs-full_ProfitLossFromOperatingActivities"
    assert run(row)["rows"][0]["metrics"]["op"]["value"] == 20
    source.update(accession=DART_RECEIPT, source_url=DART_VIEWER.replace(DART_RECEIPT, "20260814003202"))
    assert run(row)["rows"][0]["metrics"]["op"]["value"] is None


def test_no_sourced_income_holds_row_and_target_basis():
    peer = period()
    peer["metric_sources"] = {}
    assert run(peer)["held"] == 1
    result = run(target=peer)
    assert "no_sourced_target_income" in result["basis"]["reasons"]
    assert result["held"] == 1


@pytest.mark.parametrize("field,value,reason", [
    ("filed", None, "missing_filed_date"), ("filed", "2026-10-18", "invalid_filed_date"),
    ("source_url", "", "invalid_or_missing_period_basis"),
    ("fs_div", None, "invalid_or_missing_period_basis")])
def test_missing_and_future_basis(field, value, reason):
    row = run(period(**{field: value}))["rows"][0]
    assert row["status"] == "held"
    assert any(reason in r or field + "_mismatch" == r for r in row["reasons"])


def test_stale_target_cannot_qualify_matching_peers():
    old = period(start="2024-01-01", end="2024-12-31", period_kind="annual", filed="2025-02-01")
    result = run(old, old)
    assert "stale_period" in result["basis"]["reasons"] and result["held"] == 1


def test_auto_cap_excludes_target_and_is_independent_of_name_market_cap():
    stocks = {str(i): stock(name=str(10-i), market_cap=i*1000) for i in range(8)}
    stocks["TARGET"] = stock()
    stocks["OTHER"] = stock(industry="Other")
    result = run(stocks=stocks)
    assert [r["ticker"] for r in result["rows"]] == ["0", "1", "2", "3", "4"]
    assert result["selection"] == {"eligible": 8, "selected": 5, "omitted": 3}
    assert all("직접 경쟁사" in r["selection"]["limitation"] for r in result["rows"])


def test_exact_target_period_after_five_missing_candidates_is_selected_first():
    stocks = {f"A{i}": stock([]) for i in range(5)}
    stocks["ZEXACT"] = stock()
    result = run(stocks=stocks)
    assert [r["ticker"] for r in result["rows"]] == ["ZEXACT", "A0", "A1", "A2", "A3"]
    assert result["qualified"] == 1 and result["selection"]["omitted"] == 1
    assert result["rows"][0]["selection"]["has_exact_target_period"]
    assert result["rows"][0]["selection"]["policy"] == "exact_target_period_then_ticker"
    assert any("기간근거 보유 후보 우선" in n and "경제적 순위" in n for n in result["notes"])


@pytest.mark.parametrize("field,value", [("start", "2026-01-01"), ("end", "2026-03-31"),
    ("period_kind", "ytd"), ("currency", "USD"), ("fs_div", "OFS")])
def test_availability_priority_requires_exact_fields_and_keeps_latest_target(field, value):
    stocks = {f"A{i}": stock([]) for i in range(5)}
    stocks["ZMISMATCH"] = stock([period(**{field: value})])
    result = run(stocks=stocks)
    assert [r["ticker"] for r in result["rows"]] == [f"A{i}" for i in range(5)]
    assert result["basis"]["start"] == "2026-04-01" and result["basis"]["end"] == "2026-06-30"


def test_reviewed_selection_order_is_not_reordered_by_period_availability():
    reviewed = [{"ticker": t, "reason": "Products", "limitation": "Mix", "source_url": URL}
                for t in ("MISSING", "EXACT")]
    result = run(stocks={"MISSING": stock([]), "EXACT": stock()}, reviewed=reviewed)
    assert [r["ticker"] for r in result["rows"]] == ["MISSING", "EXACT"]


@pytest.mark.parametrize("target_ticker,exact_ticker", [("000001", "000999"), ("CAT", "DE")])
def test_producer_peer_sector_precedes_broad_gics(target_ticker, exact_ticker):
    target = stock(industry=None, peer={"sector": "산업기계·컴퓨터"}, gics_ko="산업재")
    stocks = {exact_ticker: stock(industry=None, peer={"sector": "산업기계·컴퓨터"}, gics_ko="산업재"),
        "000002" if target_ticker.isdigit() else "AAL": stock(
            industry=None, peer={"sector": "항공"}, gics_ko="산업재"),
        "000003" if target_ticker.isdigit() else "ABSI": stock(
            industry=None, peer={"sector": "엔지니어링·연구"}, gics_ko="산업재")}
    result = normalized_peers(target_ticker, target, reader_financials([period()]), stocks, NOW)
    assert [r["ticker"] for r in result["rows"]] == [exact_ticker]
    selection = result["rows"][0]["selection"]
    assert selection["field"] == "peer.sector" and "직접 경쟁사" in selection["limitation"]


def test_business_prose_is_not_a_selection_key():
    target = {"business": "Shared business text"}
    result = normalized_peers("T", target, reader_financials([period()]),
                              {"P": stock(industry=None, business=target["business"])}, NOW)
    assert result["total"] == 0


@pytest.mark.parametrize("classification", ["Technology", "소재"])
def test_broad_sector_is_only_an_unreviewed_candidate(classification):
    result = normalized_peers("TARGET", {"sector": classification}, reader_financials([period()]),
        {"P": stock(industry=None, sector=classification)}, NOW)
    assert result["total"] == 1
    assert result["rows"][0]["selection"]["mode"] == "same_industry_candidate"
    assert "직접 경쟁사" in result["rows"][0]["selection"]["limitation"]


def test_no_industry_never_selects_by_name_or_market_cap():
    result = normalized_peers("T", {"name": "Sample", "market_cap": 1}, reader_financials([period()]),
                              {"P": stock()}, NOW)
    assert result["total"] == 0


def test_reviewed_selection_is_authoritative_deduped_and_keeps_missing_candidates():
    reviewed = [{"ticker": t, "reason": "Reviewed product overlap", "limitation": "Different mix",
                 "source_url": URL} for t in ("TARGET", "P", "P", "MISSING")]
    result = run(stocks={"P": stock(industry="Other"), "AUTO": stock()}, reviewed=reviewed)
    assert [r["ticker"] for r in result["rows"]] == ["P", "MISSING"]
    assert result["qualified"] == 1 and result["held"] == 1
    assert result["rows"][0]["selection"]["source_url"] == URL
    assert run(reviewed=[])["total"] == 0
    assert run(reviewed=[{"ticker": "PEER"}])["held"] == 1


def test_latest_filing_is_whole_and_ambiguous_filings_hold():
    old = period(filed="2026-07-01")
    newer = period(revenue=None)
    result = run(stocks={"P": stock([old, newer])})
    assert result["rows"][0]["metrics"]["revenue"]["value"] is None
    assert result["rows"][0]["filed"] == newer["filed"]
    assert run(stocks={"P": stock([period(), period(revenue=999)])})["held"] == 1


def test_us_adapter_output_can_be_passed_without_inventing_scope_or_standard():
    raw = {"meta": {"cik": 1, "currency": "USD"}, "series_quarterly": {"revenue": [{
        "tag": "Revenues", "start": "2026-04-01", "end": "2026-06-30", "unit": "USD",
        "form": "10-Q", "accn": "0000000001-26-000001", "filed": "2026-08-01", "val": 100}]}}
    facts = {"cik": 1, "facts": {"us-gaap": {"Revenues": {"units": {"USD": [{
        "start": "2026-04-01", "end": "2026-06-30", "form": "10-Q",
        "accn": "0000000001-26-000001", "filed": "2026-08-01", "val": 100}]}}}}}
    rows = us_periods(raw, facts)
    result = normalized_peers("T", stock(rows), reader_financials(rows), {"P": stock(rows)}, NOW)
    assert result["qualified"] == 1
    assert result["rows"][0]["accounting_standard_comparability"] == "basis_unknown"
    assert result["basis"]["fs_div"] == "ENTITY"
    assert run(stocks={"P": stock(us_periods(raw))})["held"] == 1


def test_deterministic_detached_result_and_missing_target():
    target, stocks = stock(), {"P": stock()}
    reader = reader_financials(target["financial_evidence"]["periods"])
    before = deepcopy((target, reader, stocks))
    a = normalized_peers("T", target, reader, stocks, NOW)
    b = normalized_peers("T", target, reader, stocks, NOW)
    assert a == b and (target, reader, stocks) == before
    a["rows"][0]["metrics"]["revenue"]["source"]["name"] = "changed"
    assert (target, reader, stocks) == before
    assert normalized_peers("T", target, {}, stocks, NOW)["held"] == 1


@pytest.mark.parametrize("wrap", [lambda x: x, lambda x: {"stocks": x}, lambda x: {"items": x}])
@pytest.mark.parametrize("as_list", [False, True])
def test_public_mapping_and_helper_accept_dict_and_list(wrap, as_list):
    raw = [stock(ticker="P")] if as_list else {"P": stock()}
    before = deepcopy(raw)
    result = build_peer_comparison("T", stock(), reader_financials([period()]), wrap(raw), NOW)
    assert result["qualified"] == 1 and result["rows"][0]["ticker"] == "P"
    assert result["rows"][0]["enrichment"] == "existing_exact_period"
    assert result["rows"][0]["selection"]["mode"] == "same_industry_candidate"
    assert raw == before


def test_mapping_rejects_routes_malformed_records_and_duplicate_identity():
    assert public_stock_mapping(None) == {}
    assert public_stock_mapping({"stocks": None}) == {}
    raw = [None, {"name": "No ticker"}, stock(ticker="../bad"),
           stock(ticker="p"), stock(ticker="P", name="Conflicting company"), stock(ticker="P")]
    mapping = public_stock_mapping(raw)
    assert list(mapping) == ["P"]
    assert mapping["P"]["_peer_mapping_error"] == "ambiguous_stock_identity"
    assert public_stock_mapping({"P": stock(ticker="OTHER")})["P"]["_peer_mapping_error"] == "candidate_identity_mismatch"


def us_pair(ticker="P", cik=1):
    accession = f"{cik:010d}-26-000001"
    fact = {"start": "2026-04-01", "end": "2026-06-30", "form": "10-Q",
            "accn": accession, "filed": "2026-08-01", "val": 100}
    raw = {"ticker": ticker, "meta": {"cik": cik, "currency": "USD"},
           "series_quarterly": {"revenue": [{**fact, "tag": "Revenues", "unit": "USD"}]}}
    facts = {"cik": cik, "facts": {"us-gaap": {"Revenues": {"units": {"USD": [fact]}}}}}
    return raw, facts


def us_reader():
    return reader_financials([period(currency="USD", fs_div="ENTITY", accounting_standard=None)])


def test_us_enrichment_bounded_three_candidates_six_calls_and_preserves_selection():
    calls = []
    def fetch(route):
        calls.append(route)
        if route.startswith("us_financials/"):
            ticker = route.split("/")[1].removesuffix(".json")
            return us_pair(ticker)[0]
        assert route == "sec-companyfacts/0000000001.json"
        return us_pair()[1]
    doc = {"stocks": {f"P{i}": stock([]) for i in range(9)}}
    before = deepcopy(doc)
    result = build_peer_comparison("T", stock(), us_reader(), doc, NOW, fetch=fetch)
    assert (result["total"], result["qualified"], result["held"]) == (5, 3, 2)
    assert result["selection"] == {"eligible": 9, "selected": 5, "omitted": 4}
    assert len(calls) == 6 <= 2 * result["total"]
    assert sum(r.startswith("us_financials/") for r in calls) == 3
    assert result["enrichment"]["max_workers"] == 3
    assert all("us_enrichment_cap_reached" in r["reasons"] for r in result["rows"][3:])
    assert all(r["selection"]["mode"] == "same_industry_candidate" for r in result["rows"])
    assert doc == before


def test_helper_keeps_selection_order_and_provenance_after_enrichment_reorders_availability():
    target_period = period(currency="USD", fs_div="ENTITY", accounting_standard=None)
    doc = {"ZEXISTING": stock([target_period]), "AENRICH": stock([]), "BMISSING": stock([])}
    def fetch(route):
        if route == "us_financials/AENRICH.json":
            return us_pair("AENRICH")[0]
        if route.startswith("sec-companyfacts/"):
            return us_pair()[1]
        raise ValueError("missing frozen response")
    result = build_peer_comparison("T", stock(), us_reader(), doc, NOW, fetch=fetch)
    assert [r["ticker"] for r in result["rows"]] == ["ZEXISTING", "AENRICH", "BMISSING"]
    assert result["rows"][0]["selection"]["has_exact_target_period"] is True
    assert result["rows"][1]["selection"]["has_exact_target_period"] is False
    assert result["rows"][1]["enrichment"] == "us_enriched"
    assert result["qualified"] == 2 and result["held"] == 1


@pytest.mark.parametrize("failure", ["raw_exception", "facts_exception", "wrong_ticker", "bad_cik",
                                    "wrong_public_cik", "wrong_facts_cik", "malformed_raw", "malformed_facts"])
def test_failed_us_fetch_and_identity_stay_held_without_extra_fetch(failure):
    calls = []
    raw, facts = us_pair()
    if failure == "wrong_ticker":
        raw["ticker"] = "OTHER"
    if failure == "bad_cik":
        raw["meta"]["cik"] = "../123"
    if failure == "wrong_facts_cik":
        facts["cik"] = 2
    def fetch(route):
        calls.append(route)
        if route.startswith("us_financials/"):
            if failure == "raw_exception":
                raise RuntimeError("sensitive-provider-url")
            return [] if failure == "malformed_raw" else raw
        if failure == "facts_exception":
            raise RuntimeError("sensitive-provider-url")
        return [] if failure == "malformed_facts" else facts
    doc = {"P": stock([], cik=2)} if failure == "wrong_public_cik" else {"P": stock([])}
    result = build_peer_comparison("T", stock(), us_reader(), doc, NOW, fetch=fetch)
    assert result["held"] == 1 and result["qualified"] == 0
    assert 1 <= len(calls) <= 2
    assert "sensitive-provider-url" not in json.dumps(result)
    if failure in ("raw_exception", "wrong_ticker", "bad_cik", "wrong_public_cik", "malformed_raw"):
        assert len(calls) == 1


def test_us_no_fetch_for_existing_exact_basis_or_unusable_target():
    def fail(route):
        pytest.fail(f"unexpected fetch: {route}")
    target = period(currency="USD", fs_div="ENTITY", accounting_standard=None)
    doc = {"P": stock([target])}
    assert build_peer_comparison("T", stock(), us_reader(), doc, NOW, fetch=fail)["qualified"] == 1
    assert build_peer_comparison("T", stock(), {}, {"P": stock([])}, NOW, fetch=fail)["held"] == 1
    result = build_peer_comparison("T", stock(), us_reader(), {"P": stock([])}, NOW)
    assert "fetch_unavailable" in result["rows"][0]["reasons"]


def test_us_enriched_period_mismatch_does_not_use_older_target():
    raw, facts = us_pair()
    facts["facts"]["us-gaap"]["Revenues"]["units"]["USD"][0].update(
        start="2026-01-01", end="2026-03-31")
    result = build_peer_comparison("T", stock(), us_reader(), {"P": stock([])}, NOW,
                                  fetch=lambda route: raw if route.startswith("us_financials/") else facts)
    assert result["held"] == 1 and result["basis"]["end"] == "2026-06-30"
    assert "missing_exact_target_period" in result["rows"][0]["reasons"]


def test_reviewed_helper_is_capped_and_does_not_fetch_invalid_or_missing_identity():
    reviewed = [{"ticker": t, "reason": "Products", "limitation": "Mix", "source_url": URL}
                for t in ["MISSING", "BAD", "WRONG", "P1", "P2", "P3"]]
    reviewed[1]["source_url"] = ""
    calls = []
    doc = {"BAD": stock([]), "WRONG": stock([], ticker="OTHER"),
           "P1": stock([]), "P2": stock([]), "P3": stock([])}
    def fetch(route):
        calls.append(route)
        raise RuntimeError("failed")
    result = build_peer_comparison("T", stock(), us_reader(), doc, NOW, reviewed, fetch)
    assert result["total"] == result["held"] == 5
    assert result["selection"] == {"eligible": 6, "selected": 5, "omitted": 1}
    assert sorted(calls) == ["us_financials/P1.json", "us_financials/P2.json"]
    assert all(r["selection"]["mode"] == "reviewed" for r in result["rows"])


def test_kr_helper_uses_existing_local_registry_without_network():
    # Existing bounded reviewed entry, independently covered by KR review tests.
    reviewed_stock = {"name": "대한제강", "corp_code": "00113225", "industry": "Steel"}
    target = period(start="2026-01-01", period_kind="ytd", accounting_standard=None)
    result = build_peer_comparison("000001", stock(), reader_financials([target]),
        {"stocks": {"084010": reviewed_stock}}, NOW,
        fetch=lambda route: pytest.fail(f"KR must not fetch: {route}"))
    assert result["qualified"] == 1
    row = result["rows"][0]
    assert row["enrichment"] == "kr_review_applied"
    assert row["metrics"]["revenue"]["value"] == 692069629955
    assert row["metrics"]["revenue"]["source"]["source_url"].startswith("https://dart.fss.or.kr/")
    assert "ticker" not in reviewed_stock


def test_kr_review_failure_and_no_entry_stay_held(monkeypatch):
    def fail(*args):
        raise ValueError("local registry unreadable")
    monkeypatch.setattr(peers, "reviewed_financials", fail)
    result = build_peer_comparison("000001", stock(), reader_financials([period()]),
                                   {"000002": stock([])}, NOW)
    assert result["held"] == 1 and "kr_review_failed" in result["rows"][0]["reasons"]


@pytest.mark.parametrize("financial", [
    {"is_financial": True}, {"meta": {"is_financial": True}},
    {"sector": "Financials"}, {"industry": "Banks - Regional"},
    {"industry": "Insurance - Life"}, {"gics_ko": "은행"},
    {"sector": "보험"}, {"gics_industry": "Capital Markets"},
    {"is_financial": False, "sector": "Financial Services"}])
def test_financial_comparison_suppresses_margins_but_keeps_sourced_amounts(financial):
    # Reviewed selection can cross classifications; the margin guard still applies.
    reviewed = [{"ticker": "P", "reason": "Reviewed overlap", "limitation": "Business mix", "source_url": URL}]
    result = build_peer_comparison("T", stock(), reader_financials([period()]),
                                   {"P": stock(**financial)}, NOW, reviewed)
    assert result["qualified"] == 1
    assert not result["basis"]["margins_allowed"]
    row = result["rows"][0]
    assert row["financial_sector"]["is_financial"]
    assert row["financial_sector"]["basis"]
    for metrics in (row["metrics"], result["basis"]["metrics"]):
        assert metrics["revenue"]["value"] == 100
        assert metrics["op"]["value"] == 20 and metrics["net"]["value"] == -5
        for key in ("op_margin", "net_margin"):
            assert metrics[key]["value"] is None
            assert metrics[key]["reason"] == "financial_sector_margin_not_comparable"
    assert any("금융업" in c for c in row["caveats"])


def test_target_financial_flag_suppresses_peer_and_target_margins_in_pure_function():
    result = normalized_peers("T", stock(is_financial=True), reader_financials([period()]),
                              {"P": stock()}, NOW)
    assert result["basis"]["financial_sector"]["is_financial"]
    assert result["rows"][0]["metrics"]["op_margin"]["value"] is None
    assert result["basis"]["metrics"]["op_margin"]["value"] is None
    assert result["qualified"] == 1


def test_us_verified_meta_financial_flag_propagates_without_changing_signature():
    raw, facts = us_pair()
    raw["meta"]["is_financial"] = True
    result = build_peer_comparison("T", stock(), us_reader(), {"P": stock([])}, NOW,
        fetch=lambda route: raw if route.startswith("us_financials/") else facts)
    assert result["qualified"] == 1
    assert result["rows"][0]["financial_sector"]["basis"] == [
        {"field": "meta.is_financial", "value": True}]
    assert result["basis"]["metrics"]["op_margin"]["reason"] == "financial_sector_margin_not_comparable"


def test_nonfinancial_name_does_not_trigger_financial_margin_guard():
    result = build_peer_comparison("T", stock(), reader_financials([period()]),
        {"P": stock(name="Bank Insurance Equipment", is_financial=False)}, NOW)
    assert result["basis"]["margins_allowed"]
    assert result["rows"][0]["metrics"]["op_margin"]["value"] == 20
    assert result["rows"][0]["financial_sector"]["status"] == "not_identified"
