"""Hash only the US priority set consumed by the disclosure collector.

Use the existing consumer function so ticker/currency rules cannot drift here.
Git-ref input stays in memory; neither portfolio values nor sets are printed.
"""
import argparse
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
PORTFOLIO = "data/portfolio.json"


def fingerprint(ref=None):
    spec = importlib.util.spec_from_file_location(
        "us_priority_consumer", ROOT / "api/builders/us_insider_trades_public_builder.py")
    consumer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(consumer)
    if ref is not None:
        def git(*args):
            return subprocess.run(
                ["git", *args], cwd=ROOT, check=True, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env={**os.environ, "GIT_NO_LAZY_FETCH": "1", "GIT_OPTIONAL_LOCKS": "0"},
            ).stdout

        commit = git("rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}").decode().strip()
        present = git("ls-tree", "--name-only", commit, "--", PORTFOLIO)
        payload = git("cat-file", "blob", f"{commit}:{PORTFOLIO}") if present else b""
        # Override this module's open only; _rec_us_set still parses and selects.
        consumer.open = lambda *args, **kwargs: io.TextIOWrapper(io.BytesIO(payload), encoding="utf-8")
    priority = consumer._rec_us_set()
    canonical = json.dumps(sorted(priority), separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", help="Read a local Git commit instead of the worktree")
    args = parser.parse_args()
    try:
        digest = fingerprint(args.ref)
    except Exception:
        print("US priority fingerprint could not be verified.", file=sys.stderr)
        sys.exit(1)
    print(digest)
