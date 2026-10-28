from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts.audit import us_forensics_coverage as audit


def _write(path: Path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")


@pytest.mark.parametrize("no_recent_filing", [None, 0, 1])
def test_audit_uses_dynamic_universe_and_keeps_event_absence_neutral(monkeypatch, tmp_path, no_recent_filing):
    _write(tmp_path / "us_universe_combined.json", {"tickers": ["AAA", "BBB"]})
    for key, spec in audit.SOURCES.items():
        meta = {"generated_at": "2026-09-05T00:00:00+00:00"}
        stocks = [{"ticker": "AAA"}]
        if key == "disclosure_forensics":
            meta.update({
                "processed_n": 2,
                "unprocessed_tickers": [],
                "event_present_n": 1,
                "no_recent_8k_n": 1,
            })
            if no_recent_filing is not None:
                meta["no_recent_filing_n"] = no_recent_filing
            stocks.append({"ticker": "BBB"})
        elif key == "short_interest":
            meta.update({"covered_n": 1, "universe_n": 2})
        _write(tmp_path / spec["artifact"], {"_meta": meta, "stocks": stocks})

    monkeypatch.setattr(audit, "DATA", tmp_path)
    report = audit.build_report(datetime(2026, 9, 5, 1, tzinfo=timezone.utc))

    assert report["_meta"]["universe_n"] == 2
    assert report["sources"]["insider"]["record_present_n"] == 1
    assert report["sources"]["insider"]["processed_n"] is None
    assert "이벤트 없음" in report["sources"]["insider"]["absence_means"]
    assert report["sources"]["disclosure_forensics"]["processed_n"] == 2
    assert report["sources"]["disclosure_forensics"]["record_present_n"] == 2
    assert report["sources"]["disclosure_forensics"]["no_recent_event_n"] == (1 if no_recent_filing is None else no_recent_filing)
    assert report["sources"]["disclosure_forensics"]["no_recent_8k_n"] == 1


def test_daily_workflow_rebuilds_and_commits_all_three_outputs():
    body = Path(".github/workflows/us_disclosure_feed.yml").read_text(encoding="utf-8")
    assert "us_disclosure_forensics_builder --merge-feed-only" in body
    assert "scripts/audit/us_forensics_coverage.py" in body
    for path in (
        "data/us_disclosure_feed.json",
        "data/us_disclosure_forensics.json",
        "data/metadata/us_forensics_coverage.json",
    ):
        assert f"git add {path}" in body
