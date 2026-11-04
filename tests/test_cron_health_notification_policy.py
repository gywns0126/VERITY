import sys
import types

from scripts import cron_health_monitor as monitor


def report(severity, findings=(), **extra):
    return {"severity": severity, "findings": list(findings), **extra}


def row(value, status="sent", event="opened", recovered=None):
    return {**value, "alert_incident_fingerprint": monitor._incident_fingerprint(value),
            "alert_notification_status": status, "alert_event": event,
            "alert_recovered_fingerprint": recovered}


def plan(value, previous=None, *, enabled=True, always=False):
    return monitor._plan_alert(value, previous, notify_enabled=enabled, always_notify=always)


def test_routine_warning_and_pass_are_silent_even_with_snapshot_flag():
    for value in (report("PASS", kis_lock_commits_24h=1),
                  report("WARNING", ["event_study stale 100h"])):
        assert not plan(value)["should_notify"]
        assert not plan(value, always=True)["should_notify"]


def test_critical_warning_escalation_recovery_retry_and_recurrence():
    warning = report("WARNING", ["⚠ KIS 토큰 발급 2회/24h (baseline 1회)"])
    escalated = report("FAIL", ["🚨 KIS 토큰 발급 3회/24h (ABSOLUTE 위반)"])
    routine = report("WARNING", ["event_study stale 100h"])
    assert plan(warning)["event"] == "opened"
    assert not plan(warning, row(warning))["should_notify"]
    assert plan(warning, row(warning, "failed"))["event"] == "retry"
    assert plan(escalated, row(warning))["event"] == "changed"
    recovery = plan(routine, row(escalated))
    assert recovery["event"] == "recovered" and recovery["should_notify"]
    failed = row(routine, "failed", "recovered", recovery["recovered_fingerprint"])
    assert plan(routine, failed)["event"] == "recovered"
    closed = row(routine, "sent", "recovered", recovery["recovered_fingerprint"])
    assert not plan(routine, closed)["should_notify"]
    assert plan(warning, closed)["event"] == "opened"


def test_new_critical_issue_and_variable_ages():
    first = report("FAIL", ["🔴 sample.yml 3연속 실패 (13h 전)"], fred_age_h=25.0)
    same = report("FAIL", ["🔴 sample.yml 4연속 실패 (14h 전)"], fred_age_h=26.0)
    changed = report("FAIL", same["findings"] + ["⚠ KIS 토큰 발급 2회/24h"])
    changed["fred_age_h"] = 26.0
    assert not plan(same, row(first))["should_notify"]
    assert plan(changed, row(same))["event"] == "changed"
    assert plan(first, row(first, "disabled"))["event"] == "retry"


def test_legacy_row_recomputed_and_critical_warning_not_misreported_recovered():
    value = report("WARNING", ["universe_scan fail 1건 (주말 transient 의심)"])
    old = {**value, "alert_incident_fingerprint": "old-policy", "alert_notification_status": "sent"}
    assert not plan(value, old)["should_notify"]
    assert plan(report("FAIL", ["universe_scan fail 1건"]), old)["event"] == "changed"


def test_telegram_false_is_failure_and_essential_tag(monkeypatch):
    calls = []
    fake = types.ModuleType("api.notifications.telegram")
    fake.send_message = lambda message, **kwargs: calls.append((message, kwargs)) or False
    monkeypatch.setitem(sys.modules, "api.notifications.telegram", fake)
    assert not monitor._notify_telegram(["test"])
    assert calls == [("test", {"dedupe": False, "bypass_quiet": True,
                                "notification_kind": "essential"})]


def test_main_persists_before_failed_send_and_keeps_retry(monkeypatch):
    value = report("WARNING", ["⚠ KIS 토큰 발급 2회/24h"],
                   checked_at="2026-11-04T09:00:00+09:00", window_hours=24,
                   daily_summary={"success": 1, "total": 1, "failure": 0},
                   universe_scan_summary={"success": 1, "total": 1},
                   macro_collect_summary={"total": 1, "fail_rate": 0.0},
                   runtime_metrics={"yf_fail_max": 0.0, "rate_limit_max": 0})
    calls = []
    monkeypatch.setattr(monitor, "analyze", lambda hours_window: value)
    monkeypatch.setattr(monitor, "_load_previous_alert_entry", lambda: None)
    monkeypatch.setattr(monitor, "_persist_report", lambda r: calls.append(("persist", r["alert_notification_status"])))
    monkeypatch.setattr(monitor, "_notify_telegram", lambda lines: calls.append(("send", None)) or False)
    monkeypatch.setattr(monitor, "_mark_persisted_notification", lambda r, status: calls.append(("mark", status)) or True)
    monkeypatch.setattr(sys, "argv", ["cron_health_monitor.py", "--notify"])
    assert monitor.main() == 0
    assert calls == [("persist", "pending"), ("send", None), ("mark", "failed")]
    assert plan(value, row(value, "failed"))["event"] == "retry"


def test_pass_critical_lock_persists_without_false_recovery_and_clears(tmp_path, monkeypatch):
    path = tmp_path / "cron_health.jsonl"
    monkeypatch.setattr(monitor, "_alert_history_path", lambda: str(path))
    critical = report("PASS", kis_lock_commits_24h=0, checked_at="2026-11-04T09:00:00+09:00")
    opened = plan(critical)
    assert opened["event"] == "opened" and opened["should_notify"]
    critical.update(alert_incident_fingerprint=opened["incident_fingerprint"],
                    alert_event=opened["event"], alert_notification_status="pending")
    monitor._persist_report(critical)
    assert monitor._mark_persisted_notification(critical, "sent")
    previous = monitor._load_previous_alert_entry()
    assert plan(critical, previous)["event"] == "unchanged"
    assert not plan(critical, previous)["should_notify"]
    recovered = plan(report("PASS", kis_lock_commits_24h=1), previous)
    assert recovered["event"] == "recovered" and recovered["should_notify"]


def test_main_pass_critical_notification_identifies_lock_and_fred(monkeypatch):
    value = report("PASS", kis_lock_commits_24h=0, fred_age_h=25.5,
                   checked_at="2026-11-04T09:00:00+09:00", window_hours=24,
                   daily_summary={"success": 1, "total": 1, "failure": 0},
                   universe_scan_summary={"success": 1, "total": 1},
                   macro_collect_summary={"total": 1, "fail_rate": 0.0},
                   runtime_metrics={"yf_fail_max": 0.0, "rate_limit_max": 0})
    sent = []
    monkeypatch.setattr(monitor, "analyze", lambda hours_window: value)
    monkeypatch.setattr(monitor, "_load_previous_alert_entry", lambda: None)
    monkeypatch.setattr(monitor, "_persist_report", lambda r: None)
    monkeypatch.setattr(monitor, "_notify_telegram", lambda lines: sent.extend(lines) or True)
    monkeypatch.setattr(monitor, "_mark_persisted_notification", lambda r, status: True)
    monkeypatch.setattr(sys, "argv", ["cron_health_monitor.py", "--notify"])
    assert monitor.main() == 0
    assert value["severity"] == "PASS"
    assert "중요 신호" in sent[0] and "PASS" not in sent[0]
    assert any("KIS" in line and "0건" in line for line in sent)
    assert any("FRED" in line and "25.5" in line for line in sent)
