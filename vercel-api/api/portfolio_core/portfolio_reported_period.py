"""Offline, source-bound reported customer period; no grading or I/O.

Compact validation checks internal binding only. Authenticity requires the full
archive recomputation entry point, never a caller-supplied hash alone.
"""
from copy import deepcopy
from datetime import date
from hashlib import sha256
import json
import re
from .portfolio_filing_excerpts import _legal_name
from .portfolio_public_sources import safe_public_text

_FIELDS = {
    "schema", "source_version", "source_id", "company_id", "counterparty_id",
    "corp_code", "archive_sha256", "xml_sha256", "archive_member",
    "report_period_start", "report_period_end", "fiscal_year", "paragraph_index",
    "paragraph_quote", "table_index", "header_row", "row_index", "column_index",
    "rows", "table_sha256", "period_quote", "revision",
}
_SHA = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_ID = re.compile(r"KR:[0-9]{6}\Z", re.ASCII)
_HOLD = re.compile(r"과거|이전|당시|초기|예정|계획|중단|종료|취소|철회|아니|않|없|미확인|가정|조건")


def _digest(value, *, compact=True):
    options = {"separators": (",", ":")} if compact else {}
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                             allow_nan=False, **options).encode("utf-8")).hexdigest()


def _space(value):
    return " ".join(value.split())


def _text(value, limit=600):
    if (type(value) is not str or safe_public_text(value, limit) is None
            or re.search(r"[<>\x00-\x1f\x7f]", value)):
        raise ValueError("reported-period-text")
    return value


def _relation(row, name, base, customer_names):
    quote, scope = _text(row.get("quote")), _text(row.get("scope_quote"))
    period = row.get("period_quote")
    if type(period) is not str or not re.fullmatch(r"20[0-9]{2}년", period, re.ASCII):
        raise ValueError("reported-period-year")
    years = set(re.findall(r"(?<![0-9])20[0-9]{2}(?![0-9])", quote))
    if (scope not in quote or _space(quote) not in base._sentences(_space(quote))
            or len(base._sentences(_space(quote))) != 1 or quote[-1] not in ".!?"
            or _HOLD.search(quote) or base._has_unresolved_scope(quote)
            or base._OTHER_SUBJECT.search(quote)
            or (years and years != {period[:4]})
            or not re.match(r"^당사(?:의|는|가)\s", quote)
            or not re.match(r"^당사(?:의|는|가)\s", scope)):
        raise ValueError("reported-period-relation-scope")
    # The stated scope must introduce THIS customer list, not another clause's
    # business scope in a multi-business sentence.
    label = re.search(re.escape(scope) + r"\s+(?:주요\s*)?(?:고객사|고객|매출처)\s*(?:은|는|:)", quote)
    if label is None:
        raise ValueError("reported-period-customer-scope")
    listing = re.split(r"등|이며|있으며|;|；", quote[label.end():], maxsplit=1)[0]
    names = customer_names(listing.strip())
    if sum(_legal_name(n).casefold() == _legal_name(name).casefold() for n in names) != 1:
        raise ValueError("reported-period-customer-name")
    return quote


def _table(rows, year, name):
    if (type(rows) is not list or not 2 <= len(rows) <= 500
            or len(json.dumps(rows, ensure_ascii=False).encode()) > 512 * 1024):
        raise ValueError("reported-period-table-shape")
    width = None
    for cells in rows:
        if type(cells) is not list or not 2 <= len(cells) <= 40:
            raise ValueError("reported-period-table-shape")
        width = len(cells) if width is None else width
        if len(cells) != width:
            raise ValueError("reported-period-table-shape")
        for cell in cells:
            _text(cell, 2000)
    headers = []
    for index, cells in enumerate(rows):
        if re.sub(r"\s", "", cells[0]) not in {"업체", "회사", "매출처"}:
            continue
        if not all(re.fullmatch(r"20[0-9]{2}년", _space(c), re.ASCII) for c in cells[1:]):
            raise ValueError("reported-period-table-year")
        if any(int(_space(c)[:4]) > int(year) for c in cells[1:]):
            raise ValueError("reported-period-table-year")
        if len({_space(c) for c in cells[1:]}) != len(cells[1:]):
            raise ValueError("reported-period-table-year")
        columns = [c for c in range(1, width) if _space(cells[c]) == year + "년"]
        if len(columns) == 1:
            headers.append((index, columns[0]))
    if len(headers) != 1:
        raise ValueError("reported-period-table-header")
    header, column = headers[0]
    matches = [i for i in range(header + 1, len(rows))
               if _legal_name(rows[i][0]).casefold() == _legal_name(name).casefold()]
    if len(matches) != 1:
        raise ValueError("reported-period-table-customer")
    # Preserve amounts verbatim; do not compute a share, score or threshold.
    if not re.fullmatch(r"[0-9]+(?:,[0-9]{3})*(?:\.[0-9]+)?", rows[matches[0]][column]):
        raise ValueError("reported-period-table-amount")
    return header, matches[0], column


