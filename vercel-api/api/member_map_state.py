"""Private member-owned map document API. Uses the caller's Supabase JWT only."""
from http.server import BaseHTTPRequestHandler
import json
import logging
import re

import requests

import api.supabase_client as sb
from api.member_map_state_validation import InvalidDocument, validate_document


_LOGGER = logging.getLogger(__name__)
_MAX_REQUEST_BYTES = 66 * 1024
_RPC_TIMEOUT_SECONDS = 8
_UUID = re.compile(r"^[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$")


def _json(handler, status, payload):
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Cache-Control", "private, no-store, max-age=0")
    handler.send_header("Vary", "Authorization, Origin")
    handler.send_header("X-Robots-Tag", "noindex, nofollow")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
    try:
        from api.cors_helper import resolve_origin
    except Exception:
        resolve_origin = lambda _origin: ""
    allowed_origin = resolve_origin(handler.headers.get("Origin") or "")
    if allowed_origin:
        handler.send_header("Access-Control-Allow-Origin", allowed_origin)
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _read_json(handler):
    try:
        length = int(handler.headers.get("Content-Length", "0"))
    except (TypeError, ValueError):
        return None
    if not 0 < length <= _MAX_REQUEST_BYTES:
        return None

    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate_json_key")
            result[key] = value
        return result

    try:
        raw = handler.rfile.read(length)
        # Bound nesting before parsing, independent of Python's recursion limit.
        # The request contract needs <=7 levels; brackets inside notes are text.
        depth, quoted, escaped = 0, False, False
        for byte in raw:
            if quoted:
                if escaped:
                    escaped = False
                elif byte == 92:
                    escaped = True
                elif byte == 34:
                    quoted = False
            elif byte == 34:
                quoted = True
            elif byte in (91, 123):
                depth += 1
                if depth > 12:
                    return None
            elif byte in (93, 125):
                depth -= 1
        data = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=unique_pairs,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError("invalid_number")),
        )
        return data if isinstance(data, dict) else None
    except (UnicodeError, ValueError, RecursionError):
        return None


def _identity(handler):
    authorization = (handler.headers.get("Authorization") or "").strip()
    if not authorization.startswith("Bearer "):
        return None, None
    token = authorization[7:].strip()
    if not token:
        return None, None
    try:
        user_id = sb.verify_jwt(token)
    except Exception:
        user_id = None
    if not user_id or not _UUID.fullmatch(str(user_id)):
        return None, None
    return str(user_id), token


def _validated_state(row, user_id):
    # Storage responses are not implicitly trusted, including successful RPCs.
    if not isinstance(row, dict) or set(row) != {
        "user_id", "revision", "document", "public_event_cursor_at"
    }:
        raise ValueError("invalid_storage_response")
    if row["user_id"] != user_id:
        raise ValueError("owner_mismatch")
    revision = row["revision"]
    if isinstance(revision, bool) or not isinstance(revision, int) or not 0 <= revision <= 2**53 - 1:
        raise ValueError("invalid_storage_revision")
    document = validate_document(row["document"])
    return {
        "revision": revision,
        "document": document,
        "public_event_cursor_at": row["public_event_cursor_at"],
    }


def _read_state(user_id, token):
    rows = sb.select(
        "member_map_state",
        {
            "user_id": "eq." + user_id,
            "select": "user_id,revision,document,public_event_cursor_at",
            "limit": "1",
        },
        user_jwt=token,
    )
    if not isinstance(rows, list):
        raise ValueError("invalid_storage_response")
    if not rows:
        return {
            "revision": 0,
            "document": {"layouts": []},
            "public_event_cursor_at": None,
        }
    if len(rows) != 1:
        raise ValueError("invalid_storage_response")
    return _validated_state(rows[0], user_id)


def _save_state(user_id, token, expected_revision, document):
    base_url = str(getattr(sb, "SUPABASE_URL", "")).rstrip("/")
    anon_key = str(getattr(sb, "SUPABASE_ANON_KEY", ""))
    if not base_url or not anon_key:
        raise RuntimeError("supabase_config_missing")
    response = requests.post(
        base_url + "/rest/v1/rpc/save_member_map_state_v1",
        json={"p_expected_revision": expected_revision, "p_document": document},
        headers={
            "apikey": anon_key,
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json",
        },
        timeout=_RPC_TIMEOUT_SECONDS,
    )
    try:
        result = response.json()
    except ValueError:
        result = {}
    if response.status_code == 409 or (
        isinstance(result, dict) and result.get("message") == "member_map_revision_conflict"
    ):
        raise RuntimeError("revision_conflict")
    if isinstance(result, dict) and result.get("message") == "invalid_member_map_document":
        raise RuntimeError("invalid_document")
    if not response.ok or not isinstance(result, dict):
        if response.status_code == 401:
            raise RuntimeError("unauthorized")
        raise RuntimeError("storage_unavailable")
    try:
        state = _validated_state(result, user_id)
        if state["revision"] != expected_revision + 1 or state["document"] != document:
            raise ValueError("save_response_mismatch")
    except (ValueError, TypeError, RecursionError):
        raise RuntimeError("storage_unavailable") from None
    return state


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        _json(self, 200, {})

    def do_GET(self):
        if not sb.is_configured():
            return _json(self, 503, {"error": "storage_unavailable"})
        user_id, token = _identity(self)
        if not user_id:
            return _json(self, 401, {"error": "authentication_required"})
        try:
            # This read intentionally does not write visit or cursor state.
            return _json(self, 200, _read_state(user_id, token))
        except Exception:
            _LOGGER.warning("member map state read failed [storage_unavailable]")
            return _json(self, 503, {"error": "storage_unavailable"})

    def do_POST(self):
        if not sb.is_configured():
            return _json(self, 503, {"error": "storage_unavailable"})
        user_id, token = _identity(self)
        if not user_id:
            return _json(self, 401, {"error": "authentication_required"})
        payload = _read_json(self)
        if payload is None or set(payload) != {"expected_revision", "document"}:
            return _json(self, 400, {"error": "invalid_request"})
        expected = payload["expected_revision"]
        if isinstance(expected, bool) or not isinstance(expected, int) or not 0 <= expected < 2**53 - 1:
            return _json(self, 400, {"error": "invalid_revision"})
        try:
            document = validate_document(payload["document"])
        except InvalidDocument:
            return _json(self, 400, {"error": "invalid_document"})
        try:
            result = _save_state(user_id, token, expected, document)
            return _json(self, 200, result)
        except RuntimeError as exc:
            if str(exc) == "revision_conflict":
                return _json(self, 409, {"error": "revision_conflict"})
            if str(exc) == "invalid_document":
                return _json(self, 400, {"error": "invalid_document"})
            if str(exc) == "unauthorized":
                return _json(self, 401, {"error": "authentication_required"})
            _LOGGER.warning("member map state save failed [storage_unavailable]")
            return _json(self, 503, {"error": "storage_unavailable"})
        except requests.RequestException:
            _LOGGER.warning("member map state save failed [network_error]")
            return _json(self, 503, {"error": "storage_unavailable"})

    def log_message(self, _format, *_args):
        # Avoid logging authorization data or private map content.
        return
