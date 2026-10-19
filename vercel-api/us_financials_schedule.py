"""US financial daily delivery: bounded GitHub reads, duplicate guard and receipts.

The existing Vercel clock owns dispatch. A successful workflow label alone is
not a receipt: the collector, quality gate, main push and publisher must run.
This proves workflow delivery, not independent freshness of every financial row.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import urllib.parse
import urllib.request

WORKFLOW = "us_financials_incremental.yml"
EVENT = "us_financials_incremental"
MAX_ATTEMPTS = 2
GUARD_STEP = "US financial daily slot guard"
REQUIRED_STEPS = (
    GUARD_STEP,
    "10-K/Q 이벤트 감지 + 해당 종목 재수집",
    "커버리지 발행 검사 (WARN 허용, 핵심 결함 차단)",
    "Commit + push (변경 시만)",
    "Publish (VERITY-data + Vercel Blob)",
)


def latest_slot(now: datetime) -> datetime:
    """Most recent weekday 10:30 UTC; never manufacture a future due slot."""
    now = now.astimezone(timezone.utc)
    slot = now.replace(hour=10, minute=30, second=0, microsecond=0)
    if slot > now:
        slot -= timedelta(days=1)
    while slot.weekday() > 4:
        slot -= timedelta(days=1)
    return slot


def dispatch_slot(now: datetime) -> datetime | None:
    """Reuse quarter-hour ticks, with a finite same-day recovery window."""
    now = now.astimezone(timezone.utc)
    if now.weekday() > 4 or now.minute % 15 >= 5:
        return None
    slot = now.replace(hour=10, minute=30, second=0, microsecond=0)
    end = now.replace(hour=14, minute=50, second=0, microsecond=0)
    return slot if slot <= now < end else None


def _read(repo: str, token: str, resource: str) -> dict:
    if not token:
        raise RuntimeError("GitHub read credential unavailable")
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/{resource}",
        headers={"Authorization": f"Bearer {token}",
                 "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28",
                 "User-Agent": "verity-us-financials-cadence/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=4) as response:
            doc = json.loads(response.read())
    except Exception as exc:
        # Never log request headers, raw upstream body or credentials.
        raise RuntimeError(f"GitHub cadence read failed: {type(exc).__name__}") from None
    if not isinstance(doc, dict):
        raise RuntimeError("Invalid GitHub cadence response")
    return doc


def inspect_slot(repo: str, token: str, slot: datetime, now: datetime,
                 exclude_run_id: int = 0) -> dict:
    """Inspect one automatic slot; API uncertainty must not create more work.

    Manual experiments do not consume an automatic day. The workflow rechecks
    after its existing serialized lock, so a late native cron cannot recollect
    after the dispatch path has already saved and published this slot.
    """
    end = min(now, slot + timedelta(days=1))
    query = urllib.parse.urlencode({
        "branch": "main", "per_page": 100,
        "created": f"{slot.isoformat()}..{end.isoformat()}",
    })
    doc = _read(repo, token, f"actions/workflows/{WORKFLOW}/runs?{query}")
    runs = doc.get("workflow_runs")
    if not isinstance(runs, list) or not isinstance(doc.get("total_count"), int):
        raise RuntimeError("Invalid workflow inventory")
    if doc["total_count"] > len(runs):
        raise RuntimeError("Incomplete workflow inventory")
    eligible = [r for r in runs if r.get("event") in ("schedule", "repository_dispatch")
                and r.get("head_branch") == "main"
                and int(r["id"]) != exclude_run_id]
    result = {"slot": slot.isoformat(), "checked_at": now.isoformat(),
              "status": "missing", "attempt_count": 0, "inspected_runs": [],
              "delivery_run_id": None, "active_created_at": None}
    # At most two terminal attempts plus a current active run are expected.
    # A longer inventory is observable uncertainty, not an unbounded API loop.
    if len(eligible) > 8:
        raise RuntimeError("Automatic run inventory exceeds cadence bound")
    job_reads = 0
    for run in sorted(eligible, key=lambda r: int(r["id"]), reverse=True):
        record = {k: run.get(k) for k in ("id", "event", "status", "conclusion", "created_at", "head_sha")}
        result["inspected_runs"].append(record)
        if run.get("status") != "completed":
            # Lock admission need not follow ID order. A later queued run must
            # not block this owner; a later COMPLETED receipt still suppresses it.
            if exclude_run_id and int(run["id"]) > exclude_run_id:
                record["waiting_later"] = True
                continue
            result["status"] = "active"
            result["active_created_at"] = run["created_at"]
            continue
        if job_reads >= 4:
            raise RuntimeError("Cadence job read budget exhausted")
        job_reads += 1
        jobs_doc = _read(repo, token, f"actions/runs/{run['id']}/jobs?per_page=100")
        jobs = jobs_doc.get("jobs")
        if not isinstance(jobs, list) or jobs_doc.get("total_count") != len(jobs):
            raise RuntimeError("Incomplete job inventory")
        steps = {step["name"]: step.get("conclusion") for job in jobs
                 for step in job.get("steps", [])}
        source = steps.get(REQUIRED_STEPS[1])
        if (run.get("conclusion") == "success" and source == "skipped"
                and steps.get(GUARD_STEP) == "success"):
            record["duplicate_noop"] = True
            continue
        result["attempt_count"] += 1
        if run.get("conclusion") == "success" and all(steps.get(name) == "success" for name in REQUIRED_STEPS):
            result.update(status="delivered", delivery_run_id=run["id"])
            return result
    if result["status"] != "active":
        if result["attempt_count"] >= MAX_ATTEMPTS:
            result["status"] = "attempt_limit"
        elif result["attempt_count"]:
            result["status"] = "failed"
    return result


def guard() -> int:
    now = datetime.now(timezone.utc)
    event = os.environ.get("GITHUB_EVENT_NAME", "")
    if event == "workflow_dispatch":
        result = {"status": "explicit_manual", "run": True}
    else:
        slot = latest_slot(now)
        if event not in ("schedule", "repository_dispatch"):
            raise RuntimeError("Unexpected cadence event")
        if event == "repository_dispatch":
            payload = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
            supplied = datetime.fromisoformat(str(payload.get("client_payload", {}).get("schedule_slot", "")).replace("Z", "+00:00"))
            if supplied != slot:
                raise RuntimeError("Unexpected automatic schedule_slot")
        result = inspect_slot(os.environ["GITHUB_REPOSITORY"], os.environ.get("GH_TOKEN", ""),
                              slot, now, int(os.environ["GITHUB_RUN_ID"]))
        result["run"] = result["status"] in ("missing", "failed")
    print(json.dumps(result, ensure_ascii=False))
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        output.write(f"run={str(result['run']).lower()}\n")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["guard"])
    parser.parse_args()
    try:
        raise SystemExit(guard())
    except Exception as exc:
        print(json.dumps({"status": "unknown", "error": type(exc).__name__}))
        raise SystemExit(1)
