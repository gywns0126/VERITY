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
MAX_COMPANY_JUDGMENTS = 16
_JUDGMENT_SCHEMA = "local-company-judgments-v1"
_JUDGMENT_FIELDS = {
    "record_id", "base_read_revision", "read_revision", "revision", "company_id",
    "counterparty_id", "source_id", "source_url", "published_on", "quote", "scope_quote",
    "period_quote", "status", "reviewed_on", "review_reason", "degree", "impact",
    "reason", "review_trigger", "missing_evidence", "review_reasons",
}
_JUDGMENT_REASON = "공개 원문에 연결된 회사별 검토입니다."
_JUDGMENT_TRIGGER = "원문이나 검토 범위가 바뀌면 다시 확인합니다."
_CONDITION_LABEL = "공개 원문에 명시된 조건과 범위가 유지되는 경우"
_REVIEW_LABELS = {"pending": None, "held": "검토가 보류되었습니다.",
                  "rejected": "검토가 반려되었습니다.", "accepted": "원문 범위의 검토가 완료되었습니다."}
_REVIEW_CODES = {
    "entity-scope", "state-or-time", "publication-date-is-not-period", "counter-evidence-review",
    "qualitative-degree-support", "degree-scope-or-period", "degree-context", "missing-context",
    "degree-party-attribution", "issuer-exposure-evidence-omitted", "counterparty-product-acronym",
    "impact-mechanism-missing", "impact-party-attribution",
}
_MATERIALITY_CODES = {"materiality-scope", "materiality-period", "materiality-economic-basis"}
_CHANGED_FIELDS = {
    "quote", "degree", "impact", "counter_evidence_quotes", "missing_evidence", "reason",
    "review_trigger", "economic_v2", "period_context_v2", "status", "review_reasons", "display",
}


def _enum(value, allowed):
    if type(value) is not str or value not in allowed:
        _fail()
    return value


def _hash_value(value):
    if type(value) is not str or not re.fullmatch(r"[a-f0-9]{64}", value):
        _fail()
    return value


def _day(value):
    if type(value) is not str or date.fromisoformat(value).isoformat() != value:
        _fail()
    return value


def _codes(values, allowed, limit):
    if type(values) is not list or len(values) > limit:
        _fail()
    for value in values:
        _enum(value, allowed)
    if len(set(values)) != len(values):
        _fail()
    return list(values)


def _bound_quote(value, quotes):
    if value is not None and not any(_text(value, 600) in quote for quote in quotes):
        _fail()
    return value


def _review_label(row, published):
    status = _enum(row["status"], _REVIEW_LABELS)
    if status == "pending":
        if row["reviewed_on"] is not None or row["review_reason"] is not None:
            _fail()
    elif (type(row["review_reason"]) is not str or not row["review_reason"].strip()
          or not published <= _day(row["reviewed_on"]) <= date.today().isoformat()):
        _fail()
    return _REVIEW_LABELS[status]


def _judgment_candidates(candidates):
    # Reuse the closed candidate contract. This is content binding, not proof
    # that a publisher actually ran the offline raw-document/receipt review.
    if type(candidates) is not list or len(candidates) > MAX_CANDIDATES:
        _fail()
    catalog = {}
    for c in candidates:
        for prefix in ("issuer", "counterparty"):
            identifier, name = c[prefix + "_id"], c[prefix + "_name"]
            if identifier in catalog and catalog[identifier]["name"] != name:
                _fail()
            market, ticker = identifier.split(":")
            catalog[identifier] = {"market": market, "ticker": ticker, "name": name}
    _validate({"schema": "local-ai-review-v1", "candidates": candidates,
               "coverage": {"input": len(candidates), "accepted": len(candidates),
                            "rejected": 0, "skipped": 0}}, list(catalog.values()))
    return {c["id"]: c for c in candidates}


