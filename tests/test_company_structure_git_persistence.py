"""Execute ownership durable steps against local Git repositories; no services.

The production shell is loaded from YAML, including its publication anchor.
Only a push boundary is intercepted: a second clone advances the local bare
remote immediately before the first clone attempts its real Git push.
"""

import itertools
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import yaml


WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/ownership_backfill.yml"
JOBS = ("backfill", "publish-only")
KR = "data/member_map_company_structure_sources.json"
US = "data/member_map_company_structure_us_sources.json"
INDEX = "data/member_map_company_structure_index.json"
LEGACY = "data/kr_ownership.json"
CURSOR = "data/metadata/kr_ownership_cursor.json"
PERSISTED = (KR, US, LEGACY, CURSOR, INDEX)
INPUTS = (
    "data/kr_listed.json",
    "data/universe_search.json",
    "data/sec_ticker_cik_map.json",
    "data/member_map_company_structure_aliases.json",
    "data/group_structure.json",
    LEGACY, KR, US,
    "vercel-api/public/member-map-review/company-structure.json",
    "scripts/member-map/build-live-company-structure.cjs",
    "review/member-map/company-structure-data.cjs",
    "scripts/member-map/publish-company-structure.cjs",
)


class LocalRepos:
    """One disposable bare remote and exactly two clones, with isolated config."""

    def __init__(self, root):
        self.root = Path(root)
        self.remote = self.root / "origin.git"
        self.writer = self.root / "writer"
        self.worker = self.root / "worker"
        self.real_git = shutil.which("git")
        if not self.real_git:
            raise RuntimeError("Git is required for the persistence integration tests")
        self.env = {
            "PATH": os.pathsep.join((str(Path(self.real_git).parent), os.defpath)),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_ALLOW_PROTOCOL": "file",
            "GIT_AUTHOR_NAME": "Persistence Test",
            "GIT_AUTHOR_EMAIL": "persistence@example.invalid",
            "GIT_COMMITTER_NAME": "Persistence Test",
            "GIT_COMMITTER_EMAIL": "persistence@example.invalid",
            "LC_ALL": "C",
        }
        self.git(self.root, "init", "--bare", "--initial-branch=main", str(self.remote))
        self.git(self.root, "clone", str(self.remote), str(self.writer))
        for path in sorted(set(PERSISTED + INPUTS + ("unrelated.txt",))):
            self.write(self.writer, path, self.payload())
        self.git(self.writer, "add", "--", *sorted(set(PERSISTED + INPUTS + ("unrelated.txt",))))
        self.git(self.writer, "commit", "-m", "Initial fixture")
        self.git(self.writer, "push", "origin", "HEAD:main")
        self.git(self.root, "clone", str(self.remote), str(self.worker))
        self.source_head = self.git(self.worker, "rev-parse", "HEAD").stdout.strip()
        self.calls_path = self.root / "git-calls"
        self.push_count = self.root / "push-count"
        self.race_head = self.root / "race-head"
        bindir = self.root / "bin"
        bindir.mkdir()
        wrapper = bindir / "git"
        wrapper.write_text("""#!/bin/bash
set -euo pipefail
printf '%s\\n' "$1" >> "$TEST_GIT_CALLS"
if [ "$1" = push ]; then
  count=0
  if [ -f "$TEST_PUSH_COUNT" ]; then read -r count < "$TEST_PUSH_COUNT"; fi
  count=$((count + 1))
  printf '%s\\n' "$count" > "$TEST_PUSH_COUNT"
  if [ "$TEST_DENY_PUSH" = 1 ]; then
    echo 'fixture: push denied without remote progress' >&2
    exit 1
  fi
  if [ "$count" -le "$TEST_RACES" ]; then
    "$TEST_REAL_GIT" -C "$TEST_WRITER" pull --rebase origin main
    if [ -n "$TEST_RACE_CONTENT" ]; then
      cp "$TEST_RACE_CONTENT" "$TEST_WRITER/$TEST_RACE_PATH"
    else
      printf 'remote race %s\\n' "$count" > "$TEST_WRITER/$TEST_RACE_PATH"
    fi
    "$TEST_REAL_GIT" -C "$TEST_WRITER" add -- "$TEST_RACE_PATH"
    "$TEST_REAL_GIT" -C "$TEST_WRITER" commit -m "Concurrent main $count"
    "$TEST_REAL_GIT" -C "$TEST_WRITER" push origin HEAD:main
    "$TEST_REAL_GIT" -C "$TEST_WRITER" rev-parse HEAD > "$TEST_RACE_HEAD"
  fi
fi
exec "$TEST_REAL_GIT" "$@"
""")
        wrapper.chmod(0o755)
        self.run_env = {
            **self.env,
            "PATH": str(bindir) + os.pathsep + self.env["PATH"],
            "TEST_REAL_GIT": self.real_git,
            "TEST_WRITER": str(self.writer),
            "TEST_GIT_CALLS": str(self.calls_path),
            "TEST_PUSH_COUNT": str(self.push_count),
            "TEST_RACE_HEAD": str(self.race_head),
            "TEST_RACES": "0",
            "TEST_RACE_PATH": "unrelated.txt",
            "TEST_RACE_CONTENT": "",
            "TEST_DENY_PUSH": "0",
            "SOURCE_HEAD": self.source_head,
            "BUILD_OUTCOME": "success",
            "LEGACY_OUTCOME": "success",
        }

    @staticmethod
    def payload(field="field00", value=0):
        fields = {"field%02d" % i: 0 for i in range(24)}
        fields[field] = value
        return json.dumps(fields, indent=2) + "\n"

    @staticmethod
    def write(repo, path, body):
        target = repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body)

    def git(self, repo, *args, check=True):
        return subprocess.run(
            [self.real_git, *args], cwd=repo, env=self.env,
            capture_output=True, text=True, check=check, timeout=15,
        )

    def prepare(self, job, *, build="success", legacy="success"):
        self.run_env.update(BUILD_OUTCOME=build, LEGACY_OUTCOME=legacy)
        paths = [INDEX] if job == "publish-only" else [KR, US]
        if job == "backfill":
            if legacy == "success":
                paths += [LEGACY, CURSOR]
            if build == "success":
                paths += [INDEX]
        for path in paths:
            self.write(self.worker, path, self.payload(value=1))
        return {path: (self.worker / path).read_bytes() for path in paths}

    def race(self, *, count=1, path="unrelated.txt", field=None):
        self.run_env.update(TEST_RACES=str(count), TEST_RACE_PATH=path)
        if field:
            body = self.root / "race-content"
            body.write_text(self.payload(field, 2))
            self.run_env["TEST_RACE_CONTENT"] = str(body)

    def advance_before_pull(self, path):
        self.write(self.writer, path, self.payload(value=2))
        self.git(self.writer, "add", "--", path)
        self.git(self.writer, "commit", "-m", "Inputs changed before persistence")
        self.git(self.writer, "push", "origin", "HEAD:main")

    def run(self, script):
        return subprocess.run(
            ["bash", "-e", "-o", "pipefail", "-c", script],
            cwd=self.worker, env=self.run_env, capture_output=True, text=True, timeout=30,
        )

    def remote_head(self):
        return self.git(self.remote, "rev-parse", "main").stdout.strip()

    def remote_bytes(self, path):
        return self.git(self.remote, "show", "main:" + path).stdout.encode()

    def calls(self, command):
        return self.calls_path.read_text().splitlines().count(command)


class CompanyStructureGitPersistenceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # safe_load resolves the build/publish YAML aliases as actual steps.
        cls.jobs = yaml.safe_load(WORKFLOW.read_text())["jobs"]
        cls.durable = {
            job: next(step for step in cls.jobs[job]["steps"] if step.get("id") == "durable")
            for job in JOBS
        }

    def fixture(self):
        scratch = tempfile.TemporaryDirectory(prefix="company-structure-git-")
        self.addCleanup(scratch.cleanup)
        return LocalRepos(scratch.name)

    def run_durable(self, fixture, job):
        # Execute the entire actual run block; do not copy or rewrite its loop.
        return fixture.run(self.durable[job]["run"])

    def assert_remote_saved(self, fixture, snapshots):
        for path, expected in snapshots.items():
            self.assertEqual(fixture.remote_bytes(path), expected, path)
        fixture.git(fixture.worker, "fetch", "origin", "main")
        self.assertEqual(fixture.git(fixture.worker, "merge-base", "--is-ancestor",
                                     "HEAD", "origin/main", check=False).returncode, 0)

    def assert_remote_not_overwritten(self, fixture):
        # A conflicted rebase can leave local HEAD at the upstream commit.
        # The remote must remain exactly at the competing writer's commit.
        self.assertEqual(fixture.remote_head(), fixture.race_head.read_text().strip())

    def test_unrelated_push_race_rebases_and_preserves_both_commits(self):
        for job in JOBS:
            with self.subTest(job=job):
                f = self.fixture()
                snapshots = f.prepare(job)
                f.race()
                result = self.run_durable(f, job)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual((f.calls("pull"), f.calls("push"), f.calls("fetch")), (2, 2, 2))
                self.assertEqual(f.remote_bytes("unrelated.txt"), b"remote race 1\n")
                self.assert_remote_saved(f, snapshots)
                self.assertEqual(f.git(f.worker, "status", "--porcelain").stdout, "")

    def test_conflicting_source_or_index_fails_without_remote_overwrite(self):
        for job, path in (("backfill", KR), ("publish-only", INDEX)):
            with self.subTest(job=job, path=path):
                f = self.fixture()
                f.prepare(job)
                f.race(path=path, field="field00")
                result = self.run_durable(f, job)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual((f.calls("pull"), f.calls("push"), f.calls("fetch")), (2, 1, 1))
                self.assertTrue(f.git(f.worker, "ls-files", "-u").stdout)
                self.assertEqual(f.remote_bytes(path), f.payload(value=2).encode())
                self.assert_remote_not_overwritten(f)

    def test_push_denied_without_remote_progress_fails_after_one_fetch(self):
        for job in JOBS:
            with self.subTest(job=job):
                f = self.fixture()
                f.prepare(job)
                f.run_env["TEST_DENY_PUSH"] = "1"
                result = self.run_durable(f, job)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("push failed without a concurrent main advance", result.stdout)
                self.assertEqual((f.calls("pull"), f.calls("push"), f.calls("fetch")), (1, 1, 1))
                self.assertEqual(f.remote_head(), f.source_head)

    def test_four_consecutive_races_exhaust_the_limit_without_publishing(self):
        for job in JOBS:
            with self.subTest(job=job):
                f = self.fixture()
                f.prepare(job)
                f.race(count=4)
                result = self.run_durable(f, job)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("exhausted four concurrent-main attempts", result.stdout)
                self.assertEqual((f.calls("pull"), f.calls("push"), f.calls("fetch")), (4, 4, 4))
                self.assertEqual(f.remote_bytes("unrelated.txt"), b"remote race 4\n")
                self.assertEqual(f.git(f.remote, "rev-list", "--count", "main").stdout.strip(), "5")
                self.assertEqual(f.remote_bytes(INDEX), f.payload().encode())
                self.assertEqual(f.remote_bytes(KR), f.payload().encode())
                self.assert_remote_not_overwritten(f)

    def test_publish_only_rechecks_each_source_head_input_on_retry(self):
        for path in INPUTS:
            with self.subTest(path=path):
                f = self.fixture()
                f.prepare("publish-only")
                f.race(path=path, field="field00")
                result = self.run_durable(f, "publish-only")
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual((f.calls("pull"), f.calls("push"), f.calls("fetch")), (2, 1, 1))
                self.assertEqual(f.git(f.worker, "ls-files", "-u").stdout, "")
                self.assertEqual(f.remote_bytes(path), f.payload(value=2).encode())
                self.assertEqual(f.remote_bytes(INDEX), f.payload().encode())
                self.assert_remote_not_overwritten(f)

    def test_publish_only_rejects_input_drift_before_first_push(self):
        f = self.fixture()
        f.prepare("publish-only")
        f.advance_before_pull(KR)
        remote_head = f.remote_head()
        result = self.run_durable(f, "publish-only")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((f.calls("pull"), f.calls("push"), f.calls("fetch")), (1, 0, 0))
        self.assertEqual(f.remote_head(), remote_head)
        self.assertEqual(f.remote_bytes(INDEX), f.payload().encode())

    def test_clean_merge_cannot_change_any_persisted_snapshot_bytes(self):
        cases = [("backfill", path) for path in PERSISTED] + [("publish-only", INDEX)]
        for job, path in cases:
            with self.subTest(job=job, path=path):
                f = self.fixture()
                snapshots = f.prepare(job)
                # Well-separated lines merge cleanly; the saved-byte guard must stop it.
                f.race(path=path, field="field23")
                result = self.run_durable(f, job)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual((f.calls("pull"), f.calls("push"), f.calls("fetch")), (2, 1, 1))
                self.assertEqual(f.git(f.worker, "ls-files", "-u").stdout, "")
                self.assertNotEqual((f.worker / path).read_bytes(), snapshots[path])
                self.assertEqual(f.remote_bytes(path), f.payload("field23", 2).encode())
                self.assert_remote_not_overwritten(f)

    def test_failed_build_allows_upstream_index_without_blocking_budget_save(self):
        for legacy in ("success", "failure"):
            with self.subTest(legacy=legacy):
                f = self.fixture()
                snapshots = f.prepare("backfill", build="failure", legacy=legacy)
                f.race(path=INDEX, field="field00")
                result = self.run_durable(f, "backfill")
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual((f.calls("pull"), f.calls("push"), f.calls("fetch")), (2, 2, 2))
                self.assert_remote_saved(f, snapshots)
                self.assertEqual(f.remote_bytes(INDEX), f.payload(value=2).encode())

    def test_failed_legacy_does_not_guard_unstaged_upstream_legacy_bytes(self):
        f = self.fixture()
        snapshots = f.prepare("backfill", legacy="failure")
        f.race(path=CURSOR, field="field00")
        result = self.run_durable(f, "backfill")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assert_remote_saved(f, snapshots)
        self.assertEqual(f.remote_bytes(CURSOR), f.payload(value=2).encode())

    def test_autostash_restore_conflicts_stop_even_when_pull_returns_success(self):
        f = self.fixture()
        f.prepare("backfill", build="failure")
        # Index is deliberately unstaged after a failed build, so rebase autostashes it.
        f.write(f.worker, INDEX, f.payload(value=1))
        f.race(path=INDEX, field="field00")
        result = self.run_durable(f, "backfill")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((f.calls("pull"), f.calls("push"), f.calls("fetch")), (2, 1, 1))
        self.assertIn(INDEX, f.git(f.worker, "ls-files", "-u").stdout)
        self.assert_remote_not_overwritten(f)

    def test_publication_requires_successful_safe_build_and_durable_steps(self):
        for job in JOBS:
            steps = self.jobs[job]["steps"]
            publications = [step for step in steps if "--publish" in step.get("run", "")]
            self.assertEqual(len(publications), 1)
            publish = publications[0]
            self.assertLess(steps.index(self.durable[job]), steps.index(publish))
            gate = publish["if"].strip().removeprefix("${{").removesuffix("}}")
            for safe, build, durable in itertools.product(("success", "failure", "skipped"), repeat=3):
                with self.subTest(job=job, safe=safe, build=build, durable=durable):
                    expression = gate.replace("always()", "True").replace("&&", "and")
                    for step, outcome in (("safe", safe), ("build", build), ("durable", durable)):
                        expression = expression.replace("steps." + step + ".outcome", repr(outcome))
                    self.assertEqual(eval(expression, {"__builtins__": {}}),
                                     safe == build == durable == "success")


if __name__ == "__main__":
    unittest.main()
