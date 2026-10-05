"""Exact public cross-feed reconciliation for DART filing receipts."""
from __future__ import annotations

from datetime import date
import re
import unicodedata


_RECEIPT = re.compile(r"[0-9]{14}\Z", re.ASCII)
_TICKER = re.compile(r"[0-9]{6}\Z", re.ASCII)
_DATE = re.compile(r"[0-9]{8}\Z", re.ASCII)
_DART_ID_URL = re.compile(
    r"DART:([0-9]{14})\|https://dart\.fss\.or\.kr/dsaf001/main\.do\?rcpNo=([0-9]{14})\Z",
    re.ASCII,
)
_ISO_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\Z", re.ASCII)
_MAX_INPUT = 1000


def _date8(value):
    if not isinstance(value, str) or not _DATE.fullmatch(value):
        return None
    try:
        parsed = date(int(value[:4]), int(value[4:6]), int(value[6:8]))
    except ValueError:
        return None
    return parsed.isoformat()


def _iso_date(value):
    if not isinstance(value, str) or not _ISO_DATE.fullmatch(value):
        return None
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        return None


def _title(value):
    if not isinstance(value, str) or len(value) > 500:
        return None
    return " ".join(unicodedata.normalize("NFKC", value).split()) or None


def _coverage(input_count=0, matched=0, rejected=0, unmatched=0, omitted=0, shape_errors=0):
    return {"input": input_count, "matched": matched, "rejected": rejected,
            "unmatched": unmatched, "omitted": omitted, "shape_errors": shape_errors}


def attach_source_matches(public_documents, document_list):
    """Attach only exact DART receipt/ticker/date/title cross-feed matches.

    `matched` counts retained exact receipt/ticker pairs; exact duplicates
    increment only `omitted`. Only the supplied display
    documents are eligible targets.
    """
    for document in document_list if isinstance(document_list, list) else ():
        if isinstance(document, dict):
            document.pop("source_matches", None)
    portfolio = public_documents.get("portfolio.json") if isinstance(public_documents, dict) else None
    shape_errors = 0
    if portfolio is None:
        return _coverage()
    if not isinstance(portfolio, dict):
        return _coverage(shape_errors=1)
    if "dart_catalyst_alerts" not in portfolio:
        return _coverage()
    alerts = portfolio.get("dart_catalyst_alerts")
    if not isinstance(alerts, dict) or not isinstance(alerts.get("events"), list):
        return _coverage(shape_errors=1)
    events = alerts["events"]
    input_count = len(events)
    if input_count > _MAX_INPUT:
        return _coverage(input_count=input_count, rejected=input_count)
    if not isinstance(document_list, list):
        return _coverage(input_count=input_count, rejected=input_count, shape_errors=1)

    docs_by_receipt = {}
    for document in document_list:
        if not isinstance(document, dict):
            continue
        if document.get("kind") != "disclosure" or document.get("source") != "DART":
            continue
        identifier, url = document.get("id"), document.get("url")
        if not isinstance(identifier, str) or not isinstance(url, str):
            continue
        pair = _DART_ID_URL.fullmatch(identifier + "|" + url)
        if not pair or pair.group(1) != pair.group(2):
            continue
        receipt = pair.group(1)
        doc_date = _iso_date(document.get("as_of"))
        title = _title(document.get("title"))
        company_ids = document.get("company_ids")
        if doc_date is None or title is None or not isinstance(company_ids, list):
            continue
        tickers = {identifier[3:] for identifier in company_ids
                   if isinstance(identifier, str) and identifier.startswith("KR:")
                   and _TICKER.fullmatch(identifier[3:])}
        docs_by_receipt.setdefault(receipt, []).append((document, doc_date, title, tickers))

    rejected = unmatched = matched = omitted = 0
    seen_pairs = set()
    staged = {}
    for row in events:
        if not isinstance(row, dict):
            rejected += 1
            continue
        receipt, ticker = row.get("rcept_no"), row.get("ticker")
        filing_date, title = _date8(row.get("rcept_dt")), _title(row.get("report_nm"))
        if (not isinstance(receipt, str) or not _RECEIPT.fullmatch(receipt)
                or not isinstance(ticker, str) or not _TICKER.fullmatch(ticker)
                or filing_date is None or title is None):
            rejected += 1
            continue
        pair_key = (receipt, ticker)
        matches = [(document, doc_date, doc_title, tickers)
                   for document, doc_date, doc_title, tickers in docs_by_receipt.get(receipt, ())
                   if ticker in tickers and filing_date == doc_date and title == doc_title]
        if not matches:
            unmatched += 1
            continue
        if pair_key in seen_pairs:
            omitted += 1
            continue
        seen_pairs.add(pair_key)
        matched += 1
        for document, doc_date, doc_title, tickers in matches:
            staged.setdefault(id(document), (document, []))[1].append({
                "kind": "same-dart-receipt", "source_file": "portfolio.json",
                "receipt_no": receipt, "ticker": ticker, "as_of": doc_date,
            })
    for document, entries in staged.values():
        document["source_matches"] = sorted(
            entries, key=lambda entry: (entry["ticker"], entry["receipt_no"], entry["as_of"])
        )
    return _coverage(input_count, matched, rejected, unmatched, omitted, shape_errors)
