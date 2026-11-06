"""Run the actual US disclosure persistence shell against disposable local Git.

Reuse PR621's two-clone race fixture. No services, collection, project commits,
real remote writes or publication are performed by these regressions.
"""
from itertools import product
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

import pytest
import yaml

from tests.test_company_structure_git_persistence import LocalRepos

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = yaml.safe_load((ROOT / ".github/workflows/us_disclosure_feed.yml").read_text())
JOB = WORKFLOW["jobs"]["build"]
STEPS = JOB["steps"]
BUILD = next(step for step in STEPS if step.get("id") == "build")
DURABLE = next(step for step in STEPS if step.get("id") == "durable")
PUBLISH = next(step for step in STEPS if step.get("uses") == "./.github/actions/publish-data")
ARTIFACTS = ("data/us_disclosure_feed.json", "data/us_disclosure_forensics.json",
             "data/metadata/us_forensics_coverage.json")
HELPER = "scripts/member-map/us-priority-fingerprint.py"
CONSUMER = "api/builders/us_insider_trades_public_builder.py"
PORTFOLIO = "data/portfolio.json"
SYNTHETIC_PORTFOLIO = {
    "recommendations": [{"ticker": " aaa ", "currency": "USD", "price": 1},
                        {"ticker": "005930", "currency": "KRW"}],
    "candidates": [{"ticker": "bbb", "currency": "USD"}],
    "prices": {"synthetic": 1},
}
INPUTS = (
    ".gitattributes",
    "api/__init__.py", "api/builders/__init__.py", "api/intelligence/__init__.py",
    "api/builders/us_disclosure_feed_builder.py", "api/builders/us_disclosure_forensics_builder.py",
    "api/builders/us_insider_trades_public_builder.py", "api/intelligence/us_financials.py",
    "scripts/audit/us_forensics_coverage.py", "requirements.txt",
    HELPER,
    ".github/workflows/us_disclosure_feed.yml", ".github/actions/publish-data/action.yml",
    "data/us_universe_combined.json", "data/us_universe_sp1500.json", "data/us_financials/_summary.json",
    "data/us_stock_report_public.json", "data/universe_search.json",
    "data/us_insider_trades.json", "data/us_major_holdings.json",
    "data/us_smart_money_13f.json", "data/us_short_interest.json", "data/us_form144.json",
)


class DisclosureRepos(LocalRepos):
    def __init__(self, root):
        super().__init__(root)
        for path in (*ARTIFACTS, *INPUTS):
            self.write(self.writer, path, self.payload())
        for path in (HELPER, CONSUMER):
            self.write(self.writer, path, (ROOT / path).read_text())
        self.write(self.writer, PORTFOLIO, json.dumps(SYNTHETIC_PORTFOLIO))
        self.write(self.writer, ".gitattributes", "")
        self.git(self.writer, "add", "--", *ARTIFACTS, *INPUTS, PORTFOLIO)
        self.git(self.writer, "commit", "-m", "Disclosure fixture inputs")
        self.git(self.writer, "push", "origin", "HEAD:main")
        self.git(self.worker, "pull", "--ff-only", "origin", "main")
        python = self.root / "bin/python"
        python.write_text("""#!/bin/bash
set -euo pipefail
if [ "$1" = -m ] || [ "$1" = scripts/audit/us_forensics_coverage.py ]; then
  printf '%s\\n' "$*" >> "$TEST_COLLECTION_CALLS"
  if [ "$*" = '-m api.builders.us_disclosure_feed_builder' ] && [ -n "${TEST_COLLECTION_PORTFOLIO:-}" ]; then
    cp "$TEST_COLLECTION_PORTFOLIO" data/portfolio.json
  fi
  exit 0
fi
exec "$TEST_PYTHON" "$@"
""")
        python.chmod(0o755)
        self.run_env.update(TEST_PYTHON=sys.executable, PYTHONDONTWRITEBYTECODE="1",
                            TEST_COLLECTION_CALLS=str(self.root / "collection-calls"),
                            GITHUB_OUTPUT=str(self.root / "build-outputs"))
        result = self.run_build()
        assert result.returncode == 0, result.stdout + result.stderr
        self.source_head = self.run_env["SOURCE_HEAD"]

    def run_build(self):
        output = Path(self.run_env["GITHUB_OUTPUT"])
        output.write_text("")
        result = self.run(BUILD["run"])
        if result.returncode == 0:
            outputs = dict(line.split("=", 1) for line in output.read_text().splitlines())
            self.run_env.update(SOURCE_HEAD=outputs["source_head"],
                                US_PRIORITY_FINGERPRINT=outputs["us_priority_fingerprint"])
        return result

    def portfolio_body(self, *, priority=False):
        portfolio = json.loads((self.writer / PORTFOLIO).read_text())
        if priority:
            portfolio["recommendations"].append({"ticker": "CCC", "currency": "USD"})
        else:
            portfolio["prices"]["synthetic"] = 2
        return json.dumps(portfolio)

    def prepare(self, *, changed=True):
        if changed:
            for path in ARTIFACTS:
                self.write(self.worker, path, self.payload(value=1))
        return {path: (self.worker / path).read_bytes() for path in ARTIFACTS}

    def post_push_advance(self, path, body=None):
        # Model a second writer between successful push and remote readback.
        wrapper = self.root / "bin/git"
        self.run_env["TEST_AFTER_PATH"] = path
        self.run_env["TEST_AFTER_CONTENT"] = ""
        if body is not None:
            content = self.root / "post-push-content"
            content.write_text(body)
            self.run_env["TEST_AFTER_CONTENT"] = str(content)
        injected = """
if [ "$1" = push ]; then
  "$TEST_REAL_GIT" "$@"
  "$TEST_REAL_GIT" -C "$TEST_WRITER" pull --rebase origin main
  if [ -n "$TEST_AFTER_CONTENT" ]; then
    cp "$TEST_AFTER_CONTENT" "$TEST_WRITER/$TEST_AFTER_PATH"
  else
    printf 'post-push replacement\\n' > "$TEST_WRITER/$TEST_AFTER_PATH"
  fi
  "$TEST_REAL_GIT" -C "$TEST_WRITER" add -- "$TEST_AFTER_PATH"
  "$TEST_REAL_GIT" -C "$TEST_WRITER" commit -m 'Post-push concurrent source'
  "$TEST_REAL_GIT" -C "$TEST_WRITER" push origin HEAD:main
  exit 0
fi
"""
        wrapper.write_text(wrapper.read_text().replace('exec "$TEST_REAL_GIT" "$@"',
                                                       injected + '\nexec "$TEST_REAL_GIT" "$@"'))


