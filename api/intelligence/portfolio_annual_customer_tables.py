"""Source-bound annual-report customer cells with merged-row ownership.

This parser emits reported historical candidates only. It does not infer
current relationships, contract status, impact, or relationship strength.
"""
from __future__ import annotations

from collections import Counter
from calendar import monthrange
from copy import deepcopy
from datetime import date
from hashlib import sha256
from io import BytesIO
import html
import json
import re
import unicodedata
import zipfile

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
import warnings

from .portfolio_business_roles import _GENERIC_NAME, _SEPARATOR, _names, _revision
from .portfolio_filing_excerpts import _legal_name
from .portfolio_public_sources import safe_public_text


MAX_ARCHIVE_BYTES = 4 * 1024 * 1024
MAX_MEMBER_BYTES = 5 * 1024 * 1024
MAX_ZIP_MEMBERS = 100
MAX_TABLES = 1200
MAX_ROWS = 500
MAX_COLUMNS = 40
MAX_SPAN = 100
MAX_CAPTURE_ROWS = 1000
MAX_CAPTURE_TABLE_BYTES = 512 * 1024
MAX_CAPTURE_ROW_BYTES = 2 * 1024 * 1024
MAX_FORMER_NAME_MARKERS = 500
MAX_FORMER_NAME_TEXT = 10_000
_ID = re.compile(r"KR:[0-9]{6}\Z", re.ASCII)
_RECEIPT = re.compile(r"[0-9]{14}\Z", re.ASCII)
_DAY = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\Z", re.ASCII)
_SHA = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_CUSTOMER_HEADER = "주요고객"
_COMPANY_HEADER = "회사"


def _key(value: str) -> str:
    return "".join(unicodedata.normalize("NFKC", value).split())


def _cell_text(cell) -> str:
    return " ".join(cell.get_text(" ", strip=True).split())


def _span(cell, attribute: str) -> int:
    raw = cell.get(attribute, "1")
    if not isinstance(raw, str) or not re.fullmatch(r"[0-9]{1,3}", raw, re.ASCII):
        raise ValueError("invalid-span")
    value = int(raw)
    if not 1 <= value <= MAX_SPAN:
        raise ValueError("invalid-span")
    return value


def _logical_grid(table):
    rows = [row for row in table.find_all("tr") if row.find_parent("table") is table]
    if not rows or len(rows) > MAX_ROWS:
        raise ValueError("invalid-row-count")
    occupied = {}
    grid = []
    width = 0
    for row_index, row in enumerate(rows):
        cells = row.find_all(["td", "th"], recursive=False)
        for cell in cells:
            if cell.find("table") is not None:
                raise ValueError("nested-table")
            rowspan = _span(cell, "rowspan")
            colspan = _span(cell, "colspan")
            if row_index + rowspan > len(rows):
                raise ValueError("span-outside-table")
            column = 0
            while (row_index, column) in occupied:
                column += 1
            if column + colspan > MAX_COLUMNS:
                raise ValueError("too-many-columns")
            descriptor = {"text": _cell_text(cell), "origin_row": row_index,
                          "origin_column": column, "rowspan": rowspan, "colspan": colspan}
            for target_row in range(row_index, row_index + rowspan):
                for target_column in range(column, column + colspan):
                    coordinate = (target_row, target_column)
                    if coordinate in occupied:
                        raise ValueError("overlapping-spans")
                    occupied[coordinate] = descriptor
            width = max(width, column + colspan)
        current = {column: occupied[(row_index, column)] for column in range(width)
                   if (row_index, column) in occupied}
        if current and sorted(current) != list(range(max(current) + 1)):
            raise ValueError("gap-in-row")
        grid.append(current)
    return rows, grid


def _header(grid):
    matches = []
    for row_index, row in enumerate(grid):
        values = {column: _key(cell["text"]) for column, cell in row.items()}
        company = [column for column, value in values.items() if value == _COMPANY_HEADER]
        customer = [column for column, value in values.items() if value == _CUSTOMER_HEADER]
        division = any(value in {"사업부문", "사업의종류"} for value in values.values())
        product = any("주요제품" in value for value in values.values())
        if len(company) == len(customer) == 1 and division and product:
            matches.append((row_index, company[0], customer[0]))
    if len(matches) != 1:
        raise ValueError("ambiguous-or-missing-header")
    return matches[0]


