"""Private, sanitized NPS failure artifacts and explicit one-pass target recovery.

Recovery reads only the two existing DART ownership endpoints. It does not fetch
issuer mappings, annual holdings, history, or run portfolio analysis.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import re
import tempfile
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCHEMA = "nps-diagnostic-v1"


def _nps():
    from api.collectors import nps_holdings
    return nps_holdings


def file_hash(path):
    p = Path(path)
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None


def code_hash():
    nps = _nps()
    return hashlib.sha256(Path(nps.__file__).read_bytes() + Path(__file__).read_bytes()).hexdigest()


@contextmanager
def collection_lock():
    import fcntl
    identity = hashlib.sha256(os.path.realpath(_nps().OUTPUT_PATH).encode()).hexdigest()[:20]
    path = Path(tempfile.gettempdir()) / ("nps-holdings-" + identity + ".lock")
    with path.open("a") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def target_record(ticker, event, *, stage):
    return {"ticker": ticker, "event_date": event.get("event_date"),
            "event_receipt": event.get("event_receipt"), "corp_code": None,
            "status": "unresolved", "stage": stage, "endpoints": [],
            "last_parsed_date": None, "last_parsed_receipt": None}


def endpoint_record(endpoint):
    return {"endpoint": endpoint, "stage": "request", "http_status": None,
            "api_status": None, "exception_class": None}


def begin_diagnostic():
    nps = _nps()
    return {"schema": SCHEMA, "captured_at": datetime.now(timezone.utc).isoformat(),
            "baseline_sha256": file_hash(nps.OUTPUT_PATH),
            "catalyst_sha256": file_hash(nps.CATALYST_PATH),
            "collector_sha256": code_hash(), "status": "started", "targets": []}


def _valid_diagnostic_path(path):
    if path is None:
        return
    nps = _nps()
    forbidden = (nps.OUTPUT_PATH, nps.CATALYST_PATH, nps.HEARTBEAT_PATH,
                 nps.NAMES_PATH, nps.PORTFOLIO_PATH, nps.ANNUAL_SEED_PATH,
                 os.path.join(nps._ROOT, "data", "mapping.json"))
    if os.path.realpath(path) in {os.path.realpath(p) for p in forbidden}:
        raise ValueError("diagnostic_path_overlaps_source")


def finish_diagnostic(doc, audit, path):
    nps = _nps()
    _valid_diagnostic_path(path)
    if "_target_diagnostics" in audit:
        doc["targets"] = audit.pop("_target_diagnostics")
        doc["resolved_updates"] = audit.pop("_resolved_updates", {})
        doc["resolved_retired"] = audit.pop("_resolved_retired", [])
    keys = ("event_source_ok", "event_source_rows", "event_source_invalid_rows", "event_source_latest",
            "event_tickers", "candidate_tickers", "updated_tickers", "retired_tickers", "unresolved_tickers", "api_calls")
    doc["audit"] = {key: audit[key] for key in keys if key in audit}
    doc["status"] = "failed" if doc.get("exception_class") or audit.get("event_source_ok") is False or audit.get("unresolved_tickers", 0) else "ok"
    doc["source_changed_during_collection"] = file_hash(nps.CATALYST_PATH) != doc["catalyst_sha256"]
    for row in doc.get("targets", []):
        if row.get("status") == "unresolved":
            print("[nps_holdings] target_diagnostic=" + json.dumps(row, ensure_ascii=False, sort_keys=True))
    if path:
        nps._write_json(os.path.abspath(path), doc)
    return doc


def _reject(doc, path, reason):
    doc.update(status="recovery_rejected", recovery_reason=reason)
    if path:
        _valid_diagnostic_path(path)
        _nps()._write_json(os.path.abspath(path), doc)
    print("[nps_holdings] target recovery rejected: " + reason)
    return 3


def retry_unresolved(diagnostic_path, *, diagnostics_path):
    """Exactly one request per existing endpoint per unresolved target, no loop."""
    nps = _nps()
    _valid_diagnostic_path(diagnostics_path)
    if os.path.realpath(diagnostic_path) == os.path.realpath(diagnostics_path):
        raise ValueError("retry_diagnostic_requires_new_output_path")
    with collection_lock():
        doc = nps._load_json(diagnostic_path, {})
        attempt = begin_diagnostic()
        attempt["retry_of_sha256"] = file_hash(diagnostic_path)
        if not isinstance(doc, dict) or doc.get("schema") != SCHEMA or doc.get("status") != "failed":
            return _reject(attempt, diagnostics_path, "not_a_failed_diagnostic")
        try:
            captured = datetime.fromisoformat(doc["captured_at"])
            age = datetime.now(timezone.utc) - captured
            if not timedelta(0) <= age <= timedelta(hours=24):
                raise ValueError("age")
        except (ValueError, TypeError, KeyError):
            return _reject(attempt, diagnostics_path, "diagnostic_time_invalid_or_older_than_24h")
        for key in ("baseline_sha256", "catalyst_sha256", "collector_sha256"):
            if not doc.get(key) or doc[key] != attempt[key]:
                return _reject(attempt, diagnostics_path, key + "_changed")
        if doc.get("source_changed_during_collection"):
            return _reject(attempt, diagnostics_path, "original_source_changed_during_collection")
        previous = nps._load_json(nps.OUTPUT_PATH, {})
        if not isinstance(previous, dict) or not isinstance(previous.get("holdings"), list):
            return _reject(attempt, diagnostics_path, "last_good_holdings_missing")
        baseline = {str(row.get("ticker")): dict(row) for row in previous["holdings"] if isinstance(row, dict)}
        events, source_audit = nps._nps_catalyst_events()
        if not source_audit.get("event_source_ok"):
            return _reject(attempt, diagnostics_path, "event_source_invalid")
        targets, resolved = {}, {}
        records = doc.get("targets")
        if not isinstance(records, list) or not records:
            return _reject(attempt, diagnostics_path, "target_records_missing")
        for row in records:
            if not isinstance(row, dict):
                return _reject(attempt, diagnostics_path, "target_record_invalid")
            tk = row.get("ticker")
            if not isinstance(tk, str):
                return _reject(attempt, diagnostics_path, "target_record_invalid")
            event = events.get(tk)
            if (not isinstance(tk, str) or not re.fullmatch(r"\d{6}", tk)
                    or not event or not re.fullmatch(r"\d{14}", str(row.get("event_receipt") or ""))
                    or event.get("event_date") != row.get("event_date")
                    or event.get("event_receipt") != row.get("event_receipt")
                    or row["event_receipt"][:8] != row.get("event_date")):
                return _reject(attempt, diagnostics_path, "target_event_identity_changed_or_missing")
            if nps._date_key((baseline.get(tk) or {}).get("date")) >= event["event_date"]:
                return _reject(attempt, diagnostics_path, "target_already_covered_by_newer_output")
            if row.get("status") == "unresolved":
                targets[tk] = event
            elif row.get("status") == "resolved" and row.get("last_parsed_receipt") == event["event_receipt"]:
                resolved[tk] = row
            else:
                return _reject(attempt, diagnostics_path, "cached_resolution_receipt_unverified")
        if not targets:
            return _reject(attempt, diagnostics_path, "no_failed_targets")
        pending = {tk for tk, event in events.items() if event["event_date"] > nps._date_key((baseline.get(tk) or {}).get("date"))}
        if pending - (set(targets) | set(resolved)):
            return _reject(attempt, diagnostics_path, "other_pending_events_not_covered")
        mapping = nps._load_json(os.path.join(nps._ROOT, "data", "mapping.json"), {})
        if not isinstance(mapping, dict):
            return _reject(attempt, diagnostics_path, "local_mapping_invalid")
        for row in records:
            if row["ticker"] in targets and (not re.fullmatch(r"\d{8}", str(mapping.get(row["ticker"]) or ""))
                    or row.get("corp_code") not in (None, mapping.get(row["ticker"]))):
                return _reject(attempt, diagnostics_path, "local_corp_identity_changed_or_missing")
        cached = doc.get("resolved_updates") or {}
        retired_values = doc.get("resolved_retired") or []
        if not isinstance(cached, dict) or not isinstance(retired_values, list) or any(not isinstance(tk, str) for tk in retired_values):
            return _reject(attempt, diagnostics_path, "cached_public_fact_invalid")
        retired_cached = set(retired_values)
        if retired_cached - set(resolved):
            return _reject(attempt, diagnostics_path, "cached_retirement_identity_invalid")
        for tk in resolved:
            row = cached.get(tk)
            if tk in retired_cached:
                baseline.pop(tk, None)
            elif (not isinstance(row, dict) or set(row) - {"ticker", "name", "pct", "qty_change", "date", "src"}
                  or row.get("ticker") != tk
                  or not isinstance(row.get("pct"), (int, float)) or isinstance(row.get("pct"), bool)
                  or not math.isfinite(row["pct"]) or not 0 < row["pct"] <= 100
                  or nps._date_key(row.get("date")) < events[tk]["event_date"]
                  or row.get("src") not in ("DART majorstock live", "DART elestock live")):
                return _reject(attempt, diagnostics_path, "cached_public_fact_invalid")
            else:
                baseline[tk] = dict(row)
        updates, retired, audit = nps._from_dart_live({}, baseline, only_events=targets, corp_codes=mapping)
        finish_diagnostic(attempt, audit, diagnostics_path)
        if audit.get("unresolved_tickers") or audit.get("event_source_ok") is False:
            return 2
        # Recheck both source files after network latency. A newer writer wins.
        if file_hash(nps.OUTPUT_PATH) != doc["baseline_sha256"] or file_hash(nps.CATALYST_PATH) != doc["catalyst_sha256"]:
            return _reject(attempt, diagnostics_path, "source_or_output_changed_during_retry")
        for tk in retired:
            baseline.pop(tk, None)
        baseline.update(updates)
        result = copy.deepcopy(previous)
        result["holdings"] = sorted(baseline.values(), key=lambda row: (-(row.get("pct") or 0), row.get("ticker") or ""))
        result["count"] = len(result["holdings"])
        result["as_of_latest"] = max((nps._iso_date(row.get("date")) for row in result["holdings"]), default="")
        result["source_counts"] = {}
        for row in result["holdings"]:
            source = str(row.get("src") or "unknown")
            result["source_counts"][source] = result["source_counts"].get(source, 0) + 1
        audit["candidate_tickers"] += len(resolved)
        audit["updated_tickers"] += len(resolved) - len(retired_cached)
        audit["retired_tickers"] += len(retired_cached)
        result["dart_check"] = result["dart_refresh"] = audit
        result["generated_at"] = datetime.now(timezone(timedelta(hours=9))).isoformat()
        nps._write_json(nps.OUTPUT_PATH, result)
        nps._write_success_heartbeat(result, audit)
        print("[nps_holdings] target recovery complete: " + str(len(targets)) + " target(s)")
        return 0


def cli():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--diagnostics", help="Private sanitized diagnostic JSON; never a public source path")
    parser.add_argument("--retry-unresolved", help="One explicit target-only attempt from a failed diagnostic")
    args = parser.parse_args()
    _valid_diagnostic_path(args.diagnostics)
    if args.retry_unresolved:
        if not args.diagnostics:
            parser.error("--retry-unresolved requires a distinct --diagnostics output")
        return retry_unresolved(args.retry_unresolved, diagnostics_path=args.diagnostics)
    return _nps().main(diagnostics_path=args.diagnostics)
