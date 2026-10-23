from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from scripts.ci.realtime_portfolio_write_guard import (
    GuardError,
    RebaseFailed,
    SnapshotChanged,
    capture_analysis_head,
    compare_analysis_inputs,
    prepare_push,
)

ROOT = Path(__file__).resolve().parents[1]


def _git(path: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", "-C", str(path), *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=check,
    )
    return result.stdout.strip()


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def _init_repos(tmp_path: Path):
    bare = tmp_path / "remote.git"
    seed = tmp_path / "seed"
    _git(tmp_path, "init", "--bare", "--initial-branch=main", str(bare))
    seed.mkdir()
    _git(seed, "init", "--initial-branch=main")
    _git(seed, "config", "user.name", "fixture")
    _git(seed, "config", "user.email", "fixture@example.invalid")
    (seed / ".gitattributes").write_text("data/portfolio.json binary -diff -merge -text\n", encoding="utf-8")
    _write_json(seed / "data/portfolio.json", {
        "updated_at": "base",
        "vams": {"cash": 100, "holdings": [{"ticker": "PARR", "quantity": 10, "current_price": 10}]},
        "exec_paper": {"summary": "base"},
    })
    _write_json(seed / "data/history.json", [
        {"type": "BUY", "ticker": "PARR", "quantity": 10, "date": "2026-09-24"},
    ])
    _git(seed, "add", ".gitattributes", "data/portfolio.json", "data/history.json")
    _git(seed, "commit", "-m", "initial input")
    _git(seed, "remote", "add", "origin", str(bare))
    _git(seed, "push", "-u", "origin", "main")
    runner = tmp_path / "runner"
    competitor = tmp_path / "competitor"
    _git(tmp_path, "clone", str(bare), str(runner))
    _git(tmp_path, "clone", str(bare), str(competitor))
    for repo in (runner, competitor):
        assert _git(repo, "check-attr", "merge", "--", "data/portfolio.json") == "data/portfolio.json: merge: unset"
        _git(repo, "config", "user.name", "fixture")
        _git(repo, "config", "user.email", "fixture@example.invalid")
    base = _git(runner, "rev-parse", "HEAD")
    return bare, runner, competitor, base


