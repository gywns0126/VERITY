"""Public, read-only company-structure facts addressed by market and ticker."""
from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qsl, urlsplit
import hashlib
import json
import re
import threading
import time
import urllib.request


PUBLIC_BASE = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/"
INDEX_URL = PUBLIC_BASE + "member_map_company_structure_index.json"
INDEX_SCHEMA = "alphanest-company-structure-index-v1"
PAYLOAD_SCHEMA = "alphanest-company-structure-v1"
INDEX_MAX_BYTES = 2 * 1024 * 1024
PAYLOAD_MAX_BYTES = 2 * 1024 * 1024
MAX_ISSUERS = 25000
MAX_NODES = 3000
MAX_RELATIONS = 3000
MANIFEST_TTL = 60
PAYLOAD_CACHE_SIZE = 32
FETCH_TIMEOUT = 8

_KR = re.compile(r"[A-Z0-9]{6}\Z", re.ASCII)
_US = re.compile(r"[A-Z][A-Z0-9.-]{0,11}\Z", re.ASCII)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_SEC_EVIDENCE = re.compile(r"/Archives/edgar/data/[0-9]+/[0-9]{18}/[A-Za-z0-9_.-]+\.(?:htm|html|txt)\Z", re.I | re.ASCII)
_DART_RECEIPT = re.compile(r"[0-9]{14}\Z", re.ASCII)
_SOURCE_STATUSES = {"source-checked", "partial", "not-attempted",
                    "refresh-error", "legacy-only", "curated-only"}
_MANIFEST_CACHE = None  # (monotonic expiry, validated manifest)
_PAYLOAD_CACHE = OrderedDict()  # sha256 -> validated payload
_CACHE_LOCK = threading.RLock()


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("company-structure redirect rejected")


def _read_public_bytes(url, limit):
    """Read only a caller-independent URL, without proxies, redirects or auth headers."""
    if url != INDEX_URL and not re.fullmatch(
            re.escape(PUBLIC_BASE + "company-structure/") + r"[0-9a-f]{64}\.json", url):
        raise ValueError("company-structure URL rejected")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
    opener.addheaders = []
    request = urllib.request.Request(url, method="GET")
    with opener.open(request, timeout=FETCH_TIMEOUT) as response:
        status = getattr(response, "status", None)
        if status is None:
            status = response.getcode()
        if status != 200 or response.geturl() != url:
            raise ValueError("company-structure response rejected")
        declared = response.headers.get("Content-Length")
        if declared is not None:
            try:
                if int(declared) < 0 or int(declared) > limit:
                    raise ValueError("company-structure response rejected")
            except (TypeError, ValueError):
                raise ValueError("company-structure response rejected") from None
        raw = response.read(limit + 1)
    if not isinstance(raw, bytes) or len(raw) > limit:
        raise ValueError("company-structure response rejected")
    return raw


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(_value):
    raise ValueError("invalid JSON number")


def _loads(raw, maximum):
    if not isinstance(raw, bytes) or not raw or len(raw) > maximum:
        raise ValueError("company-structure document size rejected")
    return json.loads(raw.decode("utf-8", "strict"), object_pairs_hook=_unique_object,
                      parse_constant=_reject_constant)


def _ticker_valid(market, ticker):
    return (isinstance(ticker, str) and
            (_KR.fullmatch(ticker) if market == "KR" else
             _US.fullmatch(ticker) if market == "US" else False))


def _issuer_key_valid(key, row):
    if not isinstance(key, str) or not isinstance(row, dict):
        return False
    if not isinstance(row.get("market"), str) or not isinstance(row.get("ticker"), str):
        return False
    return key == f"{row['market']}:{row['ticker']}" and _ticker_valid(row["market"], row["ticker"])


