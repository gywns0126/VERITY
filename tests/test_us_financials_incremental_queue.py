"""Incremental priority, durable retry and integrity/publish boundaries; no network."""
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest
import yaml

from api.builders import us_financials_incremental as inc


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            value = cls(2026, 10, 2, 18, tzinfo=timezone.utc)
            return value.astimezone(tz) if tz else value.replace(tzinfo=None)

    monkeypatch.setattr(inc, "datetime", Clock)
    for name in ("STATE_PATH", "EARN_PATTERN_PATH", "EVENT_PATH", "QUARTERLY_PATH"):
        monkeypatch.setattr(inc, name, str(tmp_path / (name + ".json")))
    monkeypatch.setattr(inc, "FIN_DIR", str(tmp_path))
    monkeypatch.setattr(inc, "_universe_cik_map", lambda: {1: ["A"], 2: ["Z", "ZZ"]})
    monkeypatch.setattr(inc.time, "sleep", lambda _: None)
    monkeypatch.setattr(inc.requests, "get", lambda *a, **kw: pytest.fail("network forbidden"))
    monkeypatch.setattr(inc, "_fetch_day_filers", lambda d: [])
    monkeypatch.setattr(inc.sys, "argv", ["incremental", "--cap", "60"])
    inc._save_state({"last_processed": "2026-09-30"})
    return tmp_path


def dump(path, doc):
    Path(path).write_text(json.dumps(doc), encoding="utf-8")


def snapshot():
    return {"ticker": "Z", "meta": {"currency": "USD"}, "series_annual": {},
            "series_quarterly": {"revenue": [
                {"start": "2026-07-01", "end": "2026-09-30", "filed": "2026-10-01",
                 "fy": 2026, "fp": "Q3", "form": "10-Q", "is_annual": False,
                 "val": 100, "unit": "USD", "accn": "0000000002-26-000001"}]}}


def test_earnings_priority_fanout_and_completed_dedup(isolated, monkeypatch):
    dump(inc.EVENT_PATH, {"items": [{"ticker": "Z", "disclosures": [
        {"date": "2026-10-01", "item_codes": ["2.02"]},
        {"date": "2026-10-02", "item_codes": ["8.01"]},
        {"date": "2026-10-03", "item_codes": ["2.02"]}]}]})
    monkeypatch.setattr(inc, "_fetch_day_filers", lambda d: [(1, "10-Q", "a")])
    calls = []
    monkeypatch.setattr(inc, "_refresh", lambda t, c: (calls.append(t) or [], False))
    monkeypatch.setattr(inc.sys, "argv", ["incremental", "--cap", "1"])
    assert inc.main() == 0
    assert calls == ["Z"]  # announcement outranks alphabetical A
    assert {r["ticker"] for r in inc._load_state()["pending"]} == {"ZZ", "A"}
    assert inc.main() == 0
    assert calls == ["Z", "ZZ"]  # completed Z cannot be reintroduced
    assert inc.main() == 0
    assert calls == ["Z", "ZZ", "A"]
    assert inc._load_state()["pending"] == []


def test_overflow_failures_and_missing_survive_window_and_retry_fairly(isolated, monkeypatch):
    candidates = [{"ticker": f"T{i:02}", "filed": "2026-08-01", "attempts": 0}
                  for i in range(65)]
    inc._save_state({"last_processed": "2026-09-30", "pending": candidates})
    calls = []
    def refresh(t, c):
        calls.append(t)
        if t == "T00":
            raise subprocess.TimeoutExpired("collector", 300)
        return [], t == "T01"
    monkeypatch.setattr(inc, "_refresh", refresh)
    assert inc.main() == 1
    st = inc._load_state()
    assert len(calls) == 60
    assert len(st["pending"]) == 7
    assert st["missing_latest"] == ["T01"]
    assert st["last_run_failed"] == ["T00"]
    assert inc.main() == 1
    assert calls[60:65] == ["T60", "T61", "T62", "T63", "T64"]
    assert {r["ticker"] for r in inc._load_state()["pending"]} == {"T00", "T01"}