def _judgment_comparison(value, row):
    _keys(value, {"status", "unavailable_reason", "changed_fields", "review_changed_fields", "previous", "current"})
    value = deepcopy(value)
    _enum(value["status"], {"first", "unavailable", "changed", "unchanged"})
    _codes(value["changed_fields"], _CHANGED_FIELDS, len(_CHANGED_FIELDS))
    _codes(value["review_changed_fields"], {"decision", "reason", "checks", "materiality_review"}, 4)
    for key in ("current", "previous"):
        snapshot = value[key]
        if key == "previous" and snapshot is None:
            continue
        _keys(snapshot, {"source_version", "judgment_revision", "review_revision", "assessed_as_of",
                         "reviewed_on", "reason", "review_reason"})
        for field in ("source_version", "judgment_revision", "review_revision"):
            _hash_value(snapshot[field])
        if not row["published_on"] <= _day(snapshot["assessed_as_of"]) <= date.today().isoformat():
            _fail()
        if snapshot["reviewed_on"] is None:
            if snapshot["review_reason"] is not None:
                _fail()
        elif not row["published_on"] <= _day(snapshot["reviewed_on"]) <= snapshot["assessed_as_of"]:
            _fail()
        snapshot["reason"] = _JUDGMENT_REASON
        snapshot["review_reason"] = (row["review_reason"] if key == "current" else
                                      "이전 검토 기록입니다." if snapshot["reviewed_on"] else None)
    current, previous = value["current"], value["previous"]
    if (current["review_revision"] != row["revision"] or current["reviewed_on"] != row["reviewed_on"]
            or current["source_version"] != row["source_version"]):
        _fail()
    if value["status"] in {"changed", "unchanged"}:
        if (previous is None or value["unavailable_reason"] is not None
                or not previous["reviewed_on"] or not current["reviewed_on"]
                or previous["source_version"] != current["source_version"]
                or previous["assessed_as_of"] > current["assessed_as_of"]
                or previous["reviewed_on"] > current["reviewed_on"]
                or (value["status"] == "changed") != bool(value["changed_fields"] or value["review_changed_fields"])):
            _fail()
    else:
        if previous is not None or value["changed_fields"] or value["review_changed_fields"]:
            _fail()
        if value["status"] == "first":
            if value["unavailable_reason"] is not None:
                _fail()
        else:
            _enum(value["unavailable_reason"], {"invalid-history", "history-binding", "unreviewed",
                                               "time-reversed", "source-changed", "scope-period-changed"})
    return value


