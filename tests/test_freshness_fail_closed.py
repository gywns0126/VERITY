"""Missing evidence and partial refreshes must not become a healthy stream."""
import json
from datetime import datetime, timedelta, timezone

import pytest

from api.builders import freshness_board_builder as board
from api.observability import data_pipeline_health as pipeline
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


def setup_pipeline_macro(tmp_path, monkeypatch, payload):
    monkeypatch.setattr(pipeline, "_REPO_ROOT", tmp_path)
    monkeypatch.setattr(pipeline, "_now_kst", lambda: NOW)
    monkeypatch.setattr(pipeline, "_committed_content_ts", lambda *args, **kwargs: None)
    monkeypatch.setattr(pipeline, "_alert_egregious_freezes", lambda health: None)
    source = next(s for s in pipeline.SOURCES if s["key"] == "macro_snapshot")
    monkeypatch.setattr(pipeline, "SOURCES", [source])
    if payload is not None:
        path = tmp_path / source["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload))
    return source


def test_pipeline_writer_does_not_count_partial_macro_as_fresh(tmp_path, monkeypatch):
    setup_pipeline_macro(tmp_path, monkeypatch, {
        "collected_at": NOW.isoformat(),
        "collector_meta": {"macro": {"stale": True, "reused": True},
                           "bonds": {"stale": True, "reused": False}},
        "diagnostics": {"macro_ok": False, "bonds_ok": False, "events_ok": True},
    })
    output = tmp_path / "health.json"
    result = pipeline.write_data_pipeline_health(output_path=output)
    assert json.loads(output.read_text()) == result
    assert result["overall_status"] == "warn"
    assert result["summary"] == {"fresh": 0, "stale": 1, "missing": 0, "total": 1}
    row = result["items"][0]
    assert row["status"] == "stale"
    assert row["clock_status"] == "fresh"
    assert row["source_status"] == "partial"
    assert row["source_issues"] == ["macro", "bonds"]
    assert result["schema_version"] == "v0"


@pytest.mark.parametrize("age,status", [(0, "fresh"), (6, "fresh"), (7, "stale"), (13, "missing")])
def test_pipeline_source_check_preserves_existing_clock_thresholds(tmp_path, monkeypatch, age, status):
    source = setup_pipeline_macro(tmp_path, monkeypatch, {
        "collected_at": (NOW - timedelta(hours=age)).isoformat(),
        "collector_meta": {"macro": {"stale": False, "reused": True}},
        "diagnostics": {"macro_ok": True, "bonds_ok": True, "events_ok": True},
    })
    row = pipeline._diagnose_one(source)
    assert row["clock_status"] == row["status"] == status
    assert "source_issues" not in row  # Reuse alone is not a declared source failure.


def test_pipeline_partial_source_cannot_downgrade_missing_clock(tmp_path, monkeypatch):
    source = setup_pipeline_macro(tmp_path, monkeypatch, {
        "collected_at": (NOW - timedelta(hours=13)).isoformat(),
        "diagnostics": {"macro_ok": False},
    })
    row = pipeline._diagnose_one(source)
    assert row["clock_status"] == row["status"] == "missing"
    assert row["source_issues"] == ["macro"]
    assert pipeline.collect_data_pipeline_health()["overall_status"] == "error"


def test_pipeline_missing_file_remains_missing(tmp_path, monkeypatch):
    source = setup_pipeline_macro(tmp_path, monkeypatch, None)
    row = pipeline._diagnose_one(source)
    assert row["status"] == row["clock_status"] == "missing"
    assert row["exists"] is False
    assert pipeline.collect_data_pipeline_health()["overall_status"] == "error"


@pytest.mark.parametrize("key", ["collector_meta", "diagnostics"])
def test_pipeline_reuses_invalid_source_metadata_contract(tmp_path, monkeypatch, key):
    source = setup_pipeline_macro(tmp_path, monkeypatch, {"collected_at": NOW.isoformat(), key: ["bad"]})
    row = pipeline._diagnose_one(source)
    assert row["status"] == "stale"
    assert row["source_issues"] == ["invalid_source_metadata"]