def test_index_failure_does_not_block_existing_queue_or_advance_cursor(isolated, monkeypatch):
    inc._save_state({"last_processed": "2026-09-30", "pending": [{"ticker": "Z"}]})
    monkeypatch.setattr(inc, "_fetch_day_filers", lambda d: None)
    monkeypatch.setattr(inc, "_refresh", lambda *a: ([], False))
    assert inc.main() == 0
    assert inc._load_state()["last_processed"] == "2026-09-30"
    assert inc._load_state()["pending"] == []


def test_downstream_failure_requeues_success_and_restores_announcement(isolated, monkeypatch):
    row = {"ticker": "Z", "earnings_date": "2026-10-01", "attempts": 1}
    inc._save_state({"pending": [{"ticker": "A"}], "last_run_candidates": [row],
                     "last_run_tickers": ["Z"], "completed_earnings": {"Z": "2026-10-01"}})
    monkeypatch.setattr(inc.sys, "argv", ["incremental", "--requeue-run"])
    monkeypatch.setattr(inc, "_universe_cik_map", lambda: pytest.fail("must not collect"))
    assert inc.main() == 0
    assert inc.main() == 0  # idempotent
    st = inc._load_state()
    assert {r["ticker"] for r in st["pending"]} == {"A", "Z"}
    assert st["completed_earnings"] == {}
    assert st["last_run_tickers"] == []


@pytest.mark.parametrize("cap", ["0", "-1", "61"])
def test_hard_cap(isolated, monkeypatch, cap):
    monkeypatch.setattr(inc.sys, "argv", ["incremental", "--cap", cap])
    with pytest.raises(SystemExit):
        inc.main()


@pytest.mark.parametrize("change,expected", [
    ({"unit": "USD/shares"}, "unit_currency"),
    ({"currency": "EUR"}, "unit_currency"),
    ({"end": "2026-12-31"}, "period"),
    ({"start": "2026-01-01"}, "duration"),
    ({"start": "2026-09-30"}, "duration"),
    ({"is_annual": True}, "period"),
    ({"accn": ""}, "accession_missing"),
    ({"val": float("nan")}, "nonfinite"),
])
def test_critical_row_checks(isolated, change, expected):
    doc = snapshot()
    assert inc._snapshot_errors(doc, "Z") == []
    doc["series_quarterly"]["revenue"][0].update(change)
    assert any(expected in e for e in inc._snapshot_errors(doc, "Z"))


def test_native_currency_and_missing_metric_are_not_fatal(isolated):
    doc = snapshot()
    doc["meta"]["currency"] = "CAD"
    doc["series_quarterly"]["revenue"][0]["unit"] = "CAD"
    doc["series_quarterly"]["net_income"] = []
    assert inc._snapshot_errors(doc, "Z") == []


def test_summary_saved_does_not_count_as_ticker_success(isolated, monkeypatch):
    dump(Path(inc.FIN_DIR) / "Z.json", snapshot())  # stale file cannot satisfy success
    monkeypatch.setattr(inc.subprocess, "run", lambda *a, **kw: SimpleNamespace(
        returncode=0, stdout="", stderr="ERROR fetch\nsummary saved"))
    assert inc._refresh("Z", {}) == (["collector_failed"], False)


def test_latest_accession_evidence_and_missing_are_preserved(isolated, monkeypatch):
    doc = snapshot()
    dump(Path(inc.FIN_DIR) / "Z.json", doc)
    monkeypatch.setattr(inc.subprocess, "run", lambda *a, **kw: SimpleNamespace(
        returncode=0, stdout="", stderr="saved Z.json"))
    evidence = {"accession": "0000000002-26-000002", "form": "10-Q", "report_date": "2026-09-30"}
    assert inc._refresh("Z", evidence) == ([], True)
    saved = json.loads((Path(inc.FIN_DIR) / "Z.json").read_text())
    assert saved["meta"]["latest_filing_sync"]["status"] == "source_lag"
    assert saved["meta"]["latest_filing_sync"]["accession"] == evidence["accession"]
    evidence["accession"] = doc["series_quarterly"]["revenue"][0]["accn"]
    assert inc._refresh("Z", evidence) == ([], False)


