"""Admin-only, read-only projection of locally reviewed analysis. No public fallback."""

from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
import logging
import os
import re
import sys
from urllib.parse import parse_qs, urlparse

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from operator_ask import _authorize, _headers_to_dict, _write

SCHEMA = "analysis-console-v1"
OBJECT_PATH = "verity-reports/_operator/analysis_reviews.json"
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
_logger = logging.getLogger(__name__)


def _instant(value):
    if not isinstance(value, str):
        raise ValueError("invalid timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timezone required")
    return parsed


def _text(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("invalid text")
    return value


def _strings(value):
    if not isinstance(value, list) or any(not isinstance(v, str) for v in value):
        raise ValueError("invalid text list")
    return value


def _count(value):
    if type(value) is not int or value < 0:
        raise ValueError("invalid count")
    return value


def _sources(value):
    if not isinstance(value, dict) or not isinstance(value.get("counts"), dict):
        raise ValueError("invalid source coverage")
    counts = {key: _count(value["counts"].get(key, 0)) for key in
              ("in_bundle", "not_in_bundle", "excluded_market")}
    total = _count(value.get("total"))
    entries = value.get("entries")
    if not isinstance(entries, list) or len(entries) != total or sum(counts.values()) != total:
        raise ValueError("invalid source denominator")
    rows = []
    for row in entries:
        if not isinstance(row, dict) or row.get("state") not in counts:
            raise ValueError("invalid source entry")
        rows.append({key: _text(row.get(key)) for key in ("source", "group", "state")})
    if any(sum(row["state"] == key for row in rows) != count for key, count in counts.items()):
        raise ValueError("source count mismatch")
    return dict(total=total, counts=counts, entries=rows, scope=_text(value.get("scope")),
                limitations=_strings(value.get("limitations")))


def project(document, ticker, *, now=None):
    """Validate the published summary; allowlist fields rather than forwarding raw data."""
    if (not isinstance(document, dict) or document.get("schema") != SCHEMA
            or not isinstance(document.get("items"), dict)):
        raise ValueError("invalid analysis projection")
    generated_at = document.get("generated_at")
    _instant(generated_at)
    base = dict(schema=SCHEMA, generated_at=generated_at, ticker=ticker,
                orders_authorized=False, monitoring_active=False)
    if ticker not in document["items"]:
        return dict(base, state="not_reviewed")
    row = document["items"][ticker]
    if not isinstance(row, dict) or row.get("ticker") != ticker:
        raise ValueError("ticker mismatch")
    packet_id = row.get("packet_id")
    if not isinstance(packet_id, str) or not re.fullmatch(r"[0-9a-f]{64}", packet_id):
        raise ValueError("invalid packet id")
    facts_at, prepared_at = row.get("facts_at"), row.get("prepared_at")
    if _instant(facts_at) > _instant(prepared_at):
        raise ValueError("invalid packet dates")
    out = dict(base, packet_id=packet_id, name=_text(row.get("name")), facts_at=facts_at,
               prepared_at=prepared_at, sources=_sources(row.get("sources")),
               section_total=_count(row.get("section_total")))
    review = row.get("review")
    if review is None:
        if row.get("state") != "awaiting_review":
            raise ValueError("review missing")
        return dict(out, state="awaiting_review", review=None)
    if not isinstance(review, dict) or row.get("state") not in ("reviewed", "review_expired"):
        raise ValueError("invalid review")
    if review.get("record_id") != "analysis:" + packet_id:
        raise ValueError("review packet mismatch")
    if review.get("verdict") not in ("관심", "보류", "회피") or review.get("confidence") not in ("low", "medium", "high"):
        raise ValueError("invalid verdict")
    reviewed_at, valid_until = _instant(review.get("reviewed_at")), _instant(review.get("valid_until"))
    if reviewed_at < _instant(prepared_at) or valid_until <= reviewed_at:
        raise ValueError("invalid review dates")
    selected = {key: _text(review.get(key)) for key in
                ("record_id", "verdict", "confidence", "reviewed_at", "valid_until",
                 "reasoning_brief", "counterevidence", "limitations")}
    for key in ("change_conditions", "unresolved"):
        selected[key] = _strings(review.get(key))
    coverage = review.get("coverage")
    if not isinstance(coverage, dict):
        raise ValueError("invalid review coverage")
    selected["coverage"] = {key: _count(coverage.get(key)) for key in
                            ("section_total", "reviewed", "not_used", "primary_supported_basis", "basis_total")}
    if (coverage["section_total"] != out["section_total"]
            or coverage["reviewed"] + coverage["not_used"] != coverage["section_total"]
            or type(coverage.get("unresolved")) is not bool
            or coverage.get("verification") != "reviewer_attestation_not_machine_proof"):
        raise ValueError("invalid review denominator")
    selected["coverage"].update(unresolved=coverage["unresolved"], verification=coverage["verification"])
    evidence = review.get("evidence")
    if not isinstance(evidence, list):
        raise ValueError("invalid evidence")
    selected["evidence"] = []
    for item in evidence:
        if not isinstance(item, dict):
            raise ValueError("invalid evidence item")
        clean = {key: _text(item.get(key)) for key in
                 ("section_id", "claim", "value", "source_as_of", "excerpt", "url", "source_kind", "status", "checked_at")}
        url = urlparse(clean["url"])
        if (url.scheme not in ("https", "http") or not url.hostname or url.username or url.password
                or clean["source_kind"] != "primary" or clean["status"] not in ("confirmed", "unresolved", "refuted")):
            raise ValueError("invalid evidence source")
        _instant(clean["checked_at"])
        selected["evidence"].append(clean)
    state = "review_expired" if valid_until <= (now or datetime.now(timezone.utc)) else "reviewed"
    selected["state"] = state
    return dict(out, state=state, review=selected)


def _download():
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise ValueError("storage not configured")
    response = requests.get(
        f"{SUPABASE_URL.rstrip('/')}/storage/v1/object/{OBJECT_PATH}",
        headers={"apikey": SUPABASE_SERVICE_ROLE_KEY,
                 "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}"},
        timeout=10, allow_redirects=False,
    )
    if response.status_code == 404:
        return None
    if response.status_code != 200 or len(response.content) > 4_000_000:
        raise ValueError("storage unavailable")
    document = response.json()
    if not isinstance(document, dict):
        raise ValueError("invalid storage document")
    return document


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        _write(self, 200, {})

    def do_GET(self):
        ok, reason = _authorize(_headers_to_dict(self))
        if not ok:
            return _write(self, 401, {"error": "unauthorized", "reason": reason})
        try:
            query = parse_qs(urlparse(self.path).query, keep_blank_values=True, max_num_fields=4)
            values = query.get("ticker", [])
            if len(values) != 1 or not re.fullmatch(r"[A-Za-z0-9.^-]{1,20}", values[0]):
                raise ValueError("invalid ticker")
            ticker = values[0].upper()
        except ValueError:
            return _write(self, 400, {"error": "invalid_ticker"})
        try:
            document = _download()
            body = (dict(schema=SCHEMA, ticker=ticker, state="not_reviewed", orders_authorized=False,
                         monitoring_active=False) if document is None else project(document, ticker))
        except (requests.RequestException, ValueError, TypeError, KeyError):
            _logger.warning("analysis review unavailable: storage or projection validation failed")
            return _write(self, 503, {"error": "analysis_review_unavailable"})
        return _write(self, 200, body)
