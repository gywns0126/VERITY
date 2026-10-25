"""Strict co-filer section parsing; all fixtures are local and network-free."""

import gzip
import hashlib
import json
import os
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from api.intelligence.company_structure_sec_sections import (
    parse_bound_name_list,
    parse_cofiler_sections,
)


SPG_DOCUMENT_SHA256 = "b2cd57f2f39531572cac9d5e9c5b188ed7ce6020e325a93dbd45fc824b3466e7"
SPG_INDEX_SHA256 = "22fc1955c30aa1e8026ab3ef10f961bb86397eb9697dec4a4bccb2eca578a63a"
V17_SHA256 = "4dbb4c8c79e49246134931f0027f4363fc4ef3b3c716e68c8859232bf3d7634e"
_evidence_dir = os.environ.get("COFILER_AUDIT_EVIDENCE_DIR")
EVIDENCE_DIR = Path(_evidence_dir) if _evidence_dir else None


def _meta(issuer="SIMON PROPERTY GROUP INC."):
    return {
        "cik": "0001063761",
        "accession": "0001104659-26-019419",
        "filedDate": "2026-02-25",
        "periodEnd": "2025-12-31",
        "issuerName": issuer,
        "url": "https://www.sec.gov/Archives/edgar/data/1022344/000110465926019419/spg-20251231xex21d1.htm",
        "cofilerProof": {
            "requestedCik": "0001063761",
            "accession": "0001104659-26-019419",
            "issuerName": issuer,
            "exhibitUrl": "https://www.sec.gov/Archives/edgar/data/1022344/000110465926019419/spg-20251231xex21d1.htm",
        },
        "cofilerIndexRaw": b"previously verified SEC index bytes",
    }


def _table(rows):
    body = "".join(f"<tr><td>{name}</td><td>{jurisdiction}</td></tr>" for name, jurisdiction in rows)
    return ("<table><tr><th>Subsidiary</th><th>Jurisdiction</th></tr>" + body + "</table>")


def _two_section_exhibit(first_rows=None, second_rows=None, *, first_title=None,
                         second_title=None, after="", between=""):
    first_rows = first_rows or [("Retail Trust LLC", "Indiana")]
    second_rows = second_rows or [("Retail Trust LLC", "Indiana")]
    first_title = first_title or "List of Subsidiaries of Simon Property Group, Inc."
    second_title = second_title or "List of Subsidiaries of Simon Property Group, L.P."
    return BeautifulSoup(
        "<body><p>Exhibit 21.1</p>"
        f"<p>{first_title}</p>{_table(first_rows)}{between}"
        f"<p>{second_title}</p>{_table(second_rows)}{after}</body>",
        "html.parser",
    )


def _parse(soup, metadata=None):
    return parse_cofiler_sections(soup, metadata or _meta(), {"rows": [], "status": "needs-review"})