def test_source_lag_from_existing_submission_contract(isolated):
    dump(inc.QUARTERLY_PATH, {"stocks": {"Z": {"latest_filing_sync": {
        "status": "source_lag", "accession": "acc", "report_date": "2026-06-30", "form": "10-Q"}}}})
    rows = inc._local_candidates({2: ["Z"]}, date(2026, 10, 2), {})
    assert rows["Z"]["accession"] == "acc"


def test_new_filing_drops_previous_report_date():
    pending = {"Z": {"ticker": "Z", "accession": "old", "report_date": "2026-06-30"}}
    inc._merge_candidate(pending, "Z", {"filed": "2026-10-01", "accession": "new"})
    assert "report_date" not in pending["Z"]


def test_corrupt_shape_is_reported_and_other_candidates_continue(isolated, monkeypatch, capsys):
    inc._save_state({"last_processed": "2026-10-01", "pending": [{"ticker": "A"}, {"ticker": "Z"}]})
    def refresh(ticker, candidate):
        if ticker == "A":
            raise TypeError("invalid snapshot shape")
        return [], False
    monkeypatch.setattr(inc, "_refresh", refresh)
    assert inc.main() == 1
    st = inc._load_state()
    assert st["pending"][0]["last_error"] == "TypeError"
    assert st["last_run_tickers"] == ["Z"]
    assert "FAIL A: TypeError" in capsys.readouterr().err