def _public_judgment(row, candidates, *, source_documents=None, public_wire=False):
    optional = {k for k in ("economic_v2", "period_context_v2", "comparison") if type(row) is dict and k in row}
    _keys(row, _JUDGMENT_FIELDS | {"source_version"} | optional)
    _hash_value(row["source_version"])
    c = candidates.get(row["record_id"])
    if c is None:
        _fail()
    for field, key in (("company_id", "issuer_id"), ("counterparty_id", "counterparty_id"),
                       ("source_id", "source_id"), ("source_url", "url"), ("published_on", "as_of")):
        if row[field] != c[key]:
            _fail()
    if (not row["company_id"].startswith("KR:")
            or type(row["base_read_revision"]) is not int
            or row["base_read_revision"] != int(c["revision"][:13], 16) + 1
            or type(row["read_revision"]) is not int
            or row["read_revision"] != int(_hash_value(row["revision"])[:13], 16) + 1):
        _fail()
    quotes = [c["quote"], *[claim["quote"] for claim in c.get("claims", [])]]
    if _text(row["quote"], 600) not in quotes:
        _fail()
    if source_documents is not None:
        source = source_documents.get(row["source_id"])
        if (source is None or source["source_version"] != row["source_version"]
                or source["issuer_id"] != c["issuer_id"] or source["url"] != c["url"]
                or source["as_of"] != c["as_of"] or row["quote"] not in source["text"]
                or _legal_name(source["issuer_name"]) != _legal_name(c["issuer_name"])
                or not any(p["id"] == c["counterparty_id"]
                           and _legal_name(p["name"]) == _legal_name(c["counterparty_name"])
                           for p in source["counterparties"])):
            _fail()
    elif not public_wire:
        _fail()
    # Economic evidence remains limited to existing public candidate spans.
    for container in [c, *c.get("claims", [])]:
        quotes.extend(q for q in container.get("context", {}).values() if q is not None)
        quotes.extend(container.get("counter_evidence_quotes", []))
    out = deepcopy(row)
    _bound_quote(row["scope_quote"], [row["quote"]])
    period_support = row["quote"]
    if "period_context_v2" in row:
        context = row["period_context_v2"]
        _keys(context, {"quote", "source_version"})
        if context["source_version"] != row["source_version"]:
            _fail()
        period_support = _text(context["quote"], 600)
        if (not period_support or not re.search(r"[.!?]$", period_support)
                or type(row["period_quote"]) is not str
                or not re.fullmatch(r"(?:20\d{2}년(?:도)?|당기|보고기간|회계연도)", row["period_quote"])):
            _fail()
        if source_documents is not None:
            # Literal binding only. The offline producer already owns sentence
            # adjacency, issuer scope and semantic review; do not import it here.
            if source["text"].count(period_support) != 1:
                _fail()
        # Prepared public wire is checked by equality with its candidate-bound
        # fingerprint below; hashes are not publisher authenticity. No source
        # body or reconstructed receipt is required/imported at runtime.
    _bound_quote(row["period_quote"], [period_support])
    out["review_reason"] = _review_label(row, row["published_on"])
    _enum(row["degree"], {"high", "medium", "low", "unrated"})
    _codes(row["missing_evidence"], _MISSING, 10)
    _codes(row["review_reasons"], _REVIEW_CODES, 10)
    impact = out["impact"]
    _keys(impact, {"direction", "channel", "condition"})
    _enum(impact["direction"], {"positive", "negative", "mixed", "unknown"})
    _enum(impact["channel"], {"revenue", "cost", "capacity", "funding", "regulation", "unknown"})
    if impact["condition"] is not None:
        if type(impact["condition"]) is not str or not impact["condition"].strip():
            _fail()
        # Do not publish a model's invented conditional prose.
        impact["condition"] = _CONDITION_LABEL
    if row["status"] == "accepted":
        if (not row["scope_quote"] or not row["period_quote"] or row["review_reasons"]
                or (impact["direction"] != "unknown" and (impact["channel"] == "unknown" or impact["condition"] is None))):
            _fail()
    elif row["degree"] != "unrated" or impact["direction"] != "unknown":
        _fail()
    for key, label in (("reason", _JUDGMENT_REASON), ("review_trigger", _JUDGMENT_TRIGGER)):
        if type(row[key]) is not str or not row[key].strip():
            _fail()
        out[key] = label
    if "economic_v2" in row:
        econ = out["economic_v2"]
        _keys(econ, {"materiality", "impact_quote", "counter_evidence_quotes"})
        m = econ["materiality"]
        _keys(m, {"value", "scope", "quote", "scope_quote", "period_quote", "mechanism_quote",
                  "status", "reviewed_on", "review_reason", "review_reasons"})
        _enum(m["value"], {"material", "limited", "unrated"})
        _enum(m["scope"], {"company", "division", "product", "unknown"})
        m["review_reason"] = _review_label(m, row["published_on"])
        _codes(m["review_reasons"], _MATERIALITY_CODES, 3)
        _bound_quote(m["quote"], quotes)
        if m["quote"] is not None and not re.search(r"[.!?]$", m["quote"]):
            _fail()
        for key in ("scope_quote", "period_quote", "mechanism_quote"):
            _bound_quote(m[key], [m["quote"] or ""])
        _bound_quote(econ["impact_quote"], [row["quote"]])
        counters = econ["counter_evidence_quotes"]
        if type(counters) is not list or len(counters) > 4:
            _fail()
        for q in counters:
            if q is None or q == row["quote"]:
                _fail()
            _bound_quote(q, quotes)
        if len(set(counters)) != len(counters):
            _fail()
        if row["status"] == "accepted" and impact["direction"] != "unknown" and not econ["impact_quote"]:
            _fail()
        if m["status"] == "accepted":
            scope, period, quote = m["scope_quote"] or "", m["period_quote"] or "", m["quote"] or ""
            scoped = re.match(r"^당사(?:의)?\s+", scope) and {
                "company": bool(re.fullmatch(r"당사(?:의)?\s+(?:전체|전사)", scope)),
                "division": bool(re.search(r"사업부|부문", scope)),
                "product": bool(re.search(r"제품|서비스", scope)), "unknown": False,
            }[m["scope"]]
            cues = {"material": r"중요한|중대한|중요합니다|중대합니다|유의적인", "limited": r"경미|미미"}
            if (row["status"] not in {"accepted", "held"} or m["value"] == "unrated" or m["review_reasons"]
                    or not scoped or not re.search(r"\d{4}년|당기|보고기간|회계연도", period)
                    or (row["period_quote"] is not None and period != row["period_quote"])
                    or not re.search(r"매출|영업이익|순이익|현금흐름|원가|비용|자산|부채", quote)
                    or not re.search(r"매출|영업이익|순이익|현금흐름|원가|비용|자산|부채", m["mechanism_quote"] or "")
                    or re.search(r"아니|않|없|미확인|불확실", quote)
                    or not re.search(cues[m["value"]], quote)
                    or re.search(cues["limited" if m["value"] == "material" else "material"], quote)):
                _fail()
        elif m["value"] != "unrated":
            _fail()
    if "comparison" in out:
        out["comparison"] = _judgment_comparison(out["comparison"], out)
    # Optional history describes this judgment; it is not a new judgment.
    fingerprint = {k: v for k, v in out.items() if k not in {"revision", "read_revision", "comparison"}}
    out["revision"] = _digest(["public-company-judgment-v1", c["revision"], fingerprint])
    out["read_revision"] = int(out["revision"][:13], 16) + 1
    if "comparison" in out:
        out["comparison"]["current"]["review_revision"] = out["revision"]
    return out


