from __future__ import annotations

from hashlib import sha256
from io import BytesIO
from pathlib import Path
import zipfile

import pytest

from api.intelligence import portfolio_annual_customer_tables as annual_tables
from api.intelligence.portfolio_annual_customer_tables import (
    capture_annual_customer_tables,
    index_annual_customer_table_captures,
    index_annual_customer_tables,
)
from api.intelligence.portfolio_business_roles import attach_business_relationships


ROOT = Path(__file__).resolve().parents[1]
CASE19 = ROOT / "output/member-map-integration-20260927/structured-table-20261008"
ARCHIVE = CASE19 / "dart-document-20260320001349.zip"
MEMBER = "20260320001349.xml"
RECEIPT = "20260320001349"
ISSUER = "KR:027040"
ISSUER_NAME = "서울전자통신"
CORP_CODE = "00130587"


def _catalog(*, include_nice=True):
    rows = [
        {"id": ISSUER, "name": ISSUER_NAME, "source_names": [ISSUER_NAME]},
        {"id": "KR:011070", "name": "LG이노텍", "source_names": ["LG이노텍"]},
        {"id": "KR:066570", "name": "LG전자", "source_names": ["LG전자"]},
    ]
    if include_nice:
        rows.append({"id": "KR:063570", "name": "NICE인프라", "source_names": ["NICE인프라"]})
    return rows


def _index(archive_bytes=None, *, catalog=None, **overrides):
    values = {
        "receipt_no": RECEIPT,
        "issuer_id": ISSUER,
        "issuer_name": ISSUER_NAME,
        "corp_code": CORP_CODE,
        "filed_on": "2026-03-20",
        "fiscal_year": "2025",
        "report_name": "사업보고서 (2025.12)",
        "company_catalog": _catalog() if catalog is None else catalog,
        "expected_member": MEMBER,
    }
    values.update(overrides)
    return index_annual_customer_tables(
        ARCHIVE.read_bytes() if archive_bytes is None else archive_bytes, **values
    )


def _zip(xml: str) -> bytes:
    output = BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(MEMBER, xml.encode("utf-8"))
    return output.getvalue()


def _synthetic_xml(*, table: str, period_from="20250101", period_to="20251231") -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<DOCUMENT><COMPANY-NAME AREGCIK="00130587">서울전자통신</COMPANY-NAME>
<DOCUMENT-NAME ACODE="11011">사업보고서</DOCUMENT-NAME>
<TU AUNIT="PERIODFROM" AUNITVALUE="{period_from}">기간 시작</TU>
<TU AUNIT="PERIODTO" AUNITVALUE="{period_to}">기간 종료</TU>{table}</DOCUMENT>"""


@pytest.mark.skipif(not ARCHIVE.is_file(), reason="saved case19 source ZIP is local-only")
def test_saved_case19_preserves_issuer_rowspan_and_only_binds_unambiguous_customers():
    result = _index()

    assert result["provenance"] == {
        "archive_sha256": "a41c0b931f9e719d109d523d3c3d9f31bec960f597098412aa3c83e60e6832aa",
        "xml_sha256": "b4ab891bb970f2e05a58b367a66168df5861ed9a0fd824d352014a5d6284b097",
        "archive_member": MEMBER,
    }
    assert sorted((row["participants"][1]["id"], row["evidence"]["row_index"])
                  for row in result["relations"]) == [("KR:011070", 1), ("KR:066570", 2)]
    assert sorted((row["participants"][1]["id"], row["evidence"]["customer_origin_row_index"])
                  for row in result["relations"]) == [("KR:011070", 1), ("KR:066570", 2)]
    assert all(row["participants"][0]["id"] == ISSUER for row in result["relations"])
    assert all(row["evidence"]["report_period_start"] == "2025-01-01"
               and row["evidence"]["report_period_end"] == "2025-12-31"
               for row in result["relations"])
    assert all(row["evidence"]["customer_origin_row_index"] == row["evidence"]["row_index"]
               for row in result["relations"])
    assert all(row["status"] == "accepted_reported"
               and row["label"] == "보고서상 고객사 후보"
               and row["snapshot_scope"] == "reported-fiscal-year-not-current"
               and row["evidence"]["fiscal_year"] == "2025"
               for row in result["relations"])
    assert all(row["evidence"]["owner_rowspan"] == 2
               and row["evidence"]["column_index"] == 4
               and row["evidence"]["table_index"] == 31
               and row["evidence"]["quote"] in {
                   "세라젬, 청호나이스, LG이노텍 등",
                   "LG전자, K-golf, NICE인프라 등",
               } for row in result["relations"])
    assert not {"current_status", "impact", "strength"} & set(result["relations"][0])
    assert {hold["raw_name"] for hold in result["holds"]} == {"세라젬", "청호나이스", "K-golf", "NICE인프라"}
    assert any(hold["raw_name"] == "NICE인프라"
               and hold["reason"] == "source-former-name-collision"
               for hold in result["holds"])
    assert result["coverage"] == {
        "input": 1,
        "customer_cells_examined": 2,
        "candidate_names": 6,
        "relationships": 2,
        "identity_holds": 4,
        "rejection_reasons": {"tables_seen": 537, "matching_tables": 1},
    }


@pytest.mark.skipif(not ARCHIVE.is_file(), reason="saved case19 source ZIP is local-only")
def test_saved_result_uses_existing_business_relationship_attachment_contract():
    index = _index()
    projection = {"relationships": [], "sources": [], "coverage": {}}

    attached = attach_business_relationships(
        projection, index, [{"market": "KR", "ticker": "027040"}]
    )

    assert sorted(row["participants"][1]["id"] for row in attached["relationships"]) == [
        "KR:011070", "KR:066570"
    ]
    assert attached["sources"][0]["id"] == "source:dart:" + RECEIPT
    assert attached["coverage"]["business_roles"] == index["coverage"]
    assert projection == {"relationships": [], "sources": [], "coverage": {}}


@pytest.mark.skipif(not ARCHIVE.is_file(), reason="saved case19 source ZIP is local-only")
def test_saved_source_cover_period_must_match_report_name_not_just_caller_metadata():
    result = _index(report_name="사업보고서 (2025.12)")

    assert result["relations"]
    with pytest.raises(ValueError, match="source-report-period-mismatch"):
        _index(report_name="사업보고서 (2025.03)")


@pytest.mark.parametrize(
    ("period_from", "period_to"),
    [("20250101", "20250331"), ("20260101", "20251231"), ("20251301", "20251231")],
)
def test_source_cover_period_must_be_valid_ordered_and_match_report_period(period_from, period_to):
    xml = _synthetic_xml(
        period_from=period_from,
        period_to=period_to,
        table="""<TABLE>
