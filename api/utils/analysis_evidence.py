"""Private, deterministic observations of analysis inputs and output differences.

No pricing, scoring, source attribution, or historical reconstruction happens here.
Capture time is deliberately distinct from an explicitly supplied quote time.
"""
from collections import Counter
from copy import deepcopy
from datetime import datetime
import hashlib
import json
import math
import sys

from numpy import bool_ as numpy_bool


_OUTPUTS = frozenset({
    "analysis_change", "evidence_snapshot", "rec_price_evidence", "source_alignment",
    "verity_brain", "score_breakdown", "brain_score", "raw_brain_score",
    "brain_score_pre_macro", "recommendation", "ai_verdict", "display_verdict",
    "analyst_view", "account_route", "trade_plan", "current_price", "rec_price",
    "_carried", "_gemini_model",
})
_DISCLOSURES = frozenset({"sec_financials", "dart_financials", "fundamental_source_evidence",
                           "dart_business_report", "dart_report_analysis"})
# Only fixed producer field names may appear in public runtime diagnostics.
_DIAGNOSTIC_FIELDS = frozenset({"technical", "quant_factors", "backtest", "prediction",
                                "timing", "sec_financials", "dart_financials",
                                "fundamental_source_evidence"})


def _dict(value):
    return value if isinstance(value, dict) else {}


class _UnsupportedInputType(TypeError):
    def __init__(self, value, path):
        self.type_name = f"{type(value).__module__}.{type(value).__name__}"
        self.path = path
        super().__init__("analysis evidence requires supported JSON input types")


def _json_value(value, path="$"):
    # backtest_stock emits numpy.bool_ for recent_trades[].win (ret > 0).
    # Convert only this proven scalar; bool remains distinct from numeric 0/1.
    if isinstance(value, numpy_bool):
        return bool(value)
    if isinstance(value, float) and not math.isfinite(value):
        return {"nonfinite": str(value)}
    if isinstance(value, dict):
        return {str(k): _json_value(v, f"{path}.field[{i}]")
                for i, (k, v) in enumerate(value.items())}
    if isinstance(value, (list, tuple)):
        return [_json_value(v, f"{path}[{i}]") for i, v in enumerate(value)]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise _UnsupportedInputType(value, path)


