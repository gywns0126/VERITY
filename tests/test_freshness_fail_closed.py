"""Missing evidence and partial refreshes must not become a healthy stream."""
import json
import os
import re
import subprocess
from types import SimpleNamespace
from datetime import datetime, timedelta, timezone
from pathlib import Path

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


def test_dividends_source_clock_missing_is_unmeasurable_not_fresh(tmp_path, monkeypatch):
    setup_stream(
        tmp_path, monkeypatch, id="dividends_kr", ts_field="_meta.source_as_of",
        missing_ts_status="unmeasurable", measurement_reason="source_as_of_missing",
    )
    (tmp_path / "input.json").write_text(json.dumps({
        "005930": [{
            "updated_at": NOW.isoformat(),
            "checked_at": NOW.isoformat(),
            "ex_date": "2027-12-31",
        }],
    }))
    observed = monitor.build_observations()["rows"][0]
    assert observed["status"] == "unmeasurable"
    assert observed["quality_reason"] == "source_as_of_missing"
    assert observed["would_alarm"] is True
    assert "last_ts" not in observed

    result = board.build_board()
    assert result["streams"] == []
    assert result["_skipped"] == [{
        "id": "dividends_kr", "reason": "no_ts",
        "measurement_reason": "source_as_of_missing",
    }]
    assert result["summary"]["p0"] == {
        "total": 1, "fresh": 0, "closed": 0, "active": 1, "unmeasured": 1,
    }


def test_dividends_source_as_of_wins_over_future_ex_date(tmp_path, monkeypatch):
    setup_stream(
        tmp_path, monkeypatch, id="dividends_kr", ts_field="_meta.source_as_of",
        missing_ts_status="unmeasurable", measurement_reason="source_as_of_missing",
    )
    (tmp_path / "input.json").write_text(json.dumps({
        "_meta": {"source_as_of": (NOW - timedelta(hours=1)).isoformat()},
        "005930": [{"updated_at": NOW.isoformat(), "ex_date": "2027-12-31"}],
    }))
    observed = monitor.build_observations()["rows"][0]
    assert observed["status"] == "checked"
    assert observed["age_eff_min"] == 60
    assert board.build_board()["streams"][0]["status"] == "fresh"


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


def crypto_stream_spec():
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / "data/freshness_sla.json").read_text())
    return next(s for s in manifest["streams"] if s["id"] == "crypto")


def test_crypto_expected_members_match_producer_and_publication_lists():
    root = Path(__file__).resolve().parents[1]
    spec = crypto_stream_spec()
    workflow = (root / ".github/workflows/crypto_collect.yml").read_text()
    producer_line = next(line for line in workflow.splitlines()
                         if line.strip().startswith("git add data/crypto_macro.json"))
    producer_files = {Path(path).name for path in producer_line.split()
                      if path.endswith(".json")}
    publisher = (root / ".github/actions/publish-data/action.yml").read_text()
    public_files = set(re.findall(r"\bcrypto_[a-z_]+\.json\b", publisher))
    assert len(spec["expected_files"]) == 11
    assert set(spec["expected_files"]) == producer_files == public_files
    assert (spec["max_age_minutes"], spec["schedule"], spec["criticality"]) == (90, "always", "P0")


