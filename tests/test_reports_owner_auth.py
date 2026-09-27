"""Exercise real report handlers with synthetic authentication/storage transport."""
import importlib.util
import io
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
import requests


OWNER = {"is_admin": True, "is_super_admin": True}
DEPUTY = {"is_admin": True, "is_super_admin": False}
PUBLIC_USER = {"is_admin": False, "is_super_admin": False}
AUTH = {"Authorization": "Bearer fixture-jwt"}
ROUTES = ["", "&date=2026-09-25", "&action=list"]


@pytest.fixture
def endpoint(monkeypatch):
    for name, value in {
        "SUPABASE_URL": "https://reports.example.invalid",
        "SUPABASE_ANON_KEY": "fixture-anon",
        "SUPABASE_SERVICE_ROLE_KEY": "fixture-service",
        "API_ALLOWED_ORIGINS": "https://site.example.invalid",
    }.items():
        monkeypatch.setenv(name, value)
    path = Path(__file__).resolve().parents[1] / "vercel-api/api/reports.py"
    spec = importlib.util.spec_from_file_location("reports_owner_endpoint", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module.requests, "get", Mock(side_effect=AssertionError("network forbidden")))
    monkeypatch.setattr(module.requests, "post", Mock(side_effect=AssertionError("network forbidden")))
    return module


def response(body, status=200):
    return Mock(status_code=status, text=json.dumps(body), json=Mock(return_value=body))


def request(endpoint, kind="admin", suffix="", headers=None, period="daily"):
    handler = object.__new__(endpoint.handler)
    handler.path = f"/api/reports?period={period}&type={kind}{suffix}"
    handler.headers = AUTH if headers is None else headers
    handler.wfile = io.BytesIO()
    handler.send_response = Mock()
    handler.send_header = Mock()
    handler.end_headers = Mock()
    handler.do_GET()
    return handler.send_response.call_args.args[0], json.loads(handler.wfile.getvalue())


def auth_transport(endpoint, roles):
    endpoint.requests.get.side_effect = [response({"id": "fixture-user"}), response([roles])]


def storage_transport(endpoint, suffix):
    body = [{"name": "2026-09-25.pdf"}] if suffix == "&action=list" else {"signedURL": "/object/sign/fixture"}
    endpoint.requests.post.side_effect = [response(body)]


@pytest.mark.parametrize("suffix", ROUTES)
@pytest.mark.parametrize("period", ["daily", "weekly", "monthly", "quarterly", "semi", "annual"])
def test_owner_can_sign_and_list_private_reports(endpoint, suffix, period):
    auth_transport(endpoint, OWNER)
    storage_transport(endpoint, suffix)
    status, body = request(endpoint, suffix=suffix, period=period)
    assert status == 200
    assert body["type"] == "admin" and body["period"] == period
    profile = endpoint.requests.get.call_args_list[1]
    assert profile.kwargs["params"] == {"id": "eq.fixture-user", "select": "is_admin,is_super_admin"}
    assert profile.kwargs["headers"]["Authorization"] == "Bearer fixture-jwt"
    signed = endpoint.requests.post.call_args
    if suffix == "&action=list":
        assert signed.kwargs["json"]["prefix"] == f"archive/{period}/admin/"
        assert body["items"] == [{"date": "2026-09-25", "filename": "2026-09-25.pdf"}]
        assert "url" not in body
    else:
        expected_path = f"archive/{period}/admin/2026-09-25.pdf" if suffix else f"verity_{period}_admin.pdf"
        assert signed.args[0].endswith(f"/object/sign/verity-reports/{expected_path}")
        assert signed.kwargs["json"] == {"expiresIn": 1800}
        assert body["filename"] == expected_path and body["expires_in"] == 1800


@pytest.mark.parametrize("roles", [DEPUTY, PUBLIC_USER])
@pytest.mark.parametrize("suffix", ROUTES)
def test_deputy_and_nonadmin_cannot_sign_or_list_private_reports(endpoint, roles, suffix):
    auth_transport(endpoint, roles)
    status, body = request(endpoint, suffix=suffix)
    assert status == 403 and body == {"error": "Owner only"}
    endpoint.requests.post.assert_not_called()


@pytest.mark.parametrize("roles", [OWNER, DEPUTY, PUBLIC_USER])
@pytest.mark.parametrize("suffix", ROUTES)
def test_public_reports_remain_available_without_admin_lookup(endpoint, roles, suffix):
    auth_transport(endpoint, roles)
    storage_transport(endpoint, suffix)
    status, body = request(endpoint, kind="public", suffix=suffix)
    assert status == 200 and body["type"] == "public"
    assert endpoint.requests.get.call_count == 1
    signed = endpoint.requests.post.call_args
    if suffix == "&action=list":
        assert signed.kwargs["json"]["prefix"] == "archive/daily/public/"
    else:
        expected_path = "archive/daily/public/2026-09-25.pdf" if suffix else "verity_daily_public.pdf"
        assert signed.args[0].endswith(f"/object/sign/verity-reports/{expected_path}")
        assert body["filename"] == expected_path and body["expires_in"] == 21600


@pytest.mark.parametrize("roles", [
    {}, {"is_admin": True}, {"is_super_admin": True},
    {"is_admin": False, "is_super_admin": True},
    {"is_admin": 1, "is_super_admin": True},
    {"is_admin": True, "is_super_admin": 1},
    {"is_admin": "true", "is_super_admin": True},
    {"is_admin": True, "is_super_admin": "true"},
    {"is_admin": None, "is_super_admin": True},
    {"is_admin": True, "is_super_admin": None},
])
def test_missing_or_malformed_roles_never_reach_storage(endpoint, roles):
    auth_transport(endpoint, roles)
    assert request(endpoint)[0] == 403
    endpoint.requests.post.assert_not_called()


@pytest.mark.parametrize("profile", [None, {}, OWNER, [], [None], ["owner"], [OWNER, OWNER]])
def test_malformed_profile_never_reaches_storage(endpoint, profile):
    endpoint.requests.get.side_effect = [response({"id": "fixture-user"}), response(profile)]
    assert request(endpoint)[0] == 403
    endpoint.requests.post.assert_not_called()


@pytest.mark.parametrize("stage,expected", [("user", 401), ("profile", 403)])
@pytest.mark.parametrize("failure", ["http401", "http403", "http500", "timeout", "invalid_json"])
def test_auth_service_failure_never_reaches_storage(endpoint, stage, expected, failure):
    if failure == "timeout":
        failed = requests.Timeout("synthetic timeout")
    elif failure == "invalid_json":
        failed = response(None)
        failed.json.side_effect = ValueError("synthetic invalid JSON")
    else:
        failed = response(None, int(failure[4:]))
    replies = [failed] if stage == "user" else [response({"id": "fixture-user"}), failed]
    endpoint.requests.get.side_effect = replies
    assert request(endpoint)[0] == expected
    endpoint.requests.post.assert_not_called()


@pytest.mark.parametrize("kind", ["admin", "public"])
@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer "}, {"X-Admin-Token": "fixture-server-token"}])
def test_jwt_remains_required_and_no_new_bypass_is_added(endpoint, kind, headers):
    assert request(endpoint, kind=kind, headers=headers)[0] == 401
    endpoint.requests.get.assert_not_called()
    endpoint.requests.post.assert_not_called()
