"""Read existing Actions completion evidence; never run collectors or change source clocks."""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from functools import lru_cache

# No artifact hash/storage-commit receipt is emitted by these steps. Their
# completion is only pipeline evidence and must NEVER become an asset last_ts.
PRODUCERS = {
    "news_flash": ("rss_scout.yml", "Run RSSScout", ""),
    "dividends_kr": ("kr_company_facts_backfill.yml", "Backfill company facts", "schedule"),
}
_PROCESS_BUDGET_SECONDS = 20.0
_PROCESS_DEADLINE = None


class _BudgetExhausted(Exception):
    pass


def _remaining(deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise _BudgetExhausted
    return remaining


def _gh(*args, deadline):
    result = subprocess.run(["gh", *args], check=True, capture_output=True,
                            text=True, timeout=min(30.0, _remaining(deadline)))
    _remaining(deadline)
    return result.stdout


def _dividend_result(log):
    for line in reversed(log.splitlines()):
        match = re.search(r"\[facts_backfill\] \d+초 · (\{.*\})", line)
        if match:
            result = json.loads(match.group(1)).get("dividends")
            if not isinstance(result, dict) or "error" in result:
                return False
            todo = result.get("todo")
            moved = result.get("progressed", result.get("ok"))
            return (type(todo) is int and todo >= 0 and type(moved) is int
                    and 0 <= moved <= todo and (todo == 0 or moved == todo))
    return False


@lru_cache(maxsize=2)
def producer_evidence(sid):
    global _PROCESS_DEADLINE
    if sid not in PRODUCERS:
        return None
    # Local diagnostic/test runs must not implicitly access the network.
    if os.environ.get("GITHUB_ACTIONS") != "true":
        return {"status": "unavailable"}
    workflow, step_name, event = PRODUCERS[sid]
    repo = os.environ.get("GITHUB_REPOSITORY", "gywns0126/VERITY")
    branch = os.environ.get("GITHUB_BASE_REF") or "main"
    try:
        # One deadline for BOTH producers and every API/log call in this process.
        # Do not reset it per stream, retry, or build_board/build_observations call.
        if _PROCESS_DEADLINE is None:
            _PROCESS_DEADLINE = time.monotonic() + _PROCESS_BUDGET_SECONDS
        deadline = _PROCESS_DEADLINE
        _remaining(deadline)
        query = f"repos/{repo}/actions/workflows/{workflow}/runs?branch={branch}&per_page=1"
        if event:
            query += f"&event={event}"
        runs = json.loads(_gh("api", query, deadline=deadline)).get("workflow_runs") or []
        if not runs:
            return {"status": "missing"}
        run = runs[0]  # Never hide a latest failed/pending run with an older success.
        proof = {"status": "unconfirmed", "run_id": run["id"], "workflow": workflow,
                 "run_status": run.get("status"), "run_conclusion": run.get("conclusion"),
                 "clock_kind": "producer_step_completion", "asset_binding": "unverified",
                 "source_freshness_verified": False, "all_records_revalidated": False,
                 "scope": ("named_rss_step_exit_zero" if sid == "news_flash"
                           else "selected_dividend_chunk_or_resume_noop")}
        if run.get("status") != "completed":
            return {**proof, "status": "pending"}
        if run.get("conclusion") != "success":
            return proof
        jobs = json.loads(_gh("api", f"repos/{repo}/actions/runs/{run['id']}/jobs?per_page=100",
                              deadline=deadline))
        steps = [step for job in jobs.get("jobs", []) for step in job.get("steps", [])
                 if step.get("name") == step_name]
        if len(steps) != 1 or steps[0].get("conclusion") != "success":
            return proof
        stamp = steps[0].get("completed_at")
        if not stamp:
            return proof
        if sid == "dividends_kr" and not _dividend_result(
                _gh("run", "view", str(run["id"]), "--repo", repo, "--log", deadline=deadline)):
            return proof
        _remaining(deadline)
        return {**proof, "status": "pipeline_completed", "completed_at": stamp}
    except _BudgetExhausted:
        return {"status": "unavailable", "reason": "budget_exhausted"}
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
        return {"status": "unavailable"}
