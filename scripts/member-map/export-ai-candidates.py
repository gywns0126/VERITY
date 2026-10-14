#!/usr/bin/env python3
"""Replay retained public answers into the fixed public candidate artifact.

No network, key, ledger access, paid requests or publication. The explicit
input is revalidated against its preserved document and current public catalog;
only the closed candidate projection is written, never the raw model answer.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "vercel-api" / "api"))

from api.intelligence.portfolio_ai_review import prepare_review_candidates
from api.intelligence.portfolio_ai_public import validate_public_ai_review
from api.intelligence.portfolio_public_sources import load_public_sources, project_public_sources

def load_ai_review(path):
    # Reuse the existing bounded replay reader without importing the local web
    # server (and its unrelated collection/runtime dependencies) into CI.
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, 'rb') as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > 2_000_000:
            raise ValueError('invalid-local-ai-review-file')
        raw = handle.read(2_000_001)
    if len(raw) > 2_000_000:
        raise ValueError('invalid-local-ai-review-file')
    def unique(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError('duplicate-local-ai-review-field')
            value[key] = item
        return value
    return json.loads(raw, object_pairs_hook=unique)


def _load_worker():
    # Import definitions only: never invoke main(), settings, credentials or the
    # budget ledger. The module path is fixed, not supplied by a CLI argument.
    spec = importlib.util.spec_from_file_location(
        "member_map_export_worker", Path(__file__).with_name("enrich-public-relations.py"))
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)
    return worker


def _worker_payloads():
    worker = _load_worker()
    # The worker validates each fixed source and resolves exact-document context
    # precedence inside the immutable archives. Latest never overrides that union.
    archived = worker.read_archived_answers()
    latest = worker.read_existing_review()
    entries = [*archived.values(), *latest.values()]
    if len(entries) > 203:  # legacy100 + two contexts + one v2 capture + latest100
        raise ValueError("invalid-worker-ai-review-size")
    return [{"schema": "local-ai-review-input-v1", "entries": [entry]} for entry in entries]


def _read_judgment_input(path, *, limit=256_000, period_original=False):
    path = Path(path)
    if period_original:
        body = _read_period_file(path, limit)
    else:
        if any(p.is_symlink() for p in (path, *path.parents)) or not path.is_file():
            raise ValueError("invalid-public-judgment-input")
        with path.open("rb") as stream:
            body = stream.read(limit + 1)
    if len(body) > limit:
        raise ValueError("invalid-public-judgment-input")
    def unique(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError("invalid-public-judgment-input")
            value[key] = item
        return value
    def invalid_constant(_):
        raise ValueError("invalid-public-judgment-input")
    return json.loads(body, object_pairs_hook=unique, parse_constant=invalid_constant)


def _read_period_file(path, limit):
    parts = Path(path).absolute().parts
    if len(parts) < 2 or ".." in parts:
        raise ValueError("invalid-public-period-path")
    # 부모 inode를 고정한다. 경로 검사 뒤 fullpath를 열면 교체 경쟁이 남는다.
    directory = os.open(parts[0], os.O_RDONLY | os.O_DIRECTORY)
    try:
        for component in parts[1:-1]:
            following = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                dir_fd=directory)
            os.close(directory)
            directory = following
        descriptor = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                             dir_fd=directory)
    finally:
        os.close(directory)
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= limit:
            raise ValueError("invalid-public-period-size")
        body = stream.read(limit + 1)
    if not 0 < len(body) <= limit:
        raise ValueError("invalid-public-period-size")
    return body


def _period_originals(documents, directory, registry_path):
    """명시된 문서 ID의 기존 ZIP만 읽는다. 누락을 수집으로 보완하지 않는다."""
    directory = Path(directory)
    if not directory.is_dir() or any(p.is_symlink() for p in (directory, *directory.parents)):
        raise ValueError("invalid-public-period-directory")
    if type(documents) is not list or not 1 <= len(documents) <= 8:
        raise ValueError("invalid-public-period-documents")
    registry = _read_judgment_input(registry_path, limit=256_000, period_original=True)
    if type(registry) is not dict:
        raise ValueError("invalid-public-period-registry")
    archives = {}
    for document in documents:
        identifier = document.get("source_id") if type(document) is dict else None
        if type(identifier) is not str or not re.fullmatch(r"source:dart:[0-9]{14}", identifier, re.ASCII):
            raise ValueError("invalid-public-period-source")
        if identifier in archives:
            raise ValueError("duplicate-public-period-source")
        path = directory / ("dart-document-" + identifier[12:] + ".zip")
        archives[identifier] = _read_period_file(path, 4 * 1024 * 1024)
    return {"period_archives": archives, "issuer_registry": registry}


def _contract_context(sources, catalog):
    from portfolio_core.portfolio_contract_facts import index_contract_events
    from api.intelligence.portfolio_ai_public import validated_contract_sources
    artifact = sources.get("member_map_auto_evidence.json", {})
    facts = artifact.get("contract_facts", [])
    if type(facts) is not list:
        raise ValueError("invalid-contract-review-source")
    indexed = {}
    for fact in facts:
        receipt = fact["receipt_no"]
        if receipt in indexed:
            raise ValueError("duplicate-contract-review-source")
        indexed[receipt] = fact
    return artifact, index_contract_events(artifact, catalog if facts else []), validated_contract_sources(artifact)


def export_candidates(input_path, source_dir, output_path, *, worker_state=False,
                      judgment_input=None, judgment_reviews=None, judgment_as_of=None,
                      judgment_previous=None, retained_public_judgments=None,
                      period_source_dir=None, issuer_registry_path=None,
                      append_public_judgments=None, append_only=False):
    if (type(worker_state) is not bool or type(append_only) is not bool
            or append_only and (worker_state or input_path is not None or append_public_judgments is None
                                or period_source_dir is None or issuer_registry_path is None)
            or not append_only and ((worker_state and input_path is not None)
                                    or (not worker_state and input_path is None))):
        raise ValueError("invalid-public-ai-input-mode")
    if output_path.name != "member_map_ai_candidates.json" or output_path.is_symlink():
        raise ValueError("invalid-public-ai-output")
    judgment_args = [judgment_input, judgment_reviews, judgment_as_of]
    if (any(v is not None for v in judgment_args) and not all(v is not None for v in judgment_args)
            or judgment_previous is not None and judgment_input is None
            or retained_public_judgments is not None and judgment_input is not None):
        raise ValueError("invalid-public-judgment-arguments")
    if ((period_source_dir is None) != (issuer_registry_path is None)
            or period_source_dir is not None and judgment_input is None):
        raise ValueError("invalid-public-period-arguments")
    if append_public_judgments is not None and (
            judgment_input is None or retained_public_judgments is not None
            or judgment_previous is not None or period_source_dir is None):
        raise ValueError("invalid-public-append-arguments")
    review_names = {"universe_search.json", "public_disclosure_feed.json",
                    "member_map_auto_evidence.json", "member_map_ai_candidates.json"}
    if {p.name for p in Path(source_dir).iterdir()} == review_names:
        spec = importlib.util.spec_from_file_location("member_map_public_validator",
            Path(__file__).with_name("validate-public-ai-artifact.py"))
        validator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(validator)
        sources = validator.read_review_sources(source_dir)
        catalog = validator.project_public_sources(sources)["companies"]
    else:
        sources = load_public_sources(source_dir)
        catalog = project_public_sources(sources)["companies"]
    # Combine the retained comparison archive and current claims archive without
    # increasing the worker's per-archive bound or replacing either input.
    if append_only:
        payloads = []
    elif worker_state:
        payloads = _worker_payloads()
    else:
        inputs = input_path if isinstance(input_path, (list, tuple)) else [input_path]
        if not 1 <= len(inputs) <= 2:
            raise ValueError("invalid-public-ai-input-count")
        payloads = (load_ai_review(incoming) for incoming in inputs)
    artifact = {"schema": "local-ai-review-v1", "candidates": [],
                "coverage": dict(input=0, accepted=0, rejected=0, skipped=0)}
    seen_documents, document_versions = {}, {}
    for payload in payloads:
        # Enforce the original per-input gates BEFORE dedupe; 101 copies must
        # not turn an oversized archive into a valid one-entry input.
        if (type(payload) is not dict or set(payload) != {"schema", "entries"}
                or payload["schema"] != "local-ai-review-input-v1"
                or type(payload["entries"]) is not list or len(payload["entries"]) > 100
                or len(json.dumps(payload, ensure_ascii=False, allow_nan=False).encode()) > 2_000_000):
            raise ValueError("invalid-local-ai-review")
        candidates = []
        for entry in payload["entries"]:
            if type(entry) is not dict or set(entry) != {"document", "answer"}:
                raise ValueError("invalid-local-ai-entry")
            document = json.dumps(entry["document"], ensure_ascii=False, sort_keys=True, allow_nan=False)
            answer = json.dumps(entry["answer"], ensure_ascii=False, sort_keys=True, allow_nan=False)
            if document in seen_documents:
                if seen_documents[document] != answer:
                    raise ValueError("conflicting-local-ai-answer")
                continue
            seen_documents[document] = answer
            source_id = entry["document"].get("source_id") if type(entry["document"]) is dict else None
            document_versions.setdefault(source_id, set()).add(hashlib.sha256(document.encode()).hexdigest())
            # Prepare distinct documents individually so the replay helper's
            # within-batch ID suppression cannot hide a conflicting revision.
            prepared = prepare_review_candidates({"schema": payload["schema"], "entries": [entry]}, catalog)
            candidates.extend(prepared["candidates"])
            for key in artifact["coverage"]:
                artifact["coverage"][key] += prepared["coverage"][key]
        candidates.sort(key=lambda row: (row["as_of"], row["id"]), reverse=True)
        artifact["candidates"].extend(candidates)
    # Duplicate IDs, conflicting revisions, extra fields and excessive size all
    # fail before replacing the last valid output; no implicit winner or eviction.
    context = {}
    if append_only:
        _, contract_events, contract_sources = _contract_context(sources, catalog)
        context = {"contract_events": contract_events, "contract_sources": contract_sources}
        baseline = _read_judgment_input(append_public_judgments, limit=2_000_000)
        checked = validate_public_ai_review(baseline, catalog, **context)
        if checked != baseline:
            raise ValueError("unsafe-append-public-baseline")
        artifact = {key: baseline[key] for key in ("schema", "candidates", "coverage")}
    else:
        artifact = validate_public_ai_review(artifact, catalog)
    if judgment_input is not None:
        # Revalidate the original public packet and revision-bound review, never
        # trust an accepted flag in a projected/client record. No archive miss
        # can invoke a provider, ledger, key lookup or private member query.
        from api.intelligence.portfolio_business_judgment import project_company_judgments
        from api.intelligence.portfolio_ai_public import project_public_company_judgments
        payload = _read_judgment_input(judgment_input, period_original=period_source_dir is not None)
        if type(payload) is not dict or set(payload) != {"documents", "answer"}:
            raise ValueError("invalid-public-judgment-input")
        if type(payload["documents"]) is not list:
            raise ValueError("invalid-public-judgment-documents")
        for document in payload["documents"]:
            if type(document) is not dict:
                raise ValueError("invalid-public-judgment-documents")
            version = hashlib.sha256(json.dumps(document, ensure_ascii=False,
                sort_keys=True, allow_nan=False).encode()).hexdigest()
            if not append_only and document_versions.get(document.get("source_id")) != {version}:
                raise ValueError("stale-public-judgment-source")
        reviews = _read_judgment_input(judgment_reviews, period_original=period_source_dir is not None)
        prior = {}
        if judgment_previous is not None:
            # The existing producer validates this exact prior-artifact bundle.
            # Malformed requested history cannot masquerade as a first judgment.
            prior = {"previous": _read_judgment_input(judgment_previous, limit=2_800_000)}
        period_inputs = {}
        if period_source_dir is not None:
            period_inputs = _period_originals(payload["documents"], period_source_dir, issuer_registry_path)
        requested_v3 = [r for r in payload["answer"]["judgments"]
                        if type(r) is dict and "period_context_v3" in r] if (
                            type(payload["answer"]) is dict and type(payload["answer"].get("judgments")) is list) else []
        if requested_v3 and not period_inputs:
            raise ValueError("missing-public-period-originals")
        if append_only and (not requested_v3 or len(requested_v3) != len(payload["answer"]["judgments"])):
            raise ValueError("append-only-requires-period-originals")
        if append_public_judgments is not None and (
                not requested_v3 or len(requested_v3) != len(payload["answer"]["judgments"])):
            raise ValueError("invalid-public-append-period-judgments")
        local = project_company_judgments(payload["answer"], payload["documents"],
            artifact["candidates"], reviews, as_of=judgment_as_of, **prior, **period_inputs)
        if len(requested_v3) != sum("period_context_v3" in r for r in local["judgments"]):
            raise ValueError("unbound-public-period-judgment")
        artifact["company_judgments"] = project_public_company_judgments(
            local, artifact["candidates"], source_documents=payload["documents"], **period_inputs)
        if requested_v3 and len(artifact["company_judgments"]["judgments"]) != len(local["judgments"]):
            raise ValueError("unbound-public-period-judgment")
        artifact = validate_public_ai_review(artifact, catalog)
        if append_public_judgments is not None:
            from api.intelligence.portfolio_ai_public import MAX_COMPANY_JUDGMENTS
            if not append_only:
                _, contract_events, contract_sources = _contract_context(sources, catalog)
                context = {"contract_events": contract_events, "contract_sources": contract_sources}
            previous = _read_judgment_input(append_public_judgments, limit=2_000_000)
            checked = validate_public_ai_review(previous, catalog, **context)
            if checked != previous or any(artifact[k] != previous[k] for k in ("candidates", "coverage")):
                raise ValueError("changed-append-public-baseline")
            old = previous.get("company_judgments", {"schema": "local-company-judgments-v1", "judgments": []})
            if project_public_company_judgments(old, artifact["candidates"], **context) != old:
                raise ValueError("stale-append-public-judgments")
            added = artifact["company_judgments"]["judgments"]
            existing = {r["record_id"] for r in old["judgments"]}
            if (not added or any(r["status"] != "accepted" or r["record_id"] in existing for r in added)
                    or len(old["judgments"]) + len(added) > MAX_COMPANY_JUDGMENTS):
                raise ValueError("invalid-new-public-judgments")
            artifact["company_judgments"] = {"schema": old["schema"], "judgments": [*old["judgments"], *added]}
            if validate_public_ai_review(artifact, catalog, **context) != artifact:
                raise ValueError("unsafe-append-public-judgments")
    elif retained_public_judgments is not None:
        from api.intelligence.portfolio_ai_public import project_public_company_judgments
        prior = validate_public_ai_review(_read_judgment_input(retained_public_judgments, limit=2_000_000), catalog)
        prior_rows = prior.get("company_judgments", {}).get("judgments", [])
        current = {c["id"]: c for c in artifact["candidates"]}
        # Already public, sanitized rows may survive an unchanged-source refresh.
        # A new/changed/removed source withdraws the old grade, never retargets it.
        retained = []
        for item in prior_rows:
            candidate = current.get(item["record_id"])
            if (candidate and item["base_read_revision"] == int(candidate["revision"][:13], 16) + 1
                    and item["company_id"] == candidate["issuer_id"]
                    and item["counterparty_id"] == candidate["counterparty_id"]
                    and item["source_id"] == candidate["source_id"]
                    and item["source_url"] == candidate["url"] and item["published_on"] == candidate["as_of"]
                    and document_versions.get(item["source_id"]) == {item.get("source_version")}):
                retained.append(item)
        artifact["company_judgments"] = project_public_company_judgments(
            {"schema": "local-company-judgments-v1", "judgments": retained}, artifact["candidates"])
        artifact = validate_public_ai_review(artifact, catalog)
    body = (json.dumps(artifact, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n").encode()
    if len(body) > 2_000_000:
        raise ValueError("public-ai-output-too-large")
    # Validate before replacing: invalid refresh cannot erase a working snapshot.
    descriptor, temporary = tempfile.mkstemp(prefix="member-map-ai-", dir=output_path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, output_path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return {"schema": artifact["schema"], "coverage": artifact["coverage"],
            "bytes": len(body), "network_calls": 0, "published": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--input", action="append", type=Path)
    inputs.add_argument("--worker-state", action="store_true")
    inputs.add_argument("--append-only", action="store_true", help="이미 공개된 후보를 재사용하고 원문 검수 판정만 추가")
    parser.add_argument("--source-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--judgment-input", type=Path, help="Saved public documents and answer; never a projected receipt")
    parser.add_argument("--judgment-reviews", type=Path, help="Explicit revision-bound local reviews; private text is not exported")
    parser.add_argument("--judgment-as-of")
    parser.add_argument("--judgment-previous", type=Path, help="Existing prior {answer,documents,candidates,reviews,as_of} bundle")
    parser.add_argument("--retained-public-judgments", type=Path, help="Prior public artifact; retain only exact unchanged candidate bindings")
    parser.add_argument("--period-source-dir", type=Path, help="기존 native DART ZIP 디렉터리; 누락 원문은 수집하지 않음")
    parser.add_argument("--issuer-registry-path", type=Path, help="기존 issuer name/corp_code JSON; period-source-dir와 함께 지정")
    parser.add_argument("--append-public-judgments", type=Path, help="기존 후보·판정·기준일을 보존하고 새 v3 검수 판정만 추가")
    args = parser.parse_args()
    try:
        result = export_candidates(args.input, args.source_dir, args.output, worker_state=args.worker_state,
            judgment_input=args.judgment_input, judgment_reviews=args.judgment_reviews,
            judgment_as_of=args.judgment_as_of, judgment_previous=args.judgment_previous,
            retained_public_judgments=args.retained_public_judgments,
            period_source_dir=args.period_source_dir, issuer_registry_path=args.issuer_registry_path,
            append_public_judgments=args.append_public_judgments, append_only=args.append_only)
    except (ValueError, OSError, TypeError):
        print("public-ai-export-rejected", file=sys.stderr)
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
