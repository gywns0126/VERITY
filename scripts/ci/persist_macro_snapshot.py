#!/usr/bin/env python3
"""Persist the prepared macro commit with bounded Git calls and no autostash.

Rebuild only its three selected outputs on the fetched remote tree. Never merge
snapshot generations, drop concurrent ledger entries, or overwrite another
writer's shared health snapshot. The workflow retains the inputs as an artifact.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time

SNAPSHOT = "data/macro_snapshot.json"
LEDGER = "data/metadata/fred_health.jsonl"
HEALTH = "data/metadata/data_pipeline_health.json"
PATHS = (SNAPSHOT, LEDGER, HEALTH)


class GitFailure(RuntimeError):
    pass


def git(repo, *args, deadline, phase, input=None, env=None, check=True):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise GitFailure("Persistence budget exhausted")
    limit = min(30 if args[0] in ("fetch", "push") else 15, remaining)
    started = time.monotonic()
    print(f"[macro_persist] phase={phase} start timeout_s={limit:.1f}", flush=True)
    settings = dict(os.environ, GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="Never")
    settings.update(env or {})
    process = subprocess.Popen(["git", "-C", str(repo), *args], stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               env=settings, start_new_session=True)
    try:
        stdout, stderr = process.communicate(input=input, timeout=limit)
    except subprocess.TimeoutExpired:
        # Kill the Git process group, including a blocked transport child.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.communicate()
        print(f"[macro_persist] phase={phase} timeout elapsed_s={time.monotonic()-started:.2f}", flush=True)
        raise GitFailure(f"{phase} timed out") from None
    print(f"[macro_persist] phase={phase} rc={process.returncode} elapsed_s={time.monotonic()-started:.2f}", flush=True)
    if check and process.returncode:
        # Do not echo transport stderr: it can contain credential-bearing URLs.
        raise GitFailure(f"{phase} failed rc={process.returncode}")
    return subprocess.CompletedProcess(args, process.returncode, stdout, stderr)


def persist(repo, branch, attempts=3, budget_s=180, retry_delay=5):
    deadline = time.monotonic() + budget_s
    def run(*args, **kwargs):
        return git(repo, *args, deadline=deadline, phase=kwargs.pop("phase", args[0]), **kwargs)
    def blob(ref, path):
        result = run("show", f"{ref}:{path}", phase="read_blob", check=False)
        if result.returncode not in (0, 128):
            raise GitFailure("Cannot read prepared or remote output")
        return result.stdout if result.returncode == 0 else None

    run("check-ref-format", f"refs/heads/{branch}")
    source = run("rev-parse", "HEAD").stdout.decode().strip()
    base = run("rev-parse", "HEAD^").stdout.decode().strip()
    changed = run("diff-tree", "--no-commit-id", "--name-only", "-r", source).stdout.decode().splitlines()
    if not changed or set(changed) - set(PATHS):
        raise GitFailure("Prepared commit must contain only explicit macro outputs")
    prepared = {path: blob(source, path) for path in PATHS}
    before = {path: blob(base, path) for path in PATHS}
    if not prepared[SNAPSHOT]:
        raise GitFailure("Prepared macro snapshot missing")
    old_ledger, new_ledger = before[LEDGER] or b"", prepared[LEDGER] or b""
    if not new_ledger.startswith(old_ledger):
        raise GitFailure("Prepared FRED ledger is not append-only")
    additions = Counter(new_ledger[len(old_ledger):].splitlines(keepends=True))
    message = run("log", "-1", "--format=%B", source).stdout
    digest = hashlib.sha256(prepared[SNAPSHOT]).hexdigest()
    last_error = None
    with tempfile.TemporaryDirectory(prefix="macro-persist-") as temp:
        index_env = {"GIT_INDEX_FILE": str(Path(temp) / "index")}
        for attempt in range(1, attempts + 1):
            try:
                run("fetch", "--no-tags", "origin", f"refs/heads/{branch}", phase="fetch")
                remote = run("rev-parse", "FETCH_HEAD").stdout.decode().strip()
                incoming = {path: blob(remote, path) for path in PATHS}
                if incoming[SNAPSHOT] not in (before[SNAPSHOT], prepared[SNAPSHOT]):
                    raise RuntimeError("Remote macro generation changed; preserve remote and recover artifact")
                ledger = incoming[LEDGER] or b""
                baseline_lines = Counter(old_ledger.splitlines(keepends=True))
                remote_lines = Counter(ledger.splitlines(keepends=True))
                if baseline_lines - remote_lines:
                    raise RuntimeError("Remote FRED ledger was rewritten; preserve remote and recover artifact")
                required = baseline_lines + additions
                missing = required - remote_lines
                if missing and ledger and not ledger.endswith(b"\n"):
                    raise RuntimeError("Remote FRED ledger has incomplete final line")
                outputs = dict(prepared)
                outputs[LEDGER] = ledger + b"".join(line * count for line, count in missing.items())
                if incoming[HEALTH] != before[HEALTH]:
                    outputs[HEALTH] = incoming[HEALTH]
                    print("[macro_persist] preserved_concurrent_health=true", flush=True)
                run("read-tree", remote, env=index_env)
                for path in PATHS:
                    if outputs[path] == incoming[path]:
                        continue
                    if outputs[path] is None:
                        raise RuntimeError("Unexpected output deletion")
                    oid = run("hash-object", "-w", "--stdin", input=outputs[path]).stdout.decode().strip()
                    run("update-index", "--add", "--cacheinfo", f"100644,{oid},{path}", env=index_env)
                tree = run("write-tree", env=index_env).stdout.decode().strip()
                if tree == run("rev-parse", f"{remote}^{{tree}}").stdout.decode().strip():
                    print(f"[macro_persist] already_persisted={remote} snapshot_sha256={digest}", flush=True)
                    return remote
                commit = run("commit-tree", tree, "-p", remote, input=message).stdout.decode().strip()
                run("push", "origin", f"{commit}:refs/heads/{branch}", phase="push")
                print(f"[macro_persist] persisted_commit={commit} snapshot_sha256={digest} ledger_added={sum(missing.values())}", flush=True)
                return commit
            except GitFailure as exc:
                last_error = exc
                print(f"[macro_persist] attempt={attempt}/{attempts} failed={exc}", flush=True)
                if attempt < attempts:
                    time.sleep(min(retry_delay * attempt, max(0, deadline - time.monotonic())))
    raise GitFailure(f"Persistence retries exhausted: {last_error}; recover saved artifact")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("branch")
    args = parser.parse_args()
    try:
        persist(Path.cwd(), args.branch)
    except (RuntimeError, OSError) as exc:
        raise SystemExit(f"::error::Macro persistence failed: {exc}") from exc


if __name__ == "__main__":
    main()
