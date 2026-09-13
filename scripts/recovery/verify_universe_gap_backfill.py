#!/usr/bin/env python3
"""Read back an isolated recovery dataset; optionally compare KR price samples."""
from __future__ import annotations

import argparse
import ast
import json
import sys
import urllib.request
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import universe_gap_backfill as recovery

SAMPLES = ("005930", "000660", "035420")


def compare_naver(rows: list, tickers: tuple = SAMPLES) -> dict:
    local = {(r["ticker"], r["date"].replace("-", "")): r for r in rows if r["key"].startswith("KR:")}
    evidence, errors = [], []
    for ticker in tickers:
        url = ("https://api.finance.naver.com/siseJson.naver?symbol=" + ticker
               + "&requestType=1&startTime=20260908&endTime=20260911&timeframe=day")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://finance.naver.com/"})
            with urllib.request.urlopen(req, timeout=25) as response:
                data = ast.literal_eval(response.read().decode("utf-8-sig").strip())
            if data[0][:6] != ["날짜", "시가", "고가", "저가", "종가", "거래량"]:
                raise ValueError("Unrecognized Naver columns")
            seen = set()
            for record in data[1:]:
                day = str(record[0])
                if day not in {d.replace("-", "") for d in recovery.DAYS}:
                    continue
                if day in seen:
                    raise ValueError("Duplicate Naver date")
                seen.add(day)
                own = local.get((ticker, day))
                if own is None:
                    raise ValueError("Missing primary sample bar")
                differences = []
                for key, value in zip(("open", "high", "low", "close", "volume"), record[1:6]):
                    if not recovery.finite(value):
                        raise ValueError("Nonfinite Naver value")
                    if value != own[key]:
                        differences.append({"field": key, "yahoo": own[key], "naver": value})
                evidence.append({"ticker": ticker, "date": own["date"], "checked_at": recovery.now(),
                                 "source_url": url, "primary_source_url": own["source_url"],
                                 "ohlc_match": not any(d["field"] != "volume" for d in differences),
                                 "volume_match": not any(d["field"] == "volume" for d in differences),
                                 "differences": differences})
            if len(seen) != len(recovery.DAYS):
                raise ValueError("Naver sample date coverage incomplete")
        except (OSError, ValueError, SyntaxError, IndexError, TypeError) as exc:
            errors.append({"ticker": ticker, "error": type(exc).__name__ + ":" + str(exc)[:150]})
    return {"scope": "KR sample only; not whole-universe independent verification",
            "sample_tickers": list(tickers), "expected_sample_bars": len(tickers) * len(recovery.DAYS),
            "checked_sample_bars": len(evidence), "ohlc_matches": sum(e["ohlc_match"] for e in evidence),
            "volume_matches": sum(e["volume_match"] for e in evidence),
            "action_on_difference": "preserve provider values; no silent reconciliation",
            "errors": errors, "evidence": evidence}


def verify(output: Path) -> dict:
    def load(name):
        return json.loads((output / name).read_text(encoding="utf-8"))

    manifest, target_doc = load("manifest.json"), load("targets.json")
    targets, evidence = target_doc["targets"], load("run_evidence.json")
    if manifest["status"] == "running":
        raise ValueError("Collection still running")
    required = {"targets.json", "run_evidence.json", "prices_daily.jsonl", "attempts.json", "coverage.json"}
    if set(manifest["files_sha256"]) != required:
        raise ValueError("Incomplete/foreign file checksum manifest")
    for name, expected in manifest["files_sha256"].items():
        if recovery.sha256(output / name) != expected:
            raise ValueError(f"Checksum mismatch: {name}")
    rows = recovery.read_prices(output / "prices_daily.jsonl")
    recovery.validate_saved_prices(rows, targets)
    if target_doc["count"] != len(targets) or len({t["key"] for t in targets}) != len(targets):
        raise ValueError("Roster denominator mismatch")
    if sorted(e["run_id"] for e in evidence) != sorted(recovery.RUN_IDS):
        raise ValueError("Run denominator mismatch")
    for run in evidence:
        text = "\n".join("scan\tCHECK\t" + e["logged_at"] + " " + e["message"] for e in run["evidence"])
        # Recheck the saved allowlisted observations, with persistence count from
        # the separately recorded source metadata. No full log/secrets on disk.
        text += ("\nscan\tCHECK\t2026-09-11T00:00:00Z remote: error: File data/stock_history/2026-Q3.jsonl" * run["rejected_pushes"])
        parsed = recovery.parse_log(text)
        for field in ("reported_unsaved_rows", "coarse", "candidate_diff"):
            if parsed[field] != run[field]:
                raise ValueError("Saved log evidence/count inconsistency")
    attempts = load("attempts.json")
    if set(attempts) - {t["key"] for t in targets}:
        raise ValueError("Attempt outside roster")
    coverage = recovery.price_coverage(targets, rows, attempts)
    saved = load("coverage.json")
    if {k:v for k,v in coverage.items() if k != "retrieved_at"} != {k:v for k,v in saved.items() if k != "retrieved_at"}:
        raise ValueError("Coverage readback mismatch")
    if manifest["original_missing_snapshot_rows_restored"] != 0 or manifest["observation_trail_eligible"] is not False:
        raise ValueError("Recovery must not claim original snapshots")
    return {"checked_at": recovery.now(), "schema_valid_rows": len(rows), "duplicate_rows": 0,
            "coverage": {k:v for k,v in coverage.items() if k != "unresolved"},
            "run_evidence_checked": len(evidence), "run_evidence_expected": len(recovery.RUN_IDS),
            "by_market": dict(sorted(Counter(r["market"] for r in rows).items())),
            "original_snapshots_restored": 0, "production_consumers_changed": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--cross-source", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    result = verify(args.output)
    if args.cross_source:
        result["cross_source"] = compare_naver(recovery.read_prices(args.output / "prices_daily.jsonl"))
    if args.report:
        recovery.atomic_json(args.report, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    cross = result.get("cross_source") or {}
    if cross.get("errors") or cross.get("ohlc_matches", 0) != cross.get("expected_sample_bars", 0):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
