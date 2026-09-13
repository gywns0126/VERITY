"""Shared input and bounded read contract for private Nest records (no service key)."""
import json
import math
import re
import time


def read_body(handler):
    try:
        length = int(handler.headers.get("Content-Length", 0) or 0)
        if not 0 < length <= 16384:
            return {}
        value = json.loads(handler.rfile.read(length).decode("utf-8"))
        return value if isinstance(value, dict) else {}
    except (ValueError, TypeError, UnicodeError):
        return {}


def number(value, default=None):
    if isinstance(value, bool):
        return default
    if isinstance(value, str):
        value = re.sub(r"[,\s₩$원]", "", value)
    try:
        value = float(value)
        return value if math.isfinite(value) else default
    except (ValueError, TypeError, OverflowError):
        return default


def asset(body):
    ticker = str(body.get("ticker") or "").strip().upper()
    market = str(body.get("market") or "kr").strip().lower()
    # Direct futures have contract units, not stock shares. Never silently use KRW.
    if market not in ("kr", "us") or ticker.startswith("CMD_"):
        return None
    pattern = r"[0-9A-Z]{6}" if market == "kr" else r"[A-Z][A-Z0-9.\-]{0,14}"
    return (ticker, market) if re.fullmatch(pattern, ticker) else None


def select_all(select, table, params, jwt):
    """Keyset pagination: do not report a truncated 1,000-row portfolio as complete.

    ID is immutable. An extra empty page proves EOF even when the server's own
    max_rows is smaller than requested. Fail explicitly above the bounded budget.
    """
    rows = []
    cursor = None
    deadline = time.monotonic() + 12
    for _ in range(100):
        if time.monotonic() > deadline:
            raise ValueError("Read budget exceeded; refusing partial totals")
        query = dict(params, order="id.asc", limit="1000")
        if cursor:
            query["id"] = "gt." + cursor
        page = select(table, query, user_jwt=jwt)
        if not isinstance(page, list):
            raise ValueError("Invalid database response")
        if not page:
            return rows
        next_cursor = str(page[-1]["id"])
        if cursor and next_cursor <= cursor:
            raise ValueError("Non-progressing pagination")
        rows.extend(page)
        cursor = next_cursor
    raise ValueError("Record read limit exceeded; refusing partial totals")
