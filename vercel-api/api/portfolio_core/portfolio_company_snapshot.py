"""Public company core snapshots; no member data, model call or full-corpus read.

This is an initial, read-only facts/disclosures lane, not portfolio analysis.
The existing full analysis remains authoritative for relations and judgments.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import urllib.request

from .portfolio_prepared_business import (
    PUBLIC_BLOB_BASE_URL, BUSINESS_SOURCE_FILES, RECEIPT_FILENAME,
    RECEIPT_SCHEMA, implementation_sha256, _checked_receipt,
    _BASE_FACT_KEYS, _BASE_FACT_WITH_PROVENANCE, _BASE_PROVENANCE_KEYS,
    _BASE_DOCUMENT_KEYS, _BASE_FILING_KEYS,
)
from .portfolio_public_sources import safe_public_text, _canonical_disclosure_url, _sec_filing

RELEASE_FILE = "member_map_company_release.json"
BUCKET_PREFIX = "member_map_company_snapshots/"
RELEASE_SCHEMA = "member-map-company-release-v1"
BUCKET_SCHEMA = "member-map-company-bucket-v1"
SCOPE = "core-facts-disclosures"
RELEASE_MAX_BYTES = 128 * 1024
BUCKET_MAX_BYTES = 2 * 1024 * 1024
_HASH = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_BUCKET = re.compile(r"[0-9a-f]{2}\Z", re.ASCII)
_ID = re.compile(r"KR:[0-9]{6}\Z|US:[A-Z][A-Z0-9]{0,9}(?:[.-][A-Z0-9]{1,2})?\Z", re.ASCII)
_BINDING = {"source_revision", "parent_source_revision", "implementation_sha256", "projection_sha256", "utc_day", "scope"}


def _published_day(value):
    # The root is bound to the current exact public parent, not an implicit
    # midnight expiry. Keep the last successful publication available during a
    # delayed regular run; this date never replaces a source/filing date.
    try:
        return type(value) is str and datetime.strptime(value, "%Y-%m-%d").date().isoformat() == value and value <= datetime.now(timezone.utc).date().isoformat()
    except ValueError:
        return False


def encode(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def projection_sha256():
    return sha256(Path(__file__).read_bytes())


def company_bucket(identifier):
    return sha256(identifier.encode("ascii"))[:2]


def core_source_revision(revisions):
    if type(revisions) is not dict or set(revisions) != set(BUSINESS_SOURCE_FILES) or any(
            type(value) is not str or not _HASH.fullmatch(value) for value in revisions.values()):
        raise ValueError("company snapshot source hashes rejected")
    return sha256(encode(revisions))


def _object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate company snapshot key")
        value[key] = item
    return value


def decode(raw):
    def reject(_):
        raise ValueError("nonfinite company snapshot value")
    value = json.loads(raw.decode("utf-8"), object_pairs_hook=_object, parse_constant=reject)
    stack = [(value, 0)]
    while stack:
        item, depth = stack.pop()
        if depth > 32:
            raise ValueError("company snapshot depth")
        if type(item) is dict:
            stack.extend((child, depth + 1) for child in item.values())
        elif type(item) is list:
            stack.extend((child, depth + 1) for child in item)
    return value


def write_company_snapshots(artifact, receipt, output_dir, documents, source_hashes, *, parent_raw=None):
    """Offline publisher only: sanitize all six inputs once, then split them.

    No fact, source date, filing identity or document URL is synthesized here.
    Source identity remains bound to the existing publisher's exact parent.
    """
    from .portfolio_engine import _business_index_revision
    from .portfolio_company_names import add_public_company_names
    from .portfolio_public_sources import project_public_sources, _temporary_public_text_cache
    from .portfolio_public_fetch import _document_revision
    if (set(documents) != set(BUSINESS_SOURCE_FILES)
            or not _checked_receipt(artifact, receipt)):
        raise ValueError("company snapshot parent rejected")
    parent_raw = encode(receipt) if parent_raw is None else parent_raw
    if type(parent_raw) is not bytes or not 0 < len(parent_raw) <= 4096 or decode(parent_raw) != receipt:
        raise ValueError("company snapshot parent bytes rejected")
    with _temporary_public_text_cache():
        projected = project_public_sources(documents)
        catalog = add_public_company_names(documents, projected["companies"], _owned_catalog=True)
        by_id = {row["id"]: row for row in catalog}
        if _business_index_revision(documents, by_id, utc_day=receipt["utc_day"]) != receipt["source_revision"]:
            raise ValueError("company snapshot source generation mismatch")
    core_source_revision(source_hashes)  # Closed six-name and digest validation.
    revisions = {name: _document_revision(documents[name]) for name in BUSINESS_SOURCE_FILES}
    binding = {"source_revision": core_source_revision(revisions),
               "parent_source_revision": receipt["source_revision"],
               "implementation_sha256": receipt["implementation_sha256"],
               "projection_sha256": projection_sha256(), "utc_day": receipt["utc_day"], "scope": SCOPE}
    groups = {}
    for identifier, row in sorted(by_id.items()):
        # Closed public allowlist; do not publish a selected response or notes.
        public = {key: row[key] for key in ("id", "market", "ticker", "name", "sector", "facts", "documents")}
        if "source_names" in row:
            public["source_names"] = row["source_names"]
        groups.setdefault(company_bucket(identifier), {})[identifier] = public
    directory = Path(output_dir)
    if directory.exists() and any(directory.iterdir()):
        raise ValueError("new empty company snapshot output directory required")
    directory.mkdir(parents=True, exist_ok=True)
    manifest = {"schema": RELEASE_SCHEMA, **binding,
                "parent_receipt_sha256": sha256(parent_raw),
                "parent_artifact_sha256": receipt["artifact_sha256"],
                "source_sha256": dict(source_hashes),
                "company_count": len(by_id), "buckets": {}}
    for bucket, rows in sorted(groups.items()):
        raw = encode({"schema": BUCKET_SCHEMA, **binding, "companies": rows})
        if len(raw) > BUCKET_MAX_BYTES:
            raise ValueError("company snapshot bucket exceeds limit")
        digest = sha256(raw)
        (directory / (digest + ".json")).write_bytes(raw)
        manifest["buckets"][bucket] = {"sha256": digest, "bytes": len(raw), "companies": len(rows)}
    raw = encode(manifest)
    if len(raw) > RELEASE_MAX_BYTES:
        raise ValueError("company snapshot release exceeds limit")
    (directory / RELEASE_FILE).write_bytes(raw)
    return manifest


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("company snapshot redirect rejected")


def _read(filename, limit):
    if filename not in (RELEASE_FILE, RECEIPT_FILENAME) and not (
            filename.startswith(BUCKET_PREFIX) and filename.endswith(".json")
            and _HASH.fullmatch(filename[len(BUCKET_PREFIX):-5])):
        raise ValueError("company snapshot path rejected")
    url = PUBLIC_BLOB_BASE_URL + filename
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
    opener.addheaders = []
    with opener.open(urllib.request.Request(url, method="GET"), timeout=2) as response:
        if response.status != 200 or response.geturl() != url:
            raise ValueError("company snapshot response rejected")
        mime = response.headers.get("Content-Type", "").split(";", 1)[0].strip()
        if mime not in ("application/json", "text/json"):
            raise ValueError("company snapshot MIME rejected")
        raw = response.read(limit + 1)
        if not raw or len(raw) > limit:
            raise ValueError("company snapshot size rejected")
        return raw


def _positions(positions):
    if type(positions) is not list or not 1 <= len(positions) <= 30:
        raise ValueError("invalid company snapshot positions")
    result = []
    for row in positions:
        if type(row) is not dict or set(row) != {"ticker", "market"}:
            raise ValueError("invalid company snapshot position")
        if type(row["ticker"]) is not str or row["market"] not in ("KR", "US"):
            raise ValueError("invalid company snapshot identifier")
        identifier = row["market"] + ":" + row["ticker"]
        if not _ID.fullmatch(identifier) or identifier in [item["id"] for item in result]:
            raise ValueError("invalid company snapshot identifier")
        result.append({**row, "id": identifier})
    return result


def _selected_row(row, position):
    """Validate just the selected public records, reusing the source contracts."""
    def scalar(value, limit):
        return type(value) is str and 0 < len(value) <= limit and not re.search(r"[\x00-\x1f\x7f]", value)
    def text(value, limit):
        return type(value) is str and bool(value) and safe_public_text(value, limit) == value
    def date(value, annual=False):
        if type(value) is not str:
            return False
        if annual and re.fullmatch(r"(?:19|20)[0-9]{2}|2100", value):
            return True
        try:
            return datetime.strptime(value, "%Y-%m-%d").strftime("%Y-%m-%d") == value
        except ValueError:
            return False
    required = {"id", "market", "ticker", "name", "sector", "facts", "documents"}
    if (type(row) is not dict or not required <= row.keys() or row.keys() - required - {"source_names"}
            or any(row[key] != position[key] for key in ("id", "market", "ticker"))
            or not text(row["name"], 160)
            or row["sector"] is not None and not text(row["sector"], 120)
            or type(row["facts"]) is not list or len(row["facts"]) > 10000
            or type(row["documents"]) is not list or len(row["documents"]) > 10000):
        raise ValueError("company snapshot row rejected")
    if "source_names" in row and (type(row["source_names"]) is not list or len(row["source_names"]) > 4
            or any(not text(value, 160) for value in row["source_names"])):
        raise ValueError("company snapshot names rejected")
    for fact in row["facts"]:
        if (type(fact) is not dict or fact.keys() not in (_BASE_FACT_KEYS, _BASE_FACT_WITH_PROVENANCE)
                or type(fact["value"]) not in (int, float) or not math.isfinite(fact["value"])
                or not text(fact["metric"], 80) or not text(fact["unit"], 30)
                or not date(fact["as_of"], annual=True) or fact["source"] not in ("DART", "SEC", "KRX")):
            raise ValueError("company snapshot fact rejected")
        proof = fact.get("provenance")
        if "provenance" in fact and (type(proof) is not dict or not proof.keys() <= _BASE_PROVENANCE_KEYS
                or any(type(value) is not bool and not scalar(value, 600) for value in proof.values())):
            raise ValueError("company snapshot provenance rejected")
    seen = set()
    for doc in row["documents"]:
        if (type(doc) is not dict or not _BASE_DOCUMENT_KEYS <= doc.keys()
                or doc.keys() - _BASE_DOCUMENT_KEYS - {"item_codes", "filing"}
                or not scalar(doc["id"], 400) or not text(doc["title"], 300)
                or not scalar(doc["url"], 600) or not date(doc["as_of"])
                or doc["kind"] != "disclosure" or doc["source"] not in ("DART", "SEC")
                or _canonical_disclosure_url(doc["url"], doc["source"]) != (doc["url"], doc["id"])
                or doc["id"] in seen):
            raise ValueError("company snapshot document rejected")
        seen.add(doc["id"])
        if "item_codes" in doc and (doc["source"] != "SEC" or type(doc["item_codes"]) is not list
                or len(doc["item_codes"]) > 32 or any(type(code) is not str or not re.fullmatch(r"[1-9]\.[0-9]{2}", code) for code in doc["item_codes"])):
            raise ValueError("company snapshot item codes rejected")
        if "filing" in doc:
            filing = doc["filing"]
            if (row["market"] != "US" or doc["source"] != "SEC" or type(filing) is not dict
                    or filing.keys() != _BASE_FILING_KEYS
                    or any(type(value) not in (str, bool, type(None)) or type(value) is str and len(value) > 240 for value in filing.values())
                    or _sec_filing({**filing, "label": filing["form"], "primary_document": filing["primary_document"] or ""}, doc["url"], doc["as_of"]) != filing):
                raise ValueError("company snapshot filing rejected")
    return row


def read_company_snapshot(positions, *, _reader=None):
    """Fixed public locations only, selected buckets only, request-local output."""
    requested = _positions(positions)
    reader = _reader or _read
    with ThreadPoolExecutor(max_workers=2) as pool:
        manifest_future = pool.submit(reader, RELEASE_FILE, RELEASE_MAX_BYTES)
        parent_future = pool.submit(reader, RECEIPT_FILENAME, 4096)
        manifest_raw, parent_raw = manifest_future.result(), parent_future.result()
    manifest, parent = decode(manifest_raw), decode(parent_raw)
    if (type(manifest) is not dict or set(manifest) != {"schema", *_BINDING,
            "parent_receipt_sha256", "parent_artifact_sha256", "source_sha256", "company_count", "buckets"}
            or manifest["schema"] != RELEASE_SCHEMA or manifest["scope"] != SCOPE
            or not _published_day(manifest["utc_day"])
            or manifest["implementation_sha256"] != implementation_sha256()
            or manifest["projection_sha256"] != projection_sha256()
            or type(parent) is not dict or set(parent) != {
                "schema", "artifact_sha256", "source_revision", "implementation_sha256", "utc_day"}
            or parent["schema"] != RECEIPT_SCHEMA
            or sha256(parent_raw) != manifest["parent_receipt_sha256"]
            or parent["artifact_sha256"] != manifest["parent_artifact_sha256"]
            or parent["source_revision"] != manifest["parent_source_revision"]
            or any(parent[key] != manifest[key] for key in ("implementation_sha256", "utc_day"))
            or any(type(manifest[key]) is not str or not _HASH.fullmatch(manifest[key]) for key in
                   ("source_revision", "parent_source_revision", "implementation_sha256", "projection_sha256", "parent_receipt_sha256", "parent_artifact_sha256"))
            or type(manifest["company_count"]) is not int or not 0 <= manifest["company_count"] <= 50000
            or type(manifest["buckets"]) is not dict or len(manifest["buckets"]) > 256):
        raise ValueError("company snapshot release rejected")
    core_source_revision(manifest["source_sha256"])
    total = 0
    for key, entry in manifest["buckets"].items():
        if (not _BUCKET.fullmatch(key) or type(entry) is not dict
                or set(entry) != {"sha256", "bytes", "companies"}
                or type(entry["sha256"]) is not str or not _HASH.fullmatch(entry["sha256"])
                or type(entry["bytes"]) is not int or not 1 <= entry["bytes"] <= BUCKET_MAX_BYTES
                or type(entry["companies"]) is not int or not 1 <= entry["companies"] <= 50000):
            raise ValueError("company snapshot bucket declaration rejected")
        total += entry["companies"]
    if total != manifest["company_count"]:
        raise ValueError("company snapshot denominator rejected")
    bucket_keys = sorted({company_bucket(row["id"]) for row in requested})
    if any(key not in manifest["buckets"] for key in bucket_keys):
        raise ValueError("company snapshot bucket missing")
    def load(key):
        entry = manifest["buckets"][key]
        raw = reader(BUCKET_PREFIX + entry["sha256"] + ".json", entry["bytes"])
        if len(raw) != entry["bytes"] or sha256(raw) != entry["sha256"]:
            raise ValueError("company snapshot exact bytes rejected")
        body = decode(raw)
        if (type(body) is not dict or set(body) != {"schema", *_BINDING, "companies"}
                or body["schema"] != BUCKET_SCHEMA
                or any(body[name] != manifest[name] for name in _BINDING)
                or type(body["companies"]) is not dict or len(body["companies"]) != entry["companies"]
                or any(not _ID.fullmatch(identifier) or company_bucket(identifier) != key
                       for identifier in body["companies"])):
            raise ValueError("company snapshot generation rejected")
        return body["companies"]
    with ThreadPoolExecutor(max_workers=min(8, len(bucket_keys))) as pool:
        buckets = dict(zip(bucket_keys, pool.map(load, bucket_keys)))
    rows = []
    for position in requested:
        row = buckets[company_bucket(position["id"])].get(position["id"])
        if row is None:
            raise ValueError("company snapshot company missing")
        rows.append(deepcopy(_selected_row(row, position)))
    return compose_core_payload(rows, requested, manifest, sha256(manifest_raw))


def compose_core_payload(rows, requested, manifest, manifest_sha):
    """Core-only v1 projection for the existing strict client adapter.

    No portfolio-wide relation/AI/price claims. The UI must keep this partial
    read-only until its ordinary full analysis has been applied.
    """
    documents, companies = {}, []
    for row in rows:
        company = {key: deepcopy(row[key]) for key in ("id", "ticker", "market", "name", "facts")}
        company["document_ids"] = []
        if len(row.get("source_names", [])) > 1:
            company["source_names"] = deepcopy(row["source_names"])
        if row.get("sector"):
            company["sector"] = row["sector"]
        for doc in row["documents"]:
            public = {key: deepcopy(doc[key]) for key in ("id", "title", "url", "as_of", "kind", "source")}
            if "filing" in doc:
                public["filing"] = deepcopy(doc["filing"])
            prior = documents.get(public["id"])
            if prior is not None and {key: value for key, value in prior.items() if key != "company_ids"} != public:
                raise ValueError("company snapshot document identity conflict")
            if prior is None:
                documents[public["id"]] = {**public, "company_ids": []}
            documents[public["id"]]["company_ids"].append(row["id"])
            company["document_ids"].append(public["id"])
        companies.append(company)
    ordered = sorted(documents.values(), key=lambda doc: (doc["as_of"], doc["id"]), reverse=True)
    returned = ordered[:60]
    allowed = {doc["id"] for doc in returned}
    for company in companies:
        company["document_ids"] = [identifier for identifier in company["document_ids"] if identifier in allowed]
    for doc in returned:
        doc["company_ids"].sort()
    result = {"schema": "alphaconsole-portfolio-v1", "companies": companies,
        "documents": returned, "coverage": {"requested": len(requested), "matched": len(companies),
            "missing": [], "missing_source_files": [],
            "evidence": {"document_records": {"total": len(ordered), "returned": len(returned),
                "omitted": len(ordered) - len(returned)}}, "ai_review": {"status": "unavailable"}},
        "_meta": {"delivery": "private-response-only", "shared_cache": False,
            "snapshot_scope": SCOPE, "snapshot_release": manifest_sha,
            "core_claims": core_claims(rows),
            "source_revision": manifest["source_revision"], "utc_day": manifest["utc_day"],
            "pending": ["relations", "judgments", "market-context", "prices", "changes"],
            "external_model_calls": 0, "operator_private_sources_used": False}}
    result["revision"] = sha256(encode(result))
    return result


def core_claims(rows):
    """Bounded content inclusion proof, before a response document cap.

    Extra overlay facts/documents may extend this set. Collection clocks are
    absent; original financial periods and filing dates remain in the hashes.
    """
    claims, count = {}, 0
    for row in rows:
        items = set()
        for fact in row.get("facts", []):
            items.add("f:" + sha256(encode(fact)))
        for doc in row.get("documents", []):
            core = {key: doc[key] for key in ("id", "title", "url", "as_of", "kind", "source")}
            items.add("d:" + sha256(encode(core)))
            if "filing" in doc:
                items.add("p:" + sha256(encode([doc["id"], doc["filing"]])))
        count += len(items)
        if count > 4096:
            return {"status": "unbounded"}
        claims[row["id"]] = sorted(items)
    return {"status": "ready", "companies": claims}
