"""Cockpit persistence against local remotes only; no production writes."""
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

from scripts.ci import persist_cockpit_snapshot as module

ROOT = Path(__file__).resolve().parents[1]


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args], stderr=subprocess.PIPE, timeout=10)


def write(repo, path, value):
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(value)


def commit(repo, message, paths):
    git(repo, "add", "--", *paths)
    git(repo, "commit", "-m", message)


@pytest.fixture
def repos(tmp_path, monkeypatch):
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    # Identities inherited by commit-tree, including detached CI checkouts.
    for key in ("GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME"):
        monkeypatch.setenv(key, "Offline Test")
    for key in ("GIT_AUTHOR_EMAIL", "GIT_COMMITTER_EMAIL"):
        monkeypatch.setenv(key, "offline@example.invalid")
    remote, writer, producer = (tmp_path / p for p in ("remote.git", "writer", "producer"))
    git(tmp_path, "init", "--bare", str(remote))
    git(tmp_path, "clone", str(remote), str(writer))
    git(writer, "checkout", "-b", "main")
    for path in module.PATHS:
        write(writer, path, b'{"generation":"base"}\n')
    write(writer, "code.txt", b"base code\n")
    commit(writer, "baseline", [*module.PATHS, "code.txt"])
    git(writer, "push", "origin", "main")
    git(tmp_path, "clone", "--depth=1", "-b", "main", remote.as_uri(), str(producer))
    for path in module.PATHS:
        write(producer, path, b'{"generation":"prepared"}\n')
    commit(producer, "prepared cockpit", module.PATHS)
    return remote, writer, producer


def state(producer):
    return (git(producer, "rev-parse", "HEAD"), (producer / ".git/index").read_bytes(),
            git(producer, "status", "--porcelain"),
            {str(p.relative_to(producer)): p.read_bytes() for p in producer.rglob("*")
             if p.is_file() and ".git" not in p.relative_to(producer).parts})


def test_shallow_merge_does_not_fetch_missing_ancestry_or_change_dirty_producer(repos):
    remote, writer, producer = repos
    # A side-parent diverges behind the CI clone's shallow boundary.
    git(writer, "checkout", "-b", "side")
    for i in range(6):
        write(writer, "side.txt", f"side {i}\n".encode())
        commit(writer, f"side change {i}", ["side.txt"])
    git(writer, "checkout", "main")
    write(writer, "code.txt", b"concurrent code\n")
    commit(writer, "concurrent code", ["code.txt"])
    git(writer, "merge", "--no-ff", "side", "-m", "concurrent merge")
    git(writer, "push", "origin", "main")
    # The former unbounded pull fetched side-parent ancestry despite depth=1 checkout.
    git(producer, "fetch", "origin", "main")
    assert int(git(producer, "rev-list", "--count", "FETCH_HEAD")) > 6
    write(producer, "code.txt", b"private dirty code\n")
    write(producer, "untracked.txt", b"private byproduct\n")
    before = state(producer)
    result = module.persist(producer, "main", retry_delay=0)
    assert state(producer) == before
    assert git(remote, "rev-parse", "main").decode().strip() == result
    assert git(remote, "show", "main:code.txt") == b"concurrent code\n"
    assert git(remote, "show", "main:side.txt") == b"side 5\n"
    assert git(producer, "rev-list", "--count", "FETCH_HEAD").strip() == b"1"
    for path in module.PATHS:
        assert git(remote, "show", f"main:{path}") == b'{"generation":"prepared"}\n'
    assert set(git(remote, "diff-tree", "--no-commit-id", "--name-only", "-r", "main")
               .decode().splitlines()) == set(module.PATHS)


def test_newer_remote_generation_is_never_overwritten(repos):
    remote, writer, producer = repos
    path = module.PATHS[0]
    write(writer, path, b'{"generation":"newer"}\n')
    commit(writer, "newer cockpit", [path])
    git(writer, "push", "origin", "main")
    head, before = git(remote, "rev-parse", "main"), state(producer)
    with pytest.raises(RuntimeError, match="generation changed"):
        module.persist(producer, "main", retry_delay=0)
    assert git(remote, "rev-parse", "main") == head
    assert state(producer) == before


def test_push_rejection_retries_fresh_remote_without_losing_code(repos, monkeypatch):
    remote, writer, producer = repos
    original = module.git
    calls = []

    def racing(repo, *args, **kwargs):
        calls.append(args[0])
        if args[0] == "push" and calls.count("push") == 1:
            write(writer, "code.txt", b"late concurrent code\n")
            commit(writer, "late code", ["code.txt"])
            git(writer, "push", "origin", "main")
        return original(repo, *args, **kwargs)

    monkeypatch.setattr(module, "git", racing)
    module.persist(producer, "main", retry_delay=0)
    assert calls.count("push") == calls.count("fetch") == 2
    assert git(remote, "show", "main:code.txt") == b"late concurrent code\n"


def test_exhausted_transport_fails_closed_and_existing_budget_is_reused(repos, monkeypatch):
    remote, _, producer = repos
    original, head = module.git, git(remote, "rev-parse", "main")
    fetches = []

    def unavailable(repo, *args, **kwargs):
        if args[0] == "fetch":
            fetches.append(kwargs)
            raise module.GitFailure("cockpit_fetch timed out")
        return original(repo, *args, **kwargs)

    monkeypatch.setattr(module, "git", unavailable)
    with pytest.raises(module.GitFailure, match="retries exhausted"):
        module.persist(producer, "main", retry_delay=0)
    assert len(fetches) == 3
    assert len({call["deadline"] for call in fetches}) == 1
    assert git(remote, "rev-parse", "main") == head


def test_already_applied_outputs_are_idempotent_after_uncertain_push_result(repos):
    remote, writer, producer = repos
    for path in module.PATHS:
        write(writer, path, b'{"generation":"prepared"}\n')
    commit(writer, "already stored cockpit", module.PATHS)
    git(writer, "push", "origin", "main")
    head = git(remote, "rev-parse", "main").decode().strip()
    assert module.persist(producer, "main", retry_delay=0) == head
    assert git(remote, "rev-parse", "main").decode().strip() == head


def test_unrelated_prepared_commit_is_rejected_before_remote_write(repos):
    remote, _, producer = repos
    write(producer, "code.txt", b"must not publish\n")
    commit(producer, "unrelated local commit", ["code.txt"])
    head = git(remote, "rev-parse", "main")
    with pytest.raises(RuntimeError, match="only explicit cockpit"):
        module.persist(producer, "main", retry_delay=0)
    assert git(remote, "rev-parse", "main") == head


def test_workflow_stops_publication_and_retains_outputs_on_persistence_failure():
    doc = yaml.safe_load((ROOT / ".github/workflows/cockpit_aggregate.yml").read_text())
    steps = doc["jobs"]["aggregate"]["steps"]
    persist = next(s for s in steps if s.get("id") == "persist")
    publish = next(s for s in steps if s.get("uses") == "./.github/actions/publish-data")
    retain = next(s for s in steps if s.get("uses") == "actions/upload-artifact@v4")
    assert publish["if"] == "success()"
    assert retain["if"] == "failure() && steps.persist.outcome == 'failure'"
    assert set(retain["with"]["path"].splitlines()) == set(module.PATHS)
    assert "persist_cockpit_snapshot.py" in persist["run"]
    assert "git pull" not in persist["run"] and "--autostash" not in persist["run"]
    result = subprocess.run([sys.executable, str(ROOT / "scripts/ci/persist_cockpit_snapshot.py"),
                             "--help"], capture_output=True, text=True)
    assert result.returncode == 0
