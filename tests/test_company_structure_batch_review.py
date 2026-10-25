"""Public exhibit layout variants; no source calls or ownership inference."""
import pytest
import json
import gzip
import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path
import yaml

from api.intelligence.company_structure_sec import PARSER_REVISION, parse_exhibit, find_exhibit
from api.collectors.company_structure_us_refresh import latest_metadata
from api.collectors import company_structure_us_refresh as refresh_core

META = {"cik": "0000004904", "accession": "0000004904-26-000018",
        "filedDate": "2026-02-12", "periodEnd": "2025-12-31",
        "url": "https://www.sec.gov/Archives/edgar/data/4904/000000490426000018/ex21.htm",
        "issuerName": "American Electric Power Company, Inc."}

CBT_META = {"cik": "0000016040", "accession": "0001193125-25-292412",
            "filedDate": "2025-11-24", "periodEnd": "2025-09-30",
            "url": "https://www.sec.gov/Archives/edgar/data/16040/000119312525292412/cbt-ex21.htm",
            "issuerName": "Cabot Corp"}

AVT_META = {"cik": "0000008858", "accession": "0001104659-26-096346",
            "filedDate": "2026-08-14", "periodEnd": "2026-06-27",
            "url": "https://www.sec.gov/Archives/edgar/data/8858/000110465926096346/avt-20260627xex21d1.htm",
            "issuerName": "AVNET INC"}

CPK_META = {"cik": "0000019745", "accession": "0001628280-26-011753",
            "filedDate": "2026-02-25", "periodEnd": "2025-12-31",
            "url": "https://www.sec.gov/Archives/edgar/data/19745/000162828026011753/cpk12312025ex-21.htm",
            "issuerName": "CHESAPEAKE UTILITIES CORP"}

CMI_META = {"cik": "0000026172", "accession": "0000026172-26-000009",
            "filedDate": "2026-02-10", "periodEnd": "2025-12-31",
            "url": "https://www.sec.gov/Archives/edgar/data/26172/000002617226000009/cmi202510-kex21.htm",
            "issuerName": "CUMMINS INC"}


def _statement_exhibit(*, title="List of Subsidiaries of American Electric Power Company, Inc.",
                       preamble="", rows=None, after=""):
    if rows is None:
        rows = ["First Company LLC, a Delaware limited liability company",
                "Second Company, Inc., an Ohio corporation"]
    return ("<body><p>Exhibit 21.1</p><p>" + title + "</p>" + preamble +
            "".join(f"<p>{row}</p>" for row in rows) + after + "</body>")


def test_issuer_bound_flat_statement_list_has_only_source_rows():
    result = parse_exhibit(_statement_exhibit(), META)
    assert result["status"] == "parsed"
    assert [row["name"] for row in result["rows"]] == ["First Company LLC", "Second Company, Inc."]
    assert [row["jurisdiction"] for row in result["rows"]] == ["Delaware", "Ohio"]
    assert result["scope"] == "reported-subsidiary-list-not-exhaustive"
    assert all(row["ownershipPct"] is None and row["directOwnership"] == "unspecified"
               for row in result["rows"])


def test_numbered_statement_list_requires_matching_as_of_and_count():
    preamble = ("<p>As of December 31, 2025, American Electric Power Company, Inc. "
                "had two sole subsidiaries:</p>")
    rows = ["1. First Company LLC, a Delaware limited liability company;",
            "2. Second Company, Inc., an Ohio corporation."]
    result = parse_exhibit(_statement_exhibit(title="Subsidiaries of American Electric Power Company, Inc.",
                                               preamble=preamble, rows=rows), META)
    assert result["status"] == "parsed"
    assert len(result["rows"]) == 2


@pytest.mark.parametrize("change", [
    {"title": "List of Subsidiaries of Other Inc."},
    {"title": "Former Subsidiaries of American Electric Power Company, Inc."},
    {"preamble": "<p>As of January 1, 2026, American Electric Power Company, Inc. had two sole subsidiaries:</p>"},
    {"preamble": "<p>As of December 31, 2025, Other Inc. had two sole subsidiaries:</p>"},
    {"preamble": "<p>As of December 31, 2025, American Electric Power Company, Inc. had three sole subsidiaries:</p>"},
    {"rows": ["First Company LLC, a Delaware limited liability company",
              "Second Company, Inc., an Ohio corporation (formerly Other Inc.)"]},
    {"rows": ["First Company LLC Second Company Inc., a Delaware limited liability company"]},
    {"rows": ["First Company and Second Company Inc., a Delaware corporation"]},
    {"rows": ["First Company DBA Second Company LLC, a Delaware limited liability company"]},
    {"rows": ["First Company LLC, a Delaware limited liability company (owned 75% by Other Inc.)"]},
    {"rows": ["First Company LLC, a Delaware limited liability company",
              "2. Second Company, Inc., an Ohio corporation"]},
    {"rows": ["First Company LLC, a limited liability company"]},
    {"after": "<p>First Company LLC is owned by Second Company, Inc.</p>"},
    {"after": "<p>Additional subsidiaries are listed below.</p>"},
    {"after": "<p>Formerly Other Inc.</p>"},
    {"after": "Unbound extra sentence."},
    {"after": "<table><tr><td>Other Subsidiary LLC</td><td>Ohio</td></tr></table>"},
])
def test_flat_statement_near_misses_remain_held(change):
    result = parse_exhibit(_statement_exhibit(**change), META)
    assert result["status"] == "needs-review"
    assert result["rows"] == []


@pytest.mark.parametrize("issuer_name", [None, "Other Inc."])
def test_flat_statement_requires_exact_metadata_issuer(issuer_name):
    result = parse_exhibit(_statement_exhibit(), {**META, "issuerName": issuer_name})
    assert result["status"] == "needs-review"


@pytest.mark.parametrize("ticker,cik,accession,filed,period,issuer,digest,filename,status,rows", [
    ("AXGN", "0000805928", "0000805928-26-000031", "2026-02-24", "2025-12-31", "Axogen, Inc.",
     "4cc8d718981828fc89e3e5829a8cabbb06bdd804f76bac9c9df5119c28352750", "ex211subsidiariesofaxogen1.htm", "parsed", 4),
    ("FWDI", "0000038264", "0001683168-25-009068", "2025-12-11", "2025-09-30", "Forward Industries, Inc.",
     "9c9c89e7a67506e0fdc4b1754f320727b39b0e1e893891e7057c4f73564a1af2", "forward_ex2101.htm", "parsed", 4),
    ("CASY", "0000726958", "0000726958-26-000046", "2026-06-22", "2026-04-30", "CASEYS GENERAL STORES INC",
     "93fca8f42949c331eae1261c0fc78f653a7da281bb5b07d076abbdc467437a4e", "casy-ex211_2026430xq4.htm", "needs-review", 0),
    ("TOL", "0000794170", "0000794170-25-000112", "2025-12-19", "2025-10-31", "Toll Brothers, Inc.",
     "a0f8ad6bba577fa3b964a9b26d15c9c25e429f8d9822ef847b7f117cf8a17d01", "tol-20251031x10kxex21.htm", "needs-review", 0),
])
def test_saved_flat_statement_originals(ticker, cik, accession, filed, period, issuer, digest, filename, status, rows):
    cache_dir = os.environ.get("SEC_EXHIBIT_CACHE_DIR")
    if not cache_dir:
        pytest.skip("set SEC_EXHIBIT_CACHE_DIR for offline original checks")
    raw = gzip.decompress((Path(cache_dir) / f"{digest}.gz").read_bytes())
    assert hashlib.sha256(raw).hexdigest() == digest
    url = (f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
           f"{accession.replace('-', '')}/{filename}")
    result = parse_exhibit(raw, {"cik": cik, "accession": accession, "filedDate": filed,
                                 "periodEnd": period, "url": url, "issuerName": issuer})
    assert result["parserRevision"] == PARSER_REVISION
    assert (result["status"], len(result["rows"])) == (status, rows)
    assert result["scope"] == "reported-subsidiary-list-not-exhaustive"
    assert all(row["ownershipPct"] is None and row["directOwnership"] == "unspecified"
               for row in result["rows"])


