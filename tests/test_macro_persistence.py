"""Offline persistence regressions using disposable local Git repositories."""
import importlib.util
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from unittest.mock import Mock

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "macro_persistence_under_test", ROOT / "scripts/ci/persist_macro_snapshot.py"
)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)

BASE_ROW = b'{"entry":"baseline"}\n'
LOCAL_ROW = b'{"entry":"local"}\n'
REMOTE_ROW = b'{"entry":"remote"}\n'
SNAPSHOT = b'{\n  "collected_at": "2026-10-18T12:00:00+09:00",\n  "value": 12\n}\n'


class LocalRepositories:
    def __init__(self, root):
        self.root = root
        self.remote = root / "remote.git"
        self.producer = root / "producer"
        self.writer = root / "writer"
        self.git(root, "init", "--bare", str(self.remote))
        self.git(root, "clone", str(self.remote), str(self.producer))
        self.configure(self.producer)
        self.git(self.producer, "checkout", "-b", "main")
        self.write(self.producer, module.SNAPSHOT, b'{"collected_at":"old"}\n')
        self.write(self.producer, module.LEDGER, BASE_ROW)
        self.write(self.producer, module.HEALTH, b'{\n"macro":0,\n"scan":0\n}\n')
        self.write(self.producer, "unrelated.txt", b"base\n")
        self.commit(self.producer, "baseline")
        self.git(self.producer, "push", "-u", "origin", "main")
        self.git(root, "clone", "-b", "main", str(self.remote), str(self.writer))
        self.configure(self.writer)
        self.write(self.producer, module.SNAPSHOT, SNAPSHOT)
        self.write(self.producer, module.LEDGER, BASE_ROW + LOCAL_ROW)
        self.write(self.producer, module.HEALTH, b'{"macro":"local"}\n')
        self.commit(self.producer, "prepared macro")

    def git(self, repo, *args):
        return subprocess.run(
            ["git", "-C", str(repo), *args], check=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10,
        ).stdout

    def configure(self, repo):
        self.git(repo, "config", "user.name", "Offline Test")
        self.git(repo, "config", "user.email", "offline@example.invalid")
        self.git(repo, "config", "commit.gpgsign", "false")
        self.git(repo, "config", "core.hooksPath", "/dev/null")

    def write(self, repo, path, data):
        target = repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    def commit(self, repo, message, amend=False):
        self.git(repo, "add", "--all")
        self.git(repo, "commit", *( ["--amend"] if amend else [] ), "-m", message)

    def remote_blob(self, path):
        return self.git(self.remote, "show", "main:" + path)

    def remote_head(self):
        return self.git(self.remote, "rev-parse", "main")

    def push_writer(self, path="unrelated.txt", data=b"remote writer\n", delete=False):
        if delete:
            self.git(self.writer, "rm", "--", path)
        else:
            self.write(self.writer, path, data)
        self.commit(self.writer, "concurrent writer")
        self.git(self.writer, "push", "origin", "main")

    def producer_state(self):
        # Compare raw index bytes, not just its tree: staged/unstaged splits matter.
        files = {
            str(path.relative_to(self.producer)): path.read_bytes()
            for path in self.producer.rglob("*")
            if path.is_file() and ".git" not in path.relative_to(self.producer).parts
        }
        return (
            self.git(self.producer, "rev-parse", "HEAD"),
            (self.producer / ".git" / "HEAD").read_bytes(),
            (self.producer / ".git" / "index").read_bytes(),
            self.git(self.producer, "stash", "list"), files,
        )

    def persist(self, **kwargs):
        before = self.producer_state()
        try:
            return module.persist(self.producer, "main", retry_delay=0, **kwargs)
        finally:
            assert self.producer_state() == before


@pytest.fixture
def repos(tmp_path, monkeypatch):
    monkeypatch.setenv("VERITY_MODE", "dev")
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    return LocalRepositories(tmp_path)


