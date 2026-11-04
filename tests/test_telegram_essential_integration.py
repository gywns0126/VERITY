"""Synthetic notification integration: no real credentials or network."""
import json
import socket
from types import SimpleNamespace

import pytest

import api.config as config
import api.notifications.quiet_hours as quiet
import api.notifications.telegram as telegram


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("TELEGRAM_NOTIFICATION_MODE", "essential")
    monkeypatch.setattr(telegram, "TELEGRAM_BOT_TOKEN", "fixture-token")
    monkeypatch.setattr(telegram, "TELEGRAM_CHAT_ID", "fixture-chat")
    monkeypatch.setattr(telegram, "_VOLUME_LEDGER_PATH", str(tmp_path / "volume.jsonl"))
    monkeypatch.setattr(telegram, "_ALERT_TYPE_LEDGER_PATH", str(tmp_path / "types.jsonl"))
    monkeypatch.setattr(telegram, "_DEDUPE_STORE_PATH", str(tmp_path / "dedupe.json"))
    monkeypatch.setattr(config, "TELEGRAM_CRITICAL_ONLY", False)
    monkeypatch.setattr(quiet, "is_quiet_hours", lambda: False)
    def forbidden(*args, **kwargs):
        raise AssertionError("network forbidden in integration tests")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(telegram.requests, "post", forbidden)


def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def capture_posts(monkeypatch):
    calls = []
    def fake_post(url, **kwargs):
        calls.append(kwargs["json"])
        return SimpleNamespace(status_code=200, text="ok")
    monkeypatch.setattr(telegram.requests, "post", fake_post)
    return calls