def _flat_table_exhibit(*, title="Subsidiaries of American Electric Power Company, Inc.",
                        heading="Name", jurisdiction="Jurisdiction", row="First Company LLC",
                        place="Delaware", after="", row_spans=('3', '3', '3')):
    values = [f"<td colspan='{row_spans[0]}'>{row}</td>",
              f"<td colspan='{row_spans[1]}'></td>",
              f"<td colspan='{row_spans[2]}'>{place}</td>"]
    return (f"<body><p>Exhibit 21.1</p><p>{title}</p><table>"
            "<tr><td></td><td></td><td></td><td></td><td></td><td></td>"
            "<td></td><td></td><td></td></tr>"
            "<tr><td colspan='3'></td><td colspan='3'></td><td colspan='3'></td></tr>"
            "<tr><td colspan='3'></td><td colspan='3'></td><td colspan='3'></td></tr>"
            f"<tr><td colspan='3'>{heading}</td><td colspan='3'></td>"
            f"<td colspan='3'>{jurisdiction}</td></tr>"
            f"<tr>{''.join(values)}</tr></table>{after}</body>")


def test_exact_issuer_flat_table_accepts_late_header_without_parent_inference():
    result = parse_exhibit(_flat_table_exhibit(), META)
    assert result["status"] == "parsed"
    assert [(r["name"], r["jurisdiction"]) for r in result["rows"]] == [
        ("First Company LLC", "Delaware")]
    assert result["rows"][0]["ownershipPct"] is None
    assert result["rows"][0]["directOwnership"] == "unspecified"
    assert result["scope"] == "reported-subsidiary-list-not-exhaustive"


def test_flat_table_date_mismatch_in_name_cannot_bypass_common_as_of_guard():
    result = parse_exhibit(_flat_table_exhibit(
        row="Glumac as of January 1, 2024", place="California"), META)
    assert result["status"] == "needs-review"
    assert result["reviewReason"] == "exhibit-as-of-differs-from-period-end"
    assert result["statedAsOf"] == "2024-01-01"
    assert result["rows"] == []


@pytest.mark.parametrize("change", [
    {"title": "Subsidiaries of Other Inc."},
    {"title": "Former Subsidiaries of American Electric Power Company, Inc."},
    {"title": "Subsidiaries of American Electric Power Company, Inc. as of January 1, 2026"},
    {"heading": "Trade Name"},
    {"jurisdiction": "Amount"},
    {"place": "USD"},
    {"place": "Delaware 75%"},
    {"row": "First Company LLC (75%)"},
    {"row": "First Company LLC (2)"},
    {"row": "First Company LLC Second Company Inc."},
    {"row": "First Company LLC Other Products"},
    {"row": "First Company LLC d/b/a Other Company"},
    {"row": "First Company LLC formerly Other Company"},
    {"after": "<p>Second Company LLC is owned by First Company LLC.</p>"},
    {"after": "<table><tr><td>Second Company LLC</td><td>Ohio</td></tr></table>"},
    {"row_spans": ('3', '4', '2')},
])
def test_flat_table_near_misses_remain_held_without_partial_rows(change):
    result = parse_exhibit(_flat_table_exhibit(**change), META)
    assert result["status"] == "needs-review"
    assert result["rows"] == []


@pytest.mark.parametrize("issuer_name", [None, "Other Inc."])
def test_flat_table_needs_matching_metadata_issuer(issuer_name):
    result = parse_exhibit(_flat_table_exhibit(), {**META, "issuerName": issuer_name})
    assert result["status"] == "needs-review"


@pytest.mark.parametrize("omitted_name", ["Example Properties Trust", "Foreign Systems Ltd",
                                               "Branch Technologies, Inc.", "Total Solutions LLC"])
def test_issuer_bound_table_does_not_silently_omit_populated_entity_rows(omitted_name):
    html = ("<p>Subsidiaries of American Electric Power Company, Inc.</p>"
            "<table><tr><th>Name</th><th>Jurisdiction</th></tr>"
            f"<tr><td>{omitted_name}</td><td>Delaware</td></tr>"
            "<tr><td>Other Company LLC</td><td>Ohio</td></tr></table>")
    result = parse_exhibit(html, META)
    assert (result["status"], result["reviewReason"], result["rows"]) == (
        "needs-review", "partial-table-row-omission", [])


def test_saved_svc_trust_rows_hold_entire_exhibit_without_partial_output():
    cache_dir = os.environ.get("SEC_EXHIBIT_CACHE_DIR")
    if not cache_dir:
        pytest.skip("set SEC_EXHIBIT_CACHE_DIR for the offline saved-original check")
    digest = "85b5dd8d8ab3ed8b565df0d9b9b588a26433545f76b46a1663c860932b466311"
    raw = gzip.decompress((Path(cache_dir) / f"{digest}.gz").read_bytes())
    assert hashlib.sha256(raw).hexdigest() == digest
    result = parse_exhibit(raw, {
        "cik": "0000945394", "accession": "0000945394-26-000012",
        "filedDate": "2026-02-25", "periodEnd": "2025-12-31",
        "url": "https://www.sec.gov/Archives/edgar/data/945394/000094539426000012/svc_123125xex211subsidiary.htm",
        "issuerName": "Service Properties Trust",
    })
    assert (result["status"], result["reviewReason"], result["rows"]) == (
        "needs-review", "partial-table-row-omission", [])


def _registrant_pages(title="American Electric Power Company, Inc. Subsidiaries of the Registrant",
                      gap="", second_name="Second Company GmbH"):
    header = "<tr><td>Name of Company</td><td>Jurisdiction</td></tr>"
    first = f"<table>{header}<tr><td>First Company LLC</td><td>Delaware</td></tr></table>"
    second = f"<table>{header}<tr><td>{second_name}</td><td>Germany</td></tr></table>"
    return f"<p>{title}</p>{first}{gap}{second}"


