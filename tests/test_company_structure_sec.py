import gzip
import hashlib
import os
from pathlib import Path

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


def test_accepts_sec_co_registrant_archive_wrapper_for_matching_accession():
    cik = "0000006201"
    accession = "0000006201-26-000014"
    wrapper = ("https://www.sec.gov/Archives/edgar/data/4515/"
               "000000620126000014/ex211q42510k.htm")
    index = _index(("7", "EX-21.1", "ex211q42510k.htm", "EX-21.1", wrapper))

    assert find_exhibit(index, cik=cik, accession=accession) == wrapper
    metadata = {"cik": cik, "accession": accession, "filedDate": "2026-02-18",
                "periodEnd": "2025-12-31", "url": wrapper}
    parsed = parse_exhibit(_exhibit([("American Airlines, Inc.", "Delaware")]), metadata)
    assert parsed["status"] == "parsed"
    assert parsed["cik"] == cik
    assert parsed["url"] == wrapper


def test_co_registrant_archive_wrapper_still_requires_exact_accession():
    wrapper = ("https://www.sec.gov/Archives/edgar/data/4515/"
               "000000620126000015/ex211q42510k.htm")
    with pytest.raises(ValueError, match="invalid-sec-document-url"):
        find_exhibit(_index(("7", "EX-21.1", "ex211q42510k.htm", "EX-21.1", wrapper)),
                     cik="0000006201", accession="0000006201-26-000014")


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


@pytest.mark.parametrize("stated", ["March 1, 2026", "2026-03-01"])
def test_exhibit_date_cannot_inherit_a_different_financial_period(stated):
    fixture = f"<p>Subsidiaries of Example Inc. As of {stated}</p>" + _exhibit([("Other Inc.", "Delaware")])
    meta = {**META, "periodEnd": "2026-02-28"}
    result = parse_exhibit(fixture, meta)
    assert result["status"] == "needs-review"
    assert result["rows"] == []
    assert result["statedAsOf"] == "2026-03-01"
    assert result["reviewReason"] == "exhibit-as-of-differs-from-period-end"
    assert result["periodEnd"] == "2026-02-28"


@pytest.mark.parametrize("stated", ["May 3,2026", "2026-05-03"])
def test_matching_explicit_exhibit_date_keeps_supported_rows(stated):
    fixture = f"<p>As of {stated}</p>" + _exhibit([("Other Inc.", "Delaware")])
    assert parse_exhibit(fixture, META)["status"] == "parsed"


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


def test_acu_paragraph_pairs_in_one_physical_row_are_two_complete_entities():
    # Synthetic DOM mirrors the original ACU table: a blank spacer column and
    # two font-wrapped paragraphs in each cell of the last physical row.
    # Original URL: /data/2098/000119312526102079/acu-ex21.htm
    # Original SHA256: c729628bfab992a92e7123eb73c13baf61d5eaba7847940113cd4fa9e133294d
    singles = [("Acme United Limited", "Canada"), ("Acme United Europe GmbH", "Germany"),
               ("Acme United (Asia Pacific) Limited", "Hong Kong"), ("Acme United China Limited", "China")]
    body = "".join(f"<tr><td><p><font>{name}</font></p></td><td>&nbsp;</td>"
                   f"<td><p><font>{jurisdiction}</font></p></td></tr>" for name, jurisdiction in singles)
    fixture = ("<table><tr style='visibility:collapse'><td></td><td></td><td></td></tr>"
               "<tr><td><p><font>Name</font></p></td><td>&nbsp;</td>"
               "<td><p>Country of Incorporation</p></td></tr>" + body +
               "<tr><td><p><font>Acme United Netherlands Cooperatie U.A.</font></p>"
               "<p><font>Acme United (APAC) Pte.Ltd.</font></p></td><td><p>&nbsp;</p></td>"
               "<td><p><font>Netherlands</font></p><p><font>Singapore</font></p></td></tr></table>")
    result = parse_exhibit(fixture, META)
    assert result["status"] == "parsed"
    assert [(r["name"], r["jurisdiction"]) for r in result["rows"]] == singles + [
        ("Acme United Netherlands Cooperatie U.A.", "Netherlands"), ("Acme United (APAC) Pte.Ltd.", "Singapore")]
    assert len(result["rows"]) == 6
    assert [r["sourceRow"]["blockIndex"] for r in result["rows"][-2:]] == [0, 1]
    assert result["rows"][-1]["sourceRow"]["index"] == result["rows"][-2]["sourceRow"]["index"]
    assert all(r["ownershipPct"] is None and r["directOwnership"] == "unspecified" for r in result["rows"])