def _judgment_envelope(projection):
    _keys(projection, {"schema", "judgments"})
    if (projection["schema"] != _JUDGMENT_SCHEMA or type(projection["judgments"]) is not list
            or len(projection["judgments"]) > MAX_COMPANY_JUDGMENTS
            or len(json.dumps(projection, ensure_ascii=False, allow_nan=False).encode()) > 200_000):
        _fail()
    return projection["judgments"]


def _judgment_sources(documents):
    """Closed raw-document indexing only, not offline semantic revalidation."""
    if type(documents) is not list or not 1 <= len(documents) <= 8:
        _fail()
    if len(json.dumps(documents, ensure_ascii=False, allow_nan=False).encode()) > 80_000:
        _fail()
    sources = {}
    for doc in documents:
        optional = {"resolved_relations"} if type(doc) is dict and "resolved_relations" in doc else set()
        _keys(doc, {"source_id", "issuer_id", "issuer_name", "url", "as_of", "text", "counterparties"} | optional)
        match = _SOURCE.fullmatch(doc["source_id"]) if type(doc["source_id"]) is str else None
        if (not match or doc["source_id"] in sources
                or doc["url"] != "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=" + match[1]
                or _day(doc["as_of"]) != f"{match[1][:4]}-{match[1][4:6]}-{match[1][6:8]}"
                or doc["as_of"] > date.today().isoformat()):
            _fail()
        _entity(doc["issuer_id"])
        _text(doc["issuer_name"], 160)
        _text(doc["text"], 600)
        parties = doc["counterparties"]
        if type(parties) is not list or not 1 <= len(parties) <= 8:
            _fail()
        ids, names = {doc["issuer_id"]}, {_legal_name(doc["issuer_name"]).casefold()}
        if "" in names:
            _fail()
        for party in parties:
            _keys(party, {"id", "name"})
            identifier = _entity(party["id"])
            name = _legal_name(_text(party["name"], 160)).casefold()
            if identifier in ids or not name or name in names:
                _fail()
            ids.add(identifier)
            names.add(name)
        relations = doc.get("resolved_relations", [])
        if type(relations) is not list or len(relations) > 24:
            _fail()
        for relation in relations:
            _keys(relation, {"counterparty_id", "role"})
            _entity(relation["counterparty_id"])
            _enum(relation["role"], {"customer", "supplier"})
        sources[doc["source_id"]] = {**doc, "source_version": _digest(doc)}
    return sources


def project_public_company_judgments(projection, candidates, *, source_documents=None):
    """Offline export only, AFTER project_company_judgments(raw, receipts).

    Preserve the local UI shape, omit individually unsafe/stale bindings, and
    replace private free prose with fixed labels. No receipt authenticity or
    source semantics can be established here; that is the offline producer's
    duty. The public revision binds the FULL current candidate revision.
    Fresh local rows require source_documents to carry the canonical original
    document digest, never a digest inferred from the quote. Prepared public
    wire may be read without documents; pass current documents on re-export
    to withdraw any changed document, including outside the candidate quote.
    """
    try:
        rows, indexed = _judgment_envelope(projection), _judgment_candidates(candidates)
        sources = _judgment_sources(source_documents) if source_documents is not None else None
        ids = [r.get("record_id") for r in rows if type(r) is dict and type(r.get("record_id")) is str]
        output = []
        for row in rows:
            try:
                if type(row) is not dict or ids.count(row.get("record_id")) != 1:
                    continue
                is_public = row.get("reason") == _JUDGMENT_REASON and row.get("review_trigger") == _JUDGMENT_TRIGGER
                prepared = row
                if not is_public:
                    if sources is None or row.get("source_id") not in sources:
                        continue
                    version = sources[row["source_id"]]["source_version"]
                    if "source_version" in row and row["source_version"] != version:
                        continue
                    prepared = {**row, "source_version": version}
                value = _public_judgment(prepared, indexed, source_documents=sources, public_wire=is_public)
                # Retention is not re-signing: an already-public judgment must
                # still match its full candidate-bound public fingerprint.
                if is_public and value != row:
                    continue
                output.append(value)
            except (ValueError, TypeError, KeyError, OverflowError, RecursionError, UnicodeError):
                continue
        return {"schema": _JUDGMENT_SCHEMA, "judgments": output}
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError, UnicodeError):
        raise ValueError("invalid-public-company-judgments") from None