def _blank_name_exhibit(title="Subsidiaries of American Electric Power Company, Inc.",
                        name="First Company LLC", after=""):
    return (f"<p>{title}</p><table><tr><td></td><td>Jurisdiction of Incorporation</td></tr>"
            f"<tr><td>{name}</td><td>Delaware</td></tr></table>{after}")


def test_exact_registrant_title_continues_identical_headers_without_direct_parent_inference():
    result = parse_exhibit(_registrant_pages(), META)
    assert result["status"] == "parsed"
    assert [row["name"] for row in result["rows"]] == ["First Company LLC", "Second Company GmbH"]
    assert [row["sourceRow"]["tableIndex"] for row in result["rows"]] == [0, 1]
    assert all(row["ownershipPct"] is None and row["directOwnership"] == "unspecified"
               for row in result["rows"])


@pytest.mark.parametrize("changes,reason", [
    ({"title": "Subsidiaries of the Registrant"}, "multiple-tables-issuer-scope-unbound"),
    ({"title": "Other Inc. Subsidiaries of the Registrant"}, "multiple-tables-issuer-scope-unbound"),
    ({"gap": "<p>Subsidiaries of Other Inc.</p>"}, "continuation-scope-text"),
    ({"gap": "<p>Joint ventures</p>"}, "continuation-scope-text"),
    ({"title": "American Electric Power Company, Inc. Subsidiaries of the Registrant As of January 1, 2026"},
     "exhibit-as-of-differs-from-period-end"),
    ({"second_name": "Second Company GmbH Other Products"}, "ambiguous-row-binding"),
    ({"second_name": "Second Company GmbH (7)"}, "ambiguous-row-binding"),
])
def test_registrant_page_near_misses_remain_held(changes, reason):
    result = parse_exhibit(_registrant_pages(**changes), META)
    assert result["status"] == "needs-review"
    assert result["reviewReason"] == reason


@pytest.mark.parametrize("issuer_name", [None, "Other Inc."])
def test_registrant_page_needs_matching_metadata_issuer(issuer_name):
    result = parse_exhibit(_registrant_pages(), {**META, "issuerName": issuer_name})
    assert result["status"] == "needs-review"
    assert result["reviewReason"] == "multiple-tables-issuer-scope-unbound"


def test_single_blank_name_header_requires_exact_issuer_and_keeps_nonexhaustive_scope():
    result = parse_exhibit(_blank_name_exhibit(), META)
    assert result["status"] == "parsed"
    assert len(result["rows"]) == 1
    assert result["rows"][0]["name"] == "First Company LLC"
    assert result["scope"] == "reported-subsidiary-list-not-exhaustive"
    assert result["rows"][0]["directOwnership"] == "unspecified"


def test_blank_header_omission_note_never_accepts_another_issuer_or_extra_scope():
    note = ("* Pursuant to Item 601(b)(21)(ii) of Regulation S-K, the names of other subsidiaries of "
            + META["issuerName"] + " are omitted because, considered in the aggregate, they would not constitute "
            "a significant subsidiary as of the end of the year covered by this report.")
    parsed = parse_exhibit(_blank_name_exhibit(after=f"<p>{note}</p>"), META)
    assert parsed["status"] == "parsed"
    assert parsed["scope"] == "reported-subsidiary-list-not-exhaustive"
    for invalid in (note.replace(META["issuerName"], "Other Inc."), note + " Ownership was sold after year end."):
        held = parse_exhibit(_blank_name_exhibit(after=f"<p>{invalid}</p>"), META)
        assert held["status"] == "needs-review"
        assert held["reviewReason"] == "continuation-scope-text"


@pytest.mark.parametrize("html,reason", [
    (_blank_name_exhibit(title="Subsidiaries of the Registrant"), "issuer-scope-unbound"),
    (_blank_name_exhibit(title="Subsidiaries of Other Inc."), "issuer-scope-unbound"),
    (_blank_name_exhibit(title="Former Subsidiaries of American Electric Power Company, Inc."),
     "issuer-scope-unbound"),
    (_blank_name_exhibit(title="Other Inc. Subsidiaries of American Electric Power Company, Inc."),
     "issuer-scope-unbound"),
    (_blank_name_exhibit(after="<p>Subsidiaries of Other Inc.</p>"), "continuation-scope-text"),
    (_blank_name_exhibit(title="Subsidiaries of American Electric Power Company, Inc. As of January 1, 2026"),
     "issuer-scope-unbound"),
    (_blank_name_exhibit(name="First Company LLC (7)"), "ambiguous-row-binding"),
    (_blank_name_exhibit(name="First Company LLC (57.5%)"), "ambiguous-row-binding"),
])
def test_blank_name_header_near_misses_remain_held(html, reason):
    result = parse_exhibit(html, META)
    assert result["status"] == "needs-review"
    assert result["reviewReason"] == reason


@pytest.mark.parametrize("issuer_name", [None, "Other Inc."])
def test_blank_name_header_needs_matching_metadata_issuer(issuer_name):
    result = parse_exhibit(_blank_name_exhibit(), {**META, "issuerName": issuer_name})
    assert result["status"] == "needs-review"
    assert result["reviewReason"] == "issuer-scope-unbound"


@pytest.mark.parametrize("ticker,digest,status,reason,row_count", [
    ("PATK", "7ddabb4bda869511f1066d6022ea8f4d019ff16b696d784c6b79a2fbe65e89d2",
     "needs-review", "ambiguous-row-binding", 57),
    ("AAPL", "07440f57317859d67a3aa728a976f4711163ac8d31e2a09b0fda60ea8d56b71d",
     "parsed", None, 19),
    ("ADBE", "f01631480cdb7d83a321edff4d1c60add066254a2f8a93e34412123c2f838112",
     "needs-review", "ambiguous-row-binding", 58),
    ("IBCP", "80a5da7350153c46956b67d9ae36f59a1e3b0f7092299c09ca34582266bed8da",
     "needs-review", "issuer-scope-unbound", 0),
    ("WABC", "76b317d1257e55f762bb88686c5120f0049dcc46372e4d5065e1f8c7a09d0a61",
     "needs-review", "issuer-scope-unbound", 0),
    ("AORT", "b91b2dda6eec55fbb3bea369f2aabad291e996c5065cb97d880bbcca9c41007d",
     "parsed", None, 38),
    ("TTEK", "11c9be71d0d8acb874f96667ae1b608dd52c93e589526adfa5b46580d20297ab",
     "parsed", None, 24),
    ("UNP", "6eeb75646bacabf9d94dc58f64d11b7884f698aa14b4f77582d5f896375b3146",
     "parsed", None, 1),
    ("POWL", "06f1c7892f06925ceba0505361a5887798ed8ce59f2d7a00acc88671770f2eeb",
     "parsed", None, 15),
    ("HWC", "52aae9fd8dea41ff4db612869b511f4462ae0a7137062a9874fd53ff9d3bc2d1",
     "parsed", None, 6),
])
def test_saved_originals_keep_source_hash_and_review_boundary(ticker, digest, status, reason, row_count):
    cache_dir = os.environ.get("SEC_EXHIBIT_CACHE_DIR")
    if not cache_dir:
        pytest.skip("set SEC_EXHIBIT_CACHE_DIR for the offline saved-original check")
    raw = gzip.decompress((Path(cache_dir) / f"{digest}.gz").read_bytes())
    assert hashlib.sha256(raw).hexdigest() == digest
    ledger = json.loads((Path(__file__).resolve().parents[1] /
                         "data/member_map_company_structure_us_sources.json").read_text())
    cik, issuer = next((cik, item) for cik, item in ledger["issuers"].items()
                       if ticker in item.get("tickerAliases", []))
    review, filing = issuer.get("reviewExhibit") or issuer.get("exhibit"), issuer["filingMetadata"]
    assert review["documentSha256"] == digest
    result = parse_exhibit(raw, {"cik": cik, "accession": filing["accession"],
                                 "filedDate": filing["filed_date"], "periodEnd": filing["period_end"],
                                 "url": review["url"], "issuerName": filing["issuer_name"]})
    assert result["parserRevision"] == PARSER_REVISION
    assert (result["status"], result.get("reviewReason"), len(result["rows"])) == (status, reason, row_count)
    assert result["scope"] == "reported-subsidiary-list-not-exhaustive"
    if ticker == "PATK":
        assert not any("Hyperform" in row["name"] for row in result["rows"])
    if ticker == "AAPL":
        assert all(row["ownershipPct"] is None and row["directOwnership"] == "unspecified"
                   for row in result["rows"])


