"""Selected public change-center comparisons; no scores, collector or member cache.

project_public_changes accepts the producer's {"stocks": ...} document and is
IO/clock free. Dates describe collection snapshots, not trading sessions or
freshness. Business comparisons describe retained excerpts, not complete filings.
Only the transport helpers read data; they never persist requests or responses.
"""
from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import date, datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import threading
import time

from .portfolio_public_fetch import _read_public_document, _unique_object


PUBLIC_CHANGE_BASE_URL = "https://raw.githubusercontent.com/gywns0126/VERITY-data/main/stock_change_public/"
MAX_PREFIXES = 20
MAX_SHARD_BYTES = 4 * 1024 * 1024
FETCH_TIMEOUT_SECONDS = 3
FETCH_BUDGET_SECONDS = 3
_FIELDS = {
    "price": "가격", "market_cap": "시가총액", "pbr": "PBR", "eps": "EPS",
    "roe": "ROE", "debt_ratio": "부채비율", "operating_margin": "영업이익률",
    "revenue_growth": "매출성장률", "shares_outstanding": "발행주식수",
}
_SAFE_NUMBER = 2**53 - 1
_REPORT_KEYS = ("fiscal_year", "filed_at", "report", "text", "truncated", "url", "hash")


def _selection(positions):
    # Reuse the engine's identifier-only contract without an import cycle.
    from .portfolio_engine import validate_positions

    requested = validate_positions(positions)
    tickers = sorted(p["ticker"] for p in requested if p["market"] == "KR")
    prefixes = sorted({ticker[:3] for ticker in tickers})
    if len(prefixes) > MAX_PREFIXES:
        raise ValueError("public-change-prefix-limit")
    return requested, tickers, prefixes


def _day(value):
    if type(value) is not str or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _number(value):
    return (type(value) in (int, float) and abs(value) <= _SAFE_NUMBER
            and math.isfinite(value))


def _today(raw, url, counts, reasons, cutoff):
    if type(raw) is not dict or type(raw.get("fields")) is not list:
        reasons["invalid_today"] += 1
        return None
    fields = raw["fields"]
    counts["input"] += len(fields)
    current, previous = _day(raw.get("as_of")), _day(raw.get("previous_as_of"))
    status = raw.get("status")
    if status == "insufficient_history":
        reasons["insufficient_history"] += 1
        counts["rejected"] += len(fields)
        return None
    if (not current or not previous or previous >= current or current > cutoff
            or status not in ("changed", "unchanged")
            or (status == "unchanged" and fields) or (status == "changed" and not fields)
            or len(fields) > 10):
        reasons["invalid_comparison"] += 1
        counts["rejected"] += len(fields)
        return None
    keys = Counter(f.get("key") for f in fields
                   if type(f) is dict and type(f.get("key")) is str)
    accepted = []
    for field in fields:
        reason = None
        if type(field) is not dict or type(field.get("key")) is not str:
            reason = "invalid_field"
        else:
            key = field["key"]
            if key == "per":
                reason = "per_basis_unverified"
            elif key not in _FIELDS:
                reason = "unsupported_field"
            elif keys[key] != 1:
                reason = "duplicate_field"
            elif not all(_number(field.get(k)) for k in ("before", "after", "delta")):
                reason = "invalid_number"
            else:
                before, after = field["before"], field["after"]
                if key in ("price", "market_cap", "shares_outstanding") and min(before, after) < 0:
                    reason = "invalid_number"
                elif key == "shares_outstanding" and (before % 1 or after % 1):
                    reason = "invalid_number"
                elif math.isclose(before, after, rel_tol=1e-12, abs_tol=1e-12):
                    reason = "unchanged_field"
                elif not math.isclose(field["delta"], round(after - before, 6),
                                      rel_tol=0, abs_tol=1e-9):
                    reason = "delta_mismatch"
                elif "delta_pct" not in field:
                    reason = "missing_delta_pct"
                elif before == 0:
                    if field["delta_pct"] is not None:
                        reason = "delta_pct_mismatch"
                elif (not _number(field["delta_pct"])
                      or not math.isclose(field["delta_pct"],
                                          round((after - before) / abs(before) * 100, 2),
                                          rel_tol=0, abs_tol=1e-9)):
                    reason = "delta_pct_mismatch"
        if reason:
            reasons[reason] += 1
            counts["rejected"] += 1
        else:
            accepted.append({k: field[k] for k in ("key", "before", "after", "delta", "delta_pct")})
            accepted[-1]["label"] = _FIELDS[field["key"]]
            counts["accepted"] += 1
    counts["pairs"] += 1
    projected_status = status
    if len(accepted) != len(fields):
        projected_status = "partial" if accepted else "unavailable"
    return {
        "status": projected_status, "source_status": status,
        "as_of": raw["as_of"], "previous_as_of": raw["previous_as_of"],
        "date_basis": "collection_date", "source_url": url, "fields": accepted,
    }


