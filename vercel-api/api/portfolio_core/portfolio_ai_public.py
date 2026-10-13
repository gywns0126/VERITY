"""Closed public AI-candidate artifact and selected-company projection; no I/O.

The offline producer owns original-document and semantic verification. This
boundary checks the prepared wire contract, public text, catalogue bindings and
content hashes only. Hashes detect inconsistency, not publisher authenticity.
No model, fallback, ledger, credentials or network modules are imported here.
"""
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
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
    "review_trigger", "economic_v2", "period_context_v2", "period_context_v3", "status", "review_reasons", "display",
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


def _kr_contract_today():
    """KR contract date-only evidence uses the Seoul calendar, not host UTC."""
    return datetime.now(timezone(timedelta(hours=9))).date().isoformat()


def _review_label(row, published, *, today=None):
    status = _enum(row["status"], _REVIEW_LABELS)
    if status == "pending":
        if row["reviewed_on"] is not None or row["review_reason"] is not None:
            _fail()
    elif (type(row["review_reason"]) is not str or not row["review_reason"].strip()
          or not published <= _day(row["reviewed_on"]) <= (today if today is not None else date.today().isoformat())):
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


def _judgment_comparison(value, row, *, today=None):
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
        if not row["published_on"] <= _day(snapshot["assessed_as_of"]) <= (today if today is not None else date.today().isoformat()):
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


def _contract_proof_facts(facts, filed_on):
    """Closed source-free projection; never invent raw metadata to validate it."""
    from .portfolio_contract_facts import (
        _quoted_field, _quoted_day, _validate_financial_terms,
        _validate_revenue_basis, _revenue_basis,
    )
    _keys(facts, {"contract", "correction"})
    contract = facts["contract"]
    optional = set(contract) & {"financial_terms", "financial_notes", "revenue_basis"} if type(contract) is dict else set()
    _keys(contract, {"type", "name", "counterparty", "period", "signed_on"} | optional)
    for key in ("type", "name", "counterparty", "signed_on"):
        _quoted_field(contract[key])
    period = contract["period"]
    _keys(period, {"label", "start", "end"}); _text(period["label"], 2000)
    for key in ("start", "end"):
        _quoted_field(period[key])
    if "financial_terms" in contract:
        _validate_financial_terms(contract["financial_terms"])
    if "financial_notes" in contract:
        notes = _quoted_field(contract["financial_notes"])
        if not re.fullmatch(r"(?:9|10)\.\s*기타\s*투자판단(?:에\s*참고할\s*사항|과\s*관련한\s*중요사항)", notes["label"]):
            _fail()
    if "revenue_basis" in contract:
        _validate_revenue_basis(contract["revenue_basis"], filed_on)
        if ("recent_revenue" not in contract.get("financial_terms", {})
                or "financial_notes" not in contract
                or _revenue_basis(contract["financial_notes"]["value"]) != contract["revenue_basis"]):
            _fail()
    correction = facts["correction"]
    if correction is not None:
        _keys(correction, {"corrected_on", "related_filing_date", "reason", "changes"})
        for key in ("corrected_on", "related_filing_date", "reason"):
            quoted = _quoted_field(correction[key])
            if key != "reason" and _quoted_day(quoted["value"]).isoformat() > _day(filed_on):
                _fail()
        changes = correction["changes"]
        if type(changes) is not list or not 1 <= len(changes) <= 20:
            _fail()
        for change in changes:
            _keys(change, {"field", "before", "after"})
            for value in change.values():
                _text(value, 2000)