@pytest.fixture
def repos(tmp_path):
    return DisclosureRepos(tmp_path)


def assert_saved(fixture, snapshots):
    for path, expected in snapshots.items():
        assert fixture.remote_bytes(path) == expected, path
    fixture.git(fixture.worker, "fetch", "origin", "main")
    assert fixture.git(fixture.worker, "merge-base", "--is-ancestor",
                       "HEAD", "origin/main", check=False).returncode == 0


@pytest.mark.parametrize("changed", [True, False])
def test_success_and_no_change_both_require_verified_remote(repos, changed):
    snapshots = repos.prepare(changed=changed)
    result = repos.run(DURABLE["run"])
    assert result.returncode == 0, result.stdout + result.stderr
    assert (repos.calls("pull"), repos.calls("push"), repos.calls("fetch")) == (1, 1, 1)
    assert repos.calls("commit") == int(changed)
    assert_saved(repos, snapshots)
    assert repos.git(repos.worker, "status", "--porcelain").stdout == ""


def test_unrelated_main_race_preserves_exact_outputs_and_other_commit(repos):
    snapshots = repos.prepare()
    repos.race()
    result = repos.run(DURABLE["run"])
    assert result.returncode == 0, result.stdout + result.stderr
    assert (repos.calls("pull"), repos.calls("push"), repos.calls("fetch")) == (2, 2, 2)
    assert repos.remote_bytes("unrelated.txt") == b"remote race 1\n"
    assert_saved(repos, snapshots)


def test_market_only_portfolio_race_preserves_exact_outputs(repos):
    snapshots = repos.prepare()
    body = repos.root / "market-only-portfolio"
    body.write_text(repos.portfolio_body())
    repos.race(path=PORTFOLIO)
    repos.run_env["TEST_RACE_CONTENT"] = str(body)
    result = repos.run(DURABLE["run"])
    assert result.returncode == 0, result.stdout + result.stderr
    assert repos.calls("push") == 2
    assert_saved(repos, snapshots)


