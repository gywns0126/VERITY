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
        "annual_backfill": {"generated_at": ts, "counts_valid": True, "error": 0,
                            "requested": 0, "attempted": 0,
                            "unresolved_error_cells": 0, "unclassified_cells": 0},
    }
    monkeypatch.setattr(data_health_builder, "_guard_section", lambda now: {"held_24h": 0, "recent": []})
    monkeypatch.setattr(data_health_builder, "_verify_section", lambda: sections["publish_verify"])
    monkeypatch.setattr(data_health_builder, "_coverage_section", lambda: sections["coverage"])
    monkeypatch.setattr(data_health_builder, "_freshness_section", lambda: sections["freshness"])
    monkeypatch.setattr(data_health_builder, "_annual_backfill_section", lambda: sections["annual_backfill"])
    return sections


def test_cdn_cache_age_does_not_change_health_status(healthy_sections):
    doc = data_health_builder.build()

    assert doc["status"] == "green"
    assert doc["reasons"] == []


@pytest.mark.parametrize("name", ["publish_verify", "coverage", "freshness", "annual_backfill"])
def test_missing_monitor_evidence_is_not_green(healthy_sections, name):
    healthy_sections[name] = None
    doc = data_health_builder.build()
    assert doc["status"] == "amber"
    assert doc["evidence"][name]["status"] == "missing"


@pytest.mark.parametrize("name,hours", [("publish_verify", 4), ("freshness", 4), ("coverage", 97), ("annual_backfill", 49)])
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


_annual_reader = data_health_builder._annual_backfill_section


def _annual_ledger(tmp_path, monkeypatch, run_overrides=None, cells=None):
    monkeypatch.setattr(data_health_builder, "_DATA", str(tmp_path))
    run = {"attempted_at": datetime.now(data_health_builder.KST).isoformat(),
           "requested": 2, "attempted": 2, "success": 1, "empty": 1,
           "error": 0, "deferred": 0, "touched": 1, "requests": 3}
    run.update(run_overrides or {})
    (tmp_path / "dart_kr_fin_history_missing.json").write_text(json.dumps({
        "_meta": {"last_run": run}, "cells": cells or {}}))
    return run


def test_actual_annual_failure_reaches_health_without_relabeling_financial_date(tmp_path, monkeypatch, healthy_sections):
    run = _annual_ledger(tmp_path, monkeypatch, {"success": 0, "error": 1},
                         {"005930|2023": {"status": "error"}})
    healthy_sections["annual_backfill"] = _annual_reader()
    doc = data_health_builder.build()
    assert doc["status"] == "amber"
    assert "연간 재무 수집 실패 1/2칸" in doc["reasons"]
    assert doc["annual_backfill"]["clock_kind"] == "collection_attempt"
    assert doc["annual_backfill"]["attempted_at"] == run["attempted_at"]


def test_old_error_outside_latest_batch_remains_visible(tmp_path, monkeypatch, healthy_sections):
    _annual_ledger(tmp_path, monkeypatch, cells={"005930|2020": {"status": "error"}})
    healthy_sections["annual_backfill"] = _annual_reader()
    doc = data_health_builder.build()
    assert "연간 재무 미해결 수집 오류 1칸" in doc["reasons"]
    assert doc["status"] == "amber"


@pytest.mark.parametrize("overrides", [
    {"requested": 0}, {"attempted": 0}, {"success": True}, {"error": -1},
    {"touched": 3}, {"touched": 0}, {"requests": None}, {"requests": 0},
    {"requests": 5}, {"attempted_at": None},
    {"attempted_at": "2026-10-18T00:00:00"},
])
def test_invalid_annual_counters_or_clock_cannot_be_green(tmp_path, monkeypatch, healthy_sections, overrides):
    _annual_ledger(tmp_path, monkeypatch, overrides)
    healthy_sections["annual_backfill"] = _annual_reader()
    assert data_health_builder.build()["status"] == "amber"


def test_normal_no_data_and_quota_defer_are_distinct_from_failures(tmp_path, monkeypatch, healthy_sections):
    _annual_ledger(tmp_path, monkeypatch, {"requested": 3, "deferred": 1},
                   {"005930|2010": {"status": "013", "no_data_attempts": 2}})
    healthy_sections["annual_backfill"] = _annual_reader()
    assert data_health_builder.build()["status"] == "green"


@pytest.mark.parametrize("cells", [{"x": None}, {"x": {"status": "000"}}])
def test_unknown_legacy_cell_outcomes_remain_unmeasured(tmp_path, monkeypatch, healthy_sections, cells):
    _annual_ledger(tmp_path, monkeypatch, cells=cells)
    healthy_sections["annual_backfill"] = _annual_reader()
    assert data_health_builder.build()["status"] == "amber"


def test_zero_quota_pending_work_cannot_look_successful(tmp_path, monkeypatch, healthy_sections):
    _annual_ledger(tmp_path, monkeypatch, {"attempted": 0, "success": 0, "empty": 0,
                   "deferred": 2, "touched": 0, "requests": 0})
    healthy_sections["annual_backfill"] = _annual_reader()
    assert "연간 재무 수집 대상이 있으나 실행된 셀 없음" in data_health_builder.build()["reasons"]


def test_confirmed_source_blank_remains_amber_not_official_013(tmp_path, monkeypatch, healthy_sections):
    _annual_ledger(tmp_path, monkeypatch, {"success": 0, "empty": 1, "source_gap": 1, "requests": 4},
                   {"082660|2025": {"status": "source_blank", "reason": "source_period_blank"}})
    healthy_sections["annual_backfill"] = _annual_reader()
    doc = data_health_builder.build()
    assert doc["status"] == "amber"
    assert doc["annual_backfill"]["counts_valid"] is True
    assert doc["annual_backfill"]["unclassified_cells"] == 0
    assert doc["annual_backfill"]["unresolved_error_cells"] == 0
    assert "연간 재무 원천 기간 공란 1칸" in doc["reasons"]


@pytest.mark.parametrize("value", [-1, True, "1", 2])
def test_invalid_source_gap_counter_cannot_be_green(tmp_path, monkeypatch, healthy_sections, value):
    _annual_ledger(tmp_path, monkeypatch, {"source_gap": value})
    healthy_sections["annual_backfill"] = _annual_reader()
    assert data_health_builder.build()["status"] == "amber"
