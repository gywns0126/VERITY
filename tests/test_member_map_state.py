"""Local-only contract tests for the private member map API and validator."""
import importlib.util
import io
import json
import logging
import re
import sys
import types
from pathlib import Path
from unittest.mock import Mock

import pytest


ROOT = Path(__file__).resolve().parents[1]
API_DIR = ROOT / "vercel-api" / "api"
USER_A = "11111111-1111-4111-8111-111111111111"
USER_B = "22222222-2222-4222-8222-222222222222"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def modules(monkeypatch):
    package = types.ModuleType("api")
    package.__path__ = [str(API_DIR)]
    sb = types.ModuleType("api.supabase_client")
    sb.SUPABASE_URL = "https://supabase.invalid"
    sb.SUPABASE_ANON_KEY = "anon-test-key"
    sb.is_configured = lambda: True
    sb.verify_jwt = lambda token: {"jwt-a": USER_A, "jwt-b": USER_B}.get(token)

    def select(_table, filters, user_jwt=None):
        user_id = filters["user_id"][3:]
        return [{"user_id": user_id, "revision": 4,
                 "document": {"layouts": []}, "public_event_cursor_at": None}]

    sb.select = Mock(side_effect=select)
    monkeypatch.setitem(sys.modules, "api", package)
    monkeypatch.setitem(sys.modules, "api.supabase_client", sb)
    monkeypatch.delitem(sys.modules, "api.member_map_state_validation", raising=False)
    validation = _load("api.member_map_state_validation", API_DIR / "member_map_state_validation.py")
    monkeypatch.setitem(sys.modules, "api.member_map_state_validation", validation)
    monkeypatch.delitem(sys.modules, "api.member_map_state", raising=False)
    api = _load("api.member_map_state", API_DIR / "member_map_state.py")
    monkeypatch.setitem(sys.modules, "api.member_map_state", api)
    return api, validation, sb


def _document():
    return {"layouts": [{
        "map_key": "nest",
        "positions": [{"node_id": "node-a", "x": 0.25, "y": -0.5}],
        "notes": [{"note_id": "note-a", "anchor": None, "x": 0, "y": 1,
                   "text": "plain note", "done": False}],
        "marks": {"node-a": {"read_revision": 8, "important": True,
                               "disposition": "later"}},
    }]}


def _invoke(api, method, token=None, payload=None, origin="https://app.example"):
    h = object.__new__(api.handler)
    h.headers = {"Origin": origin}
    if token:
        h.headers["Authorization"] = "Bearer " + token
    body = b"" if payload is None else json.dumps(payload).encode()
    h.headers["Content-Length"] = str(len(body))
    h.rfile = io.BytesIO(body)
    h.wfile = io.BytesIO()
    h._headers_sent = []
    h.send_response = lambda status: setattr(h, "status", status)
    h.send_header = lambda key, value: h._headers_sent.append((key, value))
    h.end_headers = lambda: None
    getattr(h, method)()
    response = json.loads(h.wfile.getvalue() or b"{}")
    return h, response


class _RpcResponse:
    def __init__(self, status, data):
        self.status_code = status
        self.ok = 200 <= status < 300
        self._data = data

    def json(self):
        return self._data


def test_get_is_member_filtered_no_mutation_and_private_cache(modules, monkeypatch):
    api, _, sb = modules
    rpc = Mock()
    monkeypatch.setattr(api.requests, "post", rpc)
    for token, user_id in (("jwt-a", USER_A), ("jwt-b", USER_B)):
        h, body = _invoke(api, "do_GET", token=token)
        assert body["revision"] == 4
        assert sb.select.call_args.kwargs["user_jwt"] == token
        assert sb.select.call_args.args[1]["user_id"] == "eq." + user_id
        headers = dict(h._headers_sent)
        assert headers["Cache-Control"].startswith("private, no-store")
    rpc.assert_not_called()
    assert sb.select.call_count == 2