@pytest.mark.parametrize("wrapper", ["p", "div", "br"])
def test_explicit_matched_blocks_split_but_inline_spans_remain_whole(wrapper):
    names = ["<span>Example </span><font>Holdings, </font><span>Inc.</span>", "<b>Other </b><span>Ltd.</span>"]
    jurisdictions = ["<span>New </span><font>Zealand</font>", "Singapore"]
    wrap = lambda values: "<br>".join(values) if wrapper == "br" else "".join(f"<{wrapper}>{v}</{wrapper}>" for v in values)
    result = parse_exhibit(_exhibit([(wrap(names), wrap(jurisdictions))]), META)
    assert result["status"] == "parsed"
    assert [(r["name"], r["jurisdiction"]) for r in result["rows"]] == [
        ("Example Holdings, Inc.", "New Zealand"), ("Other Ltd.", "Singapore")]
    single = parse_exhibit(_exhibit([(names[0], jurisdictions[0])]), META)
    assert single["status"] == "parsed"
    assert single["rows"][0]["name"] == "Example Holdings, Inc."


@pytest.mark.parametrize("name,jurisdiction", [
    ("<p>First Inc.</p><p>Second Ltd.</p>", "<p>Netherlands</p>"),
    ("<p>First Inc.</p>", "<p>Netherlands</p><p>Singapore</p>"),
    ("<p>Example Holdings</p><p>Inc.</p>", "<p>New</p><p>Zealand</p>"),
    ("<p>First Inc.</p><p>Second</p>", "<p>Netherlands</p><p>Singapore</p>"),
    ("First Inc.; Second Ltd.", "Netherlands; Singapore"),
    ("First Inc. Second Ltd.", "Netherlands Singapore"),
    ("<span>First Inc.</span><span>Second Ltd.</span>", "Netherlands Singapore"),
    ("<p>Inc.</p><p>Ltd.</p>", "<p>Netherlands</p><p>Singapore</p>"),
    ("<p>First Inc. Second Ltd.</p><p>Third LLC</p>", "<p>Netherlands</p><p>Singapore</p>"),
])
def test_ambiguous_or_mismatched_multi_entry_cells_never_concatenate_fake_entities(name, jurisdiction):
    result = parse_exhibit(_exhibit([("Safe Inc.", "Delaware"), (name, jurisdiction)]), META)
    assert result["status"] == "needs-review"
    assert [(r["name"], r["jurisdiction"]) for r in result["rows"]] == [("Safe Inc.", "Delaware")]


def test_split_entities_still_obey_row_cap_and_vie_quarantine():
    pairs = [("<p>First Inc.</p><p>Second Ltd.</p>", "<p>Delaware</p><p>Singapore</p>")]
    capped = parse_exhibit(_exhibit(pairs * 501), META)
    assert capped["status"] == "needs-review"
    assert len(capped["rows"]) == 1000
    assert parse_exhibit(_exhibit(pairs) + "<p>Variable Interest Entities</p>", META)["rows"] == []


@pytest.mark.parametrize("issuer_name", ["AMREP CORP.", "Amrep Corporation", "AMREP, CORP."])
def test_explicit_axr_registrant_is_excluded_only_after_official_root_name_match(issuer_name):
    fixture = _exhibit([("AMREP Corporation (Registrant)", "Oklahoma"), ("Subsidiary Inc.", "Delaware")])
    metadata = {**META, "issuerName": issuer_name}
    before = metadata.copy()
    result = parse_exhibit(fixture, metadata)
    assert result["status"] == "parsed"
    assert [r["name"] for r in result["rows"]] == ["Subsidiary Inc."]
    assert metadata == before


@pytest.mark.parametrize("issuer_name", [None, "", "Other Corporation", "AMREP Holdings Corp.", 42])
def test_registrant_without_matching_root_is_quarantined_not_a_subsidiary(issuer_name):
    result = parse_exhibit(_exhibit([("AMREP Corporation (Registrant)", "Oklahoma"),
                                     ("Subsidiary Inc.", "Delaware")]), {**META, "issuerName": issuer_name})
    assert result["status"] == "needs-review"
    assert [r["name"] for r in result["rows"]] == ["Subsidiary Inc."]