def _hash(value):
    body = json.dumps(_json_value(value), sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def verify_input_snapshot(evidence):
    """Recompute a persisted private snapshot's documented canonical JSON digest."""
    try:
        return (isinstance(evidence, dict)
                and evidence.get("hash_scope") == "pre_brain_candidate_inputs_v1"
                and isinstance(evidence.get("input_snapshot"), dict)
                and evidence.get("input_hash") == _hash(evidence["input_snapshot"]))
    except (TypeError, ValueError):
        return False


def _identity(stock):
    ticker, currency = stock.get("ticker"), stock.get("currency")
    if not isinstance(ticker, str) or not ticker or not isinstance(currency, str) or not currency:
        return None
    return ticker, currency  # No ticker normalization or currency inference.


def _index(records):
    groups = {}
    for record in records:
        if isinstance(record, dict) and _identity(record):
            groups.setdefault(_identity(record), []).append(record)
    return {key: rows[0] for key, rows in groups.items() if len(rows) == 1}, {
        key for key, rows in groups.items() if len(rows) > 1}


def capture_previous_analysis(portfolio):
    """Freeze the load-time baseline before main mutates carried records in place."""
    return deepcopy({"recommendations": portfolio.get("recommendations") or [],
                     "analysis_provenance": portfolio.get("analysis_provenance") or {}})


def capture_analysis_inputs(records, portfolio):
    """Exact pre-Brain candidate projection, plus the existing macro context.

    input_snapshot stays private and allows the immutable run artifact to preserve
    values, not just an unverifiable digest. This scope is not all process state.
    """
    unique, duplicates = _index(records)
    snapshots = {}
    try:
        context = {key: _json_value(portfolio.get(key), f"context.{key}")
                   for key in ("macro", "market_summary")}
        for key, record in unique.items():
            inputs = {name: _json_value(value, f"candidate.{name}" if name in _DIAGNOSTIC_FIELDS
                                       else f"candidate.field[{i}]")
                      for i, (name, value) in enumerate(record.items()) if name not in _OUTPUTS}
            snapshot = {"candidate": inputs, "context": context}
            snapshots[key] = {"input_hash": _hash(snapshot), "input_snapshot": snapshot,
                              "input_field_hashes": {name: _hash(value) for name, value in inputs.items()},
                              "context_hash": _hash(context)}
    except _UnsupportedInputType as exc:
        # No value repr, ticker, record identity, or source body in diagnostics.
        print("[analysis_evidence] unsupported_input " + json.dumps({
            "type": exc.type_name, "path": exc.path,
        }, ensure_ascii=True), file=sys.stderr)
        raise
    return {"records": snapshots, "duplicates": duplicates, "candidate_count": len(records)}


def _measurement(stock):
    brain = _dict(stock.get("verity_brain"))
    scope = _dict(_dict(brain.get("fact_score")).get("coverage_scope"))
    alignment = _dict(scope.get("source_alignment") or stock.get("source_alignment"))
    counts = Counter(_dict(v).get("status", "unknown")
                     for v in _dict(alignment.get("fields")).values())
    missing = stock.get("fundamental_missing_fields")
    return {"data_coverage": brain.get("data_coverage"),
            "component_states": deepcopy(_dict(scope.get("component_states"))),
            "fundamental_missing_fields": sorted(k for k, v in missing.items() if v)
            if isinstance(missing, dict) else deepcopy(missing),
            "source_alignment_status": alignment.get("status", "unknown"),
            "source_alignment_counts": {k: counts[k] for k in
                                        ("aligned", "partial", "mismatch", "unknown", "missing")}}


def _observations(stock):
    brain = _dict(stock.get("verity_brain"))
    return {"grade": brain.get("grade"), "recommendation": stock.get("recommendation"),
            "scores": {"brain_score": brain.get("brain_score"),
                       "fact_score": _dict(brain.get("fact_score")).get("score"),
                       "sentiment_score": _dict(brain.get("sentiment_score")).get("score")},
            "price": stock.get("price"), "measurement": _measurement(stock)}


def _run(provenance, mode):
    return {"run_id": provenance.get("analysis_run_id"),
            "run_attempt": provenance.get("analysis_run_attempt"), "mode": mode,
            "scan_id": provenance.get("scan_id"), "scan_as_of": provenance.get("source_as_of"),
            "scan_completed_at": provenance.get("completed_at"),
            "scan_snapshot_sha256": provenance.get("snapshot_sha256")}


def _valid_price(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0


def _timestamp(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo is not None else None
    except ValueError:
        return None


def _quote(stock, captured_at=None):
    # Never substitute collection/capture time for quote time or infer adjustment.
    as_of = stock.get("price_as_of") or stock.get("price_timestamp")
    parsed = _timestamp(as_of)
    capture_time = _timestamp(captured_at)
    as_of = as_of if parsed else None
    source = stock.get("price_source")
    adjustment = stock.get("price_adjustment")
    reasons = []
    if not _valid_price(stock.get("price")):
        reasons.append("price_missing_or_invalid")
    if not as_of:
        reasons.append("quote_timestamp_missing_or_invalid")
    if parsed and capture_time and parsed > capture_time:
        reasons.append("quote_timestamp_after_capture")
    if not isinstance(source, str) or not source or source == "unknown":
        reasons.append("price_source_unknown")
    if not isinstance(adjustment, (str, bool)) or adjustment == "unknown" or adjustment == "":
        reasons.append("price_adjustment_unknown")
    return {"value": stock.get("price") if _valid_price(stock.get("price")) else None, "as_of": as_of,
            "source": source if isinstance(source, str) and source else "unknown",
            "adjustment": adjustment if isinstance(adjustment, (str, bool)) else "unknown",
            "status": "missing" if not _valid_price(stock.get("price")) else
                      "captured" if not reasons else "unknown", "reasons": reasons}


def mark_analysis_evidence_unavailable(records, provenance, captured_at, mode, error_type):
    """Replace all partial/stale diagnostics after a batch capture failure."""
    run = _run(_dict(provenance), mode)
    for stock in records:
        if not isinstance(stock, dict):
            continue
        identity = {"ticker": stock.get("ticker"), "currency": stock.get("currency")}
        stock["analysis_change"] = {"schema": "analysis-change-v1", "status": "unavailable",
            "changes": {}, "reasons": ["diagnostic_capture_failed"], "previous_completed_at": None,
            "observed_differences_only": True}
        stock["evidence_snapshot"] = {"schema": "analysis-evidence-v1", **identity,
            "captured_at": captured_at, "run": deepcopy(run), "input_hash": None,
            "reason": "diagnostic_capture_failed", "price": _quote(stock, captured_at)}
        stock["rec_price_evidence"] = {"schema": "rec-price-evidence-v1", **identity,
            "value": stock.get("rec_price") if _valid_price(stock.get("rec_price")) else None,
            "status": "unknown" if _valid_price(stock.get("rec_price")) else "missing",
            "captured_at": None, "quote_as_of": None, "source": "unknown", "adjustment": "unknown",
            "reason": "diagnostic_capture_failed", "run": None}
    return {"schema": "analysis-changes-v1", "status": "unavailable",
            "current_count": len(records), "compared_count": 0, "unresolved_count": len(records),
            "reasons": {"diagnostic_capture_failed": len(records)}, "error_type": error_type,
            "observed_differences_only": True}


def attach_analysis_evidence(records, previous, inputs, provenance, captured_at, mode,
                             new_rec_price_ids=()):
    """Attach diagnostics only; return denominator-preserving cohort counts."""
    old_records = previous.get("recommendations") or []
    old, old_duplicates = _index(old_records)
    current, current_duplicates = _index(records)
    previous_provenance = _dict(previous.get("analysis_provenance"))
    completed = previous_provenance.get("status") == "completed"
    counts = Counter()
    reasons = Counter()
    run = _run(provenance, mode)
    for stock in records:
        if not isinstance(stock, dict):
            counts["unresolved"] += 1
            reasons["invalid_record"] += 1
            continue
        key = _identity(stock)
        prior = old.get(key)
        captured = inputs["records"].get(key, {})
        quote = _quote(stock, captured_at)
        snapshot = {"schema": "analysis-evidence-v1", "ticker": stock.get("ticker"),
                    "currency": stock.get("currency"), "captured_at": captured_at,
                    "analysis_as_of": provenance.get("source_as_of"), "price": quote,
                    "hash_scope": "pre_brain_candidate_inputs_v1", "run": deepcopy(run),
                    "hash_algorithm": "sha256-canonical-json-sort-keys-utf8-v1",
                    "observations": _observations(stock),
                    **deepcopy(captured)}
        if not captured:
            snapshot["reason"] = "ambiguous_input_identity" if key in inputs["duplicates"] else "input_snapshot_unavailable"
            snapshot["input_hash"] = None
        stock["evidence_snapshot"] = snapshot

        rec_price = stock.get("rec_price")
        existing = stock.get("rec_price_evidence")
        if not isinstance(existing, dict) and prior:
            existing = prior.get("rec_price_evidence")
        valid_origin = (key is not None and _valid_price(rec_price) and isinstance(existing, dict)
                        and existing.get("schema") == "rec-price-evidence-v1"
                        and (existing.get("ticker"), existing.get("currency")) == key
                        and existing.get("value") == rec_price
                        and existing.get("status") in ("captured", "unknown")
                        and (existing.get("captured_at") is None or _timestamp(existing.get("captured_at")))
                        and (existing.get("quote_as_of") is None or _timestamp(existing.get("quote_as_of"))))
        if valid_origin and existing.get("status") == "captured":
            origin_quote = _quote({"price": rec_price, "price_as_of": existing.get("quote_as_of"),
                                   "price_source": existing.get("source"),
                                   "price_adjustment": existing.get("adjustment")}, existing.get("captured_at"))
            valid_origin = bool(_timestamp(existing.get("captured_at"))) and origin_quote["status"] == "captured"
        if valid_origin:
            stock["rec_price_evidence"] = deepcopy(existing)
        else:
            is_new = key is not None and key in new_rec_price_ids and key not in current_duplicates
            stock["rec_price_evidence"] = {
                "schema": "rec-price-evidence-v1", "ticker": stock.get("ticker"),
                "currency": stock.get("currency"), "value": rec_price if _valid_price(rec_price) else None,
                "status": "missing" if not _valid_price(rec_price) else quote["status"]
                          if is_new and rec_price == quote["value"] else "unknown",
                "captured_at": captured_at if is_new else None,
                "quote_as_of": quote["as_of"] if is_new else None,
                "source": quote["source"] if is_new else "unknown",
                "adjustment": quote["adjustment"] if is_new else "unknown",
                "reason": "first_observed_rec_price" if is_new else "legacy_origin_unavailable",
                "quote_reasons": deepcopy(quote["reasons"]) if is_new else ["legacy_origin_unavailable"],
                "run": deepcopy(run) if is_new else None}

        change = {"schema": "analysis-change-v1", "status": "unavailable", "changes": {},
                  "previous_completed_at": previous_provenance.get("analysis_completed_at") if completed else None,
                  "reasons": [], "observed_differences_only": True}
        reason = ("missing_identity" if key is None else
                  "ambiguous_identity" if key in old_duplicates or key in current_duplicates else
                  "previous_analysis_not_completed" if not completed else
                  "new_identity" if prior is None else None)
        if reason:
            change["reasons"].append(reason)
            counts["unresolved"] += 1
            reasons[reason] += 1
        else:
            counts["compared"] += 1
            old_snapshot = _dict(prior.get("evidence_snapshot"))
            saved_observations = old_snapshot.get("observations")
            saved_identity = (old_snapshot.get("ticker"), old_snapshot.get("currency"))
            has_saved_observations = (old_snapshot.get("schema") == "analysis-evidence-v1"
                                      and saved_identity == key and isinstance(saved_observations, dict)
                                      and set(saved_observations) == set(_observations(stock)))
            before = saved_observations if has_saved_observations else _observations(prior)
            after = _observations(stock)
            for name in before:
                if name == "price" and not has_saved_observations:
                    change["reasons"].append("previous_analysis_price_observation_unavailable")
                    reasons["previous_analysis_price_observation_unavailable"] += 1
                    continue
                if name == "price":
                    counts["price_compared"] += 1
                if before[name] != after[name]:
                    change["changes"][name] = {"before": before[name], "after": after[name]}
            old_hashes = old_snapshot.get("input_field_hashes")
            new_hashes = captured.get("input_field_hashes")
            old_candidate = _dict(_dict(old_snapshot.get("input_snapshot")).get("candidate"))
            old_hashes_valid = (isinstance(old_hashes, dict) and verify_input_snapshot(old_snapshot)
                               and saved_identity == key
                               and old_hashes == {name: _hash(value) for name, value in old_candidate.items()}
                               and old_snapshot.get("context_hash") == _hash(old_snapshot["input_snapshot"].get("context")))
            if old_hashes_valid and isinstance(new_hashes, dict):
                counts["inputs_compared"] += 1
                changed = sorted(k for k in old_hashes.keys() | new_hashes.keys()
                                 if old_hashes.get(k) != new_hashes.get(k))
                if changed or old_snapshot.get("context_hash") != captured.get("context_hash"):
                    change["changes"]["inputs"] = {"changed_fields": changed,
                        "changed_field_count": len(changed),
                        "context_changed": old_snapshot.get("context_hash") != captured.get("context_hash")}
                disclosure_changes = [k for k in changed if k in _DISCLOSURES]
                if disclosure_changes:
                    change["changes"]["disclosures"] = {"changed_fields": disclosure_changes,
                                                               "changed_field_count": len(disclosure_changes)}
            else:
                change["reasons"].append("previous_or_current_input_snapshot_unavailable")
                reasons["previous_or_current_input_snapshot_unavailable"] += 1
            change["status"] = "changed" if change["changes"] else "unchanged"
            counts[change["status"]] += 1
        stock["analysis_change"] = change
    return {"schema": "analysis-changes-v1", "previous_status": previous_provenance.get("status", "unknown"),
            "baseline_source": previous.get("baseline_source", "unknown"),
            "baseline_reason": previous.get("baseline_reason"),
            "current_count": len(records), "previous_count": len(old_records),
            "compared_count": counts["compared"], "changed_count": counts["changed"],
            "unchanged_count": counts["unchanged"], "unresolved_count": counts["unresolved"],
            "price_compared_count": counts["price_compared"],
            "input_compared_count": counts["inputs_compared"],
            "input_snapshot_count": sum(bool(_dict(r).get("evidence_snapshot", {}).get("input_hash"))
                                        for r in records if isinstance(r, dict)),
            "new_count": len(current.keys() - old.keys() - old_duplicates) if completed else None,
            "removed_count": len(old.keys() - current.keys() - current_duplicates) if completed else None,
            "reasons": dict(reasons), "observed_differences_only": True}