@pytest.mark.parametrize("missing_count", [0, 1, 11])
def test_crypto_archives_excluded_but_expected_missing_members_counted(tmp_path, monkeypatch, missing_count):
    spec = crypto_stream_spec()
    setup_stream(tmp_path, monkeypatch, **spec)
    present = spec["expected_files"][:11 - missing_count]
    for name in present:
        (tmp_path / name).write_text(json.dumps({"collected_at": NOW.isoformat()}))
    for name in ("crypto_exogenous_history.json", "crypto_regime_history.json"):
        (tmp_path / name).write_text(json.dumps({"collected_at": (NOW - timedelta(days=63)).isoformat()}))
    row = monitor.build_observations()["rows"][0]
    counts = {"members": 11, "measured": 11 - missing_count, "unmeasured": missing_count}
    assert row["group_counts"] == counts
    assert row["would_alarm"] is bool(missing_count)
    result = board.build_board()
    if missing_count == 11:
        assert row["measured"] is False
        assert result["summary"]["p0"]["unmeasured"] == 1
        assert result["_skipped"][0]["group_counts"] == counts
    else:
        assert row["age_eff_min"] == 0
        public = result["streams"][0]
        assert public["group_counts"] == counts
        assert public["status"] == ("stale" if missing_count else "fresh")
        if missing_count:
            assert row["quality_reason"] == public["stale_reason"] == "partial_group"


@pytest.mark.parametrize("expected", [None, [], {}, "crypto_macro.json", [None], [""],
                                      ["crypto_*.json"], ["../outside.json"]])
def test_invalid_expected_members_cannot_fall_back_to_a_fresh_glob(tmp_path, monkeypatch, expected):
    setup_stream(tmp_path, monkeypatch, file="crypto_*.json", expected_files=expected)
    (tmp_path / "crypto_macro.json").write_text(json.dumps({"collected_at": NOW.isoformat()}))
    row = monitor.build_observations()["rows"][0]
    assert row["would_alarm"] is True
    assert row["status"] == "invalid_expected_files"
    result = board.build_board()
    assert result["summary"]["fresh"] == 0
    assert result["summary"]["p0"]["unmeasured"] == 1
    assert result["_skipped"][0]["reason"] == "invalid_expected_files"


def setup_pipeline_clock(tmp_path, monkeypatch, kind, text):
    monkeypatch.setattr(pipeline, "_REPO_ROOT", tmp_path)
    monkeypatch.setattr(pipeline, "_now_kst", lambda: NOW)
    source = {"key": "input", "label": "input", "path": "input.jsonl" if kind.startswith("jsonl") else "input.json",
              "type": kind, "max_fresh_hours": 26}
    path = tmp_path / source["path"]
    path.write_text(text, encoding="utf-8")
    os.utime(path, (NOW.timestamp(), NOW.timestamp()))
    return source


@pytest.mark.parametrize("key", ["ts", "ts_kst", "logged_at", "created_at", "run_id"])
@pytest.mark.parametrize("age,status", [(6, "fresh"), (27, "stale"), (53, "missing")])
def test_pipeline_jsonl_clock_not_checkout_mtime(tmp_path, monkeypatch, key, age, status):
    stamp = (NOW - timedelta(hours=age)).isoformat()
    source = setup_pipeline_clock(tmp_path, monkeypatch, "jsonl_runtime", json.dumps({key: stamp}) + "\n")
    row = pipeline._diagnose_one(source)
    assert row["ts_source"] == "content"
    assert row["last_update_kst"] == stamp
    assert row["age_hours"] == age
    assert row["status"] == status
    assert row["last_entry"][key] == stamp


@pytest.mark.parametrize("kind,key", [("json_content", "generated_at"), ("json_collected_at", "collected_at")])
def test_pipeline_json_clock_not_checkout_mtime(tmp_path, monkeypatch, kind, key):
    source = setup_pipeline_clock(tmp_path, monkeypatch, kind,
                                  json.dumps({key: (NOW - timedelta(hours=53)).isoformat()}))
    row = pipeline._diagnose_one(source)
    assert row["age_hours"] == 53
    assert row["status"] == "missing"
    assert row["ts_source"] == "content"


@pytest.mark.parametrize("kind", ["json_content", "json_collected_at", "jsonl_runtime"])
@pytest.mark.parametrize("text,reason", [("", "empty_content"), ("{", "invalid_json"),
    ("[]", "invalid_object"), ("{}", "missing_timestamp"),
    ('{"collected_at":"bad"}', "invalid_timestamp"),
    ('{"collected_at":true}', "invalid_timestamp")])