def test_save_initial_revision_uses_member_jwt_and_anon_key_only(modules, monkeypatch):
    api, _, _ = modules
    response = _RpcResponse(200, {"user_id": USER_A, "revision": 1, "document": _document(),
                                  "public_event_cursor_at": None})
    rpc = Mock(return_value=response)
    monkeypatch.setattr(api.requests, "post", rpc)
    _, body = _invoke(api, "do_POST", "jwt-a", {
        "expected_revision": 0, "document": _document()})
    assert body["revision"] == 1
    assert set(body) == {"revision", "document", "public_event_cursor_at"}
    call = rpc.call_args
    assert call.kwargs["json"]["p_expected_revision"] == 0
    assert call.kwargs["headers"]["Authorization"] == "Bearer jwt-a"
    assert call.kwargs["headers"]["apikey"] == "anon-test-key"


@pytest.mark.parametrize("payload", [
    {"expected_revision": 0, "user_id": USER_B, "document": {"layouts": []}},
    {"expected_revision": 0, "document": {"layouts": [], "owner_id": USER_B}},
    {"expected_revision": 0, "document": {"layouts": [{"map_key": "nest",
       "positions": [], "notes": [], "marks": {}, "extra": True}]}},
])
def test_malicious_owner_or_unknown_fields_rejected_before_rpc(modules, monkeypatch, payload):
    api, _, _ = modules
    rpc = Mock()
    monkeypatch.setattr(api.requests, "post", rpc)
    _, body = _invoke(api, "do_POST", "jwt-a", payload)
    assert body["error"] in ("invalid_request", "invalid_document")
    rpc.assert_not_called()


def test_stale_revision_maps_to_409(modules, monkeypatch):
    api, _, _ = modules
    monkeypatch.setattr(api.requests, "post", Mock(return_value=_RpcResponse(
        409, {"code": "PT409", "message": "member_map_revision_conflict"})))
    h, body = _invoke(api, "do_POST", "jwt-a", {
        "expected_revision": 3, "document": _document()})
    assert h.status == 409
    assert body == {"error": "revision_conflict"}


def test_marks_contract_bounds_revision_and_rejects_old_boolean_shape(modules):
    _, validation, _ = modules
    document = _document()
    validation.validate_document(document)
    for field, value in (("read_revision", True), ("read_revision", 0),
                         ("read_revision", 2**53 - 1),
                         ("disposition", []), ("disposition", {}),
                         ("important", "yes"), ("disposition", "done")):
        bad = _document()
        bad["layouts"][0]["marks"]["node-a"][field] = value
        with pytest.raises(validation.InvalidDocument):
            validation.validate_document(bad)
    bad = _document()
    bad["layouts"][0]["marks"]["node-a"] = True
    with pytest.raises(validation.InvalidDocument):
        validation.validate_document(bad)


def test_payload_size_and_database_validation_errors_are_400(modules, monkeypatch):
    api, _, _ = modules
    oversized = _document()
    oversized["layouts"][0]["notes"] = [
        {"note_id": f"n{i}", "anchor": None, "x": 0, "y": 0,
         "text": "x" * 2000, "done": False} for i in range(40)]
    _, body = _invoke(api, "do_POST", "jwt-a", {
        "expected_revision": 0, "document": oversized})
    assert body["error"] == "invalid_request"  # bounded request before parse

    monkeypatch.setattr(api.requests, "post", Mock(return_value=_RpcResponse(
        400, {"message": "invalid_member_map_document", "code": "22023"})))
    h, body = _invoke(api, "do_POST", "jwt-a", {
        "expected_revision": 0, "document": _document()})
    assert h.status == 400
    assert body == {"error": "invalid_document"}


def test_unauthenticated_requests_rejected(modules, monkeypatch):
    api, _, _ = modules
    rpc = Mock()
    monkeypatch.setattr(api.requests, "post", rpc)
    get_h, get_body = _invoke(api, "do_GET")
    post_h, post_body = _invoke(api, "do_POST", payload={
        "expected_revision": 0, "document": _document()})
    assert (get_h.status, get_body["error"]) == (401, "authentication_required")
    assert (post_h.status, post_body["error"]) == (401, "authentication_required")
    rpc.assert_not_called()


