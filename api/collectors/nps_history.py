"""NPS disclosure observations for the annual domestic evaluation top 100.

Contract: build_history(full_rows, *, previous=None, cache=None, cache_path=...,
                       period_start=None, period_end=None, now=None, ttl_hours=168).
It reads local last-good rows only; it never collects or writes. The public
payload embeds detail_history.stocks[].events/observed_pct/collection.
Only an explicit CLI --collect calls majorstock, with a budget and TTL resume.

Offline augmentation (preserves every existing payload field):
  python -m api.collectors.nps_history --input /tmp/nps.json --output /tmp/nps-detail.json
Optional collection: append --collect --maxcalls 20 --ttl-hours 168 --resume.
Optional annual seed: --annual-input data/nps_full_holdings_annual.json;
invalid explicit seeds fail before collection or output writes. Only full and
full_n are replaced, and a newer valid payload annual date is never downgraded.
Cache: data/nps_history_cache.json, local raw-row/checkpoint store, NOT a new
public artifact. Its workflow persistence is the main owner's responsibility.
Keep this cache to retain rows outside a selected period or changing top 100.
No document-body requests: report/trade dates and correction links stay null.
See output/nps-feasibility-20261008/verification.json for verified boundaries.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import os
import re
import tempfile
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
CACHE_PATH = ROOT / "data" / "nps_history_cache.json"
INPUT_PATH = ROOT / "data" / "nps_holdings.json"
TOP_N = 100
TTL_HOURS = 168
DART_URL = "https://opendart.fss.or.kr/api/majorstock.json"
DATE_BASIS = "filing_date"


def _now(value=None):
    value = value or datetime.now(timezone.utc)
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _date(value, *, annual=False):
    text = str(value or "").strip()
    if annual and re.fullmatch(r"20\d{2}년?", text):
        text = text[:4] + "-12-31"
    if re.fullmatch(r"\d{8}", text):
        text = f"{text[:4]}-{text[4:6]}-{text[6:]}"
    text = text.replace(".", "-").replace("/", "-")
    try:
        return date.fromisoformat(text).isoformat()
    except (ValueError, TypeError):
        return None


def _number(value, *, integer=False, nonnegative=False):
    if value is None or isinstance(value, bool):
        return None
    text = str(value).replace(",", "").replace("%", "").strip()
    try:
        number = float(text)
    except (ValueError, TypeError, OverflowError):
        return None
    if not math.isfinite(number) or (nonnegative and number < 0):
        return None
    if integer:
        # Quantity is an integer: don't round fractional observations.
        try:
            from decimal import Decimal
            exact = Decimal(text)
            return int(exact) if exact == exact.to_integral_value() else None
        except (ValueError, ArithmeticError):
            return None
    return number


def _ticker(value):
    text = str(value or "").strip().upper().split(".")[0]
    return text if re.fullmatch(r"[0-9A-Z]{6}", text) and text != "000000" else None


def select_top100(full_rows):
    """Latest *dated* annual cohort; never rank across years or sum duplicates.

    Rank the source securities BEFORE ticker matching. Missing/ambiguous
    mappings occupy their original top-100 slots; never promote row 101.
    An undated row is excluded, not assigned the newest year. Conflicting
    duplicate valuations are excluded. Zero is valid; negative, missing and
    nonfinite valuations are excluded. Ties use the public source name.
    """
    rows = full_rows if isinstance(full_rows, list) else []
    excluded = Counter()
    dated = []
    for row in rows:
        if not isinstance(row, dict):
            excluded["invalid_row"] += 1
            continue
        asof = _date(row.get("as_of"), annual=True)
        if not asof or not asof.endswith("-12-31"):
            excluded["missing_or_nonannual_date"] += 1
            continue
        dated.append((asof, row))
    dates = sorted({asof for asof, _ in dated})
    selected_date = dates[-1] if dates else None
    groups = defaultdict(list)
    for index, (asof, row) in enumerate(dated):
        if asof != selected_date:
            excluded["other_annual_date"] += 1
            continue
        name = re.sub(r"\s+", "", str(row.get("name") or "")).casefold()
        ticker = _ticker(row.get("ticker"))
        # Source security names distinguish preferred from ordinary shares;
        # an issuer/ticker collision must not silently combine those positions.
        identity = ("name", name) if name else ("ticker", ticker) if ticker else ("unidentified", index)
        groups[identity].append(row)
    valid, conflicts, duplicate_n = [], [], 0
    for group in groups.values():
        tickers = {_ticker(row.get("ticker")) for row in group}
        identified = tickers - {None}
        ticker = next(iter(identified)) if len(identified) == 1 else None
        amounts = [_number(r.get("eval_amt_100m"), nonnegative=True) for r in group]
        if any(a is None for a in amounts):
            excluded["invalid_valuation"] += len(group)
            continue
        if len(set(amounts)) != 1:
            conflicts.extend(identified)
            excluded["conflicting_duplicate"] += len(group)
            continue
        duplicate_n += len(group) - 1
        pcts = {_number(r.get("pct"), nonnegative=True) for r in group}
        selection_pct = next(iter(pcts)) if len(pcts) == 1 else None
        if selection_pct is not None and selection_pct > 100:
            selection_pct = None
        valid.append({"ticker": ticker, "name": group[0].get("name") or ticker,
                      "eval_amt_100m": amounts[0], "selection_pct": selection_pct,
                      "selection_as_of": selected_date,
                      "mapping_reason": "conflicting_ticker_mapping" if len(identified) > 1 else "ticker_unresolved" if ticker is None else None})
        if any(row.get("security_type") == "preferred" for row in group):
            valid[-1]["security_type"] = "preferred"
    by_ticker = defaultdict(list)
    for row in valid:
        if row["ticker"]:
            by_ticker[row["ticker"]].append(row)
    for ticker, securities in by_ticker.items():
        if len(securities) > 1:
            conflicts.append(ticker)
            for row in securities:
                row.update(ticker=None, mapping_reason="duplicate_ticker_mapping")
    valid.sort(key=lambda r: (-r["eval_amt_100m"], str(r["name"] or "").casefold()))
    top100 = [dict(row, rank=i + 1) for i, row in enumerate(valid[:TOP_N])]
    targets = [{k: v for k, v in row.items() if k != "mapping_reason"} for row in top100 if row["ticker"]]
    unmatched = [{"rank": row["rank"], "name": row["name"], "ticker": None,
                  "eval_amt_100m": row["eval_amt_100m"], "selection_as_of": selected_date,
                  "reason": row["mapping_reason"]} for row in top100 if not row["ticker"]]
    return targets, {
        "as_of": selected_date, "limit": TOP_N,
        "rank_by": "eval_amt_100m", "rank_order": "descending", "tie_break": "source_name_asc",
        "annual_input_n": len(rows), "eligible_n": len(valid),
        "target_n": len(targets), "annual_dates_seen": dates,
        "annual_top100_n": len(top100), "annual_top100_unmatched_n": len(unmatched),
        "annual_top100_unmatched_rows": unmatched,
        "excluded_rows": dict(excluded), "duplicate_rows_n": duplicate_n,
        "conflicting_tickers": sorted(set(conflicts)),
    }


def annual_cohort_as_of(rows, *, require_top100=False):
    """Validate a whole annual cohort, not just its mapped/ranked subset."""
    if not isinstance(rows, list) or not rows or any(
        not isinstance(row, dict) or not isinstance(row.get("name"), str) or not row["name"].strip()
        for row in rows
    ):
        return None
    _, selection = select_top100(rows)
    if (len(selection["annual_dates_seen"]) != 1 or selection["excluded_rows"]
            or selection["duplicate_rows_n"] or selection["conflicting_tickers"]
            or selection["eligible_n"] != len(rows)
            or (require_top100 and selection["annual_top100_n"] != TOP_N)):
        return None
    return selection["as_of"]


def read_annual_seed(path, *, strict=False):
    """Read a local official annual seed; invalid/missing seeds never mean zero.

    strict=True fails before CLI collection/output writes. The default loader
    may fall back to its existing source or published last-good cohort instead.
    Missing ticker mappings retain source slots and do not invalidate the seed.
    """
    try:
        document = _read_json(path, strict=True)
        source = document.get("source")
        if not isinstance(source, dict):
            raise ValueError
        url = urlsplit(str(source.get("url") or ""))
        rows = document.get("full")
        asof = annual_cohort_as_of(rows, require_top100=True)
        if (type(document.get("schema_version")) is not int or document["schema_version"] != 1
                or type(document.get("full_n")) is not int or document["full_n"] != len(rows or [])
                or type(source.get("rows")) is not int or source["rows"] != document["full_n"]
                or not asof or document.get("as_of") != asof
                or url.scheme != "https" or url.hostname not in ("officialfund.nps.or.kr", "fund.nps.or.kr")
                or url.username or url.password or url.port not in (None, 443)):
            raise ValueError
        return document
    except (OSError, ValueError, TypeError, AttributeError):
        if strict:
            raise ValueError("invalid annual seed; refusing to replace last-good") from None
        return None


def _nps(row):
    return isinstance(row, dict) and "국민연금" in re.sub(r"\s+", "", str(row.get("repror") or ""))


def _unique_rows(rows):
    seen, result = set(), []
    for row in rows:
        if not _nps(row):
            continue
        key = json.dumps(row, ensure_ascii=False, sort_keys=True)
        if key not in seen:
            seen.add(key)
            result.append(copy.deepcopy(row))
    return result


def normalize_history(rows):
    """Keep NPS originals, dedup receipts, preserve variants and corrections.

    An unresolved same-receipt conflict becomes null in the affected numeric
    field; no arbitrary row wins. Separate correction receipts stay separate.
    Neither correction linkage nor the document's report date is inferred.
    """
    rows = rows if isinstance(rows, list) else []
    originals = _unique_rows(rows)
    groups, unparsed = defaultdict(list), []
    for row in originals:
        receipt = str(row.get("rcept_no") or "").strip()
        if not re.fullmatch(r"\d{14}", receipt):
            unparsed.append(row)
        else:
            groups[receipt].append(row)
    events = []
    fields = {"qty": ("stkqy", True, True), "pct": ("stkrt", False, True),
              "qty_change": ("stkqy_irds", True, False), "pct_change_pp": ("stkrt_irds", False, False)}
    for receipt, variants in groups.items():
        event = {"rcept_no": receipt, "raw_rows": variants,
                 "as_of": None, "trade_date": None, "date_basis": DATE_BASIS,
                 "source_url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={receipt}",
                 "correction_of": None, "correction_link_verified": False}
        conflicts = []
        dates = {_date(row.get("rcept_dt")) for row in variants}
        event["filed_at"] = next(iter(dates)) if len(dates) == 1 else None
        if len(dates) > 1:
            conflicts.append("filed_at")
        for name, (source, integer, nonnegative) in fields.items():
            values = {_number(row.get(source), integer=integer, nonnegative=nonnegative) for row in variants}
            if name == "pct":
                values = {v if v is None or v <= 100 else None for v in values}
            event[name] = next(iter(values)) if len(values) == 1 else None
            if len(values) > 1:
                conflicts.append(name)
        reasons = list(dict.fromkeys(str(row.get("report_resn") or "") for row in variants))
        event["reason"] = reasons[0] if len(reasons) == 1 else None
        event["is_correction"] = any("정정" in str(row.get("report_tp") or "") + str(row.get("report_resn") or "")
                                     for row in variants)
        event["conflicting_fields"] = conflicts
        delta = event["qty_change"]
        event["change_label"] = ("보유 수량 증가" if delta > 0 else "보유 수량 감소" if delta < 0 else "보유 수량 변동 없음") if delta is not None else None
        events.append(event)
    events.sort(key=lambda e: (e["filed_at"] is None, e["filed_at"] or "", e["rcept_no"]))
    return {"events": events, "unparsed_rows": unparsed,
            "raw_n": sum(_nps(row) for row in rows), "unique_raw_n": len(originals),
            "duplicate_n": sum(_nps(row) for row in rows) - len(originals),
            "conflict_receipt_n": sum(bool(e["conflicting_fields"]) for e in events)}


def _read_json(path, *, strict=False):
    if path is None:
        return {}
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            raise ValueError("object required")
        return data
    except FileNotFoundError:
        return {}
    except (OSError, ValueError, TypeError):
        if strict:
            raise ValueError("local JSON unreadable; refusing to overwrite") from None
        return {"_read_error": "cache_unreadable"}


def _save_json(path, data):
    """Atomic checkpoints; a failed write leaves the previous cache intact."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=1, allow_nan=False)
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _entries(cache, previous):
    """Recover embedded raw originals if a local cache is missing/failed/partial."""
    stored = (cache or {}).get("entries") or {}
    result = {ticker: copy.deepcopy(entry) for ticker, entry in stored.items()
              if isinstance(entry, dict)} if isinstance(stored, dict) else {}
    previous = previous or {}
    old_stocks = previous.get("stocks") or list((previous.get("by_ticker") or {}).values())
    for old in old_stocks:
        if not isinstance(old, dict):
            continue
        ticker = _ticker(old.get("ticker"))
        if not ticker:
            continue
        entry = result.setdefault(ticker, {})
        raw = [row for event in old.get("events", []) for row in event.get("raw_rows", [])]
        raw += old.get("unparsed_rows", [])
        entry["raw_rows"] = _unique_rows(raw + (entry.get("raw_rows") or []))
        collection = old.get("collection") or {}
        def stamp(value):
            try:
                return _now(value) if value else datetime.min.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError, AttributeError):
                return datetime.min.replace(tzinfo=timezone.utc)
        previous_attempt_is_latest = stamp(collection.get("last_attempt_at")) > stamp(entry.get("last_attempt_at"))
        for key in ("collected_at", "last_good_at", "last_attempt_at"):
            if stamp(collection.get(key)) > stamp(entry.get(key)):
                entry[key] = collection[key]
        for key in ("last_status", "missing_reason"):
            if previous_attempt_is_latest or entry.get("last_status") is None:
                entry[key] = collection.get(key)
    return result


