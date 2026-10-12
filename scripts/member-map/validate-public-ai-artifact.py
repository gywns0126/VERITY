#!/usr/bin/env python3
"""Validate an already reviewed public projection offline; preserve exact bytes.

No raw answers, private receipts, keys, network or provider calls. Invalid
optional judgments must fail, not be silently removed during publication.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "vercel-api" / "api"))
from api.intelligence.portfolio_ai_public import validate_public_ai_review, validated_contract_sources
from portfolio_core.portfolio_public_sources import load_public_sources, project_public_sources, PUBLIC_SOURCE_MAX_BYTES


REVIEW_SOURCE_FILES = frozenset({"universe_search.json", "public_disclosure_feed.json",
                               "member_map_auto_evidence.json", "member_map_ai_candidates.json"})


def read_review_sources(directory):
    """Exactly the four saved public review sources; no missing-source padding."""
    directory = Path(directory)
    if any(p.is_symlink() for p in (directory, *directory.parents)) or not directory.is_dir():
        raise ValueError("invalid-public-review-directory")
    if {p.name for p in directory.iterdir()} != REVIEW_SOURCE_FILES:
        return load_public_sources(directory)
    def unique(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError("duplicate-public-field")
            value[key] = item
        return value
    def invalid_constant(_):
        raise ValueError("invalid-public-constant")
    directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    sources = {}
    try:
        for name in sorted(REVIEW_SOURCE_FILES):
            limit = PUBLIC_SOURCE_MAX_BYTES[name]
            descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
            with os.fdopen(descriptor, "rb") as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= limit:
                    raise ValueError("invalid-public-review-source")
                raw = stream.read(limit + 1)
            if len(raw) > limit:
                raise ValueError("invalid-public-review-source")
            document = json.loads(raw.decode("utf-8"), object_pairs_hook=unique, parse_constant=invalid_constant)
            if type(document) is not dict:
                raise ValueError("invalid-public-review-source")
            sources[name] = document
    finally:
        os.close(directory_fd)
    return sources


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
    sources = read_review_sources(source_dir)
    catalog = project_public_sources(sources)["companies"]
    from portfolio_core.portfolio_contract_facts import index_contract_events
    from api.intelligence.portfolio_ai_public import project_public_company_judgments
    canonical = sources.get("member_map_auto_evidence.json", {})
    events = index_contract_events(canonical, catalog)
    facts = {}
    for fact in canonical.get("contract_facts", []):
        if fact["receipt_no"] in facts:
            raise ValueError("duplicate-contract-review-source")
        facts[fact["receipt_no"]] = fact
    facts = validated_contract_sources(canonical)
    if "company_judgments" in payload and project_public_company_judgments(
            payload["company_judgments"], payload["candidates"], contract_events=events,
            contract_sources=facts) != payload["company_judgments"]:
        raise ValueError("stale-contract-judgment-source")
    if validate_public_ai_review(payload, catalog, contract_events=events, contract_sources=facts) != payload:
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