def _report(raw, cutoff):
    if type(raw) is not dict or any(k not in raw for k in _REPORT_KEYS):
        return None
    if any(type(raw[k]) is not str for k in _REPORT_KEYS if k != "truncated"):
        return None
    if (type(raw["truncated"]) is not bool or not 0 < len(raw["text"]) <= 40000
            or not 0 < len(raw["report"]) <= 200
            or not re.fullmatch(r"(?:19|20|21)[0-9]{2}", raw["fiscal_year"])
            or re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", raw["text"] + raw["report"])):
        return None
    filed = raw["filed_at"]
    if re.fullmatch(r"[0-9]{8}", filed):
        filed = f"{filed[:4]}-{filed[4:6]}-{filed[6:]}"
    parsed = _day(filed)
    match = re.fullmatch(r"https://dart\.fss\.or\.kr/dsaf001/main\.do\?rcpNo=([0-9]{14})", raw["url"])
    if (not parsed or parsed > cutoff or int(raw["fiscal_year"]) > parsed.year
            or not match or match[1][:8] != filed.replace("-", "")):
        return None
    compact = re.sub(r"\s+", " ", raw["text"]).strip()
    if not compact or hashlib.sha256(compact.encode("utf-8")).hexdigest() != raw["hash"]:
        return None
    return {k: raw[k] for k in _REPORT_KEYS}


def _business(raw, url, counts, reasons, cutoff):
    counts["input"] += 1
    if type(raw) is not dict or raw.get("status") not in ("changed", "unchanged"):
        counts["rejected"] += 1
        reasons["missing_comparison"] += 1
        return None
    current, previous = _report(raw.get("current"), cutoff), _report(raw.get("previous"), cutoff)
    if current is None or previous is None:
        counts["rejected"] += 1
        reasons["invalid_original_pair"] += 1
        return None
    if previous["filed_at"].replace("-", "") > current["filed_at"].replace("-", ""):
        counts["rejected"] += 1
        reasons["reversed_filing_dates"] += 1
        return None
    def sentences(text):
        return [s.strip() for s in re.split(r"(?<=[.!?다요])\s+", re.sub(r"\s+", " ", text).strip())
                if len(s.strip()) >= 12]
    current_sent, previous_sent = sentences(current["text"]), sentences(previous["text"])
    added = [s for s in current_sent if s not in set(previous_sent)][:5]
    removed = [s for s in previous_sent if s not in set(current_sent)][:5]
    status = "changed" if current["hash"] != previous["hash"] else "unchanged"
    if raw["status"] != status or raw.get("added") != added or raw.get("removed") != removed:
        counts["rejected"] += 1
        reasons["text_delta_mismatch"] += 1
        return None
    counts["accepted"] += 1
    return {"status": status, "source_url": url, "current": current, "previous": previous,
            "added": added, "removed": removed}


def project_public_changes(payload, positions, *, as_of):
    """Project only selected KR records from one or merged public shard stocks.

    No missing comparison becomes an unchanged fact. Coverage counts numeric
    input fields, complete business pairs and selected stock records separately.
    Unknown fields (including labels, names, disclosures and private extras)
    never pass through. source_url is code-owned, not taken from the payload.
    as_of is a required injected ISO date, used only to reject future dates.
    """
    cutoff = _day(as_of)
    if cutoff is None:
        raise ValueError("invalid-change-as-of")
    requested, tickers, _ = _selection(positions)
    raw_stocks = payload.get("stocks") if type(payload) is dict else None
    valid_shape = type(raw_stocks) is dict
    raw_stocks = raw_stocks if valid_shape else {}
    stocks, missing, rejected = {}, [], []
    daily = Counter(input=0, accepted=0, rejected=0, pairs=0)
    business = Counter(input=0, accepted=0, rejected=0)
    daily_reasons, business_reasons = Counter(), Counter()
    for ticker in tickers:
        if ticker not in raw_stocks:
            missing.append(ticker)
            continue
        row = raw_stocks[ticker]
        if (type(row) is not dict or row.get("ticker") != ticker
                or row.get("market") not in ("KR", "KOSPI", "KOSDAQ", "KONEX")):
            rejected.append(ticker)
            continue
        url = PUBLIC_CHANGE_BASE_URL + ticker[:3] + ".json"
        stocks[ticker] = {
            "ticker": ticker, "market": "KR", "source_url": url,
            "today": _today(row.get("today"), url, daily, daily_reasons, cutoff),
            "business_report": _business(row.get("business_report"), url, business, business_reasons, cutoff),
        }
    supported = len(tickers)
    available = sum(bool((r["today"] and r["today"]["status"] in ("changed", "unchanged", "partial"))
                         or r["business_report"]) for r in stocks.values())
    complete = (supported and len(stocks) == supported and daily["pairs"] == supported
                and not daily["rejected"] and business["accepted"] == supported)
    coverage = {
        "status": "complete" if complete else "partial" if available else "unavailable",
        "requested": len(requested), "eligible": supported, "matched": len(stocks),
        "available": available, "missing": missing, "rejected": rejected,
        "unsupported": [p["id"] for p in requested if p["market"] != "KR"],
        "shape_errors": int(not valid_shape),
        "today": {**daily, "rejection_reasons": dict(sorted(daily_reasons.items()))},
        "business_report": {**business, "rejection_reasons": dict(sorted(business_reasons.items()))},
    }
    return {"stocks": stocks, "coverage": coverage}


def validate_public_change_projection(projection, positions, *, as_of):
    """Validate the closed projected contract at an engine trust boundary.

    Unlike the raw projector, unknown projected keys are rejected. Return a new
    allowlisted copy, including partial/source_status and original denominators.
    """
    from copy import deepcopy

    def require(condition):
        if not condition:
            raise ValueError("invalid-public-change-projection")

    def count(value):
        return type(value) is int and 0 <= value <= _SAFE_NUMBER

    cutoff = _day(as_of)
    require(cutoff is not None)
    requested, tickers, prefixes = _selection(positions)
    require(type(projection) is dict and set(projection) == {"stocks", "coverage"})
    stocks, coverage = projection["stocks"], projection["coverage"]
    require(type(stocks) is dict and set(stocks) <= set(tickers))
    for ticker, row in stocks.items():
        require(type(row) is dict and set(row) == {
            "ticker", "market", "source_url", "today", "business_report"})
        url = PUBLIC_CHANGE_BASE_URL + ticker[:3] + ".json"
        require(row["ticker"] == ticker and row["market"] == "KR" and row["source_url"] == url)
        today = row["today"]
        if today is not None:
            require(type(today) is dict and type(today.get("fields")) is list)
            fields = today["fields"]
            status, source_status = today.get("status"), today.get("source_status")
            require((status in ("changed", "partial") and bool(fields) and source_status == "changed")
                    or (status == "unavailable" and not fields and source_status == "changed")
                    or (status == "unchanged" and not fields and source_status == "unchanged"))
            raw = {**today, "status": "changed" if fields else "unchanged"}
            checked = _today(raw, url, Counter(), Counter(), cutoff)
            require(checked is not None)
            checked.update(status=status, source_status=source_status)
            require(checked == today)
        business = row["business_report"]
        if business is not None:
            checked = _business(business, url, Counter(), Counter(), cutoff)
            require(checked is not None and checked == business)
    base_keys = {"status", "requested", "eligible", "matched", "available", "missing",
                 "rejected", "unsupported", "shape_errors", "today", "business_report"}
    require(type(coverage) is dict and set(coverage) in (base_keys, base_keys | {"shards"}))
    for key in ("requested", "eligible", "matched", "available", "shape_errors"):
        require(count(coverage[key]))
    require(coverage["requested"] == len(requested) and coverage["eligible"] == len(tickers)
            and coverage["matched"] == len(stocks) and coverage["shape_errors"] in (0, 1))
    for key in ("missing", "rejected"):
        values = coverage[key]
        require(type(values) is list and all(type(v) is str for v in values))
        require(values == sorted(set(values)) and set(values) <= set(tickers))
    missing, rejected = set(coverage["missing"]), set(coverage["rejected"])
    require(not (missing & rejected or missing & set(stocks) or rejected & set(stocks))
            and missing | rejected | set(stocks) == set(tickers))
    require(coverage["unsupported"] == [p["id"] for p in requested if p["market"] != "KR"])
    today_reasons = {
        "invalid_today", "insufficient_history", "invalid_comparison", "invalid_field",
        "per_basis_unverified", "unsupported_field", "duplicate_field", "invalid_number",
        "unchanged_field", "delta_mismatch", "missing_delta_pct", "delta_pct_mismatch",
    }
    business_reasons = {
        "missing_comparison", "invalid_original_pair", "reversed_filing_dates", "text_delta_mismatch",
    }
    for key, allowed_reasons in (("today", today_reasons), ("business_report", business_reasons)):
        section = coverage[key]
        keys = {"input", "accepted", "rejected", "rejection_reasons"}
        if key == "today":
            keys.add("pairs")
        require(type(section) is dict and set(section) == keys)
        require(all(count(section[k]) for k in keys - {"rejection_reasons"}))
        require(section["input"] == section["accepted"] + section["rejected"])
        reasons = section["rejection_reasons"]
        require(type(reasons) is dict and set(reasons) <= allowed_reasons
                and all(count(v) and v > 0 for v in reasons.values()))
        require(not section["rejected"] or bool(reasons))
    daily, business = coverage["today"], coverage["business_report"]
    require(daily["accepted"] == sum(len(r["today"]["fields"]) for r in stocks.values() if r["today"]))
    require(daily["pairs"] == sum(r["today"] is not None for r in stocks.values()))
    require(business["input"] == len(stocks)
            and business["accepted"] == sum(r["business_report"] is not None for r in stocks.values())
            and sum(business["rejection_reasons"].values()) == business["rejected"])
    require(not coverage["shape_errors"] or not stocks)
    require(daily["rejected"] >= sum(r["today"] is not None and r["today"]["status"] in
                                    ("partial", "unavailable") for r in stocks.values()))
    available = sum(bool((r["today"] and r["today"]["status"] in ("changed", "unchanged", "partial"))
                         or r["business_report"]) for r in stocks.values())
    complete = (tickers and len(stocks) == len(tickers) and daily["pairs"] == len(tickers)
                and not daily["rejected"] and business["accepted"] == len(tickers))
    require(coverage["available"] == available and coverage["status"] ==
            ("complete" if complete else "partial" if available else "unavailable"))
    if "shards" in coverage:
        shard = coverage["shards"]
        require(type(shard) is dict and set(shard) == {"expected", "available", "missing", "status"})
        require(count(shard["expected"]) and count(shard["available"]))
        require(type(shard["missing"]) is list and all(type(p) is str for p in shard["missing"]))
        require(shard["missing"] == sorted(set(shard["missing"])) and set(shard["missing"]) <= set(prefixes))
        require(shard["expected"] == len(prefixes)
                and shard["available"] == len(prefixes) - len(shard["missing"])
                and not any(t[:3] in shard["missing"] for t in stocks))
        expected = ("not_applicable" if not prefixes else "complete" if not shard["missing"]
                    else "partial" if shard["available"] else "unavailable")
        require(shard["status"] == expected)
    return deepcopy(projection)


def _download_shard(prefix, *, timeout=FETCH_TIMEOUT_SECONDS):
    if type(prefix) is not str or not re.fullmatch(r"[0-9]{3}", prefix):
        raise ValueError("invalid-public-change-prefix")
    if not _number(timeout) or not 0 < timeout <= FETCH_TIMEOUT_SECONDS:
        raise ValueError("invalid-public-change-timeout")
    return _read_public_document(PUBLIC_CHANGE_BASE_URL + prefix + ".json",
                                 MAX_SHARD_BYTES, timeout=timeout)


def _from_shards(documents, positions, prefixes, as_of):
    stocks, available = {}, []
    for prefix in prefixes:
        document = documents.get(prefix)
        if type(document) is not dict or type(document.get("stocks")) is not dict:
            continue
        available.append(prefix)
        # Never let one shard populate another shard's selected ticker.
        stocks.update({ticker: row for ticker, row in document["stocks"].items()
                       if type(ticker) is str and re.fullmatch(r"[0-9]{6}", ticker)
                       and ticker[:3] == prefix})
    result = project_public_changes({"stocks": stocks}, positions, as_of=as_of)
    result["coverage"]["shards"] = {
        "expected": len(prefixes), "available": len(available),
        "missing": [p for p in prefixes if p not in available],
        "status": ("not_applicable" if not prefixes else
                   "complete" if len(available) == len(prefixes) else
                   "partial" if available else "unavailable"),
    }
    return result


def fetch_public_changes(positions, *, as_of=None, _fetcher=None, _clock=None):
    """Read at most 20 selected prefixes within one three-second IO budget.

    Existing transport enforces fixed GET, no proxies/credentials/redirects,
    size and socket timeout, unique JSON keys and nonfinite-number rejection.
    No cache or retries. Only documents completed before the deadline survive;
    failures/timeouts report missing shards without exposing exception text.
    Test hooks are local only; HTTP callers cannot provide a clock or fetcher.
    """
    clock = _clock or time.monotonic
    deadline = clock() + FETCH_BUDGET_SECONDS
    _, _, prefixes = _selection(positions)
    as_of = as_of if as_of is not None else datetime.now(timezone.utc).date().isoformat()
    if _day(as_of) is None:
        raise ValueError("invalid-change-as-of")
    documents = {}
    if prefixes:
        stopped = threading.Event()

        def read(prefix):
            remaining = deadline - clock()
            # A worker can dequeue just before cancellation. Recheck here so
            # finishing one request never starts queued IO after the deadline.
            if stopped.is_set() or remaining <= 0:
                return None
            document = (_fetcher(prefix) if _fetcher is not None else
                        _download_shard(prefix, timeout=min(FETCH_TIMEOUT_SECONDS, remaining)))
            return document if not stopped.is_set() and clock() < deadline else None

        pool = ThreadPoolExecutor(max_workers=min(4, len(prefixes)))
        futures = {}
        try:
            for prefix in prefixes:
                futures[pool.submit(read, prefix)] = prefix
            remaining = deadline - clock()
            if remaining > 0:
                done, _ = wait(futures, timeout=remaining)
            else:
                done = {future for future in futures if future.done()}
            for future in done:
                try:
                    documents[futures[future]] = future.result()
                except Exception:
                    pass
        finally:
            stopped.set()
            for future in futures:
                future.cancel()
            # The executor context manager would wait for running requests.
            # Workers never write to documents or mutate the returned result.
            pool.shutdown(wait=False, cancel_futures=True)
    return _from_shards(documents, positions, prefixes, as_of)


def _open_directory(path, *, dir_fd=None):
    before = os.stat(path, dir_fd=dir_fd, follow_symlinks=False)
    if not stat.S_ISDIR(before.st_mode):
        raise ValueError("invalid-change-source")
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, dir_fd=dir_fd)
    try:
        after = os.fstat(descriptor)
        if not stat.S_ISDIR(after.st_mode) or (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
            raise ValueError("invalid-change-source")
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def _open_root(source_dir):
    path = os.fspath(source_dir)
    if type(path) is not str or not path or "\x00" in path or ".." in Path(path).parts:
        raise ValueError("invalid-change-source")
    return _open_directory(path)


def _load_local_shard(directory_fd, prefix):
    # Same no-follow/inode/size gates as portfolio_price_sources, which is not
    # shipped in portfolio_core. Keep this fixed-shard reader self-contained.
    filename = prefix + ".json"
    before = os.stat(filename, dir_fd=directory_fd, follow_symlinks=False)
    if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_SHARD_BYTES:
        raise ValueError("invalid-change-source")
    descriptor = os.open(filename, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                         | getattr(os, "O_NONBLOCK", 0), dir_fd=directory_fd)
    try:
        after = os.fstat(descriptor)
        if (not stat.S_ISREG(after.st_mode) or after.st_size > MAX_SHARD_BYTES
                or (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino)):
            raise ValueError("invalid-change-source")
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = -1
            raw = stream.read(MAX_SHARD_BYTES + 1)
        if len(raw) > MAX_SHARD_BYTES:
            raise ValueError("invalid-change-source")
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    def finite_float(value):
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("invalid-change-source")
        return number
    document = json.loads(
        raw.decode("utf-8"), object_pairs_hook=_unique_object, parse_float=finite_float,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError("invalid-change-source")))
    if type(document) is not dict:
        raise ValueError("invalid-change-source")
    return document


