"""Missing evidence and partial refreshes must not become a healthy stream."""
import json
from datetime import datetime, timedelta, timezone

import pytest

from api.builders import freshness_board_builder as board
from scripts import freshness_shadow_monitor as monitor

NOW = datetime(2026, 10, 19, 12, tzinfo=timezone(timedelta(hours=9)))


def setup_stream(tmp_path, monkeypatch, **fields):
    spec = {"id": "input", "file": "input.json", "criticality": "P0",
            "schedule": "always", "max_age_minutes": 90, **fields}
    manifest = tmp_path / "freshness_sla.json"
    manifest.write_text(json.dumps({"streams": [spec]}))
    for mod in (board, monitor):
        monkeypatch.setattr(mod, "DATA_DIR", str(tmp_path))
        monkeypatch.setattr(mod, "MANIFEST", str(manifest))
        monkeypatch.setattr(mod, "now_kst", lambda: NOW)


@pytest.mark.parametrize("payload,status", [(None, "missing"), ("broken", "unreadable"),
    ({}, "no_ts"), ({"generated_at": "bad"}, "bad_ts")])
def test_unmeasured_is_actionable_and_remains_in_denominator(tmp_path, monkeypatch, payload, status):
    setup_stream(tmp_path, monkeypatch)
    if payload is not None:
        (tmp_path / "input.json").write_text(payload if isinstance(payload, str) else json.dumps(payload))
    row = monitor.build_observations()["rows"][0]
    assert row["status"] == status
    assert row["would_alarm"] is True
    assert row["criticality"] == "P0"
    assert monitor.format_freshness_alarm(row) == f"input {status}"
    result = board.build_board()
    assert result["summary"]["p0"] == {"total": 1, "fresh": 0, "closed": 0,
                                      "active": 1, "unmeasured": 1}


def test_one_fresh_member_cannot_hide_an_old_member(tmp_path, monkeypatch):
    setup_stream(tmp_path, monkeypatch, file="group_*.json")
    for name, stamp in (("new", NOW), ("old", NOW - timedelta(hours=10))):
        (tmp_path / f"group_{name}.json").write_text(json.dumps({"generated_at": stamp.isoformat()}))
    obs = monitor.build_observations()["rows"][0]
    assert obs["would_alarm"] is True
    assert obs["age_eff_min"] == 600
    result = board.build_board()["streams"][0]
    assert result["status"] == "stale"
    assert result["group_counts"] == {"members": 2, "measured": 2, "unmeasured": 0}


def test_unreadable_group_member_is_not_dropped(tmp_path, monkeypatch):
    setup_stream(tmp_path, monkeypatch, file="group_*.json")
    (tmp_path / "group_new.json").write_text(json.dumps({"generated_at": NOW.isoformat()}))
    (tmp_path / "group_bad.json").write_text("broken")
    obs = monitor.build_observations()["rows"][0]
    assert obs["would_alarm"] is True
    assert obs["quality_reason"] == "partial_group"
    assert board.build_board()["streams"][0]["status"] == "stale"


def test_declared_observation_clock_does_not_fall_back_to_generation(tmp_path, monkeypatch):
    setup_stream(tmp_path, monkeypatch, ts_field="_meta.as_of")
    (tmp_path / "input.json").write_text(json.dumps({"generated_at": NOW.isoformat()}))
    assert monitor.build_observations()["rows"][0]["status"] == "no_ts"
    assert board.build_board()["summary"]["fresh"] == 0


def test_partial_macro_source_cannot_be_fresh_just_because_rebuilt(tmp_path, monkeypatch):
    setup_stream(tmp_path, monkeypatch, id="macro_snapshot")
    (tmp_path / "input.json").write_text(json.dumps({"collected_at": NOW.isoformat(),
        "collector_meta": {"macro": {"stale": True}, "bonds": {"stale": False}},
        "diagnostics": {"macro_ok": False, "bonds_ok": True, "events_ok": True}}))
    row = monitor.build_observations()["rows"][0]
    assert row["would_alarm"] is True
    assert monitor.format_freshness_alarm(row) == "macro_snapshot source_quality: macro"
    public = board.build_board()["streams"][0]
    assert public["status"] == "stale"
    assert public["source_issues"] == ["macro"]
    assert public["source_status"] == "partial"


def test_closed_schedule_does_not_page_on_missing_file(tmp_path, monkeypatch):
    setup_stream(tmp_path, monkeypatch, schedule="market_hours")
    monkeypatch.setattr(monitor, "now_kst", lambda: NOW.replace(hour=22))
    monkeypatch.setattr(board, "now_kst", lambda: NOW.replace(hour=22))
    assert monitor.build_observations()["rows"][0]["would_alarm"] is False
    counts = board.build_board()["summary"]["p0"]
    assert counts["total"] == counts["unmeasured"] == 1
    assert counts["active"] == 0


@pytest.mark.parametrize("key", ["collector_meta", "diagnostics"])
def test_bad_macro_metadata_is_a_named_quality_failure(key):
    assert monitor.source_quality_issues("macro_snapshot", {key: ["bad"]}) == ["invalid_source_metadata"]


def test_stale_alarm_still_reports_real_age_and_limit():
    assert monitor.format_freshness_alarm({"id": "crypto", "age_eff_min": 114,
            "max_age_min": 90}) == "crypto 1.9h>1.5h(90분)"
