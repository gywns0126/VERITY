"""Offline provenance regressions for daily macro quotes and snapshot fallback."""
from copy import deepcopy
from datetime import datetime
from types import SimpleNamespace

import pandas as pd
import pytest

from api.builders import macro_collect_builder as builder
from api.collectors import macro_data as macro


NOW = "2026-10-17T09:00:00+09:00"
OLD = "2026-10-16T09:00:00+09:00"


@pytest.fixture(autouse=True)
def offline_clock(monkeypatch):
    monkeypatch.setattr(macro, "_now_kst_iso", lambda: NOW)
    monkeypatch.setattr(builder, "_now_kst", lambda: datetime.fromisoformat(NOW))

    def forbidden(*args, **kwargs):
        raise AssertionError("external collection is forbidden in these tests")

    monkeypatch.setattr(macro.requests, "get", forbidden)
    monkeypatch.setattr(macro.yf, "Ticker", forbidden)
    monkeypatch.setattr(macro.yf, "download", forbidden)


def history(index=None):
    return pd.DataFrame(
        {"Close": [100.0, 105.0, float("nan")]},
        index=index if index is not None else pd.date_range(
            "2026-10-14", periods=3, tz="America/New_York"),
    )


YAHOO_READERS = [
    lambda: macro._get_usd_krw(),
    lambda: macro._get_fx("JPY=X", "USD/JPY"),
    lambda: macro._get_commodity("^VIX", "VIX"),
    lambda: macro._get_commodity_with_history("GC=F", "gold"),
    lambda: macro._get_index_change("^N225", "Nikkei"),
]


@pytest.mark.parametrize("read", YAHOO_READERS)
def test_daily_source_date_tracks_selected_close_not_fetch_clock(monkeypatch, read):
    monkeypatch.setattr(macro.yf, "Ticker", lambda *_: SimpleNamespace(history=lambda **_: history()))
    row = read()
    assert row["status"] == "ok"
    assert row["value"] == 105
    assert row["source_as_of"] == "2026-10-15"  # trailing NaN's date is not the quote date
    assert row["fetched_at"] == row["last_successful_at"] == NOW
    assert row["as_of"] == NOW  # legacy contract remains a collection timestamp
    assert row["as_of_kind"] == "fetched_at"
    assert row["stale"] is False
    assert row["reused"] is False


@pytest.mark.parametrize("read", YAHOO_READERS)
@pytest.mark.parametrize("source_date", [None, "not-a-date", "2026-02-30", pd.NaT, 42])
def test_missing_or_invalid_daily_index_never_becomes_collection_date(monkeypatch, read, source_date):
    frame = history(pd.Index(["2026-10-14", source_date, "2026-10-16"]))
    monkeypatch.setattr(macro.yf, "Ticker", lambda *_: SimpleNamespace(history=lambda **_: frame))
    row = read()
    assert row["value"] == 105
    assert row["source_as_of"] is None
    assert row["source_date_status"] in {"missing", "invalid"}
    assert row["last_successful_at"] == NOW  # value fetched, observation date unknown
    assert row["stale"] is True


@pytest.mark.parametrize("read", YAHOO_READERS)
def test_failed_collection_has_no_success_clock(monkeypatch, read):
    def unavailable(**kwargs):
        raise RuntimeError("offline fixture")

    monkeypatch.setattr(macro.yf, "Ticker", lambda *_: SimpleNamespace(history=unavailable))
    row = read()
    assert row["status"] == "fail"
    assert row["source_as_of"] is None
    assert row["last_successful_at"] is None
    assert row["stale"] is True


@pytest.mark.parametrize("day,expected", [
    ("2026-10-15", "2026-10-15"), (None, None), ("2026-02-30", None), ("garbage", None),
    ("2026-10-18", None),
])
def test_fred_keeps_date_attached_to_last_nonmissing_value(monkeypatch, day, expected):
    response = SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: {"observations": [
            {"date": "2026-10-16", "value": "."},
            {"date": day, "value": "105"},
            {"date": "2026-10-14", "value": "100"},
        ]},
    )
    monkeypatch.setattr(macro.requests, "get", lambda *_, **__: response)
    row = macro._get_index_change_fred("SP500", "S&P500")
    assert row["value"] == 105
    assert row["source_as_of"] == expected
    assert row["fetched_at"] == row["last_successful_at"] == NOW
    assert row["stale"] is (expected is None)


def previous_snapshot():
    return {
        "collected_at": OLD,
        "macro": {"gold": {
            "value": 100, "status": "ok", "source": "yfinance", "as_of": OLD,
            "source_as_of": "2026-10-14", "fetched_at": OLD, "last_successful_at": OLD,
        }},
        "bonds": {"us": {"as_of": "2026-10-14", "value": 4.0}},
        "global_events": [{"title": "old event"}],
        "collector_meta": {
            name: {"last_successful_at": OLD, "fetched_at": OLD}
            for name in ("macro", "bonds", "global_events")
        },
    }


def build_fixture(monkeypatch, previous, results):
    monkeypatch.setattr(builder, "_load_existing", lambda: previous)
    monkeypatch.setattr(builder, "_safe_call", lambda fn, name, timeout_s: results[name])
    return builder.build()