def test_actual_spg_original_hash_and_both_parent_sections_are_reviewed():
    if EVIDENCE_DIR is None or not EVIDENCE_DIR.is_dir():
        pytest.skip("Set COFILER_AUDIT_EVIDENCE_DIR to the preserved replay evidence directory")

    replay_path = EVIDENCE_DIR / "cofiler-bound-replay-v17-20261025.json"
    replay_bytes = replay_path.read_bytes()
    assert hashlib.sha256(replay_bytes).hexdigest() == V17_SHA256
    replay = json.loads(replay_bytes)
    receipt = next(row for row in replay["rows"] if row["cik"] == "0001063761")
    assert receipt["result"]["documentSha256"] == SPG_DOCUMENT_SHA256
    assert receipt["result"]["cofilerProof"]["indexSha256"] == SPG_INDEX_SHA256

    repository = Path(__file__).resolve().parents[1]
    source = json.loads((repository / "data/member_map_company_structure_us_sources.json").read_text())
    issuer = source["issuers"]["0001063761"]
    filing = issuer["filingMetadata"]
    assert issuer["tickerAliases"] == ["SPG"]
    for field in ("cik", "accession", "issuer_name", "filed_date", "period_end"):
        assert filing[field] == receipt["filingMetadata"][field]

    original = gzip.decompress((EVIDENCE_DIR / "raw-cache" / (SPG_DOCUMENT_SHA256 + ".gz")).read_bytes())
    index = gzip.decompress((EVIDENCE_DIR / "raw-cache" / (SPG_INDEX_SHA256 + ".gz")).read_bytes())
    assert hashlib.sha256(original).hexdigest() == SPG_DOCUMENT_SHA256
    assert hashlib.sha256(index).hexdigest() == SPG_INDEX_SHA256
    metadata = {
        "cik": filing["cik"],
        "accession": filing["accession"],
        "filedDate": filing["filed_date"],
        "periodEnd": filing["period_end"],
        "issuerName": filing["issuer_name"],
        "url": receipt["result"]["cofilerProof"]["exhibitUrl"],
        "cofilerProof": receipt["result"]["cofilerProof"],
        "cofilerIndexRaw": index,
    }
    result = parse_cofiler_sections(BeautifulSoup(original, "html.parser"), metadata, {"rows": []})

    assert result["status"] == "parsed"
    assert [section["rowCount"] for section in result["reviewedSections"]] == [14, 13]
    assert [section["parentName"] for section in result["reviewedSections"]] == [
        "Simon Property Group, Inc.", "Simon Property Group, L.P."
    ]
    assert len(result["rows"]) == 14
    assert {row["parentName"] for row in result["rows"]} == {"Simon Property Group, Inc."}
    assert [row["sourceRow"]["tableIndex"] for row in result["rows"]] == [0] * 14
    assert [row["sourceRow"]["index"] for row in result["rows"]] == list(range(2, 16))
    assert all(row["name"] in row["sourceRow"]["text"] and
               row["jurisdiction"] in row["sourceRow"]["text"] for row in result["rows"])
    assert all(row["ownershipPct"] is None and row["directOwnership"] == "unspecified"
               and "from" not in row and "to" not in row for row in result["rows"])


def test_target_section_is_emitted_without_merging_identically_named_rows():
    soup = _two_section_exhibit(
        first_rows=[("Shared LLC", "Indiana"), ("Only Inc.", "Ohio")],
        second_rows=[("Shared LLC", "Delaware"), ("Secondary Only LLC", "Texas")],
    )
    result = _parse(soup)
    assert result["status"] == "parsed"
    assert [row["name"] for row in result["rows"]] == ["Shared LLC", "Only Inc."]
    assert [row["jurisdiction"] for row in result["rows"]] == ["Indiana", "Ohio"]
    assert [section["rowCount"] for section in result["reviewedSections"]] == [2, 2]
    assert [row["sourceRow"]["tableIndex"] for row in result["rows"]] == [0, 0]


@pytest.mark.parametrize("issuer", [
    "SIMON PROPERTY GROUP INCORPORATED",
    "SIMON PROPERTY GROUP COMPANY",
    "Another Parent Inc.",
])
def test_wrong_or_renamed_requested_parent_is_not_fuzzily_matched(issuer):
    result = _parse(_two_section_exhibit(), _meta(issuer))
    assert result["status"] == "needs-review"
    assert result["reviewReason"] == "issuer-scope-unbound"
    assert result["rows"] == []


def test_missing_section_heading_is_reviewed_not_guessed():
    soup = BeautifulSoup(
        "<body><p>Exhibit 21.1</p>" + _table([("Retail Trust LLC", "Indiana")]) +
        "<p>List of Subsidiaries of Simon Property Group, L.P.</p>" +
        _table([("Retail Trust LLC", "Indiana")]) + "</body>", "html.parser")
    result = _parse(soup)
    assert result["status"] == "needs-review"
    assert result["reviewReason"] == "missing-section-header"
    assert result["rows"] == []


def test_unreviewed_additional_table_blocks_promotion():
    soup = _two_section_exhibit(after=_table([("Unbound LLC", "Florida")]))
    result = _parse(soup)
    assert result["status"] == "needs-review"
    assert result["reviewReason"] == "unreviewed-table"
    assert result["rows"] == []


def test_shifted_name_and_jurisdiction_cells_do_not_pass_header_binding():
    misaligned = (
        "<table><tr><th>Subsidiary</th><td></td><th>Jurisdiction</th><td></td></tr>"
        "<tr><td></td><td>Retail Trust LLC</td><td></td><td>Indiana</td></tr></table>"
    )
    soup = BeautifulSoup(
        "<body><p>List of Subsidiaries of Simon Property Group, Inc.</p>" + misaligned +
        "<p>List of Subsidiaries of Simon Property Group, L.P.</p>" +
        _table([("Retail Trust LLC", "Indiana")]) + "</body>", "html.parser")
    result = _parse(soup)
    assert result["status"] == "needs-review"
    assert result["reviewReason"] == "column-position-mismatch"
    assert result["rows"] == []