def validate_reported_period_projection(context, row):
    """Validate compact internal binding; does NOT authenticate original bytes."""
    if type(context) is not dict or set(context) != _FIELDS or type(row) is not dict:
        raise ValueError("reported-period-shape")
    if context["schema"] != "reported-customer-period-v1":
        raise ValueError("reported-period-schema")
    for key in ("source_version", "archive_sha256", "xml_sha256", "table_sha256", "revision"):
        if type(context[key]) is not str or not _SHA.fullmatch(context[key]):
            raise ValueError("reported-period-hash")
    for key in ("company_id", "counterparty_id"):
        if type(context[key]) is not str or not _ID.fullmatch(context[key]) or context[key] != row.get(key):
            raise ValueError("reported-period-row-identity")
    if context["company_id"] == context["counterparty_id"]:
        raise ValueError("reported-period-row-identity")
    for key in ("source_id", "source_version", "period_quote"):
        if context[key] != row.get(key):
            raise ValueError("reported-period-row-binding")
    match = re.fullmatch(r"source:dart:([0-9]{14})", str(context["source_id"]))
    if (not match or context["archive_member"] != match[1] + ".xml"
            or type(context["corp_code"]) is not str
            or not re.fullmatch(r"[0-9]{8}", context["corp_code"], re.ASCII)
            or type(context["fiscal_year"]) is not str
            or not re.fullmatch(r"20[0-9]{2}", context["fiscal_year"], re.ASCII)
            or context["period_quote"] != context["fiscal_year"] + "년"):
        raise ValueError("reported-period-source-identity")
    try:
        start, end = (date.fromisoformat(context[k]) for k in ("report_period_start", "report_period_end"))
        filed = date.fromisoformat(f"{match[1][:4]}-{match[1][4:6]}-{match[1][6:8]}")
        if (start.isoformat() != context["report_period_start"] or end.isoformat() != context["report_period_end"]
                or start > end or end.year != int(context["fiscal_year"]) or end > filed or filed > date.today()):
            raise ValueError("period")
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("reported-period-calendar") from exc
    for key in ("paragraph_index", "table_index", "header_row", "row_index", "column_index"):
        if type(context[key]) is not int or context[key] < 0:
            raise ValueError("reported-period-index")
    rows = context["rows"]
    index = context["row_index"]
    if type(rows) is not list or index >= len(rows) or type(rows[index]) is not list or not rows[index]:
        raise ValueError("reported-period-index")
    name = row.get("counterparty_name", rows[index][0])
    _text(name, 160)
    legal_name = _legal_name(name).casefold()
    if (legal_name in {"기타", "계", "합계", "고객", "매출처", "익명"}
            or re.search(r"그룹|계열|종속|고객군|익명", legal_name)
            or re.fullmatch(r"[a-z](?:사|업체|기업)?|(?:고객|매출처|업체)[a-z0-9]+", legal_name)):
        raise ValueError("reported-period-customer-name")
    if _table(rows, context["fiscal_year"], name) != (context["header_row"], index, context["column_index"]):
        raise ValueError("reported-period-table-binding")
    # These are literal compact bindings, NOT full-sentence/role approval.
    # The candidate fingerprint and original producer own those gates.
    quote, scope = _text(row.get("quote")), _text(row.get("scope_quote"))
    paragraph = _text(context["paragraph_quote"])
    if _space(paragraph).count(_space(quote)) != 1 or scope not in quote:
        raise ValueError("reported-period-paragraph")
    if context["table_sha256"] != _digest(rows) or context["revision"] != _digest(
            {k: v for k, v in context.items() if k != "revision"}):
        raise ValueError("reported-period-revision")
    return deepcopy(context)


def _business_section(node):
    section = node.find_parent("section-1")
    title = section.find("title", recursive=False) if section is not None else None
    return section if title is not None and re.sub(r"\s", "", title.get_text()) == "II.사업의내용" else None