def avt_exhibit(*, prefix="<p>Avnet, Inc.</p><p>Foreign and Domestic Subsidiaries</p>",
                gap="", continuation_name="Avnet Philippines Pty Ltd., Inc.",
                continuation_country="Philippines", extra_cell=""):
    # Exact AVT Exhibit 21.1 header and representative rows from the saved
    # four-table source. Each table is on its own matching page DIV, with an
    # explicit page-break HR between pages in the archived exhibit.
    page = '<div style="max-width:100%;padding-left:11.76%;padding-right:11.76%;position:relative;">'
    break_hr = '<hr style="page-break-after:always;">'
    return ("<body>" + prefix + page
            + "<table><tr><td>Company Name</td><td>Country</td></tr>"
              "<tr><td>Avnet (Asia Pacific Holdings) Limited</td><td>Hong Kong</td></tr>"
              "<tr><td>Avnet (Holdings) Ltd</td><td>United Kingdom</td></tr></table></div>"
            + break_hr
            + gap
            + page + "<table>"
            + f"<tr><td>{continuation_name}</td><td>{continuation_country}</td>{extra_cell}</tr>"
              "<tr><td>Avnet, Inc.</td><td>United States</td></tr>"
              "<tr><td>Avnet Europe (Branch office in France)</td><td>France</td></tr></table></div>"
              + break_hr + page
              + "<table><tr><td>EBV Elektronik SAS</td><td>France</td></tr></table></div>"
              + break_hr + page
              + "<table><tr><td>Memec Group Limited</td><td>United Kingdom</td></tr></table></div></body>")


def cbt_table(name, *, name_header="Subsidiary", jurisdiction_header="State/Jurisdiction of Incorporation",
              jurisdiction="Delaware"):
    return (f"<table><tr><td>{name_header}</td><td>{jurisdiction_header}</td></tr>"
            f"<tr><td>{name}</td><td>{jurisdiction}</td></tr></table>")


def cbt_three_tables(*, title="Exhibit 21 Subsidiaries of Cabot Corporation (as of September 30, 2025)*",
                     first_gap="Exhibit 21", second_gap="Exhibit 21", second_header="Subsidiary",
                     third_row="Cabot Specialty Fluids LLC"):
    return (f"<p>{title}</p>"
            + cbt_table("Cabot Holdings LLC")
            + f"<p>{first_gap}</p>"
            + cbt_table("Cabot International LLC", name_header=second_header)
            + f"<p>{second_gap}</p>"
            + cbt_table(third_row))


def table(header, jurisdiction="Location of Incorporation"):
    return (f"<table><tr><td>{header}</td><td></td><td>{jurisdiction}</td></tr>"
            "<tr><td>Parent Holdings LLC</td><td></td><td>Delaware</td></tr>"
            "<tr><td style='padding-left:30px'>Indirect Company, Inc.</td><td></td><td>Ohio</td></tr></table>")


@pytest.mark.parametrize("header", ["Name of Company", "Name of Entity", "Entity"])
def test_explicit_entity_headers_preserve_indirect_scope(header):
    # AEP uses Name of Company + Location of Incorporation and indentation to
    # describe intermediate parents. Never infer direct ownership from layout.
    html = ("<p>Subsidiaries of American Electric Power Company, Inc. As of December 31, 2025</p>"
            "<p>Each company shown indented is a subsidiary of the company immediately above.</p>" + table(header))
    result = parse_exhibit(html, META)
    assert result["status"] == "parsed"
    assert [r["name"] for r in result["rows"]] == ["Parent Holdings LLC", "Indirect Company, Inc."]
    assert all(r["ownershipPct"] is None and r["directOwnership"] == "unspecified" for r in result["rows"])


@pytest.mark.parametrize("header", ["Name of Customer", "Name of Supplier", "Doing Business As"])
def test_other_parties_and_trade_names_do_not_become_legal_entities(header):
    result = parse_exhibit(table(header), META)
    assert result["status"] == "needs-review"
    assert result["reviewReason"] == "explicit-name-jurisdiction-header-missing"
    assert result["rows"] == []


@pytest.mark.parametrize("html,reason", [
    ("<p>Variable interest entities</p>", "vie-scope-needs-review"),
    (table("Name of Company", "Country"), "explicit-name-jurisdiction-header-missing"),
    (table("Name") + table("Name"), "multiple-tables-issuer-scope-unbound"),
    ("<p>As of January 1, 2026</p>" + table("Name"), "exhibit-as-of-differs-from-period-end"),
    (table("Name").replace("<td>Ohio</td>", ""), "ambiguous-row-binding"),
])
def test_batch_review_has_actionable_reasons_without_promotion(html, reason):
    result = parse_exhibit(html, META)
    assert result["status"] == "needs-review"
    assert result["reviewReason"] == reason


@pytest.mark.parametrize("issuer_name,title_name", [
    ("Cabot Corp", "Cabot Corporation"),
    ("Cabot Corporation", "Cabot Corp"),
])
def test_cbt_title_binds_only_terminal_corp_corporation(issuer_name, title_name):
    html = cbt_three_tables(title=f"Exhibit 21 Subsidiaries of {title_name} (as of September 30, 2025)*")
    result = parse_exhibit(html, {**CBT_META, "issuerName": issuer_name})
    assert result["status"] == "parsed"
    assert [row["name"] for row in result["rows"]] == [
        "Cabot Holdings LLC", "Cabot International LLC", "Cabot Specialty Fluids LLC"]
    assert [row["sourceRow"]["tableIndex"] for row in result["rows"]] == [0, 1, 2]
    assert all(row["ownershipPct"] is None and row["directOwnership"] == "unspecified"
               for row in result["rows"])


