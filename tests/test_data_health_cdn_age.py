import json
from datetime import datetime, timedelta

import pytest

from api.builders import data_health_builder


@pytest.fixture
def healthy_sections(monkeypatch):
    ts = datetime.now(data_health_builder.KST).isoformat()
    sections = {
        "publish_verify": {"generated_at": ts, "ok": True, "failed": 0,
                           "checked": 4, "max_cdn_age_s": 999999,
                           "files": [{"file": name, "ok": True}
                                     for name in data_health_builder._EXPECTED_VERIFY_FILES]},
        "coverage": {"generated_at": ts, "last_run_at": ts, "kr_total": 2550,
                     "us_total": 5271, "core_fill_pct": {"fields.facts.PER": 50},
                     "last_run_blocked": False, "last_run_warns": 0},
        "freshness": {"generated_at": ts, "stream_count": 1, "skipped_count": 0,
                      "stale_p0": [], "stale_other": []},
    }
    monkeypatch.setattr(data_health_builder, "_guard_section", lambda now: {"held_24h": 0, "recent": []})
    monkeypatch.setattr(data_health_builder, "_verify_section", lambda: sections["publish_verify"])
    monkeypatch.setattr(data_health_builder, "_coverage_section", lambda: sections["coverage"])
    monkeypatch.setattr(data_health_builder, "_freshness_section", lambda: sections["freshness"])
    return sections


def test_cdn_cache_age_does_not_change_health_status(healthy_sections):
    doc = data_health_builder.build()

    assert doc["status"] == "green"
    assert doc["reasons"] == []


@pytest.mark.parametrize("name", ["publish_verify", "coverage", "freshness"])
def test_missing_monitor_evidence_is_not_green(healthy_sections, name):
    healthy_sections[name] = None
    doc = data_health_builder.build()
    assert doc["status"] == "amber"
    assert doc["evidence"][name]["status"] == "missing"


@pytest.mark.parametrize("name,hours", [("publish_verify", 4), ("freshness", 4), ("coverage", 97)])
def test_rebuilt_aggregate_does_not_refresh_old_evidence(healthy_sections, name, hours):
    stamp = (datetime.now(data_health_builder.KST) - timedelta(hours=hours)).isoformat()
    healthy_sections[name]["generated_at"] = stamp
    doc = data_health_builder.build()
    assert doc["status"] == "amber"
    assert doc["evidence"][name]["generated_at"] == stamp
    assert doc["evidence"][name]["status"] == "stale"


@pytest.mark.parametrize("stamp", [None, "not-a-date", "2026-10-18T00:00:00"])
def test_invalid_evidence_clock_is_not_green(healthy_sections, stamp):
    healthy_sections["publish_verify"]["generated_at"] = stamp
    assert data_health_builder.build()["status"] == "amber"


def test_future_clock_is_not_fresh(healthy_sections):
    healthy_sections["freshness"]["generated_at"] = (
        datetime.now(data_health_builder.KST) + timedelta(hours=1)).isoformat()
    assert data_health_builder.build()["evidence"]["freshness"]["status"] == "future"


def test_daily_coverage_allows_weekend_gap(healthy_sections):
    stamp = (datetime.now(data_health_builder.KST) - timedelta(hours=72)).isoformat()
    healthy_sections["coverage"].update(generated_at=stamp, last_run_at=stamp)
    assert data_health_builder.build()["status"] == "green"


@pytest.mark.parametrize("name,field,value", [
    ("publish_verify", "files", []),
    ("publish_verify", "checked", 2),
    ("coverage", "kr_total", 0),
    ("coverage", "last_run_at", None),
    ("freshness", "stream_count", 0),
    ("freshness", "skipped_count", 1),
])
def test_unmeasured_inputs_cannot_pass(healthy_sections, name, field, value):
    healthy_sections[name][field] = value
    assert data_health_builder.build()["status"] == "amber"


def test_old_failure_stays_red(healthy_sections):
    healthy_sections["publish_verify"].update(ok=False, failed=1, generated_at=None)
    assert data_health_builder.build()["status"] == "red"


def test_inconsistent_summary_cannot_hide_failed_file(healthy_sections):
    healthy_sections["publish_verify"]["files"][0]["ok"] = False
    assert data_health_builder.build()["status"] == "red"


def test_partial_successful_checks_cannot_claim_all_passed(healthy_sections):
    verify = healthy_sections["publish_verify"]
    verify.update(checked=1, files=verify["files"][:1])
    assert data_health_builder.build()["status"] == "amber"


@pytest.mark.parametrize("payload", ["not JSON", "[]", '{"results": [1]}'])
def test_malformed_verify_file_becomes_missing(tmp_path, monkeypatch, payload):
    monkeypatch.setattr(data_health_builder, "_META", str(tmp_path))
    (tmp_path / "publish_verify.json").write_text(payload)
    assert data_health_builder._verify_section() is None


def test_actual_files_with_no_results_do_not_turn_green(tmp_path, monkeypatch):
    monkeypatch.setattr(data_health_builder, "_META", str(tmp_path))
    monkeypatch.setattr(data_health_builder, "_DATA", str(tmp_path))
    ts = datetime.now(data_health_builder.KST).isoformat()
    (tmp_path / "publish_verify.json").write_text(json.dumps({"generated_at": ts, "ok": True, "checked": 0}))
    doc = data_health_builder.build()
    assert doc["status"] == "amber"
    assert doc["coverage"] is None


def test_stream_without_measured_status_is_not_valid_evidence(tmp_path, monkeypatch):
    monkeypatch.setattr(data_health_builder, "_DATA", str(tmp_path))
    (tmp_path / "freshness_board.json").write_text(json.dumps({
        "_meta": {"generated_at": datetime.now(data_health_builder.KST).isoformat()},
        "streams": [{"id": "stock_report_public"}], "_skipped_count": 0,
    }))
    assert data_health_builder._freshness_section() is None
