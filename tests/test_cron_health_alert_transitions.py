import json
import sys

from scripts import cron_health_monitor as monitor


def report(severity="FAIL", findings=None, checked_at="2026-10-21T22:14:15+09:00"):
    return {
        "severity": severity,
        "findings": findings or [],
        "checked_at": checked_at,
        "window_hours": 24,
    }


def persisted(value, status="sent", event="opened", recovered=None):
    row = dict(value)
    row["alert_incident_fingerprint"] = monitor._incident_fingerprint(value)
    row["alert_notification_status"] = status
    row["alert_event"] = event
    row["alert_recovered_fingerprint"] = recovered
    return row


def test_incident_fingerprint_ignores_age_counts_order_and_rate_limit_context():
    earlier = report(findings=[
        "universe_scan fail 1건",
        "rate_limit 15건 (wrapper cooler 정상 동작 의미일 수도)",
        "freshness stale(P1+): event_study 765.2h>240.0h(14400분), logo_map 2472.8h>2160.0h(129600분)",
        "🔴 member_map_judgments.yml 3연속 실패 (13h 전) — 스스로 낫지 않는 고장, 원인 진단 필요",
    ])
    later = report(findings=[
        "🔴 member_map_judgments.yml 4연속 실패 (14h 전) — 스스로 낫지 않는 고장, 원인 진단 필요",
        "freshness stale(P1+): event_study 766.2h>240.0h(14400분), logo_map 2473.8h>2160.0h(129600분)",
        "rate_limit 19건 (wrapper cooler 정상 동작 의미일 수도)",
        "universe_scan fail 2건",
    ], checked_at="2026-10-21T23:14:15+09:00")
    assert monitor._incident_fingerprint(earlier) == monitor._incident_fingerprint(later)


def test_new_issue_or_severity_change_changes_incident_fingerprint():
    base = report("WARNING", ["freshness stale(P1+): event_study 765.2h>240.0h(14400분)"])
    added = report("WARNING", base["findings"] + ["universe_scan fail 1건"])
    escalated = report("FAIL", base["findings"])
    assert monitor._incident_fingerprint(base) != monitor._incident_fingerprint(added)
    assert monitor._incident_fingerprint(base) != monitor._incident_fingerprint(escalated)


def test_warning_context_does_not_reopen_fail_but_new_fail_driver_does():
    base = report("FAIL", [
        "universe_scan fail 1건",
        "freshness stale(P1+): event_study 765.2h>240.0h(14400분)",
    ])
    warning_changed = report("FAIL", [
        "universe_scan fail 2건",
        "freshness stale(P1+): logo_map 2472.8h>2160.0h(129600분)",
    ])
    critical_added = report("FAIL", warning_changed["findings"] + [
        "freshness P0 stale: source_quality:macro 3.0h>2.0h(120분)",
    ])
    assert monitor._incident_fingerprint(base) == monitor._incident_fingerprint(warning_changed)
    assert monitor._incident_fingerprint(base) != monitor._incident_fingerprint(critical_added)


def test_alert_plan_opens_suppresses_retries_changes_and_reopens_after_recovery():
    current = report(findings=["universe_scan fail 1건"])
    opened = monitor._plan_alert(current, None, notify_enabled=True, always_notify=False)
    assert opened["event"] == "opened" and opened["should_notify"]

    sent = persisted(current, "sent")
    unchanged = monitor._plan_alert(current, sent, notify_enabled=True, always_notify=False)
    assert unchanged["event"] == "unchanged"
    assert not unchanged["should_notify"]
    assert unchanged["notification_status"] == "already_sent"

    failed = persisted(current, "failed")
    retry = monitor._plan_alert(current, failed, notify_enabled=True, always_notify=False)
    assert retry["event"] == "retry" and retry["should_notify"]

    changed_report = report(findings=[
        "universe_scan fail 2건",
        "freshness P0 stale: source_quality:macro 3.0h>2.0h(120분)",
    ])
    changed = monitor._plan_alert(changed_report, sent, notify_enabled=True, always_notify=False)
    assert changed["event"] == "changed" and changed["should_notify"]

    healthy = report("PASS")
    recovered = monitor._plan_alert(healthy, sent, notify_enabled=True, always_notify=False)
    assert recovered["event"] == "recovered" and recovered["should_notify"]
    closed = persisted(healthy, "sent", event="recovered",
                       recovered=recovered["recovered_fingerprint"])
    stable = monitor._plan_alert(healthy, closed, notify_enabled=True, always_notify=False)
    assert stable["event"] == "healthy" and not stable["should_notify"]
    reopened = monitor._plan_alert(current, closed, notify_enabled=True, always_notify=False)
    assert reopened["event"] == "opened" and reopened["should_notify"]