@pytest.mark.parametrize("marker", ["Exhibit 21", "Exhibit 21.1"])
def test_cbt_three_tables_allow_only_matching_repeated_exhibit_marker(marker):
    html = cbt_three_tables(title=f"{marker} Subsidiaries of Cabot Corporation (as of September 30, 2025)*",
                            first_gap=marker, second_gap=marker)
    result = parse_exhibit(html, CBT_META)
    assert result["status"] == "parsed"
    assert len(result["rows"]) == 3


@pytest.mark.parametrize("changes,reason", [
    ({"title": "Exhibit 21 Subsidiaries of Another Corporation (as of September 30, 2025)*"},
     "multiple-tables-issuer-scope-unbound"),
    ({"title": "Exhibit 21 Former Subsidiaries of Cabot Corporation (as of September 30, 2025)*"},
     "multiple-tables-issuer-scope-unbound"),
    ({"first_gap": "Exhibit 8"}, "continuation-scope-text"),
    ({"first_gap": "Exhibit 21 additional subsidiaries"}, "continuation-scope-text"),
    ({"title": "Subsidiaries of Cabot Corporation (as of September 30, 2025)*"},
     "continuation-scope-text"),
    ({"first_gap": "Exhibit 21.1"}, "continuation-scope-text"),
    ({"second_header": "Company Name"}, "continuation-headers-differ"),
    ({"title": "Exhibit 21 Subsidiaries of Cabot Corporation (as of September 30, 2024)*"},
     "exhibit-as-of-differs-from-period-end"),
    ({"third_row": "Cabot Specialty Fluids LLC<br>Unbound Name LLC"}, "ambiguous-row-binding"),
    ({"third_row": "Cabot Corporation Foundation, Inc."}, "ambiguous-row-binding"),
    ({"third_row": "Energy Transport Limited LLC"}, "ambiguous-row-binding"),
])
def test_cbt_near_misses_remain_held(changes, reason):
    result = parse_exhibit(cbt_three_tables(**changes), CBT_META)
    assert result["status"] == "needs-review"
    assert result["reviewReason"] == reason


def test_avt_issuer_bound_country_header_and_headerless_pages_preserve_exact_rows():
    result = parse_exhibit(avt_exhibit(), AVT_META)
    assert result["status"] == "parsed"
    assert [row["name"] for row in result["rows"]] == [
        "Avnet (Asia Pacific Holdings) Limited", "Avnet (Holdings) Ltd",
        "Avnet Philippines Pty Ltd., Inc.", "EBV Elektronik SAS", "Memec Group Limited"]
    assert [row["sourceRow"]["tableIndex"] for row in result["rows"]] == [0, 0, 1, 2, 3]
    assert all(row["ownershipPct"] is None and row["directOwnership"] == "unspecified"
               for row in result["rows"])


def test_avt_unrelated_unheaded_two_column_table_does_not_inherit_country_header():
    html = avt_exhibit().replace(
        "</body>",
        "<table><tr><td>Project North LLC</td><td>Delaware</td></tr>"
        "<tr><td>Account Balance</td><td>USD</td></tr></table></body>")
    result = parse_exhibit(html, AVT_META)
    assert result["status"] == "needs-review"
    assert result["reviewReason"] == "continuation-page-break-unbound"
    assert not any(row["name"] == "Project North LLC" for row in result["rows"])


def test_avt_pagebreak_does_not_license_financial_rows_as_countries():
    html = avt_exhibit(continuation_name="Account Balance", continuation_country="USD")
    result = parse_exhibit(html, AVT_META)
    assert result["status"] == "needs-review"
    assert result["reviewReason"] == "ambiguous-row-binding"
    assert not any(row["name"] == "Account Balance" for row in result["rows"])


@pytest.mark.parametrize("country", ["Millions", "Amount", "USD", "Revenue increased this year", "AlphaLand"])
def test_avt_exact_pagebreak_holds_unobserved_country_column_values(country):
    result = parse_exhibit(avt_exhibit(continuation_name="Quarterly Revenue",
                                       continuation_country=country), AVT_META)
    assert result["status"] == "needs-review"
    assert result["reviewReason"] == "ambiguous-row-binding"
    assert not any(row["name"] == "Quarterly Revenue" for row in result["rows"])


def test_avt_exact_pagebreak_holds_multiple_financial_rows():
    html = avt_exhibit(continuation_name="Quarterly Revenue", continuation_country="Millions")
    html = html.replace("<tr><td>Avnet, Inc.</td>",
                        "<tr><td>Operating Income</td><td>Thousands</td></tr>"
                        "<tr><td>Avnet, Inc.</td>")
    result = parse_exhibit(html, AVT_META)
    assert result["status"] == "needs-review"
    assert result["reviewReason"] == "ambiguous-row-binding"
    assert not {"Quarterly Revenue", "Operating Income"} & {row["name"] for row in result["rows"]}


@pytest.mark.parametrize("country", ["Korea, Republic of", "Taiwan (Province of China)"])
def test_avt_observed_country_spellings_remain_eligible(country):
    result = parse_exhibit(avt_exhibit(continuation_country=country), AVT_META)
    assert result["status"] == "parsed"
    assert result["rows"][2]["jurisdiction"] == country
    assert result["rows"][2]["ownershipPct"] is None
    assert result["rows"][2]["directOwnership"] == "unspecified"


@pytest.mark.parametrize("meta,title,header,rows", [
    (CPK_META, "Chesapeake Utilities Corporation Subsidiaries of the Registrant",
     "<td>Subsidiaries</td><td>State&nbsp;Incorporated</td><td></td>",
     "<tr><td>Eastern Shore Natural Gas Company</td><td>Delaware</td><td></td></tr>"
     "<tr><td>Sharp Energy, Inc.</td><td>Delaware</td><td></td></tr>"),
    (CMI_META, "CUMMINS INC. SUBSIDIARIES OF THE REGISTRANT EXHIBIT 21",
     "<td>Entity Name</td><td></td><td>Country or State of Organization</td>",
     "<tr><td>Apollo FC Holdings Ltd</td><td></td><td>British Columbia</td></tr>"
     "<tr><td>Arvin Environmental Management, LLC</td><td></td><td>Delaware</td></tr>"),
])
def test_registrant_bound_jurisdiction_header_synonyms(meta, title, header, rows):
    html = f"<p>{title}</p><table><tr>{header}</tr>{rows}</table>"
    result = parse_exhibit(html, meta)
    assert result["status"] == "parsed"
    assert len(result["rows"]) == 2
    assert all(row["ownershipPct"] is None and row["directOwnership"] == "unspecified"
               for row in result["rows"])