def _recent(timestamp, now, ttl_hours):
    try:
        age = (now - _now(timestamp)).total_seconds() if timestamp else None
        return age is not None and 0 <= age < ttl_hours * 3600
    except (ValueError, TypeError, AttributeError):
        return False


def _period(start, end, now):
    left = _date(start) if start is not None else None
    right = _date(end) if end is not None else now.date().isoformat()
    if (start is not None and left is None) or right is None or (left and left > right):
        raise ValueError("invalid observation period")
    return {"start": left, "end": right, "date_basis": DATE_BASIS,
            "mode": "selected_period" if left else "all_cached_through_end"}


def build_history(full_rows, *, previous=None, cache=None, cache_path=CACHE_PATH,
                  period_start=None, period_end=None, now=None, ttl_hours=TTL_HOURS,
                  annual_input_status="current") -> dict[str, Any]:
    """Local-only public API. Coverage counts tickers, not complete trade history."""
    now = _now(now)
    if not math.isfinite(ttl_hours) or ttl_hours <= 0:
        raise ValueError("ttl_hours must be finite and positive")
    cache = _read_json(cache_path) if cache is None else cache
    entries = _entries(cache, previous)
    targets, selection = select_top100(full_rows)
    selection["annual_input_status"] = annual_input_status
    period = _period(period_start, period_end, now)
    stocks, missing = [], copy.deepcopy(selection["annual_top100_unmatched_rows"])
    with_history_n = fresh_n = period_n = 0
    for target in targets:
        ticker = target["ticker"]
        # majorstock is issuer-scoped, not verified preferred-share holdings.
        # Keep any raw cache intact, but never project issuer values onto it.
        preferred = target.get("security_type") == "preferred"
        entry = {} if preferred else entries.get(ticker) or {}
        parsed = normalize_history(entry.get("raw_rows"))
        events = [e for e in parsed["events"] if e["filed_at"] and
                  (period["start"] is None or e["filed_at"] >= period["start"]) and e["filed_at"] <= period["end"]]
        good = any(e["filed_at"] for e in parsed["events"])
        fresh = good and entry.get("last_status") == "ok" and _recent(entry.get("collected_at"), now, ttl_hours)
        reason = "corp_code_missing" if preferred else entry.get("missing_reason") or entry.get("deferred_reason") or (None if fresh else "ttl_expired" if good else cache.get("_read_error") or "not_collected")
        status = "ok" if fresh else "stale" if good else "error" if entry.get("last_status") == "error" else "not_collected"
        status_label = {"ok": "공시 이력 조회됨", "stale": "이전 공시 이력 유지",
                        "error": "공시 수집 실패", "not_collected": "아직 수집되지 않음"}[status]
        collection = {key: entry.get(key) for key in ("collected_at", "last_good_at", "last_attempt_at", "last_status")}
        collection.update(status=status, missing_reason=reason, stale=not fresh,
                          retained_last_good=good and not fresh)
        pct_events = [e for e in events if e["pct"] is not None]
        correction_unverified = any(e["is_correction"] for e in parsed["events"])
        def point(event):
            return {key: event[key] for key in ("pct", "filed_at", "rcept_no", "source_url")}
        observed = {"period": dict(period, start=period["start"] or (events[0]["filed_at"] if events else None)),
                    "date_basis": DATE_BASIS, "observation_n": len(pct_events),
                    "max": point(max(pct_events, key=lambda e: e["pct"])) if pct_events and not correction_unverified else None,
                    "min": point(min(pct_events, key=lambda e: e["pct"])) if pct_events and not correction_unverified else None,
                    "correction_links_unverified": correction_unverified}
        unplaced = [row for event in parsed["events"] if not event["filed_at"] for row in event["raw_rows"]]
        stocks.append({**target, "events": events, "status": status, "status_label": status_label,
                       "last_success_at": entry.get("last_good_at") or entry.get("collected_at"),
                       "missing_reason": reason, "unparsed_rows": parsed["unparsed_rows"] + unplaced,
                       "observed_pct": observed, "collection": collection,
                       "row_coverage": {k: parsed[k] for k in ("raw_n", "unique_raw_n", "duplicate_n", "conflict_receipt_n")}})
        with_history_n += good
        fresh_n += fresh
        period_n += bool(events)
        if not fresh:
            missing.append({"ticker": ticker, "reason": reason})
    detail = {"schema_version": 1, "generated_at": now.isoformat(),
            "scope": "annual_domestic_evaluation_top100", "selection": selection,
            "period": period, "stocks": stocks,
            "coverage": {"selected_count": selection["annual_top100_n"], "mapped_count": len(targets),
                         "annual_top100_unmatched_n": selection["annual_top100_unmatched_n"],
                         "with_history_count": with_history_n,
                         "with_period_history_count": period_n, "fresh_count": fresh_n,
                         "stale_count": with_history_n - fresh_n, "missing_or_stale": missing,
                         "complete_trade_history": False},
            "network_enabled": False, "last_collection_run": cache.get("last_collection_run"),
            "note": "공시 관측 이력 · 접수일 기준, 실제 매매일 아님 · 보고기준일 미확인 · 보유 수량 증감은 매수·매도 확정 아님 · 전체 체결·평균 매입단가 복원 불가 · 정정 연결 미확인"}
    # Preserve the existing holdings no-rewrite gate: a projection timestamp
    # changes only with public history content, not with every cache-only build.
    if isinstance(previous, dict) and previous.get("generated_at"):
        old_content = {k: v for k, v in previous.items() if k != "generated_at"}
        new_content = {k: v for k, v in detail.items() if k != "generated_at"}
        if old_content == new_content:
            detail["generated_at"] = previous["generated_at"]
    return detail