@pytest.mark.parametrize("bad_rows,reason", [
    ([("Retail Trust LLC", "")], "partial-row"),
    ([("Retail Trust LLC 10% LLC", "Indiana")], "unsafe-or-incomplete-row"),
])
def test_partial_or_percentage_rows_block_the_whole_document(bad_rows, reason):
    soup = _two_section_exhibit(first_rows=bad_rows)
    result = _parse(soup)
    assert result["status"] == "needs-review"
    assert result["reviewReason"] == reason
    assert result["rows"] == []


def test_unrecognized_after_text_blocks_promotion():
    soup = _two_section_exhibit(after="<p>Additional subsidiaries appear in another schedule.</p>")
    result = _parse(soup)
    assert result["status"] == "needs-review"
    assert result["reviewReason"] == "unrecognized-scope-text"


@pytest.mark.parametrize("note,reason", [
    ("<p>Omits names of subsidiaries that as of December 31, 2024 were not, in the aggregate, “significant subsidiaries.”</p>",
     "after-text-or-date-mismatch"),
    ("<p>Omits non-significant subsidiaries.</p>", "unrecognized-scope-text"),
])
def test_after_note_must_be_known_and_match_metadata_period(note, reason):
    result = _parse(_two_section_exhibit(after=note))
    assert result["status"] == "needs-review"
    assert result["reviewReason"] == reason
    assert result["rows"] == []


def test_explicit_section_date_must_match_metadata_period():
    soup = _two_section_exhibit(first_title=(
        "List of Subsidiaries of Simon Property Group, Inc. as of January 1, 2026"))
    result = _parse(soup)
    assert result["status"] == "needs-review"
    assert result["reviewReason"] == "section-date-mismatch"
    assert result["rows"] == []


def test_cofiler_proof_must_match_requested_issuer_and_filing():
    metadata = _meta()
    metadata["cofilerProof"] = dict(metadata["cofilerProof"], accession="0000000000-00-000000")
    result = _parse(_two_section_exhibit(), metadata)
    assert result["status"] == "needs-review"
    assert result["reviewReason"] == "cofiler-proof-mismatch"
    assert result["rows"] == []


def test_flat_unjurisdictioned_awrs_style_document_is_not_this_parser_format():
    soup = BeautifulSoup(
        "<body><p>Exhibit 21</p><p>Subsidiaries of American States Water Company</p>"
        "<p>Golden State Water Company</p><p>American States Utility Services, Inc.</p></body>",
        "html.parser")
    assert _parse(soup) is None


def _awr_meta(issuer="AMERICAN STATES WATER CO"):
    return {
        "cik": "0001056903",
        "accession": "0001628280-26-009114",
        "filedDate": "2026-02-18",
        "periodEnd": "2025-12-31",
        "issuerName": issuer,
        "url": "https://www.sec.gov/Archives/edgar/data/92116/000162828026009114/ex21subsidiariesofawr-2025.htm",
        "cofilerProof": {
            "requestedCik": "0001056903",
            "accession": "0001628280-26-009114",
            "issuerName": issuer,
            "exhibitUrl": "https://www.sec.gov/Archives/edgar/data/92116/000162828026009114/ex21subsidiariesofawr-2025.htm",
        },
        "cofilerIndexRaw": b"verified AWR SEC index bytes",
    }


def _flat_list_document(title="Subsidiaries of American States Water Company", entries=None,
                        trailing=""):
    entries = entries or ["Golden State Water Company", "American States Utility Services, Inc."]
    body = "".join(f"<div>{entry}</div>" for entry in entries)
    return BeautifulSoup(
        f"<body><div>Exhibit 21</div><div>{title}</div>{body}{trailing}</body>",
        "html.parser",
    )