def test_successful_refresh_updates_success_clock_and_keeps_source_day(monkeypatch):
    previous = previous_snapshot()
    row = macro._commodity_payload(history(), "GC=F", "gold")
    result = build_fixture(monkeypatch, previous, {
        "macro": ({"gold": row}, None), "bonds": ({"value": 4.1}, None),
        "global_events": ([], None),
    })
    assert result["macro"]["gold"]["source_as_of"] == "2026-10-15"
    assert result["macro"]["gold"]["last_successful_at"] == NOW
    assert result["global_events"] == []  # successful empty list must not resurrect old events
    assert result["diagnostics"]["used_prev_snapshot"] == []
    for meta in result["collector_meta"].values():
        assert meta["last_successful_at"] == NOW
        assert meta["stale"] is meta["reused"] is False
    assert previous == previous_snapshot()


@pytest.mark.parametrize("failed_value", [None, {}])
def test_reused_snapshot_preserves_dates_across_repeated_failures(monkeypatch, failed_value):
    previous = previous_snapshot()
    results = {name: (failed_value, "timeout") for name in ("macro", "bonds", "global_events")}
    first = build_fixture(monkeypatch, previous, results)
    second = build_fixture(monkeypatch, first, results)
    for result in (first, second):
        row = result["macro"]["gold"]
        assert row["source_as_of"] == "2026-10-14"
        assert row["as_of"] == row["fetched_at"] == row["last_successful_at"] == OLD
        assert row["stale"] is row["reused"] is True
        for meta in result["collector_meta"].values():
            assert meta["last_successful_at"] == meta["fetched_at"] == OLD
            assert meta["last_attempted_at"] == NOW
            assert meta["stale"] is meta["reused"] is True
    assert previous == previous_snapshot()


def test_partial_quote_failure_preserves_only_failed_quote(monkeypatch):
    previous = previous_snapshot()
    fresh = macro._commodity_payload(history(), "SI=F", "silver")
    result = build_fixture(monkeypatch, previous, {
        "macro": ({"gold": {"status": "fail", "value": 0}, "silver": fresh}, None),
        "bonds": ({"value": 4.1}, None), "global_events": ([], None),
    })
    assert result["macro"]["gold"]["last_successful_at"] == OLD
    assert result["macro"]["gold"]["reused"] is True
    assert result["macro"]["silver"] == fresh
    assert result["diagnostics"]["reused_macro_fields"] == ["gold"]
    assert result["collector_meta"]["macro"]["last_successful_at"] == OLD
    assert result["collector_meta"]["macro"]["stale"] is True
    assert result["diagnostics"]["macro_ok"] is False


def test_legacy_fallback_does_not_invent_source_or_success_dates(monkeypatch):
    previous = {"collected_at": OLD, "macro": {"gold": {"value": 100, "as_of": OLD}}}
    saved = deepcopy(previous)
    result = build_fixture(monkeypatch, previous, {
        name: (None, "timeout") for name in ("macro", "bonds", "global_events")
    })
    row = result["macro"]["gold"]
    assert row["as_of"] == OLD
    assert row.get("source_as_of") is None
    assert row.get("last_successful_at") is None
    assert row["stale"] is row["reused"] is True
    assert result["collector_meta"]["macro"]["last_successful_at"] is None
    assert previous == saved


def test_failure_without_previous_snapshot_has_no_success_or_reuse(monkeypatch):
    result = build_fixture(monkeypatch, {}, {
        name: (None, "timeout") for name in ("macro", "bonds", "global_events")
    })
    assert result["macro"] == result["bonds"] == {}
    assert result["global_events"] == []
    for meta in result["collector_meta"].values():
        assert meta["last_successful_at"] is meta["fetched_at"] is None
        assert meta["stale"] is True
        assert meta["reused"] is False


def test_nonobject_previous_snapshot_is_ignored(monkeypatch, tmp_path):
    path = tmp_path / "macro_snapshot.json"
    path.write_text('[{"unexpected": true}]', encoding="utf-8")
    monkeypatch.setattr(builder, "OUTPUT_PATH", str(path))
    assert builder._load_existing() == {}


@pytest.mark.parametrize("source_date,expected", [
    ("2026-10-17", "2026-10-17"),
    ("2026-10-18", None),
    (pd.Timestamp("2026-10-17T23:30:00-04:00"), "2026-10-17"),
    (pd.Timestamp("2026-10-18T00:30:00+14:00"), None),
])
def test_future_source_day_is_invalid_without_timezone_shift(source_date, expected):
    meta = macro._quote_meta("yfinance", source_date, successful=True)
    assert meta["source_as_of"] == expected
    assert meta["source_date_status"] == ("ok" if expected else "invalid")
    assert meta["stale"] is (expected is None)
    assert meta["last_successful_at"] == NOW


def test_future_source_date_makes_macro_health_stale(monkeypatch):
    row = macro._commodity_payload(history(pd.date_range("2026-10-17", periods=3)), "GC=F", "gold")
    assert row["source_as_of"] is None
    assert row["source_date_status"] == "invalid"
    result = build_fixture(monkeypatch, previous_snapshot(), {
        "macro": ({"gold": row}, None), "bonds": ({"value": 4.1}, None),
        "global_events": ([], None),
    })
    assert result["collector_meta"]["macro"]["stale"] is True
    assert result["diagnostics"]["macro_ok"] is False
