"""Bounded automatic financial delivery; no live dispatch or financial fetch."""
import importlib.util
import io
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 19, 11, tzinfo=timezone.utc)
SLOT = NOW.replace(hour=10, minute=30)


def module():
    spec = importlib.util.spec_from_file_location("financial_schedule_test", ROOT / "vercel-api/us_financials_schedule.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def dispatcher():
    spec = importlib.util.spec_from_file_location("financial_dispatch_test", ROOT / "vercel-api/api/cron/dispatch_pulse.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def run(id=10, event="repository_dispatch", status="completed", conclusion="success"):
    return dict(id=id, event=event, status=status, conclusion=conclusion,
                created_at=SLOT.isoformat(), head_branch="main", head_sha="a" * 40)


def fake_reads(m, monkeypatch, runs, steps=None, total=None):
    calls = []
    def read(repo, token, resource):
        calls.append(resource)
        if "/runs?" in resource:
            return {"workflow_runs": runs, "total_count": len(runs) if total is None else total}
        row_steps = (steps or {}).get(int(resource.split("/")[2]),
                                     {name: "success" for name in m.REQUIRED_STEPS})
        return {"total_count": 1, "jobs": [{"steps": [{"name": n, "conclusion": c}
                                                    for n, c in row_steps.items()]}]}
    monkeypatch.setattr(m, "_read", read)
    return calls


def test_original_daily_slot_and_finite_recovery_window():
    m = module()
    start = datetime(2026, 10, 18, tzinfo=timezone.utc)
    found = []
    for i in range(7 * 1440):
        now = start + timedelta(minutes=i)
        if now.minute % 5 and now.minute != 7:
            continue
        slot = m.dispatch_slot(now)
        if slot:
            assert slot.weekday() < 5
            assert (slot.hour, slot.minute) == (10, 30)
            assert slot <= now < slot + timedelta(hours=4, minutes=20)
            found.append(slot)
    assert len(found) == 5 * 18
    assert len(set(found)) == 5
    assert m.dispatch_slot(datetime(2026, 10, 19, 10, 29, tzinfo=timezone.utc)) is None
    assert m.dispatch_slot(datetime(2026, 10, 19, 14, 50, tzinfo=timezone.utc)) is None
    assert m.latest_slot(datetime(2026, 10, 19, 10, 29, tzinfo=timezone.utc)).isoformat() == "2026-10-16T10:30:00+00:00"


@pytest.mark.parametrize("runs,status,attempts", [([], "missing", 0),
    ([run(status="in_progress", conclusion=None)], "active", 0),
    ([run(event="workflow_dispatch")], "missing", 0),
    ([run()], "delivered", 1),
    ([run(conclusion="failure")], "failed", 1),
    ([run(10, conclusion="failure"), run(11, conclusion="cancelled")], "attempt_limit", 2)])
def test_original_run_and_step_evidence(monkeypatch, runs, status, attempts):
    m = module()
    fake_reads(m, monkeypatch, runs)
    receipt = m.inspect_slot("owner/repo", "test-only", SLOT, NOW)
    assert receipt["status"] == status
    assert receipt["attempt_count"] == attempts


def test_noop_green_is_not_delivery_or_an_attempt(monkeypatch):
    m = module()
    steps = {name: "skipped" for name in m.REQUIRED_STEPS}
    steps[m.GUARD_STEP] = "success"
    fake_reads(m, monkeypatch, [run()], {10: steps})
    receipt = m.inspect_slot("owner/repo", "test-only", SLOT, NOW)
    assert receipt["status"] == "missing"
    assert receipt["attempt_count"] == 0


@pytest.mark.parametrize("missing_step", module().REQUIRED_STEPS)
def test_success_label_without_executed_delivery_steps_is_not_accepted(monkeypatch, missing_step):
    m = module()
    steps = {name: "success" for name in m.REQUIRED_STEPS}
    del steps[missing_step]
    fake_reads(m, monkeypatch, [run()], {10: steps})
    assert m.inspect_slot("owner/repo", "test-only", SLOT, NOW)["status"] == "failed"


def test_guard_excludes_self_and_manual_but_accepts_later_completed_receipt(monkeypatch):
    m = module()
    fake_reads(m, monkeypatch, [run(10), run(11), run(12), run(9, event="workflow_dispatch")])
    receipt = m.inspect_slot("owner/repo", "test-only", SLOT, NOW, exclude_run_id=11)
    assert receipt["delivery_run_id"] == 12


def test_later_queued_run_does_not_block_current_lock_owner(monkeypatch):
    m = module()
    fake_reads(m, monkeypatch, [run(11, status="in_progress"), run(12, status="queued")])
    assert m.inspect_slot("owner/repo", "test-only", SLOT, NOW, exclude_run_id=11)["status"] == "missing"


def test_dependency_failure_is_not_a_successful_duplicate_noop(monkeypatch):
    m = module()
    steps = {name: "skipped" for name in m.REQUIRED_STEPS}
    steps[m.GUARD_STEP] = "success"
    steps["Install dependencies"] = "failure"
    fake_reads(m, monkeypatch, [run(10, conclusion="failure"), run(11, conclusion="failure")],
               {10: steps, 11: steps})
    receipt = m.inspect_slot("owner/repo", "test-only", SLOT, NOW)
    assert receipt["status"] == "attempt_limit"
    assert receipt["attempt_count"] == 2


def test_failed_newer_run_does_not_hide_prior_completed_delivery(monkeypatch):
    m = module()
    fake_reads(m, monkeypatch, [run(10), run(11, conclusion="failure")])
    assert m.inspect_slot("owner/repo", "test-only", SLOT, NOW)["delivery_run_id"] == 10


def test_incomplete_inventory_is_unknown(monkeypatch):
    m = module()
    fake_reads(m, monkeypatch, [], total=101)
    with pytest.raises(RuntimeError, match="Incomplete"):
        m.inspect_slot("owner/repo", "test-only", SLOT, NOW)


def test_api_job_reads_have_a_shared_finite_bound(monkeypatch):
    m = module()
    calls = fake_reads(m, monkeypatch, [run(i, conclusion="failure") for i in range(1, 7)])
    with pytest.raises(RuntimeError, match="budget"):
        m.inspect_slot("owner/repo", "test-only", SLOT, NOW)
    assert len(calls) == 5  # one run inventory plus at most four job inventories


def test_read_error_does_not_expose_upstream_body_or_credential(monkeypatch):
    m = module()
    def fail(*args, **kwargs):
        raise OSError("sensitive upstream body test-secret")
    monkeypatch.setattr(m.urllib.request, "urlopen", fail)
    with pytest.raises(RuntimeError) as exc:
        m._read("owner/repo", "test-secret", "actions/runs")
    assert str(exc.value) == "GitHub cadence read failed: OSError"


def test_wire_payload_and_handler_skip_fail_closed(monkeypatch):
    m = dispatcher()
    class Clock(datetime):
        @staticmethod
        def now(tz):
            return datetime(2026, 10, 19, 11, 45, tzinfo=tz)
    monkeypatch.setattr(m, "datetime", Clock)
    monkeypatch.setattr(m, "CRON_SECRET", "test-only")
    cadence = m._us_financials_cadence()
    calls = []
    monkeypatch.setattr(m, "_dispatch", lambda evt, payload:
                        (calls.append((evt, payload)) or (204, "dispatched")))
    for state, expected_dispatches, expected_http in [("missing", 1, 200), ("failed", 1, 200),
            ("active", 0, 200), ("delivered", 0, 200), ("attempt_limit", 0, 502),
            ("unknown", 0, 502)]:
        calls.clear()
        def inspect(*args):
            if state == "unknown":
                raise RuntimeError("unknown")
            return {"status": state}
        monkeypatch.setattr(cadence, "inspect_slot", inspect)
        request = object.__new__(m.handler)
        request.headers = {"Authorization": "Bearer test-only"}
        request.wfile = io.BytesIO()
        statuses = []
        request.send_response = statuses.append
        request.send_header = lambda *args: None
        request.end_headers = lambda: None
        request.do_GET()
        assert statuses == [expected_http]
        financial = [(e, p) for e, p in calls if e == "us_financials_incremental"]
        assert len(financial) == expected_dispatches
        if financial:
            assert financial[0][1] == {"schedule_slot": SLOT.isoformat()}


def test_existing_cron_config_and_time_budget_are_preserved():
    m = dispatcher()
    config = json.loads((ROOT / "vercel-api/vercel.json").read_text())
    assert config["crons"] == [{"path": "/api/cron/dispatch_pulse",
                                "schedule": "0,5,7,10,15,20,25,30,35,40,45,50,55 * * * *"}]
    assert "git diff --quiet $B HEAD -- vercel-api/" in config["ignoreCommand"]
    assert config["functions"]["api/cron/dispatch_pulse.py"]["includeFiles"] == "us_financials_schedule.py"
    start = datetime(2026, 10, 18, tzinfo=timezone.utc)
    worst = 0
    for i in range(7 * 1440):
        now = start + timedelta(minutes=i)
        events = [m._split_event(e)[0] for e in m._resolve_events(now)]
        bound = len(events) * 8 + 14 * len(m._resolve_backup_events(now))
        bound += 6 if "daily_analysis_quick" in events else 0
        bound += 20 if "us_financials_incremental" in events else 0
        worst = max(worst, bound)
    assert worst < config["functions"]["api/cron/dispatch_pulse.py"]["maxDuration"]


def test_workflow_guard_precedes_network_collection_and_guards_publish():
    doc = yaml.safe_load((ROOT / ".github/workflows/us_financials_incremental.yml").read_text())
    trigger = doc.get("on", doc.get(True))
    assert trigger["repository_dispatch"]["types"] == ["us_financials_incremental"]
    assert doc["permissions"]["actions"] == "read"
    assert doc["concurrency"] == {"group": "verity-us-incremental", "cancel-in-progress": False}
    steps = doc["jobs"]["incremental"]["steps"]
    assert steps[1]["name"] == module().GUARD_STEP
    for step in steps:
        if step.get("id") in ("incr", "report", "quarterly", "quality"):
            assert step["if"] == "steps.slot.outputs.run == 'true'"
    persist = next(s for s in steps if s.get("id") == "persist")
    assert "steps.incr.outcome != 'skipped'" in persist["if"]
    assert "steps.persist.outcome == 'success'" in steps[-1]["if"]


@pytest.mark.parametrize("state,expected", [("missing", "true"), ("failed", "true"),
        ("active", "false"), ("delivered", "false"), ("attempt_limit", "false")])
def test_guard_uses_serialized_remote_receipt(tmp_path, monkeypatch, state, expected):
    m = module()
    event = tmp_path / "event.json"
    output = tmp_path / "out"
    event.write_text(json.dumps({"client_payload": {"schedule_slot": SLOT.isoformat()}}))
    class Clock(datetime):
        @staticmethod
        def now(tz): return NOW
    monkeypatch.setattr(m, "datetime", Clock)
    monkeypatch.setattr(m, "inspect_slot", lambda *args: {"status": state})
    for k, v in {"GITHUB_EVENT_NAME": "repository_dispatch", "GITHUB_EVENT_PATH": str(event),
                 "GITHUB_REPOSITORY": "owner/repo", "GITHUB_RUN_ID": "11",
                 "GITHUB_OUTPUT": str(output)}.items():
        monkeypatch.setenv(k, v)
    assert m.guard() == 0
    assert output.read_text() == f"run={expected}\n"


def test_bad_slot_is_not_a_manual_override(tmp_path, monkeypatch):
    m = module()
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"client_payload": {"schedule_slot": "2099-01-01T10:30:00Z"}}))
    monkeypatch.setenv("GITHUB_EVENT_NAME", "repository_dispatch")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    with pytest.raises(RuntimeError, match="schedule_slot"):
        m.guard()