def load_public_changes(source_dir, positions, *, as_of=None):
    """Read source_dir/stock_change_public/{prefix}.json without network/cache.

    Reuse the existing descriptor-relative pattern: reject symlinks, nonregular
    files, duplicate JSON keys, nonfinite values and over-limit files. A missing
    or unsafe optional source is represented as unavailable shard coverage.
    """
    _, _, prefixes = _selection(positions)
    as_of = as_of if as_of is not None else datetime.now(timezone.utc).date().isoformat()
    if _day(as_of) is None:
        raise ValueError("invalid-change-as-of")
    documents = {}
    if prefixes:
        try:
            root_fd = _open_root(source_dir)
        except (OSError, ValueError, TypeError):
            return _from_shards(documents, positions, prefixes, as_of)
        try:
            try:
                directory_fd = _open_directory("stock_change_public", dir_fd=root_fd)
            except (OSError, ValueError, TypeError):
                return _from_shards(documents, positions, prefixes, as_of)
            try:
                for prefix in prefixes:
                    try:
                        documents[prefix] = _load_local_shard(directory_fd, prefix)
                    except (OSError, ValueError, TypeError, RecursionError):
                        pass
            finally:
                os.close(directory_fd)
        finally:
            os.close(root_fd)
    return _from_shards(documents, positions, prefixes, as_of)