def test_exact_committed_outputs_and_dirty_producer_are_preserved(repos):
    repos.write(repos.producer, "unrelated.txt", b"staged\n")
    repos.git(repos.producer, "add", "--", "unrelated.txt")
    repos.write(repos.producer, "unrelated.txt", b"unstaged after staging\n")
    repos.write(repos.producer, "untracked.txt", b"private local byproduct\n")
    repos.write(repos.producer, module.SNAPSHOT, b"uncommitted snapshot byproduct\n")
    source = repos.git(repos.producer, "rev-parse", "HEAD").strip()
    result = repos.persist()
    assert result.encode() == repos.remote_head().strip()
    assert repos.remote_blob(module.SNAPSHOT) == SNAPSHOT
    assert repos.remote_blob(module.LEDGER) == BASE_ROW + LOCAL_ROW
    assert repos.remote_blob(module.HEALTH) == b'{"macro":"local"}\n'
    changed = repos.git(repos.remote, "diff-tree", "--no-commit-id", "--name-only", "-r", "main")
    assert set(changed.decode().splitlines()) == set(module.PATHS)
    assert repos.remote_blob("unrelated.txt") == b"base\n"
    assert repos.git(repos.producer, "rev-parse", "HEAD").strip() == source


@pytest.mark.parametrize("health", [b'{"scan":"remote"}\n', b'{\n"macro":0,\n"scan":7\n}\n'])
def test_concurrent_health_is_preserved_as_exact_whole_blob(repos, health):
    repos.push_writer(module.HEALTH, health)
    repos.persist()
    assert repos.remote_blob(module.HEALTH) == health
    assert repos.remote_blob(module.SNAPSHOT) == SNAPSHOT


def test_concurrent_health_deletion_is_not_resurrected(repos):
    repos.push_writer(module.HEALTH, delete=True)
    repos.persist()
    paths = repos.git(repos.remote, "ls-tree", "-r", "--name-only", "main").decode().splitlines()
    assert module.HEALTH not in paths
    assert repos.remote_blob(module.SNAPSHOT) == SNAPSHOT


def test_concurrent_ledger_appends_preserve_remote_bytes_and_local_rows(repos):
    repos.push_writer(module.LEDGER, BASE_ROW + REMOTE_ROW)
    repos.persist()
    assert repos.remote_blob(module.LEDGER) == BASE_ROW + REMOTE_ROW + LOCAL_ROW


@pytest.mark.parametrize("remote_ledger", [b"", REMOTE_ROW, BASE_ROW.rstrip(b"\n")])
def test_remote_ledger_rewrite_or_baseline_deletion_fails_closed(repos, remote_ledger):
    repos.push_writer(module.LEDGER, remote_ledger)
    before = repos.remote_head()
    with pytest.raises(RuntimeError, match="ledger.*rewritten"):
        repos.persist()
    assert repos.remote_head() == before
    assert repos.remote_blob(module.LEDGER) == remote_ledger


def test_remote_ledger_file_deletion_fails_closed(repos):
    repos.push_writer(module.LEDGER, delete=True)
    before = repos.remote_head()
    with pytest.raises(RuntimeError, match="ledger.*rewritten"):
        repos.persist()
    assert repos.remote_head() == before


def test_remote_partial_append_fails_without_overwriting_remote(repos):
    repos.push_writer(module.LEDGER, BASE_ROW + b'{"unfinished":')
    before = repos.remote_head()
    with pytest.raises(RuntimeError, match="incomplete final line"):
        repos.persist()
    assert repos.remote_head() == before


def test_remote_snapshot_generation_change_fails_closed(repos):
    newest = b'{"collected_at":"newer-than-prepared"}\n'
    repos.push_writer(module.SNAPSHOT, newest)
    before = repos.remote_head()
    with pytest.raises(RuntimeError, match="generation changed"):
        repos.persist()
    assert repos.remote_head() == before
    assert repos.remote_blob(module.SNAPSHOT) == newest


