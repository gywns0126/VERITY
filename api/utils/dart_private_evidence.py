"""Restore private DART provenance only onto an exactly matching public row.

The existing private Storage object contains public DART facts plus source
metadata. This module never restores a scalar, price, portfolio, or unknown unit.
"""
from __future__ import annotations

import copy
import json
import os
from functools import lru_cache
from pathlib import Path

from scripts.ci.private_analysis_files import strip_private_fields

OBJECT = "_operator/dart_fundamentals_kr.json"
BUCKET = "verity-reports"


def _canonical(value):
    # Type-sensitive: True is not 1, 1.0 is not 1; NaN cannot establish identity.
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def merge_source_evidence(public_rows, private_snapshot):
    result = copy.deepcopy(public_rows)
    private_rows = private_snapshot.get("fundamentals") if isinstance(private_snapshot, dict) else None
    if not isinstance(public_rows, dict) or not isinstance(private_rows, dict):
        return result, 0
    restored = 0
    for ticker, public_row in result.items():
        private_row = private_rows.get(ticker)
        if (not isinstance(public_row, dict) or "_source_evidence" in public_row
                or not isinstance(private_row, dict)
                or not isinstance(private_row.get("_source_evidence"), dict)):
            continue
        try:
            matches = _canonical(strip_private_fields(private_row)) == _canonical(public_row)
        except (TypeError, ValueError):
            matches = False
        if matches:
            public_row["_source_evidence"] = copy.deepcopy(private_row["_source_evidence"])
            restored += 1
    return result, restored


@lru_cache(maxsize=1)
def load_private_snapshot():
    """At most one fixed-object authenticated GET per opted-in process."""
    if os.environ.get("DART_PRIVATE_EVIDENCE") != "1":
        return None
    if os.environ.get("OPERATOR_BUCKET", BUCKET) != BUCKET:
        return None
    url = (os.environ.get("SUPABASE_URL") or "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or ""
    if not url or not key:
        return None
    try:
        import requests
        response = requests.get(f"{url}/storage/v1/object/{BUCKET}/{OBJECT}",
                                headers={"apikey": key, "Authorization": f"Bearer {key}"},
                                timeout=15, allow_redirects=False)
        if response.status_code != 200:
            return None
        document = response.json()
        return document if isinstance(document, dict) and isinstance(document.get("fundamentals"), dict) else None
    except Exception:
        # A missing first-run object or unavailable private source stays unknown.
        # Never log URLs, headers, responses or exception strings.
        return None


def restore_source_evidence(public_rows):
    return merge_source_evidence(public_rows, load_private_snapshot())


def restore_batch_cache(path):
    path = Path(path)
    document = json.loads(path.read_text(encoding="utf-8"))
    rows = document.get("fundamentals") if isinstance(document, dict) else None
    if not isinstance(rows, dict):
        raise ValueError("invalid public DART cache")
    restored_rows, restored = restore_source_evidence(rows)
    if restored:
        document["fundamentals"] = restored_rows
        temporary = path.with_name(path.name + ".private-restore.tmp")
        temporary.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)
    return restored


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--restore-batch-cache", required=True)
    args = parser.parse_args()
    restored = restore_batch_cache(args.restore_batch_cache)
    print(f"[dart_private_evidence] metadata rows restored={restored}; scalar fields unchanged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