def test_actual_awr_original_emits_only_thirteen_unjurisdictioned_names():
    if EVIDENCE_DIR is None or not EVIDENCE_DIR.is_dir():
        pytest.skip("Set COFILER_AUDIT_EVIDENCE_DIR to the preserved replay evidence directory")

    repository = Path(__file__).resolve().parents[1]
    source = json.loads((repository / "data/member_map_company_structure_us_sources.json").read_text())
    filing = source["issuers"]["0001056903"]["filingMetadata"]
    replay = json.loads((EVIDENCE_DIR / "cofiler-bound-replay-v17-20261025.json").read_text())
    receipt = next(row for row in replay["rows"] if row["cik"] == "0001056903")
    for field in ("cik", "accession", "issuer_name", "filed_date", "period_end"):
        assert filing[field] == receipt["filingMetadata"][field]

    document_hash = receipt["result"]["documentSha256"]
    index_hash = receipt["result"]["cofilerProof"]["indexSha256"]
    original = gzip.decompress((EVIDENCE_DIR / "raw-cache" / f"{document_hash}.gz").read_bytes())
    index = gzip.decompress((EVIDENCE_DIR / "raw-cache" / f"{index_hash}.gz").read_bytes())
    assert hashlib.sha256(original).hexdigest() == document_hash
    assert hashlib.sha256(index).hexdigest() == index_hash

    proof = receipt["result"]["cofilerProof"]
    metadata = {
        "cik": filing["cik"], "accession": filing["accession"],
        "filedDate": filing["filed_date"], "periodEnd": filing["period_end"],
        "issuerName": filing["issuer_name"], "url": proof["exhibitUrl"],
        "cofilerProof": proof, "cofilerIndexRaw": index,
    }
    result = parse_bound_name_list(
        BeautifulSoup(original, "html.parser"), metadata, {"rows": []})

    assert result["status"] == "parsed"
    assert len(result["rows"]) == 13
    assert [row["name"] for row in result["rows"]] == [
        "Golden State Water Company", "American States Utility Services, Inc.",
        "Fort Bliss Water Services Company", "Old Dominion Utility Services, Inc.",
        "Terrapin Utility Services, Inc.", "Palmetto State Utility Services, Inc.",
        "Old North Utility Services, Inc.", "Emerald Coast Utility Services, Inc.",
        "Fort Riley Utility Services, Inc.", "Bay State Utility Services LLC",
        "Patuxent River Utility Services LLC", "California Cities Water Company, Inc.",
        "Bear Valley Electric Service, Inc.",
    ]
    assert all(row["jurisdiction"] is None and row["ownershipPct"] is None and
               row["directOwnership"] == "unspecified" and
               "from" not in row and "to" not in row for row in result["rows"])
    assert all(row["sourceRow"]["text"] == row["name"] for row in result["rows"])
    assert [row["sourceRow"]["index"] for row in result["rows"]] == list(range(3, 16))


def test_bound_name_list_accepts_only_exact_terminal_co_company_equivalence():
    metadata = _awr_meta()
    result = parse_bound_name_list(_flat_list_document(), metadata, {"rows": []})
    assert result["status"] == "parsed"
    assert result["rows"][0]["parentName"] == "American States Water Company"

    mismatch = parse_bound_name_list(
        _flat_list_document(title="Subsidiaries of American Water Company"),
        metadata, {"rows": []})
    assert mismatch["status"] == "needs-review"
    assert mismatch["reviewReason"] == "bound-list-issuer-mismatch"
    assert mismatch["rows"] == []

    expanded = parse_bound_name_list(
        _flat_list_document(title="Subsidiaries of American States Water Corporation"),
        metadata, {"rows": []})
    assert expanded["status"] == "needs-review"
    assert expanded["reviewReason"] == "bound-list-issuer-mismatch"


def test_bound_name_list_requires_current_cofiler_proof():
    metadata = _awr_meta()
    metadata.pop("cofilerProof")
    result = parse_bound_name_list(_flat_list_document(), metadata, {"rows": []})
    assert result["status"] == "needs-review"
    assert result["reviewReason"] == "cofiler-proof-mismatch"
    assert result["rows"] == []


