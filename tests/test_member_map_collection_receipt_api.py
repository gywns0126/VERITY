"""Collection diagnostics reach the API without becoming map content or user state."""
from copy import deepcopy
import importlib
import json

from tests.test_member_map_analysis import modules, _bundle, _request
from tests.test_member_map_refresh_api_overlay import baseline, state


def test_collection_receipt_is_private_response_metadata_not_content_revision(modules, monkeypatch):
    endpoint, storage = modules
    helper = importlib.import_module("api.portfolio_core.member_map_freshness")
    source = _bundle()
    source["refresh_receipt"] = helper.collection_receipt({"DART": state()},
        now="2026-10-12T12:01:00+00:00")
    monkeypatch.setattr(endpoint, "fetch_public_sources", lambda: source)
    def request():
        return endpoint.analyze_request(_request("jwt-a", {
            "positions": [{"ticker": "005930", "market": "KR"}]}))
    status, headers, first = request()
    assert status == 200
    assert first["_meta"]["source_health"] == source["refresh_receipt"]
    source["refresh_receipt"] = helper.collection_receipt({"DART": state()},
        now="2026-10-12T12:10:00+00:00", checkpoint_status="retained")
    status, _, second = request()
    assert status == 200
    assert first["revision"] == second["revision"]
    assert first["companies"] == second["companies"]
    assert second["_meta"]["source_health"]["sources"]["DART"]["health"]["status"] == "delayed"
    second["_meta"]["source_health"]["sources"].clear()
    assert source["refresh_receipt"]["sources"]
    assert "no-store" in headers["Cache-Control"]
    storage.select.assert_not_called()


def test_invalid_optional_receipt_cannot_leak_fields_or_hide_facts(modules, monkeypatch):
    endpoint, storage = modules
    source = _bundle()
    source["refresh_receipt"] = {"cursor": "private-canary", "status": "success"}
    monkeypatch.setattr(endpoint, "fetch_public_sources", lambda: source)
    status, _, result = endpoint.analyze_request(_request("jwt-a", {
        "positions": [{"ticker": "005930", "market": "KR"}]}))
    assert status == 200 and result["companies"]
    assert result["_meta"]["source_health"] == {"status": "rejected"}
    assert "private-canary" not in json.dumps(result)
    storage.select.assert_not_called()


def test_borrowed_snapshot_retains_original_collection_clock_after_read_failure(modules, monkeypatch):
    fetch = importlib.import_module("api.portfolio_core.portfolio_public_fetch")
    fetch._reset_cache_for_tests()
    monkeypatch.setattr(fetch, "_download_source", baseline)
    monkeypatch.setattr(fetch, "_read_refresh_states", lambda: {"DART": state()})
    first = fetch.borrow_public_sources_for_analysis()
    receipt = first["refresh_receipt"]
    assert receipt["checkpoint_status"] == "available"
    assert receipt["sources"]["DART"]["last_success_at"] == state()["last_success_at"]
    assert receipt["sources"]["SEC"]["status"] == "unknown"
    assert not receipt["screen_delivery_verified"]
    assert all(key not in json.dumps(receipt) for key in ("feed", "cursor", "lease_owner", "jwt-a"))
    original = deepcopy(first["documents"])
    def failed():
        raise TimeoutError("private-canary")
    monkeypatch.setattr(fetch, "_read_refresh_states", failed)
    fetch._CACHE_EXPIRES_AT = 0
    second = fetch.borrow_public_sources_for_analysis()
    assert second["refresh_receipt"]["checkpoint_status"] == "retained"
    assert second["refresh_receipt"]["sources"]["DART"]["last_success_at"] == state()["last_success_at"]
    assert second["documents"] == original
    assert second["revision"] == first["revision"]
    assert "private-canary" not in json.dumps(second)
    assert "refresh_receipt" not in fetch.fetch_public_sources()
    fetch._reset_cache_for_tests()