<TR><TH>회사</TH><TH>사업부문</TH><TH>주요 제품</TH><TH>주요고객</TH></TR>
<TR><TD>서울전자통신</TD><TD>전원</TD><TD>부품</TD><TD>LG이노텍</TD></TR>
</TABLE>""",
    )

    with pytest.raises(ValueError, match="source-report-period-mismatch"):
        _index(_zip(xml), catalog=_catalog(include_nice=False))


def test_empty_physical_row_keeps_issuer_rowspan_for_following_customer_cell():
    xml = _synthetic_xml(table="""<TABLE>
<TR><TH>회사</TH><TH>사업부문</TH><TH>주요 제품</TH><TH>주요고객</TH></TR>
<TR><TD rowspan="3">서울전자통신</TD><TD>전원</TD><TD>부품</TD><TD>LG이노텍</TD></TR>
<TR></TR>
<TR><TD>ODM</TD><TD>장비</TD><TD>LG전자</TD></TR>
</TABLE>""")
    catalog = _catalog(include_nice=False)

    result = _index(
        _zip(xml), catalog=catalog,
        receipt_no="20260320001349", filed_on="2026-03-20",
    )

    assert sorted((row["participants"][1]["id"], row["evidence"]["row_index"])
                  for row in result["relations"]) == [("KR:011070", 1), ("KR:066570", 3)]
    assert all(row["evidence"]["owner_rowspan"] == 3 for row in result["relations"])


@pytest.mark.parametrize(
    ("receipt_no", "filed_on", "fiscal_year", "report_name"),
    [
        ("20260230001349", "2026-02-30", "2025", "사업보고서 (2025.03)"),
        ("20260320001349", "2026-03-20", "2025", "사업보고서 (2024.03)"),
        ("20990320001349", "2099-03-20", "2098", "사업보고서 (2098.03)"),
    ],
)
def test_invalid_or_future_filing_dates_and_periods_are_rejected(
    receipt_no, filed_on, fiscal_year, report_name
):
    with pytest.raises(ValueError, match="annual-source-date-period-mismatch"):
        _index(_zip(_synthetic_xml(table="<TABLE><TR><TD>설명</TD></TR></TABLE>")),
               receipt_no=receipt_no, filed_on=filed_on,
               fiscal_year=fiscal_year, report_name=report_name)


def test_nested_table_is_not_reparsed_as_independent_customer_table():
    xml = _synthetic_xml(table="""<TABLE>
