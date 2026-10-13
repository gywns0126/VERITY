"""Authenticated private response over fixed public portfolio artifacts.

POST accepts identifier-only positions.  Authentication proves the caller but
the identity and token are never passed to the public fetcher or analysis engine.
No member storage is read or written by this endpoint.
"""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler
import json
import logging
import re
import sys
import time

from api.member_map_state import _identity, _read_json
from api.portfolio_core.portfolio_engine import analyze_portfolio, validate_positions
from api.portfolio_core.portfolio_public_fetch import (
    PUBLIC_SOURCE_FILES,
    fetch_public_sources,
)


_LOGGER = logging.getLogger(__name__)
_MAX_RESPONSE_BYTES = 4 * 1024 * 1024
_ANALYSIS_ORIGINS = frozenset({"https://project-yw131.vercel.app"})
_PUBLIC_BUNDLE_REVISION = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)


def _stage_clock():
    try:
        return time.monotonic()
    except Exception:
        return None


def _log_stage_timing(stage, started, status):
    """Fixed metadata only; instrumentation failure cannot change a response."""
    try:
        if (stage not in ("public_sources", "prices", "changes", "projection")
                or status not in ("ok", "error") or started is None):
            return
        elapsed_ms = max(0, int((time.monotonic() - started) * 1000))
        print(f"member_map_stage stage={stage} status={status} elapsed_ms={elapsed_ms}",
              file=sys.stderr)
    except Exception:
        pass


def _resolve_origin(origin):
    origin = str(origin or "").strip()
    if origin in _ANALYSIS_ORIGINS:
        return origin
    try:
        from api.cors_helper import resolve_origin
    except Exception:
        return ""
    try:
        return resolve_origin(origin)
    except Exception:
        return ""


def _headers(allowed_origin="", *, method_allowed=True):
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Cache-Control": "private, no-store, max-age=0",
        "CDN-Cache-Control": "no-store",
        "Vercel-CDN-Cache-Control": "no-store",
        "Pragma": "no-cache",
        "Expires": "0",
        "Vary": "Authorization, Origin",
        "X-Robots-Tag": "noindex, nofollow",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "Authorization, Content-Type",
    }
    if not method_allowed:
        headers["Allow"] = "POST, OPTIONS"
    if allowed_origin:
        headers["Access-Control-Allow-Origin"] = allowed_origin
    return headers


def _origin_result(request, *, method_allowed=True):
    raw_origin = request.headers.get("Origin")
    if raw_origin is None or raw_origin == "":
        return None, _headers(method_allowed=method_allowed)
    origin = str(raw_origin).strip()
    allowed = _resolve_origin(origin)
    if not origin or allowed != origin:
        return (403, _headers(method_allowed=method_allowed),
                {"error": "origin_not_allowed"}), None
    return None, _headers(allowed, method_allowed=method_allowed)


def _valid_fetch_result(bundle):
    if type(bundle) is not dict or set(bundle) != {"documents", "coverage", "revision"}:
        return None
    documents = bundle.get("documents")
    coverage = bundle.get("coverage")
    revision = bundle.get("revision")
    if type(documents) is not dict or type(coverage) is not dict:
        return None
    if type(revision) is not str or not _PUBLIC_BUNDLE_REVISION.fullmatch(revision):
        return None
    if not set(documents).issubset(PUBLIC_SOURCE_FILES):
        return None
    if any(type(document) is not dict for document in documents.values()):
        return None
    if set(coverage) != {"expected", "available", "missing", "status"}:
        return None
    missing = coverage.get("missing")
    expected_missing = [name for name in PUBLIC_SOURCE_FILES if name not in documents]
    if (
        coverage.get("expected") != len(PUBLIC_SOURCE_FILES)
        or coverage.get("available") != len(documents)
        or missing != expected_missing
        or coverage.get("status") not in {"complete", "partial", "unavailable"}
    ):
        return None
    expected_status = (
        "complete" if len(documents) == len(PUBLIC_SOURCE_FILES)
        else "partial" if documents else "unavailable"
    )
    return (documents, revision) if coverage.get("status") == expected_status else None


