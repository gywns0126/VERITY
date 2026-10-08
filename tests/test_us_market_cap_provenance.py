"""Cached US market-cap provenance through the helper and stock-data consumer.

Network-free: the snapshot is temporary, Yahoo is fake, and sockets are blocked.
"""
from __future__ import annotations

import json
import socket

import pandas as pd
import pytest

from api.collectors import stock_data, yfinance_safe


OLD_DATE = "2026-09-01T08:00:00+09:00"
OTHER_DATE = "2026-09-20T09:00:00+09:00"
FILE_DATE = "2026-10-07T12:00:00+09:00"

UNKNOWN_METADATA = [
    pytest.param({}, id="legacy-generated-at-only"),
    pytest.param({"market_cap_as_of": None}, id="null-map"),
    pytest.param({"market_cap_as_of": FILE_DATE}, id="string-map"),
    pytest.param({"market_cap_as_of": [OLD_DATE]}, id="list-map"),
    pytest.param({"market_cap_as_of": 123}, id="number-map"),
    pytest.param({"market_cap_as_of": {"OLD": None}}, id="null-date"),
    pytest.param({"market_cap_as_of": {"OLD": ""}}, id="empty-date"),
    pytest.param({"market_cap_as_of": {"OLD": True}}, id="boolean-date"),
    pytest.param({"market_cap_as_of": {"OLD": [OLD_DATE]}}, id="list-date"),
    pytest.param({"market_cap_as_of": {"OTHER": OTHER_DATE}}, id="missing-ticker-date"),
]


@pytest.fixture(autouse=True)
def _isolated_cache_and_no_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("network access forbidden in provenance tests")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    monkeypatch.setattr(stock_data, "_US_MCAP_CACHE", {})
    monkeypatch.setattr(stock_data.yf, "Ticker", blocked)


@pytest.fixture
def snapshot(tmp_path, monkeypatch):
    # The helper resolves data/ relative to its module, not api.config.DATA_DIR.
    monkeypatch.setattr(
        stock_data, "__file__", str(tmp_path / "api" / "collectors" / "stock_data.py")
    )
    path = tmp_path / "data" / "us_market_caps.json"
    path.parent.mkdir(parents=True, exist_ok=True)

    def write(metadata):
        doc = {
            "generated_at": FILE_DATE,
            "market_caps": {"OLD": 5_000_000_000, "OTHER": 7_000_000_000},
            **metadata,
        }
        path.write_text(json.dumps(doc), encoding="utf-8")

    return write


@pytest.fixture
def fake_yahoo(monkeypatch):
    class FakeStock:
        info = {}  # No quote cap or shares: exercise the actual cached fallback.

        def history(self, period):
            return pd.DataFrame(
                {"Close": [20.0, 21.0], "High": [22.0, 23.0],
                 "Low": [19.0, 20.0], "Volume": [100, 200]},
                index=pd.date_range("2026-10-05", periods=2),
            )

    monkeypatch.setattr(stock_data.yf, "Ticker", lambda _: FakeStock())
    monkeypatch.setattr(yfinance_safe, "safe_yf_call", lambda fn, **kwargs: fn())


def test_helper_returns_distinct_ticker_dates(snapshot):
    snapshot({"market_cap_as_of": {"OLD": OLD_DATE, "OTHER": OTHER_DATE}})

    assert stock_data._us_market_cap_cached("old") == (5_000_000_000, OLD_DATE)
    assert stock_data._us_market_cap_cached("OTHER") == (7_000_000_000, OTHER_DATE)


def test_helper_keeps_failed_ticker_last_good_date(snapshot):
    snapshot({"market_cap_as_of": {"OLD": OLD_DATE}, "failed_tickers": ["OLD"]})

    assert stock_data._us_market_cap_cached("OLD") == (5_000_000_000, OLD_DATE)


@pytest.mark.parametrize("metadata", UNKNOWN_METADATA)
def test_helper_unknown_date_never_uses_generated_at(snapshot, metadata):
    snapshot(metadata)

    assert stock_data._us_market_cap_cached("OLD") == (5_000_000_000, None)


def test_stock_data_emits_ticker_dates_including_failed_carry_forward(snapshot, fake_yahoo):
    snapshot({
        "market_cap_as_of": {"OLD": OLD_DATE, "OTHER": OTHER_DATE},
        "failed_tickers": ["OLD"],
    })

    for ticker, cap, date in [
        ("OLD", 5_000_000_000, OLD_DATE),
        ("OTHER", 7_000_000_000, OTHER_DATE),
    ]:
        result = stock_data.get_stock_data(ticker)
        assert result is not None
        assert result["market_cap"] == cap
        assert result["market_cap_source"] == "us_market_caps.json"
        assert result["market_cap_as_of"] == date


@pytest.mark.parametrize("metadata", UNKNOWN_METADATA)
def test_stock_data_emits_null_for_unknown_date(snapshot, fake_yahoo, metadata):
    snapshot(metadata)

    result = stock_data.get_stock_data("OLD")
    assert result is not None
    assert result["market_cap"] == 5_000_000_000
    assert result["market_cap_source"] == "us_market_caps.json"
    assert result["market_cap_as_of"] is None
