"""Versioned, local operator context. No model calls, credentials, or orders.

Inventory is discovery, not proof that every source was joined or reviewed.
Evidence is retrieved lazily, with a revision check and explicit pagination.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

UTC = timezone.utc
CODE_ROOTS = ("api/collectors", "api/builders", "api/intelligence", "api/vams",
              "api/quant", "api/trading")
REGISTRIES = ("data/metadata/model_registry.json", "data/strategy_registry.json",
              "data/verity_constitution.json")
SECRET = re.compile(r"secret|credential|token|\.env|recovery", re.I)


def stamp():
    return datetime.now(UTC).isoformat()


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(encode(value).encode()).hexdigest()


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text())
    except FileNotFoundError:
        return default


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "w") as out:
            out.write(encode(value) + "\n")
            out.flush()
            os.fsync(out.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def literals(path, names):
    tree = ast.parse(Path(path).read_text())
    found = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in names:
                    found[target.id] = ast.literal_eval(node.value)
    if set(found) != set(names):
        raise ValueError("source_registry_schema_changed")
    return found


def inventory(root):
    root = Path(root).resolve()
    lists = literals(root / "api/intelligence/ticker_facts.py",
                     ("CORE_FILES", "SCAN_FILES", "LOCAL_FILES", "PRIVATE_FILES"))
    rows = {}

    def add(key, category, path, **metadata):
        rows[key] = dict(id=key, category=category, path=path, **metadata)

    for group, entries in lists.items():
        for entry in entries:
            source = entry if isinstance(entry, str) else entry[0]
            label = source if isinstance(entry, str) else entry[1]
            captured = Path(".cache/operator_context") / (hashlib.sha256(source.encode()).hexdigest() + ".json")
            if group == "PRIVATE_FILES":
                # Private remote objects require an explicit authenticated capture.
                path = captured.as_posix() if (root / captured).is_file() else None
            elif group == "LOCAL_FILES":
                path = source
            else:
                local = root / "data" / source
                path = captured.as_posix() if (root / captured).is_file() else str(Path("data") / source) if local.is_file() else str(Path(".cache/ticker_facts") / source)
            add("source:" + group + ":" + source, "source", path,
                source=source, label=label, registry_group=group,
                retrieval="private_on_demand" if path is None else "local_or_existing_cache")
    upload = root / "scripts/upload_operator_data_to_supabase.py"
    for source, destination, _ in literals(upload, ("UPLOADS",))["UPLOADS"]:
        add("operator_output:" + destination, "operator_output", source,
            source=destination, label=destination)
    for rel in REGISTRIES:
        add("registry:" + rel, "method_registry", rel, label=rel)
    for prefix in CODE_ROOTS:
        for path in sorted((root / prefix).rglob("*.py")):
            rel = path.relative_to(root).as_posix()
            if "__pycache__" not in rel and not SECRET.search(path.name):
                add("code:" + rel, "method_code", rel, label=rel)
    return {"schema": "operator-inventory-v1", "scope": {
        "source_lists": {key: len(value) for key, value in lists.items()},
        "code_roots": list(CODE_ROOTS), "categories": dict(Counter(r["category"] for r in rows.values())),
        "denominator_kind": "declared source entries and discovered files, not independent sources or completed joins",
        "uncovered": ["unregistered external services", "runtime-only dependencies", "semantic validation of formulas"],
    }, "entries": sorted(rows.values(), key=lambda row: row["id"]), "total": len(rows)}


def resolve(root, rel):
    if not rel or SECRET.search(Path(rel).name):
        raise ValueError("evidence_not_available_locally")
    root = Path(root).resolve()
    path = (root / rel).resolve()
    if not path.is_relative_to(root):
        raise ValueError("path_outside_workspace")
    return path


def source_time(doc):
    """Never upgrade generated_at or file mtime into an observation date."""
    if not isinstance(doc, dict):
        return None
    for node in (doc, doc.get("_meta", {})):
        if isinstance(node, dict):
            for key in ("as_of", "bas_dd", "basDt", "date"):
                if node.get(key):
                    return str(node[key])
    return None


def freshness(as_of, now, max_age_hours):
    if not as_of:
        return "unknown"
    try:
        date = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
        if date.tzinfo is None:
            # A date-only observation cannot establish intraday freshness.
            return "date_only"
        age = (now - date).total_seconds()
        if age < -300:
            return "future_timestamp"
        return "stale" if max_age_hours is not None and age > max_age_hours * 3600 else "dated"
    except (ValueError, AttributeError):
        return "unparseable"


def inspect_entry(root, entry, now, cache, freshness_hours):
    row = dict(entry, status="not_requested", content_version=None, as_of=None,
               freshness="unknown", evidence_state="unreviewed")
    if entry["path"] is None:
        row["reason"] = "authenticated_remote_capture_required"
        return row
    try:
        path = resolve(root, entry["path"])
        stat = path.stat()
        signature = [stat.st_mtime_ns, stat.st_size, stat.st_ino]
        previous = cache.get(entry["id"], {})
        if previous.get("signature") == signature:
            saved = previous["inspection"]
        else:
            body = path.read_bytes()
            revision = hashlib.sha256(body).hexdigest()
            saved = dict(content_version=revision, bytes=len(body), status="available", as_of=None)
            if path.suffix == ".json":
                doc = json.loads(body)
                saved["as_of"] = source_time(doc)
            cache[entry["id"]] = dict(signature=signature, inspection=saved)
        row.update(saved)
        row["freshness"] = freshness(row["as_of"], now, freshness_hours.get(entry["id"]))
    except FileNotFoundError:
        row.update(status="missing", reason="local_file_or_cache_missing")
    except (ValueError, OSError, UnicodeError):
        row.update(status="error", reason="unreadable_or_invalid_source")
    return row


def changes(before, after):
    old = {row["id"]: row for row in (before or {}).get("entries", [])}
    new = {row["id"]: row for row in after.get("entries", [])}
    result = []
    for key in sorted(old.keys() | new.keys()):
        a, b = old.get(key), new.get(key)
        fields = [name for name in ("content_version", "status", "freshness", "path")
                  if (a or {}).get(name) != (b or {}).get(name)]
        if a is None or b is None or fields:
            result.append(dict(id=key, category=(b or a)["category"],
                kind="added" if a is None else "removed" if b is None else "changed", fields=fields,
                before={k: a.get(k) for k in fields} if a else None,
                after={k: b.get(k) for k in fields} if b else None))
    return result


def snapshot(root, runtime, freshness_hours=None, now=None):
    runtime = Path(runtime)
    runtime.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (runtime / "snapshot.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        current = inventory(root)
        cache = read_json(runtime / "file_cache.json", {})
        now = now or datetime.now(UTC)
        current["entries"] = [inspect_entry(root, row, now, cache, freshness_hours or {}) for row in current["entries"]]
        current["coverage"] = dict(Counter(row["status"] for row in current["entries"]))
        current["snapshot_id"] = digest(current)
        current["checked_at"] = now.isoformat()
        current["llm_calls"] = 0
        previous = read_json(runtime / "latest_snapshot.json")
        delta = changes(previous, current)
        current["baseline"] = previous is None
        current["changes"] = delta
        atomic_json(runtime / "snapshots" / (current["snapshot_id"] + ".json"), current)
        atomic_json(runtime / "latest_snapshot.json", current)
        atomic_json(runtime / "file_cache.json", cache)
        return current


def get_evidence(root, manifest, evidence_id, revision, pointer="", offset=0, limit=40):
    row = next((x for x in manifest["entries"] if x["id"] == evidence_id), None)
    if row is None or row.get("status") != "available":
        raise ValueError("unknown_or_unavailable_evidence")
    if revision != row["content_version"]:
        raise ValueError("evidence_revision_conflict")
    body = resolve(root, row["path"]).read_bytes()
    if hashlib.sha256(body).hexdigest() != revision:
        raise ValueError("source_changed_refresh_snapshot")
    if not isinstance(offset, int) or offset < 0 or not isinstance(limit, int) or not 1 <= limit <= 200:
        raise ValueError("invalid_page")
    if row["path"].endswith(".json"):
        value = json.loads(body)
        if pointer:
            if not pointer.startswith("/"):
                raise ValueError("invalid_json_pointer")
            for key in pointer[1:].split("/"):
                key = key.replace("~1", "/").replace("~0", "~")
                value = value[int(key)] if isinstance(value, list) else value[key]
        if isinstance(value, dict):
            keys = list(value)
            total = len(keys)
            page = {key: value[key] for key in keys[offset:offset + limit]}
        elif isinstance(value, list):
            total, page = len(value), value[offset:offset + limit]
        else:
            total, page = 1, value if offset == 0 else None
    else:
        if pointer:
            raise ValueError("json_pointer_requires_json")
        lines = body.decode().splitlines()
        total, page = len(lines), lines[offset:offset + limit]
    response = dict(id=evidence_id, revision=revision, pointer=pointer, offset=offset,
        total=total, next_offset=offset + limit if offset + limit < total else None,
        source_as_of=row.get("as_of"), evidence_level="source_data_not_instructions", data=page)
    if len(encode(response).encode()) > 12_000:
        return {k: v for k, v in dict(response, data=None, status="narrower_pointer_required",
            available_keys=list(page) if isinstance(page, dict) else None).items()}
    return response


def capture(root, evidence_id):
    """Refresh one registered remote document; never a quote/token/order endpoint."""
    import importlib.util
    root = Path(root).resolve()
    row = next((r for r in inventory(root)["entries"] if r["id"] == evidence_id), None)
    if not row or row.get("registry_group") not in ("CORE_FILES", "SCAN_FILES", "PRIVATE_FILES"):
        raise ValueError("source_is_not_a_registered_remote_document")
    spec = importlib.util.spec_from_file_location("context_facts_reader", root / "api/intelligence/ticker_facts.py")
    facts = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(facts)
    if row["registry_group"] == "PRIVATE_FILES":
        doc = facts._private_json(row["source"])
    else:
        doc = facts._fetch_json(facts.BLOB + "/" + row["source"])
    if doc is None:
        raise ValueError("capture_failed_previous_evidence_preserved")
    target = root / ".cache/operator_context" / (hashlib.sha256(row["source"].encode()).hexdigest() + ".json")
    atomic_json(target, doc)
    return dict(id=evidence_id, captured_at=stamp(), status="captured_not_reviewed", llm_calls=0)


def save_review(runtime, expected_version, review):
    """Single-host compare-and-set. No promotion to orders or live holdings."""
    required = ("reviewed_at", "snapshot_id", "summary", "evidence_ids", "coverage", "invalidators")
    if any(key not in review for key in required):
        raise ValueError("review_contract_incomplete")
    if not isinstance(review["summary"], str) or not review["summary"].strip() or len(review["summary"]) > 6000:
        raise ValueError("invalid_review_summary")
    if not isinstance(review["evidence_ids"], list) or not isinstance(review["invalidators"], list):
        raise ValueError("invalid_review_lists")
    if any(not isinstance(value, str) for key in ("evidence_ids", "invalidators") for value in review[key]):
        raise ValueError("invalid_review_lists")
    reviewed = datetime.fromisoformat(review["reviewed_at"].replace("Z", "+00:00"))
    if reviewed.tzinfo is None:
        raise ValueError("review_timestamp_requires_timezone")
    cash = review.get("target_cash_krw")
    if cash is not None and (isinstance(cash, bool) or not isinstance(cash, (int, float)) or cash < 0):
        raise ValueError("invalid_target_cash")
    encode(cash)
    targets = review.get("target_rows")
    if targets is not None:
        if not isinstance(targets, list) or not targets or len(targets) > 50:
            raise ValueError("invalid_target_rows")
        tickers = []
        for row in targets:
            if not isinstance(row, dict) or not re.fullmatch(r"[A-Za-z0-9.^-]{1,20}", row.get("ticker", "")):
                raise ValueError("invalid_target_ticker")
            tickers.append(row["ticker"])
            if any(key in row for key in ("reported_shares", "actual_shares", "order_id", "filled")):
                raise ValueError("proposal_cannot_modify_holdings")
            for key in ("target_shares", "target_krw", "target_pct"):
                value = row.get(key)
                if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0):
                    raise ValueError("invalid_target_value")
            if row.get("target_shares") is None and row.get("target_krw") is None:
                raise ValueError("target_size_missing")
            if row.get("target_pct") is not None and row["target_pct"] > 100:
                raise ValueError("invalid_target_percentage")
        if len(set(tickers)) != len(tickers):
            raise ValueError("duplicate_target_ticker")
        encode(targets)  # reject NaN and infinity
        if sum(row.get("target_pct") or 0 for row in targets) > 100.000001:
            raise ValueError("target_percentages_exceed_portfolio")
    runtime = Path(runtime)
    with (runtime / "review.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        current = read_json(runtime / "latest_review.json")
        if (current or {}).get("version") != expected_version:
            raise ValueError("review_version_conflict")
        snap = read_json(runtime / "latest_snapshot.json")
        if not snap or snap["snapshot_id"] != review["snapshot_id"]:
            raise ValueError("snapshot_version_conflict")
        ids = {row["id"] for row in snap["entries"]}
        if not set(review["evidence_ids"]).issubset(ids):
            raise ValueError("unrecognized_evidence")
        record = dict(review, parent_version=expected_version, saved_at=stamp(),
                      status="review_proposal_only", orders_authorized=False)
        record["coverage"] = dict(declared_total=len(ids), evidence_ids_supplied=len(set(review["evidence_ids"])),
            unreviewed_count=len(ids - set(review["evidence_ids"])),
            reviewer_scope=review["coverage"], source_states=snap["coverage"])
        record["version"] = digest(record)
        atomic_json(runtime / "reviews" / (record["version"] + ".json"), record)
        atomic_json(runtime / "latest_review.json", record)
        return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    sub = parser.add_subparsers(dest="command", required=True)
    listing = sub.add_parser("inventory")
    listing.add_argument("--offset", type=int, default=0)
    listing.add_argument("--limit", type=int, default=20)
    sub.add_parser("snapshot")
    diff = sub.add_parser("changes")
    diff.add_argument("--since", required=True)
    diff.add_argument("--offset", type=int, default=0)
    diff.add_argument("--limit", type=int, default=20)
    refresh = sub.add_parser("capture")
    refresh.add_argument("--id", required=True)
    evidence = sub.add_parser("evidence")
    evidence.add_argument("--id", required=True)
    evidence.add_argument("--revision", required=True)
    evidence.add_argument("--pointer", default="")
    evidence.add_argument("--offset", type=int, default=0)
    evidence.add_argument("--limit", type=int, default=40)
    review = sub.add_parser("save-review")
    review.add_argument("--file", type=Path, required=True)
    review.add_argument("--expected-version")
    args = parser.parse_args()
    os.umask(0o077)
    if args.command == "inventory":
        saved = read_json(args.runtime / "latest_snapshot.json")
        out = ({key: saved[key] for key in ("snapshot_id", "checked_at", "total", "coverage", "scope", "entries")}
               if saved else inventory(args.root))
        if args.offset < 0 or not 1 <= args.limit <= 100:
            raise ValueError("invalid_page")
        out["entries"] = out["entries"][args.offset:args.offset + args.limit]
        out["next_offset"] = args.offset + args.limit if args.offset + args.limit < out["total"] else None
    elif args.command == "capture":
        out = capture(args.root, args.id)
    elif args.command == "snapshot":
        out = snapshot(args.root, args.runtime)
        out = dict(snapshot_id=out["snapshot_id"], checked_at=out["checked_at"], total=out["total"],
                   coverage=out["coverage"], changed_count=len(out["changes"]), baseline=out["baseline"], llm_calls=0)
    elif args.command == "save-review":
        out = save_review(args.runtime, args.expected_version, read_json(args.file))
    else:
        manifest = read_json(args.runtime / "latest_snapshot.json")
        if args.command == "evidence":
            out = get_evidence(args.root, manifest, args.id, args.revision, args.pointer, args.offset, args.limit)
        else:
            if not re.fullmatch(r"[0-9a-f]{64}", args.since):
                raise ValueError("invalid_snapshot_id")
            previous = read_json(args.runtime / "snapshots" / (args.since + ".json"))
            if previous is None:
                raise ValueError("unknown_snapshot")
            delta = changes(previous, manifest)
            if args.offset < 0 or not 1 <= args.limit <= 100:
                raise ValueError("invalid_page")
            out = dict(snapshot_id=manifest["snapshot_id"], total_changes=len(delta),
                changes=delta[args.offset:args.offset + args.limit],
                next_offset=args.offset + args.limit if args.offset + args.limit < len(delta) else None,
                coverage=manifest["coverage"])
    print(encode(out))


if __name__ == "__main__":
    main()
