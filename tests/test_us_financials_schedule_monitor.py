"""Offline tests: no GitHub, provider, Telegram or production-state access."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import yaml

from scripts import us_financials_schedule_monitor as m

SLOT = datetime(2026, 10, 19, 10, 30, tzinfo=timezone.utc)


def helper(status="missing", runs=None, **overrides):
    result = {"slot": m._iso(SLOT), "status": status, "inspected_runs": runs or [],
              "attempt_count": 0, "delivery_run_id": None}
    result.update(overrides)
    return SimpleNamespace(latest_slot=Mock(return_value=SLOT), inspect_slot=Mock(return_value=result))


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(m, "HEALTH_PATH", tmp_path / "health.json")
    monkeypatch.setattr(m, "_load_helper", Mock(side_effect=AssertionError("unmocked helper")))
    monkeypatch.setattr(m, "_send_alert", Mock(side_effect=AssertionError("unmocked alert")))
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GH_TOKEN", "fixture-token")


@pytest.mark.parametrize("minutes,severity,reason", [
    (0, "WARNING", "within_grace"), (30, "WARNING", "within_grace"),
    (30.01, "FAIL", "missing_after_grace"), (60, "FAIL", "missing_after_grace"),
])
def test_missing_grace(minutes, severity, reason):
    h = helper()
    now = SLOT + timedelta(minutes=minutes)
    report = m.inspect("owner/repo", "fixture-token", now, h)
    assert (report["severity"], report["reason"]) == (severity, reason)
    h.latest_slot.assert_called_once_with(now)
    h.inspect_slot.assert_called_once_with("owner/repo", "fixture-token", SLOT, now)


@pytest.mark.parametrize("status", ["failed", "attempt_limit"])
def test_completed_failure_is_not_hidden_by_grace(status):
    report = m.inspect("owner/repo", "fixture-token", SLOT, helper(status))
    assert report["status"] == status
    assert report["severity"] == "FAIL"


def test_delivery_is_explicitly_not_data_quality_acceptance():
    report = m.inspect("owner/repo", "fixture-token", SLOT,
                       helper("delivered", delivery_run_id=123, attempt_count=1))
    assert report["severity"] == "PASS"
    assert report["delivery_run_id"] == 123
    assert report["acceptance_scope"] == "workflow_delivery_only"
    assert "data_quality_accepted" not in report


@pytest.mark.parametrize("minutes,severity", [(45, "WARNING"), (45.01, "FAIL")])
@pytest.mark.parametrize("status", ["queued", "in_progress"])
def test_active_age_includes_queue_time(minutes, severity, status):
    now = SLOT + timedelta(minutes=minutes)
    run = {"id": 12, "status": status, "created_at": m._iso(SLOT),
           "run_started_at": m._iso(now)}
    report = m.inspect("owner/repo", "fixture-token", now, helper("active", [run]))
    assert report["severity"] == severity
    assert report["active_age_minutes"] == round(minutes, 2)


def test_oldest_active_run_and_camel_case_metadata():
    runs = [{"id": 11, "status": "in_progress", "createdAt": m._iso(SLOT)},
            {"id": 12, "status": "queued", "created_at": m._iso(SLOT + timedelta(minutes=40))},
            {"id": 10, "status": "completed", "created_at": "malformed"}]
    report = m.inspect("owner/repo", "fixture-token", SLOT + timedelta(minutes=46), helper("active", runs))
    assert report["severity"] == "FAIL"
    assert report["active_age_minutes"] == 46


@pytest.mark.parametrize("overrides", [
    {"status": "unexpected"}, {"slot": "2026-10-18T10:30:00Z"},
    {"inspected_runs": "body"}, {"inspected_runs": [None]},
    {"attempt_count": True}, {"attempt_count": -1},
    {"status": "delivered", "delivery_run_id": None},
    {"status": "active", "inspected_runs": []},
    {"status": "active", "inspected_runs": [{"status": "queued"}]},
    {"status": "active", "inspected_runs": [{"status": "queued", "created_at": "2027-01-01T00:00:00Z"}]},
])
def test_malformed_helper_result_is_unknown_not_pass(overrides):
    report = m.inspect("owner/repo", "fixture-token", SLOT + timedelta(hours=1), helper(**overrides))
    assert (report["status"], report["severity"]) == ("unknown", "UNKNOWN")


def test_api_unknown_never_becomes_missing_or_leaks_exception():
    h = helper()
    h.inspect_slot.side_effect = RuntimeError("token=do-not-print private response body")
    report = m.inspect("owner/repo", "fixture-token", SLOT, h)
    assert report["slot"] == m._iso(SLOT)
    assert report["severity"] == "UNKNOWN"
    assert report["status"] == "unknown"
    assert "do-not-print" not in json.dumps(report)


def test_missing_credentials_do_not_query_helper():
    h = helper()
    report = m.inspect("owner/repo", "", SLOT, h)
    assert report["status"] == "unknown"
    h.inspect_slot.assert_not_called()


def test_allowlisted_metadata_only():
    run = {"id": 3, "event": "schedule", "status": "completed", "head_sha": "abc",
           "head_branch": "main", "arbitrary_response_body": "never-persist", "token": "never-persist"}
    report = m.inspect("owner/repo", "fixture-token", SLOT, helper("failed", [run]))
    assert report["inspected_runs"] == [{k: v for k, v in run.items() if k not in {"token", "arbitrary_response_body"}}]
    assert "never-persist" not in json.dumps(report)


def test_notify_once_per_slot_and_status_with_persisted_state(tmp_path):
    path = tmp_path / "health.json"
    send = Mock(return_value=True)
    now = SLOT + timedelta(hours=1)
    first = m.monitor("owner/repo", "fixture-token", now=now, path=path, notify=True, helper=helper(), sender=send)
    second = m.monitor("owner/repo", "fixture-token", now=now + timedelta(hours=1), path=path,
                       notify=True, helper=helper(), sender=send)
    assert first["alert_outcome"] == "sent"
    assert second["alert_outcome"] == "already_sent"
    assert send.call_count == 1
    third = m.monitor("owner/repo", "fixture-token", now=now, path=path,
                      notify=True, helper=helper("failed"), sender=send)
    assert third["alert_outcome"] == "sent"
    assert send.call_count == 2
    assert len(json.loads(path.read_text())["alert_state"]) == 2


def test_new_slot_is_new_incident(tmp_path):
    path = tmp_path / "health.json"
    key = f"{m._iso(SLOT - timedelta(days=3))}|missing"
    path.write_text(json.dumps({"alert_state": {key: m._iso(SLOT)}}))
    send = Mock(return_value=True)
    report = m.monitor("owner/repo", "fixture-token", now=SLOT + timedelta(hours=1), path=path,
                       notify=True, helper=helper(), sender=send)
    assert report["alert_outcome"] == "sent"
    assert key in report["alert_state"]
    send.assert_called_once()


@pytest.mark.parametrize("mode", ["disabled", "grace", "active", "delivered"])
def test_no_alert_for_nonincidents_or_disabled_notifications(mode):
    send = Mock()
    h = helper()
    now = SLOT
    if mode == "disabled":
        now += timedelta(hours=1)
    elif mode == "active":
        h = helper("active", [{"status": "queued", "created_at": m._iso(SLOT)}])
    elif mode == "delivered":
        h = helper("delivered", delivery_run_id=12)
    m.monitor("owner/repo", "fixture-token", now=now, notify=mode != "disabled", helper=h, sender=send)
    send.assert_not_called()


@pytest.mark.parametrize("outcome", [False, RuntimeError("secret-transport-url")])
def test_failed_alert_is_not_acknowledged_and_can_retry(outcome, capsys):
    send = Mock(side_effect=outcome) if isinstance(outcome, Exception) else Mock(return_value=outcome)
    report = m.monitor("owner/repo", "fixture-token", now=SLOT + timedelta(hours=1),
                       notify=True, helper=helper(), sender=send)
    assert report["alert_outcome"] == "failed"
    assert report["alert_state"] == {}
    retry = Mock(return_value=True)
    report = m.monitor("owner/repo", "fixture-token", now=SLOT + timedelta(hours=1),
                       notify=True, helper=helper(), sender=retry)
    assert report["alert_outcome"] == "sent"
    assert "secret-transport-url" not in capsys.readouterr().out


def test_api_unknown_notifies_only_once():
    h = helper()
    h.inspect_slot.side_effect = RuntimeError("secret")
    send = Mock(return_value=True)
    for _ in range(2):
        report = m.monitor("owner/repo", "fixture-token", now=SLOT, notify=True, helper=h, sender=send)
        assert report["status"] == "unknown"
    assert send.call_count == 1


@pytest.mark.parametrize("body", ["{broken", "[]", '{"alert_state": []}'])
def test_unreadable_alert_state_is_not_erased_or_resent(body):
    m.HEALTH_PATH.write_text(body)
    send = Mock()
    with pytest.raises((ValueError, AttributeError)):
        m.monitor("owner/repo", "fixture-token", now=SLOT + timedelta(hours=1),
                  notify=True, helper=helper(), sender=send)
    assert m.HEALTH_PATH.read_text() == body
    send.assert_not_called()


def test_atomic_write_failure_preserves_previous_and_cleans_temp(monkeypatch):
    m.HEALTH_PATH.write_text('{"previous": true}')
    monkeypatch.setattr(m.os, "replace", Mock(side_effect=OSError("fixture failure")))
    with pytest.raises(OSError):
        m._write_health(m.HEALTH_PATH, {"new": True})
    assert json.loads(m.HEALTH_PATH.read_text()) == {"previous": True}
    assert list(m.HEALTH_PATH.parent.glob("health.json.*")) == []


@pytest.mark.parametrize("status,severity,code", [("delivered", "PASS", 0), ("missing", "WARNING", 0),
                                                ("missing", "FAIL", 1), ("unknown", "UNKNOWN", 1)])
def test_cli_exit_policy(monkeypatch, capsys, status, severity, code):
    fake = Mock(return_value={"status": status, "severity": severity})
    monkeypatch.setattr(m, "monitor", fake)
    assert m.main(["--notify"]) == code
    assert json.loads(capsys.readouterr().out)["severity"] == severity
    assert fake.call_args.kwargs["notify"] is True


def test_cli_state_failure_is_unknown_and_sanitized(monkeypatch, capsys):
    monkeypatch.setattr(m, "monitor", Mock(side_effect=OSError("secret-path")))
    assert m.main([]) == 1
    output = capsys.readouterr().out
    assert json.loads(output)["status"] == "unknown"
    assert "secret-path" not in output


def test_existing_telegram_transport_is_used_without_exposing_its_logs(monkeypatch, capsys):
    import sys
    def send(*args, **kwargs):
        print("secret-url-token", file=sys.stderr)
        print("private-error")
        assert kwargs == {"dedupe": False, "bypass_quiet": True, "source": "us_financials_schedule_monitor"}
        return True
    monkeypatch.setitem(sys.modules, "api.notifications.telegram", SimpleNamespace(send_message=send))
    # The fixture replaces this boundary; exercise the saved implementation explicitly below.
    assert ORIGINAL_SEND({"slot": m._iso(SLOT), "status": "failed", "severity": "FAIL", "reason": "failed"}) is True
    output = capsys.readouterr()
    assert output.out == output.err == ""


ORIGINAL_SEND = m._send_alert
ORIGINAL_LOAD = m._load_helper


@pytest.mark.parametrize("case,expected,attempts", [
    ("missing", "FAIL", 0), ("manual", "FAIL", 0), ("noop", "FAIL", 0),
    ("delivered", "PASS", 1), ("publish_skipped", "FAIL", 1),
    ("active", "FAIL", 0),
])
def test_real_shared_helper_contract_with_mocked_github(monkeypatch, case, expected, attempts):
    h = ORIGINAL_LOAD()
    run = {"id": 123, "event": "schedule", "head_branch": "main", "head_sha": "fixture-head",
           "created_at": m._iso(SLOT), "status": "completed", "conclusion": "success"}
    steps = [{"name": name, "conclusion": "success"} for name in h.REQUIRED_STEPS]
    if case == "manual":
        run["event"] = "workflow_dispatch"
    elif case == "noop":
        steps[1]["conclusion"] = "skipped"
    elif case == "publish_skipped":
        steps[-1]["conclusion"] = "skipped"
    elif case == "active":
        run.update(status="queued", conclusion=None)
    runs = [] if case == "missing" else [run]
    responses = [{"workflow_runs": runs, "total_count": len(runs)}]
    if case in {"noop", "delivered", "publish_skipped"}:
        responses.append({"jobs": [{"steps": steps}], "total_count": 1})
    read = Mock(side_effect=responses)
    monkeypatch.setattr(h, "_read", read)
    report = m.monitor("owner/repo", "fixture-token", now=SLOT + timedelta(hours=1), helper=h)
    assert report["severity"] == expected
    assert report["attempt_count"] == attempts
    assert report["expected_slot_count"] == 1
    assert read.call_count == len(responses)
    if case == "delivered":
        assert report["delivery_run_id"] == 123
    if case == "noop":
        assert report["inspected_runs"][0]["duplicate_noop"] is True


def test_real_latest_slot_before_monday_due_and_weekend(monkeypatch):
    h = ORIGINAL_LOAD()
    read = Mock(return_value={"workflow_runs": [], "total_count": 0})
    monkeypatch.setattr(h, "_read", read)
    for now in (SLOT - timedelta(hours=1), SLOT - timedelta(days=1)):
        report = m.inspect("owner/repo", "fixture-token", now, h)
        assert report["slot"] == "2026-10-16T10:30:00Z"
        assert report["severity"] == "FAIL"  # Prior unfulfilled Friday, not a future Monday slot.


def test_future_helper_slot_is_unknown_without_query():
    h = helper()
    report = m.inspect("owner/repo", "fixture-token", SLOT - timedelta(seconds=1), h)
    assert report["status"] == "unknown"
    h.inspect_slot.assert_not_called()


def test_workflow_always_checks_and_persists_us_health():
    workflow = yaml.safe_load((Path(__file__).resolve().parents[1] / ".github/workflows/cron_health_monitor.yml").read_text())
    steps = workflow["jobs"]["monitor"]["steps"]
    assert workflow["jobs"]["monitor"]["concurrency"] == {
        "group": "cron-health-monitor", "cancel-in-progress": False,
    }
    assert steps[0]["uses"] == "actions/checkout@v4"
    assert steps[0]["with"]["ref"] == "main"
    index = next(i for i, step in enumerate(steps) if step.get("name") == "Check US financial automatic delivery")
    step = steps[index]
    assert step["if"] == "success() || failure()"
    assert step["run"] == "python scripts/us_financials_schedule_monitor.py --notify"
    assert step["env"]["GH_TOKEN"] == "${{ secrets.GITHUB_TOKEN }}"
    artifact = next(s for s in steps if s.get("uses") == "actions/upload-artifact@v4")
    persist = next(s for s in steps if s.get("id") == "persist")
    assert index < steps.index(artifact) < steps.index(persist)
    assert "data/metadata/us_financials_schedule_health.json" in artifact["with"]["path"]
    assert persist["if"] == "success() || failure()"
    assert "git add -- data/metadata/us_financials_schedule_health.json" in persist["run"]
    assert "github.ref == 'refs/heads/main'" in workflow["jobs"]["monitor"]["if"]
    assert persist["env"]["TARGET_BRANCH"] == "${{ github.ref_name }}"
    assert persist["run"].strip().endswith('python scripts/ci/persist_health_snapshot.py "$TARGET_BRANCH"')
    assert "continue-on-error" not in persist