def _cached_resolver():
    """Reuse get_corp_code with its existing mapping, without self-heal requests.

    load_mapping normally refreshes missing/stale name maps. Prime only its
    local mapping cache so neither build_mapping nor ensure_name_map can run
    outside the majorstock call budget. No mapping/name files are written.
    """
    from api.collectors import dart_corp_code
    if not dart_corp_code._mapping_cache:
        if not os.path.isfile(dart_corp_code.MAPPING_PATH):
            raise FileNotFoundError("cached DART mapping unavailable")
        dart_corp_code._mapping_cache = _read_json(dart_corp_code.MAPPING_PATH, strict=True)
    if not dart_corp_code._mapping_cache:
        raise ValueError("cached DART mapping empty")
    return dart_corp_code.get_corp_code


def collect_history(full_rows, *, allow_network=False, maxcalls=20, ttl_hours=TTL_HOURS,
                    resume=True, previous=None, cache=None, cache_path=CACHE_PATH,
                    api_key=None, corp_resolver=None, session=None, now=None):
    """Explicit opt-in only; checkpoint each result, never erase last-good rows.

    maxcalls includes failed HTTP/JSON attempts; there are no hidden retries,
    mapping downloads, body requests or secondary endpoints. --resume also
    skips recent failed/empty attempts within the TTL, moving on to other rows.
    """
    if not allow_network:
        raise ValueError("network disabled; explicit --collect required")
    if isinstance(maxcalls, bool) or not isinstance(maxcalls, int) or not 0 <= maxcalls <= TOP_N:
        raise ValueError("maxcalls must be an integer in 0..100")
    if not math.isfinite(ttl_hours) or ttl_hours <= 0:
        raise ValueError("ttl_hours must be finite and positive")
    now = _now(now)
    cache = copy.deepcopy(_read_json(cache_path, strict=True) if cache is None else cache)
    stored = cache.get("entries", {})
    if not isinstance(stored, dict) or any(
        not isinstance(entry, dict) or not isinstance(entry.get("raw_rows", []), list)
        for entry in stored.values()
    ):
        raise ValueError("invalid cache entries; refusing to overwrite")
    entries = _entries(cache, previous)
    cache.update(schema_version=1, entries=entries)
    targets, selection = select_top100(full_rows)
    run = {"at": now.isoformat(), "annual_as_of": selection["as_of"], "target_n": len(targets),
           "annual_top100_n": selection["annual_top100_n"],
           "annual_top100_unmatched_n": selection["annual_top100_unmatched_n"],
           "maxcalls": maxcalls, "calls": 0, "ttl_skipped_n": 0,
           "unattempted": copy.deepcopy(selection["annual_top100_unmatched_rows"])}
    if api_key is None:
        from api.config import DART_API_KEY
        api_key = DART_API_KEY
    resolver_error = None
    if corp_resolver is None and api_key and maxcalls:
        try:
            corp_resolver = _cached_resolver()
        except Exception:  # never log exception URLs, messages or credentials
            resolver_error = "corp_mapping_unavailable"
    if session is None and api_key and maxcalls:
        import requests
        session = requests.Session()
    cache["last_collection_run"] = run
    for target in targets:
        ticker = target["ticker"]
        entry = entries.setdefault(ticker, {})
        if target.get("security_type") == "preferred":
            entry["deferred_reason"] = "corp_code_missing"
            run["unattempted"].append({"ticker": ticker, "reason": "corp_code_missing"})
            continue
        if _recent(entry.get("collected_at"), now, ttl_hours) or (resume and _recent(entry.get("last_attempt_at"), now, ttl_hours)):
            run["ttl_skipped_n"] += 1
            continue
        reason = "missing_dart_key" if not api_key else "maxcalls_reached" if run["calls"] >= maxcalls else resolver_error
        corp_code = None
        if reason is None:
            try:
                corp_code = str(corp_resolver(ticker) or "")
            except Exception:
                reason = "corp_mapping_unavailable"
            if not re.fullmatch(r"\d{8}", corp_code or ""):
                reason = reason or "corp_code_missing"
        if reason:
            run["unattempted"].append({"ticker": ticker, "reason": reason})
            entry["deferred_reason"] = reason
            # Don't fabricate a collection timestamp when no request was made.
            continue
        run["calls"] += 1
        entry["last_attempt_at"] = now.isoformat()
        received = []
        reason = None
        try:
            response = session.get(DART_URL, params={"crtfc_key": api_key, "corp_code": corp_code}, timeout=15)
            if response.status_code != 200:
                reason = "http_error"
            else:
                document = response.json()
                if not isinstance(document, dict):
                    reason = "invalid_response"
                elif document.get("status") == "013":
                    reason = "empty_response"
                elif document.get("status") != "000":
                    reason = "dart_error"
                elif not isinstance(document.get("list"), list):
                    reason = "invalid_response"
                else:
                    received = _unique_rows(document["list"])
                    if not received:
                        reason = "no_nps_rows" if document["list"] else "empty_response"
                    elif any(row.get("corp_code") and str(row["corp_code"]) != corp_code for row in received):
                        received, reason = [], "corp_code_mismatch"
                    elif not any(e["filed_at"] for e in normalize_history(received)["events"]):
                        reason = "invalid_nps_rows"
        except Exception:
            reason = "transport_or_json_error"
        # Empty/error responses never replace the old list; partial success is additive.
        entry["raw_rows"] = _unique_rows((entry.get("raw_rows") or []) + received)
        entry.pop("deferred_reason", None)
        entry.update(last_status="error" if reason else "ok", missing_reason=reason)
        if not reason:
            entry.update(collected_at=now.isoformat(), last_good_at=now.isoformat())
        if cache_path is not None:
            _save_json(cache_path, cache)
    if cache_path is not None:
        _save_json(cache_path, cache)
    return cache


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", type=Path, default=INPUT_PATH)
    parser.add_argument("--annual-input", type=Path, help="validated local official annual seed")
    parser.add_argument("--output", type=Path, required=True, help="new augmented payload; must differ from input/cache")
    parser.add_argument("--cache", type=Path, default=CACHE_PATH)
    parser.add_argument("--collect", action="store_true", help="opt in to bounded DART majorstock requests")
    parser.add_argument("--maxcalls", type=int, default=20)
    parser.add_argument("--ttl-hours", type=float, default=TTL_HOURS)
    parser.add_argument("--resume", action="store_true", help="also skip recent failed/empty attempts within TTL")
    parser.add_argument("--period-start")
    parser.add_argument("--period-end")
    args = parser.parse_args(argv)
    if args.output.resolve() in (args.input.resolve(), args.cache.resolve()) or args.cache.resolve() == args.input.resolve():
        parser.error("input, output and cache must be distinct paths")
    if args.annual_input and args.annual_input.resolve() in (args.input.resolve(), args.output.resolve(), args.cache.resolve()):
        parser.error("annual input must differ from input, output and cache")
    try:
        if not args.input.is_file():
            raise ValueError("input payload missing")
        payload = _read_json(args.input, strict=True)
        previous = payload.get("detail_history")
        # Validate local arguments before any optional request.
        _period(args.period_start, args.period_end, _now())
        if not math.isfinite(args.ttl_hours) or args.ttl_hours <= 0 or not 0 <= args.maxcalls <= TOP_N:
            raise ValueError("invalid TTL or request budget")
        if args.annual_input:
            annual = read_annual_seed(args.annual_input, strict=True)
            current_asof = annual_cohort_as_of(payload.get("full"))
            if current_asof is None or annual["as_of"] >= current_asof:
                payload["full"], payload["full_n"] = annual["full"], annual["full_n"]
        cache = _read_json(args.cache, strict=args.collect)
        if args.collect:
            cache = collect_history(payload.get("full"), allow_network=True, maxcalls=args.maxcalls,
                                    ttl_hours=args.ttl_hours, resume=args.resume, previous=previous,
                                    cache=cache, cache_path=args.cache)
        payload["detail_history"] = build_history(payload.get("full"), previous=previous, cache=cache,
                                                  period_start=args.period_start, period_end=args.period_end,
                                                  ttl_hours=args.ttl_hours)
        _save_json(args.output, payload)
        detail = payload["detail_history"]
        print(json.dumps({"output": str(args.output), "annual_as_of": detail["selection"]["as_of"],
                          "target_n": detail["selection"]["target_n"],
                          "annual_top100_unmatched_n": detail["selection"]["annual_top100_unmatched_n"],
                          "annual_top100_unmatched_rows": detail["selection"]["annual_top100_unmatched_rows"],
                          "coverage": {k: v for k, v in detail["coverage"].items() if k != "missing_or_stale"},
                          "missing_reason_counts": dict(Counter(r["reason"] for r in detail["coverage"]["missing_or_stale"])),
                          "collection_run": cache.get("last_collection_run")}, ensure_ascii=False))
        return 0
    except (ValueError, OSError, TypeError):
        # Do not echo exceptions: request URLs/config strings can contain secrets.
        print("nps_history: local input/output error; original input preserved; cache checkpoints may remain")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
