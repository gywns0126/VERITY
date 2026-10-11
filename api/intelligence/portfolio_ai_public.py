"""Closed public AI-candidate artifact and selected-company projection; no I/O.

The offline producer owns original-document and semantic verification. This
boundary checks the prepared wire contract, public text, catalogue bindings and
content hashes only. Hashes detect inconsistency, not publisher authenticity.
No model, fallback, ledger, credentials or network modules are imported here.
"""
from copy import deepcopy
from datetime import date
import hashlib
import json
import re

from .portfolio_filing_excerpts import _legal_name
from .portfolio_public_sources import safe_public_text


PUBLIC_AI_REVIEW_FILE = "member_map_ai_candidates.json"
MAX_CANDIDATES = 400
MAX_BYTES = 2_000_000
MAX_RETURNED = 40
_ERROR = "invalid-public-ai-review"
_ENTITY = re.compile(r"(?:KR:[0-9]{6}|US:[A-Z][A-Z0-9.-]{0,12})\Z", re.ASCII)
_SOURCE = re.compile(r"source:dart:([0-9]{14})\Z", re.ASCII)
_CANDIDATE_FIELDS = {
    "id", "revision", "issuer_id", "issuer_name", "counterparty_id", "counterparty_name",
    "role", "quote", "source_id", "url", "as_of", "status", "verification",
    "evidence_scope", "current_validity",
}
_CLAIM_FIELDS = {
    "claim_kind", "directness", "claim_state", "quote", "context", "scope_quote",
    "channel_quote", "counter_evidence_quotes", "missing_evidence", "review_reasons",
    "decision", "degree", "degree_basis",
}
_CONTEXT_FIELDS = {"object_quote", "scale_quote", "time_quote"}
_MISSING = {
    "entity_scope", "role", "object", "period", "scale", "denominator", "structured_table",
    "counter_evidence_not_searched", "path_evidence", "source_context",
}


def _fail():
    raise ValueError(_ERROR)


def _keys(value, fields):
    if type(value) is not dict or set(value) != fields:
        _fail()


