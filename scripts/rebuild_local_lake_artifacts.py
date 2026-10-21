"""Isolated event-study rebuild; never reset or lock another session's checkout."""
from __future__ import annotations

import fcntl
import hashlib
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import time

REMOTE = "https://github.com/gywns0126/VERITY.git"
LAKE = Path.home() / "VERITY_data_lake"
JOB = Path(os.environ.get("VERITY_EVENT_STUDY_JOB", str(LAKE / "event_study_job"))).expanduser()
REPO = JOB / "repo"
OUTPUT = "data/event_study.json"
SPARSE = ["/api/", "/data/dart_catalyst_backfill.jsonl",
          "/data/dart_catalyst_alerts.jsonl", "/data/us_catalyst_backfill.jsonl",
          "/" + OUTPUT]


def command(*args, cwd=REPO, timeout=300):
    return subprocess.run(args, cwd=str(cwd), check=True, capture_output=True,
                          text=True, timeout=timeout).stdout


def network(*args, cwd=REPO):
    for attempt in range(3):
        try:
            return command(*args, cwd=cwd)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            if attempt == 2:
                raise
            print("[retry] network operation failed", flush=True)
            time.sleep(5 * (attempt + 1))


def _validated_counts(doc):
    stocks = doc.get("stocks") if isinstance(doc, dict) else None
    meta = doc.get("_meta") if isinstance(doc, dict) else None
    if not isinstance(stocks, dict) or not stocks or not isinstance(meta, dict):
        raise ValueError("Empty or invalid event study")
    occurrences = 0
    for stock in stocks.values():
        events = stock.get("events") if isinstance(stock, dict) else None
        if not isinstance(events, list) or not events:
            raise ValueError("Invalid issuer event history")
        for group in events:
            rows = group.get("occurrences") if isinstance(group, dict) else None
            if not isinstance(rows, list) or not rows or not all(isinstance(row, dict) for row in rows):
                raise ValueError("Invalid issuer occurrences")
            occurrences += len(rows)
    kr = sum(ticker.isdigit() for ticker in stocks)
    us = len(stocks) - kr
    if not kr or not us:
        raise ValueError("Refusing missing KR or US market")
    if any(meta.get(key) != value for key, value in (
            ("stock_count", len(stocks)), ("kr_count", kr),
            ("us_count", us), ("occurrence_count", occurrences))):
        raise ValueError("Event study count mismatch")
    return kr, us, occurrences


def validate(old, new):
    _validated_counts(new)
    missing = set(old.get("stocks", {})) - set(new["stocks"])
    if missing:
        raise ValueError(f"Refusing loss of {len(missing)} previously published issuers")