def analyze_request(request):
    """Analyze one request without writing to the HTTP response.

    ``request`` needs only ``headers`` and ``rfile`` attributes, making the full
    authentication, parsing, validation, and fetch ordering locally testable.
    """
    origin_error, response_headers = _origin_result(request)
    if origin_error:
        return origin_error

    try:
        user_id, _token = _identity(request)
    except Exception:
        _LOGGER.warning("member map analysis authentication failed [authentication_unavailable]")
        return 503, response_headers, {"error": "authentication_unavailable"}
    if not user_id:
        return 401, response_headers, {"error": "authentication_required"}

    payload = _read_json(request)
    if payload is None or set(payload) != {"positions"}:
        return 400, response_headers, {"error": "invalid_request"}
    try:
        validated_positions = validate_positions(payload["positions"])
    except Exception:
        return 400, response_headers, {"error": "invalid_positions"}

    started, stage_status = _stage_clock(), "error"
    try:
        validated_sources = _valid_fetch_result(fetch_public_sources())
        if validated_sources is not None and validated_sources[0]:
            stage_status = "ok"
    except Exception:
        _LOGGER.warning("member map analysis public refresh failed [source_unavailable]")
        return 503, response_headers, {"error": "public_sources_unavailable"}
    finally:
        _log_stage_timing("public_sources", started, stage_status)
    if validated_sources is None or not validated_sources[0]:
        _LOGGER.warning("member map analysis public refresh empty [source_unavailable]")
        return 503, response_headers, {"error": "public_sources_unavailable"}
    documents, public_bundle_revision = validated_sources

    price_positions = [
        {"ticker": position["ticker"], "market": position["market"]}
        for position in validated_positions
    ]
    started, stage_status = _stage_clock(), "error"
    try:
        from api.portfolio_core.portfolio_price_fetch import fetch_public_prices

        price_documents = fetch_public_prices(price_positions)
        if type(price_documents) is not dict:
            raise ValueError("invalid public price result")
        stage_status = "ok"
    except Exception:
        _LOGGER.warning("member map analysis price refresh failed [price_source_unavailable]")
        price_documents = {}
    finally:
        _log_stage_timing("prices", started, stage_status)

    # Identifiers only, after authentication and request validation. Optional
    # change-center failure cannot remove the existing filing/price result.
    started, stage_status = _stage_clock(), "error"
    try:
        from api.portfolio_core.portfolio_change_facts import fetch_public_changes
        change_projection = fetch_public_changes(price_positions)
        stage_status = "ok"
    except Exception:
        _LOGGER.warning("member map change refresh failed [change_source_unavailable]")
        change_projection = None
    finally:
        _log_stage_timing("changes", started, stage_status)

    started, stage_status = _stage_clock(), "error"
    try:
        result = analyze_portfolio(
            payload["positions"],
            documents,
            public_bundle_revision=public_bundle_revision,
            price_documents=price_documents,
            change_projection=change_projection,
        )
        if type(result) is not dict or result.get("schema") != "alphaconsole-portfolio-v1":
            raise ValueError("invalid analysis result")
        stage_status = "ok"
    except Exception:
        _LOGGER.warning("member map analysis failed [analysis_unavailable]")
        return 503, response_headers, {"error": "analysis_unavailable"}
    finally:
        _log_stage_timing("projection", started, stage_status)
    return 200, response_headers, result


def _encode_result(result):
    status, headers, payload = result
    try:
        body = json.dumps(
            payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    except Exception:
        _LOGGER.warning("member map analysis response rejected [serialization_unavailable]")
        status = 503
        body = b'{"error":"analysis_unavailable"}'
    if len(body) > _MAX_RESPONSE_BYTES:
        _LOGGER.warning("member map analysis response rejected [response_too_large]")
        status = 503
        body = b'{"error":"analysis_unavailable"}'
    return status, headers, body


def _send(handler, result):
    status, headers, body = _encode_result(result)
    handler.send_response(status)
    for key, value in headers.items():
        handler.send_header(key, value)
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    try:
        handler.wfile.write(body)
    except (BrokenPipeError, ConnectionResetError):
        # The private payload is not retried or logged after a client disconnect.
        return


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        origin_error, response_headers = _origin_result(self)
        return _send(self, origin_error or (200, response_headers, {}))

    def do_GET(self):
        origin_error, response_headers = _origin_result(self, method_allowed=False)
        return _send(
            self,
            origin_error or (405, response_headers, {"error": "method_not_allowed"}),
        )

    def do_POST(self):
        return _send(self, analyze_request(self))

    def log_message(self, _format, *_args):
        # Never log authorization headers or the private selection payload.
        return
