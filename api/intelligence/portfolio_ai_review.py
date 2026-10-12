"""Offline public-response replay for the loopback review, never confirmed edges.

No ledger, credentials, network or member storage is accessed here. An explicit
review input carries the retained public document and saved model answer, so the
current validator can recheck provenance without spending or changing caches.
"""
from copy import deepcopy
import json

from .portfolio_ai_fallback import (
    _digest, _ambiguous_party_name, validate_document, replay_answer,
)
from .portfolio_filing_excerpts import _legal_name


def prepare_review_candidates(payload, catalog):
    if (type(payload) is not dict or set(payload) != {"schema", "entries"}
            or payload["schema"] != "local-ai-review-input-v1"
            or type(payload["entries"]) is not list or len(payload["entries"]) > 100
            or len(json.dumps(payload, ensure_ascii=False).encode()) > 2_000_000):
        raise ValueError("invalid-local-ai-review")
    names = {}
    for company in catalog:
        key = f"{company['market']}:{company['ticker']}"
        if key in names and names[key] != company["name"]:
            raise ValueError("ambiguous-local-ai-catalog")
        names[key] = company["name"]
    candidates, seen, rejected, count = [], set(), 0, 0
    for entry in payload["entries"]:
        if type(entry) is not dict or set(entry) != {"document", "answer"}:
            raise ValueError("invalid-local-ai-entry")
        doc = validate_document(entry["document"])
        parties = {doc["issuer_id"]: doc["issuer_name"],
                   **{p["id"]: p["name"] for p in doc["counterparties"]}}
        if any(key not in names or _legal_name(name) != _legal_name(names[key])
               for key, name in parties.items()):
            raise ValueError("unbound-local-ai-company")
        answer = entry["answer"]
        batch = replay_answer(answer, doc)
        count += len(answer["claims"] if "claims" in batch else answer["candidates"])
        rejected += len(batch["rejected"])
        if "claims" in batch:
            # One stable source/company/role node, including contradictory claims
            # in its detail. State/wording revisions must not orphan user notes.
            groups = {}
            for claim in batch["claims"]:
                if _ambiguous_party_name(claim["quote"], parties[claim["counterparty_id"]], names.values()):
                    rejected += 1
                    continue
                identifier = "automatic:ai:" + _digest([claim["source_id"], claim["issuer_id"],
                                                        claim["counterparty_id"], claim["role"]])[:24]
                row = groups.setdefault(identifier, {
                    **{k: claim[k] for k in ("issuer_id", "counterparty_id", "role", "quote", "source_id", "url", "as_of")},
                    "id": identifier, "issuer_name": parties[claim["issuer_id"]],
                    "counterparty_name": parties[claim["counterparty_id"]], "status": "ai_candidate",
                    "verification": "unreviewed-model-extraction", "evidence_scope": "unspecified",
                    "current_validity": "not-inferred", "claims": []})
                row["claims"].append({k: deepcopy(claim[k]) for k in (
                    "claim_kind", "directness", "claim_state", "quote", "context", "scope_quote", "channel_quote",
                    "counter_evidence_quotes", "missing_evidence", "review_reasons", "decision", "degree", "degree_basis")})
            for identifier, row in groups.items():
                if identifier in seen:
                    rejected += len(row["claims"])
                    continue
                seen.add(identifier)
                row["revision"] = _digest(row)
                candidates.append(row)
            continue
        for row in batch["candidates"]:
            # Bind quoted occurrences against the supplied public catalogue too,
            # not only a historical model request's possibly incomplete shortlist.
            if _ambiguous_party_name(row["quote"], parties[row["counterparty_id"]], names.values()):
                rejected += 1
                continue
            identifier = "automatic:ai:" + _digest([row["source_id"], row["issuer_id"],
                                                   row["counterparty_id"], row["role"]])[:24]
            candidate = {key: row[key] for key in ("issuer_id", "counterparty_id", "role", "quote",
                                                   "source_id", "url", "as_of", "status", "verification")}
            candidate.update(id=identifier, issuer_name=parties[row["issuer_id"]],
                             counterparty_name=parties[row["counterparty_id"]],
                             evidence_scope=row.get("evidence_scope", "unspecified"),
                             current_validity="not-inferred")
            if "context" in row:
                candidate["context"] = deepcopy(row["context"])
            candidate["revision"] = _digest(candidate)
            if identifier in seen:
                rejected += 1
                continue
            seen.add(identifier)
            candidates.append(candidate)
    candidates.sort(key=lambda row: (row["as_of"], row["id"]), reverse=True)
    return {"schema": "local-ai-review-v1", "candidates": candidates,
            "coverage": {"input": count, "accepted": len(candidates), "rejected": rejected,
                         "skipped": count - len(candidates) - rejected}}


def project_review_candidates(prepared, selected_ids):
    selected = set(selected_ids)
    matching = [row for row in prepared["candidates"]
                if row["issuer_id"] in selected or row["counterparty_id"] in selected]
    return {"schema": "local-ai-review-v1", "candidates": deepcopy(matching[:40]),
            "coverage": {**prepared["coverage"], "matched": len(matching),
                         "returned": min(len(matching), 40), "omitted": max(len(matching) - 40, 0)}}
