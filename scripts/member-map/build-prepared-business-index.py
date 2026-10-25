#!/usr/bin/env python3
"""Derive a public index from the existing reviewed public source bundle.

This adds no new human approval. The existing trusted publish action must
upload the derived artifact first and its automatic receipt last.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "vercel-api"))

from api.portfolio_core.portfolio_engine import (  # noqa: E402
    build_prepared_business_index,
    prepared_business_index_sha256,
    prepared_business_publisher_receipt,
)
from api.portfolio_core.portfolio_public_sources import (  # noqa: E402
    PUBLIC_SOURCE_MAX_BYTES,
)
from api.portfolio_core.portfolio_prepared_business import (  # noqa: E402
    ARTIFACT_MAX_BYTES, RECEIPT_MAX_BYTES, BUSINESS_SOURCE_FILES,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt-output", type=Path, required=True)
    args = parser.parse_args()
    if (not args.source_dir.is_dir() or args.output == args.receipt_output
            or any(path.exists() or path.is_symlink()
                   for path in (args.output, args.receipt_output))):
        parser.error("source directory and two new output paths required")

    documents, source_hashes = {}, {}
    for name in BUSINESS_SOURCE_FILES:
        path = args.source_dir / name
        if not path.exists():
            continue
        if path.is_symlink() or not path.is_file() or path.stat().st_size > PUBLIC_SOURCE_MAX_BYTES[name]:
            parser.error("public source path rejected")
        raw = path.read_bytes()
        documents[name] = json.loads(raw)
        source_hashes[name] = hashlib.sha256(raw).hexdigest()
    if len(documents) != len(BUSINESS_SOURCE_FILES):
        parser.error("six reviewed business dependency sources required")
    artifact = build_prepared_business_index(documents)
    payload = json.dumps(artifact, ensure_ascii=True, sort_keys=True,
                         separators=(",", ":"), allow_nan=False).encode("utf-8")
    receipt = prepared_business_publisher_receipt(artifact)
    receipt_payload = json.dumps(receipt, ensure_ascii=True, sort_keys=True,
                                 separators=(",", ":"), allow_nan=False).encode("utf-8")
    if len(payload) > ARTIFACT_MAX_BYTES or len(receipt_payload) > RECEIPT_MAX_BYTES:
        parser.error("prepared public artifact exceeds bounded publish size")
    args.output.write_bytes(payload)
    args.receipt_output.write_bytes(receipt_payload)
    print(json.dumps({"source_revision": artifact["source_revision"],
                      "implementation_sha256": artifact["implementation_sha256"],
                      "matcher_version": artifact["matcher_version"],
                      "sha256": prepared_business_index_sha256(artifact),
                      "utc_day": artifact["utc_day"],
                      "bytes": len(payload), "sources": len(documents),
                      "source_sha256": source_hashes}, sort_keys=True))


if __name__ == "__main__":
    main()
