"""Pure, fail-closed joins to the fixed retained DART overview artifact.

This is additional retained source text, not a complete filing or fresh evidence.
No aliases, fuzzy matching, retrieval, review acceptance or spending occurs here.
Hashes bind bytes, not authenticity: callers must supply the fixed raw artifact.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import date
import hashlib
import re

from .portfolio_public_sources import safe_public_text

CONTEXT_FIELD = "retained_context_v1"
_FIELDS = {"issuer_name", "receipt_no", "filing_date", "text", "raw_sha256", "excerpt_sha256"}
_DART_URL = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo="
# Same rejection boundary as the existing extraction lane; never import that
# lane here (it consumes this helper). Safety checks also cover the whole suffix.
_INSTRUCTION = re.compile(r"ignore.{0,30}instruction|system\s*prompt|api[_ -]?key|비밀|지시를?\s*무시", re.I)
_REASONS = ("shape", "identity", "name", "receipt", "date", "url", "text", "instruction",
            "hash", "prefix", "collision", "missing-raw", "existing-context")


def _sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _public_lines(text):
    # Exact project_public_business_overviews transformation, NOT whitespace
    # deletion/case folding/Unicode normalization or a semantic similarity test.
    return text.replace("\r\n", " ").replace("\r", " ").replace("\n", " ").strip()


def _public_excerpt(text):
    # Mirror _cut_at_sentence(600) + refresh_kr_business_overview_public's hard
    # 600-character cap. Kept pure: importing the collector loads api.config.
    # Require the entire projection, not any arbitrary short matching prefix.
    excerpt = text
    if len(text) > 600:
        head = text[:600]
        for mark in ("습니다.", "합니다.", "다."):
            index = head.rfind(mark)
            if index > 300:
                excerpt = head[:index + len(mark)].strip()
                break
        else:
            excerpt = head.rstrip() + "…"
        if len(excerpt) > 600:
            excerpt = excerpt[:599] + "…"
    return _public_lines(excerpt)


def validate_retained_context(doc):
    """Return effective public text; absent context leaves the excerpt unchanged.

    Context text and both hashes retain original UTF-8 bytes. Only CR/LF are
    projected to spaces for the existing public-text safety boundary and output.
    This does not replace the caller's base document/counterparty validation.
    """
    if type(doc) is not dict or type(doc.get("text")) is not str:
        raise ValueError("shape")
    if CONTEXT_FIELD not in doc:
        return doc["text"]
    context = doc[CONTEXT_FIELD]
    if type(context) is not dict or set(context) != _FIELDS:
        raise ValueError("shape")
    if not re.fullmatch(r"KR:[0-9]{6}", str(doc.get("issuer_id"))):
        raise ValueError("identity")
    name = context["issuer_name"]
    if safe_public_text(name, 160) is None or name != doc.get("issuer_name"):
        raise ValueError("name")
    receipt = context["receipt_no"]
    if (type(receipt) is not str or not re.fullmatch(r"[0-9]{14}", receipt)
            or doc.get("source_id") != "source:dart:" + receipt):
        raise ValueError("receipt")
    filing_date = f"{receipt[:4]}-{receipt[4:6]}-{receipt[6:8]}"
    if context["filing_date"] != filing_date or doc.get("as_of") != filing_date:
        raise ValueError("date")
    try:
        date.fromisoformat(filing_date)
    except ValueError:
        raise ValueError("date") from None
    if doc.get("url") != _DART_URL + receipt:
        raise ValueError("url")
    text, excerpt = context["text"], doc["text"]
    if (type(text) is not str or not 1 <= len(text) <= 2500
            or len(excerpt) > 600 or safe_public_text(excerpt, 600) is None
            or safe_public_text(_public_lines(text), 2500) is None):
        raise ValueError("text")
    effective = _public_lines(text)
    if _INSTRUCTION.search(effective) or _INSTRUCTION.search(excerpt):
        raise ValueError("instruction")
    try:
        valid_hashes = context["raw_sha256"] == _sha(text) and context["excerpt_sha256"] == _sha(excerpt)
    except UnicodeEncodeError:
        raise ValueError("text") from None
    if not valid_hashes:
        raise ValueError("hash")
    if _public_excerpt(text) != excerpt:
        raise ValueError("prefix")
    return effective


def enrich_judgment_documents(documents, raw):
    """Copy documents, add only unambiguous, validated, longer retained text.

    ``raw`` is the parsed dart_business_overview.json envelope (``rows`` keyed
    by six-digit ticker). Duplicate source IDs in documents or duplicate receipt
    IDs in raw rows reject all affected joins, including partially equal copies.
    Missing/invalid optional context falls back to the unchanged base excerpt;
    an invalid pre-attached context is removed. No input object is modified.
    Counts partition input into enriched/unchanged/rejected; reasons are closed.
    """
    if type(documents) is not list or any(type(doc) is not dict for doc in documents):
        raise ValueError("shape")
    rows = raw.get("rows") if type(raw) is dict else None
    if type(rows) is not dict:
        raise ValueError("shape")
    sources = Counter(doc.get("source_id") for doc in documents
                      if type(doc.get("source_id")) is str)
    receipts = Counter(row.get("rcept_no") for row in rows.values()
                       if type(row) is dict and type(row.get("rcept_no")) is str)
    result = deepcopy(documents)
    counts = {"input": len(result), "enriched": 0, "unchanged": 0, "rejected": 0,
              "reasons": {reason: 0 for reason in _REASONS}}
    for doc in result:
        had_context = CONTEXT_FIELD in doc
        existing = doc.pop(CONTEXT_FIELD, None)
        try:
            issuer = doc.get("issuer_id")
            if type(issuer) is not str or not re.fullmatch(r"KR:[0-9]{6}", issuer):
                raise ValueError("identity")
            source_id = doc.get("source_id")
            if type(source_id) is not str:
                raise ValueError("identity")
            row = rows.get(issuer[3:])
            if type(row) is not dict:
                raise ValueError("missing-raw")
            receipt = row.get("rcept_no")
            if type(receipt) is not str:
                raise ValueError("receipt")
            if sources[source_id] != 1 or receipts[receipt] != 1:
                raise ValueError("collision")
            filed = row.get("rcept_dt")
            if type(filed) is not str or not re.fullmatch(r"[0-9]{8}", filed):
                raise ValueError("date")
            text, excerpt = row.get("text"), doc.get("text")
            if type(text) is not str or type(excerpt) is not str:
                raise ValueError("text")
            try:
                context = {"issuer_name": row.get("name"), "receipt_no": receipt,
                           "filing_date": f"{filed[:4]}-{filed[4:6]}-{filed[6:8]}",
                           "text": text, "raw_sha256": _sha(text), "excerpt_sha256": _sha(excerpt)}
            except UnicodeEncodeError:
                raise ValueError("text") from None
            doc[CONTEXT_FIELD] = context
            effective = validate_retained_context(doc)
            if had_context and existing != context:
                raise ValueError("existing-context")
            if effective == excerpt:
                doc.pop(CONTEXT_FIELD)
                counts["unchanged"] += 1
            elif existing == context:
                counts["unchanged"] += 1
            else:
                counts["enriched"] += 1
        except ValueError as error:
            if str(error) not in counts["reasons"]:
                raise
            doc.pop(CONTEXT_FIELD, None)
            counts["rejected"] += 1
            counts["reasons"][str(error)] += 1
    return result, counts
