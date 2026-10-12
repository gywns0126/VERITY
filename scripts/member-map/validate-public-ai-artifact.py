#!/usr/bin/env python3
"""Validate an already reviewed public projection offline; preserve exact bytes.

No raw answers, private receipts, keys, network or provider calls. Invalid
optional judgments must fail, not be silently removed during publication.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from api.intelligence.portfolio_ai_public import validate_public_ai_review
from api.intelligence.portfolio_public_sources import load_public_sources, project_public_sources


def validate(artifact, expected_sha256, source_dir, output):
    if (not re.fullmatch(r"[a-f0-9]{64}", expected_sha256)
            or any(p.is_symlink() for p in (artifact, *artifact.parents))
            or not artifact.is_file() or artifact.stat().st_size > 2_000_000
            or output.name != "member_map_ai_candidates.json" or output.is_symlink()):
        raise ValueError("invalid-public-artifact")
    body = artifact.read_bytes()
    if hashlib.sha256(body).hexdigest() != expected_sha256:
        raise ValueError("unexpected-public-artifact")

    def unique(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError("duplicate-public-field")
            value[key] = item
        return value

    def invalid_constant(_):
        raise ValueError("invalid-public-constant")

    payload = json.loads(body, object_pairs_hook=unique, parse_constant=invalid_constant)
    catalog = project_public_sources(load_public_sources(source_dir))["companies"]
    if validate_public_ai_review(payload, catalog) != payload:
        raise ValueError("unsafe-optional-public-judgment")
    output.write_bytes(body)
    return {"sha256": expected_sha256, "count": len(payload["candidates"]), "network_calls": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--artifact", required=True, type=Path)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--source-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = validate(args.artifact, args.sha256, args.source_dir, args.output)
    except (OSError, ValueError, TypeError, KeyError):
        print("public-ai-artifact-rejected", file=sys.stderr)
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
