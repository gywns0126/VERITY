"""Local pulse control-flow/cost guards. No workflow, Git push, or Blob calls."""
import json
import io
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import urllib.request
from urllib.parse import quote

import pytest
import yaml

from api import config
from api.collectors import dart_catalyst as collector


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/dart_catalyst_pulse.yml"


def steps():
    return yaml.safe_load(WORKFLOW.read_text())["jobs"]["pulse"]["steps"]


def named(name):
    return next(s for s in steps() if s.get("name") == name)


def test_zero_new_build_commit_and_publish_are_attempt_gated():
    for name in ("Build public feed with listing-check evidence", "Commit and push pulse artifacts",
                 "Publish to VERITY-data + Blob", "Verify published Blob source-check evidence"):
        assert named(name)["if"] == "steps.collect.outputs.attempted == 'true'"
    assert named("Build dependent alerts only for new filings")["if"] == (
        "steps.collect.outputs.attempted == 'true' && steps.collect.outputs.new != '0'")
    publish = named("Publish to VERITY-data + Blob")
    assert publish["uses"] == "./.github/actions/publish-data"
    assert "always()" not in publish["if"]  # A failed commit/push must block publication.
    workflow = yaml.safe_load(WORKFLOW.read_text())
    triggers = workflow.get("on", workflow.get(True))
    assert set(triggers) == {"repository_dispatch", "workflow_dispatch"}
    assert workflow["concurrency"] == {"group": "verity-catalyst-pulse", "cancel-in-progress": True}
    assert workflow["jobs"]["pulse"]["timeout-minutes"] == 15


def test_incomplete_collection_fails_only_after_publication():
    sequence = steps()
    publish = named("Publish to VERITY-data + Blob")
    verify = named("Verify published Blob source-check evidence")
    final = named("Fail incomplete collection after publishing evidence")
    assert sequence.index(final) > sequence.index(verify) > sequence.index(publish)
    assert final == sequence[-1]
    assert final["if"] == (
        "steps.collect.outputs.attempted == 'true' && steps.collect.outputs.collection_status != 'success'")
    completed = subprocess.run(["bash", "-c", final["run"]], text=True, capture_output=True)
    assert completed.returncode == 1
    assert "::error::DART listing collection incomplete" in completed.stdout