@pytest.mark.parametrize("key", ["recommendations", "candidates"])
def test_changed_us_priority_set_after_rebase_blocks_retry_and_publication(repos, key):
    repos.prepare()
    portfolio = json.loads((repos.writer / PORTFOLIO).read_text())
    portfolio[key].append({"ticker": "CCC", "currency": "USD"})
    body = repos.root / "changed-priority"
    body.write_text(json.dumps(portfolio))
    repos.race(path=PORTFOLIO)
    repos.run_env["TEST_RACE_CONTENT"] = str(body)
    result = repos.run(DURABLE["run"])
    assert result.returncode != 0 and "US priority inputs changed" in result.stdout
    assert (repos.calls("pull"), repos.calls("push"), repos.calls("fetch")) == (2, 1, 1)
    assert repos.remote_head() == repos.race_head.read_text().strip()
    for path in ARTIFACTS:
        assert repos.remote_bytes(path) == repos.payload().encode()


def test_priority_mutation_after_build_is_rejected_before_commit(repos):
    repos.prepare()
    repos.write(repos.worker, PORTFOLIO, repos.portfolio_body(priority=True))
    result = repos.run(DURABLE["run"])
    assert result.returncode != 0 and "US priority inputs changed" in result.stdout
    assert repos.calls("commit") == repos.calls("push") == 0
    assert repos.remote_head() == repos.source_head


def test_digest_is_captured_before_collection_and_never_rebased_to_later_inputs(repos):
    baseline = repos.run_env["US_PRIORITY_FINGERPRINT"]
    body = repos.root / "collection-priority-mutation"
    body.write_text(repos.portfolio_body(priority=True))
    repos.run_env["TEST_COLLECTION_PORTFOLIO"] = str(body)
    result = repos.run_build()  # Actual BUILD shell; only provider calls are stubbed.
    assert result.returncode == 0, result.stdout + result.stderr
    assert repos.run_env["US_PRIORITY_FINGERPRINT"] == baseline
    current = repos.run(f"python {HELPER}")
    assert current.returncode == 0 and current.stdout.strip() != baseline
    repos.prepare()
    result = repos.run(DURABLE["run"])
    assert result.returncode != 0 and "US priority inputs changed" in result.stdout
    assert repos.calls("commit") == repos.calls("push") == 0


@pytest.mark.parametrize("priority", [False, True], ids=["price-only", "changed-priority"])
def test_post_push_readback_checks_remote_priority_set(repos, priority):
    snapshots = repos.prepare()
    repos.post_push_advance(PORTFOLIO, repos.portfolio_body(priority=priority))
    result = repos.run(DURABLE["run"])
    assert (result.returncode == 0) == (not priority), result.stdout + result.stderr
    assert (repos.calls("pull"), repos.calls("push"), repos.calls("fetch")) == (1, 1, 1)
    if priority:
        assert "US priority inputs changed" in result.stdout
        assert (repos.worker / PORTFOLIO).read_text() != repos.remote_bytes(PORTFOLIO).decode()
    assert_saved(repos, snapshots)


def test_fingerprint_uses_exact_consumer_ticker_currency_and_set_semantics(repos):
    portfolio = {
        "recommendations": [{"ticker": " aaa "}, {"ticker": "AAA", "currency": "KRW"},
                            {"ticker": "005930", "currency": "KRW"},
                            {"ticker": "005931", "currency": "usd"},
                            {"ticker": "005932", "currency": "USD"}, {"ticker": "  "}],
        "candidates": [{"ticker": "bbb", "currency": "USD"}, {"ticker": 123}],
        "other": [{"ticker": "IGNORED", "currency": "USD"}],
    }
    repos.write(repos.worker, PORTFOLIO, json.dumps(portfolio))
    expected = hashlib.sha256(b'["005932","123","AAA","BBB"]').hexdigest()
    result = repos.run(f"python {HELPER}")
    assert result.returncode == 0 and result.stdout.strip() == expected
    for key in ("recommendations", "candidates"):
        portfolio[key].reverse()
    portfolio["prices"] = {"synthetic": 999}
    repos.write(repos.worker, PORTFOLIO, json.dumps(portfolio))
    assert repos.run(f"python {HELPER}").stdout.strip() == expected
    repos.git(repos.worker, "add", "--", PORTFOLIO)
    repos.git(repos.worker, "commit", "-m", "Synthetic priority semantics")
    assert repos.run(f"python {HELPER} --ref HEAD").stdout.strip() == expected


@pytest.mark.parametrize("baseline", ["", "invalid"])
def test_missing_or_invalid_build_digest_cannot_publish(repos, baseline):
    repos.prepare()
    repos.run_env["US_PRIORITY_FINGERPRINT"] = baseline
    result = repos.run(DURABLE["run"])
    assert result.returncode != 0 and repos.calls("commit") == repos.calls("push") == 0