@pytest.mark.parametrize("generation_race", [False, True])
def test_non_fast_forward_push_race_refetches_remote(repos, monkeypatch, generation_race):
    original = module.git
    pushes = []

    def race(repo, *args, **kwargs):
        if args[0] == "push":
            pushes.append(args)
            if len(pushes) == 1:
                if generation_race:
                    repos.push_writer(module.SNAPSHOT, b'{"collected_at":"latest-race"}\n')
                else:
                    repos.write(repos.writer, module.HEALTH, b'{"health":"race"}\n')
                    repos.write(repos.writer, module.LEDGER, BASE_ROW + REMOTE_ROW)
                    repos.push_writer()
        return original(repo, *args, **kwargs)

    monkeypatch.setattr(module, "git", race)
    if generation_race:
        with pytest.raises(RuntimeError, match="generation changed"):
            repos.persist()
        assert len(pushes) == 1
        assert b"latest-race" in repos.remote_blob(module.SNAPSHOT)
    else:
        repos.persist()
        assert len(pushes) == 2
        assert repos.remote_blob(module.SNAPSHOT) == SNAPSHOT
        assert repos.remote_blob(module.LEDGER) == BASE_ROW + REMOTE_ROW + LOCAL_ROW
        assert repos.remote_blob(module.HEALTH) == b'{"health":"race"}\n'
        assert repos.remote_blob("unrelated.txt") == b"remote writer\n"


def test_rejected_push_exhausts_and_cli_reports_nonzero(repos, monkeypatch):
    hook = repos.remote / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\nexit 1\n")
    hook.chmod(0o755)
    before = repos.remote_head()
    original = module.git
    pushes = []

    def counted(repo, *args, **kwargs):
        if args[0] == "push":
            pushes.append(args)
        return original(repo, *args, **kwargs)

    monkeypatch.setattr(module, "git", counted)
    with pytest.raises(module.GitFailure, match="retries exhausted"):
        repos.persist(attempts=3)
    assert len(pushes) == 3
    assert repos.remote_head() == before
    state = repos.producer_state()
    monkeypatch.chdir(repos.producer)
    monkeypatch.setattr(sys, "argv", ["persist_macro_snapshot.py", "main"])
    failure = module.GitFailure("Persistence retries exhausted")
    monkeypatch.setattr(module, "persist", Mock(side_effect=failure))
    with pytest.raises(SystemExit) as exc:
        module.main()
    assert exc.value.code != 0
    assert "::error::Macro persistence failed" in str(exc.value.code)
    assert repos.producer_state() == state


@pytest.mark.parametrize("same_baseline_row", [False, True])
def test_idempotence_preserves_identical_log_row_multiplicity(repos, same_baseline_row):
    if same_baseline_row:
        # A repeated row can be a distinct observation even when byte-identical.
        repos.write(repos.producer, module.LEDGER, BASE_ROW * 3)
        repos.commit(repos.producer, "prepared repeated observations", amend=True)
        repos.push_writer(module.LEDGER, BASE_ROW * 2 + REMOTE_ROW)
        expected = BASE_ROW * 2 + REMOTE_ROW + BASE_ROW
    else:
        # One of two identical local rows is already on remote: add only one.
        repos.write(repos.producer, module.LEDGER, BASE_ROW + LOCAL_ROW * 2)
        repos.commit(repos.producer, "prepared repeated additions", amend=True)
        repos.push_writer(module.LEDGER, BASE_ROW + REMOTE_ROW + LOCAL_ROW)
        expected = BASE_ROW + REMOTE_ROW + LOCAL_ROW * 2
    first = repos.persist()
    assert repos.remote_blob(module.LEDGER) == expected
    second = repos.persist()
    assert second == first
    assert repos.remote_head().strip() == first.encode()
    assert repos.remote_blob(module.LEDGER) == expected


def test_prepared_extra_path_is_rejected_without_publishing(repos):
    repos.write(repos.producer, "unexpected.txt", b"must remain local\n")
    repos.commit(repos.producer, "unexpected prepared path", amend=True)
    before = repos.remote_head()
    with pytest.raises(module.GitFailure, match="only explicit macro outputs"):
        repos.persist()
    assert repos.remote_head() == before


def test_prepared_ledger_rewrite_is_rejected(repos):
    repos.write(repos.producer, module.LEDGER, LOCAL_ROW)
    repos.commit(repos.producer, "invalid prepared ledger", amend=True)
    before = repos.remote_head()
    with pytest.raises(module.GitFailure, match="not append-only"):
        repos.persist()
    assert repos.remote_head() == before