def _contract_event_revision(event):
    """Selection-independent binding of the existing validated event projection."""
    fields = ("id", "root_receipt", "participants", "signed_on", "title", "as_of", "current_status")
    docs = []
    for d in event["documents"]:
        f = d["contract_facts"]
        _keys(f, {"schema", "receipt_no", "issuer", "filing", "contract", "correction",
                  "counterparty_company_id", "verified_common_event", "current_contract_status"})
        _keys(f["issuer"], {"id", "name"}); _keys(f["filing"], {"title", "filed_on"})
        _entity(f["issuer"]["id"]); _text(f["issuer"]["name"], 160)
        from .portfolio_contract_facts import _contract_title, _filing_title, _is_correction_title
        if (f["schema"] != "dart-contract-fact-v1" or not re.fullmatch(r"[0-9]{14}", f["receipt_no"])
                or d["id"] != "DART:" + f["receipt_no"] or d["url"] != "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=" + f["receipt_no"]
                or d["company_ids"] != [f["issuer"]["id"]]
                or f["issuer"]["id"] != event["participants"][0]["id"]
                or _day(f["filing"]["filed_on"]) != d["as_of"]
                or _contract_title(f["filing"]["title"]) != "단일판매공급계약체결"
                or _contract_title(_filing_title(d["title"])) != _contract_title(f["filing"]["title"])
                or _is_correction_title(d["title"]) != (f["correction"] is not None)
                or f["counterparty_company_id"] is not None or f["verified_common_event"] is not False
                or f["current_contract_status"] != "not-inferred"):
            _fail()
        _contract_proof_facts({"contract": f["contract"], "correction": f["correction"]}, d["as_of"])
        docs.append({k: d[k] for k in ("id", "url", "title", "as_of", "company_ids", "contract_facts")})
    return _digest({**{k: event[k] for k in fields}, "documents": docs,
                    "termination_notices": event.get("termination_notices", [])})


def validated_contract_sources(artifact):
    """Current canonical facts only; invalid/duplicate receipts cannot back review."""
    from .portfolio_contract_facts import validate_contract_fact
    values = artifact.get("contract_facts", []) if type(artifact) is dict else []
    if type(values) is not list or len(values) > 1000:  # Existing fact-lane bound.
        return {}
    out, seen, duplicates = {}, set(), set()
    for raw in values:
        receipt = raw.get("receipt_no") if type(raw) is dict else None
        if type(receipt) is not str:
            continue
        if receipt in seen:
            duplicates.add(receipt)
        seen.add(receipt)
        try:
            out[receipt] = validate_contract_fact(raw)
        except (ValueError, KeyError, TypeError, OverflowError, RecursionError, UnicodeError):
            continue
    for receipt in duplicates:
        out.pop(receipt, None)
    return out


def _contract_events(value):
    if value is None:
        return {}
    values = list(value["events"].values()) if "events" in value else value["items"]
    if type(values) is not list or len(values) > MAX_CANDIDATES:
        _fail()
    out = {}
    for e in values:
        issuer, party = e["participants"]
        if (e["kind"] != "reported-contract" or e["identity_basis"] != "explicit-contract-parties"
                or e["current_status"] != "not-inferred" or issuer["role"] != "supplier"
                or party["role"] != "counterparty" or issuer["id"] == party["id"]
                or e["company_ids"] != [issuer["id"], party["id"]]
                or e["id"] != f"contract:{issuer['id']}:{e['root_receipt']}" or e["id"] in out):
            _fail()
        _entity(issuer["id"]); _entity(party["id"])
        out[e["id"]] = e
    return out


def _contract_denominator(contract, denominator, published):
    """Issuer section 2 only; section 3 counterparty sales are not its denominator."""
    _keys(denominator, {"year", "scope", "quote"})
    notes = contract.get("financial_notes", {}).get("value", "")
    prefix = r"(?:상기\s*['\"‘’]?2\.\s*(?:계약내역의?\s*)?|상기\s*계약내역의\s*)최근\s*매출액(?:\(원\))?['\"‘’]?"
    basis = r"(?:\s*및\s*계약상대방의\s*최근\s*매출액)?\s*(?:은|는)\s*(?:당사의\s*)?((?:19|20)\d{2})년(?:도|말)?\s*(연결|별도|개별)\s*재무제표\s*기준"
    matches = list(re.finditer(prefix + basis, notes))
    if (type(denominator["year"]) is not int or denominator["year"] > int(published[:4])
            or denominator["scope"] not in {"consolidated", "separate"} or denominator["quote"] != notes
            or len(matches) != 1 or re.search(r"아닌|아니|않|미확인", notes)
            or int(matches[0][1]) != denominator["year"]
            or ("consolidated" if matches[0][2] == "연결" else "separate") != denominator["scope"]):
        _fail()