def test_pipeline_unmeasured_content_never_falls_back_to_mtime(tmp_path, monkeypatch, kind, text, reason):
    source = setup_pipeline_clock(tmp_path, monkeypatch, kind, text)
    row = pipeline._diagnose_one(source)
    assert row["status"] == "missing"
    assert row["ts_source"] == "none"
    assert row["age_hours"] is None
    assert row["timestamp_issue"] == reason


@pytest.mark.parametrize("stamp,expected,age", [
    ("2026-10-19T02:00:00Z", "2026-10-19T11:00:00+09:00", 1),
    ("2026-10-19T11:00:00", "2026-10-19T11:00:00+09:00", 1),
    ("2026-10-19", "2026-10-19T00:00:00+09:00", 12),
])
def test_pipeline_collected_clock_timezone_and_date_normalization(tmp_path, monkeypatch, stamp, expected, age):
    source = setup_pipeline_clock(tmp_path, monkeypatch, "json_collected_at", json.dumps({"collected_at": stamp}))
    row = pipeline._diagnose_one(source)
    assert row["status"] == "fresh"
    assert row["last_update_kst"] == expected
    assert row["age_hours"] == age


@pytest.mark.parametrize("kind", ["json_content", "json_collected_at", "jsonl_runtime"])
def test_pipeline_future_content_is_not_fresh_even_when_age_rounds_to_zero(tmp_path, monkeypatch, kind):
    source = setup_pipeline_clock(tmp_path, monkeypatch, kind,
        json.dumps({"collected_at": (NOW + timedelta(microseconds=1)).isoformat()}))
    row = pipeline._diagnose_one(source)
    assert row["status"] == "missing"
    assert row["timestamp_issue"] == "future_timestamp"
    assert row["ts_source"] == "none"  # Not an age-based freeze notification.


def test_pipeline_reads_full_last_jsonl_record_and_does_not_skip_broken_tail(tmp_path, monkeypatch):
    entry = {"ts": NOW.isoformat(), "large_field": "x" * 20000}
    source = setup_pipeline_clock(tmp_path, monkeypatch, "jsonl_quarter",
                                  json.dumps(entry) + "\n\n")
    row = pipeline._diagnose_one(source)
    assert row["status"] == "fresh"
    assert row["line_count"] == 2
    assert row["last_entry"] == {"ts": NOW.isoformat()}
    with (tmp_path / source["path"]).open("a") as stream:
        stream.write('{"ts":')
    row = pipeline._diagnose_one(source)
    assert row["status"] == "missing"
    assert row["timestamp_issue"] == "invalid_json"


def test_pipeline_invalid_declared_clock_does_not_use_other_clock(tmp_path, monkeypatch):
    source = setup_pipeline_clock(tmp_path, monkeypatch, "json_content",
        json.dumps({"generated_at": "bad", "collected_at": NOW.isoformat()}))
    assert pipeline._diagnose_one(source)["timestamp_issue"] == "invalid_timestamp"


def test_pipeline_runtime_committed_clock_uses_same_run_id_contract(monkeypatch):
    stamp = (NOW - timedelta(hours=105)).isoformat()
    monkeypatch.setattr(pipeline, "_now_kst", lambda: NOW)
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs:
                        SimpleNamespace(returncode=0, stdout=json.dumps({"run_id": stamp}) + "\n"))
    assert pipeline._committed_content_ts("data/metadata/runtime_load_log.jsonl", is_jsonl=True).isoformat() == stamp
    result = pipeline._persistence_frozen([{"path": "data/metadata/runtime_load_log.jsonl",
        "key": "runtime_load", "type": "jsonl_runtime", "max_fresh_hours": 26, "status": "fresh"}])
    assert result[0]["committed_age_hours"] == 105
    assert result[0]["limit_hours"] == 104  # Existing 4x persistence threshold is unchanged.
