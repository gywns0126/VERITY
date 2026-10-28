"""Offline evidence contracts; no natural-run or screen-delivery claims."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
NOW = "2026-10-28T02:00:00+00:00"
ORIGIN = "2026-10-28T01:00:00+00:00"


def stamp(seconds):
    return (datetime.fromisoformat(ORIGIN) + timedelta(seconds=seconds)).isoformat()


@pytest.fixture(params=[
    "api/observability/member_map_freshness.py",
    "vercel-api/api/portfolio_core/member_map_freshness.py",
], ids=["collector", "api-mirror"])
def freshness(request):
    spec = importlib.util.spec_from_file_location("delivery_evidence_test", ROOT / request.param)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def event(**changes):
    value = {"source_available_at": ORIGIN, "source_precision": "timestamp",
             "first_seen_at": stamp(120), "facts_visible_at": stamp(300),
             "analysis_visible_at": stamp(900)}
    value.update(changes)
    return value


def test_mirror_bytes_match():
    assert (ROOT / "api/observability/member_map_freshness.py").read_bytes() == (
        ROOT / "vercel-api/api/portfolio_core/member_map_freshness.py").read_bytes()


def test_exact_source_and_observation_are_separate(freshness):
    row = event(source_available_at="2026-10-28T10:00:00+09:00")
    original = deepcopy(row)
    measured = freshness.delivery_evidence(row, now=NOW, priority="important")
    assert row == original
    assert measured["end_to_end_measurable"] is True
    assert measured["timestamps"] == {key: value for key, value in event().items() if key != "source_precision"}
    assert measured["source_available"]["facts"] == {"status": "on-time", "delay_seconds": 300}
    assert measured["first_observed"]["facts"] == {"status": "on-time", "delay_seconds": 180}
    assert measured["analysis"] == {"status": "on-time", "delay_seconds": 900}


@pytest.mark.parametrize("source,precision", [("2026-10-28", "date"), (None, "unknown")])
def test_date_or_missing_source_never_becomes_midnight(freshness, source, precision):
    measured = freshness.delivery_evidence(event(source_available_at=source, source_precision=precision), now=NOW)
    assert measured["source_precision"] == precision
    assert measured["timestamps"]["source_available_at"] == source
    assert measured["basis"] == "first-observed-only"
    assert measured["end_to_end_measurable"] is False
    assert measured["source_available"]["facts"] == {"status": "unknown", "delay_seconds": None}
    assert measured["first_observed"]["facts"]["delay_seconds"] == 180


def test_legacy_exact_input_and_date_infer_only_supplied_precision(freshness):
    row = event()
    row.pop("source_precision")
    assert freshness.delivery_evidence(row, now=NOW)["source_precision"] == "timestamp"
    row["source_available_at"] = "2026-10-28"
    assert freshness.delivery_evidence(row, now=NOW)["source_precision"] == "date"


@pytest.mark.parametrize("changes", [
    {"source_available_at": "2026-10-28T03:00:00Z"},
    {"first_seen_at": "2026-10-28T03:00:00Z"},
    {"first_seen_at": stamp(-1)},
    {"source_available_at": "not-a-clock"},
    {"source_available_at": "2026-10-28", "source_precision": "timestamp"},
    {"source_available_at": "2026-10-28T01:00:00", "source_precision": "timestamp"},
    {"first_seen_at": "2026-10-28T01:00:00"},
    {"first_seen_at": ""},
    {"source_precision": "date"},
])
def test_invalid_origins_do_not_fall_back_to_green(freshness, changes):
    measured = freshness.delivery_evidence(event(**changes), now=NOW)
    assert measured["status"] == "invalid-clock"
    assert measured["end_to_end_measurable"] is False
    for axis in ("source_available", "first_observed"):
        for lane in ("facts", "analysis"):
            assert measured[axis][lane] == {"status": "invalid-clock", "delay_seconds": None}


@pytest.mark.parametrize("visible", [stamp(119), stamp(3601), "2026-10-28", "invalid"])
def test_bad_facts_receipt_excluded_without_discarding_valid_analysis(freshness, visible):
    row = event(facts_visible_at=visible)
    # A future facts receipt also makes the earlier analysis receipt inverted.
    if visible == stamp(3601):
        row["analysis_visible_at"] = None
    measured = freshness.delivery_evidence(row, now=NOW)
    assert measured["facts"]["status"] == "invalid-clock"
    assert measured["facts"]["delay_seconds"] is None


def test_analysis_before_facts_is_invalid_but_missing_facts_is_not_fabricated(freshness):
    measured = freshness.delivery_evidence(event(analysis_visible_at=stamp(299)), now=NOW)
    assert measured["facts"]["status"] == "on-time"
    assert measured["analysis"]["status"] == "invalid-clock"
    measured = freshness.delivery_evidence(event(facts_visible_at=None), now=NOW)
    assert measured["facts"] == {"status": "overdue", "delay_seconds": 3600}
    assert measured["analysis"]["status"] == "on-time"
    assert measured["timestamps"]["facts_visible_at"] is None


def test_orphan_receipt_unknown_and_future_receipt_invalid(freshness):
    unknown = freshness.delivery_evidence({"facts_visible_at": stamp(100)}, now=NOW)
    assert unknown["status"] == "unknown" and unknown["facts"]["status"] == "unknown"
    invalid = freshness.delivery_evidence({"facts_visible_at": stamp(3601)}, now=NOW)
    assert invalid["facts"]["status"] == "invalid-clock"


@pytest.mark.parametrize("priority,lane,target", [
    ("important", "facts", 300), ("important", "analysis", 900),
    ("ordinary", "facts", 900), ("ordinary", "analysis", 1800),
    ("complex", "facts", 300), ("complex", "analysis", 3600),
])
def test_exact_target_and_one_second_over_boundary(freshness, priority, lane, target):
    field = lane + "_visible_at"
    for offset, expected in ((target, "on-time"), (target + 1, "late")):
        measured = freshness.delivery_evidence(
            {"source_available_at": ORIGIN, field: stamp(offset)},
            now=stamp(target + 1), priority=priority)
        assert measured[lane] == {"status": expected, "delay_seconds": offset}
    for offset, expected in ((target, "pending"), (target + 1, "overdue")):
        measured = freshness.delivery_evidence({"source_available_at": ORIGIN},
            now=stamp(offset), priority=priority)
        assert measured[lane] == {"status": expected, "delay_seconds": offset}


def test_batch_denominators_p95_completed_only_and_mixed_priorities(freshness):
    rows = [
        event(facts_visible_at=stamp(300)),
        event(facts_visible_at=stamp(1000), analysis_visible_at=stamp(1800)),
        event(facts_visible_at=None, analysis_visible_at=None),
        event(source_available_at=stamp(3400), first_seen_at=stamp(3450),
              facts_visible_at=None, analysis_visible_at=None),
        event(source_available_at="2026-10-28", source_precision="date",
              facts_visible_at=stamp(300)),
        {},
        event(facts_visible_at="bad"),
        event(priority="important", facts_visible_at=stamp(301)),
    ]
    before = deepcopy(rows)
    report = freshness.summarize_delivery_evidence(iter(rows), now=NOW)
    assert rows == before
    assert report["events_total"] == 8
    assert report["source_precision_counts"] == {"timestamp": 6, "date": 1, "unknown": 1}
    facts = report["source_available"]["facts"]
    assert facts == {"eligible": 5, "completed": 3, "unknown": 2, "invalid": 1,
                     "on_time": 1, "late": 2, "pending": 1, "overdue": 1,
                     "p95_seconds": 1000, "overdue_n": 1, "overdue_m": 2}
    observed = report["first_observed"]["facts"]
    assert observed["p95_seconds"] == 880
    assert observed["eligible"] == 6 and observed["unknown"] == 1
    assert observed["on_time"] == 4 and observed["late"] == 0
    for axis in ("source_available", "first_observed"):
        for stats in report[axis].values():
            assert stats["eligible"] + stats["unknown"] + stats["invalid"] == report["events_total"]
            assert stats["completed"] == stats["on_time"] + stats["late"]
            assert stats["overdue_m"] == stats["pending"] + stats["overdue"]
    assert "achieved_sla" not in json.dumps(report)


def test_nearest_rank_p95_uses_completed_count(freshness):
    rows = [{"source_available_at": ORIGIN, "facts_visible_at": stamp(n)} for n in range(1, 21)]
    rows += [{"source_available_at": ORIGIN}, {}, {"source_available_at": "bad"}]
    stats = freshness.summarize_delivery_evidence(rows, now=NOW)["source_available"]["facts"]
    assert stats["p95_seconds"] == 19
    assert stats["completed"] == 20 and stats["overdue_n"] == 1 and stats["overdue_m"] == 1


def test_empty_and_unknown_batches_have_no_achieved_target(freshness):
    for rows, total in (([], 0), ([{}], 1)):
        result = freshness.summarize_delivery_evidence(rows, now=NOW)
        assert result["events_total"] == total
        for axis in ("source_available", "first_observed"):
            for stats in result[axis].values():
                assert stats["p95_seconds"] is None
                assert stats["overdue_n"] == stats["overdue_m"] == 0
                assert stats["unknown"] == total


def test_clock_advance_cannot_create_delivery_samples(freshness):
    rows = [{"source_available_at": ORIGIN, "first_seen_at": stamp(1)}]
    early = freshness.summarize_delivery_evidence(rows, now=stamp(100))
    late = freshness.summarize_delivery_evidence(rows, now=NOW)
    assert early["source_available"]["facts"]["pending"] == 1
    assert late["source_available"]["facts"]["overdue_n"] == 1
    for result in (early, late):
        assert result["source_available"]["facts"]["completed"] == 0
        assert result["source_available"]["facts"]["p95_seconds"] is None


@pytest.mark.parametrize("checkpoint", ["available", "retained", "read-failed", "not-read"])
def test_collection_closed_projection_and_absent_sources(freshness, checkpoint):
    states = {"DART": {"status": "partial", "last_attempt_at": NOW, "last_success_at": stamp(3400),
                       "feed": {"private": "must-not-copy"}, "error": "credential=must-not-copy"},
              "untrusted": {"status": "must-not-copy"}}
    original = deepcopy(states)
    result = freshness.collection_receipt(states, now=NOW, checkpoint_status=checkpoint)
    assert states == original
    assert freshness.validate_collection_receipt(result) is True
    assert set(result) == {"schema", "checked_at", "checkpoint_status", "sources",
                           "screen_delivery_verified", "analysis_delivery_verified"}
    assert set(result["sources"]) == {"DART", "SEC", "news"}
    assert result["sources"]["DART"] == {
        "status": "partial", "last_attempt_at": NOW, "last_success_at": stamp(3400),
        "health": {"status": "delayed", "age_seconds": 200}}
    assert result["sources"]["SEC"] == {
        "status": "unknown", "last_attempt_at": None, "last_success_at": None,
        "health": {"status": "unknown", "age_seconds": None}}
    assert result["screen_delivery_verified"] is result["analysis_delivery_verified"] is False
    assert "must-not-copy" not in json.dumps(result)


def test_warm_diagnostics_preserve_original_success_clock(freshness):
    states = {"DART": {"status": "error", "last_attempt_at": stamp(200), "last_success_at": ORIGIN}}
    early = freshness.collection_receipt(states, now=stamp(120))
    late = freshness.collection_receipt(states, now=NOW, checkpoint_status="retained")
    assert early["sources"]["DART"]["health"] == {"status": "on-time", "age_seconds": 120}
    assert late["sources"]["DART"]["health"] == {"status": "delayed", "age_seconds": 3600}
    assert late["sources"]["DART"]["status"] == "error"
    assert late["sources"]["DART"]["last_success_at"] == ORIGIN
    assert freshness.validate_collection_receipt(late)


@pytest.mark.parametrize("changes", [
    {"status": ["success"], "last_success_at": "bad"},
    {"status": "private-key-in-status", "last_attempt_at": "private-key-in-time"},
    {"last_success_at": stamp(3601)},
    {"last_success_at": "2026-10-28"},
    {"last_success_at": "2026-10-28T01:00:00"},
    {"last_attempt_at": stamp(100), "last_success_at": stamp(101)},
])
def test_collection_sanitizes_invalid_statuses_and_clocks(freshness, changes):
    state = {"status": "success", "last_attempt_at": NOW}
    state.update(changes)
    result = freshness.collection_receipt({"DART": state}, now=NOW)
    assert freshness.validate_collection_receipt(result)
    dart = result["sources"]["DART"]
    assert dart["status"] == "unknown"
    assert dart["last_success_at"] is None
    assert dart["health"] == {"status": "unknown", "age_seconds": None}
    assert "private-key" not in json.dumps(result)


@pytest.mark.parametrize("source,boundary", [("DART", 120), ("SEC", 120), ("news", 300)])
def test_collection_cadence_boundaries(freshness, source, boundary):
    states = {source: {"status": "success", "last_success_at": ORIGIN, "last_attempt_at": ORIGIN}}
    for age, status in ((boundary, "on-time"), (boundary + 1, "delayed")):
        result = freshness.collection_receipt(states, now=stamp(age))
        assert result["sources"][source]["health"] == {"status": status, "age_seconds": age}
        assert freshness.validate_collection_receipt(result)


@pytest.mark.parametrize("path,value", [
    (("extra",), "private"),
    (("schema",), "other"),
    (("checked_at",), "2026-10-28"),
    (("checkpoint_status",), "secret=untrusted"),
    (("checkpoint_status",), ["available"]),
    (("screen_delivery_verified",), True),
    (("analysis_delivery_verified",), 0),
    (("sources", "extra"), {}),
    (("sources", "DART", "feed"), {"private": "not-allowed"}),
    (("sources", "DART", "status"), ["success"]),
    (("sources", "DART", "last_success_at"), stamp(3601)),
    (("sources", "DART", "health", "status"), "on-time"),
    (("sources", "DART", "health", "age_seconds"), False),
    (("sources", "DART", "health", "age_seconds"), float("nan")),
    (("sources", "DART", "health", "age_seconds"), float("inf")),
])
def test_receipt_validator_rejects_open_or_forged_shapes(freshness, path, value):
    result = freshness.collection_receipt({}, now=NOW)
    parent = result
    for key in path[:-1]:
        parent = parent[key]
    parent[path[-1]] = value
    assert freshness.validate_collection_receipt(result) is False


@pytest.mark.parametrize("value", [None, [], "", 0, {"sources": {}}])
def test_receipt_validator_is_boolean_for_malformed_input(freshness, value):
    assert freshness.validate_collection_receipt(value) is False


@pytest.mark.parametrize("value", ["0001-01-01T00:00:00+23:00", "9999-12-31T23:59:59-23:00",
                                   "2026-10-28T00:00:00", "2026-10-28", None, {}])
def test_unrepresentable_naive_or_noninstant_is_unknown(freshness, value):
    assert freshness.instant(value) is None


def test_natural_collection_does_not_supply_screen_receipts(freshness):
    from api.collectors.member_map_listing_delta import merge_feed, parse_dart_list
    row = parse_dart_list({"status": "000", "page_no": 1, "page_count": 100,
        "total_count": 1, "total_page": 1,
        "list": [{"rcept_no": "20261028000001", "rcept_dt": "20261028",
                  "stock_code": "123456", "report_nm": "Public filing"}]})["rows"][0]
    row.update(name="Example", observed_at=ORIGIN)
    original = merge_feed({"items": []}, [row], ORIGIN, max_per_ticker=8)
    refreshed = merge_feed(original, [{**row, "observed_at": NOW}], NOW, max_per_ticker=8)
    observed = refreshed["items"][0]["disclosures"][0]["observed_at"]
    assert observed == ORIGIN
    # Only date precision and the preserved observed_at can be supplied.
    measured = freshness.delivery_evidence({
        "source_available_at": row["date"], "source_precision": row["date_precision"],
        "first_seen_at": observed}, now=NOW)
    assert measured["end_to_end_measurable"] is False
    assert measured["source_available"]["facts"]["status"] == "unknown"
    assert measured["first_observed"]["facts"]["status"] == "overdue"
    assert measured["timestamps"]["facts_visible_at"] is None
    assert measured["timestamps"]["analysis_visible_at"] is None


def test_api_and_generation_fields_are_not_screen_or_publication_evidence(freshness):
    row = {"generated_at": NOW, "observed_at": ORIGIN, "source_reported_at": ORIGIN,
           "date_precision": "timestamp", "source_date_field": "atom.updated",
           "facts_delivered_at": NOW, "analysis_delivered_at": NOW, "feed": {"items": []}}
    report = freshness.summarize_delivery_evidence([row], now=NOW)
    assert report["source_precision_counts"] == {"timestamp": 0, "date": 0, "unknown": 1}
    for axis in ("source_available", "first_observed"):
        for stats in report[axis].values():
            assert stats["unknown"] == 1 and stats["eligible"] == stats["completed"] == 0
            assert stats["p95_seconds"] is None


@pytest.mark.parametrize("now", ["bad", "2026-10-28", "2026-10-28T02:00:00"])
def test_invalid_evaluation_clocks_raise_fixed_input_error(freshness, now):
    with pytest.raises(ValueError, match="^freshness-input$"):
        freshness.delivery_evidence({}, now=now)
    with pytest.raises(ValueError, match="^freshness-input$"):
        freshness.summarize_delivery_evidence([], now=now)
    with pytest.raises(ValueError, match="^freshness-input$"):
        freshness.collection_receipt({}, now=now)
