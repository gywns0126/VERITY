"""Publisher-bound public business index; never accepts member inputs.

The trusted publisher writes the receipt last from the same staged sources.
Neither a candidate artifact nor a self-declared hash authorizes promotion.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import base64
import gzip
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import re
import threading
import time
import unicodedata
import urllib.error
import urllib.request
import zlib

from .portfolio_public_sources import (project_public_business_overviews, safe_public_text,
    BASE_PROJECTION_FILES, PUBLIC_COMPANY_FIELDS, PUBLIC_FACT_FIELDS, PUBLIC_DOCUMENT_FIELDS,
    base_projection_revision, project_public_sources)


SCHEMA = "portfolio-public-business-index-v1"
RECEIPT_SCHEMA = "portfolio-public-business-release-v1"
ARTIFACT_FILENAME = "portfolio_public_business_index.json"
RECEIPT_FILENAME = "portfolio_public_business_release.json"
# Only these public inputs affect company identity, names, or business excerpts.
# The runtime public-bundle coverage remains the separate 16-source contract.
BUSINESS_SOURCE_FILES = (
    "universe_search.json",
    "stock_report_public.json",
    "us_stock_report_public.json",
    "public_disclosure_feed.json",
    "us_disclosure_feed.json",
    "kr_business_overview_public.json",
)
ARTIFACT_MAX_BYTES = 8 * 1024 * 1024
RECEIPT_MAX_BYTES = 4096
PUBLIC_BLOB_BASE_URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/"
FETCH_TIMEOUT_SECONDS = 2
_CACHE_TTL_SECONDS = 60
_MAX_JSON_DEPTH = 32
_FETCH_LOCK = threading.Lock()
_FETCH_CACHE = None
_FETCH_EXPIRES_AT = 0.0
# Bump on any change to business matching, role/context indexing, or envelope.
MATCHER_VERSION = "business-matchers-2026-10-27-v3"
_BASE_MAX_BYTES = 64 * 1024 * 1024
_BASE_COMPANY_KEYS = frozenset(PUBLIC_COMPANY_FIELDS)
_BASE_FACT_KEYS = frozenset(PUBLIC_FACT_FIELDS)
_BASE_FACT_WITH_PROVENANCE = _BASE_FACT_KEYS | {"provenance"}
_BASE_DOCUMENT_KEYS = frozenset(PUBLIC_DOCUMENT_FIELDS)
_BASE_DOCUMENT_WITH_CODES = _BASE_DOCUMENT_KEYS | {"item_codes"}
_BASE_PROVENANCE_KEYS = frozenset({"kind", "rcept_no", "period_start", "period_end",
    "filed", "fs_div", "account_name", "source_url", "cik", "accession", "form",
    "tag", "currency_verified"})
_DIGEST = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_MATERIAL_KEYS = {"stable_id", "kind", "verified_event", "participants", "source", "evidence"}
_SOURCE_KEYS = {"id", "kind", "receipt_no", "as_of", "report_name", "url",
                "document_issuer", "artifact_observed_at", "revision"}
_MATERIAL_EVIDENCE_KEYS = {"anchor", "char_start", "char_end", "excerpt",
                           "published_excerpt_truncated", "fiscal_year"}
_RELATION_KEYS = {"stable_id", "type", "status", "verification", "snapshot_scope",
                  "label", "participants", "source", "evidence", "revision"}
_ROLE_EVIDENCE_KEYS = {"role", "raw_name", "quote", "char_start", "char_end",
                       "source_field", "field_sha256", "fiscal_year",
                       "published_excerpt_truncated"}
_IMPLEMENTATION_FILES = (
    "portfolio_engine.py", "portfolio_prepared_business.py",
    "portfolio_public_sources.py", "portfolio_company_names.py",
    "portfolio_business_roles.py", "portfolio_market_context.py",
    "portfolio_filing_excerpts.py",
)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("prepared public redirect rejected")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate prepared public JSON key")
        result[key] = value
    return result


def _reject_constant(_value):
    raise ValueError("nonfinite prepared public JSON value")


def _bounded_json_depth(value):
    pending = [(value, 0)]
    while pending:
        item, depth = pending.pop()
        if depth > _MAX_JSON_DEPTH:
            return False
        if type(item) is dict:
            pending.extend((child, depth + 1) for child in item.values())
        elif type(item) is list:
            pending.extend((child, depth + 1) for child in item)
        elif type(item) not in (str, int, float, bool, type(None)):
            return False
    return True


def _copy_or_miss(pair):
    try:
        return deepcopy(pair)
    except (RecursionError, TypeError, ValueError):
        return None, None


def _read_fixed_public_json(filename, limit):
    url = PUBLIC_BLOB_BASE_URL + filename
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    opener = urllib.request.build_opener(_NoRedirect(), urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=FETCH_TIMEOUT_SECONDS) as response:
        if (response.status != 200 or response.geturl() != url
                or int(response.headers.get("Content-Length") or "0") > limit):
            raise ValueError("prepared public response rejected")
        raw = response.read(limit + 1)
        if not raw or len(raw) > limit:
            raise ValueError("prepared public response exceeds limit")
    value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object,
                       parse_constant=_reject_constant)
    if not _bounded_json_depth(value):
        raise ValueError("prepared public JSON depth rejected")
    return value


def fetch_publisher_prepared_business(*, _reader=None):
    """Read only two fixed public objects; failure leaves source computation intact.

    Successful and failed reads are cached for at most one minute. A cached
    failure remains a miss; the caller must still validate any successful pair
    against its current public source bundle before use.
    """
    global _FETCH_CACHE, _FETCH_EXPIRES_AT
    reader = _reader or _read_fixed_public_json
    if _reader is None and _FETCH_CACHE is not None and time.monotonic() < _FETCH_EXPIRES_AT:
        return _copy_or_miss(_FETCH_CACHE)
    with _FETCH_LOCK:
        if _reader is None and _FETCH_CACHE is not None and time.monotonic() < _FETCH_EXPIRES_AT:
            return _copy_or_miss(_FETCH_CACHE)
        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                artifact_future = pool.submit(reader, ARTIFACT_FILENAME, ARTIFACT_MAX_BYTES)
                receipt_future = pool.submit(reader, RECEIPT_FILENAME, RECEIPT_MAX_BYTES)
                artifact, receipt = artifact_future.result(), receipt_future.result()
            pair = ((artifact, receipt) if type(artifact) is dict and type(receipt) is dict
                    and _bounded_json_depth(artifact) and _bounded_json_depth(receipt)
                    else (None, None))
            if _reader is None:
                _FETCH_CACHE = pair
                _FETCH_EXPIRES_AT = time.monotonic() + _CACHE_TTL_SECONDS
            return _copy_or_miss(pair)
        except (OSError, ValueError, TypeError, UnicodeError, TimeoutError, RecursionError,
                urllib.error.URLError):
            if _reader is None:
                _FETCH_CACHE = (None, None)
                _FETCH_EXPIRES_AT = time.monotonic() + _CACHE_TTL_SECONDS
            return None, None


def implementation_sha256():
    """Bind the candidate to the exact matcher code deployed with it."""
    digest = hashlib.sha256()
    directory = Path(__file__).resolve().parent
    for name in _IMPLEMENTATION_FILES:
        digest.update(name.encode("ascii"))
        digest.update(b"\0")
        digest.update((directory / name).read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def artifact_sha256(artifact):
    """Canonical digest of the complete reviewed JSON payload."""
    return hashlib.sha256(json.dumps(
        artifact, sort_keys=True, ensure_ascii=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")).hexdigest()


def publisher_receipt_for(artifact):
    """Create the commit marker from the publisher's built artifact."""
    return {"schema": RECEIPT_SCHEMA,
            "artifact_sha256": artifact_sha256(artifact),
            "source_revision": artifact["source_revision"],
            "implementation_sha256": artifact["implementation_sha256"],
            "utc_day": artifact["utc_day"]}


