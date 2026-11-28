import importlib.util
import json
from pathlib import Path

import pytest

from api.utils.kr_pulse_quote import aware_time, read_listings, valid_kr_quote

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "sanitize_pulse_quotes", ROOT / ".github/actions/publish-data/sanitize_pulse_quotes.py"
)
stage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stage)

LISTED = {"257720": {"market": "KQ"}, "005930": {"market": "KS"}}


def silicon_quote(at):
    return {"source": "yahoo", "symbol": "257720.KQ", "price": 30250, "observed_at": at}


@pytest.mark.parametrize(("observed", "as_of", "valid"), [
    ("2026-11-27T15:30:09+09:00", "2026-11-28T05:03:55+09:00", True),
    ("2026-11-27T15:30:09+09:00", "2026-11-30T08:59:59+09:00", True),
    ("2026-11-27T15:30:09+09:00", "2026-11-30T09:00:01+09:00", False),
    ("2026-11-27T15:29:59+09:00", "2026-11-28T05:03:55+09:00", False),
    ("2026-11-27T10:10:00+09:00", "2026-11-27T10:39:59+09:00", True),
    ("2026-11-27T10:10:00+09:00", "2026-11-27T11:10:00+09:00", False),
    ("2026-11-27T11:10:01+09:00", "2026-11-27T11:10:00+09:00", False),
    ("2026-11-19T15:30:00+09:00", "2026-11-19T17:10:00+09:00", False),
    ("2026-11-19T16:30:05+09:00", "2026-11-19T17:10:00+09:00", True),
    ("2026-11-27T15:30:09", "2026-11-28T05:03:55+09:00", False),
])
def test_validate_session_and_observation(observed, as_of, valid):
    assert valid_kr_quote("257720", 30250, silicon_quote(observed), LISTED, aware_time(as_of)) is valid


def test_independent_public_pulse_withholds_unverified_prices_even_without_portfolio():
    quote = silicon_quote("2026-11-27T15:30:09+09:00")
    raw = {"updated_at": "2026-11-28T05:03:55+09:00",
           "prices": {"257720": 43500, "005930": 179100, "999999": 10, "AAPL": 200},
           "kr_quotes": {"257720": quote}, "counts": {"kr": 3, "kr_requested": 3, "us": 1}}
    stage.sanitize(raw, LISTED, aware_time("2026-11-28T09:00:00+09:00"))
    assert raw["prices"] == {"AAPL": 200}
    assert raw["kr_quotes"] == {}
    assert raw["counts"] == {"kr": 0, "kr_requested": 3, "us": 1}


def test_public_pulse_generation_cannot_claim_later_print():
    quote = silicon_quote("2026-11-27T15:30:09+09:00")
    raw = {"updated_at": "2026-11-27T15:30:00+09:00", "prices": {"257720": 30250},
           "kr_quotes": {"257720": quote}}
    stage.sanitize(raw, LISTED, aware_time("2026-11-28T09:00:00+09:00"))
    assert raw["prices"] == {}


# Legacy pulse prices and independent Nov 26 bars from VERITY-data b4230a44.
# The final two columns are synthetic trade inputs, not live provider observations.
# ticker: (legacy overlay, daily bar, synthetic price, synthetic trade time)
INCIDENT_BATCH = {
    "257720": (43500, 29600, 30150, "2026-11-27T15:30:01+09:00"),
    "145020": (223500, 208000, 209000, "2026-11-27T15:30:02+09:00"),
    "403870": (36300, 37600, 41000, "2026-11-27T15:30:03+09:00"),
}


@pytest.mark.parametrize("with_trade_evidence", [False, True], ids=["legacy", "synthetic-trades"])
def test_nov28_kosdaq_batch_on_both_public_outputs(tmp_path, monkeypatch, with_trade_evidence):
    monkeypatch.syspath_prepend(str(Path(stage.__file__).parent))
    from merge_pulse import main as merge_portfolio

    as_of = aware_time("2026-11-28T23:48:00+09:00")
    listed = read_listings()
    batch = {"updated_at": "2026-11-28T05:03:55+09:00", "prices": {}}
    recommendations = []
    for ticker, (legacy, bar, trade, observed_at) in INCIDENT_BATCH.items():
        assert listed[ticker]["market"] == "KQ"
        recommendations.append({
            "ticker": ticker, "ticker_yf": f"{ticker}.KQ", "currency": "KRW",
            "price": legacy, "current_price": legacy,
            "price_source": "yfinance.history", "price_time_kind": "daily_bar_start",
            "price_bar_date": "2026-11-26", "price_bar_as_of": "2026-11-26T00:00:00+09:00",
            "price_bar_value": bar, "price_adjustment": "auto_adjust",
        })
        batch["prices"][ticker] = trade if with_trade_evidence else legacy
        if with_trade_evidence:
            batch.setdefault("kr_quotes", {})[ticker] = {
                "source": "yahoo", "symbol": f"{ticker}.KQ", "price": trade,
                "observed_at": observed_at,
            }

    portfolio_path = tmp_path / "portfolio.json"
    pulse_path = tmp_path / "price_pulse.json"
    portfolio_path.write_text(json.dumps({"recommendations": recommendations}))
    pulse_path.write_text(json.dumps(batch))
    assert merge_portfolio(portfolio_path, pulse_path, as_of=as_of) == 0
    public_pulse = json.loads(pulse_path.read_text())
    stage.sanitize(public_pulse, listed, as_of)
    rows = {r["ticker"]: r for r in json.loads(portfolio_path.read_text())["recommendations"]}

    assert rows.keys() == INCIDENT_BATCH.keys()
    assert public_pulse["prices"] == (batch["prices"] if with_trade_evidence else {})
    assert public_pulse["kr_quotes"] == batch.get("kr_quotes", {})
    for ticker, (_, bar, trade, observed_at) in INCIDENT_BATCH.items():
        row = rows[ticker]
        assert row["price"] == row["current_price"] == (trade if with_trade_evidence else bar)
        assert row["price_bar_value"] == bar and row["price_bar_date"] == "2026-11-26"
        assert row["price_bar_as_of"] == "2026-11-26T00:00:00+09:00"
        assert row["price_time_kind"] == ("trade" if with_trade_evidence else "daily_bar_start")
        assert row.get("price_as_of") == (observed_at if with_trade_evidence else None)
