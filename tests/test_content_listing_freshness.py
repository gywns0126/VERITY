"""Listing coverage does not certify original text, event recency or latest revision."""
import sys
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "vercel-api"))
from content_evidence import build_result

NOW = datetime(2026, 9, 27, 4, tzinfo=timezone.utc)


def source():
    groups = [{"corp_cls": c, "pblntf_ty": t, "status": "success", "pages_attempted": 1,
               "pages_succeeded": 1, "total_pages": 0, "failure": None}
              for c in ("Y", "K") for t in ("B", "C", "D", "I")]
    return {"items": [], "_meta": {"generated_at": NOW.isoformat(), "source_collection": {
        "schema_version": 1, "endpoint": "list.json", "status": "success",
        "attempted_at": (NOW - timedelta(minutes=2)).isoformat(),
        "completed_at": (NOW - timedelta(minutes=1)).isoformat(),
        "successful_checked_at": (NOW - timedelta(minutes=1)).isoformat(),
        "window": {"bgn": "2026-09-20", "end": "2026-09-27"},
        "scope": {"corp_cls": ["Y", "K"], "pblntf_ty": ["B", "C", "D", "I"],
                  "i_title_keywords": ["단일판매", "공급계약", "수주"], "requires_stock_code": True},
        "groups": groups, "groups_expected": 8, "groups_completed": 8,
        "pages_attempted": 8, "pages_succeeded": 8}}}


def result(doc, now=NOW):
    return build_result(doc, "search_content_candidates", {}, now)


def test_successful_empty_listing_is_separate_from_original_or_market():
    out = result(source())
    assert out["listing_collection"]["status"] == "recent"
    assert out["listing_collection"]["groups_completed"] == 8
    assert out["freshness_status"] == "unknown"
    assert out["source_checked_at"] is None
    assert out["breaking_eligible"] is False
    assert out["latest_revision_verified"] is False
    assert out["listing_collection"]["whole_market_coverage"] is False


def test_artifact_rebuild_does_not_refresh_listing_check():
    doc = source()
    later = NOW + timedelta(days=2)
    doc["_meta"]["generated_at"] = later.isoformat()
    out = result(doc, later)
    assert out["listing_collection"]["status"] == "stale"
    assert out["listing_collection"]["checked_at"] == source()["_meta"]["source_collection"]["successful_checked_at"]


def test_new_listing_check_does_not_refresh_preserved_old_snapshot():
    doc = source()
    doc["_meta"]["generated_at"] = (NOW - timedelta(days=20)).isoformat()
    out = result(doc)
    assert out["listing_collection"]["status"] == "recent"
    assert out["freshness_status"] == "stale"
    assert out["breaking_eligible"] is False


def test_inconsistent_or_unscoped_claims_fail_closed():
    edits = [{"groups_completed": 7}, {"groups_expected": 7}, {"pages_succeeded": 9},
             {"groups": []}, {"completed_at": NOW.isoformat()}, {"successful_checked_at": "tomorrow"},
             {"endpoint": "document.xml"}, {"scope": {}}, {"window": {"bgn": "2026-09-20", "end": "2026-09-26"}}]
    for edit in edits:
        doc = source()
        doc["_meta"]["source_collection"].update(edit)
        assert result(doc)["listing_collection"]["status"] == "unknown"
    doc = source()
    doc["_meta"]["source_collection"]["groups"][0]["pages_succeeded"] = True
    assert result(doc)["listing_collection"]["status"] == "unknown"


def test_partial_never_keeps_a_success_time():
    doc = source()
    s = doc["_meta"]["source_collection"]
    s["status"] = "partial"
    s["groups_completed"] = 7
    s["groups"][0].update(status="truncated", failure="page_cap")
    out = result(doc)["listing_collection"]
    assert out["status"] == "partial" and out["checked_at"] is None
    assert out["groups_completed"] == 7


def test_projection_excludes_extra_metadata_and_is_pure():
    doc = source()
    doc["_meta"]["source_collection"]["window"]["secret"] = "do-not-return"
    before = deepcopy(doc)
    assert "secret" not in result(doc)["listing_collection"]["window"]
    assert doc == before