def _validate_manifest(raw):
    doc = _loads(raw, INDEX_MAX_BYTES)
    issuers = doc.get("issuers") if isinstance(doc, dict) else None
    if (not isinstance(doc, dict) or doc.get("schema") != INDEX_SCHEMA
            or not isinstance(doc.get("generatedAt"), str) or not doc["generatedAt"].strip()
            or not isinstance(issuers, dict) or len(issuers) > MAX_ISSUERS
            or not isinstance(doc.get("coverage"), dict)
            or _contains_url_field(doc["coverage"])):
        raise ValueError("company-structure manifest rejected")
    for issuer_id, row in issuers.items():
        if (not _issuer_key_valid(issuer_id, row)
                or not isinstance(row.get("name"), str) or not row["name"].strip()
                or len(row["name"]) > 300 or re.search(r"[\x00-\x1f\x7f]", row["name"])
                or row.get("status") not in _SOURCE_STATUSES):
            raise ValueError("company-structure issuer rejected")
        digest, size = row.get("sha256"), row.get("bytes")
        if digest is None and size is None:
            continue
        elif (not isinstance(digest, str) or not _SHA256.fullmatch(digest)
              or isinstance(size, bool) or not isinstance(size, int)
              or not 1 <= size <= PAYLOAD_MAX_BYTES):
            raise ValueError("company-structure payload metadata rejected")
    return doc


def _get_manifest():
    global _MANIFEST_CACHE
    now = time.monotonic()
    with _CACHE_LOCK:
        cached = _MANIFEST_CACHE
        if cached and now < cached[0]:
            return deepcopy(cached[1])
    # A failed refresh propagates; the expired object is never returned as current.
    manifest = _validate_manifest(_read_public_bytes(INDEX_URL, INDEX_MAX_BYTES))
    with _CACHE_LOCK:
        _MANIFEST_CACHE = (time.monotonic() + MANIFEST_TTL, manifest)
    return deepcopy(manifest)


def _validate_payload(raw, digest, expected_bytes, issuer_id):
    if len(raw) != expected_bytes or hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError("company-structure payload integrity mismatch")
    doc = _loads(raw, PAYLOAD_MAX_BYTES)
    companies, relations = (doc.get("companies"), doc.get("relations")) if isinstance(doc, dict) else (None, None)
    if (not isinstance(doc, dict) or doc.get("schema") != PAYLOAD_SCHEMA
            or not set(doc) <= {"schema", "observedAt", "companies", "relations", "coverage"}
            or not isinstance(companies, list) or len(companies) > MAX_NODES
            or not all(isinstance(item, dict) for item in companies)
            or not isinstance(relations, list) or len(relations) > MAX_RELATIONS
            or not all(isinstance(item, dict) for item in relations)
            or not any(item.get("id") == issuer_id for item in companies)
            or not isinstance(doc.get("coverage"), dict)
            or doc["coverage"].get("status") not in _SOURCE_STATUSES):
        raise ValueError("company-structure payload rejected")
    if _contains_url_field(doc["coverage"]):
        raise ValueError("company-structure coverage URL rejected")
    company_ids = set()
    for company in companies:
        company_id, name = company.get("id"), company.get("name")
        if (not isinstance(company_id, str) or not company_id or len(company_id) > 180
                or company_id in company_ids or not isinstance(name, str) or not name or len(name) > 300):
            raise ValueError("company-structure company rejected")
        if re.search(r"[\x00-\x1f\x7f]", company_id + name):
            raise ValueError("company-structure company text rejected")
        company_ids.add(company_id)
        if any(_is_url_field(key) for key in company):
            raise ValueError("company-structure company URL rejected")
    relation_ids = set()
    for relation in relations:
        relation_id = relation.get("id")
        if (not isinstance(relation_id, str) or not relation_id or len(relation_id) > 600
                or relation_id in relation_ids or relation.get("from") not in company_ids
                or relation.get("to") not in company_ids
                or relation.get("from") == relation.get("to")
                or relation.get("type") not in {"major-shareholder", "investment", "subsidiary"}
                or not isinstance(relation.get("label"), str) or not relation["label"] or len(relation["label"]) > 300
                or relation.get("status") not in {"source-dated", "official-undated", "undated-snapshot"}
                or ("asOf" not in relation)
                or ("ownershipPct" not in relation)
                or not isinstance(relation.get("evidence"), list)
                or (relation.get("asOf") is not None and not _valid_date(relation["asOf"]))
                or (relation.get("ownershipPct") is not None and
                    (isinstance(relation["ownershipPct"], bool) or
                     not isinstance(relation["ownershipPct"], (int, float)) or
                     not 0 <= relation["ownershipPct"] <= 100))):
            raise ValueError("company-structure relation rejected")
        if any(_is_url_field(key) for key in relation):
            raise ValueError("company-structure relation URL rejected")
        relation_ids.add(relation_id)
        evidence = relation.get("evidence")
        if not isinstance(evidence, list) or len(evidence) > 10:
            raise ValueError("company-structure evidence rejected")
        for item in evidence:
            if (not isinstance(item, dict) or not isinstance(item.get("title"), str)
                    or not item["title"] or len(item["title"]) > 300
                    or not _allowed_evidence_url(item.get("url"))
                    or (item.get("asOf") is not None and not _valid_date(item["asOf"]))):
                raise ValueError("company-structure evidence rejected")
        if "directOwnership" in relation and relation["directOwnership"] not in {"direct", "indirect", "unspecified"}:
            raise ValueError("company-structure ownership qualifier rejected")
        for optional_text in ("source_kind", "asOfMeaning"):
            if optional_text in relation and (not isinstance(relation[optional_text], str)
                                              or len(relation[optional_text]) > 500):
                raise ValueError("company-structure relation metadata rejected")
    return doc


