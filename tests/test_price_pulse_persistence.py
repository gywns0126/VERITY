"""Price persistence regressions use disposable Git remotes, not broker services."""
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

from scripts.ci import persist_cockpit_snapshot as transport
from scripts.ci import persist_price_pulse as pulse
from tests.test_cockpit_persistence import git, write, commit, state

ROOT = Path(__file__).resolve().parents[1]
PRICE, LOCK = pulse.PATHS
PREPARED = b'{\n  "collected_at": "2026-10-19T23:00:00+09:00", "price": 123\n}\n'


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
    mode = getattr(request, "param", "existing")
    write(writer, PRICE, b'{"generation":"base"}\n')
    write(writer, "code.txt", b"base code\n")
    paths = [PRICE, "code.txt"]
    if mode == "existing":
        write(writer, LOCK, b"2026-10-18\n")
        paths.append(LOCK)
    commit(writer, "baseline", paths)
    git(writer, "push", "origin", "main")
    git(tmp_path, "clone", "--depth=1", "-b", "main", remote.as_uri(), str(producer))
    write(producer, PRICE, PREPARED)
    paths = [PRICE]
    if mode != "missing":
        write(producer, LOCK, b"2026-10-19\n")
        paths.append(LOCK)
    commit(producer, "prepared price pulse", paths)
    return remote, writer, producer


def test_exact_prepared_price_and_date_lock_preserve_remote_code_and_dirty_producer(repos):
    remote, writer, producer = repos
    write(writer, "code.txt", b"concurrent code\n")
    commit(writer, "concurrent code", ["code.txt"])
    git(writer, "push", "origin", "main")
    remote_before = git(remote, "rev-parse", "main").strip()
    write(producer, PRICE, b"uncommitted byproduct\n")
    write(producer, "code.txt", b"staged code\n")
    git(producer, "add", "--", "code.txt")
    write(producer, "code.txt", b"unstaged code\n")
    before = state(producer)
    result = pulse.persist(producer, "main", retry_delay=0)
    assert state(producer) == before
    assert git(remote, "show", f"main:{PRICE}") == PREPARED
    assert git(remote, "show", f"main:{LOCK}") == b"2026-10-19\n"
    assert git(remote, "show", "main:code.txt") == b"concurrent code\n"
    assert git(remote, "rev-parse", result + "^").strip() == remote_before
    assert git(producer, "rev-list", "--count", "FETCH_HEAD").strip() == b"1"
    assert set(git(remote, "diff-tree", "--no-commit-id", "--name-only", "-r", "main")
               .decode().splitlines()) == set(pulse.PATHS)


@pytest.mark.parametrize("path,value", [(PRICE, b'{"generation":"newer"}\n'), (LOCK, b"2026-10-20\n")])
def test_remote_price_or_newer_date_lock_fails_closed(repos, path, value):
    remote, writer, producer = repos
    write(writer, path, value)
    commit(writer, "concurrent generation", [path])
    git(writer, "push", "origin", "main")
    head, before = git(remote, "rev-parse", "main"), state(producer)
    with pytest.raises(RuntimeError, match="Remote price_pulse generation changed"):
        pulse.persist(producer, "main", retry_delay=0)
    assert git(remote, "rev-parse", "main") == head
    assert git(remote, "show", f"main:{path}") == value
    assert state(producer) == before


@pytest.mark.parametrize("repos", ["new", "missing"], indirect=True)
def test_optional_date_lock_initial_absence(repos, request):
    remote, _, producer = repos
    prepared_lock = (producer / LOCK).exists()
    pulse.persist(producer, "main", retry_delay=0)
    assert git(remote, "show", f"main:{PRICE}") == PREPARED
    if prepared_lock:
        assert git(remote, "show", f"main:{LOCK}") == b"2026-10-19\n"
    else:
        assert git(remote, "ls-tree", "main", "--", LOCK) == b""


@pytest.mark.parametrize("repos", ["missing"], indirect=True)
def test_absent_local_lock_does_not_remove_concurrent_remote_lock(repos):
    remote, writer, producer = repos
    write(writer, LOCK, b"2026-10-20\n")
    commit(writer, "first remote date lock", [LOCK])
    git(writer, "push", "origin", "main")
    pulse.persist(producer, "main", retry_delay=0)
    assert git(remote, "show", f"main:{LOCK}") == b"2026-10-20\n"


