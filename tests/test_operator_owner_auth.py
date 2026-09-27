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
    monkeypatch.setattr(module.requests, "get", Mock(side_effect=AssertionError("network forbidden")))
    return module


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
def test_deputy_nonadmin_missing_or_malformed_roles_denied(endpoint, roles):
    transport(endpoint, [roles])
    assert endpoint._authorize(AUTH) == (False, "unauthorized")


@pytest.mark.parametrize("profile", [None, {}, OWNER, [], [None], ["owner"], [OWNER, OWNER]])
def test_malformed_profile_denied(endpoint, profile):
    transport(endpoint, profile)
    assert endpoint._authorize(AUTH) == (False, "unauthorized")


@pytest.mark.parametrize("user", [None, [], "owner", {}, {"id": None}, {"id": ""}, {"id": " "}, {"id": 1}])
def test_invalid_user_denied_before_profile_lookup(endpoint, user):
    endpoint.requests.get.side_effect = [response(user)]
    assert endpoint._authorize(AUTH) == (False, "unauthorized")
    assert endpoint.requests.get.call_count == 1


@pytest.mark.parametrize("stage", ["user", "profile"])
@pytest.mark.parametrize("status", [401, 403, 500])
def test_auth_service_http_failure_denied(endpoint, stage, status):
    replies = [response(None, status)]
    if stage == "profile":
        replies.insert(0, response({"id": "fixture-owner"}))
    endpoint.requests.get.side_effect = replies
    assert endpoint._authorize(AUTH) == (False, "unauthorized")
    assert endpoint.requests.get.call_count == len(replies)


@pytest.mark.parametrize("stage", ["user", "profile"])
@pytest.mark.parametrize("failure", ["timeout", "invalid_json"])
def test_auth_service_exception_denied(endpoint, stage, failure):
    if failure == "timeout":
        failed = requests.Timeout("synthetic timeout")
    else:
        failed = response(None)
        failed.json.side_effect = ValueError("synthetic invalid JSON")
    replies = [failed]
    if stage == "profile":
        replies.insert(0, response({"id": "fixture-owner"}))
    endpoint.requests.get.side_effect = replies
    assert endpoint._authorize(AUTH) == (False, "unauthorized")


@pytest.mark.parametrize("setting", ["SUPABASE_URL", "SUPABASE_ANON_KEY"])
def test_missing_auth_configuration_denied(endpoint, monkeypatch, setting):
    monkeypatch.setattr(endpoint, setting, "")
    assert endpoint._authorize(AUTH) == (False, "unauthorized")
    endpoint.requests.get.assert_not_called()


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
def test_handler_enforces_real_owner_gate_before_core(endpoint, monkeypatch, roles, expected):
    transport(endpoint, [roles])
    ask = Mock(return_value={"facts": {"ticker": "fixture", "_meta": {"status": "empty"}}})
    core = types.ModuleType("operator_core")
    core.operator_ask = types.SimpleNamespace(ask=ask)
    monkeypatch.setitem(sys.modules, "operator_core", core)
    handler = object.__new__(endpoint.handler)
    handler.path = "/api/operator_ask?ticker=fixture"
    handler.headers = {"Authorization": "Bearer fixture-jwt"}
    handler.wfile = io.BytesIO()
    handler.send_response = Mock()
    handler.send_header = Mock()
    handler.end_headers = Mock()
    handler.do_GET()
    handler.send_response.assert_called_once_with(expected)
    if expected == 200:
        ask.assert_called_once_with("fixture", "", facts_only=True)
    else:
        ask.assert_not_called()
        assert json.loads(handler.wfile.getvalue())["error"] == "unauthorized"
