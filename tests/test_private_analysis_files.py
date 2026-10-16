"""Public Git staging never receives the newly private evidence fields."""
import json
from pathlib import Path
import subprocess

import pytest
import yaml

from scripts.ci import private_analysis_files as guard
from tests.test_operator_early_delivery import artifacts, NOW


@pytest.fixture
def repository(tmp_path):
    root = tmp_path / "checkout"
    (root / "data").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    return root


def write(path, document):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document))


def test_changed_staged_unknown_and_nested_history_jsonl_are_sanitized(repository):
    root = repository
    private = {"ticker": "ABC", "price": 42, "score": 71,
               "evidence_snapshot": {"input_snapshot": {"private": True}},
               "sec_financials": {"revenue": 3, "_source_evidence": {"revenue": "private"}}}
    staged = root / "data/portfolio.json"
    write(staged, {"recommendations": [private]})
    subprocess.run(["git", "-C", str(root), "add", "data/portfolio.json"], check=True)
    write(root / "data/new_unknown_path.json", {"nested": [private], "analysis_changes": {"private": True}})
    write(root / "data/history/runs/run.json", {"recommendations": [private]})
    lines = root / "data/metadata/trail.jsonl"
    lines.parent.mkdir(parents=True)
    lines.write_text(json.dumps({"row": private}) + '\n\n{"untouched":42}\n')
    assert guard.sanitize_changed_data(root) == 4
    clean = {"ticker": "ABC", "price": 42, "score": 71, "sec_financials": {"revenue": 3}}
    assert json.loads(staged.read_text()) == {"recommendations": [clean]}
    assert json.loads((root / "data/new_unknown_path.json").read_text()) == {"nested": [clean]}
    assert json.loads((root / "data/history/runs/run.json").read_text()) == {"recommendations": [clean]}
    assert json.loads(lines.read_text().splitlines()[0]) == {"row": clean}
    assert lines.read_text().endswith('\n\n{"untouched":42}\n')
    subprocess.run(["git", "-C", str(root), "add", "data/"], check=True)
    indexed = subprocess.run(["git", "-C", str(root), "show", ":data/portfolio.json"],
                             check=True, capture_output=True).stdout
    assert b"evidence_snapshot" not in indexed and b"_source_evidence" not in indexed
    assert json.loads(indexed)["recommendations"][0]["score"] == 71


def test_invalid_or_unsupported_paths_block_before_any_body_is_rewritten(repository):
    root = repository
    write(root / "data/a.json", {"price": 42, "evidence_snapshot": {"private": True}})
    (root / "data/z.jsonl").write_text('{"broken":')
    before = (root / "data/a.json").read_bytes()
    with pytest.raises(ValueError):
        guard.sanitize_changed_data(root)
    assert (root / "data/a.json").read_bytes() == before
    (root / "data/z.jsonl").unlink()
    (root / "data/unknown.txt").write_text('{"input_snapshot":{"private":true}}')
    with pytest.raises(ValueError):
        guard.sanitize_changed_data(root)


def test_data_symlink_is_rejected(repository, tmp_path):
    outside = tmp_path / "private.json"
    write(outside, {"evidence_snapshot": {"private": True}})
    (repository / "data/link.json").symlink_to(outside)
    with pytest.raises(ValueError):
        guard.sanitize_changed_data(repository)


def context(root, tmp_path):
    portfolio, scan = artifacts()
    portfolio["postprocessing"] = {"completed": True}
    portfolio["recommendations"][0]["evidence_snapshot"] = {"input_snapshot": {"private": True}}
    write(root / "data/portfolio.json", portfolio)
    (root / "data/universe_candidates.json").write_bytes(scan)
    env = {"GITHUB_RUN_ID": "456", "GITHUB_RUN_ATTEMPT": "2", "ANALYSIS_MODE": "full",
           "VERITY_MODE": "prod", "UNIVERSE_EXPECTED_SCAN_ID": "gh:123:1",
           "RUNNER_TEMP": str(tmp_path / "runner-temp")}
    return env


def test_final_capture_preserves_postprocessing_and_exact_scan_outside_git(repository, tmp_path):
    env = context(repository, tmp_path)
    body = (repository / "data/portfolio.json").read_bytes()
    snapshot = (repository / "data/universe_candidates.json").read_bytes()
    paths = guard.capture_final_sources(repository, env, NOW)
    assert paths[0].read_bytes() == body and paths[1].read_bytes() == snapshot
    assert json.loads(paths[0].read_bytes())["postprocessing"] == {"completed": True}
    assert guard.capture_final_sources(repository, env, NOW) == paths  # Idempotent same bytes.
    guard.sanitize_changed_data(repository)
    assert b"input_snapshot" not in (repository / "data/portfolio.json").read_bytes()
    assert paths[0].read_bytes() == body
    assert paths[0].parent.parent == Path(env["RUNNER_TEMP"])


@pytest.mark.parametrize("kind", ["staging", "foreign_run", "foreign_scan", "inside_checkout", "conflict"])
def test_capture_rejects_foreign_partial_or_unsafe_destination(repository, tmp_path, kind):
    env = context(repository, tmp_path)
    if kind == "staging": env["VERITY_MODE"] = "staging"
    if kind == "foreign_run": env["GITHUB_RUN_ID"] = "999"
    if kind == "foreign_scan": env["UNIVERSE_EXPECTED_SCAN_ID"] = "gh:999:1"
    if kind == "inside_checkout": env["RUNNER_TEMP"] = str(repository / "data")
    if kind == "conflict":
        path = guard.final_source_paths(repository, env["RUNNER_TEMP"], "456", "2")[0]
        path.parent.mkdir(parents=True)
        path.write_text("foreign bytes")
    with pytest.raises(ValueError):
        guard.capture_final_sources(repository, env, NOW)


def test_main_failure_exits_before_commit_ready(repository, tmp_path, monkeypatch):
    env = context(repository, tmp_path)
    env["GITHUB_RUN_ID"] = "999"
    for key, value in env.items(): monkeypatch.setenv(key, value)
    output = tmp_path / "outputs"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    monkeypatch.chdir(repository)
    monkeypatch.setattr(guard.sys, "argv", ["guard", "--capture-final"])
    assert guard.main() == 1 and not output.exists()


def test_both_workflows_guard_before_broad_stage_and_final_uses_captured_sources():
    root = Path(__file__).resolve().parents[1]
    for workflow in ("daily_analysis_full.yml", "daily_analysis.yml"):
        doc = yaml.safe_load((root / ".github/workflows" / workflow).read_text())
        steps = doc["jobs"]["analyze"]["steps"]
        commit = next(step for step in steps if step["name"] == "Commit & push results")
        run = commit["run"]
        assert run.index("set -euo pipefail") < run.index("private_analysis_files.py") < run.index("git add data/")
        if workflow == "daily_analysis_full.yml":
            assert "--capture-final" in run and "ANALYSIS_MODE" in commit["env"]
            upload = next(step for step in steps if step.get("id") == "final_operator_upload")
            assert "--portfolio-source" in upload["run"] and "--snapshot-source" in upload["run"]
        else:
            assert "--capture-final" not in run
