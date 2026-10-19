#!/usr/bin/env python3
"""Persist only the two prepared cockpit outputs on the latest remote tree.

The five-minute job must not fetch ancestry or rebase a shallow checkout across
concurrent merges. Reuse the bounded Git transport and process-group cleanup
already used by macro persistence; leave the producer's index and files intact.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import tempfile
import time

try:
    from .persist_macro_snapshot import GitFailure, git
except ImportError:  # Direct workflow invocation.
    from persist_macro_snapshot import GitFailure, git

PATHS = ("data/metadata/cockpit_state.json", "data/metadata/system_map.json")


def persist(repo, branch, attempts=3, budget_s=120, retry_delay=2, *, paths=None, label="cockpit"):
    # Health uses the same whole-blob conflict policy with its own explicit list.
    paths = tuple(PATHS if paths is None else paths)
    deadline = time.monotonic() + budget_s

    def run(*args, **kwargs):
        return git(repo, *args, deadline=deadline, phase=kwargs.pop("phase", args[0]), **kwargs)

    def blob(ref, path):
        return run("show", f"{ref}:{path}", phase="read_output").stdout

    run("check-ref-format", f"refs/heads/{branch}")
    source = run("rev-parse", "HEAD").stdout.decode().strip()
    base = run("rev-parse", "HEAD^").stdout.decode().strip()
    changed = run("diff-tree", "--no-commit-id", "--name-only", "-r", source).stdout.decode().splitlines()
    if not changed or set(changed) - set(paths):
        raise RuntimeError(f"Prepared commit must contain only explicit {label} outputs")
    prepared = {path: blob(source, path) for path in paths}
    before = {path: blob(base, path) for path in paths}
    message = run("log", "-1", "--format=%B", source).stdout
    last_error = None
    with tempfile.TemporaryDirectory(prefix=f"{label}-persist-") as temp:
        index_env = {"GIT_INDEX_FILE": str(Path(temp) / "index")}
        for attempt in range(1, attempts + 1):
            try:
                # No missing merge-parent history, tags, or submodule traversal.
                run("fetch", "--depth=1", "--no-tags", "--no-recurse-submodules",
                    "origin", f"refs/heads/{branch}", phase=f"{label}_fetch")
                remote = run("rev-parse", "FETCH_HEAD").stdout.decode().strip()
                incoming = {path: blob(remote, path) for path in paths}
                if any(incoming[path] not in (before[path], prepared[path]) for path in paths):
                    raise RuntimeError(f"Remote {label} generation changed; preserve remote and recover artifact")
                run("read-tree", remote, env=index_env)
                for path in paths:
                    oid = run("hash-object", "-w", "--stdin", input=prepared[path]).stdout.decode().strip()
                    run("update-index", "--add", "--cacheinfo", f"100644,{oid},{path}", env=index_env)
                tree = run("write-tree", env=index_env).stdout.decode().strip()
                if tree == run("rev-parse", f"{remote}^{{tree}}").stdout.decode().strip():
                    print(f"[{label}_persist] already_persisted={remote}", flush=True)
                    return remote
                commit = run("commit-tree", tree, "-p", remote, input=message).stdout.decode().strip()
                run("push", "origin", f"{commit}:refs/heads/{branch}", phase=f"{label}_push")
                print(f"[{label}_persist] persisted_commit={commit}", flush=True)
                return commit
            except GitFailure as exc:
                last_error = exc
                print(f"[{label}_persist] attempt={attempt}/{attempts} failed={exc}", flush=True)
                if attempt < attempts:
                    time.sleep(min(retry_delay * attempt, max(0, deadline - time.monotonic())))
    raise GitFailure(f"{label.capitalize()} persistence retries exhausted: {last_error}; recover saved artifact")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("branch")
    args = parser.parse_args()
    try:
        persist(Path.cwd(), args.branch)
    except (RuntimeError, OSError) as exc:
        raise SystemExit(f"::error::Cockpit persistence failed: {exc}") from exc


if __name__ == "__main__":
    main()