<TR><TH>회사</TH><TH>사업부문</TH><TH>주요 제품</TH><TH>주요고객</TH></TR>
<TR><TD>서울전자통신</TD><TD>전원</TD><TD>부품</TD><TD>상위값<TABLE>
<TR><TH>회사</TH><TH>사업부문</TH><TH>주요 제품</TH><TH>주요고객</TH></TR>
<TR><TD>서울전자통신</TD><TD>전원</TD><TD>부품</TD><TD>LG이노텍</TD></TR>
</TABLE></TD></TR></TABLE>""")

    result = _index(_zip(xml), catalog=_catalog(include_nice=False))

    assert result["relations"] == []
    assert result["coverage"]["relationships"] == 0
    assert result["coverage"]["rejection_reasons"].get("nested-table") == 1
    assert result["coverage"]["rejection_reasons"].get("matching_tables", 0) == 0


@pytest.mark.parametrize("span", ["0", "101", "2x", "2"])
def test_malformed_or_out_of_bounds_rowspan_fails_closed(span):
    xml = _synthetic_xml(table=f"""<TABLE>
<TR><TH>회사</TH><TH>사업부문</TH><TH>주요 제품</TH><TH>주요고객</TH></TR>
<TR><TD rowspan="{span}">서울전자통신</TD><TD>전원</TD><TD>부품</TD><TD>LG이노텍</TD></TR>
</TABLE>""")

    result = _index(_zip(xml), catalog=_catalog(include_nice=False))

    expected = "span-outside-table" if span == "2" else "invalid-span"
    assert result["relations"] == []
    assert result["coverage"]["rejection_reasons"].get(expected) == 1


def test_archive_member_must_match_receipt_when_no_expected_member_is_supplied():
    xml = _synthetic_xml(table="""<TABLE>
<TR><TH>회사</TH><TH>사업부문</TH><TH>주요 제품</TH><TH>주요고객</TH></TR>
<TR><TD>서울전자통신</TD><TD>전원</TD><TD>부품</TD><TD>LG이노텍</TD></TR>
</TABLE>""")
    archive_bytes = BytesIO()
    with zipfile.ZipFile(archive_bytes, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("other-receipt.xml", xml.encode("utf-8"))

    with pytest.raises(ValueError, match="archive-receipt-member-mismatch"):
        _index(archive_bytes.getvalue(), catalog=_catalog(include_nice=False), expected_member=None)


def test_overlapping_colspan_is_rejected_without_partial_relations():
    xml = _synthetic_xml(table="""<TABLE>
<TR><TH>회사</TH><TH>사업부문</TH><TH>주요 제품</TH><TH>주요고객</TH></TR>
<TR><TD>서울전자통신</TD><TD rowspan="2">전원</TD><TD>부품</TD><TD>LG이노텍</TD></TR>
<TR><TD colspan="2">잘못된 병합</TD><TD>LG전자</TD></TR>
</TABLE>""")

    result = _index(_zip(xml), catalog=_catalog(include_nice=False))

    assert result["relations"] == []
    assert result["coverage"]["rejection_reasons"].get("overlapping-spans") == 1


def test_compact_capture_replays_saved_case19_and_preserves_former_name_hold():
    if not ARCHIVE.is_file():
        pytest.skip("saved case19 source ZIP is local-only")
    capture = capture_annual_customer_tables(
        ARCHIVE.read_bytes(), receipt_no=RECEIPT, issuer_id=ISSUER,
        issuer_name=ISSUER_NAME, corp_code=CORP_CODE, filed_on="2026-03-20",
        fiscal_year="2025", report_name="사업보고서 (2025.12)", expected_member=MEMBER,
    )

    replay = index_annual_customer_table_captures([capture], company_catalog=_catalog())

    assert sorted((row["participants"][1]["id"], row["evidence"]["table_index"])
                  for row in replay["relations"]) == [("KR:011070", 31), ("KR:066570", 31)]
    assert replay["coverage"]["input"] == replay["coverage"]["captures_accepted"] == 1
    assert replay["sources"][0]["id"] == "source:dart:" + RECEIPT
    assert {row["raw_name"] for row in replay["holds"]} >= {"NICE인프라"}
    nice_hold = next(row for row in replay["holds"] if row.get("raw_name") == "NICE인프라")
    assert nice_hold["reason"] == "source-former-name-collision"
    assert all(row["status"] == "accepted_reported"
               and row["snapshot_scope"] == "reported-fiscal-year-not-current"
               and not {"current_status", "impact", "strength"} & set(row)
               for row in replay["relations"])


def test_compact_capture_replay_revision_is_stable_across_run_times(monkeypatch):
    xml = _synthetic_xml(table="""<TABLE>
