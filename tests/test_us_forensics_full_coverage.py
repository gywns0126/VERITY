from __future__ import annotations

import json

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
