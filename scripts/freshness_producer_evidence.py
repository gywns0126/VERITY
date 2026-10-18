"""Read existing Actions completion evidence; never run collectors or change source clocks."""
from __future__ import annotations

import json
import hashlib
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

# A named step alone has no artifact binding. Its completion must NEVER become
# an asset last_ts; the separate RSS receipt below verifies the actual file pair.
PRODUCERS = {
    "news_flash": ("rss_scout.yml", "Run RSSScout", ""),
    "dividends_kr": ("kr_company_facts_backfill.yml", "Backfill company facts", "schedule"),
}
_PROCESS_BUDGET_SECONDS = 20.0
_PROCESS_DEADLINE = None
RSS_SOURCES = frozenset({"SEC 공식 발표", "CNBC", "Fed 공식 발표"})


def collection_receipt(sid, artifact_path):
    """Verify the RSS query/output pair, never article publication freshness.

    A complete query can be measured even with zero filtered new headlines.
    A partial query or a mismatched file remains unmeasured, not a new timestamp.
    Missing legacy receipts fall back only to separately labelled job diagnostics.
    """
    if sid != "news_flash":
        return None
    path = Path(artifact_path)
    receipt_path = path.parent / "metadata/rss_source_receipt.json"
    if not receipt_path.exists():
        return None
    invalid = {"status": "invalid_receipt", "asset_binding": "unverified",
               "source_freshness_verified": False, "all_records_revalidated": False}
    try:
        doc = json.loads(receipt_path.read_bytes())
        payload = path.read_bytes()
        rows = json.loads(payload)
        if (not isinstance(doc, dict) or not isinstance(rows, list)
                or any(not isinstance(row, dict) for row in rows)):
            return invalid
        scope, asset, feeds = doc.get("scope"), doc.get("asset"), doc.get("feeds")
        if not isinstance(scope, dict) or not isinstance(asset, dict) or not isinstance(feeds, list):
            return invalid
        if (type(doc.get("schema_version")) is not int or doc["schema_version"] != 1
                or doc.get("producer") != "RSSScout"
                or doc.get("clock_kind") != "source_query_attempt"
                or len(feeds) != len(RSS_SOURCES)
                or any(not isinstance(feed, dict) for feed in feeds)
                or {f.get("source") for f in feeds} != RSS_SOURCES
                or scope.get("kind") != "configured_rss_feed_query"
                or type(scope.get("expected_feeds")) is not int
                or scope["expected_feeds"] != len(RSS_SOURCES)
                or asset.get("path") != "data/news_flash.json"
                or asset.get("status") != "bound"
                or type(asset.get("rows")) is not int or asset["rows"] != len(rows)
                or asset.get("sha256") != hashlib.sha256(payload).hexdigest()):
            return invalid
        def stamp(value):
            result = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if result.tzinfo is None:
                raise ValueError("clock must include timezone")
            return result
        started, finished = stamp(doc["started_at"]), stamp(doc["finished_at"])
        if started > finished or finished > datetime.now(timezone.utc):
            return invalid
        successes = 0
        for feed in feeds:
            if not started <= stamp(feed["started_at"]) <= stamp(feed["finished_at"]) <= finished:
                return invalid
            if feed.get("outcome") in ("success", "success_empty"):
                status = feed.get("http_status")
                if type(status) is not int or not 200 <= status < 300:
                    return invalid
                successes += 1
            elif feed.get("outcome") not in ("transport_error", "http_error", "parse_error"):
                return invalid
        expected_outcome = ("complete" if successes == len(feeds) else
                            "partial_failure" if successes else "all_feed_failure")
        if (type(scope.get("successful_feeds")) is not int or scope["successful_feeds"] != successes
                or doc.get("outcome") != expected_outcome
                or type(doc.get("new_rows")) is not int or doc["new_rows"] < 0):
            return invalid
        if expected_outcome == "complete" and asset.get("disposition") not in (
                "atomically_replaced", "unchanged_no_new_rows"):
            return invalid
        return {"status": "bound_query_complete" if expected_outcome == "complete" else "bound_query_incomplete",
                "asset_binding": "verified_sha256", "completed_at": doc["finished_at"],
                "clock_kind": "source_query_attempt", "outcome": expected_outcome,
                "expected_feeds": len(feeds), "successful_feeds": successes,
                "new_rows": doc["new_rows"], "source_freshness_verified": False,
                "all_records_revalidated": False}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return invalid


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