def test_registrant_guard_does_not_globally_strip_or_alias_other_company_names():
    result = parse_exhibit(_exhibit([("AMREP Corporation", "Oklahoma"),
                                     ("AMREP Holdings Corporation", "Delaware")]), {**META, "issuerName": "AMREP CORP."})
    assert result["status"] == "parsed"
    assert [r["name"] for r in result["rows"]] == ["AMREP Corporation", "AMREP Holdings Corporation"]
    paired = _exhibit([("<p>AMREP Corporation (Registrant)</p><p>Subsidiary Inc.</p>",
                        "<p>Oklahoma</p><p>Delaware</p>")])
    result = parse_exhibit(paired, {**META, "issuerName": "AMREP CORP."})
    assert result["status"] == "parsed"
    assert [r["name"] for r in result["rows"]] == ["Subsidiary Inc."]
    assert result["rows"][0]["sourceRow"]["blockIndex"] == 1


@pytest.mark.parametrize("marker", ["1", "(2)", "*", "†", "‡", "¹"])
def test_trailing_numeric_symbol_sup_footnotes_leave_complete_inline_names_intact(marker):
    fixture = _exhibit([(f"<p><font>Example </font><span>Corp.</span><sup><a>{marker}</a></sup></p>",
                         "<p>New <span>Zealand</span><sup>1</sup></p>")])
    result = parse_exhibit(fixture, META)
    assert result["status"] == "parsed"
    assert [(r["name"], r["jurisdiction"]) for r in result["rows"]] == [("Example Corp.", "New Zealand")]
    self_row = _exhibit([(f"AMREP Corporation (Registrant)<sup>{marker}</sup>", "Oklahoma"),
                         ("Subsidiary Inc.", "Delaware")])
    assert [r["name"] for r in parse_exhibit(self_row, {**META, "issuerName": "AMREP CORP."})["rows"]] == ["Subsidiary Inc."]


@pytest.mark.parametrize("name", ["Example<sup>2</sup> Corp.", "Example Corp.<sup>Other Ltd.</sup>",
                                  "Example Corp.<sup>a</sup>", "Example Corp.<sup>1</sup> Holdings",
                                  "Example<sup>1</sup>"])
def test_ambiguous_or_embedded_sup_content_requires_review_instead_of_deleting_legal_text(name):
    result = parse_exhibit(_exhibit([(name, "Delaware")]), META)
    assert result["status"] == "needs-review"
    assert result["rows"] == []


@pytest.mark.parametrize("annotation", [
    "f/k/a Neuman USA Ltd.", "FKA Neuman USA Ltd.", "formerly known as Neuman USA Ltd.",
    "f/k/a Neuman USA Ltd.; Name Change on 09/06/13", "f/k/a Neuman (USA) Ltd.",
])
def test_explicit_balanced_ball_historical_alias_keeps_current_name_and_original_source_text(annotation):
    current = "Ball Advanced Aluminum Technologies Corp."
    original = f"{current} ({annotation})"
    result = parse_exhibit(_exhibit([(original, "Delaware")]), META)
    assert result["status"] == "parsed"
    assert [(r["name"], r["jurisdiction"]) for r in result["rows"]] == [(current, "Delaware")]
    assert result["rows"][0]["sourceRow"]["text"] == original + " Delaware"
    assert result["rows"][0]["ownershipPct"] is None
    assert result["rows"][0]["directOwnership"] == "unspecified"


@pytest.mark.parametrize("name", [
    "Ball Corp. (f/k/a Old Ltd.", "Ball Corp. (FKA )", "(f/k/a Old Ltd.)", "Ball (f/k/a Old Ltd.)",
    "Ball Corp. (f/k/a Old Ltd.))", "Ball Corp. (f/k/a Old Ltd.) and Other Inc.",
    "Ball Corp. Old Ltd.", "Ball Corp.; Old Ltd.", "First Inc. Second Ltd. (f/k/a Old Corp.)",
])
def test_alias_guard_does_not_rescue_incomplete_annotations_or_unmarked_multiple_companies(name):
    result = parse_exhibit(_exhibit([(name, "Delaware")]), META)
    assert result["status"] == "needs-review"
    assert result["rows"] == []


def test_alias_guard_preserves_general_parentheses_and_wrapped_inline_text():
    for name in ["Ball (Asia Pacific) Corp.", "Ball Corp. (wholly owned)"]:
        result = parse_exhibit(_exhibit([(name, "Delaware")]), META)
        assert result["status"] == "parsed"
        assert result["rows"][0]["name"] == name
    name = "<span>Ball Advanced Aluminum </span><font>Technologies Corp.</font> (f/k/a <span>Neuman USA Ltd.</span>)<sup>1</sup>"
    result = parse_exhibit(_exhibit([(name, "Delaware")]), META)
    assert result["status"] == "parsed"
    assert result["rows"][0]["name"] == "Ball Advanced Aluminum Technologies Corp."
    assert "f/k/a Neuman USA Ltd." in result["rows"][0]["sourceRow"]["text"]