@pytest.mark.parametrize("path", ARTIFACTS)
@pytest.mark.parametrize("field", ["field00", "field23"], ids=["conflict", "clean-merge"])
def test_any_conflicting_or_cleanly_merged_output_change_blocks_publish(repos, path, field):
    snapshots = repos.prepare()
    repos.race(path=path, field=field)
    result = repos.run(DURABLE["run"])
    assert result.returncode != 0
    assert (repos.calls("pull"), repos.calls("push"), repos.calls("fetch")) == (2, 1, 1)
    assert repos.remote_head() == repos.race_head.read_text().strip()
    assert repos.remote_bytes(path) == repos.payload(field, 2).encode()
    if field == "field00":
        assert repos.git(repos.worker, "ls-files", "-u").stdout
    else:
        assert repos.git(repos.worker, "ls-files", "-u").stdout == ""
        assert (repos.worker / path).read_bytes() != snapshots[path]


@pytest.mark.parametrize("path", INPUTS)
def test_each_source_and_code_input_is_rebound_on_every_retry(repos, path):
    repos.prepare()
    repos.race(path=path, field="field23")
    result = repos.run(DURABLE["run"])
    assert result.returncode != 0, path
    assert (repos.calls("pull"), repos.calls("push"), repos.calls("fetch")) == (2, 1, 1)
    assert repos.git(repos.worker, "ls-files", "-u").stdout == ""
    assert repos.remote_head() == repos.race_head.read_text().strip()
    for artifact in ARTIFACTS:
        assert repos.remote_bytes(artifact) == repos.payload().encode()


def test_source_drift_before_first_push_fails_closed(repos):
    repos.prepare()
    repos.advance_before_pull("data/us_universe_combined.json")
    remote = repos.remote_head()
    result = repos.run(DURABLE["run"])
    assert result.returncode != 0
    assert (repos.calls("pull"), repos.calls("push"), repos.calls("fetch")) == (1, 0, 0)
    assert repos.remote_head() == remote


def test_uncommitted_input_change_and_preexisting_staging_cannot_be_committed(repos):
    repos.prepare()
    repos.write(repos.worker, "data/us_universe_combined.json", repos.payload(value=3))
    result = repos.run(DURABLE["run"])
    assert result.returncode != 0 and repos.calls("commit") == repos.calls("push") == 0
    repos.git(repos.worker, "add", "--", "data/us_universe_combined.json")
    result = repos.run(DURABLE["run"])
    assert result.returncode != 0 and repos.calls("commit") == repos.calls("push") == 0
    assert repos.remote_head() == repos.source_head


def test_failed_commit_blocks_all_pushes(repos):
    repos.prepare()
    hook = repos.worker / ".git/hooks/pre-commit"
    hook.write_text("#!/bin/sh\nexit 1\n")
    hook.chmod(0o755)
    result = repos.run(DURABLE["run"])
    assert result.returncode != 0 and repos.calls("commit") == 1
    assert repos.calls("pull") == repos.calls("push") == repos.calls("fetch") == 0
    assert repos.remote_head() == repos.source_head


def test_fixed_push_rejection_is_not_retried(repos):
    repos.prepare()
    repos.run_env["TEST_DENY_PUSH"] = "1"
    result = repos.run(DURABLE["run"])
    assert result.returncode != 0
    assert "push failed without a concurrent main advance" in result.stdout
    assert (repos.calls("pull"), repos.calls("push"), repos.calls("fetch")) == (1, 1, 1)
    assert repos.remote_head() == repos.source_head


def test_four_unrelated_races_exhaust_limit_and_leave_remote_artifacts_untouched(repos):
    repos.prepare()
    repos.race(count=4)
    result = repos.run(DURABLE["run"])
    assert result.returncode != 0
    assert "exhausted four concurrent-main attempts" in result.stdout
    assert (repos.calls("pull"), repos.calls("push"), repos.calls("fetch")) == (4, 4, 4)
    assert repos.remote_bytes("unrelated.txt") == b"remote race 4\n"
    for path in ARTIFACTS:
        assert repos.remote_bytes(path) == repos.payload().encode()


def test_autostash_restore_conflict_cannot_hide_behind_successful_pull(repos):
    repos.prepare()
    repos.write(repos.worker, "unrelated.txt", repos.payload(value=1))
    repos.race(path="unrelated.txt", field="field00")
    result = repos.run(DURABLE["run"])
    assert result.returncode != 0
    assert (repos.calls("pull"), repos.calls("push"), repos.calls("fetch")) == (2, 1, 1)
    assert repos.git(repos.worker, "ls-files", "-u").stdout
    assert repos.remote_head() == repos.race_head.read_text().strip()


