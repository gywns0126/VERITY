"""JSON-equivalent overlay copies keep dates, ordering and isolation intact."""
from copy import deepcopy
import importlib
import json
from pathlib import Path
import sys
import types

import pytest

PACKAGE = "map_overlay_copy_test"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(Path(__file__).resolve().parents[1] / "vercel-api/api/portfolio_core")]
sys.modules[PACKAGE] = package
fetch = importlib.import_module(PACKAGE + ".portfolio_public_fetch")
live = importlib.import_module(PACKAGE + ".member_map_live_refresh")
STAMP = "2026-10-12T12:00:00+00:00"


def row(title, url):
    return {"title": title, "source": "Synthetic", "link": url, "time": STAMP}


@pytest.mark.parametrize("incoming", [[], [row("new", "https://example.org/new")],
                                     [row("updated", "https://example.org/old")]])
def test_news_cells_order_and_nested_alias_isolation_match_deepcopy(incoming):
    shared = {"date": STAMP, "evidence": ["original sentence"], "value": 0.0}
    docs = {"portfolio.json": {"headlines": [row("old", "https://example.org/old")],
                              "non_news": {"left": shared, "right": shared}},
            "member_map_ai_candidates.json": {"judgments": []}}
    state = {"news": {"feed": {"headlines": incoming}}}
    before = deepcopy(docs)
    expected = live.overlay_states(docs, state)
    actual = live.overlay_states(docs, state, copy_document=fetch._copy_public_bundle)
    assert json.dumps(actual, ensure_ascii=False) == json.dumps(expected, ensure_ascii=False)
    assert docs == before
    copied = actual["portfolio.json"]["non_news"]
    assert copied["left"] is copied["right"]
    assert copied["left"] is not shared
    copied["left"]["evidence"].append("synthetic edit")
    assert docs == before
    assert actual["member_map_ai_candidates.json"] is docs["member_map_ai_candidates.json"]


def test_validated_checkpoint_and_retained_error_path_are_isolated():
    fetch._reset_cache_for_tests()
    checkpoint = live.apply_result("news", {}, {
        "status": "partial", "error": "per-feed-completeness-unavailable",
        "requests": 1, "feed": {"headlines": [row("new", "https://example.org/new")]},
    }, STAMP)
    docs = {"portfolio.json": {"headlines": [row("old", "https://example.org/old")]}}
    accepted = fetch._refresh_overlay(docs, lambda: {"news": checkpoint})
    assert fetch._LIVE_CHECKPOINT_STATUS == "available"
    assert accepted["portfolio.json"]["headlines"][0]["title"] == "new"
    original = deepcopy(fetch._LIVE_STATES)
    checkpoint["feed"]["headlines"][0]["title"] = "caller edit"
    assert fetch._LIVE_STATES == original
    def failed_read():
        raise RuntimeError("synthetic unavailable")
    retained = fetch._refresh_overlay(docs, failed_read)
    assert retained == accepted
    assert fetch._LIVE_CHECKPOINT_STATUS == "retained"
    retained["portfolio.json"]["headlines"][0]["title"] = "response edit"
    assert fetch._LIVE_STATES == original
    assert original["news"]["last_attempt_at"] == STAMP
    assert original["news"].get("last_success_at") is None
    fetch._reset_cache_for_tests()
