"""Public-interface guards for issuer-bound, multi-page Exhibit 21 tables."""

import pytest

from api.intelligence.company_structure_sec import parse_exhibit


META = {
    "cik": "0001234567",
    "accession": "0001234567-26-000001",
    "filedDate": "2026-02-20",
    "periodEnd": "2025-12-31",
    "issuerName": "Sample Corp",
    "url": "https://www.sec.gov/Archives/edgar/data/1234567/000123456726000001/ex21.htm",
}
TITLE = "<p>Exhibit 21</p><h1>Subsidiaries of Sample Corp. as of December 31, 2025</h1>"
HEADER = "<tr><th>Name</th><th></th><th>Jurisdiction of Organization</th></tr>"
BLANK = "<tr><td></td><td></td><td></td></tr>" * 4
FIRST = "<tr><td>North Star Holdings, Inc.</td><td></td><td>Delaware</td></tr>"
SECOND = "<tr><td>East River Services LLC</td><td></td><td>New York</td></tr>"
OMISSION = ("Pursuant to Item 601(b)(21) of Regulation S-K, we have omitted some "
            "subsidiaries that, considered in the aggregate as a single subsidiary, would not "
            "constitute a significant subsidiary as of December 31, 2025 under Rule 1-02(w) "
            "of Regulation S-X.")


def _page(row, *, header=HEADER):
    # Four physical blank rows keep the old first-three-row header path out.
    return f"<table>{BLANK}{header}{row}</table>"


def _exhibit(*, title=TITLE, first=FIRST, second=SECOND, second_header=HEADER,
             between="", footer=""):
    return ("<html><body>" + title + _page(first) + between +
            _page(second, header=second_header) + footer + "</body></html>")


def _pairs(result):
    return [(row["name"], row["jurisdiction"]) for row in result["rows"]]


def test_two_pages_repeat_exact_header_and_keep_blank_column_and_unknown_parentage():
    result = parse_exhibit(_exhibit(), META)
    assert result["status"] == "parsed", result.get("reviewReason")
    assert result["parserRevision"] == "2026-10-25-bound-continuations-v19"
    assert result["periodEnd"] == "2025-12-31"
    assert result["scope"] == "reported-subsidiary-list-not-exhaustive"
    assert _pairs(result) == [
        ("North Star Holdings, Inc.", "Delaware"),
        ("East River Services LLC", "New York"),
    ]
    assert [row["sourceRow"]["tableIndex"] for row in result["rows"]] == [0, 1]
    assert all(row["ownershipPct"] is None and row["directOwnership"] == "unspecified"
               for row in result["rows"])


def test_split_jurisdiction_header_is_only_a_physical_header_continuation():
    split = ("<tr><th>Name</th><th></th><th>State of</th></tr>"
             "<tr><th></th><th></th><th>Organization</th></tr>")
    html = "<html><body>" + TITLE + _page(FIRST, header=split) + _page(SECOND, header=split) + "</body></html>"
    result = parse_exhibit(html, META)
    assert result["status"] == "parsed", result.get("reviewReason")
    assert len(result["rows"]) == 2


def test_closed_prefix_omission_note_limits_scope_without_dropping_rows():
    result = parse_exhibit(_exhibit(title=TITLE + f"<p>{OMISSION}</p>"), META)
    assert result["status"] == "parsed", result.get("reviewReason")
    assert len(result["rows"]) == 2
    assert result["scope"] == "reported-subsidiary-list-not-exhaustive"


def test_closed_footer_omission_note_is_not_an_extra_company_row():
    result = parse_exhibit(_exhibit(footer=f"<p>{OMISSION}</p>"), META)
    assert result["status"] == "parsed", result.get("reviewReason")
    assert len(result["rows"]) == 2
    assert result["scope"] == "reported-subsidiary-list-not-exhaustive"


def test_existing_first_row_header_path_still_returns_its_parsed_result():
    html = ("<table><tr><th>Name</th><th>Jurisdiction of Incorporation</th></tr>"
            "<tr><td>Prior Services LLC</td><td>Delaware</td></tr></table>")
    result = parse_exhibit(html, META)
    assert result["status"] == "parsed"
    assert _pairs(result) == [("Prior Services LLC", "Delaware")]


def test_unheaded_second_page_requires_the_same_complete_physical_column_binding():
    result = parse_exhibit(_exhibit(second_header=""), META)
    assert result["status"] == "parsed", result.get("reviewReason")
    assert _pairs(result) == [("North Star Holdings, Inc.", "Delaware"),
                              ("East River Services LLC", "New York")]
    assert [r["sourceRow"]["tableIndex"] for r in result["rows"]] == [0, 1]
    assert all(r["ownershipPct"] is None and r["directOwnership"] == "unspecified"
               for r in result["rows"])
    missing_first_header = _exhibit(second_header="").replace(HEADER, "", 1)
    assert parse_exhibit(missing_first_header, META)["status"] == "needs-review"


@pytest.mark.parametrize("mutation", [
    {"title": "<p>Exhibit 21</p><h1>Subsidiaries of Other Corp. as of December 31, 2025</h1>"},
    {"title": "<p>Exhibit 21</p><h1>Subsidiaries of Sample Corp. as of December 30, 2025</h1>"},
    {"between": "<p>Subsidiaries of Other Corp.</p>"},
    {"second_header": "<tr><th>Name</th><th></th><th>State of Incorporation</th></tr>"},
    {"second_header": "<tr><th>Name</th><th></th><th>Ownership %</th>"
                      "<th>Jurisdiction of Organization</th></tr>"},
    {"second": "<tr><td>East River Services LLC</td><td>Trade name</td>"
               "<td>New York</td></tr>"},
    {"second": "<tr><td>East River Services LLC</td><td></td><td></td></tr>"},
    {"second": "<tr><td>East River Services LLC</td><td>New York</td><td></td></tr>"},
    {"second": "<tr><td>East River Services LLC</td><td>New York</td></tr>"},
    {"second": "<tr><td>East River Services LLC</td><td></td><td>USA</td></tr>"},
    {"second": "<tr><td>East River Services LLC (100%)</td><td></td>"
               "<td>New York</td></tr>"},
    {"title": TITLE + "<p>Pursuant to Item 601(b)(21), former subsidiaries follow.</p>"},
    {"between": "<p style='display:none'>Other Parent has an additional entity.</p>"},
    {"footer": "<p>Other affiliates were also included.</p>"},
    {"footer": "<p>Subsidiaries not included on this list, considered in the aggregate as "
               "a single subsidiary, would not constitute a significant subsidiary as of "
               "December 30, 2025.</p>"},
    {"second": "<tr><td>East River Services LLC<table><tr><td>Hidden LLC</td>"
               "</tr></table></td><td></td><td>New York</td></tr>"},
])
def test_ambiguous_page_scope_or_row_is_not_promoted(mutation):
    result = parse_exhibit(_exhibit(**mutation), META)
    assert result["status"] == "needs-review", (mutation, result)


def test_inline_real_name_spacing_and_jurisdiction_are_preserved():
    row = ("<tr><td><span>North&nbsp;Star</span> <span>&amp; Co., Inc.</span></td>"
           "<td></td><td><span>New</span> <span>York</span></td></tr>")
    result = parse_exhibit(_exhibit(first=row), META)
    assert result["status"] == "parsed", result.get("reviewReason")
    assert _pairs(result)[0] == ("North Star & Co., Inc.", "New York")
