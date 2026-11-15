#!/usr/bin/env python3
"""Build optional company candidates from one staged public bundle, without IO to services."""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
from pathlib import Path
import sys
import types

ROOT = Path(__file__).resolve().parents[2]
ARTIFACT = "portfolio_public_business_index.json"
RECEIPT = "portfolio_public_business_release.json"


class CandidateError(ValueError):
    """Fixed diagnostics only; never include a source value or traceback."""


def _read(directory, name, limit, decoder):
    file = directory / name
    if file.is_symlink() or not file.is_file() or not 0 < file.stat().st_size <= limit:
        raise CandidateError("candidate-input-rejected")
    with file.open("rb") as stream:
        raw = stream.read(limit + 1)
    if not 0 < len(raw) <= limit:
        raise CandidateError("candidate-input-rejected")
    value = decoder(raw)
    if type(value) is not dict:
        raise CandidateError("candidate-input-rejected")
    return value, raw


def build(source_dir, output_dir, *, writer=None, dependencies=None):
    """Only the writer owns company schemas, projections and parent/source validation."""
    # An isolated package path avoids an already-imported repository api package
    # selecting the wrong copy when tests or other local tools load this CLI.
    package_name = "company_snapshot_publish_core"
    if package_name not in sys.modules:
        package = types.ModuleType(package_name)
        package.__path__ = [str(ROOT / "vercel-api/api/portfolio_core")]
        sys.modules[package_name] = package
    contract = importlib.import_module(package_name + ".portfolio_company_snapshot")
    decode, encode, write_company_snapshots = contract.decode, contract.encode, contract.write_company_snapshots
    if dependencies is None or writer is None:
        prepared = importlib.import_module(package_name + ".portfolio_prepared_business")
        public = importlib.import_module(package_name + ".portfolio_public_sources")
        if dependencies is None:
            dependencies = (prepared.ARTIFACT_MAX_BYTES, prepared.RECEIPT_MAX_BYTES,
                            prepared.BUSINESS_SOURCE_FILES, public.PUBLIC_SOURCE_MAX_BYTES)
        if writer is None:
            writer = write_company_snapshots
    source, output = Path(source_dir), Path(output_dir)
    if source.is_symlink() or not source.is_dir() or output.is_symlink():
        raise CandidateError("candidate-directory-rejected")
    source, output = source.resolve(), output.resolve()
    if source == output or source in output.parents or output in source.parents:
        raise CandidateError("candidate-directory-rejected")
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise CandidateError("candidate-output-not-empty")
    artifact_limit, receipt_limit, names, limits = dependencies
    artifact, _ = _read(source, ARTIFACT, artifact_limit, decode)
    receipt, receipt_bytes = _read(source, RECEIPT, receipt_limit, decode)
    if receipt_bytes != encode(receipt):
        raise CandidateError("candidate-parent-not-canonical")
    documents, source_hashes = {}, {}
    for name in names:
        document, raw = _read(source, name, limits[name], decode)
        documents[name] = document
        source_hashes[name] = hashlib.sha256(raw).hexdigest()
    # The six staged dicts include both current disclosure feeds. Never derive
    # these solely from the three-source base embedded in the prepared artifact.
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    manifest = writer(artifact, receipt, output, documents, source_hashes, parent_raw=receipt_bytes)
    parent_sha256 = hashlib.sha256(receipt_bytes).hexdigest()
    if type(manifest) is not dict or manifest.get("parent_receipt_sha256") != parent_sha256:
        raise CandidateError("candidate-parent-bytes-mismatch")
    return {"built": True, "sources": len(documents), "parent_receipt_sha256": parent_sha256}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = build(args.source_dir, args.output_dir)
    except Exception:
        # Inputs and upstream exceptions may contain public facts or credentials.
        print("company snapshot candidate unavailable", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