def _is_url_field(key):
    normalized = re.sub(r"[^a-z]", "", str(key).lower())
    return normalized in {"url", "sourceurl", "sourceurls"}


def _contains_url_field(value):
    if isinstance(value, dict):
        return any(_is_url_field(key) or _contains_url_field(item) for key, item in value.items())
    if isinstance(value, list):
        return any(_contains_url_field(item) for item in value)
    return False


def _payload_matches_issuer(payload, issuer_id, expected_us_aliases=None):
    companies = payload.get("companies", [])
    if not any(isinstance(company, dict) and company.get("id") == issuer_id for company in companies):
        return False
    if issuer_id.startswith("US:"):
        coverage = payload.get("coverage")
        aliases = coverage.get("securityIds") if isinstance(coverage, dict) else None
        if (not isinstance(aliases, list) or not aliases
                or any(not isinstance(alias, str) or not alias.startswith("US:")
                       or not _US.fullmatch(alias[3:]) for alias in aliases)
                or len(set(aliases)) != len(aliases)
                or issuer_id not in aliases):
            return False
        company_ids = {company.get("id") for company in companies if isinstance(company, dict)}
        if not set(aliases) <= company_ids:
            return False
        if expected_us_aliases is not None and set(aliases) != set(expected_us_aliases):
            return False
    return True


def _valid_date(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value, re.ASCII) is not None


def _allowed_evidence_url(value):
    if (not isinstance(value, str) or len(value) > 2048
            or re.search(r"[\x00-\x20\x7f\\]", value)):
        return False
    try:
        parts = urlsplit(value)
        if (parts.scheme != "https" or not parts.hostname or parts.username or parts.password
                or parts.port not in (None, 443)):
            return False
    except ValueError:
        return False
    host = parts.hostname.lower()
    if host == "www.sec.gov":
        return bool(_SEC_EVIDENCE.fullmatch(parts.path) and not parts.query and not parts.fragment)
    if host == "dart.fss.or.kr":
        if parts.path != "/dsaf001/main.do" or parts.fragment:
            return False
        try:
            query = parse_qsl(parts.query, keep_blank_values=True, strict_parsing=True)
        except ValueError:
            return False
        return len(query) == 1 and query[0][0] == "rcpNo" and bool(_DART_RECEIPT.fullmatch(query[0][1]))
    if host == "kind.krx.co.kr":
        return not parts.fragment and not re.search(r"share|search|profile|quote", parts.path, re.I)
    if host in {"skhynix.com", "www.skhynix.com", "solidigm.com", "www.solidigm.com"}:
        return not parts.fragment
    return False


def _expected_us_aliases(manifest, digest):
    return {key for key, row in manifest["issuers"].items()
            if row["market"] == "US" and row.get("sha256") == digest}