def test_ap_plain_trailing_star_is_footnote_without_rewriting_legal_names_or_source_text():
    names = ["Air &amp; Liquid Systems Corporation*", "Ampco-Pittsburgh Securities V L.L.C.*", "Åkers AB*"]
    result = parse_exhibit(_exhibit([(name, "Delaware") for name in names]), META)
    assert result["status"] == "parsed"
    assert [r["name"] for r in result["rows"]] == ["Air & Liquid Systems Corporation", "Ampco-Pittsburgh Securities V L.L.C.", "Åkers AB"]
    assert all("*" in r["sourceRow"]["text"] for r in result["rows"])


@pytest.mark.parametrize("tag,style", [
    ("font", "font-size:6.5pt;position:relative;top:-3.5pt;vertical-align:baseline"),
    ("font", "font-size:6.5pt;vertical-align:super"),
    ("span", "font-size:7pt;vertical-align:super"),
])
def test_apog_explicit_small_raised_numeric_fonts_are_endnotes_not_name_suffixes(tag, style):
    names = ["Apogee Services, Inc.", "Viracon Singapore Pte. Ltd", "Glassec Vidros de Seguranca Ltda.",
             "Harmon Facades ULC", "Universal Woods EMEA, BVBA"]
    html = _exhibit([(f'<div><font style="font-size:10pt">{name}</font><{tag} style="{style}">({i})</{tag}></div>', "Delaware")
                     for i, name in enumerate(names, 1)])
    result = parse_exhibit(html, META)
    assert result["status"] == "parsed"
    assert [r["name"] for r in result["rows"]] == names
    assert all(f"({i})" in r["sourceRow"]["text"] for i, r in enumerate(result["rows"], 1))


@pytest.mark.parametrize("annotation", ["50% owned", "100% owned", "50.5% owned"])
def test_cal_exact_trailing_percent_owned_is_separate_annotation_never_an_inferred_percentage(annotation):
    original = f"CLT Brand Solutions Limited ({annotation})"
    result = parse_exhibit(_exhibit([(original, "United Kingdom")]), META)
    assert result["status"] == "parsed"
    assert result["rows"][0]["name"] == "CLT Brand Solutions Limited"
    assert result["rows"][0]["sourceRow"]["text"] == original + " United Kingdom"
    assert result["rows"][0]["ownershipPct"] is None
    assert result["rows"][0]["directOwnership"] == "unspecified"
    generic = "CLT Brand Solutions Trading Limited (Hong Kong)"
    assert parse_exhibit(_exhibit([(generic, "Hong Kong")]), META)["rows"][0]["name"] == generic


@pytest.mark.parametrize("name", [
    "Example* Corp.", "*", "Example Corp.**", "Example Corp. (50% owned", "Example Corp. (150% owned)",
    "Example Corp. (50% owned))", "Example Corp. (50% owned) Other Ltd.", "Example Corp. (HK",
    'Example<font style="font-size:6.5pt;position:relative;top:-3.5pt">(1)</font> Corp.',
    'Example Corp.<font style="font-size:6.5pt;vertical-align:super">Other Ltd.</font>',
])
def test_unsafe_footnotes_unbalanced_names_and_nonexact_ownership_annotations_stay_quarantined(name):
    result = parse_exhibit(_exhibit([(name, "Delaware")]), META)
    assert result["status"] == "needs-review"
    assert result["rows"] == []


def _paged_exhibit(gap="", second=None, heading="Example Inc."):
    # Repeated explicit headers reflect ADI's two-page Exhibit 21 structure.
    first = _exhibit([("First Ltd.", "Ireland")])
    second = second or _exhibit([("Second GmbH", "Germany")])
    return ("<html><head><style>td { padding: 2px; }</style></head><body>"
            f"<h1>SUBSIDIARIES OF {heading}</h1><div>{first}</div>{gap}"
            f"<div>{second}</div></body></html>")


@pytest.mark.parametrize("gap", ["", "<div>1</div>", "<div>Page 1</div>"])
def test_identical_page_headers_keep_rows_and_original_table_identity(gap):
    result = parse_exhibit(_paged_exhibit(gap), {**META, "issuerName": "EXAMPLE INC."})
    assert result["status"] == "parsed"
    assert [(r["name"], r["jurisdiction"]) for r in result["rows"]] == [
        ("First Ltd.", "Ireland"), ("Second GmbH", "Germany")]
    assert [r["sourceRow"]["tableIndex"] for r in result["rows"]] == [0, 1]
    assert all(r["ownershipPct"] is None and r["directOwnership"] == "unspecified" for r in result["rows"])