def validate_public_company_judgments(projection, candidates):
    """Strict public-wire check: raw local projections must not enter runtime."""
    sanitized = project_public_company_judgments(projection, candidates)
    if sanitized != projection:
        raise ValueError("invalid-public-company-judgments")
    return sanitized


def _optional_company_judgments(projection, candidates):
    try:
        rows = _judgment_envelope(projection)
        indexed = _judgment_candidates(candidates)
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError, UnicodeError):
        return {"schema": _JUDGMENT_SCHEMA, "judgments": []}, {"status": "rejected"}
    output = []
    ids = [r.get("record_id") for r in rows if type(r) is dict and type(r.get("record_id")) is str]
    for row in rows:
        try:
            if type(row) is not dict or ids.count(row.get("record_id")) != 1:
                continue
            value = _public_judgment(row, indexed, public_wire=True)
            if value == row:
                output.append(value)
        except (ValueError, TypeError, KeyError, OverflowError, RecursionError, UnicodeError):
            continue
    rejected = len(rows) - len(output)
    return {"schema": _JUDGMENT_SCHEMA, "judgments": output}, {
        "status": ("partial" if output else "rejected") if rejected else "ready",
        "input": len(rows), "accepted": len(output), "rejected": rejected,
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
    _keys(payload, {"schema", "candidates", "coverage"}
          | ({"company_judgments"} if type(payload) is dict and "company_judgments" in payload else set()))
    # Validate/size the base independently: a broken optional judgment lane
    # must not discard otherwise valid candidates (including legacy files).
    payload = {key: payload[key] for key in ("schema", "candidates", "coverage")}
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
    """Base candidates are atomic; optional unsafe judgments are isolated."""
    try:
        prepared = _validate(payload, catalog)
        if "company_judgments" in payload:
            prepared["company_judgments"], _ = _optional_company_judgments(
                payload["company_judgments"], prepared["candidates"])
        return prepared
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError, UnicodeError):
        raise ValueError(_ERROR) from None


def project_public_ai_review(payload, catalog, selected_ids):
    """Return at most 40 matching candidates, preserving input order and totals."""
    try:
        prepared = _validate(payload, catalog)
        if type(selected_ids) not in (list, tuple, set, frozenset):
            _fail()
        selected = {_entity(identifier) for identifier in selected_ids}
        if len(selected) != len(selected_ids):
            _fail()
        matching = [row for row in prepared["candidates"]
                    if row["issuer_id"] in selected or row["counterparty_id"] in selected]
        result = {"schema": "local-ai-review-v1", "candidates": matching[:MAX_RETURNED],
                "coverage": {**prepared["coverage"], "matched": len(matching),
                             "returned": min(len(matching), MAX_RETURNED),
                             "omitted": max(len(matching) - MAX_RETURNED, 0)}}
        if "company_judgments" in payload:
            judgments, coverage = _optional_company_judgments(payload["company_judgments"], prepared["candidates"])
            returned = {row["id"] for row in result["candidates"]}
            # Counterparty selection must never disclose another issuer's
            # judgment. Also require the associated candidate to be delivered.
            rows = [row for row in judgments["judgments"]
                    if row["company_id"] in selected and row["record_id"] in returned]
            result["company_judgments"] = {"schema": _JUDGMENT_SCHEMA, "judgments": rows}
            result["coverage"]["company_judgments"] = {**coverage, "returned": len(rows)}
        return result
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError, UnicodeError):
        raise ValueError(_ERROR) from None
