#!/usr/bin/env python3
"""Persist six prepared health outputs; reject concurrent JSON/JSONL changes.

No ledger merging or history rebase: retain the producer files for the recovery
artifact when any remote output differs from both the base and prepared bytes.
"""
import argparse
from pathlib import Path

try:
    from .persist_cockpit_snapshot import persist as persist_snapshot
except ImportError:  # Direct workflow invocation.
    from persist_cockpit_snapshot import persist as persist_snapshot

PATHS = (
    "data/metadata/cron_health.jsonl",
    "data/metadata/freshness_observations.jsonl",
    "data/freshness_board.json",
    "data/metadata/publish_verify.json",
    "data/metadata/publish_verify.jsonl",
    "data/metadata/data_health.json",
)


def persist(repo, branch, **kwargs):
    return persist_snapshot(repo, branch, paths=PATHS, label="health", **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("branch")
    args = parser.parse_args()
    try:
        persist(Path.cwd(), args.branch)
    except (RuntimeError, OSError) as exc:
        raise SystemExit(f"::error::Health persistence failed: {exc}") from exc


if __name__ == "__main__":
    main()
