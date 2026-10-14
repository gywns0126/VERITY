#!/usr/bin/env python3
"""Gate the KR full completion event against persisted producer bytes."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
import sys
from datetime import datetime, timedelta, timezone

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from api.utils.universe_candidates import snapshot_rejection
from scripts.ci.duplicate_run_guard import decide as duplicate_decide


def decide(snapshot: dict, portfolio: dict, expected: str, now: datetime) -> tuple[bool, str]:
    if not expected:
        return False, "expected producer identity missing"
    rejected = snapshot_rejection(snapshot, 26, now, expected)
    if rejected:
        return False, rejected
    if snapshot.get("scan_mode") != "prod":
        return False, "non-prod producer; no automatic production analysis"
    previous = portfolio.get("analysis_provenance") or {}
    if (previous.get("scan_id") == expected and previous.get("analysis_mode") == "full"
            and previous.get("status") == "completed"):
        return False, "this scan already completed full analysis"
    return True, f"persisted completed scan verified: {expected}"


def trigger_decision(now: datetime) -> tuple[bool, str]:
    event = os.environ.get("EVENT_NAME", "workflow_run")
    if event == "workflow_dispatch":
        expected = os.environ.get("UNIVERSE_EXPECTED_SCAN_ID", "")
        if not expected:
            return True, "manual operator request"
        snapshot = json.loads((ROOT / "data/universe_candidates.json").read_bytes())
        rejected = snapshot_rejection(snapshot, 26, now, expected)
        return not rejected, rejected or "manual completed producer verified"
    if event == "repository_dispatch" and os.environ.get("DISPATCH_MODE", "") in ("", "full"):
        return False, "KR full uses completed Universe Scan event"
    if event != "workflow_run":
        # Keep the existing success-only duplicate policy for US/periodic slots.
        try:
            repository = os.environ["GITHUB_REPOSITORY"]
            result = subprocess.run([
                "gh", "api", f"repos/{repository}/actions/workflows/daily_analysis_full.yml/runs?per_page=30",
            ], check=True, capture_output=True, text=True, timeout=30)
            return duplicate_decide(json.loads(result.stdout), int(os.environ["SELF"]),
                                    float(os.environ.get("WINDOW_MIN", "120")))
        except (OSError, subprocess.SubprocessError, ValueError, KeyError):
            return True, "US/periodic duplicate lookup failed; existing fail-open policy"
    snapshot = json.loads((ROOT / "data/universe_candidates.json").read_bytes())
    try:
        portfolio = json.loads((ROOT / "data/portfolio.json").read_bytes())
    except (OSError, ValueError):
        portfolio = {}
    return decide(snapshot, portfolio, os.environ.get("UNIVERSE_EXPECTED_SCAN_ID", ""), now)


def analysis_rejection(portfolio: dict, expected: str, run_id: str, now: datetime) -> str | None:
    if not expected:
        return None  # Existing manual/US/periodic publication policy remains.
    proof = portfolio.get("analysis_provenance") or {}
    if (proof.get("scan_id") != expected or proof.get("status") != "completed"
            or str(proof.get("analysis_run_id")) != run_id or proof.get("analysis_mode") != "full"):
        return "loaded analysis identity/completion mismatch"
    raw_hash = proof.get("snapshot_sha256") or ""
    if len(raw_hash) != 64 or any(c not in "0123456789abcdef" for c in raw_hash):
        return "source snapshot byte hash missing"
    try:
        collected = datetime.fromisoformat(proof["collected_at"])
        if not 0 <= (now - collected).total_seconds() / 3600 <= 26:
            return "analysis source expired before publication"
    except (KeyError, ValueError, TypeError):
        return "analysis source timestamp invalid"
    return None


def main() -> int:
    now = datetime.now(timezone(timedelta(hours=9)))
    if "--require-analysis" in sys.argv:
        try:
            expected = os.environ.get("UNIVERSE_EXPECTED_SCAN_ID", "")
            portfolio = json.loads((ROOT / "data/portfolio.json").read_bytes()) if expected else {}
            rejected = analysis_rejection(portfolio, expected,
                                          os.environ.get("GITHUB_RUN_ID", ""), now)
        except (OSError, ValueError, TypeError):
            rejected = "analysis read failed"
        print(f"[universe_analysis_gate] {rejected or 'analysis input identity verified'}")
        if not rejected and os.environ.get("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"], "a") as output:
                output.write("valid=true\n")
        return 1 if rejected else 0
    try:
        run, reason = trigger_decision(now)
    except (OSError, ValueError, TypeError) as exc:
        run, reason = False, f"persisted scan read failed: {type(exc).__name__}"
    print(f"[universe_analysis_gate] {reason}")
    print("run=1" if run else "run=0")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as output:
            output.write("run=1\n" if run else "run=0\n")
    return 1 if "--require-run" in sys.argv and not run else 0


if __name__ == "__main__":
    raise SystemExit(main())