def build_reported_customer_period(source, row, *, archives, issuer_registry):
    """Build the fixed 22-field witness from caller-provided native ZIP bytes."""
    import warnings
    from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
    from . import portfolio_ai_fallback as base
    from .portfolio_annual_customer_tables import (
        MAX_TABLES, _archive_member, _metadata, _source_identity,
        _logical_grid, _customer_names,
    )
    base.validate_document(source)
    if type(row) is not dict or row.get("company_id") != source["issuer_id"]:
        raise ValueError("reported-period-company")
    version = _digest(source, compact=False)
    if row.get("source_id", source["source_id"]) != source["source_id"] or row.get("source_version", version) != version:
        raise ValueError("reported-period-source-version")
    if type(archives) is not dict or source["source_id"] not in archives or type(issuer_registry) is not dict:
        raise ValueError("reported-period-original-unavailable")
    issuer = issuer_registry.get(source["issuer_id"])
    if (type(issuer) is not dict or not {"name", "corp_code"} <= set(issuer)
            or _legal_name(_text(issuer["name"], 160)).casefold() != _legal_name(source["issuer_name"]).casefold()):
        raise ValueError("reported-period-issuer-registry")
    parties = [p for p in source["counterparties"] if p["id"] == row.get("counterparty_id")]
    if len(parties) != 1:
        raise ValueError("reported-period-counterparty")
    name = parties[0]["name"]
    quote = _relation(row, name, base, _customer_names)
    if base._sentences(_space(source["text"])).count(_space(quote)) != 1:
        raise ValueError("reported-period-document-quote")
    year, receipt = row["period_quote"][:4], source["source_id"].split(":")[-1]
    archive = archives[source["source_id"]]
    body, member = _archive_member(archive, receipt + ".xml")
    if member != receipt + ".xml":
        raise ValueError("reported-period-member")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", XMLParsedAsHTMLWarning)
        soup = BeautifulSoup(body, "html.parser")
    # Report title is bound to actual PERIODTO metadata, not the cache request.
    ends = [t for t in soup.find_all("tu") if str(t.get("aunit", "")).casefold() == "periodto"]
    raw_end = ends[0].get("aunitvalue") if len(ends) == 1 else None
    if type(raw_end) is not str or not re.fullmatch(r"[0-9]{8}", raw_end, re.ASCII):
        raise ValueError("reported-period-report-period")
    report = f"사업보고서 ({raw_end[:4]}.{raw_end[4:6]})"
    _metadata(receipt_no=receipt, issuer_id=source["issuer_id"], issuer_name=issuer["name"],
              corp_code=issuer["corp_code"], filed_on=source["as_of"], fiscal_year=year, report_name=report)
    start, end = _source_identity(soup, source["issuer_id"], issuer["name"], issuer["corp_code"], year, report)
    paragraphs = []
    for index, p in enumerate(soup.find_all("p")):
        section = _business_section(p)
        overview = p.find_parent("section-2")
        title = overview.find("title", recursive=False) if overview is not None else None
        if (section is None or title is None or re.sub(r"\s", "", title.get_text()) != "1.사업의개요"
                or p.find_parent("table") is not None):
            continue
        text = _space(p.get_text(" ", strip=True))
        count = base._sentences(text).count(_space(quote))
        paragraphs.extend((index, text, section) for _ in range(count))
    if len(paragraphs) != 1:
        raise ValueError("reported-period-original-paragraph")
    paragraph_index, paragraph_quote, section = paragraphs[0]
    paragraph_years = set(re.findall(r"(?<![0-9])20[0-9]{2}(?![0-9])", paragraph_quote))
    if (_HOLD.search(paragraph_quote) or base._OTHER_SUBJECT.search(paragraph_quote)
            or (paragraph_years and paragraph_years != {year})):
        raise ValueError("reported-period-paragraph")
    tables = soup.find_all("table")
    if not 1 <= len(tables) <= MAX_TABLES:
        raise ValueError("reported-period-table-count")
    matches = []
    for table_index, table in enumerate(tables):
        if _business_section(table) is not section or table.find_parent("table") is not None:
            continue
        enclosing = table.find_parent("section-2")
        title = enclosing.find("title", recursive=False) if enclosing is not None else None
        if title is None or "매출" not in title.get_text():
            continue
        try:
            _, grid = _logical_grid(table)
            if any(c["rowspan"] != 1 or c["colspan"] != 1 for r in grid for c in r.values()):
                raise ValueError("merged")
            rows = [[r[i]["text"] for i in range(len(r))] for r in grid]
            header, row_index, column = _table(rows, year, name)
            matches.append((table_index, rows, header, row_index, column))
        except ValueError:
            continue
    if len(matches) != 1:
        raise ValueError("reported-period-original-table")
    table_index, rows, header, row_index, column = matches[0]
    result = {"schema": "reported-customer-period-v1", "source_version": version,
              "source_id": source["source_id"], "company_id": source["issuer_id"],
              "counterparty_id": row["counterparty_id"], "corp_code": issuer["corp_code"],
              "archive_sha256": sha256(archive).hexdigest(), "xml_sha256": sha256(body).hexdigest(),
              "archive_member": member, "report_period_start": start, "report_period_end": end,
              "fiscal_year": year, "paragraph_index": paragraph_index, "paragraph_quote": paragraph_quote,
              "table_index": table_index, "header_row": header, "row_index": row_index,
              "column_index": column, "rows": rows, "table_sha256": _digest(rows),
              "period_quote": row["period_quote"]}
    result["revision"] = _digest(result)
    bound_row = {**row, "source_id": source["source_id"], "source_version": version, "counterparty_name": name}
    return validate_reported_period_projection(result, bound_row)


def validate_reported_customer_period(context, source, row, *, archives, issuer_registry):
    """Fresh export gate: recompute from originals; missing originals reject."""
    actual = build_reported_customer_period(source, row, archives=archives, issuer_registry=issuer_registry)
    name = next(p["name"] for p in source["counterparties"] if p["id"] == actual["counterparty_id"])
    validate_reported_period_projection(context, {**row, "source_id": actual["source_id"],
            "source_version": actual["source_version"], "counterparty_name": name})
    if type(context) is not dict or context != actual:
        raise ValueError("reported-period-original-mismatch")
    return deepcopy(actual)