def _get_payload(entry, issuer_id, manifest):
    digest, size = entry["sha256"], entry["bytes"]
    expected_us_aliases = _expected_us_aliases(manifest, digest) if issuer_id.startswith("US:") else None
    with _CACHE_LOCK:
        payload = _PAYLOAD_CACHE.get(digest)
        if payload is not None:
            cached_size, cached_document = payload
            if (cached_size != size
                    or cached_document["coverage"]["status"] != entry["status"]
                    or not _payload_matches_issuer(cached_document, issuer_id, expected_us_aliases)):
                raise ValueError("company-structure payload metadata mismatch")
            _PAYLOAD_CACHE.move_to_end(digest)
            return deepcopy(cached_document)
    url = PUBLIC_BASE + "company-structure/" + digest + ".json"
    raw = _read_public_bytes(url, PAYLOAD_MAX_BYTES)
    payload = _validate_payload(raw, digest, size, issuer_id)
    if (payload["coverage"]["status"] != entry["status"]
            or not _payload_matches_issuer(payload, issuer_id, expected_us_aliases)):
        raise ValueError("company-structure issuer aliases rejected")
    with _CACHE_LOCK:
        _PAYLOAD_CACHE[digest] = (size, payload)
        _PAYLOAD_CACHE.move_to_end(digest)
        while len(_PAYLOAD_CACHE) > PAYLOAD_CACHE_SIZE:
            _PAYLOAD_CACHE.popitem(last=False)
    return deepcopy(payload)


def _parse_path(path):
    try:
        parts = urlsplit(path)
        pairs = parse_qsl(parts.query, keep_blank_values=True, strict_parsing=True,
                          encoding="utf-8", errors="strict") if parts.query else []
    except (ValueError, UnicodeError):
        raise ValueError("invalid query") from None
    if (parts.scheme or parts.netloc or parts.fragment or parts.path != "/api/company_structure"
            or len(pairs) != 2 or {key for key, _ in pairs} != {"market", "ticker"}
            or len({key for key, _ in pairs}) != len(pairs)):
        raise ValueError("invalid query")
    query = dict(pairs)
    market, ticker = query["market"], query["ticker"]
    if market not in {"KR", "US"} or not _ticker_valid(market, ticker):
        raise ValueError("invalid query")
    return market, ticker


def _coverage(payload_coverage, issuer_id, manifest, entry):
    coverage = dict(payload_coverage)
    source_coverage = manifest["coverage"]
    universe = {}
    total = 0
    for market in ("KR", "US"):
        block = source_coverage.get(market)
        count = block.get("total") if isinstance(block, dict) else None
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError("company-structure universe denominator rejected")
        universe[market] = count
        total += count
    if total > MAX_ISSUERS or total != len(manifest["issuers"]):
        raise ValueError("company-structure universe denominator mismatch")
    coverage.update({"requestedIssuer": issuer_id,
                     "indexGeneratedAt": manifest["generatedAt"],
                     "universeDenominator": {"total": total, "byMarket": universe},
                     "sourceStatus": entry["status"],
                     "manifestCoverage": source_coverage})
    return coverage


def _dispatch(path):
    try:
        market, ticker = _parse_path(path)
    except ValueError:
        return 400, {"error": "invalid-request"}
    try:
        manifest = _get_manifest()
        issuer_id = f"{market}:{ticker}"
        entry = manifest["issuers"].get(issuer_id)
        if entry is None:
            return 404, {"error": "issuer-not-found"}
        has_payload = entry.get("sha256") is not None or entry.get("bytes") is not None
        if not has_payload and entry["status"] in {"not-attempted", "legacy-only"}:
            payload = {"schema": PAYLOAD_SCHEMA,
                       "companies": [{"id": issuer_id, "name": entry["name"],
                                      "ticker": ticker, "market": market}],
                       "relations": [], "coverage": {"status": entry["status"]}}
        else:
            if entry["status"] == "not-attempted" or entry.get("sha256") is None or entry.get("bytes") is None:
                raise ValueError("company-structure payload metadata missing")
            payload = _get_payload(entry, issuer_id, manifest)
        output = dict(payload)
        output["coverage"] = _coverage(payload["coverage"], issuer_id, manifest, entry)
        return 200, output
    except Exception:
        # Keep last-good caches for a later retry, but never present stale facts as current.
        return 503, {"error": "company-structure-unavailable"}


class handler(BaseHTTPRequestHandler):
    def _send(self, status, body):
        encoded = json.dumps(body, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "public, max-age=60" if status == 200 else "no-store")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self):
        status, body = _dispatch(self.path)
        self._send(status, body)

    def do_HEAD(self):
        self.send_response(405)
        self.send_header("Allow", "GET")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def do_POST(self):
        self.send_response(405)
        self.send_header("Allow", "GET")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
