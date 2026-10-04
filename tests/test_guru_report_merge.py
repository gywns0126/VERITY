"""Bounded manual data recovery must not replace unrelated report records."""
import copy

import pytest

from scripts.us.merge_guru_report_backfill import merge_report


def fixture():
    source = {"verified_at": "2026-10-04", "financial_source": "SEC companyfacts"}
    base = {"_meta": {"retained": "existing"}, "stocks": [
        {"ticker": "KEEP", "nested": {"value": 7}}, {"ticker": "FIX", "old": True}]}
    candidate = {"_meta": {"manual_backfill": {"verified_at": "2026-10-04"}},
                 "stocks": [{"ticker": t, "data_coverage": source}
                            for t in ("FIX", "NEW")]}
    return base, candidate


def test_bounded_merge_preserves_unrelated_and_inputs():
    base, candidate = fixture()
    snapshot = copy.deepcopy(base)
    result, audit = merge_report(base, candidate, ["FIX", "NEW"])
    assert base == snapshot
    assert result["stocks"][0] == snapshot["stocks"][0]
    assert result["_meta"]["retained"] == "existing"
    assert audit == {"processed": 2, "requested": 2, "before": 2, "after": 3, "unchanged": 1}


@pytest.mark.parametrize("tickers", [[], ["FIX", "FIX"], ["MISSING"]])
def test_rejects_invalid_identity_set(tickers):
    base, candidate = fixture()
    with pytest.raises(ValueError):
        merge_report(base, candidate, tickers)


def test_rejects_unverified_source():
    base, candidate = fixture()
    candidate["stocks"][0]["data_coverage"] = {}
    with pytest.raises(ValueError, match="Missing source"):
        merge_report(base, candidate, ["FIX"])


def test_rejects_period_rollback():
    base, candidate = fixture()
    base["stocks"][1]["financials"] = {"period_end": "2026-12-31"}
    candidate["stocks"][0]["financials"] = {"period_end": "2025-12-31"}
    with pytest.raises(ValueError, match="older financial"):
        merge_report(base, candidate, ["FIX"])