<TR><TH>회사</TH><TH>사업부문</TH><TH>주요제품</TH><TH>주요고객</TH></TR>
<TR><TD>서울전자통신</TD><TD>전원</TD><TD>부품</TD><TD>LG이노텍</TD></TR>
</TABLE>""")
    capture = capture_annual_customer_tables(
        _zip(xml), receipt_no=RECEIPT, issuer_id=ISSUER, issuer_name=ISSUER_NAME,
        corp_code=CORP_CODE, filed_on="2026-03-20", fiscal_year="2025",
        report_name="사업보고서 (2025.12)", expected_member=MEMBER,
    )
    synthetic_archive_hashes = []
    original_index = annual_tables.index_annual_customer_tables

    def record_synthetic_archive(archive_bytes, **kwargs):
        synthetic_archive_hashes.append(sha256(archive_bytes).hexdigest())
        return original_index(archive_bytes, **kwargs)

    monkeypatch.setattr(annual_tables, "index_annual_customer_tables", record_synthetic_archive)
    simulated_now = [1_775_001_600]
    monkeypatch.setattr(zipfile.time, "time", lambda: simulated_now[0])
    first = index_annual_customer_table_captures(
        [capture], company_catalog=_catalog(include_nice=False)
    )
    simulated_now[0] = 1_788_220_800
    second = index_annual_customer_table_captures(
        [capture], company_catalog=_catalog(include_nice=False)
    )

    first_relation = first["relations"][0]
    second_relation = second["relations"][0]
    assert synthetic_archive_hashes[0] == synthetic_archive_hashes[1]
    assert first_relation["stable_id"] == second_relation["stable_id"]
    assert first_relation["revision"] == second_relation["revision"]
    assert first["sources"][0]["revision"] == second["sources"][0]["revision"]


def test_compact_capture_without_customer_table_is_valid_and_replays_zero_relations():
    xml = _synthetic_xml(table="<TABLE><TR><TD>일반 설명</TD></TR></TABLE>")
    capture = capture_annual_customer_tables(
        _zip(xml), receipt_no=RECEIPT, issuer_id=ISSUER, issuer_name=ISSUER_NAME,
        corp_code=CORP_CODE, filed_on="2026-03-20", fiscal_year="2025",
        report_name="사업보고서 (2025.12)", expected_member=MEMBER,
    )

    replay = index_annual_customer_table_captures(
        [capture], company_catalog=_catalog(include_nice=False)
    )

    assert capture["tables"] == []
    assert replay["relations"] == []
    assert replay["coverage"]["input"] == replay["coverage"]["captures_accepted"] == 1
    assert replay["coverage"]["rejection_reasons"] == {"tables_seen": 1}
    assert replay["sources"][0]["receipt_no"] == RECEIPT


def test_capture_header_uses_rebuilt_logical_column_after_colspan():
    xml = _synthetic_xml(table="""<TABLE>
<TR><TH>회사</TH><TH colspan="2">사업부문</TH><TH>주요제품</TH><TH>주요고객</TH></TR>
<TR><TD>서울전자통신</TD><TD colspan="2">전원</TD><TD>부품</TD><TD>LG이노텍</TD></TR>
</TABLE>""")
    capture = capture_annual_customer_tables(
        _zip(xml), receipt_no=RECEIPT, issuer_id=ISSUER, issuer_name=ISSUER_NAME,
        corp_code=CORP_CODE, filed_on="2026-03-20", fiscal_year="2025",
        report_name="사업보고서 (2025.12)", expected_member=MEMBER,
    )

    assert capture["tables"][0]["header"] == {
        "row_index": 0, "company_column": 0, "customer_column": 4,
    }
    replay = index_annual_customer_table_captures(
        [capture], company_catalog=_catalog(include_nice=False)
    )
    assert [row["participants"][1]["id"] for row in replay["relations"]] == ["KR:011070"]


def test_capture_rejects_private_content_in_public_table_cells():
    xml = _synthetic_xml(table="""<TABLE>
<TR><TH>회사</TH><TH>사업부문</TH><TH>주요제품</TH><TH>주요고객</TH></TR>
<TR><TD>서울전자통신</TD><TD>전원</TD><TD>부품</TD><TD>contact person@example.com</TD></TR>
</TABLE>""")

    with pytest.raises(ValueError, match="annual-customer-capture-table-rejected"):
        capture_annual_customer_tables(
            _zip(xml), receipt_no=RECEIPT, issuer_id=ISSUER, issuer_name=ISSUER_NAME,
            corp_code=CORP_CODE, filed_on="2026-03-20", fiscal_year="2025",
            report_name="사업보고서 (2025.12)", expected_member=MEMBER,
        )