def pack_base_projection(documents):
    """Offline only: sanitize the same public rows before packing them."""
    if not all(name in documents for name in BASE_PROJECTION_FILES):
        return None
    selected = {name: documents[name] for name in BASE_PROJECTION_FILES}
    revisions = {name: artifact_sha256(value) for name, value in selected.items()}
    companies = project_public_sources(selected)["companies"]
    raw = json.dumps(companies, sort_keys=True, ensure_ascii=True,
                     separators=(",", ":"), allow_nan=False).encode("utf-8")
    if len(raw) > _BASE_MAX_BYTES:
        return None  # Optimization miss, never truncate source facts.
    return {"source_revision": base_projection_revision(revisions),
            "encoding": "gzip-base64-v1",
            "data": base64.b64encode(gzip.compress(raw, mtime=0)).decode("ascii")}


def _checked_receipt(artifact, receipt):
    """The fixed publisher receipt is the trust boundary, not embedded claims."""
    try:
        code = implementation_sha256()
        day = datetime.now(timezone.utc).date().isoformat()
        return (type(artifact) is dict and set(artifact) == {
                    "schema", "matcher_version", "implementation_sha256", "source_revision",
                    "utc_day", "catalog", "index", "base_projection"}
                and artifact["schema"] == SCHEMA and artifact["matcher_version"] == MATCHER_VERSION
                and artifact["implementation_sha256"] == code and artifact["utc_day"] == day
                and type(receipt) is dict and set(receipt) == {
                    "schema", "artifact_sha256", "source_revision", "implementation_sha256", "utc_day"}
                and receipt["schema"] == RECEIPT_SCHEMA
                and receipt["implementation_sha256"] == code and receipt["utc_day"] == day
                and receipt["source_revision"] == artifact["source_revision"]
                and artifact_sha256(artifact) == receipt["artifact_sha256"])
    except (KeyError, TypeError, ValueError, RecursionError, OSError):
        return False


