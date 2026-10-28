"""Pure collection receipts and minute-level delivery evidence.

Collection, source availability, first observation and client-visible delivery
are different clocks. Targets are product goals, never an achieved-SLA claim.
No helper reads a clock, feed, environment, file or remote service.
"""
from collections.abc import Mapping
from datetime import date, datetime, timezone
from math import ceil

POLL_SECONDS = {"SEC": 120, "DART": 120, "news": 300}
TARGET_SECONDS = {
    "important": {"facts": 300, "analysis": 900},
    "ordinary": {"facts": 900, "analysis": 1800},
    "complex": {"facts": 300, "analysis": 3600},
}
_CHECKPOINT_STATUSES = ("available", "retained", "read-failed", "not-read")
_SOURCE_STATUSES = ("success", "partial", "error", "initialized", "unknown")
_RECEIPT_SCHEMA = "member-map-collection-receipt/v1"
_LANES = (("facts", "facts_visible_at"), ("analysis", "analysis_visible_at"))


def instant(value):
    if not isinstance(value, str) or "T" not in value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo is not None else None
    except (ValueError, OverflowError):
        return None


def collection_health(source, *, last_success_at, now):
    """Successful empty checks count; failed attempts must not reset this clock."""
    current, success = instant(now), instant(last_success_at)
    if source not in POLL_SECONDS or current is None:
        raise ValueError("freshness-input")
    if success is None or success > current:
        return {"status": "unknown", "age_seconds": None}
    age = (current - success).total_seconds()
    return {"status": "on-time" if age <= POLL_SECONDS[source] else "delayed",
            "age_seconds": age}


def collection_receipt(states, *, now, checkpoint_status="available"):
    """Project only checkpoint metadata, including from metadata-only snapshots.

    Closed v1 shape: schema, checked_at (explicit evaluation time),
    checkpoint_status, sources (DART/SEC/news), screen_delivery_verified=False,
    analysis_delivery_verified=False. Each source has status, last_attempt_at,
    last_success_at and health={status, age_seconds}. Unknown/malformed statuses
    become unknown; absent, malformed and future timestamps become None.
    Inverted success/attempt clocks invalidate success, never reset it to now.
    No feed, error text, private content, receipt or achieved SLA is inferred.
    Age/checked_at are diagnostics and must stay outside content revisions.
    """
    current = instant(now)
    if (not isinstance(states, Mapping) or current is None
            or checkpoint_status not in _CHECKPOINT_STATUSES):
        raise ValueError("freshness-input")
    sources = {}
    for source in ("DART", "SEC", "news"):
        state = states.get(source)
        state = state if isinstance(state, Mapping) else {}
        status = state.get("status")
        status = status if type(status) is str and status in _SOURCE_STATUSES else "unknown"
        attempt, success = (instant(state.get(field)) for field in ("last_attempt_at", "last_success_at"))
        attempt = attempt if attempt is not None and attempt <= current else None
        success = success if success is not None and success <= current else None
        if attempt is not None and success is not None and success > attempt:
            success = None
        if status == "success" and success is None:
            status = "unknown"
        sources[source] = {
            "status": status,
            "last_attempt_at": attempt.isoformat() if attempt is not None else None,
            "last_success_at": success.isoformat() if success is not None else None,
            "health": collection_health(source, last_success_at=success.isoformat() if success else None, now=now),
        }
    return {"schema": _RECEIPT_SCHEMA, "checked_at": current.isoformat(),
            "checkpoint_status": checkpoint_status, "sources": sources,
            "screen_delivery_verified": False, "analysis_delivery_verified": False}


