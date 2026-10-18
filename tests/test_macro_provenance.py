"""Offline period/clock contracts and native-field preservation regressions."""
from copy import deepcopy
from datetime import datetime

import pytest

from api.builders import macro_collect_builder as builder
from api.utils import macro_provenance as provenance

NOW = "2026-10-18T09:00:00+09:00"
OLD = "2026-10-17T09:00:00+09:00"


@pytest.mark.parametrize("period,expected,kind", [
    ("202609", "2026-09", "month"), ("2026-09", "2026-09", "month"),
    ("202610", "2026-10", "month"), ("2026-10-16", "2026-10-16", "day"),
])
def test_native_period_keeps_its_granularity(period, expected, kind):
    row = provenance.observation_meta("ecos", period, fetched_at=NOW)
    assert row["source_as_of"] == expected
    assert row["source_period_kind"] == kind
    assert row["fetched_at"] == row["last_successful_at"] == NOW
    assert row["stale"] is row["reused"] is False


@pytest.mark.parametrize("period", [None, "202613", "202611", "2026-02-30", "2026-10-19", "bad"])
def test_real_fetch_clock_does_not_invent_observation_date(period):
    row = provenance.observation_meta("fred", period, fetched_at=NOW)
    assert row["source_as_of"] is None
    assert row["source_date_status"] == ("missing" if period is None else "invalid")
    assert row["last_successful_at"] == NOW
    assert row["stale"] is True


def test_alias_and_composite_inherit_receipts_not_build_clock():
    first = provenance.observation_meta("fred", "2026-10-16", fetched_at=OLD)
    second = provenance.observation_meta("fred", "2026-10-16", fetched_at=NOW)
    assert provenance.copy_meta(first) == first
    row = provenance.derived_meta(first, second)
    assert row["source_as_of"] == "2026-10-16"
    assert row["fetched_at"] == row["last_successful_at"] == OLD
    assert row["stale"] is False
    assert provenance.copy_meta({"value": 5, "date": "2026-10-16"}) == {}


def test_composite_retains_unknown_or_mixed_input_provenance():
    first = provenance.observation_meta("fred", "2026-10-16", fetched_at=OLD)
    second = provenance.observation_meta("fred", "2026-10-15", fetched_at=NOW)
    row = provenance.derived_meta(first, second)
    assert row["source_as_of"] is None
    assert row["source_date_status"] == "mixed"
    assert row["stale"] is True
    legacy = provenance.derived_meta(first, {"value": 3.2})
    assert legacy["last_successful_at"] is None
    assert legacy["stale"] is True


def test_native_missing_and_failed_fields_keep_previous_values_and_clocks(monkeypatch):
    old_cpi = {"index": 330, "yoy_pct": 2.9, "date": "2026-09-01",
               **provenance.observation_meta("fred", "2026-09-01", fetched_at=OLD)}
    old_m2 = {"billions_usd": 23000, "date": "2026-08-01",
              **provenance.observation_meta("fred", "2026-08-01", fetched_at=OLD)}
    old_rate = {"value": 3, "date": "202609",
                **provenance.observation_meta("ecos", "202609", fetched_at=OLD)}
    previous = {"macro": {"fred": {"available": True, "core_cpi": old_cpi, "m2": old_m2},
                           "ecos": {"available": True, "korea_policy_rate": old_rate}},
                "collector_meta": {"macro": {"fetched_at": OLD, "last_successful_at": OLD}}}
    saved = deepcopy(previous)
    fresh_dgs = {"value": 4.1, **provenance.observation_meta("fred", "2026-10-16", fetched_at=NOW)}
    current = {"fred": {"available": True, "dgs10": fresh_dgs,
                         "m2": {"status": "fail", "billions_usd": 0}},
               "ecos": {"available": False}}
    monkeypatch.setattr(builder, "_now_kst", lambda: datetime.fromisoformat(NOW))
    monkeypatch.setattr(builder, "_load_existing", lambda: previous)
    results = {"macro": (current, None), "bonds": ({"value": 4}, None), "global_events": ([], None)}
    monkeypatch.setattr(builder, "_safe_call", lambda fn, name, timeout_s: results[name])
    result = builder.build()
    assert result["diagnostics"]["reused_macro_fields"] == [
        "ecos.korea_policy_rate", "fred.core_cpi", "fred.m2"]
    for group, key, old in (("fred", "core_cpi", old_cpi), ("fred", "m2", old_m2),
                            ("ecos", "korea_policy_rate", old_rate)):
        assert result["macro"][group][key] == {**old, "stale": True, "reused": True}
    assert result["macro"]["fred"]["dgs10"] == fresh_dgs
    assert result["collector_meta"]["macro"]["last_successful_at"] == OLD
    assert result["diagnostics"]["macro_ok"] is False
    assert previous == saved
    assert current["ecos"] == {"available": False}