def test_cpk_six_intermediate_parent_headers_hold_entire_exhibit():
    subheaders = [
        "Subsidiary of Sharp Energy, Inc.",
        "Subsidiary of Florida Public Utilities Company",
        "Subsidiaries of Chesapeake Service Company",
        "Subsidiaries of Chesapeake OnSight Services LLC",
        "Subsidiaries of OnSight Renewables, LLC",
        "Subsidiary of Eastern Shore Natural Gas Company",
    ]
    rows = "<tr><td>Subsidiaries</td><td>State Incorporated</td><td></td></tr>"
    rows += "<tr><td>Eastern Shore Natural Gas Company</td><td>Delaware</td><td></td></tr>"
    for heading in subheaders:
        rows += f"<tr><td>{heading}</td><td>State Incorporated</td><td></td></tr>"
        rows += "<tr><td>Sharp Energy, Inc.</td><td>Delaware</td><td></td></tr>"
    result = parse_exhibit(
        "<p>Chesapeake Utilities Corporation Subsidiaries of the Registrant</p>"
        f"<table>{rows}</table>", CPK_META)
    assert result["status"] == "needs-review"
    assert result["reviewReason"] == "ambiguous-row-binding"
    assert not set(subheaders) & {row["name"] for row in result["rows"]}


def test_cpk_exact_repeated_header_is_not_a_company_row():
    html = ("<p>Chesapeake Utilities Corporation Subsidiaries of the Registrant</p>"
            "<table><tr><td>Subsidiaries</td><td>State Incorporated</td><td></td></tr>"
            "<tr><td>Eastern Shore Natural Gas Company</td><td>Delaware</td><td></td></tr>"
            "<tr><td>Subsidiaries</td><td>State Incorporated</td><td></td></tr>"
            "<tr><td>Sharp Energy, Inc.</td><td>Delaware</td><td></td></tr></table>")
    result = parse_exhibit(html, CPK_META)
    assert result["status"] == "parsed"
    assert [row["name"] for row in result["rows"]] == [
        "Eastern Shore Natural Gas Company", "Sharp Energy, Inc."]


def test_repeated_exact_registrant_title_continues_same_header_only():
    title = "CUMMINS INC. SUBSIDIARIES OF THE REGISTRANT EXHIBIT 21"
    header = "<tr><td>Entity Name</td><td></td><td>Country or State of Organization</td></tr>"
    first = "<table>" + header + "<tr><td>Apollo FC Holdings Ltd</td><td></td><td>British Columbia</td></tr></table>"
    second = "<table>" + header + "<tr><td>Arvin Environmental Management, LLC</td><td></td><td>Delaware</td></tr></table>"
    result = parse_exhibit(f"<p>{title}</p>{first}<p>{title}</p>{second}", CMI_META)
    assert result["status"] == "parsed"
    assert [row["sourceRow"]["tableIndex"] for row in result["rows"]] == [0, 1]
    for gap in ("OTHER INC. SUBSIDIARIES OF THE REGISTRANT EXHIBIT 21",
                "CUMMINS INC. FORMER SUBSIDIARIES OF THE REGISTRANT EXHIBIT 21",
                "CUMMINS INC. SUBSIDIARIES OF THE REGISTRANT EXHIBIT 8"):
        held = parse_exhibit(f"<p>{title}</p>{first}<p>{gap}</p>{second}", CMI_META)
        assert held["status"] == "needs-review"
        assert held["reviewReason"] == "continuation-scope-text"


@pytest.mark.parametrize("title,header,row,reason", [
    ("Other Inc. Subsidiaries of the Registrant", "Subsidiaries|State Incorporated",
     "Eastern Shore Natural Gas Company|Delaware", "issuer-scope-unbound"),
    ("Chesapeake Utilities Corporation Former Subsidiaries of the Registrant",
     "Subsidiaries|State Incorporated", "Eastern Shore Natural Gas Company|Delaware", "issuer-scope-unbound"),
    ("Chesapeake Utilities Corporation Subsidiaries of the Registrant",
     "Subsidiaries|Incorporated Location|Holding Company (1) or Subsidiary (2)",
     "Eastern Shore Natural Gas Company|Delaware|2", "explicit-name-jurisdiction-header-missing"),
    ("Chesapeake Utilities Corporation Subsidiaries of the Registrant",
     "Subsidiaries|State Incorporated", "Account Balance|USD", "ambiguous-row-binding"),
    ("Chesapeake Utilities Corporation Subsidiaries of the Registrant As of January 1, 2026",
     "Subsidiaries|State Incorporated", "Eastern Shore Natural Gas Company|Delaware",
     "exhibit-as-of-differs-from-period-end"),
])
def test_jurisdiction_synonyms_preserve_scope_and_row_boundaries(title, header, row, reason):
    cells = lambda parts: "".join(f"<td>{value}</td>" for value in parts.split("|"))
    html = f"<p>{title}</p><table><tr>{cells(header)}</tr><tr>{cells(row)}</tr></table>"
    result = parse_exhibit(html, CPK_META)
    assert result["status"] == "needs-review"
    assert result["reviewReason"] == reason


@pytest.mark.parametrize("name", [
    "Prudential Oil & Gas LLC (57.5%)",
    "Southern Gulf Railway LLC (42.5%)",
    "PFC Products, Inc.(1)",
    "General Financial Supply, Inc. (6)",
    "Example Holdings LLC (123)",
])
def test_unresolved_ownership_or_numeric_footnote_never_becomes_a_legal_name(name):
    html = ("<table><tr><td>Name of Company</td><td>Jurisdiction</td></tr>"
            f"<tr><td>{name}</td><td>Delaware</td></tr></table>")
    result = parse_exhibit(html, META)
    assert result["status"] == "needs-review"
    assert result["reviewReason"] == "ambiguous-row-binding"
    assert result["rows"] == []


def test_supported_explicit_owned_annotation_is_not_rewritten_as_ownership():
    html = ("<table><tr><td>Name of Company</td><td>Jurisdiction</td></tr>"
            "<tr><td>Parent Holdings LLC (100% owned)</td><td>Delaware</td></tr></table>")
    result = parse_exhibit(html, META)
    assert result["status"] == "parsed"
    assert result["rows"][0]["name"] == "Parent Holdings LLC"
    assert result["rows"][0]["ownershipPct"] is None
    assert result["rows"][0]["directOwnership"] == "unspecified"


@pytest.mark.parametrize("later", [
    "<table><tr><td>Hill's Nutrition, Inc.</td><td>Delaware</td></tr></table>",
    "<table><tr><td>Entergy Nuclear New York Investment Company, LLC</td><td></td>"
    "<td>Delaware</td></tr></table>",
    "<table><tr><td>Union Engineering A/S</td><td></td><td>Denmark</td></tr></table>",
])
def test_headerless_substantive_following_table_cannot_be_silently_dropped(later):
    html = ("<p>Subsidiaries of American Electric Power Company, Inc.</p>"
            "<table><tr><td>Name of Company</td><td>Jurisdiction</td></tr>"
            "<tr><td>Parent Holdings LLC</td><td>Delaware</td></tr></table>" + later)
    result = parse_exhibit(html, META)
    assert result["status"] == "needs-review"
    assert result["reviewReason"] == "unreviewed-exhibit-table"
    assert result["rows"] == []


