#!/usr/bin/env python3
"""Validate bounded local contract-capture projections for public delivery."""
from __future__ import annotations

import json
from pathlib import Path
import sys


MAX_BYTES = 8 * 1024 * 1024
MAX_ROWS = 1000
CAPTURE_FIELDS = {
    "contract_facts": "validate_contract_fact",
    "documentFamilies": "validate_family",
    "contract_terminations": "validate_contract_termination",
    "filing_excerpts": "validate_filing_excerpts",
    "annual_customer_tables": "validate_annual_customer_capture",
}
FORBIDDEN_TEXT = (
    "/Users/", "\\Users\\", "/private/", "file://", "project-file:",
    "library-file:", "registryGroup", "registryId", "LOCAL_FILES", "PRIVATE_FILES",
)


def _strict_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate-json-key")
        value[key] = item
    return value


def _reject_private_metadata(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str) or any(token in key for token in FORBIDDEN_TEXT):
                raise ValueError("private-capture-metadata")
            _reject_private_metadata(item)
    elif isinstance(value, list):
        for item in value:
            _reject_private_metadata(item)
    elif isinstance(value, str) and any(token in value for token in FORBIDDEN_TEXT):
        raise ValueError("private-capture-metadata")


def _validators():
    root = Path(__file__).resolve().parents[2]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from api.intelligence.portfolio_contract_facts import validate_contract_fact
    from api.intelligence.portfolio_event_lineage import validate_family
    from api.intelligence.portfolio_contract_termination import validate_contract_termination
    from api.intelligence.portfolio_filing_excerpts import validate_filing_excerpts
    from api.intelligence.portfolio_annual_customer_tables import validate_annual_customer_capture
    return {
        "contract_facts": validate_contract_fact,
        "documentFamilies": validate_family,
        "contract_terminations": validate_contract_termination,
        "filing_excerpts": validate_filing_excerpts,
        "annual_customer_tables": validate_annual_customer_capture,
    }


def validate(payload):
    if (not isinstance(payload, dict) or not payload
            or not set(payload).issubset(CAPTURE_FIELDS)):
        raise ValueError("invalid-capture-fields")
    validators = _validators()
    counts = {}
    for field, rows in payload.items():
        if not isinstance(rows, list) or len(rows) > MAX_ROWS:
            raise ValueError("invalid-capture-count")
        receipts = set()
        validator = validators[field]
        for row in rows:
            validated = validator(row)
            if validated != row:
                raise ValueError("capture-value-changed")
            receipt = row.get("receipt_no") if isinstance(row, dict) else None
            if receipt in receipts:
                raise ValueError("duplicate-capture-receipt")
            receipts.add(receipt)
        counts[field] = len(rows)
    _reject_private_metadata(payload)
    return counts


def main():
    if sys.argv[1:] not in ([], ["--strict-json"]):
        raise ValueError("invalid-validator-mode")
    raw = sys.stdin.buffer.read(MAX_BYTES + 1)
    if not raw or len(raw) > MAX_BYTES:
        raise ValueError("capture-byte-limit")
    try:
        payload = json.loads(raw.decode("utf-8"), object_pairs_hook=_strict_object)
    except (UnicodeError, json.JSONDecodeError):
        raise ValueError("invalid-capture-json") from None
    if sys.argv[1:] == ["--strict-json"]:
        if not isinstance(payload, dict):
            raise ValueError("invalid-capture-json")
        sys.stdout.write('{"strict":true}')
        return
    sys.stdout.write(json.dumps({"counts": validate(payload)}, separators=(",", ":")))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.stderr.write("capture delivery validation failed\n")
        raise SystemExit(1)
