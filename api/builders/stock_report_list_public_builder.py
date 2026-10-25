"""Project the published stock reports to the fields used by PublicDiscovery.

This is a local, deterministic transform of an already public report. It does
not fetch data. The source digest covers the exact staged bytes, including any
reviewed corrections applied immediately before publication.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile


FACT_KEYS = (
    "시가총액", "PER", "PBR", "ROE", "부채비율", "D/E",
    "영업이익률", "순이익률", "Altman-Z",
)
ROW_KEYS = ("ticker", "name", "market", "business")
PEER_KEYS = ("sector",)
PEER_ROW_KEYS = ("key", "value", "median", "vs")
OWNERSHIP_KEYS = ("group", "family_pct", "sub_count")
SHAREHOLDER_KEYS = ("type", "name", "pct")
SCHEMA = "alphanest-discovery-list-v1"


def pick(value, keys):
    if not isinstance(value, dict):
        raise ValueError("expected object in public report")
    out = {key: value[key] for key in keys if key in value}
    if any(isinstance(item, (dict, list)) for item in out.values()):
        raise ValueError("unexpected nested value in public list field")
    return out


def optional_object(row, key, fields):
    if key not in row:
        return
    value = row[key]
    if value is None:
        return None
    return pick(value, fields)


def project_row(row):
    if not isinstance(row, dict):
        raise ValueError("stocks entry must be an object")
    out = pick(row, ROW_KEYS)
    if not isinstance(out.get("ticker"), str) or not out["ticker"]:
        raise ValueError("stocks entry has no ticker")
    for key in ("facts", "overview"):
        fields = FACT_KEYS if key == "facts" else ("sector",)
        if key in row:
            out[key] = optional_object(row, key, fields)
    if "peer" in row:
        peer = row["peer"]
        if peer is None:
            out["peer"] = None
        else:
            out["peer"] = pick(peer, PEER_KEYS)
            if "rows" in peer:
                rows = peer["rows"]
                if rows is not None and not isinstance(rows, list):
                    raise ValueError("peer.rows must be an array or null")
                out["peer"]["rows"] = (
                    [pick(item, PEER_ROW_KEYS) for item in rows]
                    if rows is not None else None
                )
    if "ownership" in row:
        own = row["ownership"]
        if own is None:
            out["ownership"] = None
        else:
            out["ownership"] = pick(own, OWNERSHIP_KEYS)
            if "shareholders" in own:
                holders = own["shareholders"]
                if holders is not None and not isinstance(holders, list):
                    raise ValueError("ownership.shareholders must be an array or null")
                out["ownership"]["shareholders"] = (
                    [pick(item, SHAREHOLDER_KEYS) for item in holders[:3]]
                    if holders is not None else None
                )
            if "cross_check" in own:
                out["ownership"]["cross_check"] = optional_object(own, "cross_check", ("status",))
    return out


def project(source_bytes, source_name):
    source = json.loads(source_bytes)
    if not isinstance(source, dict) or not isinstance(source.get("stocks"), list):
        raise ValueError("public report must contain stocks array")
    meta = source.get("_meta")
    if not isinstance(meta, dict):
        raise ValueError("public report must contain _meta object")
    if not isinstance(meta.get("generated_at"), str) or not meta["generated_at"]:
        raise ValueError("public report must contain generated_at")
    return {
        "_meta": {
            "schema": SCHEMA,
            "generated_at": meta.get("generated_at"),
            "source_file": source_name,
            "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
            "count": len(source["stocks"]),
        },
        "stocks": [project_row(row) for row in source["stocks"]],
    }


def build(source_path, output_path):
    source_bytes = source_path.read_bytes()
    body = json.dumps(
        project(source_bytes, source_path.name), ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    # A bad source or interrupted build must leave the last good file untouched.
    fd, temp_name = tempfile.mkstemp(prefix=f".{output_path.name}.", dir=output_path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(body)
        os.replace(temp_name, output_path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    return len(body)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(f"{args.output}: {build(args.source, args.output)} bytes")


if __name__ == "__main__":
    main()