def validate_collection_receipt(receipt):
    """Return bool for the exact v1 JSON shape, without consulting a wall clock.

    Validate at the receipt's explicit checked_at, not the endpoint's call time.
    This checks internal consistency, not provenance or freshness at real time.
    """
    if type(receipt) is not dict or set(receipt) != {
            "schema", "checked_at", "checkpoint_status", "sources",
            "screen_delivery_verified", "analysis_delivery_verified"}:
        return False
    if (receipt["schema"] != _RECEIPT_SCHEMA
            or type(receipt["checkpoint_status"]) is not str
            or receipt["checkpoint_status"] not in _CHECKPOINT_STATUSES
            or receipt["screen_delivery_verified"] is not False
            or receipt["analysis_delivery_verified"] is not False
            or instant(receipt["checked_at"]) is None):
        return False
    sources = receipt["sources"]
    if type(sources) is not dict or set(sources) != {"DART", "SEC", "news"}:
        return False
    for state in sources.values():
        if type(state) is not dict or set(state) != {
                "status", "last_attempt_at", "last_success_at", "health"}:
            return False
        if type(state["status"]) is not str or state["status"] not in _SOURCE_STATUSES:
            return False
        for field in ("last_attempt_at", "last_success_at"):
            if state[field] is not None and instant(state[field]) is None:
                return False
        health = state["health"]
        if type(health) is not dict or set(health) != {"status", "age_seconds"}:
            return False
        if (type(health["status"]) is not str or health["status"] not in ("on-time", "delayed", "unknown")
                or (health["age_seconds"] is not None and type(health["age_seconds"]) not in (int, float))):
            return False
    expected = collection_receipt(sources, now=receipt["checked_at"],
                                  checkpoint_status=receipt["checkpoint_status"])
    return receipt == expected


def _source_clock(event):
    raw = event.get("source_available_at")
    available = instant(raw)
    day = None
    if type(raw) is str:
        try:
            day = date.fromisoformat(raw).isoformat()
        except ValueError:
            pass
    precision = event.get("source_precision")
    if precision is None:
        precision = "timestamp" if available is not None else "date" if day else "unknown"
    if type(precision) is not str or precision not in ("timestamp", "date", "unknown"):
        raise ValueError("freshness-input")
    invalid = raw is not None and available is None and day is None
    invalid = invalid or (precision == "timestamp" and raw is not None and available is None)
    invalid = invalid or (precision == "date" and raw is not None and day is None)
    # An unknown/date source never becomes an exact publication instant.
    return available if precision == "timestamp" else None, precision, invalid, day


def _lane_evidence(origin, visible, *, current, target, invalid=False):
    if invalid:
        return {"status": "invalid-clock", "delay_seconds": None}
    if origin is None:
        return {"status": "unknown", "delay_seconds": None}
    elapsed = ((visible if visible is not None else current) - origin).total_seconds()
    status = ("on-time" if elapsed <= target else "late") if visible is not None else (
        "pending" if elapsed <= target else "overdue")
    return {"status": status, "delay_seconds": elapsed}


def delivery_evidence(event, *, now, priority="ordinary"):
    """Evaluate one explicit event, preserving distinct evidence clocks.

    Inputs: source_available_at, source_precision (timestamp/date/unknown;
    inferred only from that supplied field if omitted), first_seen_at,
    facts_visible_at, analysis_visible_at. All instants must be aware ISO text.
    The two visible fields require explicit client receipts; neither generation,
    API delivery, atom.updated nor collection success supplies such a receipt.

    The original facts/analysis + basis contract is retained. source_available
    and first_observed hold independent lane measurements; timestamps preserves
    normalized supplied instants (a date-only source remains a date).
    Invalid source data is not silently replaced by an observation. Missing
    source precision can never be recovered from a generated/observation time.
    Analysis preceding a supplied facts receipt invalidates the analysis lane.
    now is used only for future checks and outstanding age, never as visibility.
    """
    current = instant(now)
    if (not isinstance(event, Mapping) or type(priority) is not str
            or priority not in TARGET_SECONDS or current is None):
        raise ValueError("freshness-input")
    available, precision, source_invalid, day = _source_clock(event)
    raw_available = instant(event.get("source_available_at"))
    observed = instant(event.get("first_seen_at"))
    observed_invalid = event.get("first_seen_at") is not None and observed is None
    inverted = available is not None and observed is not None and observed < available
    source_invalid = source_invalid or (raw_available is not None and raw_available > current) or inverted
    observed_invalid = observed_invalid or (observed is not None and observed > current) or inverted
    # A supplied observation is a lower bound for both delivery lanes.
    clocks_invalid = source_invalid or observed_invalid
    origin = available if available is not None else observed
    basis = "source-available" if available is not None else "first-observed-only" if observed else "unknown"
    timestamps = {"source_available_at": raw_available.isoformat() if raw_available else day,
                  "first_seen_at": observed.isoformat() if observed else None}
    result = {"status": "invalid-clock" if clocks_invalid else "measured" if origin else "unknown",
              "basis": basis, "source_precision": precision, "timestamps": timestamps,
              "end_to_end_measurable": available is not None and not clocks_invalid,
              "targets": TARGET_SECONDS[priority].copy(), "source_available": {}, "first_observed": {}}
    facts = instant(event.get("facts_visible_at"))
    for lane, field in _LANES:
        visible = instant(event.get(field))
        timestamps[field] = visible.isoformat() if visible is not None else None
        invalid = event.get(field) is not None and visible is None
        invalid = invalid or (visible is not None and (
            visible > current or (available is not None and visible < available)
            or (observed is not None and visible < observed)))
        invalid = invalid or (lane == "analysis" and visible is not None
                              and facts is not None and visible < facts)
        for axis, start in (("source_available", available), ("first_observed", observed)):
            result[axis][lane] = _lane_evidence(start, visible, current=current,
                target=TARGET_SECONDS[priority][lane], invalid=invalid or clocks_invalid)
        result[lane] = result["source_available" if available is not None else "first_observed"][lane].copy()
    return result