def checked_base_projection(artifact, receipt, source_revision):
    """Decode an owned base only after exact source/code/day/receipt binding.

    This does not promote relations or freshness. Missing, mixed-publication,
    stale or malformed data uses the unchanged full source projector instead.
    """
    try:
        packed = artifact.get("base_projection") if type(artifact) is dict else None
        if (type(source_revision) is not str or not _DIGEST.fullmatch(source_revision)
                or type(packed) is not dict
                or set(packed) != {"source_revision", "encoding", "data"}
                or packed["source_revision"] != source_revision
                or packed["encoding"] != "gzip-base64-v1"
                or type(packed["data"]) is not str or len(packed["data"]) > ARTIFACT_MAX_BYTES
                or not _checked_receipt(artifact, receipt)):
            return None
        compressed = base64.b64decode(packed["data"], validate=True)
        decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
        raw = decoder.decompress(compressed, _BASE_MAX_BYTES + 1)
        if (len(raw) > _BASE_MAX_BYTES or not decoder.eof
                or decoder.unconsumed_tail or decoder.unused_data):
            return None
        companies = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object,
                               parse_constant=_reject_constant)
        if type(companies) is not list or len(companies) > 50000:
            return None
        seen, facts, documents = set(), 0, 0
        for row in companies:
            if (type(row) is not dict or row.keys() != _BASE_COMPANY_KEYS
                    or row["market"] not in {"KR", "US"} or type(row["ticker"]) is not str
                    or row["id"] != row["market"] + ":" + row["ticker"]
                    or not re.fullmatch(r"KR:[0-9]{6}|US:[A-Z][A-Z0-9]{0,9}(?:[.-][A-Z0-9]{1,2})?", row["id"])
                    or row["id"] in seen or type(row["name"]) is not str
                    or safe_public_text(row["name"], 160) != row["name"]
                    or row["sector"] is not None and safe_public_text(row["sector"], 120) != row["sector"]
                    or type(row["facts"]) is not list or type(row["documents"]) is not list):
                return None
            seen.add(row["id"])
            facts += len(row["facts"])
            documents += len(row["documents"])
            if facts > 1000000 or documents > 500000:
                return None
            for fact in row["facts"]:
                if (type(fact) is not dict or fact.keys() not in (
                        _BASE_FACT_KEYS, _BASE_FACT_WITH_PROVENANCE)
                        or type(fact["value"]) not in (int, float)
                        or any(type(fact[key]) is not str for key in ("metric", "unit", "as_of", "source"))
                        or fact["source"] not in {"DART", "SEC", "KRX"}):
                    return None
                # The publisher already ran source/provenance validation. This
                # closed, scalar-only shape bounds depth without traversing the
                # same million JSON leaves a second time on every cold request.
                proof = fact.get("provenance")
                if "provenance" in fact and (type(proof) is not dict
                        or not proof.keys() <= _BASE_PROVENANCE_KEYS
                        or any(type(value) not in (str, bool) or
                               type(value) is str and len(value) > 600 for value in proof.values())):
                    return None
            ids = set()
            for document in row["documents"]:
                if (type(document) is not dict or document.keys() not in (
                        _BASE_DOCUMENT_KEYS, _BASE_DOCUMENT_WITH_CODES)
                        or any(type(document[key]) is not str for key in PUBLIC_DOCUMENT_FIELDS)
                        or safe_public_text(document["title"], 300) != document["title"]
                        or document["id"] in ids):
                    return None
                codes = document.get("item_codes")
                if "item_codes" in document and (type(codes) is not list or len(codes) > 32
                        or any(type(code) is not str or not re.fullmatch(r"[1-9]\.[0-9]{2}", code) for code in codes)):
                    return None
                ids.add(document["id"])
        return companies
    except (AttributeError, KeyError, TypeError, ValueError, UnicodeError,
            RecursionError, OverflowError, zlib.error):
        return None