def test_empty_layout_and_numbered_ownership_notes_are_not_subsidiary_tables():
    html = ("<table><tr><td>Name of Company</td><td>Jurisdiction</td></tr>"
            "<tr><td>Parent Holdings LLC</td><td>Delaware</td></tr></table>"
            "<table><tr><td></td><td> </td></tr></table>"
            "<table><tr><td>(1)</td><td>10.26% owned</td></tr>"
            "<tr><td>(2)</td><td>50% owned</td></tr></table>")
    result = parse_exhibit(html, META)
    assert result["status"] == "parsed"
    assert [row["name"] for row in result["rows"]] == ["Parent Holdings LLC"]


@pytest.mark.parametrize("footnote,expected,reason", [
    ("This information is as of January 1, 2026.", "needs-review",
     "exhibit-as-of-differs-from-period-end"),
    ("This information is as of February 30, 2025.", "needs-review",
     "invalid-exhibit-as-of-date"),
    ("This information is as of December 31, 2025.", "parsed", None),
])
def test_explicit_as_of_in_visible_bottom_footnote_bounds_entire_exhibit(footnote, expected, reason):
    html = ("<table><tr><td>Name of Company</td><td>Jurisdiction</td></tr>"
            "<tr><td>Parent Holdings LLC</td><td>Delaware</td></tr></table>"
            f"<p><sup>1</sup>{footnote}</p>")
    result = parse_exhibit(html, META)
    assert result["status"] == expected
    assert result.get("reviewReason") == reason


def test_dates_in_head_script_or_style_are_not_visible_exhibit_dates():
    html = ("<html><head><title>As of January 1, 2026</title>"
            "<style>/* As of January 1, 2026 */</style></head><body>"
            "<script>const note = 'As of January 1, 2026';</script>"
            "<table><tr><td>Name of Company</td><td>Jurisdiction</td></tr>"
            "<tr><td>Parent Holdings LLC</td><td>Delaware</td></tr></table></body></html>")
    result = parse_exhibit(html, META)
    assert result["status"] == "parsed"
    assert result["rows"][0]["name"] == "Parent Holdings LLC"


@pytest.mark.parametrize("changes,reason", [
    ({"prefix": "<p>Subsidiaries of Other Inc.</p><p>Avnet, Inc.</p>"
                "<p>Foreign and Domestic Subsidiaries</p>"}, "issuer-scope-unbound"),
    ({"prefix": "<p>Former Avnet, Inc. Foreign and Domestic Subsidiaries</p>"}, "issuer-scope-unbound"),
    ({"prefix": "<p>Avnet, Inc. Foreign and Domestic Subsidiaries</p>"
                "<p>Variable interest entities</p>"}, "vie-scope-needs-review"),
    ({"prefix": "<p>Avnet, Inc. Foreign and Domestic Subsidiaries</p>"
                "<p>As of June 26, 2026</p>"}, "exhibit-as-of-differs-from-period-end"),
    ({"gap": "<p>Subsidiaries of Other Inc.</p>"}, "continuation-scope-text"),
    ({"gap": "<p>New subsidiaries</p>"}, "continuation-scope-text"),
    ({"continuation_name": "Alpha LLC Beta LLC"}, "ambiguous-row-binding"),
    ({"continuation_name": "Alpha LLC Beta Pty Ltd., Inc."}, "ambiguous-row-binding"),
    ({"continuation_name": "Other Inc. Subsidiaries"}, "ambiguous-row-binding"),
    ({"continuation_country": "Philippines 80%"}, "ambiguous-row-binding"),
    ({"extra_cell": "<td>100%</td>"}, "continuation-headers-differ"),
])
def test_avt_near_misses_do_not_become_relationships(changes, reason):
    result = parse_exhibit(avt_exhibit(**changes), AVT_META)
    assert result["status"] == "needs-review"
    assert result["reviewReason"] == reason


def test_avt_country_layout_rejects_unbound_metadata_issuer():
    result = parse_exhibit(avt_exhibit(), {**AVT_META, "issuerName": "Other Inc."})
    assert result["status"] == "needs-review"
    assert result["reviewReason"] == "issuer-scope-unbound"


def test_arw_semantic_continued_header_is_not_a_flat_country_page():
    meta = {"cik": "0000007536", "accession": "0001104659-26-012765",
            "filedDate": "2026-02-11", "periodEnd": "2025-12-31",
            "url": "https://www.sec.gov/Archives/edgar/data/7536/000110465926012765/arw-20251231xex21.htm",
            "issuerName": "ARROW ELECTRONICS, INC."}
    html = ("<p>Exhibit 21 SUBSIDIARIES OF ARROW ELECTRONICS, INC. As of December 31, 2025</p>"
            "<table><tr><td>Entity Name</td><td></td><td>Jurisdiction of Incorporation or Organization</td></tr>"
            "<tr><td>Arrow Argentina S.A.</td><td></td><td>Argentina</td></tr></table>"
            "<table><tr><td>Entity Name (continued)</td><td></td>"
            "<td>Jurisdiction of Incorporation or Organization (continued)</td></tr>"
            "<tr><td>Arrow ECS Baltic OU</td><td></td><td>Estonia</td></tr></table>")
    result = parse_exhibit(html, meta)
    assert result["status"] == "needs-review"
    assert result["reviewReason"] == "continuation-headers-differ"


def test_newer_40f_blocks_fallback_to_historical_20f_paper():
    data = {"cik": 756894, "tickers": ["B"], "name": "Barrick Mining Corp",
            "filings": {"recent": {"form": ["40-F", "20-F"],
                "filingDate": ["2026-03-13", "2002-04-01"],
                "reportDate": ["2025-12-31", "2001-12-31"],
                "accessionNumber": ["0000756894-26-000001", "9999999997-02-026337"],
                "primaryDocument": ["annual.htm", "9999999997-02-026337.paper"]}}}
    with pytest.raises(ValueError, match="source-gap:annual-form-40f-needs-review"):
        latest_metadata("B", "0000756894", data)
    for field in data["filings"]["recent"].values():
        del field[0]
    with pytest.raises(ValueError, match="source-gap:annual-paper-document"):
        latest_metadata("B", "0000756894", data)


@pytest.mark.parametrize("cik,accession,archive_cik", [
    ("0000066901", "0000065984-26-000174", "7323"),
    ("0000072741", "0001628280-26-008461", "13372"),
    ("0000715957", "0001193125-26-063120", "103682"),
    ("0000788784", "0001193125-26-077446", "81033"),
])
def test_shared_filing_does_not_prove_the_exhibit_belongs_to_each_issuer(cik, accession, archive_cik):
    url = f"https://www.sec.gov/Archives/edgar/data/{archive_cik}/{accession.replace('-', '')}/ex21.htm"
    index = ("<table class='tableFile'><tr><th>Document</th><th>Type</th></tr>"
             f"<tr><td><a href='{url}'>ex21.htm</a></td><td>EX-21</td></tr></table>")
    with pytest.raises(ValueError, match="sec-cofiler-issuer-needs-review"):
        find_exhibit(index, cik=cik, accession=accession)


