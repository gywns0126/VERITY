"""Validate domestic pulse quotes at collection and at publication (stdlib only)."""
from __future__ import annotations

import json
import math
import re
from datetime import date, datetime, time, timedelta, timezone
from functools import lru_cache
from pathlib import Path

from api.utils.market_calendar import is_trading_day, previous_trading_day

KST = timezone(timedelta(hours=9))
DATA = Path(__file__).resolve().parents[2] / "data"


def aware_time(value):
    """A file write time or a timezone-less date cannot identify a trade."""
    if not isinstance(value, str):
        return None
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return timestamp.astimezone(KST) if timestamp.tzinfo is not None else None
    except (ValueError, OverflowError):
        return None


@lru_cache(maxsize=32)
def _session_bounds(day):
    if not (DATA / "calendar" / f"kr_holidays_{day.year}.csv").is_file():
        return None
    if not is_trading_day(day, "KR"):
        return None
    opening, closing = time(9), time(15, 30)
    # KRX's 2026 CSAT session delayed both auctions by one hour.
    if day == date(2026, 11, 19):
        opening, closing = time(10), time(16, 30)
    elif day.month == 1 and day.day <= 7:
        previous = previous_trading_day(day, "KR")
        if previous and previous.year < day.year:
            opening = time(10)
    return datetime.combine(day, opening, KST), datetime.combine(day, closing, KST)


def expected_session(as_of):
    """Return the most recently opened KRX regular session, if covered."""
    if not isinstance(as_of, datetime) or as_of.utcoffset() is None:
        return None
    now = as_of.astimezone(KST)
    if not (DATA / "calendar" / f"kr_holidays_{now.year}.csv").is_file():
        return None
    bounds = _session_bounds(now.date())
    if bounds and now >= bounds[0]:
        return bounds
    previous = previous_trading_day(now.date(), "KR")
    return _session_bounds(previous) if previous else None


def valid_kr_quote(ticker, price, quote, listed, as_of):
    if not isinstance(quote, dict) or not isinstance(listed, dict):
        return False
    listing = listed.get(ticker)
    market = listing.get("market") if isinstance(listing, dict) else None
    if not isinstance(ticker, str) or not re.fullmatch(r"[0-9][A-Z0-9]{5}", ticker):
        return False
    if market not in ("KS", "KQ") or quote.get("symbol") != f"{ticker}.{market}":
        return False
    if quote.get("source") not in ("kis", "yahoo"):
        return False
    bound_price = quote.get("price")
    if type(price) not in (int, float) or type(bound_price) not in (int, float):
        return False
    if price != bound_price or not math.isfinite(price) or price <= 0:
        return False
    observed = aware_time(quote.get("observed_at"))
    bounds = expected_session(as_of)
    if not bounds or observed is None or observed > as_of:
        return False
    opening, closing = bounds
    # Yahoo reports a closing print with seconds, KIS minute bars with HHMM00.
    if not opening <= observed < closing + timedelta(minutes=1):
        return False
    if as_of >= closing:
        return observed >= closing
    return as_of - observed <= timedelta(minutes=30)


def read_listings():
    """Missing or invalid registry data leaves domestic quotes unverified."""
    try:
        records = json.loads((DATA / "kr_listed.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return records if isinstance(records, dict) else {}


def publishable_quotes(pulse, listed, now):
    prices = pulse.get("prices")
    quotes = pulse.get("kr_quotes")
    generated = aware_time(pulse.get("updated_at"))
    if not isinstance(prices, dict) or not isinstance(quotes, dict) or not generated or generated > now:
        return {}
    return {
        ticker: quote for ticker, quote in quotes.items()
        if valid_kr_quote(ticker, prices.get(ticker), quote, listed, now)
        and aware_time(quote["observed_at"]) <= generated
    }