def test_total_failure_marks_native_non_value_shapes_reused_without_invented_clocks():
    legacy = {"fred": {"core_cpi": {"index": 330, "date": "2026-09-01"},
                       "m2": {"billions_usd": 23000, "date": "2026-08-01"}}}
    saved = deepcopy(legacy)
    result = builder._mark_reused(legacy)
    for row in result["fred"].values():
        assert row["stale"] is row["reused"] is True
        assert row.get("last_successful_at") is None
    assert legacy == saved


def test_failed_yield_input_preserves_spread_but_mixed_dates_do_not(monkeypatch):
    from api.collectors import macro_data as macro
    y10 = {"value": 4.5, **provenance.observation_meta("fred", "2026-10-16", fetched_at=OLD)}
    y2 = {"value": 3.5, **provenance.observation_meta("fred", "2026-10-16", fetched_at=OLD)}
    saved_spread = macro._calc_yield_spread({"us_10y": y10, "us_2y": y2})
    previous = {"us_10y": y10, "us_2y": y2, "yield_spread": saved_spread}
    broken = {"value": 0, "status": "fail"}
    current = {"us_10y": broken, "us_2y": y2,
               "yield_spread": macro._calc_yield_spread({"us_10y": broken, "us_2y": y2})}
    assert current["yield_spread"]["status"] == "fail"
    builder._preserve_partial_macro(current, previous)
    assert current["yield_spread"] == {**saved_spread, "stale": True, "reused": True}
    assert current["yield_spread"]["value"] == 1.0

    mixed = macro._calc_yield_spread({"us_10y": y10, "us_2y": {
        "value": 3.7, **provenance.observation_meta("fred", "2026-10-15", fetched_at=NOW)}})
    current = {"yield_spread": mixed}
    assert mixed["source_date_status"] == "mixed" and mixed["status"] == "ok"
    builder._preserve_partial_macro(current, previous)
    assert current["yield_spread"] == mixed
    assert current["yield_spread"]["value"] == 0.8


def test_failed_daily_ecos_does_not_silently_switch_to_annual_fred():
    old = {"value": 4.18, "date": "2026-10-16", "series_id": "ECOS/817Y002/010210000",
           **provenance.observation_meta("ecos", "2026-10-16", fetched_at=OLD)}
    annual = {"value": 3.2, "date": "2025-01-01", "series_id": "IRLTLT01KRA156N",
              **provenance.observation_meta("fred", "2025-01-01", fetched_at=NOW)}
    current = {"fred": {"korea_gov_10y": annual}}
    reused = builder._preserve_partial_macro(current, {"fred": {"korea_gov_10y": old}})
    assert reused == ["fred.korea_gov_10y"]
    assert current["fred"]["korea_gov_10y"] == {**old, "stale": True, "reused": True}


def test_partial_bonds_keep_actual_fresh_points_but_not_advance_aggregate_success(monkeypatch):
    previous = {"bonds": {"old": True}, "collector_meta": {
        "bonds": {"fetched_at": OLD, "last_successful_at": OLD}}}
    points = {"stale": True, "available": True, "yield_curves": {
        "us": {"curve": [{"tenor": "10Y", "yield": 4.2, "last_successful_at": NOW}]}}}
    results = {"macro": ({"value": 3}, None), "bonds": (points, None), "global_events": ([], None)}
    monkeypatch.setattr(builder, "_load_existing", lambda: previous)
    monkeypatch.setattr(builder, "_safe_call", lambda fn, name, timeout_s: results[name])
    result = builder.build()
    assert result["bonds"] == points
    assert result["collector_meta"]["bonds"]["stale"] is True
    assert result["collector_meta"]["bonds"]["last_successful_at"] == OLD
    assert result["diagnostics"]["bonds_ok"] is False