def _public_contract_judgment(row, events, sources=None, *, public_wire=False):
    """Only prevalidated contract events, never an arbitrary record-ID escape."""
    _keys(row, _JUDGMENT_FIELDS | {"source_version", "core_selection", "comparison"})
    e, c = events[row["record_id"]], row["core_selection"]
    today = _kr_contract_today()
    _keys(c, {"basis", "event_revision", "source_receipt", "body_sha256", "fact_revision", "checked_on",
              "effective_start", "effective_end", "review_scope", "materiality", "change_kind", "facts", "reason", "denominator"})
    if (c["basis"] != "contract-announcement" or c["review_scope"] != "provided-contract-family-only"
            or c["materiality"] != "material" or row["status"] != "accepted"
            or row["degree"] != "unrated" or row["impact"] != {"direction": "unknown", "channel": "unknown", "condition": None}
            or row["review_reasons"] or row["missing_evidence"] != ["counter_evidence_not_searched"]
            or e.get("termination_notices") or c["event_revision"] != _contract_event_revision(e)
            or row["company_id"] != e["participants"][0]["id"]
            or row["counterparty_id"] != e["participants"][1]["id"]):
        _fail()
    for h in (c["event_revision"], c["body_sha256"], c["fact_revision"], row["source_version"], row["revision"]):
        _hash_value(h)
    matches = [d for d in e["documents"] if d["id"] == "DART:" + c["source_receipt"]]
    if len(matches) != 1:
        _fail()
    d = matches[0]; f = d["contract_facts"]; contract = f["contract"]
    if len([v for v in e["documents"] if v["as_of"] == e["as_of"]]) != 1:
        _fail()  # Never choose between competing latest-date originals.
    _contract_proof_facts(c["facts"], row["published_on"])
    if (c["facts"] != {"contract": contract, "correction": f["correction"]}
            or row["source_id"] != "source:dart:" + c["source_receipt"]
            or row["source_url"] != d["url"] or row["published_on"] != d["as_of"]
            or e["as_of"] != d["as_of"] or c["fact_revision"] != row["source_version"]
            or row["quote"] != contract["name"]["value"]
            or row["scope_quote"] != row["quote"] or row["period_quote"] != c["effective_start"] + " ~ " + c["effective_end"]
            or row["base_read_revision"] != int(c["event_revision"][:13], 16) + 1
            or type(row["read_revision"]) is not int or row["read_revision"] != int(row["revision"][:13], 16) + 1):
        _fail()
    from .portfolio_contract_facts import _quoted_day
    if (c["effective_start"] != _quoted_day(contract["period"]["start"]["value"]).isoformat()
            or c["effective_end"] != _quoted_day(contract["period"]["end"]["value"]).isoformat()
            or not row["published_on"] <= _day(c["checked_on"]) == _day(row["reviewed_on"]) <= today
            or not _day(c["effective_start"]) <= c["checked_on"] <= _day(c["effective_end"])):
        _fail()
    financial = contract["financial_terms"]
    if not {"amount", "recent_revenue", "revenue_ratio"} <= set(financial) or not contract.get("financial_notes"):
        _fail()
    _contract_denominator(contract, c["denominator"], row["published_on"])
    if c["change_kind"] == "new-contract":
        if f["correction"] is not None or "신규 계약" not in row["quote"]:
            _fail()
    elif c["change_kind"] == "amount-amendment":
        if not f["correction"] or not any("계약금액" in v["field"] and v["before"] != v["after"] for v in f["correction"]["changes"]):
            _fail()
        if d.get("event_lineage", {}).get("root_receipt") != e["root_receipt"]:
            _fail()
    else:
        _fail()
    if sources is not None:
        from .portfolio_contract_facts import validate_contract_fact
        original = validate_contract_fact(sources[c["source_receipt"]])
        if (_digest(original) != row["source_version"] or original["source"]["content_sha256"] != c["body_sha256"]
                or original["issuer"]["id"] != row["company_id"]
                or original["contract"] != contract or original["correction"] != f["correction"]):
            _fail()
    else:
        # Prepared fingerprints are not proof that the current canonical
        # original still exists. Missing raw facts withdraw this row only.
        _fail()
    out = deepcopy(row)
    out["reason"] = _JUDGMENT_REASON; out["review_trigger"] = _JUDGMENT_TRIGGER
    out["review_reason"] = _review_label(row, row["published_on"], today=today)
    out["core_selection"]["reason"] = "제공된 계약 원문 범위에서 발표의 규모·노출·변경을 검수했습니다. 실제 이행과 전체 후속 공시 부재는 확인하지 않았습니다."
    _text(row["quote"], 600)
    for value in (row["reason"], row["review_trigger"], c["reason"]):
        if type(value) is not str or not value.strip():
            _fail()  # Validate presence; only fixed labels leave this boundary.
    fingerprint = {k: v for k, v in out.items() if k not in {"revision", "read_revision", "comparison"}}
    out["revision"] = _digest(["public-company-judgment-v1", c["event_revision"], fingerprint])
    out["read_revision"] = int(out["revision"][:13], 16) + 1
    comparison = deepcopy(out["comparison"])
    comparison["current"]["review_revision"] = out["revision"]
    out["comparison"] = _judgment_comparison(comparison, out, today=today)
    # These receipts do not manufacture a prior AI judgment or compare grades.
    if out["comparison"]["status"] not in {"first", "unavailable"}:
        _fail()
    return out


