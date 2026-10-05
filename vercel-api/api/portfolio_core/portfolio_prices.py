"""Pure public closing-price boundary for portfolio analysis.

The module performs no IO.  It recognizes only exact, reviewed producer
contracts and never accepts a caller-provided permission flag.  A recognized
source can expose values only when its code-owned policy allows this product
projection and the producer supplies a validated completed-session date.
Restricted sources are represented without copying price values.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timezone
import math
import re
from types import MappingProxyType
from typing import Any, Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


SCHEMA = "alphaconsole-portfolio-prices-v1"
RIGHTS_CHECKED_AT = "2026-10-02"

KR_CLOSE_FILE = "kr_close_latest.json"
KR_CHART_FILES = tuple(f"kr_chart_daily/chunk_{index:02d}.json" for index in range(40))
US_HISTORY_PATTERN = "us_chart_history/{ticker}.json"
PUBLIC_PRICE_FILES = (KR_CLOSE_FILE, *KR_CHART_FILES, US_HISTORY_PATTERN)

_KR_SOURCE = "금융위원회_주식시세정보 (data.go.kr/data/15094808)"
_KR_LEGACY_SOURCE_LABEL = _KR_SOURCE + " · 이용허락범위 제한 없음"
_KR_BASIS_PREFIX = "직전 거래일 종가 (T+1). 실시간 아님"
_US_SOURCE = "yfinance period=max auto_adjust=True"

# Rights are code-owned review results, not artifact claims or caller options.
# Policies describe this product's reviewed use, not provider-wide legal rights.
# Artifact metadata and caller options cannot promote a source into this set.
SOURCE_POLICIES = MappingProxyType({
    "fsc-kr-daily-price": MappingProxyType({
        "market": "KR",
        "source_name": _KR_SOURCE,
        "basis_prefix": _KR_BASIS_PREFIX,
        "rights_status": "existing-public-display",
        "checked_at": "2026-10-05",
        "rights_reference": "https://www.data.go.kr/data/15094808/openapi.do",
        "rights_reason": (
            "Reuses the product's existing public previous-close display path; "
            "this is not a provider-wide rights determination."
        ),
        "requirements": (
            "existing-public-display-contract",
            "validated-completed-session-date",
        ),
    }),
    "yahoo-us-adjusted-history": MappingProxyType({
        "market": "US",
        "source_name": _US_SOURCE,
        "rights_status": "restricted",
        "rights_reference": "https://help.yahoo.com/kb/finance/article-exchanges-data-delays-sln2310.html",
        "rights_reason": (
            "Yahoo Finance states that its information must not be redistributed; "
            "no express public-display permission is recorded."
        ),
        "requirements": (
            "express-public-display-rights",
            "producer-explicit-currency",
            "producer-completed-session-date",
        ),
    }),
})

_TICKER = {
    "KR": re.compile(r"[0-9]{6}\Z", re.ASCII),
    "US": re.compile(r"[A-Z][A-Z0-9]{0,9}(?:[.-][A-Z0-9]{1,2})?\Z", re.ASCII),
}
_CURRENCY = re.compile(r"[A-Z]{3}\Z", re.ASCII)


def _requests(positions: Any) -> list[dict[str, str]]:
    if type(positions) is not list:
        raise ValueError("invalid-price-request")
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in positions:
        if type(item) is not dict or set(item) != {"ticker", "market"}:
            raise ValueError("identifier-only-price-request-required")
        ticker, market = item["ticker"], item["market"]
        if (
            type(ticker) is not str
            or type(market) is not str
            or market not in _TICKER
            or not _TICKER[market].fullmatch(ticker)
        ):
            raise ValueError("invalid-security-identifier")
        identifier = f"{market}:{ticker}"
        if identifier not in seen:
            result.append({"id": identifier, "ticker": ticker, "market": market})
            seen.add(identifier)
    return result


def _iso_date(value: Any) -> str | None:
    if isinstance(value, int):
        raw = str(value)
    elif isinstance(value, str):
        raw = value.strip()
    else:
        return None
    if re.fullmatch(r"[0-9]{8}", raw):
        raw = f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"
    try:
        return date.fromisoformat(raw).isoformat()
    except ValueError:
        return None


def _iso_timestamp(value: Any) -> str | None:
    if type(value) is not str:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.isoformat(timespec="seconds")


def _exchange_timezone(value: Any) -> ZoneInfo | None:
    if type(value) is not str or not 1 <= len(value) <= 64:
        return None
    try:
        return ZoneInfo(value)
    except (ValueError, ZoneInfoNotFoundError):
        return None


def _finite_positive(value: Any) -> float | int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value) or value <= 0:
        return None
    return value


def _currency(meta: Mapping[str, Any]) -> str | None:
    value = meta.get("currency")
    if type(value) is str and _CURRENCY.fullmatch(value):
        return value
    return None


def _kr_currency(meta: Mapping[str, Any]) -> str | None:
    """The FSC document contract is KRW; an explicit conflict fails closed."""
    if "currency" not in meta:
        return "KRW"
    return "KRW" if meta.get("currency") == "KRW" else None


def _rights(policy: Mapping[str, Any]) -> dict[str, str]:
    return {
        "status": str(policy["rights_status"]),
        "checked_at": policy.get("checked_at", RIGHTS_CHECKED_AT),
        "reference": str(policy["rights_reference"]),
        "reason": str(policy["rights_reason"]),
    }


def _missing(request: Mapping[str, str], reason: str) -> dict[str, Any]:
    return {
        **request,
        "status": "missing",
        "close_date": None,
        "currency": None,
        "close": None,
        "source": None,
        "rights": {"status": "not-evaluated", "reason": reason},
    }


def _restricted(
    request: Mapping[str, str], policy_id: str, source_file: str
) -> dict[str, Any]:
    policy = SOURCE_POLICIES[policy_id]
    return {
        **request,
        "status": "restricted",
        "close_date": None,
        "currency": None,
        "close": None,
        "source": {
            "id": policy_id,
            "name": policy["source_name"],
            "file": source_file,
        },
        "rights": _rights(policy),
        "requirements": list(policy["requirements"]),
    }


def _validated_ohlc(row: Any, close_date: str, close: float | int) -> dict[str, float | int] | None:
    # FSC and the existing US history producer both emit [date, O, H, L, C, volume].
    if type(row) is not list or len(row) != 6 or _iso_date(row[0]) != close_date:
        return None
    open_, high, low, row_close = (_finite_positive(value) for value in row[1:5])
    if None in (open_, high, low, row_close) or row_close != close:
        return None
    if high < max(open_, close) or low > min(open_, close) or high < low:
        return None
    return {"open": open_, "high": high, "low": low, "close": row_close}


def _available(
    request: Mapping[str, str],
    *,
    policy_id: str,
    source_file: str,
    close_date: Any,
    currency: Any,
    close: Any,
    ohlc_row: Any = None,
    observed_at: Any = None,
) -> dict[str, Any] | None:
    """Validate the permitted projection; callers cannot select the policy."""
    policy = SOURCE_POLICIES[policy_id]
    if policy["rights_status"] not in ("permitted", "existing-public-display"):
        return None
    normalized_date = _iso_date(close_date)
    normalized_close = _finite_positive(close)
    if (
        normalized_date is None
        or type(currency) is not str
        or not _CURRENCY.fullmatch(currency)
        or normalized_close is None
    ):
        return None
    quote = {
        **request,
        "status": "available",
        "close_date": normalized_date,
        "currency": currency,
        "close": normalized_close,
        "source": {
            "id": policy_id,
            "name": policy["source_name"],
            "file": source_file,
        },
        "rights": _rights(policy),
    }
    normalized_observed_at = _iso_timestamp(observed_at)
    if normalized_observed_at is not None:
        quote["observed_at"] = normalized_observed_at
    ohlc = _validated_ohlc(ohlc_row, normalized_date, normalized_close)
    if ohlc is not None:
        quote["ohlc"] = ohlc
    return quote


def _kr_quote(
    request: Mapping[str, str], close_document: Any, chart_documents: Mapping[str, Any]
) -> dict[str, Any]:
    if type(close_document) is not dict:
        return _missing(request, "kr-close-document-not-supplied")
    meta = close_document.get("_meta")
    prices = close_document.get("prices")
    if type(meta) is not dict or type(prices) is not dict or request["ticker"] not in prices:
        return _missing(request, "ticker-not-in-kr-close-document")
    policy = SOURCE_POLICIES["fsc-kr-daily-price"]
    normalized_date = _iso_date(meta.get("as_of"))
    normalized_generated_at = _iso_timestamp(meta.get("generated_at"))
    if (
        meta.get("source") not in (policy["source_name"], _KR_LEGACY_SOURCE_LABEL)
        or type(meta.get("basis")) is not str
        or not meta["basis"].startswith(policy["basis_prefix"])
        or normalized_date is None
        or normalized_generated_at is None
    ):
        return _missing(request, "unrecognized-or-unvalidated-kr-source-contract")
    observed = datetime.fromisoformat(normalized_generated_at)
    now = datetime.now(timezone.utc)
    close_day = date.fromisoformat(normalized_date)
    kst = ZoneInfo("Asia/Seoul")
    if observed > now:
        return _missing(request, "kr-collection-timestamp-is-future")
    if close_day >= observed.astimezone(kst).date() or close_day >= now.astimezone(kst).date():
        return _missing(request, "kr-close-is-not-completed-prior-day")
    currency = _kr_currency(meta)
    if currency is None:
        return _missing(request, "kr-currency-conflicts-with-producer-contract")
    if policy["rights_status"] not in ("permitted", "existing-public-display"):
        return _restricted(request, "fsc-kr-daily-price", KR_CLOSE_FILE)

    ohlc_row = None
    chunk_index = int(request["ticker"], 36) % len(KR_CHART_FILES)
    filename = KR_CHART_FILES[chunk_index]
    chunk = chart_documents.get(filename)
    stocks = chunk.get("stocks") if type(chunk) is dict else None
    stock = stocks.get(request["ticker"]) if type(stocks) is dict else None
    candles = stock.get("c") if type(stock) is dict else None
    if type(candles) is list and candles:
        candidate = candles[-1]
        if (type(candidate) is list and len(candidate) == 6
                and _iso_date(candidate[0]) == _iso_date(meta["as_of"])):
            ohlc_row = candidate
    quote = _available(
        request,
        policy_id="fsc-kr-daily-price",
        source_file=KR_CLOSE_FILE,
        close_date=normalized_date,
        currency=currency,
        close=prices[request["ticker"]],
        ohlc_row=ohlc_row,
        observed_at=meta.get("generated_at"),
    )
    if quote is None:
        return _missing(request, "approved-kr-record-failed-validation")

    previous = close_document.get("prev")
    changes = close_document.get("chg")
    previous_date = _iso_date(meta.get("prev_as_of"))
    previous_close = (
        _finite_positive(previous.get(request["ticker"]))
        if type(previous) is dict else None
    )
    source_change_pct = (
        changes.get(request["ticker"]) if type(changes) is dict else None
    )
    if (
        previous_date is not None
        and previous_date < normalized_date
        and previous_close is not None
        and not isinstance(source_change_pct, bool)
        and isinstance(source_change_pct, (int, float))
        and math.isfinite(source_change_pct)
    ):
        # FSC ``chg`` prefers source fltRt, which remains meaningful across
        # split-adjusted sessions even when the raw close ratio differs.
        quote["prev_as_of"] = previous_date
        quote["previous_close"] = previous_close
        quote["change_pct"] = round(float(source_change_pct), 2)
    return quote


def _us_quote(
    request: Mapping[str, str], history_meta: Any, history_documents: Mapping[str, Any]
) -> dict[str, Any]:
    filename = US_HISTORY_PATTERN.format(ticker=request["ticker"])
    document = history_documents.get(filename)
    if type(document) is not dict:
        return _missing(request, "us-history-document-not-supplied")
    per_file_metadata = "_meta" in document
    if not per_file_metadata and type(history_meta) is not dict:
        return _missing(request, "us-history-document-not-supplied")
    rows = document.get("c")
    if document.get("t") != request["ticker"] or type(rows) is not list or not rows:
        return _missing(request, "ticker-not-in-valid-us-history-document")
    if per_file_metadata:
        dated_rows = [row for row in rows if type(row) is list and row
                      and _iso_date(row[0]) is not None]
        if not dated_rows:
            return _missing(request, "us-history-has-no-valid-daily-row")
    else:
        # Preserve the legacy root-metadata contract; new validation is scoped
        # to producer-declared per-file metadata, not existing chart consumers.
        last = rows[-1]
        if type(last) is not list or len(last) < 5 or _iso_date(last[0]) is None:
            return _missing(request, "us-last-completed-date-invalid")
    selected_meta = document.get("_meta") if per_file_metadata else history_meta
    if type(selected_meta) is not dict:
        return _missing(request, "us-history-metadata-not-supplied")
    policy = SOURCE_POLICIES["yahoo-us-adjusted-history"]
    if selected_meta.get("source") != policy["source_name"]:
        return _missing(request, "unrecognized-us-source-contract")
    if policy["rights_status"] != "permitted":
        return _restricted(request, "yahoo-us-adjusted-history", filename)
    completed_date = _iso_date(selected_meta.get("close_date"))
    if (
        selected_meta.get("basis") != "last-completed-session-close"
        or completed_date is None
    ):
        return _missing(request, "us-completed-session-assertion-not-supplied")
    if per_file_metadata:
        exchange_zone = _exchange_timezone(selected_meta.get("exchangeTimezoneName"))
        observed_at = _iso_timestamp(selected_meta.get("observed_at"))
        if exchange_zone is None or observed_at is None:
            return _missing(request, "us-per-file-observation-metadata-invalid")
        observed = datetime.fromisoformat(observed_at)
        if observed > datetime.now(timezone.utc):
            return _missing(request, "us-per-file-observation-is-future")
        local_today = observed.astimezone(exchange_zone).date()
        if date.fromisoformat(completed_date) >= local_today:
            return _missing(request, "us-completed-session-is-not-prior-day")
        matches = [row for row in rows if isinstance(row, (list, tuple)) and row
                   and _iso_date(row[0]) == completed_date]
        if len(matches) != 1:
            return _missing(request, "us-completed-session-row-not-unique")
        completed_row = matches[0]
        if type(completed_row) is not list or len(completed_row) != 6:
            return _missing(request, "us-completed-session-row-invalid")
        valid_prior_dates = [
            row_date for row in dated_rows
            if len(row) == 6 and (row_date := _iso_date(row[0])) is not None
            and date.fromisoformat(row_date) < local_today
            and _validated_ohlc(row, row_date, row[4]) is not None
        ]
        if not valid_prior_dates or max(valid_prior_dates) != completed_date:
            return _missing(request, "us-completed-session-is-not-latest-valid-row")
    else:
        if completed_date != _iso_date(last[0]):
            return _missing(request, "us-completed-session-assertion-not-supplied")
        completed_row, observed_at = last, None
    quote = _available(
        request,
        policy_id="yahoo-us-adjusted-history",
        source_file=filename,
        close_date=completed_date,
        currency=_currency(selected_meta),
        close=completed_row[4],
        ohlc_row=completed_row,
        observed_at=observed_at,
    )
    return quote or _missing(request, "permitted-us-record-failed-validation")


def project_portfolio_prices(
    positions: Any,
    *,
    kr_close: Any = None,
    kr_charts: Mapping[str, Any] | None = None,
    us_history_meta: Any = None,
    us_history: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Project requested identifiers from supplied public EOD documents only."""
    requested = _requests(positions)
    chart_documents = kr_charts if type(kr_charts) is dict else {}
    history_documents = us_history if type(us_history) is dict else {}
    quotes = [
        _kr_quote(item, kr_close, chart_documents)
        if item["market"] == "KR"
        else _us_quote(item, us_history_meta, history_documents)
        for item in requested
    ]
    counts = {status: sum(row["status"] == status for row in quotes)
              for status in ("available", "restricted", "missing")}
    return {
        "schema": SCHEMA,
        "quotes": deepcopy(quotes),
        "coverage": {"requested": len(requested), **counts},
        "_meta": {
            "basis": "last-completed-session-close-only",
            "realtime": False,
            "network_io": False,
            "private_sources_used": False,
            "rights_checked_at": RIGHTS_CHECKED_AT,
        },
    }


__all__ = (
    "KR_CHART_FILES",
    "KR_CLOSE_FILE",
    "PUBLIC_PRICE_FILES",
    "RIGHTS_CHECKED_AT",
    "SCHEMA",
    "SOURCE_POLICIES",
    "US_HISTORY_PATTERN",
    "project_portfolio_prices",
)
