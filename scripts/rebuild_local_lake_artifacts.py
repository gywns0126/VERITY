"""Isolated event-study rebuild; never reset or lock another session's checkout."""
from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time

REMOTE = "https://github.com/gywns0126/VERITY.git"
LAKE = Path.home() / "VERITY_data_lake"
JOB = LAKE / "event_study_job"
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


def validate(old, new):
    stocks = new.get("stocks")
    if not isinstance(stocks, dict) or not stocks:
        raise ValueError("Empty or invalid event study")
    missing = set(old.get("stocks", {})) - set(stocks)
    if missing:
        raise ValueError(f"Refusing loss of {len(missing)} previously published issuers")
    meta = new.get("_meta") or {}
    if meta.get("stock_count") != len(stocks):
        raise ValueError("Stock count mismatch")
    if not meta.get("kr_count") or not meta.get("us_count"):
        raise ValueError("Refusing missing KR or US market")


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
            network("git", "clone", "--depth", "1", "--filter=blob:none",
                    "--sparse", REMOTE, str(REPO), cwd=JOB)
        if not (REPO / ".git").is_dir():
            raise RuntimeError("Expected independent clone, not a shared worktree")
        if command("git", "remote", "get-url", "origin").strip() != REMOTE:
            raise RuntimeError("Unexpected remote")
        if command("git", "status", "--porcelain").strip():
            raise RuntimeError("Pending local changes preserved; review before retry")
        network("git", "fetch", "origin", "main", "--depth=10")
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
        new = json.loads((REPO / OUTPUT).read_text())
        validate(old, new)
        if content(old) == content(new):
            (REPO / OUTPUT).write_bytes(old_bytes)
            print("[skip] verified unchanged content; original timestamp preserved")
            return 0
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
                network("git", "fetch", "origin", "main", "--depth=10")
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