def test_failed_recovery_is_retried_and_always_notify_keeps_snapshot_semantics():
    failing = report(findings=["universe_scan fail 1건"])
    healthy = report("PASS")
    recovery_fp = monitor._incident_fingerprint(failing)
    failed_recovery = persisted(healthy, "failed", event="recovered", recovered=recovery_fp)
    retry = monitor._plan_alert(healthy, failed_recovery,
                                notify_enabled=True, always_notify=False)
    assert retry["event"] == "recovered" and retry["should_notify"]
    snapshot = monitor._plan_alert(failing, persisted(failing),
                                   notify_enabled=True, always_notify=True)
    assert snapshot["event"] == "snapshot" and snapshot["should_notify"]


def test_disabled_notification_does_not_become_sent_state():
    current = report(findings=["universe_scan fail 1건"])
    disabled = monitor._plan_alert(current, None, notify_enabled=False, always_notify=False)
    assert not disabled["should_notify"]
    assert disabled["notification_status"] == "disabled"
    previous = persisted(current, "disabled")
    retry = monitor._plan_alert(current, previous, notify_enabled=True, always_notify=False)
    assert retry["event"] == "retry" and retry["should_notify"]


def test_notification_result_updates_only_matching_latest_persisted_row(tmp_path):
    path = tmp_path / "cron_health.jsonl"
    current = report(findings=["universe_scan fail 1건"])
    current.update({
        "alert_incident_fingerprint": monitor._incident_fingerprint(current),
        "alert_event": "opened",
        "alert_notification_status": "pending",
        "alert_recovered_fingerprint": None,
    })
    first = {"ts_kst": "2026-10-21T21:14:15+09:00", "severity": "PASS"}
    latest = {
        "ts_kst": current["checked_at"],
        "severity": current["severity"],
        "alert_incident_fingerprint": current["alert_incident_fingerprint"],
        "alert_event": current["alert_event"],
        "alert_notification_status": "pending",
    }
    path.write_text("\n".join(json.dumps(x) for x in (first, latest)) + "\n")
    assert monitor._mark_persisted_notification(current, "failed", str(path))
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert rows[0] == first
    assert rows[1]["alert_notification_status"] == "failed"
    assert current["alert_notification_status"] == "failed"


def test_main_persists_before_send_and_records_failed_delivery(monkeypatch):
    current = report("WARNING", ["event_study stale"])
    current.update({
        "daily_summary": {"success": 1, "total": 1, "failure": 0},
        "universe_scan_summary": {"success": 1, "total": 1},
        "macro_collect_summary": {"total": 1, "fail_rate": 0.0},
        "runtime_metrics": {"yf_fail_max": 0.0, "rate_limit_max": 0},
    })
    calls = []
    monkeypatch.setattr(monitor, "analyze", lambda hours_window: current)
    monkeypatch.setattr(monitor, "_load_previous_alert_entry", lambda: None)
    monkeypatch.setattr(monitor, "_persist_report",
                        lambda value: calls.append(("persist", value["alert_notification_status"])))
    monkeypatch.setattr(monitor, "_notify_telegram",
                        lambda lines: calls.append(("notify", lines[0])) or False)
    monkeypatch.setattr(monitor, "_mark_persisted_notification",
                        lambda value, status: calls.append(("mark", status)) or True)
    monkeypatch.setattr(sys, "argv", ["cron_health_monitor.py", "--notify"])
    assert monitor.main() == 0
    assert calls[0] == ("persist", "pending")
    assert calls[1][0] == "notify"
    assert calls[2] == ("mark", "failed")
