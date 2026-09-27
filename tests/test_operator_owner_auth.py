"""Personal facts require owner roles; transport and facts core remain synthetic."""
import importlib.util
import io
import json
from pathlib import Path
import sys
import types
from unittest.mock import Mock

import pytest
import requests


OWNER = {"is_admin": True, "is_super_admin": True}
AUTH = {"authorization": "Bearer fixture-jwt"}


@pytest.fixture
def endpoint(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://auth.example.invalid")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "fixture-anon")
    monkeypatch.setenv("ADMIN_BYPASS_TOKEN", "fixture-server-token")
    monkeypatch.setattr(sys, "path", list(sys.path))
    path = Path(__file__).resolve().parents[1] / "vercel-api/api/operator_ask.py"
    spec = importlib.util.spec_from_file_location("operator_owner_endpoint", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module.requests.sessions.Session, "request", Mock(side_effect=AssertionError("network forbidden")))
    monkeypatch.setattr(module.requests, "get", Mock(side_effect=AssertionError("network forbidden")))
    return module


@pytest.fixture
def core_ask(monkeypatch):
    ask = Mock(return_value={"facts": {"ticker": "fixture", "_meta": {"status": "empty"}}})
    core = types.ModuleType("operator_core")
    core.operator_ask = types.SimpleNamespace(ask=ask)
    monkeypatch.setitem(sys.modules, "operator_core", core)
    return ask


def dispatch(endpoint, headers=None):
    handler = object.__new__(endpoint.handler)
    handler.path = "/api/operator_ask?ticker=fixture"
    handler.headers = headers if headers is not None else {"Authorization": "Bearer fixture-jwt"}
    handler.wfile = io.BytesIO()
    handler.send_response = Mock()
    handler.send_header = Mock()
    handler.end_headers = Mock()
    handler.do_GET()
    handler.send_response.assert_called_once()
    handler.send_header.assert_any_call("Cache-Control", "no-store")
    handler.send_header.assert_any_call("Access-Control-Allow-Origin", "*")
    handler.send_header.assert_any_call("Access-Control-Allow-Methods", "GET, OPTIONS")
    handler.send_header.assert_any_call("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Admin-Token")
    return handler.send_response.call_args.args[0], json.loads(handler.wfile.getvalue())


def response(body, status=200):
    return Mock(status_code=status, json=Mock(return_value=body))


def transport(endpoint, profile):
    endpoint.requests.get.side_effect = [response({"id": "fixture-owner"}), response(profile)]


def test_owner_allowed_and_profile_bound_to_verified_user(endpoint):
    transport(endpoint, [OWNER])
    assert endpoint._authorize(AUTH) == (True, "supabase_admin")
    user_call, profile_call = endpoint.requests.get.call_args_list
    assert user_call.args == ("https://auth.example.invalid/auth/v1/user",)
    assert profile_call.args == ("https://auth.example.invalid/rest/v1/profiles",)
    assert profile_call.kwargs["params"] == {
        "id": "eq.fixture-owner", "select": "is_admin,is_super_admin",
    }
    for call in (user_call, profile_call):
        assert call.kwargs["headers"] == {"apikey": "fixture-anon", "Authorization": "Bearer fixture-jwt"}
        assert call.kwargs["timeout"] == 5


@pytest.mark.parametrize("roles", [
    {"is_admin": True, "is_super_admin": False},
    {"is_admin": False, "is_super_admin": True},
    {"is_admin": False, "is_super_admin": False},
    {}, {"is_admin": True}, {"is_super_admin": True},
    {"is_admin": 1, "is_super_admin": True},
    {"is_admin": True, "is_super_admin": 1},
    {"is_admin": "true", "is_super_admin": True},
    {"is_admin": True, "is_super_admin": "true"},
    {"is_admin": None, "is_super_admin": True},
    {"is_admin": True, "is_super_admin": None},
])
def test_deputy_nonadmin_missing_or_malformed_roles_denied(endpoint, core_ask, roles):
    transport(endpoint, [roles])
    assert dispatch(endpoint) == (401, {"error": "unauthorized", "reason": "unauthorized"})
    core_ask.assert_not_called()


@pytest.mark.parametrize("profile,expected", [
    (None, 503), ({}, 503), (OWNER, 503), ([], 401),
    ([None], 503), (["owner"], 503), ([OWNER, OWNER], 503),
])
def test_malformed_or_missing_profile_fails_closed(endpoint, core_ask, profile, expected):
    transport(endpoint, profile)
    status, body = dispatch(endpoint)
    assert status == expected
    assert body["error"] == ("auth_service_unavailable" if expected == 503 else "unauthorized")
    core_ask.assert_not_called()


@pytest.mark.parametrize("user", [None, [], "owner", {}, {"id": None}, {"id": ""}, {"id": " "}, {"id": 1}])
def test_invalid_user_unavailable_before_profile_lookup(endpoint, core_ask, user):
    endpoint.requests.get.side_effect = [response(user)]
    assert dispatch(endpoint) == (503, {"error": "auth_service_unavailable"})
    assert endpoint.requests.get.call_count == 1
    core_ask.assert_not_called()


@pytest.mark.parametrize("stage", ["user", "profile"])
@pytest.mark.parametrize("status,expected", [
    (400, 401), (401, 401), (403, 401), (404, 401),
    (408, 503), (429, 503), (500, 503), (502, 503), (503, 503), (504, 503),
    (204, 503), (302, 503),
])
def test_auth_service_http_failure_classified(endpoint, core_ask, caplog, stage, status, expected):
    replies = [response({"detail": "sensitive-upstream-body"}, status)]
    if stage == "profile":
        replies.insert(0, response({"id": "fixture-owner"}))
    endpoint.requests.get.side_effect = replies
    code, body = dispatch(endpoint)
    assert code == expected
    if expected == 503:
        assert body == {"error": "auth_service_unavailable"}
        assert caplog.messages == [f"operator_ask auth service unavailable: stage={stage} status={status}"]
    else:
        assert body == {"error": "unauthorized", "reason": "unauthorized"}
    assert endpoint.requests.get.call_count == len(replies)
    endpoint.requests.sessions.Session.request.assert_not_called()
    core_ask.assert_not_called()


@pytest.mark.parametrize("stage", ["user", "profile"])
@pytest.mark.parametrize("failure", ["timeout", "connection", "request", "invalid_json"])
def test_auth_service_exception_unavailable(endpoint, core_ask, caplog, stage, failure):
    sensitive = "fixture-jwt fixture-owner fixture-anon private@example.invalid upstream-body"
    if failure == "invalid_json":
        failed = response(None)
        failed.json.side_effect = ValueError(sensitive)
    else:
        error = {"timeout": requests.Timeout, "connection": requests.ConnectionError,
                 "request": requests.RequestException}[failure]
        failed = error(sensitive)
    replies = [failed]
    if stage == "profile":
        replies.insert(0, response({"id": "fixture-owner"}))
    endpoint.requests.get.side_effect = replies
    assert dispatch(endpoint) == (503, {"error": "auth_service_unavailable"})
    assert endpoint.requests.get.call_count == len(replies)
    endpoint.requests.sessions.Session.request.assert_not_called()
    core_ask.assert_not_called()
    upstream_status = 200 if failure == "invalid_json" else None
    assert caplog.messages == [f"operator_ask auth service unavailable: stage={stage} status={upstream_status}"]
    for secret in sensitive.split():
        assert secret not in caplog.text


@pytest.mark.parametrize("setting", ["SUPABASE_URL", "SUPABASE_ANON_KEY"])
def test_missing_auth_configuration_denied(endpoint, core_ask, monkeypatch, setting):
    monkeypatch.setattr(endpoint, setting, "")
    assert dispatch(endpoint) == (401, {"error": "unauthorized", "reason": "unauthorized"})
    endpoint.requests.get.assert_not_called()
    core_ask.assert_not_called()


@pytest.mark.parametrize("stage", ["user", "profile"])
@pytest.mark.parametrize("failure", ["InvalidURL", "MissingSchema", "InvalidSchema", "InvalidHeader"])
def test_malformed_auth_configuration_or_header_stays_denied(endpoint, core_ask, caplog, stage, failure):
    error = getattr(requests.exceptions, failure)("sensitive-config-or-header")
    replies = ([response({"id": "fixture-owner"})] if stage == "profile" else []) + [error]
    endpoint.requests.get.side_effect = replies
    assert dispatch(endpoint) == (401, {"error": "unauthorized", "reason": "unauthorized"})
    assert endpoint.requests.get.call_count == len(replies)
    core_ask.assert_not_called()
    assert "sensitive-config-or-header" not in caplog.text


@pytest.mark.parametrize("headers", [{}, {"authorization": "Bearer "}, {"authorization": "Basic fixture"}])
def test_missing_or_unsupported_jwt_denied(endpoint, headers):
    assert endpoint._authorize(headers) == (False, "unauthorized")
    endpoint.requests.get.assert_not_called()


def test_server_bypass_preserved_without_profile_lookup(endpoint):
    assert endpoint._authorize({"x-admin-token": "fixture-server-token"}) == (True, "bypass_token")
    endpoint.requests.get.assert_not_called()


@pytest.mark.parametrize("configured,supplied", [("fixture-server-token", "wrong"), ("", "fixture-server-token"), ("", "")])
def test_wrong_or_unconfigured_bypass_denied(endpoint, monkeypatch, configured, supplied):
    monkeypatch.setattr(endpoint, "ADMIN_BYPASS_TOKEN", configured)
    assert endpoint._authorize({"x-admin-token": supplied}) == (False, "unauthorized")
    endpoint.requests.get.assert_not_called()


@pytest.mark.parametrize("roles,expected", [(OWNER, 200), ({"is_admin": True, "is_super_admin": False}, 401)])
def test_handler_enforces_real_owner_gate_before_core(endpoint, core_ask, roles, expected):
    transport(endpoint, [roles])
    status, body = dispatch(endpoint)
    assert status == expected
    if expected == 200:
        core_ask.assert_called_once_with("fixture", "", facts_only=True)
    else:
        core_ask.assert_not_called()
        assert body["error"] == "unauthorized"
