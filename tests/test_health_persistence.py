"""Health persistence uses local Git remotes, never production services."""
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

from scripts.ci import persist_cockpit_snapshot as transport
from scripts.ci import persist_health_snapshot as health

ROOT = Path(__file__).resolve().parents[1]


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args],
                                   stderr=subprocess.PIPE, timeout=10)


def write(repo, path, value):
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(value)


def commit(repo, message, paths):
    git(repo, "add", "--", *paths)
    git(repo, "commit", "-m", message)


@pytest.fixture
def repos(tmp_path, monkeypatch, request):
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    for key in ("GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME"):
        monkeypatch.setenv(key, "Offline Test")
    for key in ("GIT_AUTHOR_EMAIL", "GIT_COMMITTER_EMAIL"):
        monkeypatch.setenv(key, "offline@example.invalid")
    remote, writer, producer = (tmp_path / p for p in ("remote.git", "writer", "producer"))
    git(tmp_path, "init", "--bare", str(remote))
    git(tmp_path, "clone", str(remote), str(writer))
    git(writer, "checkout", "-b", "main")
    baseline_paths = health.PATHS[:-1] if getattr(request, "param", "") in ("new", "missing") else health.PATHS
    for path in baseline_paths:
        write(writer, path, b'{"generation":"base"}\n')
    write(writer, "code.txt", b"base code\n")
    commit(writer, "baseline", [*baseline_paths, "code.txt"])
    git(writer, "push", "origin", "main")
    git(tmp_path, "clone", "--depth=1", "-b", "main", remote.as_uri(), str(producer))
    prepared_paths = health.PATHS[:-1] if getattr(request, "param", "") == "missing" else health.PATHS
    for path in prepared_paths:
        value = b'{"generation":"prepared"}\n'
        if path.endswith(".jsonl"):
            value = b'{"generation":"base"}\n' + value
        write(producer, path, value)
    commit(producer, "prepared health", prepared_paths)
    return remote, writer, producer


def state(producer):
    return (git(producer, "rev-parse", "HEAD"), (producer / ".git/index").read_bytes(),
            git(producer, "status", "--porcelain"),
            {str(p.relative_to(producer)): p.read_bytes() for p in producer.rglob("*")
             if p.is_file() and ".git" not in p.relative_to(producer).parts})


def test_health_preserves_code_merge_without_ancestry_or_producer_mutation(repos):
    remote, writer, producer = repos
    git(writer, "checkout", "-b", "side")
    for i in range(6):
        write(writer, "side.txt", f"side {i}\n".encode())
        commit(writer, f"side change {i}", ["side.txt"])
    git(writer, "checkout", "main")
    write(writer, "code.txt", b"concurrent code\n")
    commit(writer, "concurrent code", ["code.txt"])
    git(writer, "merge", "--no-ff", "side", "-m", "concurrent merge")
    git(writer, "push", "origin", "main")
    write(producer, "untracked.txt", b"private byproduct\n")
    write(producer, "code.txt", b"dirty code\n")
    before = state(producer)
    result = health.persist(producer, "main", retry_delay=0)
    assert state(producer) == before
    assert git(remote, "rev-parse", "main").decode().strip() == result
    assert git(remote, "show", "main:code.txt") == b"concurrent code\n"
    assert git(remote, "show", "main:side.txt") == b"side 5\n"
    assert git(producer, "rev-list", "--count", "FETCH_HEAD").strip() == b"1"
    for path in health.PATHS:
        assert git(remote, "show", f"main:{path}") == (producer / path).read_bytes()
    assert set(git(remote, "diff-tree", "--no-commit-id", "--name-only", "-r", "main")
               .decode().splitlines()) == set(health.PATHS)


@pytest.mark.parametrize("path", health.PATHS)
def test_any_remote_health_change_including_jsonl_is_preserved_and_rejected(repos, path):
    remote, writer, producer = repos
    write(writer, path, b'{"generation":"base"}\n{"generation":"remote"}\n')
    commit(writer, "concurrent health", [path])
    git(writer, "push", "origin", "main")
    remote_head, before = git(remote, "rev-parse", "main"), state(producer)
    with pytest.raises(RuntimeError, match="Remote health generation changed"):
        health.persist(producer, "main", retry_delay=0)
    assert git(remote, "rev-parse", "main") == remote_head
    assert state(producer) == before  # Prepared files remain available to artifact upload.


def test_health_transport_exhaustion_uses_one_budget_and_keeps_recovery_files(repos, monkeypatch):
    remote, _, producer = repos
    original, before = transport.git, state(producer)
    head, deadlines = git(remote, "rev-parse", "main"), []

    def fail_fetch(repo, *args, **kwargs):
        if args[0] == "fetch":
            deadlines.append(kwargs["deadline"])
            assert "--depth=1" in args
            raise transport.GitFailure("health_fetch timed out")
        return original(repo, *args, **kwargs)

    monkeypatch.setattr(transport, "git", fail_fetch)
    with pytest.raises(transport.GitFailure, match="Health persistence retries exhausted"):
        health.persist(producer, "main", retry_delay=0)
    assert len(deadlines) == 3 and len(set(deadlines)) == 1
    assert git(remote, "rev-parse", "main") == head
    assert state(producer) == before