def preserve_historical_issuers(old, new):
    # Validate actual fresh coverage before fallback can conceal a failed market.
    _validated_counts(old)
    _validated_counts(new)
    old_meta, meta = old["_meta"], new["_meta"]
    if old_meta.get("windows") != meta.get("windows"):
        raise ValueError("Refusing incompatible historical return windows")
    missing = set(old["stocks"]) - set(new["stocks"])
    if any(ticker.isdigit() for ticker in missing):
        raise ValueError("Refusing unverified KR issuer loss")
    existing = old_meta.get("carried_forward_issuers", {})
    if not isinstance(existing, dict):
        raise ValueError("Invalid historical carry receipts")
    carried = {}
    for ticker in sorted(missing):
        previous = old["stocks"][ticker]
        digest = hashlib.sha256(json.dumps(
            previous, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")).hexdigest()
        if ticker in existing:
            receipt = existing[ticker]
            if not isinstance(receipt, dict) or receipt.get("payload_sha256") != digest:
                raise ValueError("Historical carry receipt does not match preserved payload")
        else:
            receipt = {"previous_generated_at": old_meta.get("generated_at"),
                       "previous_us_price_source": old_meta.get("us_price_source"),
                       "payload_sha256": digest}
        new["stocks"][ticker] = deepcopy(previous)
        carried[ticker] = deepcopy(receipt)
    if carried:
        meta["carried_forward_issuers"] = carried
        meta["carried_forward_issuer_count"] = len(carried)
        meta["stock_count"] = len(new["stocks"])
        meta["kr_count"] = sum(ticker.isdigit() for ticker in new["stocks"])
        meta["us_count"] = meta["stock_count"] - meta["kr_count"]
        meta["occurrence_count"] = sum(len(group["occurrences"])
                                       for stock in new["stocks"].values()
                                       for group in stock["events"])
    else:
        meta.pop("carried_forward_issuers", None)
        meta.pop("carried_forward_issuer_count", None)
    return new


def content(doc):
    doc = dict(doc)
    doc["_meta"] = dict(doc.get("_meta") or {})
    doc["_meta"].pop("generated_at", None)
    return doc


def rebuild():
    JOB.mkdir(parents=True, exist_ok=True)
    with (JOB / "rebuild.lock").open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("[skip] another event-study rebuild owns the lock")
            return 0
        if not REPO.exists():
            # Independent .git (not a worktree of the interactive repo).
            network("git", "clone", "--filter=blob:none",
                    "--sparse", REMOTE, str(REPO), cwd=JOB)
        if not (REPO / ".git").is_dir():
            raise RuntimeError("Expected independent clone, not a shared worktree")
        if command("git", "remote", "get-url", "origin").strip() != REMOTE:
            raise RuntimeError("Unexpected remote")
        if command("git", "status", "--porcelain").strip():
            raise RuntimeError("Pending local changes preserved; review before retry")
        network("git", "fetch", "origin", "main")
        # A prior failed push must not be discarded by moving HEAD.
        ahead = command("git", "rev-list", "--count", "origin/main..HEAD").strip()
        if ahead != "0":
            raise RuntimeError("Unpublished commit preserved; review before retry")
        command("git", "checkout", "--detach", "origin/main")
        network("git", "sparse-checkout", "set", "--no-cone", *SPARSE)
        if command("git", "diff", "--cached", "--name-only").strip():
            raise RuntimeError("Unexpected staged files")
        old_bytes = (REPO / OUTPUT).read_bytes()
        old = json.loads(old_bytes)
        print(command(sys.executable, "-m", "api.builders.event_study_builder",
                      timeout=600), end="", flush=True)
        new = preserve_historical_issuers(old, json.loads((REPO / OUTPUT).read_text()))
        validate(old, new)
        if content(old) == content(new):
            (REPO / OUTPUT).write_bytes(old_bytes)
            print("[skip] verified unchanged content; original timestamp preserved")
            return 0
        (REPO / OUTPUT).write_text(json.dumps(new, ensure_ascii=False, indent=2))
        changed = command("git", "diff", "--name-only").splitlines()
        if changed != [OUTPUT]:
            raise RuntimeError(f"Unexpected modified paths: {changed}")
        command("git", "add", "--", OUTPUT)
        if command("git", "diff", "--cached", "--name-only").splitlines() != [OUTPUT]:
            raise RuntimeError("Unexpected staged paths")
        # Use the authenticated account's normal Git identity, not an invented author.
        for key in ("user.name", "user.email"):
            if not command("git", "config", "--get", key).strip():
                raise RuntimeError(f"Missing {key}")
        command("git", "commit", "-m", "data(event-study): rebuild from isolated local lake job")
        for attempt in range(3):
            try:
                network("git", "push", "origin", "HEAD:main")
                print("[ok] main artifact commit " + command("git", "rev-parse", "HEAD").strip())
                return 0
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                if attempt == 2:
                    raise
                network("git", "fetch", "origin", "main")
                # Rebase refuses overlapping remote artifact edits; no force push.
                command("git", "rebase", "origin/main")
        return 1


if __name__ == "__main__":
    os.environ["PATH"] = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
    try:
        raise SystemExit(rebuild())
    except Exception as exc:
        print(f"[error] {type(exc).__name__}: {exc}", file=sys.stderr)
        if isinstance(exc, subprocess.CalledProcessError):
            print(exc.stderr[-2000:], file=sys.stderr)
        raise SystemExit(1)
