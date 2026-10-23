#!/usr/bin/env python3
"""Fail closed before realtime output can reintroduce stale VAMS state.

Capture the exact Git commit whose portfolio/history files enter analysis. Before each
push attempt, fetch the destination branch, compare that captured VAMS projection and
full trade history with the fetched tree, then rebase onto that exact fetched commit.
Unrelated files can rebase normally; a conflicting binary portfolio change stops
without replacing the newer remote snapshot.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any

PORTFOLIO_PATH = "data/portfolio.json"
HISTORY_PATH = "data/history.json"
_SHA_RE = re.compile(r"^[0-9a-fA-F]{40,64}$")


class GuardError(RuntimeError):
    """Safe, closed diagnostic only; never includes file contents or Git stderr."""


class SnapshotChanged(GuardError):
    def __init__(self, codes: tuple[str, ...]):
        self.codes = codes
        super().__init__(",".join(codes))


class RebaseFailed(GuardError):
    """The local commit could not be safely replayed; do not retry this snapshot."""


def _git(repo: Path, *args: str, input_bytes: bytes | None = None) -> bytes:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), *args],
            input=input_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise GuardError("git_operation_failed") from exc
    return result.stdout


def capture_analysis_head(repo: Path) -> str:
    """Return HEAD only when the two analysis inputs exactly match its tracked tree."""
    head = _git(repo, "rev-parse", "--verify", "HEAD^{commit}").decode().strip()
    if not _SHA_RE.fullmatch(head):
        raise GuardError("invalid_analysis_head")
    for rel in (PORTFOLIO_PATH, HISTORY_PATH):
        try:
            working = (repo / rel).read_bytes()
            tracked = _git(repo, "show", f"{head}:{rel}")
        except OSError as exc:
            raise GuardError("analysis_input_unreadable") from exc
        if working != tracked:
            raise GuardError("analysis_input_differs_from_head")
    return head


def _reject_constant() -> None:
    raise ValueError("nonstandard_json_constant")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_json_key")
        result[key] = value
    return result


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _read_json_at(repo: Path, commit: str, rel: str) -> Any:
    try:
        raw = _git(repo, "show", f"{commit}:{rel}")
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=lambda _x: _reject_constant(),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise GuardError("snapshot_json_invalid") from exc
    except GuardError:
        raise GuardError("snapshot_file_unavailable") from None
    return value


def compare_analysis_inputs(repo: Path, analysis_head: str, remote_head: str) -> None:
    """Raise on missing/invalid inputs or if VAMS/history changed since analysis began."""
    base = _checked_sha_for(repo, analysis_head, "analysis_head")
    latest = _checked_sha_for(repo, remote_head, "remote_head")
    base_portfolio = _read_json_at(repo, base, PORTFOLIO_PATH)
    latest_portfolio = _read_json_at(repo, latest, PORTFOLIO_PATH)
    base_history = _read_json_at(repo, base, HISTORY_PATH)
    latest_history = _read_json_at(repo, latest, HISTORY_PATH)
    if not isinstance(base_portfolio, dict) or not isinstance(latest_portfolio, dict):
        raise GuardError("portfolio_shape_invalid")
    if not isinstance(base_portfolio.get("vams"), dict) or not isinstance(latest_portfolio.get("vams"), dict):
        raise GuardError("vams_projection_missing")
    if not isinstance(base_history, list) or not isinstance(latest_history, list):
        raise GuardError("history_shape_invalid")
    changed = []
    if _canonical(base_portfolio["vams"]) != _canonical(latest_portfolio["vams"]):
        changed.append("portfolio_vams_changed")
    if _canonical(base_history) != _canonical(latest_history):
        changed.append("history_changed")
    if changed:
        raise SnapshotChanged(tuple(changed))


def _checked_sha_for(repo: Path, value: str, label: str) -> str:
    if not isinstance(value, str) or not _SHA_RE.fullmatch(value):
        raise GuardError(f"invalid_{label}")
    try:
        resolved = _git(repo, "rev-parse", "--verify", f"{value}^{{commit}}").decode().strip()
    except GuardError:
        raise GuardError(f"unresolved_{label}") from None
    if not _SHA_RE.fullmatch(resolved):
        raise GuardError(f"unresolved_{label}")
    return resolved


def prepare_push(repo: Path, analysis_head: str, remote: str, branch: str) -> str:
    """Fetch, guard against that exact FETCH_HEAD, and rebase without conflict preference."""
    if not branch or branch.startswith("-") or not re.fullmatch(r"[A-Za-z0-9._/-]+", branch):
        raise GuardError("invalid_branch")
    if not remote or remote.startswith("-") or not re.fullmatch(r"[A-Za-z0-9._-]+", remote):
        raise GuardError("invalid_remote")
    _checked_sha_for(repo, analysis_head, "analysis_head")
    # Do not use --autostash: Git may return success while a stash pop conflicts.
    # A push is permitted only from a clean tracked tree after the analysis commit.
    if _git(repo, "status", "--porcelain", "--untracked-files=no").strip():
        raise GuardError("tracked_worktree_not_clean")
    # Clear only an incomplete rebase left by a previous push attempt in this ephemeral runner.
    if (repo / ".git" / "rebase-merge").exists() or (repo / ".git" / "rebase-apply").exists():
        _git(repo, "rebase", "--abort")
    _git(repo, "fetch", "--no-tags", remote, branch)
    remote_head = _git(repo, "rev-parse", "--verify", "FETCH_HEAD^{commit}").decode().strip()
    compare_analysis_inputs(repo, analysis_head, remote_head)
    # No -X theirs: unresolved line-level conflicts must stop rather than prefer stale output.
    try:
        _git(repo, "rebase", remote_head)
    except GuardError:
        try:
            _git(repo, "rebase", "--abort")
        except GuardError:
            pass
        raise RebaseFailed("rebase_failed") from None
    return remote_head


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    capture = sub.add_parser("capture")
    capture.add_argument("--repo", type=Path, default=Path.cwd())
    capture.add_argument("--output", type=Path, required=True)
    prepare = sub.add_parser("prepare-push")
    prepare.add_argument("--repo", type=Path, default=Path.cwd())
    prepare.add_argument("--analysis-head", required=True)
    prepare.add_argument("--remote", default="origin")
    prepare.add_argument("--branch", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "capture":
            head = capture_analysis_head(args.repo)
            with args.output.open("a", encoding="utf-8") as f:
                f.write(f"analysis_head={head}\n")
            print("[realtime-write-guard] captured analysis input commit")
            return 0
        remote_head = prepare_push(args.repo, args.analysis_head, args.remote, args.branch)
        print(f"[realtime-write-guard] snapshot unchanged; rebased on {remote_head}")
        return 0
    except SnapshotChanged as exc:
        print("::error::[realtime-write-guard] stale input; next natural run must refresh (" + ",".join(exc.codes) + ")")
        return 3
    except RebaseFailed as exc:
        print("::error::[realtime-write-guard] rebase could not be proven safe; no push attempted (" + str(exc) + ")")
        return 4
    except GuardError as exc:
        print("::error::[realtime-write-guard] unable to prove safe write (" + str(exc) + ")")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