@pytest.mark.parametrize("replay_outcome,cache_outcome,should_fail", [("failure", "success", True), ("success", "failure", True), ("success", "success", False)])
def test_cache_replay_failure_is_reported_without_blocking_other_collectors(tmp_path, monkeypatch, replay_outcome, cache_outcome, should_fail):
    workflow = yaml.safe_load((Path(__file__).resolve().parents[1] / '.github/workflows/ownership_backfill.yml').read_text())
    steps = workflow['jobs']['backfill']['steps']
    by_id = {s['id']: s for s in steps if 'id' in s}
    assert by_id['us-replay']['continue-on-error'] is True
    assert by_id['sec-raw-cache']['continue-on-error'] is True
    assert steps.index(by_id['sec-raw-cache']) < steps.index(by_id['us-replay']) < steps.index(by_id['us'])
    report = next(s for s in steps if s.get('name') == 'Report collection failures after durable checkpoint')
    assert "steps.us-replay.outcome == 'failure'" in report['if']
    assert "steps.sec-raw-cache.outcome == 'failure'" in report['if']
    # A normal HTTP budget deferral cannot erase an independent replay failure.
    (tmp_path / 'company-structure-run-status.json').write_text(json.dumps({'US': {'normalDeferred': True}}))
    for key, value in {'RUNNER_TEMP': str(tmp_path), 'KR_OUTCOME': 'success',
                       'US_OUTCOME': 'failure', 'US_REPLAY_OUTCOME': replay_outcome,
                       'SEC_CACHE_OUTCOME': cache_outcome}.items():
        monkeypatch.setenv(key, value)
    code = report['run'].split("python - <<'PY'\n")[1].rsplit('\nPY', 1)[0]
    if should_fail:
        with pytest.raises(SystemExit) as exc:
            exec(code, {})
        assert exc.value.code == 1
    else:
        exec(code, {})


@pytest.mark.parametrize("cik,accession,issuer,filed,period,index_sha,exhibit_sha,expected_rows", [
    ("0001056903", "0001628280-26-009114", "AMERICAN STATES WATER CO", "2026-02-18", "2025-12-31",
     "94d349a774832fd2c3e7bc18aba1bef5a682a6f927f1b62d2706dac21779d420",
     "882e5b8b7895ce1b370eac6132cc1545693100b24f2cd6c5752c5b2edafd5553", 13),
    ("0001063761", "0001104659-26-019419", "SIMON PROPERTY GROUP INC.", "2026-02-25", "2025-12-31",
     "22fc1955c30aa1e8026ab3ef10f961bb86397eb9697dec4a4bccb2eca578a63a",
     "b2cd57f2f39531572cac9d5e9c5b188ed7ce6020e325a93dbd45fc824b3466e7", 14),
    ("0001126956", "0001193125-25-282583", "SPIRE INC", "2025-11-14", "2025-09-30",
     "3bfd8e256b11e339d2a058ef538464da3cfe3906860d82f905a135dab0ceb2e3",
     "babf8640cc42c95dd2f4b9a0d0f9fc5818f046aded9b1f64fc745248810f68c3", 21),
])
def test_cofiler_index_proof_replays_exact_saved_originals(
        cik, accession, issuer, filed, period, index_sha, exhibit_sha, expected_rows, tmp_path):
    cache_dir = os.environ.get("SEC_EXHIBIT_CACHE_DIR")
    if not cache_dir:
        pytest.skip("set SEC_EXHIBIT_CACHE_DIR for offline co-filer originals")
    index = gzip.decompress((Path(cache_dir) / (index_sha + ".gz")).read_bytes())
    raw = gzip.decompress((Path(cache_dir) / (exhibit_sha + ".gz")).read_bytes())
    assert hashlib.sha256(index).hexdigest() == index_sha
    assert hashlib.sha256(raw).hexdigest() == exhibit_sha
    url, proof = find_exhibit(index, cik=cik, accession=accession, issuer_name=issuer, return_proof=True)
    assert proof == {"requestedCik": cik, "archiveCik": url.split("/data/")[1].split("/")[0],
                     "accession": accession, "issuerName": issuer, "exhibitUrl": url,
                     "indexSha256": index_sha}
    assert not refresh_core._valid_exhibit_url(url, cik, accession)
    assert refresh_core._valid_exhibit_url(url, cik, accession, proof)
    metadata = {"cik": cik, "accession": accession, "filedDate": filed, "periodEnd": period,
                "issuerName": issuer, "form": "10-K", "url": url,
                "cofilerProof": proof, "cofilerIndexRaw": index}
    parsed = parse_exhibit(raw, metadata)
    assert len(parsed["rows"]) == expected_rows
    assert parsed["status"] == ("parsed" if expected_rows else "needs-review")
    assert parsed["cofilerProof"] == proof
    if expected_rows:
        assert all(row["directOwnership"] == "unspecified" and row["ownershipPct"] is None
                   for row in parsed["rows"])
        assert all("Doing Business" not in row["name"] for row in parsed["rows"])
    for altered in ({**metadata, "cofilerProof": {**proof, "issuerName": "Other Inc."}},
                    {**metadata, "issuerName": "Other Inc."},
                    {**metadata, "cofilerIndexRaw": index + b" "},
                    {key: value for key, value in metadata.items() if key != "cofilerProof"}):
        with pytest.raises(ValueError, match="sec-cofiler"):
            parse_exhibit(raw, altered)
    now = datetime(2026, 10, 25, 12, tzinfo=timezone.utc)
    source_metadata = {"issuer_id": "US:T", "issuer_name": issuer, "cik": cik,
                       "accession": accession, "filed_date": filed, "period_end": period,
                       "form": "10-K"}
    document = {"schema": refresh_core.SCHEMA, "universe": {"US": ["T"]},
                "currentCiks": [cik], "unmapped": {}, "issuers": {cik: {
                    "cik": cik, "tickerAliases": ["T"], "attemptStatus": "not-attempted",
                    "attemptedAt": None, "filingMetadata": source_metadata,
                    "metadataCheckedAt": now.isoformat(), "sourceGap": None}}}
    index_url = (f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
                 f"{accession.replace('-', '')}/{accession}-index.html")
    available = {index_url: index, url: raw}
    requested = []
    helpers = refresh_core.load_helpers()
    def offline_get(target, maximum):
        requested.append(target)
        return available[target]
    helpers.get_public = offline_get
    cache = tmp_path.resolve() / "raw"
    collected, summary = refresh_core.refresh(document, source_dir=tmp_path, limit=1,
        fetch_public=True, checkpoint=lambda value: None, now=now, helpers=helpers,
        sleep=lambda delay: None, raw_cache_dir=cache)
    saved = collected["issuers"][cik]
    assert requested == [index_url, url]
    assert (summary["success"], summary["sourceGap"]) == ((1, 0) if expected_rows else (0, 1))
    assert saved["rawExhibitCache"]["cofilerProof"] == proof
    assert refresh_core._read_raw_exhibit(cache, index_sha) == index
    if not expected_rows:
        saved["reviewExhibit"]["parserRevision"] = "previous-revision"
        replayed, replay = refresh_core.reparse_cached_reviews(collected, cache, now=now)
        assert replay["cacheHits"] == replay["held"] == 1 and replay["errors"] == 0
        assert replayed["issuers"][cik]["reviewExhibit"]["rows"] == []
