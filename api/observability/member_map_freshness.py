"""Minute-level delivery evidence, separate from a document's reporting period.

These are product delivery targets, not investment scores or achieved SLAs.
Never substitute file mtime, generation time or first observation for publication.
"""
from datetime import datetime, timezone

POLL_SECONDS = {"SEC": 120, "DART": 120, "news": 300}
TARGET_SECONDS = {
    "important": {"facts": 300, "analysis": 900},
    "ordinary": {"facts": 900, "analysis": 1800},
    "complex": {"facts": 300, "analysis": 3600},
}


def instant(value):
    if not isinstance(value, str) or "T" not in value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo is not None else None


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


def delivery_evidence(event, *, now, priority="ordinary"):
    """A client receipt proves screen delivery; server publication alone does not.

    first_seen_at measures OUR processing only. Public availability must be an
    independently supplied exact timestamp; a date-only source stays unknown.
    analysis_visible_at means a review-accepted analysis was actually displayed.
    """
    current = instant(now)
    if priority not in TARGET_SECONDS or current is None:
        raise ValueError("freshness-input")
    available = instant(event.get("source_available_at"))
    observed = instant(event.get("first_seen_at"))
    if any(value is not None and value > current for value in (available, observed)):
        return {"status": "invalid-clock", "facts": None, "analysis": None}
    if available is not None and observed is not None and observed < available:
        return {"status": "invalid-clock", "facts": None, "analysis": None}
    origin = available or observed
    basis = "source-available" if available else "first-observed-only" if observed else "unknown"
    result = {"status": "measured" if origin else "unknown", "basis": basis,
              "end_to_end_measurable": available is not None, "targets": TARGET_SECONDS[priority].copy()}
    for lane, field in (("facts", "facts_visible_at"), ("analysis", "analysis_visible_at")):
        visible = instant(event.get(field))
        if origin is None:
            result[lane] = {"status": "unknown", "delay_seconds": None}
            continue
        if (event.get(field) is not None and visible is None) or (visible is not None and
                (visible < origin or visible > current or (observed is not None and visible < observed))):
            result[lane] = {"status": "invalid-clock", "delay_seconds": None}
            continue
        elapsed = ((visible or current) - origin).total_seconds()
        status = ("on-time" if elapsed <= TARGET_SECONDS[priority][lane] else "late") if visible else (
            "pending" if elapsed <= TARGET_SECONDS[priority][lane] else "overdue")
        result[lane] = {"status": status, "delay_seconds": elapsed}
    return result