@pytest.mark.parametrize("scenario,calls_expected,passes", [
    ("match", 1, True), ("retry_match", 3, True), ("old", 3, False),
    ("wrong_status", 3, False), ("timeout", 3, False), ("invalid_json", 3, False),
    ("failed_match", 1, True),
])
def test_blob_readback_is_bounded_exact_and_sanitized(monkeypatch, tmp_path, capsys, scenario, calls_expected, passes):
    monkeypatch.chdir(tmp_path)
    proof = {"attempted_at": "2026-09-27T10:00:00+09:00", "status": "failed" if scenario == "failed_match" else "success"}
    data = tmp_path / "data"
    data.mkdir(exist_ok=True)
    (data / "public_disclosure_feed.json").write_text(json.dumps({"_meta": {"source_collection": proof}}))
    calls, sleeps = [], []

    def fake_open(request, timeout):
        calls.append(request)
        assert timeout == 10
        assert request.full_url == (
            "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/public_disclosure_feed.json"
            "?readback=" + quote(proof["attempted_at"], safe=""))
        assert request.get_method() == "GET"
        assert not any(k.lower() in ("authorization", "cookie") for k in request.headers)
        if scenario == "timeout":
            raise TimeoutError("SECRET_EXCEPTION_DETAIL")
        if scenario == "invalid_json":
            return io.BytesIO(b"SECRET_REMOTE_RESPONSE")
        remote = dict(proof)
        if scenario == "old" or (scenario == "retry_match" and len(calls) < 3):
            remote["attempted_at"] = "2026-09-26T10:00:00+09:00"
        if scenario == "wrong_status":
            remote["status"] = "partial"
        return io.BytesIO(json.dumps({"_meta": {"source_collection": remote}}).encode())

    monkeypatch.setattr(urllib.request, "urlopen", fake_open)
    monkeypatch.setattr(time, "sleep", sleeps.append)
    body = named("Verify published Blob source-check evidence")["run"]
    code = body.split("python - <<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
    if passes:
        exec(compile(code, "<local Blob readback fixture>", "exec"), {})
    else:
        with pytest.raises(SystemExit, match="publication not verified"):
            exec(compile(code, "<local Blob readback fixture>", "exec"), {})
    assert len(calls) == calls_expected
    assert sleeps == [5] * (calls_expected - 1)
    logs = capsys.readouterr()
    assert "SECRET" not in logs.out + logs.err


def test_missing_local_readback_proof_fails_without_network(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    def no_network(*args, **kwargs):
        pytest.fail("No request allowed without local proof")

    monkeypatch.setattr(urllib.request, "urlopen", no_network)
    body = named("Verify published Blob source-check evidence")["run"]
    code = body.split("python - <<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
    with pytest.raises(SystemExit, match="artifact source-check evidence unavailable"):
        exec(compile(code, "<missing local proof fixture>", "exec"), {})


@pytest.mark.parametrize("status", ["success", "partial", "failed"])
def test_zero_new_collection_output_includes_recorded_attempt(monkeypatch, tmp_path, status):
    proof = {"status": status, "attempted_at": "fixture-time"}
    result = {"events": [], "source_collection": proof}
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(collector, "fetch_catalysts_market_wide", lambda **kw: result)
    monkeypatch.setattr(collector, "persist_catalyst_alerts", lambda events: 0)
    metadata = tmp_path / "metadata"
    metadata.mkdir()
    (metadata / "dart_catalyst_heartbeat.json").write_text(json.dumps({"source_collection": proof}))
    output = tmp_path / "output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    body = next(s["run"] for s in steps() if s.get("id") == "collect")
    code = body.split("python - <<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
    exec(compile(code, "<pulse collection fixture>", "exec"), {})
    assert output.read_text().splitlines() == ["new=0", "attempted=true", f"collection_status={status}"]
    (metadata / "dart_catalyst_heartbeat.json").write_text('{"last_run_at":"old"}')
    output.unlink()
    with pytest.raises(RuntimeError, match="not persisted"):
        exec(compile(code, "<pulse stale heartbeat fixture>", "exec"), {})
    assert not output.exists()


@pytest.mark.parametrize("new", ["0", "2"])
def test_explicit_staging_excludes_unrelated_files(tmp_path, new):
    optional = ["data/metadata/business_overview_state.json", "data/calendar_public.json", "data/urgent_alerts.json"]
    for name in optional:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}")
    script = named("Commit and push pulse artifacts")["run"]
    script = script.replace("${{ github.ref_name }}", "main")
    # Mock every Git command; quiet diff exits before any commit/push branch.
    stub = 'git() { printf "%s\\n" "$*" >> "$TASK_GIT_LOG"; return 0; }\n'
    log = tmp_path / "git.log"
    subprocess.run(["bash", "-e", "-c", stub + script], cwd=tmp_path,
                   env={**os.environ, "NEW": new, "TASK_GIT_LOG": str(log)}, check=True, capture_output=True)
    commands = log.read_text().splitlines()
    additions = [cmd.removeprefix("add -- ") for cmd in commands if cmd.startswith("add -- ")]
    expected = ["data/metadata/dart_catalyst_heartbeat.json", "data/public_disclosure_feed.json"]
    if new != "0":
        expected += ["data/dart_catalyst_alerts.jsonl", "data/stock_change_public/",
                     "data/portfolio_exposure_map.json", *optional]
    assert additions == expected
    assert not any(cmd.startswith(("commit ", "push ")) for cmd in commands)
    assert "git add data/" not in script and "git add -A" not in script


def test_pulse_shell_blocks_parse_without_execution():
    for step in steps():
        if "run" in step:
            script = re.sub(r"\$\{\{.*?\}\}", "fixture", step["run"])
            subprocess.run(["bash", "-n"], input=script, text=True, check=True, capture_output=True)


@pytest.mark.parametrize("api_changed,exit_code", [(False, 0), (True, 1)])
def test_vercel_ignore_guard_still_skips_data_only_commits(tmp_path, api_changed, exit_code):
    command = json.loads((ROOT / "vercel-api/vercel.json").read_text())["ignoreCommand"]
    assert "git diff --quiet $B HEAD -- vercel-api/" in command
    assert "VERCEL_GIT_PREVIOUS_SHA" in command
    cwd = tmp_path / "vercel-api"
    cwd.mkdir()
    # Execute the actual guard with deterministic Git responses, never a deploy.
    stub = 'git() { if [ "$1" = diff ]; then return "$TASK_API_CHANGED"; fi; return 0; }; export -f git;\n'
    completed = subprocess.run(["bash", "-c", stub + command], cwd=cwd,
                               env={**os.environ, "VERCEL_GIT_PREVIOUS_SHA": "fixture",
                                    "TASK_API_CHANGED": "1" if api_changed else "0"}, capture_output=True)
    assert completed.returncode == exit_code


@pytest.mark.parametrize("manifest_mode,expected_files", [
    ("valid", ["public_disclosure_feed.json"]),
    ("missing", ["public_disclosure_feed.json", "unchanged.json"]),
])
def test_existing_uploader_hash_skips_unchanged_content(tmp_path, manifest_mode, expected_files):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node required for the existing JavaScript uploader fixture")
    (tmp_path / "public_disclosure_feed.json").write_text('{"_meta":{"source_collection":{"status":"success"}}}')
    (tmp_path / "unchanged.json").write_text('{"unchanged":true}')
    # Run the unchanged uploader in a VM: Blob SDK and manifest fetch are in-memory fakes.
    script = r'''
    const fs = require("fs"), crypto = require("crypto"), vm = require("vm");
    const [sourcePath, dir, mode] = process.argv.slice(2);
    const puts = [], deletions = [], errors = [];
    const hashes = {"unchanged.json": crypto.createHash("sha256").update(fs.readFileSync(dir + "/unchanged.json")).digest("hex")};
    const context = {
      require: name => name === "@vercel/blob" ? {
        put: async name => { puts.push(name); return {url: "fixture"}; },
        del: async name => { deletions.push(name); }
      } : require(name),
      process: {argv: ["node", "uploader", dir], env: {BLOB_READ_WRITE_TOKEN: "local-fake", BLOB_MANIFEST_SCOPE: "fixture"},
                exit: code => {throw Error("unexpected exit " + code);}},
      fetch: async () => ({ok: mode === "valid", status: 404,
                          json: async () => ({generated_at: new Date().toISOString(), hashes})}),
      Buffer, setTimeout,
      console: {log: () => {}, error: (...args) => errors.push(args.join(" "))}
    };
    Promise.resolve(vm.runInNewContext(fs.readFileSync(sourcePath, "utf8"), context)).then(() => {
      process.stdout.write(JSON.stringify({puts, deleteCount: deletions.length, errors}));
    }).catch(error => {throw error;});
    '''
    completed = subprocess.run([node, "-", str(ROOT / ".github/actions/publish-data/blob_upload.js"),
                                str(tmp_path), manifest_mode], input=script, text=True,
                               capture_output=True, check=True)
    result = json.loads(completed.stdout)
    assert sorted(result["puts"]) == sorted(expected_files + ["_blob_manifest__fixture.json"])
    assert result["deleteCount"] > 0  # Retired-Blob cleanup remains an existing per-run cost.
    assert result["errors"] == []
