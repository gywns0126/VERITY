from __future__ import annotations

import json
from copy import deepcopy

import pytest

from api.builders import us_disclosure_forensics_builder as builder


def _write(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_merge_emits_every_ticker_and_separates_no_event_from_unknown(monkeypatch, tmp_path):
    universe_path = tmp_path / "universe.json"
    feed_path = tmp_path / "feed.json"
    output_path = tmp_path / "forensics.json"
    _write(universe_path, {
        "tickers": ["AAPL", "NONE", "MISS"],
        "names": {"AAPL": "Apple", "NONE": "No Event", "MISS": "Missing"},
    })
    _write(feed_path, {
        "_meta": {"window_days": 90, "max_per_ticker": 5, "processed_n": 2},
        "_coverage": {
            "processed_tickers": ["AAPL", "NONE"],
            "unavailable_tickers": ["MISS"],
        },
        "items": [{
            "ticker": "AAPL",
            "latest": "2026-09-04",
            "disclosures": [{
                "date": "2026-09-04",
                "title": "Current report",
                "item_codes": ["3.02"],
            }],
        }],
    })
    monkeypatch.setattr(builder, "UNIVERSE_PATH", str(universe_path))
    monkeypatch.setattr(builder, "FEED_PATH", str(feed_path))
    monkeypatch.setattr(builder, "OUTPUT_PATH", str(output_path))

    result = builder._merge_with_feed([{
        "ticker": "AAPL",
        "name": "Apple",
        "counts": {"dilution": 2},
        "n_8k": 7,
        "latest_8k": "2026-08-01",
    }])
    rows = {row["ticker"]: row for row in result["stocks"]}

    assert len(rows) == 3
    assert result["_meta"]["processed_n"] == 2
    assert result["_meta"]["unprocessed_tickers"] == ["MISS"]
    assert rows["AAPL"]["event_state"] == "recent_8k"
    assert rows["AAPL"]["counts"]["dilution"] == 2
    assert rows["NONE"]["event_state"] == "no_recent_8k"
    assert rows["MISS"]["event_state"] == "unknown"
    assert rows["MISS"]["collection_status"] == "source_unavailable"
    assert rows["AAPL"]["recent_8k_n"] == rows["AAPL"]["recent_filing_n"] == 1
    assert rows["AAPL"]["n_8k"] == 7  # Keep the original deep-window count.
    assert rows["AAPL"]["filing_state"] == "recent_filing"
    assert rows["NONE"]["filing_state"] == "no_recent_filing"
    assert rows["MISS"]["filing_state"] == "unknown"


@pytest.fixture
def merge_feed(monkeypatch, tmp_path):
    for attr, filename in (("UNIVERSE_PATH", "universe.json"), ("FEED_PATH", "feed.json"),
                           ("OUTPUT_PATH", "forensics.json")):
        monkeypatch.setattr(builder, attr, str(tmp_path / filename))
    monkeypatch.setattr(builder, "_fetch_filings", lambda *_args: pytest.fail("unexpected collection"))

    def merge(items, processed, *, unavailable=(), unresolved=(), deep=()):
        universe = list(dict.fromkeys([row["ticker"] for row in items] + list(processed)))
        _write(tmp_path / "universe.json", {"tickers": universe})
        _write(tmp_path / "feed.json", {
            "_meta": {"forms": ["8-K", "8-K/A", "6-K", "6-K/A", "20-F", "20-F/A", "40-F", "40-F/A"],
                      "window_days": 90, "max_per_ticker": 5},
            "_coverage": {"processed_tickers": processed, "unavailable_tickers": list(unavailable),
                          "unresolved_tickers": list(unresolved)},
            "items": items,
        })
        return builder._merge_with_feed(list(deep))

    return merge


def _event(form, day="2026-09-04"):
    return {"label": form, "date": day, "title": "Reported fact", "item_codes": ["3.02"]}


def _item(ticker, *events):
    return {"ticker": ticker, "latest": max(event["date"] for event in events), "disclosures": list(events)}


@pytest.mark.parametrize("form", ["6-K", "6-K/A", "20-F", "20-F/A", "40-F", "40-F/A"])
@pytest.mark.parametrize("has_deep", [False, True])
def test_foreign_forms_have_generic_state_and_cannot_inflate_8k_stats(merge_feed, form, has_deep):
    deep = [{"ticker": "ADR", "counts": {"dilution": 2}, "n_8k": 7,
             "latest_8k": "2026-08-01", "deep_window_days": 730}] if has_deep else []
    before = deepcopy(deep)
    result = merge_feed([_item("ADR", _event(form))], ["ADR"], deep=deep)
    row = result["stocks"][0]
    assert row["recent_8k_n"] == 0
    assert row["n_8k"] == (7 if has_deep else 0)
    assert row["latest_8k"] == ("2026-08-01" if has_deep else "")
    assert row["counts"] == ({"dilution": 2} if has_deep else {})
    assert row["recent_filing_n"] == 1
    assert row["recent_filing_counts"] == {form: 1}
    assert row["latest_filing"] == "2026-09-04"
    assert row["event_state"] == row["filing_state"] == "recent_filing"
    assert row["collection_status"] == "covered"
    assert result["_meta"]["event_present_n"] == 1
    assert result["_meta"]["recent_8k_present_n"] == 0
    assert result["_meta"]["no_recent_8k_n"] == 1
    assert result["_meta"]["no_recent_filing_n"] == 0
    assert deep == before


def test_mixed_forms_keep_8k_counts_latest_and_shared_cap_separate(merge_feed):
    events = [_event("8-K", "2026-09-01"), _event("8-K/A", "2026-09-02"),
              _event("6-K"), _event("20-F"), _event("40-F")]
    result = merge_feed([_item("MIX", *events)], ["MIX"])
    row = result["stocks"][0]
    assert row["n_8k"] == row["recent_8k_n"] == 2
    assert row["latest_8k"] == "2026-09-02"
    assert row["counts"] == {"dilution": 2}
    assert row["recent_filing_n"] == 5
    assert row["recent_filing_counts"] == {form: 1 for form in ("8-K", "8-K/A", "6-K", "20-F", "40-F")}
    assert row["latest_filing"] == "2026-09-04"
    assert row["recent_8k_truncated"] is row["recent_filing_truncated"] is True
    assert row["recent_filings"] == events
    assert row["event_state"] == "recent_8k" and row["filing_state"] == "recent_filing"
    assert result["_meta"]["recent_8k_present_n"] == 1
    assert result["_meta"]["no_recent_8k_n"] == result["_meta"]["no_recent_filing_n"] == 0


def test_foreign_carry_forward_does_not_turn_failure_or_deferral_into_empty(merge_feed):
    result = merge_feed([_item(ticker, _event("6-K")) for ticker in ("FAIL", "MISS", "DEFER")],
                        ["EMPTY"], unavailable=["FAIL"], unresolved=["MISS"])
    rows = {row["ticker"]: row for row in result["stocks"]}
    for ticker, status in (("FAIL", "source_unavailable"), ("MISS", "cik_unresolved"), ("DEFER", "unprocessed")):
        assert rows[ticker]["event_state"] == rows[ticker]["filing_state"] == "unknown"
        assert rows[ticker]["collection_status"] == status
        assert rows[ticker]["recent_filing_n"] == 1 and rows[ticker]["recent_8k_n"] == 0
    assert rows["EMPTY"]["filing_state"] == "no_recent_filing"
    assert result["_meta"]["no_recent_filing_n"] == result["_meta"]["no_recent_8k_n"] == 1


def test_missing_label_in_declared_mixed_feed_does_not_become_8k(merge_feed):
    event = _event("8-K")
    event.pop("label")
    result = merge_feed([_item("UNKNOWN", event)], ["UNKNOWN"])
    row = result["stocks"][0]
    assert row["recent_filing_counts"] == {"unknown": 1}
    assert row["recent_8k_n"] == 0 and row["counts"] == {}
    assert row["recent_8k_state"] == "unknown"
    assert result["_meta"]["no_recent_8k_n"] == 0


def test_foreign_forms_at_shared_cap_cannot_prove_8k_absence(merge_feed):
    result = merge_feed([_item("ADR", *[_event("6-K") for _ in range(5)])], ["ADR"])
    row = result["stocks"][0]
    assert row["recent_filing_counts"] == {"6-K": 5}
    assert row["recent_8k_n"] == 0
    assert row["recent_8k_state"] == "unknown"
    assert row["filing_state"] == row["event_state"] == "recent_filing"
    assert row["recent_8k_truncated"] is True
    assert result["_meta"]["no_recent_8k_n"] == result["_meta"]["no_recent_filing_n"] == 0
