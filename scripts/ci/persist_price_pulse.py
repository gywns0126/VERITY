#!/usr/bin/env python3
"""Persist prepared price bytes and the existing date lock without history rebase.

Reuse bounded transport and whole-blob conflict checks. A concurrent price or
date-lock generation is preserved, with this run retained in its recovery artifact.
No token issuance or token-cache access belongs in this persistence path.
"""
import argparse
from pathlib import Path

try:
    from .persist_cockpit_snapshot import persist as persist_snapshot
except ImportError:  # Direct workflow invocation.
    from persist_cockpit_snapshot import persist as persist_snapshot

PATHS = ("data/price_pulse.json", "data/.kis_issued_date.txt")


def persist(repo, branch, **kwargs):
    return persist_snapshot(repo, branch, paths=PATHS, label="price_pulse",
                            optional_paths=(PATHS[1],), **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("branch")
    args = parser.parse_args()
    try:
        persist(Path.cwd(), args.branch)
    except (RuntimeError, OSError) as exc:
        raise SystemExit(f"::error::Price pulse persistence failed: {exc}") from exc


if __name__ == "__main__":
    main()