def _archive_member(archive_bytes: bytes, expected_member: str | None) -> tuple[bytes, str]:
    if not isinstance(archive_bytes, bytes) or not 0 < len(archive_bytes) <= MAX_ARCHIVE_BYTES:
        raise ValueError("archive-size-rejected")
    try:
        with zipfile.ZipFile(BytesIO(archive_bytes)) as archive:
            infos = archive.infolist()
            if not 1 <= len(infos) <= MAX_ZIP_MEMBERS:
                raise ValueError("archive-member-count-rejected")
            total = sum(info.file_size for info in infos)
            if total > MAX_MEMBER_BYTES or any(info.flag_bits & 1 for info in infos):
                raise ValueError("archive-content-rejected")
            xml_infos = [info for info in infos if info.filename.lower().endswith((".xml", ".html", ".htm"))]
            if expected_member is not None:
                xml_infos = [info for info in xml_infos if info.filename == expected_member]
            if len(xml_infos) != 1 or xml_infos[0].file_size > MAX_MEMBER_BYTES:
                raise ValueError("archive-source-member-ambiguous")
            info = xml_infos[0]
            body = archive.read(info)
            if len(body) != info.file_size:
                raise ValueError("archive-member-size-mismatch")
            return body, info.filename
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        raise ValueError("archive-rejected") from exc


def _metadata(*, receipt_no, issuer_id, issuer_name, corp_code, filed_on,
              fiscal_year, report_name):
    if (not isinstance(receipt_no, str) or not _RECEIPT.fullmatch(receipt_no)
            or not isinstance(issuer_id, str) or not _ID.fullmatch(issuer_id)
            or not isinstance(corp_code, str) or not re.fullmatch(r"[0-9]{8}", corp_code, re.ASCII)
            or not isinstance(filed_on, str) or not _DAY.fullmatch(filed_on)
            or receipt_no[:8] != filed_on.replace("-", "")
            or not isinstance(fiscal_year, str) or not re.fullmatch(r"[0-9]{4}", fiscal_year, re.ASCII)
            or not isinstance(issuer_name, str) or safe_public_text(issuer_name, 160) is None
            or not isinstance(report_name, str) or safe_public_text(report_name, 240) is None
            or re.fullmatch(r"(?:\[(?:기재정정|첨부정정|첨부추가)\])*사업보고서 \([0-9]{4}\.(?:0[1-9]|1[0-2])\)", report_name) is None):
        raise ValueError("annual-source-metadata-rejected")
    try:
        filed = date.fromisoformat(filed_on)
        report_match = re.fullmatch(
            r"(?:\[(?:기재정정|첨부정정|첨부추가)\])*사업보고서 \(([0-9]{4})\.([0-9]{2})\)",
            report_name,
        )
        period_year, period_month = int(report_match[1]), int(report_match[2])
        period_end = date(period_year, period_month, monthrange(period_year, period_month)[1])
        if (filed > date.today() or period_year != int(fiscal_year)
                or filed < period_end):
            raise ValueError("annual-source-date-period-mismatch")
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("annual-source-date-period-mismatch") from exc


def _source_identity(soup, issuer_id: str, issuer_name: str, corp_code: str,
                     fiscal_year: str, report_name: str):
    companies = soup.find_all("company-name")
    if len(companies) != 1:
        raise ValueError("source-issuer-header-ambiguous")
    tag = companies[0]
    if (tag.get("areg cik") or tag.get("areg cik".replace(" ", "")) or tag.get("AREGCIK")) != corp_code:
        # BeautifulSoup lowercases attribute names in HTML mode.
        if tag.get("areg cik".replace(" ", "")) != corp_code:
            raise ValueError("source-corp-code-mismatch")
    if _legal_name(_cell_text(tag)).casefold() != _legal_name(issuer_name).casefold():
        raise ValueError("source-issuer-name-mismatch")
    document_names = soup.find_all("document-name")
    if (len(document_names) != 1 or "사업보고서" not in _cell_text(document_names[0])
            or document_names[0].get("acode") != "11011"):
        raise ValueError("source-report-header-mismatch")
    period_tags = [tag for tag in soup.find_all("tu")
                   if isinstance(tag.get("aunit"), str)]
    period_from = [tag for tag in period_tags if tag["aunit"].casefold() == "periodfrom"]
    period_to = [tag for tag in period_tags if tag["aunit"].casefold() == "periodto"]
    if len(period_from) != 1 or len(period_to) != 1:
        raise ValueError("source-report-period-unavailable")
    try:
        start_raw, end_raw = period_from[0].get("aunitvalue"), period_to[0].get("aunitvalue")
        if (not isinstance(start_raw, str) or not re.fullmatch(r"[0-9]{8}", start_raw, re.ASCII)
                or not isinstance(end_raw, str) or not re.fullmatch(r"[0-9]{8}", end_raw, re.ASCII)):
            raise ValueError("invalid-source-period")
        period_start = date.fromisoformat(f"{start_raw[:4]}-{start_raw[4:6]}-{start_raw[6:8]}")
        period_end = date.fromisoformat(f"{end_raw[:4]}-{end_raw[4:6]}-{end_raw[6:8]}")
        report_match = re.fullmatch(
            r"(?:\[(?:기재정정|첨부정정|첨부추가)\])*사업보고서 \(([0-9]{4})\.([0-9]{2})\)",
            report_name,
        )
        if (period_start > period_end or report_match is None
                or (period_end.year, period_end.month) != (int(report_match[1]), int(report_match[2]))
                or period_end.year != int(fiscal_year)):
            raise ValueError("source-report-period-mismatch")
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("source-report-period-mismatch") from exc
    return period_start.isoformat(), period_end.isoformat()