def test_retries_share_existing_deadline_and_leave_recovery_bytes(repos, monkeypatch):
    remote, _, producer = repos
    original, before = transport.git, state(producer)
    head, deadlines = git(remote, "rev-parse", "main"), []

    def fail_fetch(repo, *args, **kwargs):
        if args[0] == "fetch":
            deadlines.append(kwargs["deadline"])
            assert args[1:4] == ("--depth=1", "--no-tags", "--no-recurse-submodules")
            raise transport.GitFailure("price_pulse_fetch timed out")
        return original(repo, *args, **kwargs)

    monkeypatch.setattr(transport, "git", fail_fetch)
    with pytest.raises(transport.GitFailure, match="retries exhausted"):
        pulse.persist(producer, "main", retry_delay=0)
    assert len(deadlines) == 3 and len(set(deadlines)) == 1
    assert git(remote, "rev-parse", "main") == head
    assert state(producer) == before


def test_unrelated_prepared_file_rejected_before_remote_write(repos):
    remote, _, producer = repos
    write(producer, "code.txt", b"unrelated local code\n")
    commit(producer, "unrelated", ["code.txt"])
    head = git(remote, "rev-parse", "main")
    with pytest.raises(RuntimeError, match="only explicit price_pulse outputs"):
        pulse.persist(producer, "main", retry_delay=0)
    assert git(remote, "rev-parse", "main") == head


def workflow_steps():
    doc = yaml.safe_load((ROOT / ".github/workflows/price_pulse.yml").read_text())
    return doc, doc["jobs"]["pulse"]["steps"]


def test_workflow_recovery_precedes_transport_and_failed_persist_blocks_publish(tmp_path):
    doc, steps = workflow_steps()
    prepare = next(s for s in steps if s.get("id") == "prepare")
    persist = next(s for s in steps if s.get("id") == "commit")
    retain = next(s for s in steps if s.get("uses") == "actions/upload-artifact@v4")
    publish = next(s for s in steps if s.get("uses") == "./.github/actions/publish-data")
    assert steps.index(prepare) < steps.index(retain) < steps.index(persist) < steps.index(publish)
    assert persist["if"] == retain["if"] == "steps.prepare.outputs.changed == '1'"
    assert publish["if"] == "success() && steps.commit.outputs.changed == '1'"
    assert not persist.get("continue-on-error", False)
    assert not retain.get("continue-on-error", False)
    assert retain["with"]["if-no-files-found"] == "error"
    assert retain["with"]["include-hidden-files"] is True
    assert set(retain["with"]["path"].splitlines()) == {"_pulse_recovery/" + p for p in pulse.PATHS}
    assert persist["timeout-minutes"] == 3
    assert doc["jobs"]["pulse"]["timeout-minutes"] == 12
    assert doc["concurrency"] == {"group": "verity-pulse", "cancel-in-progress": False}
    assert "git add data/price_pulse.json\n" in prepare["run"]
    assert "git add data/.kis_issued_date.txt 2>/dev/null || true" in prepare["run"]
    assert not any(term in prepare["run"] + persist["run"] for term in
                   ("git pull", "--autostash", "git rebase", "-X ours", "--force"))
    for step in (prepare, persist):
        subprocess.run(["bash", "-n"], input=step["run"], text=True, check=True)
    # Execute the workflow's persistence shell with a failing stand-in, not Git or KIS.
    fake_python = tmp_path / "python"
    fake_python.write_text("#!/bin/sh\nexit 1\n")
    fake_python.chmod(0o755)
    output = tmp_path / "step-output"
    env = dict(os.environ, PATH=str(tmp_path) + os.pathsep + os.environ["PATH"],
               TARGET_BRANCH="main", GITHUB_OUTPUT=str(output))
    result = subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", persist["run"]], env=env)
    assert result.returncode != 0
    assert not output.exists()  # changed=1 is never emitted after failure.
    result = subprocess.run([sys.executable, str(ROOT / "scripts/ci/persist_price_pulse.py"), "--help"], capture_output=True)
    assert result.returncode == 0


def test_recovery_contains_exact_prepared_commit_not_working_byproduct(repos):
    _, _, producer = repos
    _, steps = workflow_steps()
    prepare = next(s for s in steps if s.get("id") == "prepare")
    archive_shell = prepare["run"].split("mkdir -p _pulse_recovery", 1)[1].rsplit('echo "changed=1"', 1)[0]
    write(producer, PRICE, b"uncommitted changed bytes\n")
    subprocess.run(["bash", "-eo", "pipefail", "-c", "mkdir -p _pulse_recovery" + archive_shell], cwd=producer, check=True)
    assert (producer / "_pulse_recovery" / PRICE).read_bytes() == PREPARED
    assert (producer / "_pulse_recovery" / LOCK).read_bytes() == b"2026-10-19\n"