@pytest.mark.parametrize("gap", ["<h2>Subsidiaries of Other Inc.</h2>", "<p>Joint ventures</p>",
                               "<p>Former subsidiaries</p>", "<p>50% owned</p>"])
def test_repeated_headers_do_not_join_different_parent_or_relationship_scopes(gap):
    result = parse_exhibit(_paged_exhibit(gap), {**META, "issuerName": "Example Inc."})
    assert result["status"] == "needs-review" and result["rows"] == []


@pytest.mark.parametrize("issuer", [None, "Other Inc.", "Example Holdings Inc."])
def test_multiple_tables_require_explicit_matching_registrant_heading(issuer):
    result = parse_exhibit(_paged_exhibit(), {**META, "issuerName": issuer})
    assert result["status"] == "needs-review" and result["rows"] == []


def test_registrant_name_is_not_a_prefix_match_for_another_parent():
    result = parse_exhibit(_paged_exhibit(heading="Example Inc. Holdings"),
                           {**META, "issuerName": "Example Inc."})
    assert result["status"] == "needs-review" and result["rows"] == []


@pytest.mark.parametrize("prefix", ["Former ", "Previous ", "Non-", "Not "])
def test_continuation_rejects_past_or_negated_root_heading(prefix):
    html = _paged_exhibit().replace("SUBSIDIARIES OF", prefix + "SUBSIDIARIES OF")
    result = parse_exhibit(html, {**META, "issuerName": "Example Inc."})
    assert result["status"] == "needs-review" and result["rows"] == []


def test_single_candidate_nested_under_another_scope_is_quarantined():
    html = "<table><tr><td>Other parent's subsidiaries" + _exhibit([("First Ltd.", "Ireland")]) + "</td></tr></table>"
    result = parse_exhibit(html, {**META, "issuerName": "Example Inc."})
    assert result["status"] == "needs-review" and result["rows"] == []


def test_continuation_does_not_relax_headers_ambiguous_rows_or_total_row_cap():
    different = _exhibit([("Second GmbH", "Germany")]).replace("Subsidiary Name", "Company Name")
    result = parse_exhibit(_paged_exhibit(second=different), {**META, "issuerName": "Example Inc."})
    assert result["status"] == "needs-review" and result["rows"] == []
    ambiguous = _exhibit([("Second Inc. Third Ltd.", "Germany")])
    result = parse_exhibit(_paged_exhibit(second=ambiguous), {**META, "issuerName": "Example Inc."})
    assert result["status"] == "needs-review"
    assert [r["name"] for r in result["rows"]] == ["First Ltd."]
    huge = _exhibit([(f"Subsidiary {i} Ltd.", "Ireland") for i in range(1000)])
    result = parse_exhibit(_paged_exhibit(second=huge), {**META, "issuerName": "Example Inc."})
    assert result["status"] == "needs-review" and len(result["rows"]) == 1000


def test_adi_flat_issuer_qualified_name_contains_explicit_jurisdiction_between_legal_words():
    # ADI SHA 51f57873bca72de428ff4b99d1b8f77a9a5c6f95ab5664976fa9ef1468d22342:
    # a single font-wrapped name and a single explicit Egypt jurisdiction cell.
    row = '<font>Analog\xa0Devices\xa0Limited\xa0Egypt\xa0LLC</font>'
    html = _paged_exhibit(heading="ANALOG DEVICES, INC.", second=_exhibit([(row, "Egypt")]))
    result = parse_exhibit(html, {**META, "issuerName": "ANALOG DEVICES INC"})
    assert result["status"] == "parsed"
    assert result["rows"][-1]["name"] == "Analog Devices Limited Egypt LLC"
    assert result["rows"][-1]["jurisdiction"] == "Egypt"
    assert result["rows"][-1]["sourceRow"]["text"] == "Analog Devices Limited Egypt LLC Egypt"
    assert result["rows"][-1]["ownershipPct"] is None


@pytest.mark.parametrize("name,jurisdiction", [
    ("Other Devices Limited Egypt LLC", "Egypt"),
    ("Analog Devices Limited Egypt LLC", "Ireland"),
    ("Analog Devices Limited Egypt LLC Other Inc.", "Egypt"),
    ("Analog Devices Limited; Egypt LLC", "Egypt"),
    ("<p>Analog Devices Limited Egypt</p><p>LLC</p>", "<p>Egypt</p><p>Egypt</p>"),
    ("Analog Devices Limited Egypt LLC (f/k/a Old Inc.", "Egypt"),
])
def test_jurisdiction_qualified_legal_name_does_not_rescue_other_roots_or_multiple_entities(name, jurisdiction):
    result = parse_exhibit(_exhibit([(name, jurisdiction)]), {**META, "issuerName": "ANALOG DEVICES INC"})
    assert result["status"] == "needs-review" and result["rows"] == []