def _public_judgment(row, candidates, *, source_documents=None, public_wire=False,
                     period_archives=None, issuer_registry=None):
    optional = {k for k in ("economic_v2", "period_context_v2", "period_context_v3", "comparison", "core_selection") if type(row) is dict and k in row}
    _keys(row, _JUDGMENT_FIELDS | {"source_version"} | optional)
    if "period_context_v2" in row and "period_context_v3" in row:
        _fail()
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
    if "period_context_v3" in row:
        try:
            from .portfolio_reported_period import (
                validate_reported_customer_period, validate_reported_period_projection,
            )
        except ImportError:
            _fail()
        # 공개 필드는 늘리지 않고 candidate의 고객명을 원문 표 행에 결속한다.
        helper_row = {**row, "counterparty_name": c["counterparty_name"]}
        context = row["period_context_v3"]
        checked = validate_reported_period_projection(context, helper_row)
        if checked != context:
            _fail()
        if source_documents is not None:
            original = {key: value for key, value in source.items() if key != "source_version"}
            checked = validate_reported_customer_period(
                context, original, helper_row, archives=period_archives, issuer_registry=issuer_registry)
            if checked != context:
                _fail()
        elif not public_wire:
            _fail()
        # 원문 재검증 없는 prepared wire 검사는 내부 결속이며 진위 인증이 아니다.
        out["period_context_v3"] = checked
        period_support = _text(context["period_quote"], 600)
    elif "period_context_v2" in row:
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
    if "core_selection" in out:
        try:
            out["core_selection"] = _public_core_selection(out["core_selection"], out, c, source_documents)
        except (ValueError, TypeError, KeyError):
            # A missing prior source or bad optional core proof must not remove
            # the otherwise valid scoped judgment during fresh export.
            out.pop("core_selection")
    # Optional history describes this judgment; it is not a new judgment.
    fingerprint = {k: v for k, v in out.items() if k not in {"revision", "read_revision", "comparison"}}
    out["revision"] = _digest(["public-company-judgment-v1", c["revision"], fingerprint])
    out["read_revision"] = int(out["revision"][:13], 16) + 1
    if "comparison" in out:
        out["comparison"]["current"]["review_revision"] = out["revision"]
    return out


