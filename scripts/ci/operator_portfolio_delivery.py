"""Validate the exact completed portfolio bytes before private early/final delivery."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import re

from api.utils.universe_candidates import snapshot_rejection

KST = timezone(timedelta(hours=9))


def compact_portfolio_source(body: bytes) -> tuple:
    """Preserve every JSON value while making transport whitespace explicit.

    The archive preserves these compact bytes, not the producer's disk formatting.
    Input evidence hashes use their own canonical scope and remain unchanged.
    """
    document = json.loads(body)
    if not isinstance(document, dict):
        raise ValueError("portfolio source must be an object")
    compact = json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return compact, {
        "format": "compact-json-utf8-v1",
        "producer_original_sha256": hashlib.sha256(body).hexdigest(),
        "producer_original_bytes": len(body),
        "archive_compact_sha256": hashlib.sha256(compact).hexdigest(),
        "archive_compact_bytes": len(compact),
    }


def portfolio_archive(body: bytes, *, run_id: str, run_attempt: str) -> dict:
    """Private content-addressed copy of all records from this completed run."""
    if not re.fullmatch(r"[0-9]+", run_id) or not re.fullmatch(r"[0-9]+", run_attempt):
        raise ValueError("numeric workflow identity required")
    digest = hashlib.sha256(body).hexdigest()
    return {"object": f"_operator/analysis_runs/{run_id}/{run_attempt}/{digest}.json",
            "sha256": digest}


def _time(value) -> datetime:
    parsed = datetime.fromisoformat(str(value))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=KST)


def prepare_portfolio_delivery(body: bytes, snapshot_body: bytes, *, run_id: str,
                               run_attempt: str, expected_scan_id: str,
                               analysis_mode: str, verity_mode: str, phase: str,
                               now: datetime) -> bytes:
    """Reject foreign/partial/stale analyses; annotate only the in-memory upload."""
    if (verity_mode != "prod" or analysis_mode not in ("full", "full_us")
            or not run_id or not run_attempt or phase not in ("analysis_complete", "final")):
        raise ValueError("production full analysis context required")
    portfolio = json.loads(body)
    snapshot = json.loads(snapshot_body)
    if not isinstance(portfolio, dict) or not isinstance(snapshot, dict):
        raise ValueError("portfolio/snapshot must be objects")
    proof = portfolio.get("analysis_provenance")
    if not isinstance(proof, dict):
        raise ValueError("analysis provenance missing")
    if (proof.get("status") != "completed" or str(proof.get("analysis_run_id")) != run_id
            or str(proof.get("analysis_run_attempt")) != run_attempt
            or proof.get("analysis_mode") != analysis_mode):
        raise ValueError("current completed analysis identity mismatch")
    max_age = 96 if now.weekday() >= 5 or (now.weekday() == 0 and now.hour < 17) else 26
    expected = expected_scan_id or snapshot.get("scan_id")
    if not expected or snapshot_rejection(snapshot, max_age, now, expected):
        raise ValueError("source scan incomplete, mismatched, or stale")
    if (proof.get("scan_id") != expected or snapshot.get("scan_mode") != "prod"
            or proof.get("snapshot_sha256") != hashlib.sha256(snapshot_body).hexdigest()
            or proof.get("collected_at") != snapshot.get("collected_at")
            or proof.get("completed_at") != snapshot.get("completed_at")
            or proof.get("producer_sha") != snapshot.get("producer_sha")):
        raise ValueError("loaded source scan bytes/identity mismatch")
    recs = portfolio.get("recommendations")
    if (not isinstance(recs, list) or any(not isinstance(row, dict) for row in recs)
            or proof.get("resulting_analysis_count") != len(recs)
            or proof.get("scan_candidate_count") != len(snapshot["candidates"])):
        raise ValueError("completed analysis counts mismatch")
    try:
        completed = _time(proof.get("analysis_completed_at"))
        if not _time(snapshot["completed_at"]) <= _time(proof.get("loaded_at")) <= completed <= now:
            raise ValueError("analysis completion time mismatch")
    except (ValueError, TypeError):
        raise ValueError("analysis completion time invalid") from None
    portfolio["analysis_provenance"] = {
        **proof,
        "delivery": {
            "phase": phase,
            "prepared_at": now.isoformat(timespec="seconds"),
            "analysis_to_prepare_seconds": round((now - completed).total_seconds(), 3),
            "source_portfolio_sha256": hashlib.sha256(body).hexdigest(),
        },
    }
    return json.dumps(portfolio, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