def test_collection_budget_preserves_unattempted(isolated, monkeypatch, capsys):
    inc._save_state({"last_processed": "2026-10-01", "pending": [{"ticker": "A"}, {"ticker": "Z"}]})
    ticks = iter([0, 0, inc.COLLECTION_BUDGET_SEC])
    monkeypatch.setattr(inc.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(inc, "_refresh", lambda *args: ([], False))
    assert inc.main() == 0
    assert inc._load_state()["pending"] == [{"ticker": "Z"}]
    assert "checked=1/2" in capsys.readouterr().err


def test_current_serializer_output_passes_gate(isolated):
    from api.intelligence import us_financials as usf
    raw = {"start": "2026-07-01", "end": "2026-09-30", "filed": "2026-10-01",
           "fy": 2026, "fp": "Q3", "form": "10-Q", "val": 100,
           "accn": "0000000002-26-000001"}
    # Exercise the actual serialization contract, not a hand-built normalized row.
    doc = usf.build_ticker_snapshot("Z", 2, facts={"cik": 2, "facts": {
        "us-gaap": {"Revenues": {"units": {"USD": [raw]}}}}}, sic_pair=(None, None))
    assert doc["series_quarterly"]["revenue"]
    assert inc._snapshot_errors(doc, "Z") == []


@pytest.mark.parametrize("filled,fatal", [(70, False), (10, True)])
def test_existing_coverage_warn_vs_fatal_exit(tmp_path, monkeypatch, filled, fatal):
    from api.builders import coverage_report_builder as cb
    baseline = {"kr_total": 0, "fields": {}, "companions": {}, "us_total": 100,
                "us_fields": {"facts": {"filled": 90, "pct": 90}},
                "us_companions": {}, "us_smallcap_fields": {}}
    current = {**baseline, "us_fields": {"facts": {"filled": filled, "pct": filled}}}
    monkeypatch.setattr(cb, "_META", str(tmp_path))
    monkeypatch.setattr(cb, "REPORT_PATH", str(tmp_path / "coverage.json"))
    monkeypatch.setattr(cb, "HISTORY_PATH", str(tmp_path / "history.jsonl"))
    monkeypatch.setattr(cb, "build", lambda: current)
    dump(cb.REPORT_PATH, baseline)
    if fatal:
        with pytest.raises(SystemExit) as error:
            cb.main()
        assert error.value.code == 1
        assert json.loads(Path(cb.REPORT_PATH).read_text()) == baseline
    else:
        cb.main()
        assert json.loads(Path(cb.REPORT_PATH).read_text()) == current


def test_workflow_failure_blocks_publish_but_persists_only_retry_state():
    root = Path(__file__).resolve().parents[1]
    workflow = yaml.safe_load((root / ".github/workflows/us_financials_incremental.yml").read_text())
    steps = workflow["jobs"]["incremental"]["steps"]
    by_id = {s["id"]: s for s in steps if "id" in s}
    for name in ("incr", "report", "quarterly", "quality"):
        assert not by_id[name].get("continue-on-error")
        assert f"steps.{name}.outcome == 'success'" in by_id["persist"]["env"]["READY"]
    assert "!cancelled()" in by_id["persist"]["if"]
    command = by_id["persist"]["run"]
    failure_branch = command.split('if [ "$READY" != "true" ]; then')[1].split("else")[0]
    assert "--requeue-run" in failure_branch
    assert "git add" not in failure_branch
    assert "git add data/\n" not in command
    publish = next(s for s in steps if s.get("uses") == "./.github/actions/publish-data")
    assert "success()" in publish["if"] and "steps.quality.outcome == 'success'" in publish["if"]
    assert workflow["concurrency"]["group"] == "verity-us-incremental"


@pytest.mark.parametrize("ready", ["true", "false"])
def test_persist_shell_stages_only_allowed_outputs(tmp_path, ready):
    root = Path(__file__).resolve().parents[1]
    workflow = yaml.safe_load((root / ".github/workflows/us_financials_incremental.yml").read_text())
    step = next(s for s in workflow["jobs"]["incremental"]["steps"] if s.get("id") == "persist")
    paths = ["data/us_financials/_summary.json", "data/us_earnings_pattern.json",
             "data/us_stock_report_public.json", "data/us_fin_annual_compact.json",
             "data/us_quarterly_public.json", "data/cross_gics_us.json",
             "data/metadata/coverage_report.json", "data/metadata/coverage_history.jsonl",
             "data/metadata/us_fin_incremental_state.json"]
    for path in paths + ["data/unrelated.json"]:
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.touch()
    # Only run the staging prefix, with both commands replaced by shell recorders.
    # No git executable, commit, push, collector or external service is invoked.
    script = "git() { printf 'git %s\\n' \"$*\"; }; python() { printf 'python %s\\n' \"$*\"; };\n"
    script += step["run"].split("git diff --staged")[0]
    result = subprocess.run(["bash", "-eu", "-c", script], cwd=tmp_path,
                            env={**os.environ, "READY": ready}, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    staged = [line.removeprefix("git add -- ") for line in result.stdout.splitlines()
              if line.startswith("git add -- ")]
    assert staged == (paths if ready == "true" else paths[-1:])
    assert ("--requeue-run" in result.stdout) == (ready == "false")


@pytest.mark.parametrize("cancelled,outcome,expected", [
    (False, "success", True), (False, "failure", True),
    (False, "skipped", False), (False, "", False),
    (True, "success", False), (True, "failure", False),
])
def test_evidence_retained_before_report_for_attempted_collection(cancelled, outcome, expected):
    root = Path(__file__).resolve().parents[1]
    workflow = yaml.safe_load((root / ".github/workflows/us_financials_incremental.yml").read_text())
    steps = workflow["jobs"]["incremental"]["steps"]
    index = next(i for i, step in enumerate(steps) if step.get("id") == "incr")
    evidence = steps[index + 1]
    assert evidence["id"] == "evidence"
    assert steps[index + 2]["id"] == "report"
    assert evidence["uses"] == "actions/upload-artifact@v4"
    assert evidence["if"] == "${{ !cancelled() && steps.incr.outcome != 'skipped' && steps.incr.outcome != '' }}"
    assert ((not cancelled) and outcome not in ("skipped", "")) == expected
    assert evidence["with"] == {
        "name": "us-financials-evidence-${{ github.run_id }}-${{ github.run_attempt }}",
        "retention-days": 7,
        "if-no-files-found": "error",
        "path": "data/us_financials/*.json\ndata/metadata/us_fin_incremental_state.json\n",
    }
    assert not evidence.get("continue-on-error")
