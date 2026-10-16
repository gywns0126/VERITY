"""Offline, primary-evidence-only repair. Unmatched future rows are preserved in quarantine.

Dry run by default. --apply changes the supplied snapshot, never calls a provider.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from api.utils.dart_period import valid_period_end


def repair_rows(lines, evidence, as_of):
    fixed, quarantined, output = [], [], []
    lookup = {r["ticker"]: r for r in evidence["rows"]}
    for line in lines:
        row = json.loads(line)
        if str(row.get("quarter_end", "")) <= as_of:
            output.append(line)
            continue
        original = dict(row)
        proof = lookup.get(row.get("ticker"))
        matches = bool(proof and all(row.get(k) == proof.get(k) for k in
                                    ("fs_div", "reprt_code", "revenue", "operating_profit", "net_income"))
                       and row["quarter_end"] == proof["incorrect_period_end"]
                       and valid_period_end(proof["period_end"], as_of=str(row.get("fetched_at", "")))
                       and proof["rcept_no"][:8] <= str(row.get("fetched_at", ""))[:10].replace("-", ""))
        if matches:
            row["quarter_end"] = proof["period_end"]
            for key in ("period_start", "period_basis", "rcept_no", "source_url"):
                row[key] = proof[key]
            row["source_as_of"] = proof["period_end"]
            row["period_verified_on"] = evidence["verified_on"]
            row["_period_original"] = original["quarter_end"]
            # Preserve fetched_at: today's repair is not a new financial observation.
            fixed.append({"original": original, "corrected": row})
            output.append(json.dumps(row, ensure_ascii=False) + "\n")
        else:
            quarantined.append({"reason": "future_period_without_matching_primary_evidence",
                                "original": original})
    return output, fixed, quarantined


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    raw = args.input.read_bytes()
    output, fixed, quarantined = repair_rows(
        raw.decode().splitlines(keepends=True), json.loads(args.evidence.read_text()), args.as_of)
    repaired = "".join(output).encode()
    audit = {"as_of": args.as_of, "applied": args.apply, "input_rows": len(raw.splitlines()),
             "corrected_rows": len(fixed), "quarantined_rows": len(quarantined),
             "before_sha256": hashlib.sha256(raw).hexdigest(),
             "after_sha256": hashlib.sha256(repaired).hexdigest(),
             "fixed": fixed, "quarantined": quarantined}
    if args.audit.exists():
        raise SystemExit("Refusing to overwrite an existing audit (original rows must be preserved).")
    args.audit.parent.mkdir(parents=True, exist_ok=True)
    args.audit.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n")
    if args.apply:
        tmp = args.input.with_suffix(args.input.suffix + ".period-repair.tmp")
        tmp.write_bytes(repaired)
        tmp.replace(args.input)
    print(json.dumps({k: v for k, v in audit.items() if k not in ("fixed", "quarantined")}))


if __name__ == "__main__":
    main()