@pytest.mark.parametrize("extra", [
    "<div>Unresolved additional subsidiaries</div>",
    "<div>Subsidiaries of Another Parent LLC</div>",
    "<div>Example Subsidiary LLC (wholly owned)</div>",
    "<div>Example Subsidiary LLC, wholly owned by Parent LLC</div>",
    "<div>Example Branch &amp; Supplemental Services LLC</div>",
    "<div>Example BR. &amp; SUP. LLC</div>",
    "<div>Example LLC and Other Company, Inc.</div>",
    "<div>Example LLC Second Company Inc.</div>",
    "<div>First Company Second Company</div>",
    "<div>Example Company<br>Second Company</div>",
    "<div>Example <sup>1</sup>Company</div>",
    "<div>American States Water Company</div>",
])
def test_bound_name_list_rejects_unknown_scope_parent_and_annotations(extra):
    soup = _flat_list_document(trailing=extra)
    result = parse_bound_name_list(soup, _awr_meta(), {"rows": []})
    assert result["status"] == "needs-review"
    assert result["rows"] == []


def test_bound_name_list_with_mixed_table_scope_is_held_for_review():
    soup = _flat_list_document(trailing=_table([("Unknown LLC", "Texas")]))
    result = parse_bound_name_list(soup, _awr_meta(), {"rows": []})
    assert result["status"] == "needs-review"
    assert result["reviewReason"] == "bound-list-unrecognized-scope"
    assert result["rows"] == []


def test_bound_name_list_rejects_explicit_date_mismatch():
    soup = _flat_list_document(
        title="Subsidiaries of American States Water Company as of January 1, 2026")
    result = parse_bound_name_list(soup, _awr_meta(), {"rows": []})
    assert result["status"] == "needs-review"
    assert result["reviewReason"] == "bound-list-date-mismatch"
    assert result["rows"] == []


def test_bound_name_list_without_evidence_cue_is_not_claimed():
    soup = BeautifulSoup("<body><div>Exhibit 21</div><div>Unrelated disclosure</div></body>",
                         "html.parser")
    assert parse_bound_name_list(soup, _awr_meta(), {"rows": []}) is None


def test_many_legal_name_blocks_preserve_existing_row_limit():
    soup = _flat_list_document(entries=[f"Entity {i} Company" for i in range(1001)])
    result = parse_bound_name_list(soup, _awr_meta(), {"rows": []})
    assert result["status"] == "needs-review"
    assert result["rows"] == []
    assert result["reviewReason"] == "row-limit"


def test_two_names_in_one_section_cell_are_not_merged():
    soup = _two_section_exhibit(first_rows=[("First LLC<br>Second LLC", "Indiana")])
    result = _parse(soup)
    assert result["status"] == "needs-review"
    assert result["rows"] == []


def test_public_parser_checks_parent_title_even_if_a_single_column_table_already_parses():
    from api.intelligence.company_structure_sec import find_exhibit, parse_exhibit
    metadata = _meta()
    index = ("<div class='companyInfo'><span>SIMON PROPERTY GROUP INC. (Filer) CIK: 0001063761</span></div>"
             "<div class='companyInfo'><span>SIMON PROPERTY GROUP L P (Filer) CIK: 0001022344</span></div>"
             "<table class='tableFile'><tr><th>Document</th><th>Type</th></tr>"
             f"<tr><td><a href='{metadata['url']}'>ex21.htm</a></td><td>EX-21.1</td></tr></table>").encode()
    _, proof = find_exhibit(index, cik=metadata['cik'], accession=metadata['accession'],
                            issuer_name=metadata['issuerName'], return_proof=True)
    metadata.update(cofilerProof=proof, cofilerIndexRaw=index)
    for parent, expected in [("Simon Property Group, Inc.", "parsed"), ("Other Parent Inc.", "needs-review")]:
        html = ("<body><p>Exhibit 21.1</p><p>List of Subsidiaries of " + parent + "</p>"
                + _table([("Actual Subsidiary LLC", "Indiana")]) + "</body>")
        result = parse_exhibit(html, metadata)
        assert result['status'] == expected
        assert len(result['rows']) == (1 if expected == 'parsed' else 0)


@pytest.mark.parametrize('name', ['First LLC Second LLC', 'First Company Second Company',
                                 'First LLC Second Company', 'First Company Second LLC'])
def test_two_unseparated_legal_entities_are_not_one_name(name):
    result = _parse(_two_section_exhibit(first_rows=[(name, 'Indiana')]))
    assert result['status'] == 'needs-review'
    assert result['rows'] == []
