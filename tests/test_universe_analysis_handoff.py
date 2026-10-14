"""Completed persisted scan identity, freshness, and failure preservation."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

import pytest

from api.builders import universe_scan_builder as builder
from api.utils import universe_candidates as loader
from scripts.ci.universe_analysis_gate import decide, analysis_rejection, trigger_decision

NOW = datetime(2026, 10, 14, 17, 0, tzinfo=timezone(timedelta(hours=9)))


def snapshot(age=1):
    source = (NOW - timedelta(hours=age)).isoformat()
    return {"schema_version": "v1", "scan_id": "gh:123:1", "scan_mode": "prod",
            "collected_at": source, "completed_at": NOW.isoformat(),
            "source_as_of": {"KR": source, "US": source},
            "diagnostics": {"ok": True},
            "candidates": [{"ticker": "005930", "currency": "KRW"}]}


@pytest.mark.parametrize("patch", [
    {"schema_version": "v0"}, {"completed_at": None},
    {"diagnostics": {"ok": False}},
    {"diagnostics": {"ok": True, "used_prev_snapshot": True}},
    {"diagnostics": {"ok": True, "kr_starved": True}},
    {"scan_id": "gh:old:1"},
    {"collected_at": (NOW + timedelta(hours=1)).isoformat()},
])
def test_incomplete_failed_or_wrong_producer_rejected(patch):
    doc = snapshot(); doc.update(patch)
    assert loader.snapshot_rejection(doc, 26, NOW, "gh:123:1")


def test_existing_freshness_windows_and_kr_origin():
    assert loader.snapshot_rejection(snapshot(26), 26, NOW) is None
    assert loader.snapshot_rejection(snapshot(26.01), 26, NOW)
    assert loader.snapshot_rejection(snapshot(72), 96, NOW) is None
    assert loader.snapshot_rejection(snapshot(96.01), 96, NOW)
    doc = snapshot(); doc["diagnostics"]["kr_used_prev"] = True
    doc["source_as_of"]["KR"] = (NOW - timedelta(hours=95)).isoformat()
    assert loader.snapshot_rejection(doc, 26, NOW) is None
    doc["source_as_of"]["KR"] = (NOW - timedelta(hours=97)).isoformat()
    assert loader.snapshot_rejection(doc, 26, NOW)


def test_completion_gate_skips_staging_and_duplicate_but_retries_partial():
    doc = snapshot()
    assert decide(doc, {}, "gh:123:1", NOW)[0]
    doc["scan_mode"] = "staging"
    assert not decide(doc, {}, "gh:123:1", NOW)[0]
    doc["scan_mode"] = "prod"
    pf = {"analysis_provenance": {"scan_id": "gh:123:1", "analysis_mode": "full", "status": "completed"}}
    assert not decide(doc, pf, "gh:123:1", NOW)[0]
    pf["analysis_provenance"]["status"] = "started"
    assert decide(doc, pf, "gh:123:1", NOW)[0]


def test_failed_empty_scan_preserves_completed_bytes(tmp_path, monkeypatch):
    out = tmp_path / "snapshot.json"
    out.write_text(json.dumps(snapshot()))
    before = out.read_bytes()
    monkeypatch.setattr(builder, "OUTPUT_PATH", str(out))
    monkeypatch.setattr(builder, "PROMOTE_PATH", str(tmp_path / "no-promotions.json"))
    monkeypatch.setattr(builder, "_now_kst", lambda: NOW)
    monkeypatch.setattr("api.analyzers.stock_filter.run_filter_pipeline_with_ramp_up", lambda **kw: [])
    result = builder.build()
    assert result["scan_id"] == "gh:123:1"
    assert result["collected_at"] == snapshot()["collected_at"]
    assert builder.main() == 1
    assert out.read_bytes() == before


def test_loader_hashes_raw_bytes_and_rechecks_stricter_contract(tmp_path, monkeypatch):
    out = tmp_path / "snapshot.json"
    out.write_text(json.dumps(snapshot(), indent=2))
    monkeypatch.setattr(loader, "SNAPSHOT_PATH", str(out))
    monkeypatch.setattr(loader, "_now_kst", lambda: NOW)
    monkeypatch.setattr("api.utils.dart_pre_attach.attach_dart_to_stocks", lambda *a, **k: {})
    monkeypatch.setenv("UNIVERSE_EXPECTED_SCAN_ID", "gh:123:1")
    loader.reset_cache()
    loaded = loader.load_universe_candidates()
    assert loaded["_load_provenance"]["snapshot_sha256"] == hashlib.sha256(out.read_bytes()).hexdigest()
    monkeypatch.setenv("UNIVERSE_EXPECTED_SCAN_ID", "gh:456:1")
    assert loader.load_universe_candidates() is None


def test_workflow_completion_chain_preserves_us_and_writer_lock():
    import yaml
    root = Path(__file__).resolve().parents[1]
    full = (root / ".github/workflows/daily_analysis_full.yml").read_text()
    assert "workflows: [Universe Scan]" in full
    assert "- cron: '50 7 * * 1-5'" not in full
    assert "- cron: '30 21 * * 2-5'" in full
    assert "UNIVERSE_EXPECTED_SCAN_ID:" in full
    assert "id: writer_gate" in full
    assert "group: verity-data-write" in full
    workflow = yaml.safe_load(full)
    assert "concurrency" not in workflow
    assert "concurrency" not in workflow["jobs"]["guard"]
    for name in ("analyze", "nps_history_only"):
        assert workflow["jobs"][name]["concurrency"] == {
            "group": "verity-data-write", "cancel-in-progress": False,
        }
    quick = (root / ".github/workflows/daily_analysis.yml").read_text()
    assert "ref: main" in quick


def test_every_analyze_step_after_writer_gate_is_gated():
    import yaml
    root = Path(__file__).resolve().parents[1]
    workflow = yaml.safe_load((root / ".github/workflows/daily_analysis_full.yml").read_text())
    steps = workflow["jobs"]["analyze"]["steps"]
    gate = next(i for i, step in enumerate(steps) if step.get("id") == "writer_gate")
    remaining = steps[gate + 1:]
    assert remaining
    for step in remaining:
        assert "steps.writer_gate.outputs.run == '1'" in step.get("if", ""), step["name"]
    contract = next(i for i, step in enumerate(steps) if step.get("id") == "analysis_contract")
    for step in steps[contract + 1:]:
        if step["name"] == "Preserve independent NPS checkpoints after analysis failure":
            assert "steps.nps_holdings.outcome == 'success'" in step["if"]
            assert "steps.analysis_contract.outputs.valid" not in step["if"]
            continue
        assert "steps.analysis_contract.outputs.valid == 'true'" in step["if"], step["name"]


def test_publication_requires_this_completed_analysis_and_keeps_manual_us_policy():
    proof = {"scan_id": "gh:123:1", "analysis_run_id": "456", "analysis_mode": "full",
             "status": "completed", "snapshot_sha256": "a" * 64,
             "collected_at": (NOW - timedelta(hours=1)).isoformat()}
    pf = {"analysis_provenance": proof}
    assert analysis_rejection(pf, "gh:123:1", "456", NOW) is None
    assert analysis_rejection(pf, "gh:123:1", "wrong", NOW)
    proof["status"] = "started"
    assert analysis_rejection(pf, "gh:123:1", "456", NOW)
    proof["status"] = "completed"; proof["scan_id"] = "gh:other:1"
    assert analysis_rejection(pf, "gh:123:1", "456", NOW)
    assert analysis_rejection({}, "", "456", NOW) is None


def test_us_duplicate_rechecked_with_existing_helper(monkeypatch):
    import subprocess
    rows = {"workflow_runs": [
        {"id": 456, "created_at": "2026-10-14T21:30:00Z", "conclusion": None},
        {"id": 123, "created_at": "2026-10-14T21:20:00Z", "conclusion": "success"},
    ]}
    monkeypatch.setenv("EVENT_NAME", "repository_dispatch")
    monkeypatch.setenv("DISPATCH_MODE", "full_us")
    monkeypatch.setenv("GITHUB_REPOSITORY", "test/VERITY")
    monkeypatch.setenv("SELF", "456")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, json.dumps(rows), ""))
    assert trigger_decision(NOW)[0] is False
    rows["workflow_runs"][1]["conclusion"] = "failure"
    assert trigger_decision(NOW)[0] is True


def test_manual_expected_identity_validates_but_allows_explicit_rerun(tmp_path, monkeypatch):
    from scripts.ci import universe_analysis_gate as gate
    data = tmp_path / "data"; data.mkdir(exist_ok=True)
    (data / "universe_candidates.json").write_text(json.dumps(snapshot()))
    monkeypatch.setattr(gate, "ROOT", tmp_path)
    monkeypatch.setenv("EVENT_NAME", "workflow_dispatch")
    monkeypatch.setenv("UNIVERSE_EXPECTED_SCAN_ID", "gh:123:1")
    assert gate.trigger_decision(NOW)[0]
    monkeypatch.setenv("UNIVERSE_EXPECTED_SCAN_ID", "gh:999:1")
    assert not gate.trigger_decision(NOW)[0]
