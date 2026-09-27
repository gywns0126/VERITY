"""Local deterministic listing-check evidence tests; no DART/runtime freshness proof."""
import json
from datetime import datetime, timedelta, timezone

import pytest

from api.collectors import dart_catalyst as collector
from api.builders import public_disclosure_feed_builder as builder


START = datetime(2026, 9, 26, 10, 0, tzinfo=timezone(timedelta(hours=9)))
EMPTY = {"status": "013", "list": []}


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(collector, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(collector, "OUTPUT_PATH", str(tmp_path / "alerts.jsonl"))
    monkeypatch.setattr(builder, "INPUT_PATH", collector.OUTPUT_PATH)
    monkeypatch.setattr(builder, "OUTPUT_PATH", str(tmp_path / "feed.json"))
    monkeypatch.setattr(builder, "HEARTBEAT_PATH", str(tmp_path / "metadata" / "dart_catalyst_heartbeat.json"))
    ticks = iter(START + timedelta(seconds=i) for i in range(1000))
    monkeypatch.setattr(collector, "now_kst", lambda: next(ticks))
    monkeypatch.setattr(builder, "_now_kst", lambda: START + timedelta(days=1))

    def no_network(*args, **kwargs):
        raise AssertionError("A fake DART response is required")

    monkeypatch.setattr(collector, "_call", no_network)


def heartbeat():
    with open(builder.HEARTBEAT_PATH, encoding="utf-8") as f:
        return json.load(f)


def row(receipt="20260923000001", **updates):
    return {"stock_code": "005930", "corp_name": "Example", "rcept_no": receipt,
            "rcept_dt": "20260923", "report_nm": "주요사항보고서", "flr_nm": "Example", **updates}


def page(rows=None, total=1):
    return {"status": "000", "list": [row()] if rows is None else rows, "total_page": total}


def run(monkeypatch, response=EMPTY, **kwargs):
    calls = []

    def fake(endpoint, params):
        calls.append((endpoint, dict(params)))
        return response(params) if callable(response) else response

    monkeypatch.setattr(collector, "_call", fake)
    return collector.fetch_catalysts_market_wide(**kwargs), calls


def test_eight_empty_groups_are_checked_not_new_filings(monkeypatch):
    result, calls = run(monkeypatch)
    check = result["source_collection"]
    assert len(calls) == 8
    assert {(p["corp_cls"], p["pblntf_ty"]) for _, p in calls} == {
        (c, t) for c in ("Y", "K") for t in ("B", "C", "D", "I")}
    assert all(e == "list.json" and p["page_count"] == "100" for e, p in calls)
    assert result["events"] == [] and result["stats"]["total"] == 0
    assert check["status"] == "success"
    assert check["groups_expected"] == check["groups_completed"] == 8
    assert check["pages_attempted"] == check["pages_succeeded"] == 8
    assert check["attempted_at"] < check["successful_checked_at"] == check["completed_at"]
    assert check["window"] == {"bgn": "2026-09-19", "end": "2026-09-26"}
    assert check["raw_body_checked"] is check["whole_market_coverage"] is False
    assert collector.persist_catalyst_alerts(result["events"]) == 0
    assert heartbeat()["source_collection"] == check
    feed = builder.build_feed()
    assert feed["_meta"]["source_collection"] == check
    assert feed["_meta"]["generated_at"] != check["successful_checked_at"]


@pytest.mark.parametrize("response,failure", [
    ({"status": "020", "list": []}, "api_020"),
    ({"status": "timeout", "message": "secret-url", "list": []}, "api_timeout"),
    ({"list": []}, "invalid_response"),
    (None, "invalid_response"),
    ({"status": "secret-url", "list": []}, "invalid_response"),
    ({"status": "000", "list": []}, "invalid_pagination_or_rows"),
    (page(total="bad"), "invalid_pagination_or_rows"),
    (page(total=0), "invalid_pagination_or_rows"),
    (page(total=1.5), "invalid_pagination_or_rows"),
    (page(total=True), "invalid_pagination_or_rows"),
    (page(rows=[None]), "invalid_pagination_or_rows"),
])
def test_failures_are_not_successful_empty(monkeypatch, response, failure):
    result, calls = run(monkeypatch, response)
    check = result["source_collection"]
    assert len(calls) == 8
    assert check["status"] == "failed" and check["groups_completed"] == 0
    assert check["successful_checked_at"] is None
    assert all(g["failure"] == failure for g in check["groups"])
    assert "secret-url" not in json.dumps(check)
    assert builder.build_feed()["_meta"]["source_collection"]["successful_checked_at"] is None


def test_partial_exception_is_sanitized_and_other_groups_continue(monkeypatch):
    def response(p):
        if p["corp_cls"] == "Y" and p["pblntf_ty"] == "B":
            raise RuntimeError("secret-url?key=private")
        return EMPTY

    result, calls = run(monkeypatch, response)
    check = result["source_collection"]
    assert len(calls) == 8 and check["groups_completed"] == 7
    assert check["status"] == "partial" and check["successful_checked_at"] is None
    assert check["groups"][0]["failure"] == "request_exception"
    assert "private" not in json.dumps(check)


def test_pagination_and_filters_preserve_existing_events(monkeypatch):
    def response(p):
        if p["corp_cls"] == "Y" and p["pblntf_ty"] == "B":
            return page([row("r" + p["page_no"])], total="2")
        if p["pblntf_ty"] == "I":
            return page([row("noise"), row("contract", report_nm="[기재정정]공급계약"),
                         row("missing", stock_code="")])
        return EMPTY

    result, calls = run(monkeypatch, response)
    assert len(calls) == 9 and result["source_collection"]["status"] == "success"
    assert [e["rcept_no"] for e in result["events"]] == ["r1", "r2", "contract"]
    assert result["stats"]["corrections"] == 1
    assert collector.persist_catalyst_alerts(result["events"]) == 3
    assert collector.persist_catalyst_alerts(result["events"]) == 0
    feed = builder.build_feed()
    assert feed["_meta"]["source_collection"]["status"] == "success"
    assert feed["items"][0]["latest"] == "2026-09-23"
    assert len(feed["items"][0]["disclosures"]) == 3
    assert all("severity" not in d for d in feed["items"][0]["disclosures"])


@pytest.mark.parametrize("second", [EMPTY, page(total=3), {"status": "timeout"}])
def test_incomplete_or_changed_pagination_fails(monkeypatch, second):
    result, _ = run(monkeypatch, lambda p: page(total=2) if p["page_no"] == "1" else second)
    check = result["source_collection"]
    assert check["status"] == "partial" and check["groups_completed"] == 0
    assert check["successful_checked_at"] is None


@pytest.mark.parametrize("max_pages", [0, 1])
def test_page_cap_is_explicit_without_extra_requests(monkeypatch, max_pages):
    result, calls = run(monkeypatch, page(total=2), max_pages=max_pages)
    check = result["source_collection"]
    assert len(calls) == 8 * max_pages
    assert check["groups_completed"] == 0 and check["successful_checked_at"] is None
    assert all(g["status"] == "truncated" and g["failure"] == "page_cap" for g in check["groups"])


def test_custom_scope_reports_actual_denominator(monkeypatch):
    result, calls = run(monkeypatch, corp_cls=("K",))
    assert len(calls) == result["source_collection"]["groups_expected"] == 4
    assert builder.build_feed()["_meta"]["source_collection"]["scope"]["corp_cls"] == ["K"]


def test_new_failed_or_interrupted_attempt_cannot_reuse_success(monkeypatch):
    run(monkeypatch)
    result, _ = run(monkeypatch, {"status": "timeout"})
    assert result["source_collection"]["successful_checked_at"] is None

    def interrupted(p):
        assert heartbeat()["source_collection"]["status"] == "running"
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        run(monkeypatch, interrupted)
    check = builder.build_feed()["_meta"]["source_collection"]
    assert check["status"] == "running" and check["successful_checked_at"] is None


@pytest.mark.parametrize("contents", [None, "broken", "[]", '{"last_run_at":"2099-01-01","new_events":0}'])
def test_legacy_missing_and_corrupt_heartbeat_are_unknown(tmp_path, contents):
    if contents is not None:
        path = tmp_path / "metadata" / "dart_catalyst_heartbeat.json"
        path.parent.mkdir()
        path.write_text(contents)
    check = builder.build_feed()["_meta"]["source_collection"]
    assert check["status"] == "unknown" and check["successful_checked_at"] is None


@pytest.mark.parametrize("change", [
    {"groups_completed": 7}, {"groups": []}, {"pages_succeeded": 0},
    {"attempted_at": "2099-01-01T00:00:00+09:00"},
    {"completed_at": "2026-09-25T00:00:00+09:00"}, {"successful_checked_at": None},
])
def test_builder_rejects_inconsistent_success(monkeypatch, change):
    result, _ = run(monkeypatch)
    result["source_collection"].update(change)
    collector._update_heartbeat(source_collection=result["source_collection"])
    assert builder.build_feed()["_meta"]["source_collection"]["status"] == "unknown"


def test_legacy_persist_neither_creates_success_nor_drops_collection(monkeypatch):
    assert collector.persist_catalyst_alerts([]) == 0
    assert "source_collection" not in heartbeat()
    result, _ = run(monkeypatch)
    collector.persist_catalyst_alerts([])
    assert heartbeat()["source_collection"] == result["source_collection"]


@pytest.mark.parametrize("status", ["success", "failed", "unknown"])
def test_zero_window_retains_items_and_generation_but_refreshes_proof(monkeypatch, tmp_path, status):
    output = tmp_path / "feed.json"
    previous = {"_meta": {"generated_at": "2026-08-01T10:00:00+09:00", "count": 1,
                           "source_collection": {"status": "old"}},
                "items": [{"ticker": "005930", "disclosures": [{"date": "2026-08-01"}]}]}
    output.write_text(json.dumps(previous))
    if status != "unknown":
        run(monkeypatch, EMPTY if status == "success" else {"status": "timeout"})
    assert builder.main() == 0
    after = json.loads(output.read_text())
    proof = after["_meta"].pop("source_collection")
    previous["_meta"].pop("source_collection")
    assert after == previous  # Includes exact historical items, generated_at, and counts.
    assert proof["status"] == status
    if status == "success":
        assert proof["successful_checked_at"] > after["_meta"]["generated_at"]
    else:
        assert proof["successful_checked_at"] is None


def test_metadata_refresh_write_failure_preserves_snapshot(monkeypatch, tmp_path):
    output = tmp_path / "feed.json"
    before = '{"_meta":{"generated_at":"old"},"items":[]}'
    output.write_text(before)
    prior_paths = set(tmp_path.iterdir())

    def failed_replace(*args):
        raise OSError("fixture failure")

    monkeypatch.setattr(builder.os, "replace", failed_replace)
    assert builder.main() == 1
    assert output.read_text() == before
    assert set(tmp_path.iterdir()) == prior_paths  # No incomplete replacement left behind.


@pytest.mark.parametrize("before", ["bad-json", '{"old":"snapshot"}', '{"_meta":[],"items":[]}'])
def test_invalid_old_snapshot_is_never_overwritten(tmp_path, before):
    output = tmp_path / "feed.json"
    output.write_text(before)
    assert builder.main() == 1
    assert output.read_text() == before


def test_heartbeat_write_failure_does_not_claim_persisted_success(monkeypatch):
    def failed_replace(*args):
        raise OSError("local write failure")

    monkeypatch.setattr(collector.os, "replace", failed_replace)
    result, _ = run(monkeypatch)
    assert result["source_collection"]["status"] == "success"  # HTTP fixture only
    assert builder.build_feed()["_meta"]["source_collection"]["status"] == "unknown"