def _commit_json(repo: Path, rel: str, mutate, message: str) -> str:
    path = repo / rel
    doc = json.loads(path.read_text(encoding="utf-8"))
    mutate(doc)
    _write_json(path, doc)
    _git(repo, "add", rel)
    _git(repo, "commit", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def _local_realtime_commit(runner: Path) -> None:
    _commit_json(
        runner,
        "data/portfolio.json",
        lambda doc: doc.update(updated_at="realtime", vams={**doc["vams"], "holdings": [{**doc["vams"]["holdings"][0], "current_price": 12}]}),
        "realtime snapshot",
    )


def test_capture_requires_actual_analysis_inputs_to_match_head(tmp_path):
    _bare, runner, _competitor, base = _init_repos(tmp_path)
    assert capture_analysis_head(runner) == base
    (runner / "data/portfolio.json").write_text("{}\n", encoding="utf-8")
    with pytest.raises(GuardError, match="analysis_input_differs_from_head"):
        capture_analysis_head(runner)


def test_prepare_push_rejects_tracked_changes_instead_of_autostashing(tmp_path):
    _bare, runner, _competitor, base = _init_repos(tmp_path)
    (runner / "data/portfolio.json").write_text("{}\n", encoding="utf-8")
    with pytest.raises(GuardError, match="tracked_worktree_not_clean"):
        prepare_push(runner, base, "origin", "main")
    assert _git(runner, "rev-parse", "HEAD") == base


def test_authoritative_vams_and_history_change_rejects_stale_realtime_commit(tmp_path):
    bare, runner, competitor, base = _init_repos(tmp_path)
    _local_realtime_commit(runner)
    _commit_json(
        competitor,
        "data/portfolio.json",
        lambda doc: doc.update(vams={"cash": 200, "holdings": []}),
        "full closes position",
    )
    _commit_json(
        competitor,
        "data/history.json",
        lambda rows: rows.append({"type": "SELL", "ticker": "PARR", "quantity": 10, "date": "2026-10-23"}),
        "full ledger sell",
    )
    _git(competitor, "push", "origin", "main")
    remote_head = _git(competitor, "rev-parse", "HEAD")
    with pytest.raises(SnapshotChanged) as caught:
        prepare_push(runner, base, "origin", "main")
    assert set(caught.value.codes) == {"portfolio_vams_changed", "history_changed"}
    blocked_push = subprocess.run(
        ["git", "-C", str(runner), "push", "origin", "HEAD:main"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert blocked_push.returncode != 0
    assert _git(runner, "ls-remote", "origin", "refs/heads/main").split()[0] == remote_head
    # The failed guard did not rewrite the authoritative remote pointer.
    assert _git(bare, "rev-parse", "refs/heads/main") == remote_head


def test_exec_paper_only_change_passes_snapshot_check_but_binary_conflict_fails_closed(tmp_path):
    bare, runner, competitor, base = _init_repos(tmp_path)
    _local_realtime_commit(runner)
    _commit_json(
        competitor,
        "data/portfolio.json",
        lambda doc: doc.update(exec_paper={"summary": "new remote paper state"}),
        "exec paper update",
    )
    remote_head = _git(competitor, "rev-parse", "HEAD")
    _git(competitor, "push", "origin", "main")

    _git(runner, "fetch", "--no-tags", "origin", "main")
    compare_analysis_inputs(runner, base, remote_head)
    with pytest.raises(RebaseFailed, match="rebase_failed"):
        prepare_push(runner, base, "origin", "main")
    assert _git(bare, "rev-parse", "refs/heads/main") == remote_head
    assert _git(runner, "rev-parse", "HEAD") != remote_head


def test_unrelated_remote_file_change_rebases_and_is_preserved(tmp_path):
    bare, runner, competitor, base = _init_repos(tmp_path)
    _local_realtime_commit(runner)
    (competitor / "docs").mkdir()
    (competitor / "docs/remote-note.txt").write_text("unrelated remote update\n", encoding="utf-8")
    _git(competitor, "add", "docs/remote-note.txt")
    _git(competitor, "commit", "-m", "unrelated file update")
    remote_head = _git(competitor, "rev-parse", "HEAD")
    _git(competitor, "push", "origin", "main")

    assert prepare_push(runner, base, "origin", "main") == remote_head
    _git(runner, "push", "origin", "HEAD:main")
    assert _git(bare, "show", "main:docs/remote-note.txt") == "unrelated remote update"
    merged = json.loads(_git(bare, "show", "main:data/portfolio.json"))
    assert merged["updated_at"] == "realtime"
    assert merged["vams"]["holdings"][0]["current_price"] == 12


def test_change_after_guard_causes_non_ff_then_next_attempt_rejects(tmp_path):
    bare, runner, competitor, base = _init_repos(tmp_path)
    _local_realtime_commit(runner)

    # First check/rebase passes against the fetched base.
    assert prepare_push(runner, base, "origin", "main") == base
    # The authoritative full writer advances after the check but before realtime push.
    _commit_json(
        competitor,
        "data/portfolio.json",
        lambda doc: doc.update(vams={"cash": 200, "holdings": []}),
        "full VAMS update in race window",
    )
    _commit_json(
        competitor,
        "data/history.json",
        lambda rows: rows.append({"type": "SELL", "ticker": "PARR", "quantity": 10, "date": "2026-10-23"}),
        "full ledger update in race window",
    )
    authoritative = _git(competitor, "rev-parse", "HEAD")
    _git(competitor, "push", "origin", "main")

    first_push = subprocess.run(
        ["git", "-C", str(runner), "push", "origin", "HEAD:main"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert first_push.returncode != 0  # non-fast-forward, no force push
    with pytest.raises(SnapshotChanged):
        prepare_push(runner, base, "origin", "main")
    assert _git(bare, "rev-parse", "refs/heads/main") == authoritative
    assert _git(bare, "show", "main:data/portfolio.json")


def test_workflow_captures_before_analysis_and_checks_each_push_attempt():
    text = (ROOT / ".github/workflows/daily_realtime.yml").read_text(encoding="utf-8")
    assert text.index("Capture analysis input HEAD") < text.index("- name: Run analysis")
    block = text[text.index("- name: Commit & push results"):text.index("- name: Publish hot data")]
    assert "prepare-push" in block
    assert "ANALYSIS_INPUT_HEAD" in block
    assert block.index("prepare-push") < block.index("git push origin")
    assert "git pull --rebase" not in block
    assert "--autostash" not in block
    assert "-X theirs" not in block
    assert 'if [ "$rc" -eq 4 ]; then' in block