def test_cors_allowlist_resolution_and_fail_closed(modules, monkeypatch):
    api, _, _ = modules
    helper = types.ModuleType("api.cors_helper")
    helper.resolve_origin = lambda origin: origin if origin == "https://app.example" else ""
    monkeypatch.setitem(sys.modules, "api.cors_helper", helper)
    allowed, _ = _invoke(api, "do_GET", "jwt-a", origin="https://app.example")
    denied, _ = _invoke(api, "do_GET", "jwt-a", origin="https://evil.example")
    assert ("Access-Control-Allow-Origin", "https://app.example") in allowed._headers_sent
    assert not any(key == "Access-Control-Allow-Origin" for key, _ in denied._headers_sent)


def test_failure_logs_are_fixed_codes_without_exception_text(modules, monkeypatch, caplog):
    api, _, sb = modules
    sb.select.side_effect = RuntimeError("https://secret.invalid/path?token=private")
    with caplog.at_level(logging.WARNING):
        _invoke(api, "do_GET", "jwt-a")
    assert "secret.invalid" not in caplog.text
    assert "token=private" not in caplog.text
    assert "[storage_unavailable]" in caplog.text


def test_migration_contains_rls_rpc_lock_and_validation_guards():
    sql = (ROOT / "supabase/migrations/2026092701_member_map_state.sql").read_text()
    assert "jsonb_object_length" not in sql
    assert "FROM jsonb_object_keys(v_layout->'marks')" in sql
    assert "jsonb_typeof(v_anchor->'kind') <> 'string'" in sql
    assert "read_revision" in sql and "'inbox','later','irrelevant'" in sql
    assert "USING (auth.uid() = user_id)" in sql
    assert "SET search_path = ''" in sql
    assert "FROM PUBLIC, anon, service_role" in sql
    assert "pg_advisory_xact_lock" in sql
    assert "v_current_revision IS DISTINCT FROM p_expected_revision" in sql
    assert "public_event_cursor_at" in sql


@pytest.mark.parametrize("value", [True, None, "12", float("nan"),
                                   float("inf"), 10**400, -1000001])
def test_invalid_coordinates_are_validation_errors(modules, value):
    _, validation, _ = modules
    document = _document()
    document["layouts"][0]["positions"][0]["x"] = value
    with pytest.raises(validation.InvalidDocument):
        validation.validate_document(document)


@pytest.mark.parametrize("token", ["expired-token", "invalid-token"])
def test_bad_tokens_never_read_or_write_storage(modules, monkeypatch, token):
    api, _, sb = modules
    rpc = Mock()
    monkeypatch.setattr(api.requests, "post", rpc)
    for method in ("do_GET", "do_POST"):
        h, _ = _invoke(api, method, token, {
            "expected_revision": 0, "document": _document()})
        assert h.status == 401
    sb.select.assert_not_called()
    rpc.assert_not_called()


@pytest.mark.parametrize("rows", [None, {}, [
    {"user_id": USER_B, "revision": 1, "document": {"layouts": []}}
]])
def test_invalid_or_other_owner_response_is_not_an_empty_portfolio(modules, rows):
    api, _, sb = modules
    sb.select.side_effect = None
    sb.select.return_value = rows
    h, response = _invoke(api, "do_GET", "jwt-a")
    assert h.status == 503
    assert response == {"error": "storage_unavailable"}


@pytest.mark.parametrize("raw", [
    b'{"expected_revision":0,"expected_revision":1,"document":{"layouts":[]}}',
    b'{"document":' + b'[' * 1500 + b']' * 1500 + b'}',
    b'{"document":{"layouts":NaN}}',
])
def test_ambiguous_or_deep_json_is_rejected_without_exception(modules, raw):
    api, _, _ = modules
    h = types.SimpleNamespace(headers={"Content-Length": str(len(raw))},
                              rfile=io.BytesIO(raw))
    assert api._read_json(h) is None