def _core_date_pattern(day):
    """Match only this already validated day; never rewrite source/review text."""
    year, month, number = day.split("-")
    month = "0?" + str(int(month)) if int(month) < 10 else month
    number = "0?" + str(int(number)) if int(number) < 10 else number
    return rf"(?<![0-9])(?:{re.escape(day)}(?![0-9])|{year}년\s*{month}월\s*{number}일(?=\s|부터|까지|~|[,.!?]|$))"


def _public_core_selection(value, row, candidate, sources):
    """Closed existing-v1 extension, only after offline receipt/source review.

    Fresh export requires both original documents. Prepared wire binds these
    minimal quotes/digests in the existing public fingerprint, never raw AI or
    arbitrary reviewer prose. This boundary does not authenticate the reviewer.
    """
    _keys(value, {"checked_on", "effective_start", "effective_end", "current_quote",
                  "period_quote", "change_quote", "reason", "candidate_revision", "previous"})
    value = deepcopy(value)
    m = row.get("economic_v2", {}).get("materiality", {})
    p = value["previous"]
    _keys(p, {"record_id", "source_id", "source_url", "published_on", "source_version", "review_revision", "quote"})
    match = _SOURCE.fullmatch(p["source_id"]) if type(p["source_id"]) is str else None
    if (row["status"] != "accepted" or m.get("status") != "accepted" or m.get("value") != "material"
            or _hash_value(value["candidate_revision"]) != candidate["revision"]
            or not match or p["source_url"] != "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=" + match[1]
            or not re.fullmatch(r"automatic:ai:[a-f0-9]{24}", p["record_id"])
            or _day(p["published_on"]).replace("-", "") != match[1][:8]
            or p["published_on"] > row["published_on"]):
        _fail()
    _hash_value(p["source_version"]); _hash_value(p["review_revision"])
    checked, start, end = (_day(value[k]) for k in ("checked_on", "effective_start", "effective_end"))
    if not checked <= row["published_on"] <= row["reviewed_on"] <= date.today().isoformat() or not start <= checked <= end:
        _fail()
    for key in ("current_quote", "period_quote", "change_quote"):
        q = _text(value[key], 600)
        if not re.search(r"[.!?]$", q) or not m["scope_quote"] or m["scope_quote"] not in q or candidate["counterparty_name"] not in q:
            _fail()
    _text(p["quote"], 600)
    checked_pattern, start_pattern, end_pattern = map(_core_date_pattern, (checked, start, end))
    if (value["change_quote"] != m["quote"] or p["quote"] == value["change_quote"]
            or not re.search(checked_pattern, value["current_quote"]) or "현재" not in value["current_quote"]
            or not re.search(r"(?:공급|납품|구매|매입|이행)하고\s+있습니다", value["current_quote"])
            or not re.search(start_pattern + r"(?:부터\s+" + end_pattern + r"까지|\s*~\s*" + end_pattern + r"\s+기간에)", value["period_quote"])
            or not re.search(r"유효|효력", value["period_quote"])
            or not re.search(checked_pattern, value["change_quote"])
            or not re.search(r"증가|감소|확대|축소|중단|재개", value["change_quote"])):
        _fail()
    if sources is not None:
        current, previous = sources.get(row["source_id"]), sources.get(p["source_id"])
        if (not current or not previous or previous["source_version"] != p["source_version"]
                or previous["issuer_id"] != row["company_id"]
                or previous["url"] != p["source_url"] or previous["as_of"] != p["published_on"]
                or previous["text"].count(p["quote"]) != 1
                or not any(v["id"] == row["counterparty_id"] for v in previous["counterparties"])
                or any(current["text"].count(value[key]) != 1 for key in ("current_quote", "period_quote", "change_quote"))):
            _fail()
    if type(value["reason"]) is not str or not value["reason"].strip():
        _fail()
    value["reason"] = "같은 회사·거래·경제 범위의 현재 확인과 전후 경제 변화를 별도로 검수했습니다."
    return value


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