@pytest.mark.parametrize("name_header,jurisdiction_header,spacer", [
    ("Name of Subsidiary", "State of Organization", True),
    ("Name", "State or Country of Organization", False),
    ("Company", "Jurisdiction of Formation", False),
    ("COMPANY", "STATE OF ORGANIZATION", True),
])
def test_exact_original_organization_headers_preserve_flat_rows_and_optional_spacer(
        name_header, jurisdiction_header, spacer):
    # ALX/BRT have a blank middle column; HWM/ARTW have two direct cells.
    middle = "<td></td>" if spacer else ""
    html = ("<table><tr>" + "<td></td>" * 9 + "</tr>"
            f"<tr><td>{name_header}</td>{middle}<td>{jurisdiction_header}</td></tr>"
            f"<tr><td></td>{middle}<td></td></tr>"
            f"<tr><td><font>Explicit Services LLC</font></td>{middle}<td><font>Delaware</font></td></tr></table>")
    result = parse_exhibit(html, META)
    assert result["status"] == "parsed"
    assert [(r["name"], r["jurisdiction"]) for r in result["rows"]] == [("Explicit Services LLC", "Delaware")]
    assert result["rows"][0]["sourceRow"]["index"] == 3
    assert result["rows"][0]["ownershipPct"] is None
    assert result["rows"][0]["directOwnership"] == "unspecified"


@pytest.mark.parametrize("name_header,jurisdiction_header", [
    ("Company Profile", "State of Organization"),
    ("Company Group", "State of Organization"),
    ("Company", "State"), ("Company", "Country"), ("Company", "Organization"),
    ("Company", "State of Organization Summary"),
    ("Name", "State or Country of Organization Unknown"),
])
def test_new_header_synonyms_do_not_accept_partial_or_fuzzy_organization_labels(name_header, jurisdiction_header):
    html = (f"<table><tr><td>{name_header}</td><td>{jurisdiction_header}</td></tr>"
            "<tr><td>Explicit Services LLC</td><td>Delaware</td></tr></table>")
    result = parse_exhibit(html, META)
    assert result["status"] == "needs-review" and result["rows"] == []


def test_hwm_exact_metadata_registrant_is_excluded_without_aliasing_similar_entities():
    names = ["Howmet Aerospace Inc.", "Howmet Aerospace Inc", "Howmet Aerospace Incorporated",
             "Howmet Aerospace Holdings Inc.", "Howmet International Inc."]
    html = _exhibit([(name, "Delaware, US") for name in names]).replace(
        "Subsidiary Name", "Name").replace("Jurisdiction of Incorporation", "State or Country of Organization")
    result = parse_exhibit(html, {**META, "issuerName": "Howmet Aerospace Inc."})
    assert result["status"] == "parsed"
    assert [r["name"] for r in result["rows"]] == names[1:]
    assert [r["sourceRow"]["index"] for r in result["rows"]] == [2, 3, 4, 5]
    unknown = parse_exhibit(html, META)
    assert [r["name"] for r in unknown["rows"]] == names


def test_hwm_header_recovery_does_not_relax_multiple_legal_terminator_guard():
    html = _exhibit([("Howmet Aerospace Inc.", "Delaware, US"),
                     ("Howmet International Inc.", "Delaware, US"),
                     ("FR Acquisition Corporation (US), Inc.", "Delaware, US"),
                     ("FR Acquisitions Corporation Europe Limited", "United Kingdom")]).replace(
        "Subsidiary Name", "Name").replace("Jurisdiction of Incorporation", "State or Country of Organization")
    result = parse_exhibit(html, {**META, "issuerName": "Howmet Aerospace Inc."})
    assert result["status"] == "needs-review"
    assert [r["name"] for r in result["rows"]] == ["Howmet International Inc."]


