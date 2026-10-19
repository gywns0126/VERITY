"""Observe US automatic-slot workflow delivery; never collect or dispatch data.

PASS proves only the shared helper's source/quality/save/Publish step contract.
It is not independent acceptance of source freshness or published data quality.
"""
from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
HEALTH_PATH = ROOT / "data/metadata/us_financials_schedule_health.json"
MISSING_GRACE_MINUTES = 30
ACTIVE_LIMIT_MINUTES = 45
STATUSES = {"delivered", "active", "missing", "failed", "attempt_limit"}


def _load_helper():
    path = ROOT / "vercel-api/us_financials_schedule.py"
    spec = importlib.util.spec_from_file_location("us_financials_schedule", path)
    if spec is None or spec.loader is None:
        raise ImportError("schedule helper unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _utc(value):
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timezone required")
    return parsed.astimezone(timezone.utc)


def _iso(value):
    return _utc(value).isoformat().replace("+00:00", "Z")


def inspect(repo, token, now, helper=None):
    """Translate the shared slot inspection to a bounded monitor verdict."""
    now = _utc(now)
    report = {
        "checked_at": _iso(now), "slot": None, "status": "unknown",
        "severity": "UNKNOWN", "acceptance_scope": "workflow_delivery_only",
        "inspected_runs": [], "attempt_count": None, "delivery_run_id": None,
    }
    try:
        helper = helper or _load_helper()
        slot = _utc(helper.latest_slot(now))
        report["slot"] = _iso(slot)
        if slot > now:
            raise ValueError("future slot")
        if not repo or not token:
            raise ValueError("GitHub configuration unavailable")
        result = helper.inspect_slot(repo, token, slot, now)
        status = result["status"]
        if status not in STATUSES or _utc(result["slot"]) != slot:
            raise ValueError("invalid slot inspection")
        runs = result["inspected_runs"]
        if not isinstance(runs, list) or any(not isinstance(run, dict) for run in runs):
            raise ValueError("invalid inspected runs")
        attempts = result["attempt_count"]
        if isinstance(attempts, bool) or not isinstance(attempts, int) or attempts < 0:
            raise ValueError("invalid attempt count")
        # Persist only public Actions metadata, never arbitrary helper/API bodies.
        fields = ("id", "databaseId", "event", "status", "conclusion", "head_sha",
                  "head_branch", "created_at", "run_started_at", "updated_at",
                  "createdAt", "startedAt", "updatedAt", "html_url", "duplicate_noop")
        report.update(status=status, attempt_count=attempts,
                      expected_slot_count=1, inspected_run_count=len(runs),
                      inspected_runs=[{k: run[k] for k in fields if k in run} for run in runs],
                      delivery_run_id=result.get("delivery_run_id"))
        if status == "delivered":
            if not result.get("delivery_run_id"):
                raise ValueError("delivery run missing")
            report.update(severity="PASS", reason="required_workflow_steps_delivered")
        elif status == "missing":
            age = (now - slot).total_seconds() / 60
            report.update(slot_age_minutes=round(age, 2),
                          severity="FAIL" if age > MISSING_GRACE_MINUTES else "WARNING",
                          reason="missing_after_grace" if age > MISSING_GRACE_MINUTES else "within_grace")
        elif status == "active":
            active = [run for run in runs if run.get("status") != "completed"]
            if not active:
                raise ValueError("active run metadata missing")
            # Use creation time, not runner start: queue time is part of delivery delay.
            ages = [(now - _utc(run.get("created_at") or run.get("createdAt"))).total_seconds() / 60
                    for run in active]
            if min(ages) < 0:
                raise ValueError("future active run")
            age = max(ages)
            report.update(active_age_minutes=round(age, 2),
                          severity="FAIL" if age > ACTIVE_LIMIT_MINUTES else "WARNING",
                          reason="active_over_limit" if age > ACTIVE_LIMIT_MINUTES else "active_within_limit")
        else:
            report.update(severity="FAIL", reason=status)
    except Exception as exc:
        # Exception messages may include authenticated URLs or response bodies.
        report.update(status="unknown", severity="UNKNOWN", reason="inspection_unavailable",
                      error_type=type(exc).__name__)
    return report


def _read_alert_state(path):
    try:
        previous = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    state = previous.get("alert_state", {})
    if not isinstance(state, dict) or any(not isinstance(v, str) for v in state.values()):
        raise ValueError("invalid alert state")
    return state


def _write_health(path, report):
    path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=path.name + ".", delete=False) as handle:
            name = handle.name
            json.dump(report, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
        name = None
    finally:
        if name is not None:
            os.unlink(name)


def _send_alert(report):
    # The existing transport logs provider exceptions; do not expose authenticated
    # request URLs here. Emit only a fixed success/failure receipt at our boundary.
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        from api.notifications.telegram import send_message
        return send_message(
            "US financial automatic delivery incident\n"
            f"slot={report['slot']} status={report['status']} severity={report['severity']}\n"
            f"reason={report['reason']}\nworkflow delivery only; data acceptance not asserted",
            dedupe=False, bypass_quiet=True, source="us_financials_schedule_monitor",
        )


def monitor(repo, token, *, now=None, path=None, notify=False, helper=None, sender=None):
    path = Path(path) if path is not None else HEALTH_PATH
    now = now or datetime.now(timezone.utc)
    report = inspect(repo, token, now, helper)
    # Do not erase unreadable dedupe state and silently resend old incidents.
    report["alert_state"] = _read_alert_state(path)
    report["alert_outcome"] = "not_requested" if not notify else "not_incident"
    key = f"{report['slot']}|{report['status']}"
    incident = report["severity"] in {"FAIL", "UNKNOWN"} and report["slot"] is not None
    if notify and incident:
        report["alert_outcome"] = "already_sent" if key in report["alert_state"] else "pending"
    _write_health(path, report)
    if report["alert_outcome"] == "pending":
        try:
            sent = (sender or _send_alert)(report) is True
        except Exception:
            sent = False
        report["alert_outcome"] = "sent" if sent else "failed"
        if sent:
            report["alert_state"][key] = report["checked_at"]
        _write_health(path, report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--notify", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = monitor(os.environ.get("GITHUB_REPOSITORY", ""),
                         os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN", ""),
                         notify=args.notify)
    except Exception as exc:
        print(json.dumps({"status": "unknown", "severity": "UNKNOWN",
                          "reason": "health_state_unavailable", "error_type": type(exc).__name__}))
        return 1
    print(json.dumps(report, ensure_ascii=False, allow_nan=False))
    return 1 if report["severity"] in {"FAIL", "UNKNOWN"} else 0


if __name__ == "__main__":
    raise SystemExit(main())