def test_health_duplicate_snapshot_is_idempotent(repos):
    remote, writer, producer = repos
    for path in health.PATHS:
        write(writer, path, (producer / path).read_bytes())
    commit(writer, "already stored health", health.PATHS)
    git(writer, "push", "origin", "main")
    head = git(remote, "rev-parse", "main").decode().strip()
    assert health.persist(producer, "main", retry_delay=0) == head


def test_health_rejects_prepared_code_change(repos):
    remote, _, producer = repos
    write(producer, "code.txt", b"unrelated\n")
    commit(producer, "unrelated", ["code.txt"])
    head = git(remote, "rev-parse", "main")
    with pytest.raises(RuntimeError, match="only explicit health outputs"):
        health.persist(producer, "main", retry_delay=0)
    assert git(remote, "rev-parse", "main") == head


@pytest.mark.parametrize("repos", ["new"], indirect=True)
def test_new_us_receipt_can_be_created_without_base_blob(repos):
    remote, _, producer = repos
    health.persist(producer, "main", retry_delay=0)
    assert git(remote, "show", f"main:{health.PATHS[-1]}") == (producer / health.PATHS[-1]).read_bytes()


@pytest.mark.parametrize("repos", ["new"], indirect=True)
def test_different_concurrent_first_us_receipt_is_not_overwritten(repos):
    remote, writer, producer = repos
    path = health.PATHS[-1]
    write(writer, path, b'{"remote":true}\n')
    commit(writer, "first remote US receipt", [path])
    git(writer, "push", "origin", "main")
    head = git(remote, "rev-parse", "main")
    with pytest.raises(RuntimeError, match="generation changed"):
        health.persist(producer, "main", retry_delay=0)
    assert git(remote, "rev-parse", "main") == head


@pytest.mark.parametrize("repos", ["missing"], indirect=True)
@pytest.mark.parametrize("remote_created", [False, True])
def test_failed_first_us_producer_preserves_six_outputs_and_remote_receipt(repos, remote_created, capsys):
    remote, writer, producer = repos
    path = health.PATHS[-1]
    if remote_created:
        write(writer, path, b'{"remote":true}\n')
        commit(writer, "first remote receipt", [path])
        git(writer, "push", "origin", "main")
    health.persist(producer, "main", retry_delay=0)
    assert f"optional_output_not_prepared={path}" in capsys.readouterr().out
    for item in health.PATHS[:-1]:
        assert git(remote, "show", f"main:{item}") == (producer / item).read_bytes()
    if remote_created:
        assert git(remote, "show", f"main:{path}") == b'{"remote":true}\n'
    else:
        assert git(remote, "ls-tree", "main", "--", path) == b""


def test_existing_us_receipt_cannot_be_deleted(repos):
    remote, _, producer = repos
    git(producer, "rm", "--", health.PATHS[-1])
    git(producer, "commit", "-m", "deleted receipt")
    head = git(remote, "rev-parse", "main")
    with pytest.raises(RuntimeError, match="deletion is not allowed"):
        health.persist(producer, "main", retry_delay=0)
    assert git(remote, "rev-parse", "main") == head


def test_workflow_keeps_monitor_policy_and_preserves_seven_outputs_before_transport():
    doc = yaml.safe_load((ROOT / ".github/workflows/cron_health_monitor.yml").read_text())
    job = doc["jobs"]["monitor"]
    assert job["concurrency"] == {"group": "cron-health-monitor", "cancel-in-progress": False}
    steps = job["steps"]
    persist = next(s for s in steps if s.get("id") == "persist")
    retain = next(s for s in steps if s.get("uses") == "actions/upload-artifact@v4")
    monitor = next(s for s in steps if s.get("name") == "Run health monitor")
    assert '--hours $HOURS --notify' in monitor["run"]
    assert '--always-notify' in monitor["run"]
    assert persist["if"] == "success() || failure()"
    assert persist["timeout-minutes"] == 3
    assert "persist_health_snapshot.py" in persist["run"]
    assert 'git add -- "$path"' in persist["run"]
    assert 'test -f "$path"' in persist["run"]
    assert all(term not in persist["run"] for term in ("git pull", "--autostash", "git rebase", "-X ours", "--force"))
    assert retain["if"] == "success() || failure()"
    assert steps.index(monitor) < steps.index(retain) < steps.index(persist)
    assert retain["with"]["name"] == "health-prepared-${{ github.run_id }}"
    assert set(retain["with"]["path"].splitlines()) == set(health.PATHS)
    assert len(health.PATHS) == 7
    for path in health.PATHS:
        assert path in persist["run"]
    subprocess.run(["bash", "-n"], input=persist["run"], text=True, check=True)
    result = subprocess.run([sys.executable, str(ROOT / "scripts/ci/persist_health_snapshot.py"),
                             "--help"], capture_output=True, text=True)
    assert result.returncode == 0