def _air_pages(heading="AAR CORP. Subsidiaries", gap="\u200b", header="Name (1)"):
    def page(rows):
        return ("<table><tr><td>\u200b</td><td>\u200b</td><td>\u200b</td></tr>"
                f"<tr><td>{header}</td><td>Place of Incorporation</td><td>Doing Business As</td></tr>"
                + "".join(f"<tr><td>{name}</td><td>Delaware</td><td>{dba}</td></tr>"
                          for name, dba in rows) + "</table>")
    return (f"<h1>{heading}</h1>" + page([
        ("<b>AAR CORP.</b>", "AAR Aviation Corp."),
        ("<i>AAR Americas, LLC (formerly HAECO Americas, LLC)</i>", "Old Brand"),
    ]) + gap + page([("<i>AAR Other Services LLC</i>", "AAR Trading Brand")]))


def test_air_footnoted_repeated_headers_exclude_title_bound_self_and_keep_source_annotations():
    # Structural fixture from AIR Exhibit 21.1, 2026-05-31 financial period.
    # SHA256 ea75922c9a21204206a458eb84bf3156056d2ca6ce24447b89f3d39392eded51
    result = parse_exhibit(_air_pages(), {**META, "issuerName": "AAR CORP"})
    assert result["status"] == "parsed"
    assert [r["name"] for r in result["rows"]] == ["AAR Americas, LLC", "AAR Other Services LLC"]
    assert [r["sourceRow"]["tableIndex"] for r in result["rows"]] == [0, 1]
    assert "formerly HAECO Americas, LLC" in result["rows"][0]["sourceRow"]["text"]
    assert "Old Brand" in result["rows"][0]["sourceRow"]["text"]
    assert all(r["ownershipPct"] is None and r["directOwnership"] == "unspecified" for r in result["rows"])


@pytest.mark.parametrize("header", ["Name 1", "Name (a)", "Name (1) summary", "Name (1)(2)"])
def test_footnoted_name_header_does_not_accept_nonexact_labels(header):
    result = parse_exhibit(_air_pages(header=header), {**META, "issuerName": "AAR CORP"})
    assert result["status"] == "needs-review" and result["rows"] == []


@pytest.mark.parametrize("heading", ["AAR CORP. Holdings Subsidiaries", "Other Corp. Subsidiaries",
    "Former AAR CORP. Subsidiaries", "AAR CORP. Subsidiaries sold", "AAR CORP. Subsidiaries of Other Corp."])
def test_root_first_title_does_not_rescue_different_or_historical_scopes(heading):
    result = parse_exhibit(_air_pages(heading=heading), {**META, "issuerName": "AAR CORP"})
    assert result["status"] == "needs-review" and result["rows"] == []


@pytest.mark.parametrize("gap", ["<p>Other parent's subsidiaries</p>", "<p>Joint ventures</p>"])
def test_root_first_title_keeps_scope_change_quarantine(gap):
    result = parse_exhibit(_air_pages(gap=gap), {**META, "issuerName": "AAR CORP"})
    assert result["status"] == "needs-review" and result["rows"] == []


@pytest.mark.parametrize("name", ["Example LLC (formerly )", "Example (formerly Other LLC)",
    "Example LLC (formerly Other LLC", "Example LLC (formerly Other LLC) and Another Inc."])
def test_short_formerly_annotation_does_not_rescue_ambiguous_names(name):
    result = parse_exhibit(_exhibit([(name, "Delaware")]), META)
    assert result["status"] == "needs-review" and result["rows"] == []


def _leading_title_exhibit(*, issuer="Example Corp.", stated="December 31, 2025",
                           title="List of Subsidiaries", jurisdiction="State of Organization",
                           preamble="", row="<tr><td>Example Services LLC</td><td>DE</td></tr>",
                           after=""):
    return ("<table><tr><td></td><td></td></tr><tr><td>EXHIBIT 21</td><td></td></tr>"
            f"<tr><td colspan='2'>{issuer}</td></tr>"
            f"<tr><td colspan='2'>{title}</td></tr>"
            f"<tr><td colspan='2'>as of {stated}</td></tr>{preamble}"
            f"<tr><th>Subsidiary</th><th>{jurisdiction}</th></tr>{row}</table>{after}")


_LEADING_META = {**META, "issuerName": "Example Corp", "periodEnd": "2025-12-31",
                 "filedDate": "2026-02-19"}


def test_bound_leading_title_and_late_header_use_existing_row_contract():
    result = parse_exhibit(_leading_title_exhibit(), _LEADING_META)
    assert result["status"] == "parsed"
    assert result["parserRevision"] == "2026-10-25-bound-leading-title-table-v17"
    assert result["scope"] == "reported-subsidiary-list-not-exhaustive"
    assert [(r["name"], r["jurisdiction"]) for r in result["rows"]] == [
        ("Example Services LLC", "DE")]
    assert result["rows"][0]["ownershipPct"] is None
    assert result["rows"][0]["directOwnership"] == "unspecified"