def _source_marker_matches(value: str, raw_name: str) -> bool:
    normalized = _key(value)
    marker = max(normalized.find("구,"), normalized.find("구，"))
    return marker >= 0 and _key(raw_name) in normalized[marker + 2:]


def _table_candidate_names(table) -> set[str]:
    """Names whose former-name markers must survive compact capture."""
    try:
        _, grid = _logical_grid(table)
        header_row, _, customer_column = _header(grid)
    except ValueError:
        return set()
    names = set()
    for row in grid[header_row + 1:]:
        customer = row.get(customer_column)
        if customer is None:
            continue
        raw_list = re.sub(r"\s*등\s*$", "", customer["text"].strip())
        names.update(part.strip() for part in _SEPARATOR.split(raw_list) if part.strip())
    return names


def _logical_grid_from_capture(rows: list[dict]) -> list[dict[int, dict]]:
    """Rebuild occupied logical coordinates from compact physical cells."""
    if not rows or len(rows) > MAX_ROWS:
        raise ValueError("invalid-row-count")
    occupied, grid, width = {}, [], 0
    for row_index, row in enumerate(rows):
        for cell in row["cells"]:
            if cell["nested_table"]:
                raise ValueError("nested-table")
            rowspan, colspan = cell["rowspan"], cell["colspan"]
            if row_index + rowspan > len(rows):
                raise ValueError("span-outside-table")
            column = 0
            while (row_index, column) in occupied:
                column += 1
            if column + colspan > MAX_COLUMNS:
                raise ValueError("too-many-columns")
            descriptor = {"text": cell["text"], "origin_row": row_index,
                          "origin_column": column, "rowspan": rowspan, "colspan": colspan}
            for target_row in range(row_index, row_index + rowspan):
                for target_column in range(column, column + colspan):
                    coordinate = (target_row, target_column)
                    if coordinate in occupied:
                        raise ValueError("overlapping-spans")
                    occupied[coordinate] = descriptor
            width = max(width, column + colspan)
        current = {column: occupied[(row_index, column)] for column in range(width)
                   if (row_index, column) in occupied}
        if current and sorted(current) != list(range(max(current) + 1)):
            raise ValueError("gap-in-row")
        grid.append(current)
    return grid


