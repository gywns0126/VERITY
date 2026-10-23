"""Public exhibit layout variants; no source calls or ownership inference."""
import pytest

from api.intelligence.company_structure_sec import parse_exhibit, find_exhibit
from api.collectors.company_structure_us_refresh import latest_metadata

META = {"cik": "0000004904", "accession": "0000004904-26-000018",
        "filedDate": "2026-02-12", "periodEnd": "2025-12-31",
        "url": "https://www.sec.gov/Archives/edgar/data/4904/000000490426000018/ex21.htm",
        "issuerName": "American Electric Power Company, Inc."}


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