@pytest.mark.parametrize("change", [
    {"issuer": "Other Corp."},
    {"stated": "December 30, 2025"},
    {"preamble": "<tr><td>Other Business LLC</td><td>DE</td></tr>"},
    {"jurisdiction": "State"},
    {"row": "<tr><td>Example Services LLC d/b/a Other</td><td>DE</td></tr>"},
    {"row": "<tr><td>Example Services Trust</td><td>DE</td></tr>"},
    {"row": "<tr><td>Example Services LLC</td><td>100% DE</td></tr>"},
    {"row": "<tr><td colspan='2'>Other Parent Subsidiaries</td></tr>"
            "<tr><td>Example Services LLC</td><td>DE</td></tr>"},
    {"after": "<p>Other parent's subsidiaries follow.</p>"},
])
def test_bound_leading_title_rejects_scope_and_row_mutations(change):
    result = parse_exhibit(_leading_title_exhibit(**change), _LEADING_META)
    assert result["status"] == "needs-review" and result["rows"] == []
    if "stated" in change:
        assert result["reviewReason"] == "exhibit-as-of-differs-from-period-end"


@pytest.mark.parametrize("issuer,sha,meta,expected", [
    ("SRE", "5fb4071b9a8bd9b2a936accb22e273cb7daa69050d27d7133e851eacabde3017",
     {"cik": "0001032208", "accession": "0001032208-26-000010", "filedDate": "2026-02-26",
      "periodEnd": "2025-12-31", "issuerName": "SEMPRA", "url":
      "https://www.sec.gov/Archives/edgar/data/86521/000103220826000010/sempra-123125xex211.htm"},
     [("San Diego Gas & Electric Company", "California"),
      ("Sempra Infrastructure Partners, LP", "Delaware"),
      ("Sempra Texas Intermediate Holding Company LLC", "Delaware"),
      ("Southern California Gas Company", "California")]),
    ("PRDO", "b2b6a723cc7b3fa06a26a2485362b0f27054a71c3a2c36ddf5036d431ab513c6",
     {"cik": "0001046568", "accession": "0001193125-26-059331", "filedDate": "2026-02-19",
      "periodEnd": "2025-12-31", "issuerName": "PERDOCEO EDUCATION Corp", "url":
      "https://www.sec.gov/Archives/edgar/data/1046568/000119312526059331/prdo-ex21.htm"},
     [("AIU Online, LLC", "DE"), ("American InterContinental University System, Inc.", "GA"),
      ("Career Education Student Finance LLC", "DE"), ("CEC Educational Services, LLC", "IL"),
      ("CEC Employee Group, LLC", "DE"), ("CEC Real Estate Holding, Inc.", "DE"),
      ("Colorado Tech, Inc.", "DE"), ("Colorado Technical University, Inc.", "CO"),
      ("MAC BriarCol, Inc.", "NY"), ("MAC KGC-Mel, Corp.", "NY"),
      ("MAC LCBCS, LLC", "DE"), ("MAC LCBNA, LLC", "DE"),
      ("MAC SB, Limited", "NY"), ("Marlin Acquisition Corp.", "FL"),
      ("Trident University International, LLC", "DE"),
      ("University of St. Augustine Acquisition Corp.", "DE"),
      ("University of St. Augustine for Health Sciences, LLC", "CA"),
      ("University of St. Augustine Intermediate Corp.", "DE"),
      ("University of St. Augustine Parent Corp.", "DE"),
      ("Words of Wisdom, LLC", "IL")]),
])
def test_bound_leading_title_saved_originals(issuer, sha, meta, expected):
    cache = os.environ.get("SEC_EXHIBIT_CACHE_DIR")
    if not cache:
        pytest.skip("saved SEC original cache is not mounted")
    path = Path(cache) / f"{sha}.gz"
    if not path.is_file():
        pytest.skip("saved SEC original is unavailable")
    raw = gzip.decompress(path.read_bytes())
    assert hashlib.sha256(raw).hexdigest() == sha
    result = parse_exhibit(raw, meta)
    assert result["status"] == "parsed", (issuer, result.get("reviewReason"))
    assert result["documentSha256"] == sha
    assert result["periodEnd"] == "2025-12-31"
    assert result["scope"] == "reported-subsidiary-list-not-exhaustive"
    assert [(r["name"], r["jurisdiction"]) for r in result["rows"]] == expected
    assert all(r["ownershipPct"] is None and r["directOwnership"] == "unspecified"
               for r in result["rows"])
