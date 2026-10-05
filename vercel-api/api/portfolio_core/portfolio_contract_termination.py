"""Closed extraction for observed public DART contract-termination layouts.

The filing proves that a termination notice was reported. It does not prove
that the contract is already terminated, resolve the counterparty, or infer an
effective date from narrative text.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import re

from bs4 import BeautifulSoup

from .portfolio_contract_facts import (
    MAIN,
    MAX_HTML,
    _ISSUER,
    _RECEIPT,
    _calendar_day,
    _contract_title,
    _decode,
    _field,
    _is_correction_title,
    _name,
    _observation,
    _quoted_day,
    _quoted_field,
    _rows,
    _single,
    _source_text,
    _text,
    _valid_viewer_url,
)


SCHEMA = "dart-contract-termination-v1"
PROVES = "termination-notice"
STATUS = "not-inferred"
MAX_RELATED_FILINGS = 20
_RELATED_HREF = re.compile(r"/dsaf001/main[.]do[?]rcpNo=([0-9]{14})\Z", re.ASCII)
_RELATED_TEXT = re.compile(r"([0-9]{4}-[0-9]{2}-[0-9]{2})\s+(.+)\Z")


def _filing_title(value):
    return _contract_title(value)


def _termination_title(value):
    normalized = re.sub(r"^\[(?:기재|첨부|기타)?정정\]", "", _name(value), count=1).strip()
    return _contract_title(normalized)


def _related_documents(soup, filed_on, table_index, label):
    containers = soup.select("body .xforms")
    if len(containers) != 1:
        raise ValueError("invalid-contract-termination-layout")
    tables = containers[0].find_all("table")
    if not 0 <= table_index < len(tables):
        raise ValueError("invalid-contract-termination-links")
    matches = []
    table = tables[table_index]
    for row in table.find_all("tr"):
        if row.find_parent("table") is not table:
            continue
        cells = row.find_all(["td", "th"], recursive=False)
        if cells and _name(_text(cells[0])) == _name(label):
            matches.append(cells)
    if len(matches) != 1 or len(matches[0]) != 2:
        raise ValueError("invalid-contract-termination-links")

    value_cell = matches[0][1]
    anchors = value_cell.find_all("a", href=True)
    if not 1 <= len(anchors) <= MAX_RELATED_FILINGS:
        raise ValueError("invalid-contract-termination-links")
    filings, documents, receipts = [], [], set()
    for anchor in anchors:
        displayed = _text(anchor)
        text_match = _RELATED_TEXT.fullmatch(displayed)
        href = anchor.get("href")
        href_match = _RELATED_HREF.fullmatch(href) if isinstance(href, str) else None
        if not text_match or not href_match:
            raise ValueError("invalid-contract-termination-link")
        related_on, title = text_match.groups()
        receipt_no = href_match.group(1)
        if (_calendar_day(related_on) > filed_on
                or receipt_no[:8] != related_on.replace('-', '')
                or receipt_no in receipts):
            raise ValueError("invalid-contract-termination-link")
        receipts.add(receipt_no)
        value = {"receipt_no": receipt_no, "filed_on": related_on,
                 "title": _source_text(title), "href": href}
        if _filing_title(title) == "단일판매공급계약체결":
            filings.append(value)
        else:
            documents.append(value)

    # Reject hidden or unlinked receipt-like text in the same value cell.
    if _text(value_cell) != _source_text(" ".join(_text(anchor) for anchor in anchors)):
        raise ValueError("invalid-contract-termination-links")
    return filings, documents


def _validate_related_link(link, *, receipt, as_of, seen, contract):
    if not isinstance(link, dict) or set(link) != {"receipt_no", "filed_on", "title", "href"}:
        raise ValueError("invalid-contract-termination")
    related_receipt = link.get("receipt_no")
    expected_href = f"/dsaf001/main.do?rcpNo={related_receipt}"
    title = _source_text(link.get("title"))
    is_contract = _filing_title(title) == "단일판매공급계약체결"
    if (not isinstance(related_receipt, str) or not _RECEIPT.fullmatch(related_receipt)
            or link.get("href") != expected_href
            or _calendar_day(link.get("filed_on")) > as_of
            or related_receipt[:8] != link["filed_on"].replace('-', '')
            or related_receipt == receipt or not title or len(title) > 300
            or is_contract is not contract or related_receipt in seen):
        raise ValueError("invalid-contract-termination")
    seen.add(related_receipt)


def validate_contract_termination(value):
    """Validate and return one closed termination-notice fact."""
    required = {
        "schema", "receipt_no", "issuer", "as_of", "filing_title", "source",
        "contract", "termination", "proves", "current_contract_status",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError("invalid-contract-termination")
    receipt = value.get("receipt_no")
    issuer = value.get("issuer")
    source = value.get("source")
    if (value.get("schema") != SCHEMA
            or not isinstance(receipt, str) or not _RECEIPT.fullmatch(receipt)
            or not isinstance(issuer, dict) or set(issuer) != {"id", "name", "source_name"}
            or not isinstance(issuer.get("id"), str) or not _ISSUER.fullmatch(issuer["id"])
            or not _name(issuer.get("name")) or len(_name(issuer["name"])) > 160
            or not _name(issuer.get("source_name")) or len(_name(issuer["source_name"])) > 160
            or value.get("proves") != PROVES
            or value.get("current_contract_status") != STATUS
            or _termination_title(value.get("filing_title")) != "단일판매공급계약해지"):
        raise ValueError("invalid-contract-termination")
    as_of = _calendar_day(value.get("as_of"))
    if (not isinstance(source, dict)
            or set(source) != {"main_url", "viewer_url", "observed_at", "content_sha256", "bytes"}
            or source.get("main_url") != MAIN + receipt
            or not _valid_viewer_url(source.get("viewer_url"), receipt)
            or not isinstance(source.get("content_sha256"), str)
            or re.fullmatch(r"[0-9a-f]{64}", source["content_sha256"], re.ASCII) is None
            or type(source.get("bytes")) is not int or not 0 < source["bytes"] <= MAX_HTML
            or as_of > _observation(source.get("observed_at")).date()):
        raise ValueError("invalid-contract-termination")

    contract = value.get("contract")
    if not isinstance(contract, dict) or set(contract) != {"name", "counterparty", "period"}:
        raise ValueError("invalid-contract-termination")
    _quoted_field(contract["name"])
    _quoted_field(contract["counterparty"])
    period = contract.get("period")
    if (not isinstance(period, dict) or set(period) != {"label", "start", "end"}
            or not _source_text(period.get("label")) or len(_source_text(period["label"])) > 2000):
        raise ValueError("invalid-contract-termination")
    start, end = _quoted_field(period["start"]), _quoted_field(period["end"])
    if _quoted_day(start["value"]) > _quoted_day(end["value"]):
        raise ValueError("invalid-contract-termination")

    termination = value.get("termination")
    if not isinstance(termination, dict) or set(termination) not in (
            {"date", "reason", "other_matters", "related_filings"},
            {"date", "reason", "other_matters", "related_filings", "related_documents"}):
        raise ValueError("invalid-contract-termination")
    _quoted_field(termination["date"])
    _quoted_day(termination["date"]["value"])
    _quoted_field(termination["reason"])
    _quoted_field(termination["other_matters"])
    links = termination.get("related_filings")
    documents = termination.get("related_documents", [])
    if (not isinstance(links, list) or not isinstance(documents, list)
            or not 1 <= len(links) + len(documents) <= MAX_RELATED_FILINGS):
        raise ValueError("invalid-contract-termination")
    seen = set()
    for link in links:
        _validate_related_link(link, receipt=receipt, as_of=as_of, seen=seen, contract=True)
    for link in documents:
        _validate_related_link(link, receipt=receipt, as_of=as_of, seen=seen, contract=False)
    return deepcopy(value)


def parse_contract_termination(viewer_bytes, *, receipt_no, issuer_id, issuer_name,
                               expected_source_issuer_name, filed_on, main_url,
                               viewer_url, observed_at):
    """Parse the observed KOSPI or KOSDAQ termination layout without inference."""
    if (not isinstance(receipt_no, str) or not _RECEIPT.fullmatch(receipt_no)
            or not isinstance(issuer_id, str) or not _ISSUER.fullmatch(issuer_id)
            or not _name(issuer_name) or not _name(expected_source_issuer_name)
            or main_url != MAIN + receipt_no or not _valid_viewer_url(viewer_url, receipt_no)):
        raise ValueError("invalid-contract-termination-source")
    as_of = _calendar_day(filed_on)
    if as_of > _observation(observed_at).date():
        raise ValueError("invalid-contract-termination-date")
    raw = viewer_bytes
    soup = BeautifulSoup(_decode(raw), "html.parser")
    title_source = _source_text(soup.title.get_text(" ", strip=True) if soup.title else "")
    parts = title_source.split("/")
    expected_title_tail = f"({filed_on.replace('-', '.')}){parts[1]}" if len(parts) == 3 else ""
    if (len(parts) != 3 or _name(parts[0]) != _name(expected_source_issuer_name)
            or _termination_title(parts[1]) != "단일판매공급계약해지"
            or _name(parts[2]) != _name(expected_title_tail)):
        raise ValueError("invalid-contract-termination-title")

    rows = _rows(soup)
    layout_matches = [(kind, row) for kind, label in (
        ("kospi", "1. 판매ㆍ공급계약 해지 구분"),
        ("kosdaq", "1. 판매ㆍ공급계약 해지내용"),
    ) for row in rows if row["cells"] and _name(row["cells"][0]) == _name(label)]
    if len(layout_matches) != 1:
        raise ValueError("invalid-contract-termination-layout")
    layout, anchor = layout_matches[0]
    body_rows = [row for row in rows if row["table_index"] == anchor["table_index"]]
    if layout == "kospi":
        name_row = _single(body_rows, "- 해지계약명")
        counterparty_row = _single(body_rows, "3. 계약상대")
        reason_row = _single(body_rows, "5. 해지 주요사유")
        other_row = _single(body_rows, "8. 기타 투자판단과 관련한 중요사항")
        related_label = "관련공시"
    else:
        name_row = anchor
        counterparty_row = _single(body_rows, "3. 계약상대방")
        reason_row = _single(body_rows, "5. 주요 해지사유")
        other_row = _single(body_rows, "8. 기타 투자판단에 참고할 사항")
        related_label = "※관련공시"
    period_row = _single(body_rows, "4. 계약기간")
    date_row = _single(body_rows, "6. 해지일자")
    if len(period_row["cells"]) != 3 or _name(period_row["cells"][1]) != "시작일":
        raise ValueError("invalid-contract-termination-period")
    end_rows = [row for row in body_rows if row["row_index"] > period_row["row_index"]
                and row["cells"] and _name(row["cells"][0]) == "종료일"]
    if len(end_rows) != 1 or len(end_rows[0]["cells"]) != 2:
        raise ValueError("invalid-contract-termination-period")

    related_filings, related_documents = _related_documents(
        soup, as_of, anchor["table_index"], related_label)
    termination = {"date": _field(date_row), "reason": _field(reason_row),
                   "other_matters": _field(other_row),
                   "related_filings": related_filings}
    if related_documents:
        termination["related_documents"] = related_documents
    result = {
        "schema": SCHEMA,
        "receipt_no": receipt_no,
        "issuer": {"id": issuer_id, "name": _name(issuer_name),
                   "source_name": _name(expected_source_issuer_name)},
        "as_of": filed_on,
        "filing_title": parts[1],
        "source": {"main_url": main_url, "viewer_url": viewer_url,
                   "observed_at": observed_at,
                   "content_sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)},
        "contract": {
            "name": _field(name_row),
            "counterparty": _field(counterparty_row),
            "period": {"label": period_row["cells"][0],
                       "start": {"label": period_row["cells"][1],
                                 "value": period_row["cells"][2]},
                       "end": {"label": end_rows[0]["cells"][0],
                               "value": end_rows[0]["cells"][1]}},
        },
        "termination": termination,
        "proves": PROVES,
        "current_contract_status": STATUS,
    }
    return validate_contract_termination(result)


def attach_contract_terminations(artifact, document_list, company_catalog):
    """Attach exact notices to exact disclosure rows without status promotion."""
    for document in document_list:
        document.pop("contract_termination", None)
    rows = artifact.get("contract_terminations", []) if isinstance(artifact, dict) else []
    coverage = {"input": len(rows) if isinstance(rows, list) else 0, "accepted": 0,
                "rejected": 0, "unmatched": 0, "attached_documents": 0,
                "promoted_contracts": 0}
    if not isinstance(rows, list) or len(rows) > 1000:
        coverage["rejected"] = coverage["input"]
        return coverage
    catalog = {row.get("id"): row for row in company_catalog if isinstance(row, dict)}
    staged, receipts = {}, set()
    for raw in rows:
        try:
            fact = validate_contract_termination(raw)
            receipt, issuer = fact["receipt_no"], fact["issuer"]["id"]
            company = catalog.get(issuer)
            source_names = {_name(name) for name in company.get("source_names", [company.get("name")])} if company else set()
            if (receipt in receipts or company is None
                    or _name(fact["issuer"]["name"]) not in source_names
                    or _name(fact["issuer"]["source_name"]) not in source_names):
                raise ValueError("invalid-contract-termination-binding")
            receipts.add(receipt)
        except (KeyError, TypeError, ValueError):
            coverage["rejected"] += 1
            continue
        matched = [document for document in document_list
                   if document.get("id") == "DART:" + receipt
                   and document.get("url") == fact["source"]["main_url"]
                   and document.get("source") == "DART"
                   and document.get("kind") == "disclosure"
                   and document.get("company_ids") == [issuer]
                   and document.get("as_of") == fact["as_of"]
                   and _is_correction_title(document.get("title")) == _is_correction_title(fact["filing_title"])
                   and _termination_title(document.get("title")) == _termination_title(fact["filing_title"])]
        if len(matched) != 1 or matched[0]["id"] in staged:
            coverage["unmatched"] += 1
            continue
        staged[matched[0]["id"]] = (matched[0], fact)
        coverage["accepted"] += 1
    for document, fact in staged.values():
        document["contract_termination"] = {
            key: deepcopy(fact[key]) for key in (
                "schema", "receipt_no", "issuer", "as_of", "filing_title",
                "contract", "termination", "proves", "current_contract_status",
            )
        }
        coverage["attached_documents"] += 1
    return coverage


def link_termination_notices(events, documents):
    """Attach notice evidence only through an exact, issuer-bound prior receipt.

    It does not merge events or change their current status. A notice can name
    multiple prior contracts; that is not evidence that those are one event.
    """
    notices = [doc for doc in documents if doc.get('contract_termination')]
    linked = 0
    for event in events:
        references = {}
        for doc in event['documents']:
            references[doc['id'].removeprefix('DART:')] = (doc['as_of'], _filing_title(doc['title']))
            for member in doc.get('event_lineage', {}).get('members', []):
                references[member['receipt_no']] = (member['published_on'], _filing_title(member['title']))
        attached = []
        for doc in notices:
            notice = doc['contract_termination']
            if notice['issuer']['id'] != event['participants'][0]['id']:
                continue
            if any(references.get(link['receipt_no']) == (link['filed_on'], _filing_title(link['title']))
                   for link in notice['termination']['related_filings']):
                attached.append(deepcopy(doc))
        if attached:
            event['termination_notices'] = sorted(attached, key=lambda d: (d['as_of'], d['id']))
            linked += len(attached)
    return linked