def identity_catalog(by_id):
    """Closed public matcher inputs, in the publisher's original catalog order."""
    return [{key: row.get(key) for key in ("id", "market", "name", "source_names")}
            for row in by_id.values()]


def compatible_catalog_revision(artifact, documents, by_id, revision_for):
    """Prove that added identities cannot affect any existing business excerpt.

    All prior identities, names, aliases, excerpts, declarations and UTC day
    remain bound. Any possible new issuer/name hit takes the full matcher path.
    The returned revision still requires normal code/receipt/index validation.
    """
    try:
        catalog = artifact.get("catalog")
        if type(catalog) is not list or not 1 <= len(catalog) <= 50000:
            return None
        original = {}
        for row in catalog:
            if (type(row) is not dict or set(row) != {"id", "market", "name", "source_names"}
                    or type(row["id"]) is not str or row["id"] in original
                    or row != {key: by_id.get(row["id"], {}).get(key) for key in row}):
                return None
            original[row["id"]] = row
        added = set(by_id) - original.keys()
        if not added or len(added) > 100:
            return None
        business = project_public_business_overviews(documents)
        if any(row["issuer_id"] in added for row in business["rows"]):
            return None
        # A conservative substring gate also catches legal-name normalization,
        # alias ambiguity and product-name collisions. False positives rebuild.
        def normalized(value):
            text = unicodedata.normalize("NFKC", value).casefold()
            text = re.sub(r"\(주[0-9]+\)|\(주석[0-9]+\)", "", text)
            return re.sub(r"\s+", "", text)
        texts = [normalized(row["text"]) for row in business["rows"]]
        aliases = []
        for identifier in added:
            row = by_id[identifier]
            aliases.extend([row.get("name"), *(row.get("source_names") or [])])
        declarations = documents.get("universe_search.json", {}).get("stocks", [])
        declarations = declarations.values() if type(declarations) is dict else declarations
        for row in declarations:
            market = "KR" if row.get("market") == "KONEX" else row.get("market")
            if f"{market}:{row.get('ticker')}" in added:
                aliases.extend([row.get("name"), row.get("name_ko")])
        for alias in aliases:
            if alias is None:
                continue
            if type(alias) is not str:
                return None
            key = normalized(alias)
            key = re.sub(r"^(?:주식회사|\(주\))|(?:주식회사|\(주\))$", "", key)
            if not key or any(key in text for text in texts):
                return None
        return revision_for(documents, original)
    except (AttributeError, KeyError, TypeError, ValueError, UnicodeError, RecursionError):
        return None