@pytest.mark.parametrize("depth", [13, 64])
def test_json_depth_limit_does_not_depend_on_interpreter_recursion(modules, depth):
    api, _, _ = modules
    raw = b'{"document":' + b'[' * depth + b']' * depth + b'}'
    h = types.SimpleNamespace(headers={"Content-Length": str(len(raw))}, rfile=io.BytesIO(raw))
    assert api._read_json(h) is None


def test_note_brackets_quotes_and_escapes_do_not_count_as_json_depth(modules):
    api, _, _ = modules
    doc = _document()
    doc["layouts"][0]["notes"][0]["text"] = '[]{}' * 80 + chr(34) + chr(92) + "한글"
    payload = {"expected_revision": 0, "document": doc}
    raw = json.dumps(payload, ensure_ascii=False).encode()
    h = types.SimpleNamespace(headers={"Content-Length": str(len(raw))}, rfile=io.BytesIO(raw))
    assert api._read_json(h) == payload


def test_duplicate_layouts_and_invalid_note_anchor_rejected(modules):
    _, validation, _ = modules
    duplicate = _document()
    duplicate["layouts"].append(_document()["layouts"][0])
    with pytest.raises(validation.InvalidDocument):
        validation.validate_document(duplicate)
    too_many = {"layouts": []}
    for index in range(4):
        layout = _document()["layouts"][0]
        layout["map_key"] = f"nest-{index}"
        too_many["layouts"].append(layout)
    with pytest.raises(validation.InvalidDocument):
        validation.validate_document(too_many)
    bad_anchor = _document()
    bad_anchor["layouts"][0]["notes"][0]["anchor"] = {"kind": None, "id": "a"}
    with pytest.raises(validation.InvalidDocument):
        validation.validate_document(bad_anchor)


def test_note_cannot_contain_postgres_null_character(modules):
    _, validation, _ = modules
    bad = _document()
    bad["layouts"][0]["notes"][0]["text"] = "note\x00tail"
    with pytest.raises(validation.InvalidDocument):
        validation.validate_document(bad)


@pytest.mark.parametrize("revision", [True, -1, "1", 1.5, None, 2**53])
def test_invalid_stored_revisions_fail_closed(modules, revision):
    api, _, sb = modules
    sb.select.side_effect = None
    sb.select.return_value = [{"user_id": USER_A, "revision": revision,
                               "document": _document(), "public_event_cursor_at": None}]
    h, body = _invoke(api, "do_GET", "jwt-a")
    assert (h.status, body) == (503, {"error": "storage_unavailable"})


@pytest.mark.parametrize("patch", [
    {"user_id": USER_B}, {"user_id": None}, {"revision": True},
    {"revision": 0}, {"revision": 2}, {"document": {"layouts": []}},
    {"document": {"layouts": None}}, {"extra": "private backend field"},
])
def test_success_status_cannot_mask_wrong_save_result(modules, monkeypatch, patch):
    api, _, _ = modules
    result = {"user_id": USER_A, "revision": 1, "document": _document(),
              "public_event_cursor_at": None, **patch}
    monkeypatch.setattr(api.requests, "post", Mock(return_value=_RpcResponse(200, result)))
    h, body = _invoke(api, "do_POST", "jwt-a", {
        "expected_revision": 0, "document": _document()})
    assert (h.status, body) == (503, {"error": "storage_unavailable"})
    assert "no-store" in dict(h._headers_sent)["Cache-Control"]


@pytest.mark.parametrize("result", [{}, None, [], {"revision": 1}])
def test_malformed_storage_shapes_fail_closed_for_get_and_save(modules, monkeypatch, result):
    api, _, sb = modules
    sb.select.side_effect = None
    sb.select.return_value = [result]
    get_h, get_body = _invoke(api, "do_GET", "jwt-a")
    monkeypatch.setattr(api.requests, "post", Mock(return_value=_RpcResponse(200, result)))
    save_h, save_body = _invoke(api, "do_POST", "jwt-a", {
        "expected_revision": 0, "document": _document()})
    assert get_h.status == save_h.status == 503
    assert get_body == save_body == {"error": "storage_unavailable"}


