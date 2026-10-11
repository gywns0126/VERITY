#!/usr/bin/env python3
"""Bounded operating proposals from shared public data, never member holdings.

The existing Supabase reservation and private result archive are mandatory.
No public posting, review receipt, confirmed relationship or paid retry is made.
The existing general report builder's CI/serverless paid-worker guards stay intact.
"""
from collections import Counter
from datetime import datetime, timedelta, timezone
import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from api.intelligence import portfolio_ai_fallback as ai
from api.intelligence.portfolio_ai_budget_ledger import SupabaseBudgetLedger
from api.intelligence.portfolio_business_judgment import prepare_judgment_packet, SYSTEM, SCHEMA

MAX_PROBES = 40
_STOP = {"error", "missing-key", "budget-ledger-unavailable", "result-store-unavailable",
         "disabled", "budget-exhausted"}


def read_sources():
    # Reuse the fixed two-public-artifact reader, not a new file/member-input API.
    spec = importlib.util.spec_from_file_location(
        "member_map_public_worker", Path(__file__).with_name("enrich-public-relations.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.read_sources()


def check_operating_environment(env):
    if (env.get("PORTFOLIO_AI_OPERATING_ENABLED") != "1"
            or env.get("PORTFOLIO_AI_LEDGER") != "supabase"
            or any(name in env for name in ("VERCEL", "VERCEL_ENV"))):
        raise ValueError("operating-consent-or-host")
    if "CI" in env or "GITHUB_ACTIONS" in env:
        if (env.get("GITHUB_ACTIONS") != "true"
                or env.get("GITHUB_REPOSITORY") != "gywns0126/VERITY"
                or env.get("GITHUB_REF") != "refs/heads/main"
                or env.get("GITHUB_EVENT_NAME") not in {"workflow_dispatch", "workflow_run"}):
            raise ValueError("operating-trusted-workflow-required")
    if not env.get("OPENAI_API_KEY"):
        raise ValueError("operating-key-missing")
    # Construction only; no credential value is emitted or written to a file.
    return SupabaseBudgetLedger(env.get("SUPABASE_URL", "").rstrip("/"),
                                env.get("SUPABASE_SERVICE_ROLE_KEY", ""))


def plan(documents, *, as_of):
    rows, coverage = ai.select_documents(documents, include_claims=True)
    selected, oversized, future = [], 0, 0
    for doc in rows:
        if doc["as_of"] > as_of:
            future += 1
            continue
        packet = prepare_judgment_packet([doc], as_of=as_of)
        payload = ai._openai_payload(doc)
        payload.update(instructions=SYSTEM, input=json.dumps(packet, ensure_ascii=False))
        payload["text"]["format"].update(name="company_judgment", schema=SCHEMA)
        if len(json.dumps(payload, ensure_ascii=False).encode()) > ai.MAX_PROMPT_BYTES:
            oversized += 1
            continue
        selected.append(doc)
    # Stable rotating probe window prevents old free cache hits from permanently
    # starving later sources. This is scheduling, not an importance/grade score.
    selected.sort(key=lambda row: (row["as_of"], ai._digest(row)), reverse=True)
    if selected:
        offset = datetime.fromisoformat(as_of).toordinal() * MAX_PROBES % len(selected)
        selected = selected[offset:] + selected[:offset]
    return selected[:MAX_PROBES], {**coverage, "judgment_eligible": len(selected),
                                  "input_too_large": oversized, "future_source": future,
                                  "selected_probe_window": min(len(selected), MAX_PROBES)}


def run_batch(documents, ledger_path, api_key, budget, *, as_of, limit, runner=None):
    if type(limit) is not int or not 1 <= limit <= 10:
        raise ValueError("operating-limit")
    runner = runner or ai.run_document
    counts, calls, pending, grade_proposals, findings, stop = Counter(), 0, 0, Counter(), 0, None
    for doc in documents:
        result = runner(doc, ledger_path, api_key, enabled=True,
                        judgment_as_of=as_of, budget_ledger=budget)
        status = result.get("status")
        counts[status] += 1
        if status in {"ok", "error"}:
            calls += 1
        if status in {"ok", "cached"}:
            judgments = result.get("judgments", [])
            pending += len(judgments)
            grade_proposals.update(row["proposal"]["degree"]["value"] for row in judgments)
            findings += len(result.get("quality_review", {}).get("findings", []))
        if result.get("budget_settlement") == "pending-reservation-retained":
            stop = "budget-settlement-pending"
            break
        if status in _STOP:
            stop = status
            break
        if calls >= limit:
            break
    return {"status": "stopped" if stop else "bounded-batch", "stop_reason": stop,
            "results": dict(counts), "paid_attempts": calls,
            "processed_documents": sum(counts.values()), "pending_judgments": pending,
            "proposed_degree_counts": dict(grade_proposals), "quality_findings": findings,
            "accepted_judgments": 0, "confirmed_relationships": 0, "published": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--limit", type=int, default=3)
    args = parser.parse_args()
    if not 1 <= args.limit <= 10:
        parser.error("limit must be between 1 and 10")
    as_of = datetime.now(timezone(timedelta(hours=9))).date().isoformat()
    docs, coverage = plan(read_sources(), as_of=as_of)
    if not args.execute:
        print(json.dumps({"status": "dry-run", "coverage": coverage, "paid_attempts": 0,
                          "model": ai.MODEL, "reasoning_effort": ai.REASONING_EFFORT,
                          "maximum_reserved_micro_usd": args.limit * ai.RESERVE_MICRO_USD}))
        return
    budget = check_operating_environment(os.environ)
    state = ROOT / ".cache" / "portfolio-ai"
    ledger = state / "operating-ledger.sqlite3"
    for path in (ROOT / ".cache", state, ledger):
        if path.is_symlink() or (path.exists() and path == ledger and not path.is_file()):
            raise ValueError("operating-private-ledger-path")
    summary = run_batch(docs, ledger, os.environ["OPENAI_API_KEY"], budget,
                        as_of=as_of, limit=args.limit)
    summary.update(schema="member-map-operating-judgment-run-v1", coverage=coverage,
                   model=ai.MODEL, reasoning_effort=ai.REASONING_EFFORT,
                   task="company-business-judgment-v1", requested_as_of=as_of,
                   budget_backend="supabase", result_archive="private-supabase",
                   monthly_internal_target_krw=ai.MONTH_BUDGET_KRW,
                   source_scope="bounded-shared-public-DART-excerpts-not-full-market",
                   review="AI proposals only; no model can authorize its own acceptance")
    print(json.dumps(summary, ensure_ascii=False))
    if summary["status"] == "stopped":
        raise SystemExit(3 if summary["stop_reason"] == "budget-exhausted" else 2)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(json.dumps({"status": "failed", "error_type": type(error).__name__}), file=sys.stderr)
        raise SystemExit(1)
