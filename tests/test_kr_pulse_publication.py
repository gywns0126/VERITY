import importlib.util
from pathlib import Path

import pytest

from api.utils.kr_pulse_quote import aware_time, valid_kr_quote

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
