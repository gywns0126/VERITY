"""Public KR prices must be source-bound and monotonic across staged generations."""
import importlib.util
import json
from datetime import datetime
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "merge_pulse", ROOT / ".github/actions/publish-data/merge_pulse.py"
)
MERGE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MERGE)
NOW = datetime.fromisoformat("2026-11-27T11:10:00+09:00")
CODE = "257720"


def daily_bar():
    return {
        "ticker": CODE, "ticker_yf": CODE + ".KQ", "currency": "KRW",
        "price": 29600, "current_price": 29600, "price_bar_value": 29600,
        "price_bar_date": "2026-11-26", "price_bar_as_of": "2026-11-26T00:00:00+09:00",
        "price_source": "yfinance.history", "price_time_kind": "daily_bar_start",
        "price_adjustment": "auto_adjust",
    }


def pulse(at="2026-11-27T11:05:00+09:00"):
    return {
        "updated_at": NOW.isoformat(), "prices": {CODE: 30250},
        "kr_quotes": {CODE: {
            "price": 30250, "symbol": CODE + ".KQ", "source": "yahoo", "observed_at": at,
        }},
    }


def merge(tmp_path, portfolio, batch):
    src = tmp_path / "portfolio.json"
    incoming = tmp_path / "price_pulse.json"
    src.write_text(json.dumps(portfolio))
    incoming.write_text(json.dumps(batch))
    assert MERGE.main(src, incoming, as_of=NOW) == 0
    return json.loads(src.read_text())


def test_verified_price_keeps_own_trade_time_and_original_bar(tmp_path):
    out = merge(tmp_path, {"recommendations": [daily_bar()]}, pulse())
    row = out["recommendations"][0]
    assert row["price"] == row["current_price"] == 30250
    assert row["price_as_of"] == "2026-11-27T11:05:00+09:00"
    assert row["price_time_kind"] == "trade"
    assert row["price_bar_source"] == "yfinance.history"
    assert row["price_bar_adjustment"] == "auto_adjust"
    assert row["price_bar_date"] == "2026-11-26" and row["price_bar_value"] == 29600


@pytest.mark.parametrize("failure", ["missing", "wrong_board", "old", "price_mismatch", "post_batch"])
def test_unverified_quotes_preserve_recommendations_and_staged_holdings(tmp_path, failure):
    batch = pulse()
    quote = batch["kr_quotes"][CODE]
    if failure == "missing":
        batch.pop("kr_quotes")
    elif failure == "wrong_board":
        quote["symbol"] = CODE + ".KS"
    elif failure == "old":
        quote["observed_at"] = "2026-11-26T11:05:00+09:00"
    elif failure == "price_mismatch":
        batch["prices"][CODE] = 43500
    elif failure == "post_batch":
        batch["updated_at"] = "2026-11-27T11:04:00+09:00"

    holding = {"ticker": CODE, "current_price": 29600, "buy_price": 24000}
    out = merge(tmp_path, {"recommendations": [daily_bar()], "vams": {"holdings": [holding]}}, batch)
    assert out["price_pulse_meta"]["counts"]["kr"] == 0
    assert out["recommendations"] == [daily_bar()]
    assert out["vams"]["holdings"] == [holding]


@pytest.mark.parametrize("bar_present", [True, False])
def test_previously_contaminated_overlay_recovers_only_identified_bar(tmp_path, bar_present):
    row = daily_bar() if bar_present else {"ticker": CODE}
    row.update(price=43500, current_price=43500)
    contaminated = {"price_pulse_meta": {"updated_at": NOW.isoformat()}, "recommendations": [row]}
    batch = {"updated_at": NOW.isoformat(), "prices": {CODE: 43500}}
    result = merge(tmp_path, contaminated, batch)["recommendations"][0]
    assert result["price"] == result["current_price"] == (29600 if bar_present else None)


def test_older_generation_preserves_existing_public_bundle(tmp_path):
    previous = {"updated_at": "2026-11-27T11:09:00+09:00", "counts": {"kr": 3}}
    portfolio = {"recommendations": [daily_bar()], "price_pulse_meta": previous}
    batch = pulse()
    batch.update(updated_at="2026-11-27T11:08:00+09:00", indices={"kospi": {"value": 1}})
    assert merge(tmp_path, portfolio, batch) == portfolio


@pytest.mark.parametrize("quote_time", ["2026-11-27T11:05:00+09:00", "2026-11-27T11:06:00+09:00"])
def test_newer_batch_cannot_replay_equal_or_older_observation(tmp_path, quote_time):
    row = dict(daily_bar(), price=31000, current_price=31000, price_as_of="2026-11-27T11:06:00+09:00")
    assert merge(tmp_path, {"recommendations": [row]}, pulse(quote_time))["recommendations"] == [row]


def test_sanitized_public_row_recovers_identified_bar_without_bundle_metadata(tmp_path):
    row = dict(daily_bar(), price=43500, current_price=43500)
    batch = {"updated_at": NOW.isoformat(), "prices": {CODE: 43500}}
    result = merge(tmp_path, {"recommendations": [row]}, batch)["recommendations"][0]
    assert result["price"] == result["current_price"] == result["price_bar_value"] == 29600
    assert result["price_bar_date"] == row["price_bar_date"]