@pytest.mark.parametrize("command,remaining,limit", [("fetch", 100, 30), ("push", 2, 2), ("read-tree", 100, 15)])
def test_command_timeout_respects_phase_and_remaining_budget(monkeypatch, command, remaining, limit):
    process = Mock(returncode=0)
    process.communicate.return_value = (b"ok", b"")
    popen = Mock(return_value=process)
    monkeypatch.setattr(module.time, "monotonic", lambda: 100.0)
    monkeypatch.setattr(module.subprocess, "Popen", popen)
    module.git(Path("."), command, deadline=100 + remaining, phase="fixture")
    assert process.communicate.call_args.kwargs["timeout"] == limit
    assert popen.call_args.kwargs["start_new_session"] is True
    assert popen.call_args.kwargs["env"]["GIT_TERMINAL_PROMPT"] == "0"


def test_expired_budget_starts_no_process(monkeypatch):
    popen = Mock()
    monkeypatch.setattr(module.time, "monotonic", lambda: 100.0)
    monkeypatch.setattr(module.subprocess, "Popen", popen)
    with pytest.raises(module.GitFailure, match="budget exhausted"):
        module.git(Path("."), "fetch", deadline=99, phase="fetch")
    popen.assert_not_called()


def test_retry_backoff_is_capped_by_total_budget(repos, monkeypatch):
    original = module.git
    clock = [100.0]
    sleeps = []
    fetches = []

    def fail_fetch(repo, *args, **kwargs):
        if args[0] == "fetch":
            fetches.append(kwargs["deadline"])
            if clock[0] < kwargs["deadline"]:
                clock[0] += 1.5
                raise module.GitFailure("fetch timed out")
        return original(repo, *args, **kwargs)

    def sleep(seconds):
        sleeps.append(seconds)
        clock[0] += seconds

    monkeypatch.setattr(module.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(module.time, "sleep", sleep)
    monkeypatch.setattr(module, "git", fail_fetch)
    before = repos.producer_state()
    with pytest.raises(module.GitFailure, match="retries exhausted"):
        module.persist(repos.producer, "main", attempts=3, budget_s=2, retry_delay=5)
    assert clock[0] <= 102.0
    assert sum(sleeps) == 0.5
    assert fetches == [102.0] * 3
    assert repos.producer_state() == before


@pytest.mark.skipif(os.name != "posix", reason="Process group termination is a POSIX contract")
def test_real_timeout_kills_transport_child_and_returns_promptly(tmp_path, monkeypatch, capsys):
    ready = tmp_path / "child-ready"
    survived = tmp_path / "child-survived"
    child = (
        "import pathlib,time; "
        f"pathlib.Path({str(ready)!r}).write_text('ready'); "
        "time.sleep(1.0); "
        f"pathlib.Path({str(survived)!r}).write_text('survived')"
    )
    parent = (
        "import subprocess,sys,time; "
        f"subprocess.Popen([sys.executable, '-c', {child!r}]); "
        "time.sleep(30)"
    )
    original_popen = subprocess.Popen
    original_killpg = os.killpg
    groups = []

    def transport(*args, **kwargs):
        return original_popen([sys.executable, "-c", parent], **kwargs)

    def kill_group(pid, sig):
        groups.append((pid, sig))
        return original_killpg(pid, sig)

    monkeypatch.setattr(module.subprocess, "Popen", transport)
    monkeypatch.setattr(module.os, "killpg", kill_group)
    started = time.monotonic()
    with pytest.raises(module.GitFailure, match="fetch timed out"):
        module.git(tmp_path, "fetch", deadline=started + 0.5, phase="fetch")
    assert time.monotonic() - started < 3
    assert ready.exists(), "The transport child must have started before the timeout"
    assert len(groups) == 1 and groups[0][1] == signal.SIGKILL
    time.sleep(1.1)
    assert not survived.exists(), "Transport child outlived the timed-out Git process"
    assert "phase=fetch timeout" in capsys.readouterr().out


def test_failed_command_does_not_echo_transport_credentials(monkeypatch, capsys):
    process = Mock(returncode=128)
    process.communicate.return_value = (b"", b"https://example.invalid/fixture-sensitive-token")
    monkeypatch.setattr(module.subprocess, "Popen", Mock(return_value=process))
    with pytest.raises(module.GitFailure) as exc:
        module.git(Path("."), "fetch", deadline=time.monotonic() + 5, phase="fetch")
    assert "fixture-sensitive-token" not in str(exc.value) + capsys.readouterr().out