def validate_annual_customer_capture(row: dict) -> dict:
    """Validate and copy one compact source row; no mapped relation is trusted."""
    expected = {
        "schema", "receipt_no", "issuer_id", "issuer_name", "corp_code", "filed_on",
        "fiscal_year", "report_name", "report_period_start", "report_period_end",
        "archive_member", "archive_sha256", "xml_sha256", "table_count", "tables",
        "former_name_markers", "former_name_scan_complete",
    }
    if type(row) is not dict or set(row) != expected or row.get("schema") != "annual-customer-table-source-v1":
        raise ValueError("annual-customer-capture-schema-rejected")
    _metadata(receipt_no=row["receipt_no"], issuer_id=row["issuer_id"], issuer_name=row["issuer_name"],
              corp_code=row["corp_code"], filed_on=row["filed_on"], fiscal_year=row["fiscal_year"],
              report_name=row["report_name"])
    member = row["archive_member"]
    if (not isinstance(member, str)
            or member.replace("\\", "/").split("/")[-1] != row["receipt_no"] + ".xml"
            or any(part in {"", ".", ".."} for part in member.replace("\\", "/").split("/"))
            or not isinstance(row["archive_sha256"], str) or not _SHA.fullmatch(row["archive_sha256"])
            or not isinstance(row["xml_sha256"], str) or not _SHA.fullmatch(row["xml_sha256"])):
        raise ValueError("annual-customer-capture-provenance-rejected")
    try:
        start = date.fromisoformat(row["report_period_start"])
        end = date.fromisoformat(row["report_period_end"])
    except (TypeError, ValueError) as exc:
        raise ValueError("annual-customer-capture-period-rejected") from exc
    report_match = re.fullmatch(
        r"(?:\[(?:기재정정|첨부정정|첨부추가)\])*사업보고서 \(([0-9]{4})\.([0-9]{2})\)",
        row["report_name"],
    )
    if (not isinstance(row["report_period_start"], str) or not _DAY.fullmatch(row["report_period_start"])
            or not isinstance(row["report_period_end"], str) or not _DAY.fullmatch(row["report_period_end"])
            or start > end or report_match is None
            or (end.year, end.month) != (int(report_match[1]), int(report_match[2]))
            or end.year != int(row["fiscal_year"])):
        raise ValueError("annual-customer-capture-period-rejected")
    tables, markers = row["tables"], row["former_name_markers"]
    if (type(row["table_count"]) is not int or not 1 <= row["table_count"] <= MAX_TABLES
            or type(tables) is not list or len(tables) > row["table_count"]
            or row["former_name_scan_complete"] is not True
            or type(markers) is not list or len(markers) > MAX_FORMER_NAME_MARKERS):
        raise ValueError("annual-customer-capture-bounds-rejected")
    previous_index = -1
    for table in tables:
        if (type(table) is not dict or set(table) != {"table_index", "rows", "header", "sha256"}
                or type(table["table_index"]) is not int
                or not previous_index < table["table_index"] < row["table_count"]
                or type(table["rows"]) is not list or not 1 <= len(table["rows"]) <= MAX_ROWS
                or type(table["header"]) is not dict
                or set(table["header"]) != {"row_index", "company_column", "customer_column"}
                or any(type(table["header"][key]) is not int or table["header"][key] < 0
                       for key in table["header"])
                or table["header"]["row_index"] >= len(table["rows"])
                or table["header"]["company_column"] >= MAX_COLUMNS
                or table["header"]["customer_column"] >= MAX_COLUMNS
                or not isinstance(table["sha256"], str) or not _SHA.fullmatch(table["sha256"])):
            raise ValueError("annual-customer-capture-table-rejected")
        previous_index = table["table_index"]
        cells_payload = []
        for table_row in table["rows"]:
            if type(table_row) is not dict or set(table_row) != {"cells"} or type(table_row["cells"]) is not list:
                raise ValueError("annual-customer-capture-table-rejected")
            cells = []
            if len(table_row["cells"]) > MAX_COLUMNS:
                raise ValueError("annual-customer-capture-table-rejected")
            for cell in table_row["cells"]:
                if (type(cell) is not dict or set(cell) != {"tag", "text", "rowspan", "colspan", "nested_table"}
                        or cell["tag"] not in {"td", "th"}
                        or not isinstance(cell["text"], str) or len(cell["text"]) > 10_000
                        or (cell["text"] and safe_public_text(cell["text"], 10_000) is None)
                        or type(cell["rowspan"]) is not int or not 1 <= cell["rowspan"] <= MAX_SPAN
                        or type(cell["colspan"]) is not int or not 1 <= cell["colspan"] <= MAX_SPAN
                        or type(cell["nested_table"]) is not bool):
                    raise ValueError("annual-customer-capture-table-rejected")
                cells.append(cell)
            cells_payload.append(cells)
        canonical = json.dumps(cells_payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(canonical) > MAX_CAPTURE_TABLE_BYTES or sha256(canonical).hexdigest() != table["sha256"]:
            raise ValueError("annual-customer-capture-table-rejected")
        try:
            grid = _logical_grid_from_capture(table["rows"])
            actual_header = _header(grid)
        except ValueError as exc:
            raise ValueError("annual-customer-capture-header-rejected") from exc
        if table["header"] != {"row_index": actual_header[0],
                               "company_column": actual_header[1],
                               "customer_column": actual_header[2]}:
            raise ValueError("annual-customer-capture-header-rejected")
    for marker in markers:
        if type(marker) is not dict or set(marker) != {"raw_name", "quote"}:
            raise ValueError("annual-customer-capture-marker-rejected")
        if (safe_public_text(marker["raw_name"], 160) is None
                or safe_public_text(marker["quote"], MAX_FORMER_NAME_TEXT) is None
                or not _source_marker_matches(marker["quote"], marker["raw_name"])):
            raise ValueError("annual-customer-capture-marker-rejected")
    size = len(json.dumps(row, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    if size > MAX_CAPTURE_ROW_BYTES:
        raise ValueError("annual-customer-capture-bounds-rejected")
    return deepcopy(row)


def capture_annual_customer_tables(archive_bytes: bytes, receipt_no: str, issuer_id: str,
                                   issuer_name: str, corp_code: str, filed_on: str,
                                   fiscal_year: str, report_name: str,
                                   expected_member: str | None = None) -> dict:
    """Capture compact physical-cell rows and source-wide former-name fragments."""
    _metadata(receipt_no=receipt_no, issuer_id=issuer_id, issuer_name=issuer_name,
              corp_code=corp_code, filed_on=filed_on, fiscal_year=fiscal_year,
              report_name=report_name)
    xml_bytes, member_name = _archive_member(archive_bytes, expected_member)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", XMLParsedAsHTMLWarning)
        soup = BeautifulSoup(xml_bytes, "html.parser")
    period_start, period_end = _source_identity(
        soup, issuer_id, issuer_name, corp_code, fiscal_year, report_name
    )
    if member_name.replace("\\", "/").split("/")[-1] != receipt_no + ".xml":
        raise ValueError("archive-receipt-member-mismatch")
    source_tables = soup.find_all("table")
    if not 1 <= len(source_tables) <= MAX_TABLES:
        raise ValueError("source-table-count-rejected")
    compact_tables, candidates = [], set()
    for table_index, table in enumerate(source_tables):
        if table.find_parent("table") is not None:
            continue
        if _COMPANY_HEADER not in _key(_cell_text(table)) or _CUSTOMER_HEADER not in _key(_cell_text(table)):
            continue
        table_rows, grid = _logical_grid(table)
        header_row, company_column, customer_column = _header(grid)
        physical_rows = []
        for physical_row in table_rows:
            cells = []
            for cell in physical_row.find_all(["td", "th"], recursive=False):
                cells.append({"tag": cell.name, "text": _cell_text(cell),
                              "rowspan": _span(cell, "rowspan"),
                              "colspan": _span(cell, "colspan"),
                              "nested_table": cell.find("table") is not None})
            physical_rows.append({"cells": cells})
        cells_payload = [row["cells"] for row in physical_rows]
        canonical = json.dumps(cells_payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        compact_tables.append({
            "table_index": table_index, "rows": physical_rows,
            "header": {"row_index": header_row, "company_column": company_column,
                       "customer_column": customer_column},
            "sha256": sha256(canonical).hexdigest(),
        })
        candidates.update(_table_candidate_names(table))
    markers = []
    for node in soup.find_all(string=True):
        value = str(node)
        normalized = _key(value)
        cue = max(normalized.find("구,"), normalized.find("구，"))
        if cue < 0:
            continue
        for name in sorted(candidates):
            if _key(name) in normalized[cue + 2:]:
                markers.append({"raw_name": name, "quote": value})
    markers = list({(row["raw_name"], row["quote"]): row for row in markers}.values())
    markers.sort(key=lambda row: (row["raw_name"], row["quote"]))
    return validate_annual_customer_capture({
        "schema": "annual-customer-table-source-v1", "receipt_no": receipt_no,
        "issuer_id": issuer_id, "issuer_name": issuer_name, "corp_code": corp_code,
        "filed_on": filed_on, "fiscal_year": fiscal_year, "report_name": report_name,
        "report_period_start": period_start, "report_period_end": period_end,
        "archive_member": member_name, "archive_sha256": sha256(archive_bytes).hexdigest(),
        "xml_sha256": sha256(xml_bytes).hexdigest(), "table_count": len(source_tables),
        "tables": compact_tables, "former_name_markers": markers,
        "former_name_scan_complete": True,
    })


def _capture_xml(row: dict) -> bytes:
    """Rebuild a parser-only envelope from validated cells.

    The full archive/XML SHA-256 values remain capture provenance declarations;
    they cannot be recomputed from this compact fragment and are not source authentication.
    """
    tables = []
    for table in row["tables"]:
        rows = []
        for physical_row in table["rows"]:
            cells = []
            for cell in physical_row["cells"]:
                tag = cell["tag"]
                attrs = f' rowspan="{cell["rowspan"]}" colspan="{cell["colspan"]}"'
                nested = "<table></table>" if cell["nested_table"] else ""
                cells.append(f"<{tag}{attrs}>{html.escape(cell['text'])}{nested}</{tag}>")
            rows.append("<tr>" + "".join(cells) + "</tr>")
        tables.append(f"<table data-captured-index=\"{table['table_index']}\">" + "".join(rows) + "</table>")
    markers = "".join(f"<former-name-marker>{html.escape(item['quote'])}</former-name-marker>"
                       for item in row["former_name_markers"])
    xml = (
        '<DOCUMENT><COMPANY-NAME AREGCIK="' + row["corp_code"] + '">' + html.escape(row["issuer_name"]) +
        '</COMPANY-NAME><DOCUMENT-NAME ACODE="11011">사업보고서</DOCUMENT-NAME>' +
        '<TU AUNIT="PERIODFROM" AUNITVALUE="' + row["report_period_start"].replace("-", "") + '"></TU>' +
        '<TU AUNIT="PERIODTO" AUNITVALUE="' + row["report_period_end"].replace("-", "") + '"></TU>' +
        markers + "".join(tables) + "</DOCUMENT>"
    )
    return xml.encode("utf-8")


def index_annual_customer_table_captures(captures: list[dict], *, company_catalog: list[dict]) -> dict:
    """Replay compact source rows through the same table ownership parser."""
    if type(captures) is not list or len(captures) > MAX_CAPTURE_ROWS:
        raise ValueError("annual-customer-capture-list-rejected")
    catalog_by_id, _ = _names(company_catalog)
    relations, holds = {}, []
    by_company = {}
    totals = Counter()
    reasons = Counter()
    source_rows = []
    seen_receipts = set()
    for raw_capture in captures:
        row = validate_annual_customer_capture(raw_capture)
        catalog_issuer = catalog_by_id.get(row["issuer_id"])
        if (catalog_issuer is None
                or _legal_name(catalog_issuer["name"]).casefold()
                != _legal_name(row["issuer_name"]).casefold()):
            raise ValueError("catalog-issuer-binding-rejected")
        if row["receipt_no"] in seen_receipts:
            raise ValueError("annual-customer-capture-duplicate-receipt")
        seen_receipts.add(row["receipt_no"])
        source = {"id": "source:dart:" + row["receipt_no"],
                  "kind": "dart-annual-report-table", "receipt_no": row["receipt_no"],
                  "as_of": row["filed_on"], "report_name": row["report_name"],
                  "document_issuer": row["issuer_id"],
                  "url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=" + row["receipt_no"],
                  "artifact_observed_at": None}
        source["revision"] = _revision(source)
        source_rows.append(source)
        if not row["tables"]:
            reasons["tables_seen"] += row["table_count"]
            continue
        synthetic = BytesIO()
        with zipfile.ZipFile(synthetic, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            member = zipfile.ZipInfo(row["receipt_no"] + ".xml", date_time=(1980, 1, 1, 0, 0, 0))
            member.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(member, _capture_xml(row))
        indexed = index_annual_customer_tables(
            synthetic.getvalue(), receipt_no=row["receipt_no"], issuer_id=row["issuer_id"],
            issuer_name=row["issuer_name"], corp_code=row["corp_code"], filed_on=row["filed_on"],
            fiscal_year=row["fiscal_year"], report_name=row["report_name"],
            company_catalog=company_catalog, expected_member=row["receipt_no"] + ".xml",
        )
        compact_table_indexes = [table["table_index"] for table in row["tables"]]
        for relation in indexed["relations"]:
            evidence = relation["evidence"]
            synthetic_index = evidence["table_index"]
            if not 0 <= synthetic_index < len(compact_table_indexes):
                raise ValueError("annual-customer-capture-table-index-mismatch")
            evidence["table_index"] = compact_table_indexes[synthetic_index]
            evidence["archive_member"] = row["archive_member"]
            evidence["archive_sha256"] = row["archive_sha256"]
            evidence["xml_sha256"] = row["xml_sha256"]
            evidence["field_sha256"] = row["xml_sha256"]
            relation.pop("revision", None)
            relation["revision"] = _revision(relation)
            relations.setdefault(relation["stable_id"], relation)
        holds.extend(indexed["holds"])
        for key in ("customer_cells_examined", "candidate_names", "identity_holds", "relationships"):
            totals[key] += indexed["coverage"][key]
        reasons.update({key: value for key, value in indexed["coverage"]["rejection_reasons"].items()
                        if key not in {"tables_seen", "matching_tables"}})
        reasons["tables_seen"] += row["table_count"]
        reasons["matching_tables"] += indexed["coverage"]["rejection_reasons"].get("matching_tables", 0)
    relation_rows = sorted(relations.values(), key=lambda relation: relation["stable_id"])
    for relation in relation_rows:
        for participant in relation["participants"]:
            by_company.setdefault(participant["id"], []).append(relation["stable_id"])
    totals["relationships"] = len(relation_rows)
    return {
        "relations": relation_rows,
        "by_company": by_company,
        "sources": source_rows,
        "coverage": {"input": len(captures), "captures_accepted": len(captures),
                     "customer_cells_examined": totals["customer_cells_examined"],
                     "candidate_names": totals["candidate_names"],
                     "relationships": len(relation_rows), "identity_holds": len(holds),
                     "rejection_reasons": dict(reasons)},
        "holds": holds,
    }


def attach_annual_customer_table_relationships(projection: dict | None, index: dict,
                                               positions: list[dict]) -> dict | None:
    """Attach replayed annual candidates with coverage kept distinct by source."""
    if projection is None or not index["coverage"]["input"]:
        return projection
    selected = {f"{row['market']}:{row['ticker']}" for row in positions}
    relation_ids = {stable_id for identifier in selected
                    for stable_id in index["by_company"].get(identifier, [])}
    result = deepcopy(projection)
    existing = {row["stable_id"] for row in result["relationships"]}
    sources = list(result["sources"])
    source_ids = {row.get("id") for row in sources}
    for relation in index["relations"]:
        if relation["stable_id"] in relation_ids and relation["stable_id"] not in existing:
            result["relationships"].append(deepcopy(relation))
            existing.add(relation["stable_id"])
            source = relation["source"]
            if source["id"] not in source_ids:
                sources.append(deepcopy(source))
                source_ids.add(source["id"])
    result["sources"] = sources
    result["coverage"]["annual_customer_tables"] = deepcopy(index["coverage"])
    return result


def _relation(*, issuer_id, issuer_name, target_id, target_name, raw_name,
              customer_quote, owner_quote, source, evidence, fiscal_year,
              report_period_start, report_period_end):
    stable_id = "relation:annual-customer:" + _revision([source["receipt_no"], issuer_id, target_id])[:16]
    relation = {
        "stable_id": stable_id,
        "type": "reported-business-counterparty",
        "status": "accepted_reported",
        "verification": "reported-annual-table",
        "snapshot_scope": "reported-fiscal-year-not-current",
        "label": "보고서상 고객사 후보",
        "participants": [
            {"id": issuer_id, "role": "document_issuer", "name": issuer_name},
            {"id": target_id, "role": "reported_customer", "name": target_name},
        ],
        "source": deepcopy(source),
        "evidence": {"role": "customer", "raw_name": raw_name,
                     "quote": customer_quote, "owner_quote": owner_quote,
                     "source_field": "annual_customer_table",
                     "field_sha256": evidence["xml_sha256"],
                     "fiscal_year": fiscal_year,
                     "report_period_start": report_period_start,
                     "report_period_end": report_period_end,
                     "table_index": evidence["table_index"],
                     "header_row": evidence["header_row"],
                     "row_index": evidence["row_index"],
                     "column_index": evidence["column_index"],
                     "owner_row_index": evidence["owner_row_index"],
                     "owner_rowspan": evidence["owner_rowspan"],
                     "customer_origin_row_index": evidence["customer_origin_row_index"],
                     "customer_rowspan": evidence["customer_rowspan"],
                     "archive_member": evidence["archive_member"],
                     "archive_sha256": evidence["archive_sha256"],
                     "xml_sha256": evidence["xml_sha256"]},
    }
    relation["revision"] = _revision(relation)
    return relation


def _source_marks_former_name(soup, raw_name: str) -> bool:
    """Hold exact catalog matches explicitly used as a former name in-source."""
    target = _key(raw_name)
    for node in soup.find_all(string=True):
        value = _key(str(node))
        marker = max(value.find("구,"), value.find("구，"))
        if marker >= 0 and target in value[marker + 2:]:
            return True
    return False


def index_annual_customer_tables(archive_bytes: bytes, *, receipt_no: str,
                                 issuer_id: str, issuer_name: str, corp_code: str,
                                 filed_on: str, fiscal_year: str, report_name: str,
                                 company_catalog: list[dict], expected_member: str | None = None) -> dict:
    """Parse one saved annual filing ZIP to an existing business-role index shape.

    Unsupported or ambiguous tables fail closed with a coverage reason. The
    caller supplies source-bound filing metadata and the existing exact-name catalog.
    """
    _metadata(receipt_no=receipt_no, issuer_id=issuer_id, issuer_name=issuer_name,
              corp_code=corp_code, filed_on=filed_on, fiscal_year=fiscal_year,
              report_name=report_name)
    by_id, aliases = _names(company_catalog)
    if issuer_id not in by_id or _legal_name(by_id[issuer_id]["name"]).casefold() != _legal_name(issuer_name).casefold():
        raise ValueError("catalog-issuer-binding-rejected")
    xml_bytes, member_name = _archive_member(archive_bytes, expected_member)
    xml_hash, archive_hash = sha256(xml_bytes).hexdigest(), sha256(archive_bytes).hexdigest()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", XMLParsedAsHTMLWarning)
        soup = BeautifulSoup(xml_bytes, "html.parser")
    report_period_start, report_period_end = _source_identity(
        soup, issuer_id, issuer_name, corp_code, fiscal_year, report_name
    )
    if member_name.rsplit("/", 1)[-1] != receipt_no + ".xml":
        raise ValueError("archive-receipt-member-mismatch")
    tables = soup.find_all("table")
    if not 1 <= len(tables) <= MAX_TABLES:
        raise ValueError("source-table-count-rejected")

    source_id = "source:dart:" + receipt_no
    source = {"id": source_id, "kind": "dart-annual-report-table",
              "receipt_no": receipt_no, "as_of": filed_on,
              "report_name": report_name, "document_issuer": issuer_id,
              "url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=" + receipt_no,
              "artifact_observed_at": None}
    source["revision"] = _revision(source)

    candidates, holds, reasons = {}, [], Counter()
    customer_cells_examined = candidate_names = 0
    table_matches = 0
    for table_index, table in enumerate(tables):
        if table.find_parent("table") is not None:
            continue
        table_text = _key(_cell_text(table))
        if _COMPANY_HEADER not in table_text or _CUSTOMER_HEADER not in table_text:
            continue
        try:
            table_rows, grid = _logical_grid(table)
            header_row, company_column, customer_column = _header(grid)
        except ValueError as exc:
            reasons[str(exc)] += 1
            continue
        table_matches += 1
        for row_index in range(header_row + 1, len(grid)):
            row = grid[row_index]
            owner = row.get(company_column)
            customer = row.get(customer_column)
            if owner is None or customer is None or not customer["text"]:
                continue
            owner_targets = aliases.get(_legal_name(owner["text"]).casefold(), set())
            if owner_targets != {issuer_id}:
                continue
            # The full merged customer cell must remain inside rows owned by
            # this same issuer; a span crossing into a subsidiary is held.
            customer_rows = range(customer["origin_row"], customer["origin_row"] + customer["rowspan"])
            if any((grid[r].get(company_column) is None
                    or aliases.get(_legal_name(grid[r][company_column]["text"]).casefold(), set()) != {issuer_id})
                   for r in customer_rows):
                reasons["customer-span-crosses-entity-boundary"] += 1
                continue
            customer_cells_examined += 1
            raw_list = customer["text"].strip()
            raw_list = re.sub(r"\s*등\s*$", "", raw_list)
            names = [part.strip() for part in _SEPARATOR.split(raw_list) if part.strip()]
            candidate_names += len(names)
            if not names or len(names) > 20 or any(_GENERIC_NAME.fullmatch(_legal_name(name)) for name in names):
                holds.append({"row_index": row_index, "reason": "customer-list-unresolved", "quote": customer["text"]})
                continue
            for raw_name in names:
                if _source_marks_former_name(soup, raw_name):
                    holds.append({"row_index": row_index, "raw_name": raw_name,
                                  "reason": "source-former-name-collision", "quote": customer["text"]})
                    continue
                targets = aliases.get(_legal_name(raw_name).casefold(), set())
                if len(targets) != 1 or issuer_id in targets:
                    holds.append({"row_index": row_index, "raw_name": raw_name,
                                  "reason": "identity-ambiguous-or-unmapped", "quote": customer["text"]})
                    continue
                target_id = next(iter(targets))
                target_name = by_id[target_id]["name"]
                relation = _relation(
                    issuer_id=issuer_id, issuer_name=by_id[issuer_id]["name"],
                    target_id=target_id, target_name=target_name, raw_name=raw_name,
                    customer_quote=customer["text"], owner_quote=owner["text"],
                    source=source,
                    evidence={"xml_sha256": xml_hash, "archive_sha256": archive_hash,
                              "archive_member": member_name, "table_index": table_index,
                              "header_row": header_row, "row_index": row_index,
                              "column_index": customer_column,
                              "owner_row_index": owner["origin_row"],
                              "owner_rowspan": owner["rowspan"],
                              "customer_origin_row_index": customer["origin_row"],
                              "customer_rowspan": customer["rowspan"]},
                    fiscal_year=fiscal_year,
                    report_period_start=report_period_start,
                    report_period_end=report_period_end)
                candidates.setdefault(relation["stable_id"], relation)
    reasons["tables_seen"] = len(tables)
    reasons["matching_tables"] = table_matches
    relations = sorted(candidates.values(), key=lambda row: row["stable_id"])
    by_company = {}
    for relation in relations:
        for person in relation["participants"]:
            by_company.setdefault(person["id"], []).append(relation["stable_id"])
    return {"relations": relations, "by_company": by_company,
            "coverage": {"input": 1, "customer_cells_examined": customer_cells_examined,
                         "candidate_names": candidate_names,
                         "relationships": len(relations), "identity_holds": len(holds),
                         "rejection_reasons": dict(reasons)},
            "holds": holds, "source": source,
            "provenance": {"archive_sha256": archive_hash, "xml_sha256": xml_hash,
                           "archive_member": member_name}}