def _digest(value):
    # Canonical bytes match the offline producer, including default separators.
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def _text(value, limit):
    if (type(value) is not str or safe_public_text(value, limit) is None
            or re.search(r"[<>\x00-\x1f\x7f]", value)
            or len(value.encode("utf-16-le")) // 2 > limit):
        _fail()
    return value  # Preserve original bytes/spacing used by revision hashes.


def _entity(value):
    if type(value) is not str or not _ENTITY.fullmatch(value):
        _fail()
    return value


def _catalog_names(catalog):
    if type(catalog) not in (list, tuple):
        _fail()
    names, owners = {}, {}
    for company in catalog:
        if type(company) is not dict:
            _fail()
        market, ticker = company["market"], company["ticker"]
        if type(market) is not str or type(ticker) is not str:
            _fail()
        identifier = _entity(market + ":" + ticker)
        if identifier in names or ("id" in company and company["id"] != identifier):
            _fail()
        name = _legal_name(_text(company["name"], 160))
        if not name:
            _fail()
        names[identifier] = name
        owners.setdefault(name, set()).add(identifier)
    return names, owners


def _context(value, quote):
    _keys(value, _CONTEXT_FIELDS)
    for key, span in value.items():
        if span is not None and _text(span, 600 if key == "scale_quote" else 120) not in quote:
            _fail()


def _claims(values):
    if type(values) is not list or not 1 <= len(values) <= 4:
        _fail()
    seen = set()
    for claim in values:
        _keys(claim, _CLAIM_FIELDS)
        if (claim["claim_kind"] not in ("relation_fact", "conditional_exposure", "co_mention")
                or claim["directness"] not in ("direct", "indirect", "not_applicable")
                or claim["claim_state"] not in ("asserted", "planned", "conditional", "negated", "historical", "conflicted")
                or claim["decision"] not in ("candidate", "needs_context", "conflict")
                or claim["degree"] != "unrated" or claim["degree_basis"] != "unrated"):
            _fail()
        quote = _text(claim["quote"], 600)
        _context(claim["context"], quote)
        for key in ("scope_quote", "channel_quote"):
            if claim[key] is not None and _text(claim[key], 600) not in quote:
                _fail()
        for key, limit in (("counter_evidence_quotes", 4), ("missing_evidence", 11), ("review_reasons", 10)):
            items = claim[key]
            if type(items) is not list or len(items) > limit:
                _fail()
            for value in items:
                if key == "counter_evidence_quotes":
                    # These may come from another sentence in the source. Its
                    # literal source binding is the offline producer's duty.
                    _text(value, 600)
                elif key == "missing_evidence":
                    if type(value) is not str or value not in _MISSING:
                        _fail()
                elif not re.fullmatch(r"[a-z-]{1,60}", _text(value, 60), re.ASCII):
                    _fail()
            if len(set(items)) != len(items):
                _fail()
        fingerprint = _digest(claim)
        if fingerprint in seen:
            _fail()
        seen.add(fingerprint)


def _validate(payload, catalog):
    _keys(payload, {"schema", "candidates", "coverage"})
    if (payload["schema"] != "local-ai-review-v1" or type(payload["candidates"]) is not list
            or len(payload["candidates"]) > MAX_CANDIDATES
            or len(json.dumps(payload, ensure_ascii=False, allow_nan=False).encode()) > MAX_BYTES):
        _fail()
    coverage = payload["coverage"]
    _keys(coverage, {"input", "accepted", "rejected", "skipped"})
    if (any(type(value) is not int or not 0 <= value <= 2**53 - 1 for value in coverage.values())
            or coverage["accepted"] != len(payload["candidates"])
            or coverage["input"] != coverage["accepted"] + coverage["rejected"] + coverage["skipped"]):
        _fail()
    names, owners = _catalog_names(catalog)
    seen = set()
    for row in payload["candidates"]:
        if type(row) is not dict:
            _fail()
        _keys(row, _CANDIDATE_FIELDS | (set(row) & {"context", "claims"}))
        issuer, party = _entity(row["issuer_id"]), _entity(row["counterparty_id"])
        if issuer == party:
            _fail()
        for identifier, key in ((issuer, "issuer_name"), (party, "counterparty_name")):
            name = _legal_name(_text(row[key], 160))
            if names.get(identifier) != name or owners.get(name) != {identifier}:
                _fail()
        source = row["source_id"]
        match = _SOURCE.fullmatch(source) if type(source) is str else None
        if not match:
            _fail()
        receipt = match[1]
        stamp = f"{receipt[:4]}-{receipt[4:6]}-{receipt[6:8]}"
        if (row["as_of"] != stamp or date.fromisoformat(stamp).isoformat() != stamp
                or row["url"] != "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=" + receipt
                or row["status"] != "ai_candidate" or row["verification"] != "unreviewed-model-extraction"
                or row["current_validity"] != "not-inferred"
                or row["evidence_scope"] not in ("historical-context", "unspecified")
                or row["role"] not in (("customer", "supplier", "partner", "other")
                                       if "claims" in row else ("customer", "supplier"))):
            _fail()
        quote = _text(row["quote"], 10000)
        if "context" in row:
            _context(row["context"], quote)
        if "claims" in row:
            _claims(row["claims"])
            if quote != row["claims"][0]["quote"]:
                _fail()
        identifier = "automatic:ai:" + _digest([source, issuer, party, row["role"]])[:24]
        if (row["id"] != identifier or identifier in seen
                or row["revision"] != _digest({key: value for key, value in row.items() if key != "revision"})):
            _fail()
        seen.add(identifier)
    return deepcopy(payload)


def validate_public_ai_review(payload, catalog):
    """Validate the entire prepared artifact; never drop just an invalid row."""
    try:
        return _validate(payload, catalog)
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
        raise ValueError(_ERROR) from None


def project_public_ai_review(payload, catalog, selected_ids):
    """Return at most 40 matching candidates, preserving input order and totals."""
    try:
        prepared = validate_public_ai_review(payload, catalog)
        if type(selected_ids) not in (list, tuple, set, frozenset):
            _fail()
        selected = {_entity(identifier) for identifier in selected_ids}
        if len(selected) != len(selected_ids):
            _fail()
        matching = [row for row in prepared["candidates"]
                    if row["issuer_id"] in selected or row["counterparty_id"] in selected]
        return {"schema": "local-ai-review-v1", "candidates": matching[:MAX_RETURNED],
                "coverage": {**prepared["coverage"], "matched": len(matching),
                             "returned": min(len(matching), MAX_RETURNED),
                             "omitted": max(len(matching) - MAX_RETURNED, 0)}}
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
        raise ValueError(_ERROR) from None
