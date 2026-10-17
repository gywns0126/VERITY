"""Observation periods and successful fetch clocks are separate contracts."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import re

_KST = timezone(timedelta(hours=9))
_META_KEYS = (
    "source", "source_as_of", "source_date_status", "source_period_kind",
    "fetched_at", "last_successful_at", "stale", "reused", "as_of", "as_of_kind",
)


def now_iso() -> str:
    return datetime.now(_KST).isoformat(timespec="seconds")


def observation_meta(source: str, source_date, *, fetched_at: str | None = None) -> dict:
    """Stamp a returned value without inventing a missing observation period.

    ECOS monthly YYYYMM stays a month, not an invented first-of-month day.
    A successful value fetch can still have an unknown or invalid source date.
    """
    stamp = fetched_at or now_iso()
    today = datetime.fromisoformat(stamp).astimezone(_KST).date()
    period = None
    kind = "day"
    raw = str(source_date) if source_date is not None else ""
    try:
        if re.fullmatch(r"\d{6}|\d{4}-\d{2}", raw):
            digits = raw.replace("-", "")
            month = date(int(digits[:4]), int(digits[4:]), 1)
            kind = "month"
            if (month.year, month.month) <= (today.year, today.month):
                period = month.strftime("%Y-%m")
        elif re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
            day = date.fromisoformat(raw)
            if day <= today:
                period = day.isoformat()
    except ValueError:
        pass
    return {
        "source": source, "source_as_of": period, "source_period_kind": kind,
        "source_date_status": "ok" if period else "missing" if source_date is None else "invalid",
        "fetched_at": stamp, "last_successful_at": stamp,
        "stale": period is None, "reused": False,
    }


def copy_meta(row: dict) -> dict:
    """Aliases inherit the source receipt; copying is not another fetch."""
    return {key: row[key] for key in _META_KEYS if key in row}


def derived_meta(*rows: dict) -> dict:
    """A composite is no newer than its oldest input; mixed dates stay explicit."""
    def oldest(key):
        try:
            values = [row[key] for row in rows]
            parsed = [datetime.fromisoformat(value) for value in values]
            if not parsed or any(value.tzinfo is None for value in parsed):
                return None
            return values[min(range(len(values)), key=lambda i: parsed[i])]
        except (KeyError, TypeError, ValueError):
            return None

    periods = [row.get("source_as_of") for row in rows]
    same_period = bool(periods) and all(p == periods[0] and p for p in periods)
    fetched = oldest("fetched_at")
    successful = oldest("last_successful_at")
    stale = not same_period or successful is None or any(row.get("stale", True) for row in rows)
    return {
        "source": "derived", "source_as_of": periods[0] if same_period else None,
        "source_date_status": "ok" if same_period else "mixed" if all(periods) else "missing",
        "source_period_kind": rows[0].get("source_period_kind", "day") if same_period else None,
        "fetched_at": fetched, "last_successful_at": successful,
        "stale": stale, "reused": any(row.get("reused", False) for row in rows),
    }
