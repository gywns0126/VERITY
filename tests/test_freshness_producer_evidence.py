import json
import subprocess
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from scripts import freshness_producer_evidence as evidence
from scripts import freshness_shadow_monitor as shadow
from api.builders import data_health_builder as health, freshness_board_builder as board

KST = timezone(timedelta(hours=9))
NOW = datetime(2026, 10, 18, 17, tzinfo=KST)


@pytest.fixture(autouse=True)
def clean_cache(monkeypatch):
    evidence.producer_evidence.cache_clear()
    monkeypatch.setattr(evidence, "_PROCESS_DEADLINE", None)
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_REPOSITORY", "fixture/repo")
    yield
    evidence.producer_evidence.cache_clear()


def replies(monkeypatch, *, sid="news_flash", conclusion="success", step="success", log=""):
    calls = []
    responses = [json.dumps({"workflow_runs": [{
        "id": 42, "status": "completed", "conclusion": conclusion,
    }]}), json.dumps({"jobs": [{"steps": [{
        "name": evidence.PRODUCERS[sid][1], "conclusion": step,
        "completed_at": "2026-10-16T23:31:59Z",
    }]}]}), log]
    def gh(*args, deadline):
        calls.append(args)
        return responses.pop(0)
    monkeypatch.setattr(evidence, "_gh", gh)
    return calls


def test_named_rss_exit_has_no_asset_or_source_freshness_claim(monkeypatch):
    calls = replies(monkeypatch)
    proof = evidence.producer_evidence("news_flash")
    assert proof["status"] == "pipeline_completed"
    assert proof["completed_at"] == "2026-10-16T23:31:59Z"
    assert proof["clock_kind"] == "producer_step_completion"
    assert proof["asset_binding"] == "unverified"
    assert proof["source_freshness_verified"] is False
    assert proof["scope"] == "named_rss_step_exit_zero"
    assert len(calls) == 2
    assert evidence.producer_evidence("news_flash") == proof
    assert len(calls) == 2  # one process reuses the same independently read proof


@pytest.mark.parametrize("conclusion,step", [("failure", "success"), ("success", "failure")])
def test_failed_run_or_collector_never_gets_an_older_success(monkeypatch, conclusion, step):
    calls = replies(monkeypatch, conclusion=conclusion, step=step)
    proof = evidence.producer_evidence("news_flash")
    assert proof["status"] == "unconfirmed"
    assert "completed_at" not in proof
    assert "status=success" not in calls[0][1]


@pytest.mark.parametrize("result,success", [
    ({"todo": 0, "ok": 0}, True),
    ({"todo": 2, "ok": 1, "progressed": 2}, True),
    ({"todo": 2, "ok": 1}, False),
    ({"error": "Timeout"}, False), ({"todo": 2, "ok": 0}, False),
])
def test_dividend_axis_must_independently_complete_even_when_job_is_green(monkeypatch, result, success):
    log = "fixture [facts_backfill] 120초 · " + json.dumps({"dividends": result, "overview": {"ok": 1}})
    calls = replies(monkeypatch, sid="dividends_kr", log=log)
    proof = evidence.producer_evidence("dividends_kr")
    assert (proof["status"] == "pipeline_completed") is success
    assert proof["scope"] == "selected_dividend_chunk_or_resume_noop"
    assert proof["all_records_revalidated"] is False
    assert proof["source_freshness_verified"] is False
    assert "event=schedule" in calls[0][1]


def test_missing_proof_and_static_logo_do_not_invent_clocks(monkeypatch):
    def unavailable(*args, deadline):
        raise OSError("offline")
    monkeypatch.setattr(evidence, "_gh", unavailable)
    assert evidence.producer_evidence("news_flash") == {"status": "unavailable"}
    assert evidence.producer_evidence("logo_map") is None


def setup_snapshot(tmp_path, monkeypatch, exists=True):
    manifest = tmp_path / "freshness_sla.json"
    manifest.write_text(json.dumps({"streams": [{
        "id": "news_flash", "file": "news_flash.json", "criticality": "P0",
        "schedule": "market_hours", "max_age_minutes": 90,
    }]}))
    if exists:
        (tmp_path / "news_flash.json").write_text('[{"published_at":"2026-01-01T00:00:00Z"}]')
    for module in (board, shadow):
        monkeypatch.setattr(module, "MANIFEST", str(manifest))
        monkeypatch.setattr(module, "DATA_DIR", str(tmp_path))
        monkeypatch.setattr(module, "now_kst", lambda: NOW)


def test_weekend_completed_pipeline_never_replaces_missing_source_clock(tmp_path, monkeypatch):
    setup_snapshot(tmp_path, monkeypatch)
    replies(monkeypatch)
    public = board.build_board()
    assert public["_skipped_count"] == 1
    assert public["streams"] == []
    assert public["_skipped"] == [{"id": "news_flash", "reason": "no_ts"}]
    proof = public["_producer_evidence"]["news_flash"]
    assert proof["completed_at"] == "2026-10-16T23:31:59Z"
    measured = shadow.build_observations()["rows"][0]
    assert measured["status"] == "no_ts"
    assert "last_ts" not in measured
    assert all(measured["producer_evidence"][key] == value for key, value in proof.items())
    assert measured["producer_evidence"]["run_id"] == 42
    assert "workflow" not in proof and "run_id" not in proof and "scope" not in proof