def checked_business_index(artifact, publisher_receipt, source_revision, documents, by_id):
    """Return a vetted common index, or None to use the existing computation.

    Source equality and today's UTC boundary are checked independently of the
    publisher receipt. Basic source/identifier checks guard malformed data;
    the receipt is trusted only because the existing publisher emits it last.
    """
    if (type(source_revision) is not str or not _DIGEST.fullmatch(source_revision)
            or type(artifact) is not dict
            or set(artifact) != {"schema", "matcher_version", "implementation_sha256",
                                 "source_revision", "utc_day", "catalog", "index", "base_projection"}
            or artifact["schema"] != SCHEMA
            or artifact["matcher_version"] != MATCHER_VERSION
            or artifact["source_revision"] != source_revision
            or type(publisher_receipt) is not dict
            or set(publisher_receipt) != {"schema", "artifact_sha256", "source_revision",
                                               "implementation_sha256", "utc_day"}
            or publisher_receipt["schema"] != RECEIPT_SCHEMA):
        return None
    try:
        code_digest = implementation_sha256()
        today = datetime.now(timezone.utc).date().isoformat()
        if (artifact["implementation_sha256"] != code_digest
                or artifact["utc_day"] != today
                or publisher_receipt["source_revision"] != source_revision
                or publisher_receipt["implementation_sha256"] != code_digest
                or publisher_receipt["utc_day"] != today):
            return None
        if (not _bounded_json_depth(artifact)
                or not _bounded_json_depth(publisher_receipt)):
            return None
        if (type(publisher_receipt["artifact_sha256"]) is not str
                or not _DIGEST.fullmatch(publisher_receipt["artifact_sha256"])
                or artifact_sha256(artifact) != publisher_receipt["artifact_sha256"]):
            return None
        index = artifact["index"]
        if (type(index) is not dict or set(index) != {
                "materials", "by_company", "coverage", "market_context", "reported_roles"}):
            return None
        materials, by_company = index["materials"], index["by_company"]
        if (type(materials) is not dict or len(materials) > 5000
                or type(by_company) is not dict or len(by_company) > len(by_id)
                or type(index["coverage"]) is not dict
                or type(index["market_context"]) is not dict
                or type(index["reported_roles"]) is not dict):
            return None
        if (set(index["coverage"]) != {"status", "input", "accepted", "rejected",
                                         "missing", "generated_at", "indexed_materials",
                                         "unknown_issuer", "no_unique_other_company_mention",
                                         "ambiguous_alias_only", "companies_with_materials"}
                or set(index["market_context"]) != {
                    "by_indicator", "power", "infrastructure", "coverage"}
                or set(index["reported_roles"]) != {"relations", "by_company", "coverage"}):
            return None
        rows = project_public_business_overviews(documents)["rows"]
        source_rows = {(row["issuer_id"], row["source"]["id"]): row for row in rows}
        if index["coverage"].get("missing") != ("kr_business_overview_public.json" not in documents):
            return None
        for identifier, material in materials.items():
            if (type(identifier) is not str or type(material) is not dict
                    or set(material) != _MATERIAL_KEYS
                    or material.get("stable_id") != identifier
                    or material.get("kind") != "co_mention_candidate"
                    or material.get("verified_event") is not False):
                return None
            participants, source, evidence = (material.get(key) for key in
                                              ("participants", "source", "evidence"))
            if (type(participants) is not list or len(participants) < 2
                    or type(source) is not dict or set(source) != _SOURCE_KEYS
                    or type(evidence) is not dict or set(evidence) != _MATERIAL_EVIDENCE_KEYS):
                return None
            issuer = participants[0].get("id") if type(participants[0]) is dict else None
            row = source_rows.get((issuer, source.get("id")))
            if (row is None or issuer not in by_id
                    or participants[0].get("role") != "document_issuer"
                    or any(set(p) != {"id", "role"} for p in participants if type(p) is dict)
                    or len({p.get("id") for p in participants if type(p) is dict}) != len(participants)
                    or any(type(p) is not dict or p.get("role") != "mentioned_company"
                           or p.get("id") not in by_id for p in participants[1:])
                    or evidence.get("excerpt") != row["text"]
                    or safe_public_text(evidence.get("excerpt"), 600) is None
                    or evidence.get("fiscal_year") != row["fiscal_year"]
                    or evidence.get("char_start") != 0
                    or evidence.get("char_end") != len(row["text"])
                    or evidence.get("published_excerpt_truncated") != row["truncated"]
                    or source.get("receipt_no") != row["source"]["receipt_no"]
                    or source.get("as_of") != row["source"]["as_of"]
                    or any(source.get(key) != value for key, value in row["source"].items())
                    or source.get("artifact_observed_at") is not None):
                return None
        for company, identifiers in by_company.items():
            if (company not in by_id or type(identifiers) is not list
                    or len(identifiers) > len(materials)
                    or any(identifier not in materials or company not in {
                        row["id"] for row in materials[identifier]["participants"]
                    } for identifier in identifiers)):
                return None
        expected_links = {}
        for identifier, material in materials.items():
            for participant in material["participants"]:
                expected_links.setdefault(participant["id"], []).append(identifier)
        # Canonical JSON sorts material object keys, but preserves link arrays.
        # Link membership is semantic; array order is not. Sorting retains the
        # duplicate/missing/extra-link rejection while surviving serialization.
        if ({key: sorted(values) for key, values in by_company.items()}
                != {key: sorted(values) for key, values in expected_links.items()}):
            return None
        coverage = index["coverage"]
        if (coverage.get("indexed_materials") != len(materials)
                or coverage.get("companies_with_materials") != len(by_company)
                or coverage.get("accepted") != len(rows)):
            return None
        roles = index["reported_roles"]
        if (type(roles["relations"]) is not list or len(roles["relations"]) > 50000
                or type(roles["by_company"]) is not dict
                or type(roles["coverage"]) is not dict
                or set(roles["coverage"]) != {"input", "candidate_sentences",
                                               "relationships", "unresolved_names",
                                               "rejection_reasons"}
                or roles["coverage"]["relationships"] != len(roles["relations"])):
            return None
        for relation in roles["relations"]:
            if (type(relation) is not dict or set(relation) != _RELATION_KEYS
                    or type(relation["source"]) is not dict
                    or set(relation["source"]) != _SOURCE_KEYS
                    or type(relation["evidence"]) is not dict
                    or set(relation["evidence"]) != _ROLE_EVIDENCE_KEYS
                    or type(relation["participants"]) is not list
                    or len(relation["participants"]) != 2):
                return None
            issuer, target = relation["participants"]
            if (type(issuer) is not dict or set(issuer) != {"id", "role", "name"}
                    or type(target) is not dict or set(target) != {"id", "role"}
                    or issuer["id"] not in by_id or target["id"] not in by_id
                    or issuer["name"] != by_id[issuer["id"]]["name"]
                    or issuer["role"] != "document_issuer"
                    or target["role"] not in {"reported_customer", "reported_supplier"}):
                return None
            source = relation["source"]
            row = source_rows.get((issuer["id"], source["id"]))
            evidence = relation["evidence"]
            start, end = evidence.get("char_start"), evidence.get("char_end")
            if (row is None or any(source.get(key) != value for key, value in row["source"].items())
                    or source.get("artifact_observed_at") is not None
                    or type(start) is not int or type(end) is not int
                    or not 0 <= start < end <= len(row["text"])
                    or evidence.get("quote") != row["text"][start:end]
                    or evidence.get("fiscal_year") != row["fiscal_year"]
                    or evidence.get("published_excerpt_truncated") != row["truncated"]):
                return None
        return index
    except (AttributeError, KeyError, TypeError, ValueError, OverflowError,
            RecursionError, UnicodeError, OSError):
        return None
