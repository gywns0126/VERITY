#!/usr/bin/env python3
"""Explicit-store public source refresh. Default: plan only, zero network/writes.

Uses only this checkout's module and tracked DartScout; no external capture
runner is required. Dry-run does not verify deployment or live collection.
"""
from __future__ import annotations

import argparse
import fcntl
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location(
    "company_structure_refresh", ROOT / "api/collectors/company_structure_refresh.py")
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)


def run(args):
    def execute():
        now = datetime.now(timezone.utc)
        document = core.build_document(
            args.source_dir, core.read_json(args.store) if args.store.exists() else None,
            core.read_json(args.seed) if args.seed else None, now)
        document, summary = core.refresh(
            document, source_dir=args.source_dir, limit=args.limit,
            fetch_public=args.fetch_public, now=now,
            checkpoint=lambda value: core.atomic_json(args.store, value))
        if args.fetch_public:
            document["summary"] = summary
            core.atomic_json(args.store, document)
        print(json.dumps(summary, ensure_ascii=False))
        return summary["exitCode"]

    # Stable sidecar lock survives atomic replacement of the source store.
    if args.fetch_public:
        args.store.parent.mkdir(parents=True, exist_ok=True)
        with args.store.with_name(args.store.name + ".lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return execute()
    return execute()


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=ROOT)
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=300)
    parser.add_argument("--fetch-public", action="store_true")
    parser.add_argument("--seed", type=Path)
    return parser.parse_args(argv)


if __name__ == "__main__":
    try:
        raise SystemExit(run(parse_args()))
    except Exception as exc:
        # Exception messages can include credential-bearing request URLs.
        print(json.dumps({"error": type(exc).__name__}))
        raise SystemExit(1)