def test_weekend_missing_artifact_not_hidden_by_successful_producer(tmp_path, monkeypatch):
    setup_snapshot(tmp_path, monkeypatch, exists=False)
    calls = replies(monkeypatch)
    assert board.build_board()["_skipped"] == [{"id": "news_flash", "reason": "missing"}]
    assert shadow.build_observations()["rows"] == [{"id": "news_flash", "status": "missing"}]
    assert calls == []


def test_weekend_absent_success_evidence_stays_unmeasured(tmp_path, monkeypatch):
    setup_snapshot(tmp_path, monkeypatch)
    replies(monkeypatch, conclusion="failure")
    assert board.build_board()["_skipped_count"] == 1
    row = shadow.build_observations()["rows"][0]
    assert row["status"] == "no_ts"
    assert row["producer_evidence"]["status"] == "unconfirmed"


def test_latest_pending_is_explicit_and_does_not_use_old_success(monkeypatch):
    calls = []
    def gh(*args, deadline):
        calls.append(args)
        return json.dumps({"workflow_runs": [{"id": 43, "status": "in_progress",
                                             "conclusion": None}]})
    monkeypatch.setattr(evidence, "_gh", gh)
    proof = evidence.producer_evidence("news_flash")
    assert proof["status"] == "pending"
    assert "completed_at" not in proof
    assert len(calls) == 1


def test_one_deadline_is_propagated_to_all_five_producer_calls(monkeypatch):
    clock = SimpleNamespace(now=100.0)
    monkeypatch.setattr(evidence.time, "monotonic", lambda: clock.now)
    deadlines = []
    def gh(*args, deadline):
        deadlines.append(deadline)
        clock.now += 3
        if args[0] == "run":
            return '[facts_backfill] 10초 · {"dividends":{"todo":0,"ok":0}}'
        if "/jobs?" in args[1]:
            return json.dumps({"jobs": [{"steps": [
                {"name": "Run RSSScout", "conclusion": "success", "completed_at": "2026-10-16T23:31:59Z"}
            ]}]}) if len(deadlines) == 2 else json.dumps({"jobs": [{"steps": [
                {"name": "Backfill company facts", "conclusion": "success", "completed_at": "2026-10-17T23:32:17Z"}
            ]}]})
        return '{"workflow_runs":[{"id":42,"status":"completed","conclusion":"success"}]}'
    monkeypatch.setattr(evidence, "_gh", gh)
    assert evidence.producer_evidence("news_flash")["status"] == "pipeline_completed"
    assert evidence.producer_evidence("dividends_kr")["status"] == "pipeline_completed"
    assert deadlines == [120.0] * 5


def test_individual_timeout_uses_remaining_shared_budget(monkeypatch):
    clock = SimpleNamespace(now=100.0)
    monkeypatch.setattr(evidence.time, "monotonic", lambda: clock.now)
    timeouts = []
    def run(*args, **kwargs):
        timeouts.append(kwargs["timeout"])
        clock.now += 7
        return SimpleNamespace(stdout="fixture")
    monkeypatch.setattr(evidence.subprocess, "run", run)
    assert evidence._gh("api", "fixture", deadline=120) == "fixture"
    assert evidence._gh("api", "fixture", deadline=120) == "fixture"
    with pytest.raises(evidence._BudgetExhausted):
        evidence._gh("api", "fixture", deadline=120)
    assert timeouts == [20, 13, 6]
    with pytest.raises(evidence._BudgetExhausted):
        evidence._gh("api", "fixture", deadline=120)
    assert len(timeouts) == 3


def test_timeout_exhausts_process_budget_and_second_producer_never_starts(monkeypatch):
    clock = SimpleNamespace(now=100.0)
    monkeypatch.setattr(evidence.time, "monotonic", lambda: clock.now)
    calls = []
    def run(args, **kwargs):
        calls.append(kwargs["timeout"])
        clock.now += kwargs["timeout"]
        raise subprocess.TimeoutExpired(args, kwargs["timeout"])
    monkeypatch.setattr(evidence.subprocess, "run", run)
    assert evidence.producer_evidence("news_flash")["status"] == "unavailable"
    assert evidence.producer_evidence("dividends_kr") == {
        "status": "unavailable", "reason": "budget_exhausted"}
    assert calls == [20.0]


def test_budget_timeout_does_not_stop_later_health_aggregation(tmp_path, monkeypatch):
    setup_snapshot(tmp_path, monkeypatch)
    clock = SimpleNamespace(now=100.0)
    monkeypatch.setattr(evidence.time, "monotonic", lambda: clock.now)
    def run(args, **kwargs):
        clock.now += kwargs["timeout"]
        raise subprocess.TimeoutExpired(args, kwargs["timeout"])
    monkeypatch.setattr(evidence.subprocess, "run", run)
    snapshot = board.build_board()
    monkeypatch.setattr(health, "_DATA", str(tmp_path))
    monkeypatch.setattr(health, "_META", str(tmp_path))
    monkeypatch.setattr(health, "_load_json", lambda path:
                        snapshot if path.endswith("freshness_board.json") else None)
    result = health.build()
    assert result["status"] == "amber"
    assert result["freshness"]["skipped_count"] == 1
    assert result["freshness"]["producer_evidence"]["news_flash"]["status"] == "unavailable"
    assert "신선도 감시 대상 누락·미측정" in result["reasons"]
