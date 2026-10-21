import pytest

from api.intelligence.company_structure_sec import find_exhibit, parse_exhibit


CIK = "0001136869"
ACCESSION = "0001193125-26-201710"
BASE = "https://www.sec.gov/Archives/edgar/data/1136869/000119312526201710/"
META = {"cik": CIK, "accession": ACCESSION, "filedDate": "2026-07-02",
        "periodEnd": "2026-05-03", "url": BASE + "zbh-ex21.htm"}


def _index(*rows):
    body = "".join(f"<tr><td>{seq}</td><td>{desc}</td><td><a href='{href}'>{doc}</a></td><td>{kind}</td></tr>"
                   for seq, desc, doc, kind, href in rows)
    return ("<html><table class='tableFile'><tr><th>Seq</th><th>Description</th>"
            "<th>Document</th><th>Type</th></tr>" + body + "</table></html>")


def _exhibit(rows):
    body = "".join(f"<tr><td>{name}</td><td>{jurisdiction}</td></tr>" for name, jurisdiction in rows)
    return ("<html><table><tr><th>Subsidiary Name</th><th>Jurisdiction of "
            "Incorporation</th></tr>" + body + "</table></html>")


def test_finds_only_exact_ex21_type_in_same_filing_directory():
    html = _index(("1", "Annual report", "10-K", "10-K", "annual.htm"),
                  ("2", "Exhibit 21", "zbh-ex21.htm", "EX-21", "zbh-ex21.htm"))
    assert find_exhibit(html, cik=CIK, accession=ACCESSION) == BASE + "zbh-ex21.htm"


def test_accepts_exact_ex21_1_type():
    html = _index(("1", "Exhibit 21.1", "zbh-ex21-1.htm", "EX-21.1", "zbh-ex21-1.htm"))
    assert find_exhibit(html, cik=CIK, accession=ACCESSION) == BASE + "zbh-ex21-1.htm"


def test_20f_selects_only_ex8_subsidiaries_description_and_default_stays_10k():
    html = _index(("1", "List of Subsidiaries", "issuer-ex8.htm", "EX-8", "issuer-ex8.htm"),
                  ("2", "List of Subsidiaries", "issuer-ex8-1.htm", "EX-8.1", "issuer-ex8-1.htm"))
    with pytest.raises(ValueError, match="sec-exhibit-ambiguous"):
        find_exhibit(html, cik=CIK, accession=ACCESSION, form="20-F")
    assert find_exhibit(_index(("1", "List of Subsidiaries", "issuer-ex8-1.htm", "EX-8.1",
                               "issuer-ex8-1.htm")),
                        cik=CIK, accession=ACCESSION, form="20-F") == BASE + "issuer-ex8-1.htm"
    assert find_exhibit(html, cik=CIK, accession=ACCESSION) is None


def test_20f_requires_explicit_subsidiaries_description_and_supported_form():
    html = _index(("1", "Variable Interest Entities", "issuer-ex8.htm", "EX-8", "issuer-ex8.htm"))
    assert find_exhibit(html, cik=CIK, accession=ACCESSION, form="20-F") is None
    with pytest.raises(ValueError, match="unsupported-sec-form"):
        find_exhibit(html, cik=CIK, accession=ACCESSION, form="8-K")


def test_vie_in_index_description_fails_closed_for_review():
    html = _index(("1", "List of Subsidiaries", "issuer-ex8.htm", "EX-8", "issuer-ex8.htm"),
                  ("2", "Variable Interest Entities", "issuer-ex99.htm", "EX-99", "issuer-ex99.htm"))
    with pytest.raises(ValueError, match="sec-vie-needs-review"):
        find_exhibit(html, cik=CIK, accession=ACCESSION, form="20-F")


def test_vie_in_exhibit_returns_needs_review_without_promoting_rows():
    fixture = _exhibit([("Subsidiary One Ltd.", "Cayman Islands")]).replace(
        "<table>", "<p>Consolidated affiliated entities include a VIE.</p><table>")
    result = parse_exhibit(fixture, META)
    assert result["status"] == "needs-review"
    assert result["rows"] == []


def test_no_matching_exhibit_returns_none():
    assert find_exhibit(_index(("1", "Description mentions EX-21", "x.htm", "EX-10", "x.htm")),
                        cik=CIK, accession=ACCESSION) is None