def summarize_delivery_evidence(events, *, now, priority="ordinary"):
    """Aggregate only supplied events; never infer scope, receipts or SLA success.

    Rows are delivery_evidence inputs, with optional per-row priority overriding
    the default. No deduplication: the caller defines the batch denominator.
    Return events_total, source_precision_counts, source_available/first_observed
    -> facts/analysis -> eligible, completed, unknown, invalid, on_time, late,
    pending, overdue, p95_seconds, overdue_n, overdue_m.
    eligible = on_time + late + pending + overdue; completed = on_time + late;
    eligible + unknown + invalid = events_total for EACH axis/lane.
    p95 is nearest-rank ceil(.95*N), using only completed delays on that axis.
    overdue_n/m = overdue / (pending + overdue), never / delivered samples.
    Empty samples yield p95=None and 0/0, not evidence of achieved targets.
    """
    if (instant(now) is None or type(priority) is not str or priority not in TARGET_SECONDS
            or isinstance(events, (str, bytes, Mapping))):
        raise ValueError("freshness-input")
    result = {"events_total": 0, "source_precision_counts": {"timestamp": 0, "date": 0, "unknown": 0}}
    samples = {}
    for axis in ("source_available", "first_observed"):
        result[axis] = {}
        for lane, _ in _LANES:
            result[axis][lane] = dict.fromkeys(
                ("eligible", "completed", "unknown", "invalid", "on_time", "late", "pending", "overdue"), 0)
            samples[axis, lane] = []
    for event in events:
        if not isinstance(event, Mapping):
            raise ValueError("freshness-input")
        evidence = delivery_evidence(event, now=now, priority=event.get("priority", priority))
        result["events_total"] += 1
        result["source_precision_counts"][evidence["source_precision"]] += 1
        for axis in ("source_available", "first_observed"):
            for lane, _ in _LANES:
                measurement = evidence[axis][lane]
                status = measurement["status"]
                stats = result[axis][lane]
                stats[{"on-time": "on_time", "invalid-clock": "invalid"}.get(status, status)] += 1
                if status in ("on-time", "late", "pending", "overdue"):
                    stats["eligible"] += 1
                if status in ("on-time", "late"):
                    stats["completed"] += 1
                    samples[axis, lane].append(measurement["delay_seconds"])
    for (axis, lane), values in samples.items():
        values.sort()
        stats = result[axis][lane]
        stats.update(p95_seconds=values[ceil(.95 * len(values)) - 1] if values else None,
                     overdue_n=stats["overdue"], overdue_m=stats["pending"] + stats["overdue"])
    return result
