"""Bounded source-field extraction for public DART contract filing bodies.

This module preserves quoted filing strings. It does not resolve counterparties,
infer contract validity, score relationships, or predict market impact.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime
import hashlib
import json
import re
import unicodedata
from urllib.parse import parse_qs, urlencode, urlsplit

from bs4 import BeautifulSoup, Comment, NavigableString


MAIN = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo="
VIEWER = "https://dart.fss.or.kr/report/viewer.do"
MAX_HTML = 1024 * 1024
MAX_TABLES = 20
MAX_ROWS = 200
MAX_CELLS = 8
MAX_CELL_CHARS = 2000
_RECEIPT = re.compile(r"[0-9]{14}\Z", re.ASCII)
_ISSUER = re.compile(r"KR:[0-9]{6}\Z", re.ASCII)
_DAY = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\Z", re.ASCII)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
MAX_EVENT_DOCUMENTS = 100
MAX_SELECTED_EVENT_BYTES = 512 * 1024
_DOC = re.compile(
    r"\bviewDoc\(\s*(['\"])([0-9]{14})\1\s*,\s*(['\"])([0-9]{1,20})\3"
    r"\s*,\s*(['\"])0\5\s*,\s*(['\"])0\6\s*,\s*(['\"])0\7"
    r"\s*,\s*(['\"])HTML\8\s*(?:,\s*(['\"])\9\s*)?\)"
)


def _name(value):
    if not isinstance(value, str) or any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise ValueError("invalid-contract-source")
    return " ".join(unicodedata.normalize("NFKC", value).split())


def _source_text(value):
    if not isinstance(value, str) or any(ord(ch) < 32 and ch not in "\t\r\n" for ch in value):
        raise ValueError("invalid-contract-source")
    return " ".join(value.split())


def _calendar_day(value):
    if not isinstance(value, str) or not _DAY.fullmatch(value):
        raise ValueError("invalid-contract-date")
    return date.fromisoformat(value)


def _quoted_day(value):
    """Normalize the date only for comparisons; retain the quoted source text."""
    match = re.fullmatch(r"([0-9]{4})[.-]([0-9]{1,2})[.-]([0-9]{1,2})\.?", value or "")
    if not match:
        raise ValueError("invalid-contract-date")
    return date(*(int(part) for part in match.groups()))


def _observation(value):
    if not isinstance(value, str) or len(value) > 40:
        raise ValueError("invalid-contract-observation")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("invalid-contract-observation")
    return parsed


def _valid_viewer_url(url, receipt_no):
    if not isinstance(url, str):
        return False
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.netloc != "dart.fss.or.kr" or parsed.fragment:
        return False
    params = parse_qs(parsed.query, keep_blank_values=True)
    if (parsed.path != "/report/viewer.do" or set(params) != {
            "rcpNo", "dcmNo", "eleId", "offset", "length", "dtd"}
            or any(len(values) != 1 for values in params.values())):
        return False
    return (params["rcpNo"] == [receipt_no]
            and re.fullmatch(r"[0-9]{1,20}", params["dcmNo"][0], re.ASCII) is not None
            and all(params[key] == ["0"] for key in ("eleId", "offset", "length"))
            and params["dtd"] == ["HTML"]
            and url == VIEWER + "?" + urlencode({
                "rcpNo": receipt_no, "dcmNo": params["dcmNo"][0], "eleId": "0",
                "offset": "0", "length": "0", "dtd": "HTML",
            }))


def extract_viewer_url(main_html, receipt_no):
    """Extract one literal whole-document viewer URL for the requested receipt."""
    if (not isinstance(main_html, str) or len(main_html.encode("utf-8")) > MAX_HTML
            or not isinstance(receipt_no, str) or not _RECEIPT.fullmatch(receipt_no)):
        raise ValueError("invalid-contract-source")
    soup = BeautifulSoup(main_html, "html.parser")
    candidates = set()
    for script in soup.find_all("script"):
        for match in _DOC.finditer(script.get_text()):
            if match[2] == receipt_no:
                candidates.add(match[4])
    if len(candidates) != 1:
        raise ValueError("invalid-contract-viewer")
    url = VIEWER + "?" + urlencode({
        "rcpNo": receipt_no, "dcmNo": candidates.pop(), "eleId": "0",
        "offset": "0", "length": "0", "dtd": "HTML",
    })
    if not _valid_viewer_url(url, receipt_no):
        raise ValueError("invalid-contract-viewer")
    return url


def _decode(raw):
    if not isinstance(raw, bytes) or not raw or len(raw) > MAX_HTML:
        raise ValueError("invalid-contract-source")
    for encoding in ("utf-8", "euc-kr", "cp949"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("invalid-contract-source")


def _text(node):
    parts = []
    stack = [node]
    while stack:
        child = stack.pop()
        if isinstance(child, Comment):
            continue
        if isinstance(child, NavigableString):
            parts.append(str(child))
        elif getattr(child, "name", None) not in {"script", "style", "noscript", "template", "iframe", "object"}:
            stack.extend(reversed(list(child.children)))
    value = _source_text("".join(parts))
    if len(value) > MAX_CELL_CHARS:
        raise ValueError("contract-field-too-large")
    return value


def _rows(soup):
    containers = soup.select("body .xforms")
    if len(containers) != 1:
        raise ValueError("invalid-contract-layout")
    tables = containers[0].find_all("table")
    if not 1 <= len(tables) <= MAX_TABLES:
        raise ValueError("invalid-contract-layout")
    rows = []
    for table_index, table in enumerate(tables):
        for row_index, row in enumerate(table.find_all("tr")):
            if row.find_parent("table") is not table:
                continue
            cells = row.find_all(["td", "th"], recursive=False)
            if not cells or len(cells) > MAX_CELLS or any(cell.find("table") for cell in cells):
                continue
            values = [_text(cell) for cell in cells]
            if any(values):
                rows.append({"table_index": table_index, "row_index": row_index, "cells": values})
    if not rows or len(rows) > MAX_ROWS:
        raise ValueError("invalid-contract-layout")
    return rows


def _single(rows, label):
    target = _name(label)
    matches = [row for row in rows if row["cells"] and _name(row["cells"][0]) == target]
    if len(matches) != 1:
        raise ValueError("invalid-contract-field")
    return matches[0]


def _field(row, value_index=-1):
    cells = row["cells"]
    if len(cells) < 2 or not cells[value_index]:
        raise ValueError("invalid-contract-field")
    return {"label": cells[0], "value": cells[value_index]}


def _contract_title(value):
    return re.sub(r"[\sㆍᆞ·•]", "", _name(value))


def _filing_title(value):
    return re.sub(r"^\[(?:기재|첨부|기타)?정정\]", "", _name(value)).strip()


def _is_correction_title(value):
    return re.match(r"^\[(?:기재|첨부|기타)?정정\]", _name(value)) is not None


def _quoted_field(value):
    if not isinstance(value, dict) or set(value) != {"label", "value"}:
        raise ValueError("invalid-contract-fact")
    label, text = _source_text(value["label"]), _source_text(value["value"])
    if not label or not text or len(label) > 2000 or len(text) > 2000:
        raise ValueError("invalid-contract-fact")
    return {"label": label, "value": text}


def validate_contract_fact(value):
    """Validate one closed manifest-bound fact without resolving counterparties."""
    required = {
        "schema", "receipt_no", "issuer", "filing", "source", "contract", "correction",
        "counterparty_company_id", "verified_common_event", "current_contract_status",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError("invalid-contract-fact")
    receipt, issuer = value.get("receipt_no"), value.get("issuer")
    filing, source, contract = value.get("filing"), value.get("source"), value.get("contract")
    if (value.get("schema") != "dart-contract-fact-v1"
            or not isinstance(receipt, str) or not _RECEIPT.fullmatch(receipt)
            or not isinstance(issuer, dict) or set(issuer) != {"id", "name"}
            or not isinstance(issuer.get("id"), str) or not _ISSUER.fullmatch(issuer["id"])
            or not _name(issuer.get("name")) or len(_name(issuer["name"])) > 160
            or not isinstance(filing, dict) or set(filing) not in ({"title", "filed_on"}, {"title", "filed_on", "source_title"})
            or _contract_title(filing.get("title")) != "단일판매공급계약체결"
            or not isinstance(source, dict)
            or set(source) != {"main_url", "viewer_url", "observed_at", "content_sha256", "bytes"}
            or source.get("main_url") != MAIN + receipt
            or not _valid_viewer_url(source.get("viewer_url"), receipt)
            or not isinstance(source.get("content_sha256"), str)
            or not _SHA256.fullmatch(source["content_sha256"])
            or type(source.get("bytes")) is not int or not 0 < source["bytes"] <= MAX_HTML
            or not isinstance(contract, dict)
            or set(contract) != {"type", "name", "counterparty", "period", "signed_on"}
            or value.get("counterparty_company_id") is not None
            or value.get("verified_common_event") is not False
            or value.get("current_contract_status") != "not-inferred"):
        raise ValueError("invalid-contract-fact")
    filed_on = filing.get("filed_on")
    if 'source_title' in filing:
        title = filing['source_title']
        if (not isinstance(title, str) or len(title) > 300 or re.search(r'[<>\x00-\x1f\x7f]', title)
                or _contract_title(_filing_title(title)) != _contract_title(filing['title'])
                or _is_correction_title(title) != (value['correction'] is not None)):
            raise ValueError('invalid-contract-source-title')
    if _calendar_day(filed_on) > _observation(source["observed_at"]).date():
        raise ValueError("invalid-contract-fact")
    period = contract.get("period")
    if (not isinstance(period, dict) or set(period) != {"label", "start", "end"}
            or not _source_text(period.get("label")) or len(_source_text(period["label"])) > 2000):
        raise ValueError("invalid-contract-fact")
    projected_contract = {
        "type": _quoted_field(contract["type"]),
        "name": _quoted_field(contract["name"]),
        "counterparty": _quoted_field(contract["counterparty"]),
        "period": {"label": _source_text(period["label"]),
                   "start": _quoted_field(period["start"]),
                   "end": _quoted_field(period["end"])},
        "signed_on": _quoted_field(contract["signed_on"]),
    }
    correction = value.get("correction")
    projected_correction = None
    if correction is not None:
        if (not isinstance(correction, dict)
                or set(correction) != {"corrected_on", "related_filing_date", "reason", "changes"}
                or not isinstance(correction.get("changes"), list)
                or not 1 <= len(correction["changes"]) <= 20):
            raise ValueError("invalid-contract-fact")
        corrected = _quoted_field(correction["corrected_on"])
        related = _quoted_field(correction["related_filing_date"])
        # The correction can be prepared before its submission date.
        # Preserve both dates; only a date after the filing is contradictory.
        if any(_quoted_day(field["value"]) > _calendar_day(filed_on) for field in (corrected, related)):
            raise ValueError("invalid-contract-date")
        changes = []
        for change in correction["changes"]:
            if not isinstance(change, dict) or set(change) != {"field", "before", "after"}:
                raise ValueError("invalid-contract-fact")
            row = {key: _source_text(change[key]) for key in ("field", "before", "after")}
            if any(not item or len(item) > 2000 for item in row.values()):
                raise ValueError("invalid-contract-fact")
            changes.append(row)
        projected_correction = {"corrected_on": corrected, "related_filing_date": related,
                                "reason": _quoted_field(correction["reason"]), "changes": changes}
    # Validation above uses normalized comparison values, but the enriched
    # public artifact must retain the parser's original quoted strings.
    return deepcopy(value)


def validate_contract_facts_artifact(value):
    """Validate the bounded builder output before evidence enrichment."""
    if (not isinstance(value, dict)
            or set(value) != {"schema", "created_at", "documents", "coverage", "limitations"}
            or value.get("schema") != "portfolio-contract-facts-v1"
            or not isinstance(value.get("documents"), list)
            or not 1 <= len(value["documents"]) <= 1000
            or not isinstance(value.get("coverage"), dict)
            or value["coverage"] != {"input": len(value["documents"]),
                                      "accepted": len(value["documents"]), "rejected": 0}
            or not isinstance(value.get("limitations"), list)
            or not 1 <= len(value["limitations"]) <= 20):
        raise ValueError("invalid-contract-facts-artifact")
    _observation(value.get("created_at"))
    documents, receipts = [], set()
    for row in value["documents"]:
        projected = validate_contract_fact(row)
        if (projected["receipt_no"] in receipts
                or projected["source"]["observed_at"] != value["created_at"]):
            raise ValueError("invalid-contract-facts-artifact")
        receipts.add(projected["receipt_no"])
        documents.append(projected)
    limitations = [_source_text(item) for item in value["limitations"]]
    if any(not item or len(item) > 500 for item in limitations):
        raise ValueError("invalid-contract-facts-artifact")
    return {"schema": value["schema"], "created_at": value["created_at"],
            "documents": documents, "coverage": deepcopy(value["coverage"]),
            "limitations": limitations}


def attach_contract_facts(artifact, document_list, company_catalog):
    """Attach exact filing facts without creating relationships or event identity."""
    for document in document_list:
        document.pop("contract_facts", None)
    rows = artifact.get("contract_facts", []) if isinstance(artifact, dict) else []
    coverage = {"input": len(rows) if isinstance(rows, list) else 0, "accepted": 0,
                "rejected": 0, "unmatched": 0, "attached_documents": 0,
                "resolved_counterparties": 0, "verified_relationships": 0}
    if not isinstance(rows, list) or len(rows) > 1000:
        coverage.update(rejected=coverage["input"], shape_errors=1)
        return coverage
    catalog = {row.get("id"): row for row in company_catalog if isinstance(row, dict)}
    staged, receipts = {}, set()
    for raw in rows:
        try:
            fact = validate_contract_fact(raw)
            receipt, issuer = fact["receipt_no"], fact["issuer"]["id"]
            company = catalog.get(issuer)
            source_names = company.get("source_names", [company.get("name")]) if company else []
            if receipt in receipts or company is None or _name(fact["issuer"]["name"]) not in {_name(n) for n in source_names}:
                raise ValueError("invalid-contract-fact-binding")
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
                   and document.get("as_of") == fact["filing"]["filed_on"]
                   and _is_correction_title(document.get("title")) == (fact["correction"] is not None)
                   and _contract_title(_filing_title(document.get("title")))
                   == _contract_title(fact["filing"]["title"])]
        if len(matched) != 1 or matched[0]["id"] in staged:
            coverage["unmatched"] += 1
            continue
        staged[matched[0]["id"]] = (matched[0], fact)
        coverage["accepted"] += 1
    for document, fact in staged.values():
        document["contract_facts"] = {
            "schema": fact["schema"], "receipt_no": fact["receipt_no"],
            "issuer": fact["issuer"], "filing": {key: fact['filing'][key] for key in ('title', 'filed_on')},
            "contract": fact["contract"], "correction": fact["correction"],
            "counterparty_company_id": None, "verified_common_event": False,
            "current_contract_status": "not-inferred",
        }
        coverage["attached_documents"] += 1
    return coverage


def index_contract_events(artifact, company_catalog):
    """Index explicit contract parties once per public bundle, never per member.

    Exact legal names only; anonymous parties, MOU/forecasts and competing
    contracts never merge. A DART family plus a consistent named contract body
    establishes reported event identity, not current validity or market impact.
    """
    from .portfolio_event_lineage import attach_event_lineage
    from .portfolio_contract_termination import attach_contract_terminations, link_termination_notices
    from .portfolio_public_sources import safe_public_text

    def legal_name(value):
        return re.sub(r"^(?:주식회사|\(주\))|(?:주식회사|\(주\))$", "",
                      re.sub(r"\s+", "", unicodedata.normalize("NFKC", value)).casefold())

    names, documents = {}, {}
    for company in company_catalog:
        if not _ISSUER.fullmatch(company["id"]):
            continue
        for name in company.get("source_names", [company["name"]]):
            names.setdefault(legal_name(name), set()).add(company["id"])
        for raw in company.get("documents", []):
            doc = documents.setdefault(raw["id"], {**deepcopy(raw), "company_ids": []})
            if company["id"] not in doc["company_ids"]:
                doc["company_ids"].append(company["id"])
    values = list(documents.values())
    facts_coverage = attach_contract_facts(artifact, values, company_catalog)
    attach_event_lineage(artifact, values, company_catalog)
    attach_contract_terminations(artifact, values, company_catalog)
    coverage = {"fact_documents": facts_coverage["attached_documents"], "accepted_documents": 0,
                "unresolved_party": 0, "insufficient_terms": 0, "conflicting_family": 0,
                "events": 0}
    groups = {}
    for doc in values:
        fact = doc.get("contract_facts")
        if not fact:
            continue
        contract, issuer = fact["contract"], fact["issuer"]["id"]
        counterparties = names.get(legal_name(contract["counterparty"]["value"]), set())
        if len(counterparties) != 1 or issuer in counterparties:
            coverage["unresolved_party"] += 1
            continue
        counterparty = next(iter(counterparties))
        try:
            start, end = (_quoted_day(contract["period"][key]["value"]) for key in ("start", "end"))
            signed = _quoted_day(contract["signed_on"]["value"])
            name = contract["name"]["value"]
            if (start > end or signed > _calendar_day(doc["as_of"])
                    or len(name.strip()) < 3 or re.search(r"미정|미확정|예정|협의|의향|양해|MOU|LOI|가계약", name, re.I)
                    or names.get(legal_name(fact["issuer"]["name"])) != {issuer}):
                raise ValueError("insufficient-contract-terms")
            # Public field safety, not raw transport metadata, controls display.
            strings = [fact["issuer"]["name"], contract["name"]["value"],
                       contract["type"]["value"], contract["counterparty"]["value"]]
            if any(safe_public_text(text, 2000) is None for text in strings):
                raise ValueError("unsafe-contract-terms")
        except (ValueError, TypeError):
            coverage["insufficient_terms"] += 1
            continue
        family = doc.get("event_lineage")
        # A correction with no explicit official lineage stays a source fact.
        if fact["correction"] is not None and not family:
            coverage["insufficient_terms"] += 1
            continue
        root = family["root_receipt"] if family else fact["receipt_no"]
        key = f"contract:{issuer}:{root}"
        groups.setdefault(key, []).append((doc, issuer, counterparty, name, signed.isoformat()))
    events = []
    for identifier, entries in groups.items():
        # Similar titles/parties/dates without an official family have separate keys.
        signatures = {(a, b, legal_name(name), signed) for _, a, b, name, signed in entries}
        if len(signatures) != 1:
            coverage["conflicting_family"] += len(entries)
            continue
        entries.sort(key=lambda row: (row[0]["as_of"], row[0]["id"]))
        latest, issuer, counterparty, name, signed = entries[-1]
        root = identifier.rsplit(":", 1)[1]
        history = [deepcopy(row[0]) for row in entries]
        events.append({"id": identifier, "kind": "reported-contract", "identity_basis": "explicit-contract-parties",
                       "current_status": "not-inferred", "root_receipt": root,
                       "company_ids": [issuer, counterparty],
                       "participants": [{"id": issuer, "role": "supplier"}, {"id": counterparty, "role": "counterparty"}],
                       "title": name, "as_of": latest["as_of"], "signed_on": signed,
                       "documents": history})
        coverage["accepted_documents"] += len(entries)
    coverage["events"] = len(events)
    coverage["linked_termination_notices"] = link_termination_notices(events, values)
    by_company = {}
    for event in events:
        for identifier in event["company_ids"]:
            by_company.setdefault(identifier, []).append(event["id"])
    return {"events": {event["id"]: event for event in events}, "by_company": by_company,
            "coverage": coverage}


def select_contract_events(index, identifiers, limit=20):
    """Select from the shared reverse index; never mutate or cache selections."""
    selected = set(identifiers)
    keys = {key for identifier in selected for key in index["by_company"].get(identifier, [])}
    events = [index["events"][key] for key in keys]
    events.sort(key=lambda item: (len(selected.intersection(item["company_ids"])) > 1,
                                  max([item["as_of"]] + [d['as_of'] for d in item.get('termination_notices', [])]),
                                  item["id"]), reverse=True)
    items = []
    items_bytes = 2  # JSON array brackets
    oversized_history = 0
    for event in events:
        if len(items) >= limit:
            break
        documents = event.get("documents")
        if (not isinstance(documents, list) or len(documents) > MAX_EVENT_DOCUMENTS
                or len(event.get('termination_notices', [])) > MAX_EVENT_DOCUMENTS):
            oversized_history += 1
            continue
        item = {**deepcopy(event),
                "selected_company_ids": sorted(selected.intersection(event["company_ids"]))}
        encoded = json.dumps(item, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        added_bytes = len(encoded) + (1 if items else 0)
        if items_bytes + added_bytes > MAX_SELECTED_EVENT_BYTES:
            oversized_history += 1
            continue
        items.append(item)
        items_bytes += added_bytes
    return {"items": items, "coverage": {**index["coverage"], "selected": len(events),
            "returned": len(items), "omitted": len(events) - len(items),
            "oversized_history": oversized_history}}


def parse_contract_facts(viewer_bytes, *, receipt_no, issuer_id, issuer_name,
                         filed_on, main_url, viewer_url, observed_at):
    """Extract only explicit contract fields and correction cells from one body."""
    if (not isinstance(receipt_no, str) or not _RECEIPT.fullmatch(receipt_no)
            or not isinstance(issuer_id, str) or not _ISSUER.fullmatch(issuer_id)
            or not _name(issuer_name) or len(_name(issuer_name)) > 160
            or main_url != MAIN + receipt_no or not _valid_viewer_url(viewer_url, receipt_no)):
        raise ValueError("invalid-contract-source")
    filing_day = _calendar_day(filed_on)
    observed = _observation(observed_at)
    if filing_day > observed.date():
        raise ValueError("invalid-contract-date")
    raw = viewer_bytes
    html = _decode(raw)
    soup = BeautifulSoup(html, "html.parser")
    title_source = _source_text(soup.title.get_text(" ", strip=True) if soup.title else "")
    parts = title_source.split("/")
    if (len(parts) < 3 or _name(parts[0]) != _name(issuer_name)
            or _contract_title(parts[1]) != "단일판매공급계약체결"
            or f"({filed_on.replace('-', '.')})" not in title_source):
        raise ValueError("invalid-contract-title")
    rows = _rows(soup)
    kosdaq = any(_name(row["cells"][0]) == _name("1. 판매ㆍ공급계약 내용") for row in rows)
    if kosdaq and any(_name(row["cells"][0]) == _name("1. 판매ㆍ공급계약 구분") for row in rows):
        raise ValueError("ambiguous-contract-layout")
    anchor = _single(rows, "1. 판매ㆍ공급계약 내용" if kosdaq else "1. 판매ㆍ공급계약 구분")
    # Correction tables may quote the same field labels. Contract terms must
    # come from the single table anchored by the actual contract section.
    body_rows = [row for row in rows if row["table_index"] == anchor["table_index"]]
    type_field = ({"label": "공시 유형", "value": parts[1]} if kosdaq
                  else _field(anchor))
    name_row = _single(body_rows, "1. 판매ㆍ공급계약 내용" if kosdaq else "- 체결계약명")
    counterparty_row = _single(body_rows, "3. 계약상대방" if kosdaq else "3. 계약상대")
    period_row = _single(body_rows, "5. 계약기간")
    signed_row = _single(body_rows, "8. 계약(수주)일자" if kosdaq else "7. 계약(수주)일자")
    if len(period_row["cells"]) != 3 or _name(period_row["cells"][1]) != "시작일":
        raise ValueError("invalid-contract-period")
    end_rows = [row for row in rows if row["table_index"] == period_row["table_index"]
                and row["row_index"] > period_row["row_index"]
                and row["cells"] and _name(row["cells"][0]) == "종료일"]
    if len(end_rows) != 1 or len(end_rows[0]["cells"]) != 2:
        raise ValueError("invalid-contract-period")
    correction_rows = [row for row in rows if row["cells"] and _name(row["cells"][0]) == "정정일자"]
    correction = None
    if correction_rows:
        if len(correction_rows) != 1:
            raise ValueError("invalid-contract-correction")
        related = _single(rows, "2. 정정관련 공시서류제출일")
        reason = _single(rows, "3. 정정사유")
        headers = [row for row in rows if [_name(value) for value in row["cells"][:3]]
                   == ["정정항목", "정정전", "정정후"]]
        if len(headers) != 1:
            raise ValueError("invalid-contract-correction")
        header = headers[0]
        changes = [{"field": row["cells"][0], "before": row["cells"][1], "after": row["cells"][2]}
                   for row in rows if row["table_index"] == header["table_index"]
                   and row["row_index"] > header["row_index"] and len(row["cells"]) >= 3]
        if not changes:
            raise ValueError("invalid-contract-correction")
        corrected_on = _field(correction_rows[0])
        related_on = _field(related)
        if any(_quoted_day(field["value"]) > filing_day for field in (corrected_on, related_on)):
            raise ValueError("invalid-contract-date")
        correction = {"corrected_on": corrected_on, "related_filing_date": related_on,
                      "reason": _field(reason), "changes": changes}
    return {
        "schema": "dart-contract-fact-v1",
        "receipt_no": receipt_no,
        "issuer": {"id": issuer_id, "name": _name(issuer_name)},
        "filing": {"title": parts[1], "filed_on": filed_on},
        "source": {"main_url": main_url, "viewer_url": viewer_url,
                   "observed_at": observed_at, "content_sha256": hashlib.sha256(raw).hexdigest(),
                   "bytes": len(raw)},
        "contract": {
            "type": type_field,
            "name": _field(name_row),
            "counterparty": _field(counterparty_row),
            "period": {"label": period_row["cells"][0],
                       "start": {"label": period_row["cells"][1], "value": period_row["cells"][2]},
                       "end": {"label": end_rows[0]["cells"][0], "value": end_rows[0]["cells"][1]}},
            "signed_on": _field(signed_row),
        },
        "correction": correction,
        "counterparty_company_id": None,
        "verified_common_event": False,
        "current_contract_status": "not-inferred",
    }