def test_empty_get_and_duplicate_rows_are_distinct(modules):
    api, _, sb = modules
    sb.select.side_effect = None
    sb.select.return_value = []
    h, body = _invoke(api, "do_GET", "jwt-a")
    assert h.status == 200 and body["revision"] == 0
    row = {"user_id": USER_A, "revision": 1, "document": _document(),
           "public_event_cursor_at": None}
    sb.select.return_value = [row, row]
    h, body = _invoke(api, "do_GET", "jwt-a")
    assert (h.status, body) == (503, {"error": "storage_unavailable"})


def test_non_json_success_is_not_reported_as_saved(modules, monkeypatch):
    api, _, _ = modules
    response = _RpcResponse(200, None)
    response.json = Mock(side_effect=ValueError("private upstream response"))
    monkeypatch.setattr(api.requests, "post", Mock(return_value=response))
    h, body = _invoke(api, "do_POST", "jwt-a", {
        "expected_revision": 0, "document": _document()})
    assert (h.status, body) == (503, {"error": "storage_unavailable"})


def test_invalid_verified_identity_never_reaches_storage(modules, monkeypatch):
    api, _, sb = modules
    sb.verify_jwt = lambda _token: "-" * 36
    rpc = Mock()
    monkeypatch.setattr(api.requests, "post", rpc)
    h, body = _invoke(api, "do_POST", "jwt-a", {
        "expected_revision": 0, "document": _document()})
    assert (h.status, body) == (401, {"error": "authentication_required"})
    rpc.assert_not_called()
    sb.select.assert_not_called()


@pytest.mark.parametrize("delta,accepted", [(-1, True), (0, True), (1, False)])
def test_jsonb_size_boundary_before_rpc(modules, monkeypatch, delta, accepted):
    api, validation, _ = modules
    document = {"layouts": [{"map_key": "nest", "positions": [], "marks": {},
        "notes": [{"note_id": f"n{i}", "anchor": None, "x": 0, "y": 0,
                   "text": "x" * 1905, "done": False} for i in range(33)]}]}
    # Ordinary string/integer JSON differs from jsonb::text only in key order.
    size = len(json.dumps(document, ensure_ascii=False).encode())
    document["layouts"][0]["notes"][-1]["text"] = "x" * (1905 + 65536 + delta - size)
    assert len(json.dumps(document, ensure_ascii=False).encode()) == 65536 + delta
    assert len(json.dumps(document, separators=(",", ":")).encode()) < 65536
    rpc = Mock(return_value=_RpcResponse(200, {"user_id": USER_A, "revision": 1,
                     "document": document, "public_event_cursor_at": None}))
    monkeypatch.setattr(api.requests, "post", rpc)
    h, body = _invoke(api, "do_POST", "jwt-a", {"expected_revision": 0, "document": document})
    assert h.status == (200 if accepted else 400)
    assert rpc.call_count == int(accepted)
    if not accepted:
        assert body == {"error": "invalid_document"}


def test_jsonb_exponents_and_unicode_size(modules):
    _, validation, _ = modules
    document = _document()
    document["layouts"][0]["positions"][0].update(x=1e-7, y=-0.0)
    document["layouts"][0]["notes"][0]["text"] = '한🙂\n"\\'
    expected = json.dumps(document, ensure_ascii=False).replace('1e-07', '0.0000001').replace('-0.0', '0.0')
    assert validation.document_storage_bytes(document) == len(expected.encode())


def test_deployment_does_not_override_member_cors_or_enable_public_cache():
    config = json.loads((ROOT / "vercel-api/vercel.json").read_text())
    for path in ("/api/member_map_state", "/api/member_map_state/", "/api/member_map_state.py"):
        for rule in config.get("headers", []):
            if re.fullmatch(rule["source"], path):
                headers = {h["key"].lower(): h["value"].lower() for h in rule["headers"]}
                assert headers.get("access-control-allow-origin") != "*"
                for key in ("cache-control", "cdn-cache-control", "vercel-cdn-cache-control"):
                    if key in headers:
                        assert "no-store" in headers[key]