@pytest.mark.parametrize("path", [ARTIFACTS[0], ARTIFACTS[2], "data/us_universe_combined.json"])
def test_successful_push_still_requires_exact_remote_readback(repos, path):
    repos.prepare()
    repos.post_push_advance(path)
    result = repos.run(DURABLE["run"])
    assert result.returncode != 0
    assert (repos.calls("pull"), repos.calls("push"), repos.calls("fetch")) == (1, 1, 1)
    assert repos.remote_bytes(path) == b"post-push replacement\n"


def test_publication_gate_rejects_failed_skipped_or_cancelled_build_or_persist():
    assert STEPS.index(BUILD) < STEPS.index(DURABLE) < STEPS.index(PUBLISH)
    expression = PUBLISH["if"].strip().removeprefix("${{").removesuffix("}}")
    for overall, build, durable in product(
            (True, False), ("success", "failure", "skipped", "cancelled"),
            ("success", "failure", "skipped", "cancelled")):
        gate = expression.replace("success()", repr(overall)).replace("&&", "and")
        gate = gate.replace("steps.build.outcome", repr(build)).replace("steps.durable.outcome", repr(durable))
        assert eval(gate, {"__builtins__": {}}) == (overall and build == durable == "success")
    assert DURABLE["env"]["SOURCE_HEAD"] == "${{ steps.build.outputs.source_head }}"
    assert DURABLE["env"]["US_PRIORITY_FINGERPRINT"] == "${{ steps.build.outputs.us_priority_fingerprint }}"
    assert 'echo "source_head=$(git rev-parse HEAD)"' in BUILD["run"]


def test_existing_schedule_budgets_dependencies_secret_scope_and_no_kis():
    triggers = WORKFLOW.get("on", WORKFLOW.get(True))
    assert set(triggers) == {"schedule", "workflow_dispatch"}
    assert triggers["schedule"] == [{"cron": "0 5 * * *"}]
    assert triggers["workflow_dispatch"]["inputs"]["max_seconds"]["default"] == "1800"
    assert WORKFLOW["concurrency"] == {"group": "verity-us-disclosure", "cancel-in-progress": False}
    assert WORKFLOW["permissions"] == {"contents": "write"}
    assert JOB["timeout-minutes"] == 45
    assert JOB["if"] == "github.ref == 'refs/heads/main'"
    checkout = next(step for step in STEPS if step.get("uses") == "actions/checkout@v4")
    assert checkout["with"] == {"ref": "main", "fetch-depth": 100}
    assert next(step for step in STEPS if step.get("name") == "Install dependencies")["run"] == (
        "pip install -r requirements.txt")
    assert BUILD["env"]["US_DISCLOSURE_MAX_SECONDS"] == "${{ github.event.inputs.max_seconds || '1800' }}"
    assert re.findall(r"^          git add (.+)$",
                      (ROOT / ".github/workflows/us_disclosure_feed.yml").read_text(), re.M) == list(ARTIFACTS)
    assert set(re.findall(r"secrets\.([A-Z_]+)", json.dumps(WORKFLOW))) == {
        "GITHUB_TOKEN", "VERITY_DATA_PAT", "VERCEL_BLOB_TOKEN"}
    assert "KIS_" not in json.dumps(WORKFLOW)
    assert "-X ours" not in DURABLE["run"] and "rebase --abort" not in DURABLE["run"]
    assert not any(step.get("continue-on-error") for step in STEPS)


def test_data_only_commit_still_skips_vercel_deployment(repos):
    repos.prepare()
    result = repos.run(DURABLE["run"])
    assert result.returncode == 0, result.stdout + result.stderr
    changed = repos.git(repos.worker, "diff", "--name-only", repos.source_head, "HEAD").stdout.splitlines()
    assert set(changed) == set(ARTIFACTS)
    command = json.loads((ROOT / "vercel-api/vercel.json").read_text())["ignoreCommand"]
    ignored = subprocess.run(command, shell=True, cwd=repos.worker / "vercel-api",
        env={**repos.run_env, "VERCEL_GIT_PREVIOUS_SHA": repos.source_head},
        capture_output=True, text=True, timeout=15)
    assert ignored.returncode == 0, ignored.stdout + ignored.stderr


def test_workflow_shell_blocks_are_syntactically_valid():
    for step in STEPS:
        if step.get("run"):
            result = subprocess.run(["bash", "-n"], input=step["run"], capture_output=True, text=True)
            assert result.returncode == 0, result.stderr