def test_routine_is_skipped_before_missing_credentials_and_never_printed(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(telegram, "TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setattr(telegram, "TELEGRAM_CHAT_ID", "")
    assert telegram.send_message("routine-fixture", notification_kind="routine") is False
    assert "routine-fixture" not in capsys.readouterr().out
    entry = rows(tmp_path / "volume.jsonl")[0]
    assert entry["outcome"] == "policy_skip"
    assert not (tmp_path / "dedupe.json").exists()


def test_missing_credentials_essential_retains_no_token_outcome(monkeypatch, tmp_path):
    monkeypatch.setattr(telegram, "TELEGRAM_BOT_TOKEN", "")
    assert not telegram.send_message("essential-fixture", notification_kind="essential")
    assert rows(tmp_path / "volume.jsonl")[0]["outcome"] == "no_token"


@pytest.mark.parametrize("kind", ["essential", "command", "unspecified"])
def test_essential_command_and_unknown_reach_existing_send_gate(monkeypatch, kind):
    posts = capture_posts(monkeypatch)
    assert telegram.send_message("synthetic unknown or actionable", notification_kind=kind)
    assert len(posts) == 1


def test_policy_does_not_bypass_quiet_or_dedupe(monkeypatch, tmp_path):
    posts = capture_posts(monkeypatch)
    monkeypatch.setattr(quiet, "is_quiet_hours", lambda: True)
    assert not telegram.send_message("action", notification_kind="essential")
    assert telegram.send_message("action", notification_kind="essential", bypass_quiet=True)
    assert not telegram.send_message("action", notification_kind="essential", bypass_quiet=True)
    assert [x["outcome"] for x in rows(tmp_path / "volume.jsonl")] == ["quiet_skip", "sent", "dedupe_skip"]
    assert len(posts) == 1


def test_mixed_batch_records_all_but_sends_only_actionable(monkeypatch, tmp_path):
    posts = capture_posts(monkeypatch)
    alerts = [{"level": "CRITICAL", "category": "macro", "message": "macro-only"},
              {"level": "CRITICAL", "category": "earnings", "message": "earnings-only"},
              {"level": "CRITICAL", "category": "geopolitical", "message": "geopolitical-only"},
              {"level": "CRITICAL", "type": "STOP_LOSS", "message": "actionable-risk"}]
    assert telegram.send_alerts(alerts)
    assert len(rows(tmp_path / "types.jsonl")) == 4
    assert len(posts) == 1 and "actionable-risk" in posts[0]["text"]
    assert all(x not in posts[0]["text"] for x in ("macro-only", "earnings-only", "geopolitical-only"))


def test_informational_critical_only_is_recorded_but_not_sent(tmp_path):
    assert not telegram.send_alerts([{"level": "CRITICAL", "category": "macro", "message": "fixture"}])
    assert len(rows(tmp_path / "types.jsonl")) == 1
    assert not (tmp_path / "volume.jsonl").exists()


def test_all_mode_preserves_previous_informational_batch(monkeypatch):
    monkeypatch.setenv("TELEGRAM_NOTIFICATION_MODE", "all")
    posts = capture_posts(monkeypatch)
    assert telegram.send_alerts([{"level": "CRITICAL", "category": "macro", "message": "macro-fixture"}])
    assert "macro-fixture" in posts[0]["text"]


@pytest.mark.parametrize("call", [
    lambda: telegram.send_daily_report({}),
    lambda: telegram.send_morning_briefing({}),
    lambda: telegram.send_cross_verification_alert([{}]),
    lambda: telegram.send_postmortem_report({"failures": [{}]}),
    lambda: telegram.send_vams_simulation_report({"vams": {"simulation_stats": {"total_trades": 1}}}),
    lambda: telegram.send_export_trade_top3([]),
    lambda: telegram.send_export_trade_top3([{}]),
    lambda: telegram.send_timing_signal_alert([{}]),
    lambda: telegram.send_paper_trade_alert([{"type": "NEW_BUY"}]),
    lambda: telegram.send_auto_trade_intent([{}], dry_run=True),
])
def test_routine_producers_do_not_send(call, tmp_path):
    call()
    assert rows(tmp_path / "volume.jsonl")[-1]["outcome"] == "policy_skip"


@pytest.mark.parametrize("call", [
    lambda: telegram.send_deadman_alert(["synthetic"]),
    lambda: telegram.send_auto_trade_intent([{}]),
    lambda: telegram.send_auto_trade_filled([{}]),
    lambda: telegram.send_auto_trade_failed({}, "synthetic"),
    lambda: telegram.send_auto_trade_blocked([{}]),
])
def test_actual_order_and_deadman_are_preserved(monkeypatch, call):
    posts = capture_posts(monkeypatch)
    assert call() is True
    assert len(posts) == 1


@pytest.mark.parametrize("mode,expected", [
    ("essential", ["STOP_LOSS"]),
    ("all", ["macro", "STOP_LOSS"]),
])
def test_realtime_marks_only_actual_policy_selected_items(monkeypatch, mode, expected):
    """Run the real main.py selection/send/mark block with synthetic in-memory data."""
    import ast
    import textwrap
    from pathlib import Path
    from api.notifications.essential_policy import essential_only_enabled, is_essential_alert
    from api.notifications.telegram_dedupe import filter_deduped_realtime_alerts, mark_realtime_alerts_sent, _fingerprint

    monkeypatch.setenv("TELEGRAM_NOTIFICATION_MODE", mode)
    source = (Path(__file__).resolve().parents[1] / "api/main.py").read_text()
    start = source.index('        _level_rank = {"CRITICAL": 0')
    end = source.index('        try:\n            maybe_send_tail_risk_digest', start)
    code = textwrap.dedent(source[start:end])
    ast.parse(code)
    alerts = [{"level": "CRITICAL", "category": "macro", "message": "macro-fixture"},
              {"level": "CRITICAL", "type": "STOP_LOSS", "message": "actionable-fixture"}]
    portfolio = {}; sent = []
    scope = {"TELEGRAM_REALTIME_MIN_LEVEL": "CRITICAL", "briefing": {"alerts": alerts},
             "portfolio": portfolio, "essential_only_enabled": essential_only_enabled,
             "is_essential_alert": is_essential_alert,
             "filter_deduped_realtime_alerts": filter_deduped_realtime_alerts,
             "mark_realtime_alerts_sent": mark_realtime_alerts_sent,
             "send_alerts": lambda selected, sent_alerts: (sent.extend(a for a in selected if not essential_only_enabled() or is_essential_alert(a)), sent_alerts.extend(sent), True)[-1]}
    exec(compile(code, "<synthetic-realtime-selection>", "exec"), scope)
    assert [a.get("type") or a.get("category") for a in sent] == expected
    assert set(portfolio["_telegram_realtime_dedupe"]) == {_fingerprint(a) for a in sent}
    assert alerts[0]["message"] == "macro-fixture"  # analysis input remains intact


def test_mixed_batches_record_all_and_only_successful_batch_is_returned(monkeypatch, tmp_path):
    """Actual sender with a fake first success and second failure; no network."""
    calls = []
    def fake_post(url, **kwargs):
        calls.append(kwargs["json"]["text"])
        return SimpleNamespace(status_code=200 if len(calls) == 1 else 500, text="synthetic")
    monkeypatch.setattr(telegram.requests, "post", fake_post)
    macro = {"level": "CRITICAL", "category": "macro", "message": "informational"}
    risk = {"level": "CRITICAL", "type": "STOP_LOSS", "message": "stop risk"}
    holding = {"level": "WARNING", "category": "holding", "message": "holding risk"}
    delivered = []
    assert telegram.send_alerts([macro, risk, holding], sent_alerts=delivered) is True
    assert delivered == [risk]
    assert len(rows(tmp_path / "types.jsonl")) == 3
    assert len(calls) == 2 and "informational" not in calls[0]
    assert "stop risk" in calls[0] and "holding risk" in calls[1]
    assert [row["outcome"] for row in rows(tmp_path / "volume.jsonl")] == ["sent", "api_fail"]


def test_legacy_boolean_result_and_empty_outlist_on_failure(monkeypatch):
    monkeypatch.setattr(telegram.requests, "post", lambda *a, **kw: SimpleNamespace(status_code=500, text="synthetic"))
    alerts = [{"level": "CRITICAL", "type": "STOP_LOSS", "message": "risk"}]
    delivered = []
    assert telegram.send_alerts(alerts, sent_alerts=delivered) is False
    assert delivered == []
    assert telegram.send_alerts(alerts) is False
