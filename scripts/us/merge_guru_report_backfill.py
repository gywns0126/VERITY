#!/usr/bin/env python3
"""Merge verified, bounded report records without rebuilding unrelated stocks.

Run only after official-source verification. Publication remains the existing
GitHub Actions publish-data responsibility; no credentials or network here.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def merge_report(base, candidate, tickers):
    requested = list(tickers)
    if not requested or len(set(requested)) != len(requested):
        raise ValueError("Expected non-empty unique tickers")
    previous = {r["ticker"]: r for r in base["stocks"]}
    incoming = {r["ticker"]: r for r in candidate["stocks"]}
    if len(previous) != len(base["stocks"]) or len(incoming) != len(candidate["stocks"]):
        raise ValueError("Duplicate stock identity")
    if set(requested) - incoming.keys():
        raise ValueError("Candidate is missing requested tickers")
    merged = copy.deepcopy(base)
    rows = {r["ticker"]: r for r in merged["stocks"]}
    for ticker in requested:
        new = incoming[ticker]
        coverage = new.get("data_coverage") or {}
        if not coverage.get("verified_at") or not coverage.get("financial_source"):
            raise ValueError(f"Missing source verification: {ticker}")
        old = previous.get(ticker) or {}
        old_period = str((old.get("financials") or {}).get("period_end") or "")
        new_period = str((new.get("financials") or {}).get("period_end") or "")
        if old_period and new_period and old_period > new_period:
            raise ValueError(f"Refusing older financial period: {ticker}")
        rows[ticker] = copy.deepcopy(new)
    merged["stocks"] = list(rows.values())
    meta = merged.setdefault("_meta", {})
    meta["count"] = len(rows)
    meta["generated_at"] = datetime.now(timezone.utc).isoformat()
    meta["manual_backfill"] = {"tickers": requested,
                               "verified_at": candidate["_meta"]["manual_backfill"]["verified_at"]}
    for ticker, row in previous.items():
        if ticker not in requested and rows[ticker] != row:
            raise AssertionError(f"Unrelated report changed: {ticker}")
    return merged, {"processed": len(requested), "requested": len(requested),
                    "before": len(previous), "after": len(rows),
                    "unchanged": sum(t not in requested for t in previous)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--seed", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raw = args.report.read_bytes()
    candidate = json.loads(args.candidate.read_text(encoding="utf-8"))
    seed = json.loads(args.seed.read_text(encoding="utf-8"))
    result, audit = merge_report(json.loads(raw), candidate, seed["stocks"])
    result["_meta"]["manual_backfill"]["base_sha256"] = hashlib.sha256(raw).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False,
                                      allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False))


if __name__ == "__main__":
    main()
