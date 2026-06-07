"""US market_cap fallback (aed82498) — yfinance marketCap 누락 시 shares×price."""
from api.collectors.stock_data import _market_cap_or_fallback


def test_fallback_when_marketcap_missing():
    # marketCap 누락 → shares × price
    assert _market_cap_or_fallback(0, 1_000_000_000, 100.0) == 100_000_000_000
    assert _market_cap_or_fallback(None, 500_000_000, 41.1) == int(500_000_000 * 41.1)


def test_uses_marketcap_when_present():
    assert _market_cap_or_fallback(175_000_000_000, 1, 1) == 175_000_000_000


def test_zero_when_no_data():
    assert _market_cap_or_fallback(0, None, 100) == 0
    assert _market_cap_or_fallback(0, 1_000_000, 0) == 0
    assert _market_cap_or_fallback(None, None, None) == 0