def project_public_company_judgments(projection, candidates, *, source_documents=None,
                                    contract_events=None, contract_sources=None,
                                    period_archives=None, issuer_registry=None):
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
        events = _contract_events(contract_events)
        sources = _judgment_sources(source_documents) if source_documents is not None else None
        ids = [r.get("record_id") for r in rows if type(r) is dict and type(r.get("record_id")) is str]
        output = []
        for row in rows:
            try:
                if type(row) is not dict or ids.count(row.get("record_id")) != 1:
                    continue
                is_public = row.get("reason") == _JUDGMENT_REASON and row.get("review_trigger") == _JUDGMENT_TRIGGER
                if row.get("record_id") in events:
                    value = _public_contract_judgment(row, events, contract_sources, public_wire=is_public)
                    if not is_public or value == row:
                        output.append(value)
                    continue
                prepared = row
                if not is_public:
                    if sources is None or row.get("source_id") not in sources:
                        continue
                    version = sources[row["source_id"]]["source_version"]
                    if "source_version" in row and row["source_version"] != version:
                        continue
                    prepared = {**row, "source_version": version}
                value = _public_judgment(prepared, indexed, source_documents=sources, public_wire=is_public,
                                         period_archives=period_archives, issuer_registry=issuer_registry)
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


def validate_public_company_judgments(projection, candidates, *, contract_events=None, contract_sources=None):
    """Strict public-wire check: raw local projections must not enter runtime."""
    sanitized = project_public_company_judgments(projection, candidates, contract_events=contract_events,
                                                contract_sources=contract_sources)
    if sanitized != projection:
        raise ValueError("invalid-public-company-judgments")
    return sanitized


def _optional_company_judgments(projection, candidates, contract_events=None, contract_sources=None):
    try:
        rows = _judgment_envelope(projection)
        indexed = _judgment_candidates(candidates)
        events = _contract_events(contract_events)
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError, UnicodeError):
        return {"schema": _JUDGMENT_SCHEMA, "judgments": []}, {"status": "rejected"}
    output = []
    ids = [r.get("record_id") for r in rows if type(r) is dict and type(r.get("record_id")) is str]
    for row in rows:
        try:
            if type(row) is not dict or ids.count(row.get("record_id")) != 1:
                continue
            value = (_public_contract_judgment(row, events, contract_sources, public_wire=True) if row.get("record_id") in events
                     else _public_judgment(row, indexed, public_wire=True))
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


def validate_public_ai_review(payload, catalog, *, contract_events=None, contract_sources=None):
    """Base candidates are atomic; optional unsafe judgments are isolated."""
    try:
        prepared = _validate(payload, catalog)
        if "company_judgments" in payload:
            prepared["company_judgments"], _ = _optional_company_judgments(
                payload["company_judgments"], prepared["candidates"], contract_events, contract_sources)
        return prepared
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError, UnicodeError):
        raise ValueError(_ERROR) from None


def project_public_ai_review(payload, catalog, selected_ids, *, contract_events=None, contract_sources=None):
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
            judgments, coverage = _optional_company_judgments(payload["company_judgments"], prepared["candidates"],
                                                             contract_events, contract_sources)
            returned = {row["id"] for row in result["candidates"]}
            try:
                returned.update(_contract_events(contract_events))
            except (ValueError, KeyError, TypeError):
                pass  # Optional contract review never breaks base candidates.
            # Counterparty selection must never disclose another issuer's
            # judgment. Also require the associated candidate to be delivered.
            rows = [row for row in judgments["judgments"]
                    if row["company_id"] in selected and row["record_id"] in returned]
            result["company_judgments"] = {"schema": _JUDGMENT_SCHEMA, "judgments": rows}
            result["coverage"]["company_judgments"] = {**coverage, "returned": len(rows)}
        return result
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError, UnicodeError):
        raise ValueError(_ERROR) from None