def test_ambiguous_ex21_rows_fail_closed():
    html = _index(("1", "One", "a.htm", "EX-21", "a.htm"),
                  ("2", "Two", "b.htm", "EX-21.1", "b.htm"))
    with pytest.raises(ValueError, match="sec-exhibit-ambiguous"):
        find_exhibit(html, cik=CIK, accession=ACCESSION)


@pytest.mark.parametrize("href", [
    "https://evil.example/x.htm", "javascript:alert(1)", "../x.htm",
    "%2e%2e%2fx.htm", "sub%2fdoc.htm", "https://www.sec.gov/Archives/edgar/data/1136869/other/x.htm",
])
def test_rejects_nonlocal_or_path_escape_links(href):
    html = _index(("1", "Exhibit 21", "x.htm", "EX-21", href))
    with pytest.raises(ValueError, match="invalid-sec-document-url"):
        find_exhibit(html, cik=CIK, accession=ACCESSION)


def test_parses_explicit_rows_and_keeps_ownership_and_parentage_unknown():
    result = parse_exhibit(_exhibit([("Example Holdings, Inc.", "Delaware"),
                                    ("Example Services GmbH", "Germany")]), META)
    assert result["status"] == "parsed"
    assert result["schema"] == "sec-company-subsidiaries-v1"
    assert result["scope"] == "reported-subsidiary-list-not-exhaustive"
    assert [(row["name"], row["jurisdiction"]) for row in result["rows"]] == [
        ("Example Holdings, Inc.", "Delaware"), ("Example Services GmbH", "Germany")]
    assert all(row["ownershipPct"] is None and row["directOwnership"] == "unspecified"
               for row in result["rows"])
    assert result["rows"][0]["sourceRow"] == {
        "index": 1, "text": "Example Holdings, Inc. Delaware"}
    assert len(result["documentSha256"]) == 64


@pytest.mark.parametrize("metadata", [
    {**META, "cik": "1136869"}, {**META, "accession": "bad"},
    {**META, "url": "https://evil.example/zbh-ex21.htm"},
    {**META, "url": BASE + "../other.htm"},
    {**META, "periodEnd": "2026-99-03"},
])
def test_metadata_identity_dates_and_url_are_strict(metadata):
    with pytest.raises(ValueError, match="invalid-sec-"):
        parse_exhibit(_exhibit([("Example Inc.", "Delaware")]), metadata)


def test_missing_required_header_or_malformed_rows_need_review():
    no_jurisdiction = "<table><tr><th>Subsidiary Name</th><th>Country</th></tr><tr><td>X Inc.</td><td>US</td></tr></table>"
    assert parse_exhibit(no_jurisdiction, META)["status"] == "needs-review"
    generic_state = "<table><tr><th>Name</th><th>State</th></tr><tr><td>X Inc.</td><td>Delaware</td></tr></table>"
    assert parse_exhibit(generic_state, META)["status"] == "needs-review"
    malformed = "<table><tr><th>Subsidiary Name</th><th>Jurisdiction</th></tr><tr><td>X Inc.</td></tr></table>"
    assert parse_exhibit(malformed, META)["status"] == "needs-review"


def test_accepts_plain_name_header_when_jurisdiction_is_explicit():
    fixture = ("<table><tr><th>Name</th><th>Jurisdiction of Incorporation</th></tr>"
               "<tr><td>Example Holdings, Inc.</td><td>Delaware</td></tr></table>")
    result = parse_exhibit(fixture, META)
    assert result["status"] == "parsed"
    assert result["rows"][0]["name"] == "Example Holdings, Inc."
    assert result["rows"][0]["jurisdiction"] == "Delaware"


def test_omits_non_entity_and_ambiguous_rows_and_enforces_row_cap():
    fixture = _exhibit([("Domestic subsidiaries", "United States"),
                        ("Example Trust", "Delaware"),
                        ("Example Branch", "France"),
                        ("Example, Inc.", "Delaware")])
    result = parse_exhibit(fixture, META)
    assert [row["name"] for row in result["rows"]] == ["Example, Inc."]
    too_many = _exhibit([(f"Subsidiary {i} Inc.", "Delaware") for i in range(1001)])
    capped = parse_exhibit(too_many, META)
    assert capped["status"] == "needs-review"
    assert len(capped["rows"]) == 1000


def test_exhibit_size_limit():
    with pytest.raises(ValueError, match="sec-exhibit-size"):
        parse_exhibit(b" " * (8 * 1024 * 1024 + 1), META)
