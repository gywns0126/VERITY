"""Personal investment routes require owner roles; site administration does not."""
import importlib.util
import io
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
import requests


def load_admin():
    path = Path(__file__).resolve().parents[1] / "vercel-api/api/admin.py"
    spec = importlib.util.spec_from_file_location("admin_owner_auth", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


INVENTORY = load_admin()
PRIVATE_ROUTES = tuple(INVENTORY.ROUTES)
SITE_ROUTES = tuple(INVENTORY.MOD_ROUTES)
OWNER = {"is_admin": True, "is_super_admin": True}
DEPUTY = {"is_admin": True, "is_super_admin": False}


@pytest.fixture
def adm(monkeypatch):
    module = load_admin()
    monkeypatch.setattr(module, "SUPABASE_URL", "https://auth.example.invalid")
    monkeypatch.setattr(module, "SUPABASE_ANON_KEY", "fixture-anon")
    monkeypatch.setattr(module, "ADMIN_BYPASS_TOKEN", "fixture-server-token")
    monkeypatch.setattr(module, "_sec_is_blocked", Mock(return_value=False))
    monkeypatch.setattr(module, "_sec_note_unauthorized", Mock())
    monkeypatch.setattr(module.requests, "get", Mock(side_effect=AssertionError("network forbidden")))
    return module


def response(body, status=200):
    return Mock(status_code=status, json=Mock(return_value=body))


def transport(adm, profile):
    def get(url, **kwargs):
        assert kwargs["headers"]["Authorization"] == "Bearer fixture-jwt"
        if url.endswith("/auth/v1/user"):
            return response({"id": "fixture-user"})
        assert url.endswith("/rest/v1/profiles")
        assert kwargs["params"] == {"id": "eq.fixture-user", "select": "is_admin,is_super_admin"}
        return response(profile)
    adm.requests.get.side_effect = get


def dispatch(adm, route, method="GET", headers=None):
    handler = object.__new__(adm.handler)
    handler.path = "/api/admin?type=" + route
    handler.headers = headers if headers is not None else {"Authorization": "Bearer fixture-jwt"}
    handler.rfile = io.BytesIO(b"")
    handler.wfile = io.BytesIO()
    handler.send_response = Mock()
    handler.send_header = Mock()
    handler.end_headers = Mock()
    getattr(handler, "do_" + method)()
    handler.send_header.assert_any_call("Cache-Control", "no-store")
    return handler.send_response.call_args.args[0], json.loads(handler.wfile.getvalue())


@pytest.mark.parametrize("route", PRIVATE_ROUTES)
@pytest.mark.parametrize("profile,expected", [(OWNER, 200), (DEPUTY, 401)])
def test_every_investment_route_is_owner_only(adm, monkeypatch, route, profile, expected):
    transport(adm, [profile])
    consumer = Mock(return_value={"_status": 200, "_body": {"private_fixture": True}})
    monkeypatch.setitem(adm.ROUTES, route, consumer)
    status, body = dispatch(adm, route)
    assert status == expected
    assert consumer.call_count == (1 if expected == 200 else 0)
    if expected == 401:
        assert "private_fixture" not in body


@pytest.mark.parametrize("route", SITE_ROUTES)
@pytest.mark.parametrize("method", ["GET", "POST", "DELETE"])
def test_deputy_keeps_general_site_management(adm, monkeypatch, route, method):
    transport(adm, [DEPUTY])
    consumer = Mock(return_value={"_status": 200, "_body": {"site_fixture": True}})
    monkeypatch.setitem(adm.MOD_ROUTES, route, consumer)
    assert dispatch(adm, route, method) == (200, {"site_fixture": True})
    assert consumer.call_count == 1
    assert consumer.call_args.args[1:] == (method, {})


@pytest.mark.parametrize("profile", [
    None, {}, [], [None], [OWNER, OWNER],
    [{"is_admin": True}], [{"is_super_admin": True}],
    [{"is_admin": 1, "is_super_admin": True}],
    [{"is_admin": True, "is_super_admin": "true"}],
    [{"is_admin": False, "is_super_admin": True}],
])
def test_invalid_or_incomplete_profile_fails_closed(adm, profile):
    transport(adm, profile)
    assert dispatch(adm, "portfolio_full")[0] == 401


@pytest.mark.parametrize("user", [None, [], {}, {"id": " "}, {"id": 1}])
def test_invalid_user_fails_before_profile(adm, user):
    adm.requests.get.side_effect = [response(user)]
    assert dispatch(adm, "portfolio_full")[0] == 401
    assert adm.requests.get.call_count == 1


@pytest.mark.parametrize("failed", [response({}, 500), requests.Timeout("fixture"), ValueError("fixture")])
@pytest.mark.parametrize("stage", ["user", "profile"])
def test_auth_service_failure_denies(adm, failed, stage):
    adm.requests.get.side_effect = ([response({"id": "fixture-user"})] if stage == "profile" else []) + [failed]
    assert dispatch(adm, "portfolio_full")[0] == 401


@pytest.mark.parametrize("route", PRIVATE_ROUTES + SITE_ROUTES)
def test_no_session_denied_on_every_route(adm, route):
    assert dispatch(adm, route, headers={})[0] == 401
    adm.requests.get.assert_not_called()


def test_server_bypass_preserved(adm, monkeypatch):
    consumer = Mock(return_value={"_body": {"private_fixture": True}})
    monkeypatch.setitem(adm.ROUTES, "portfolio_full", consumer)
    assert dispatch(adm, "portfolio_full", headers={"X-Admin-Token": "fixture-server-token"})[0] == 200
    adm.requests.get.assert_not_called()


def test_unknown_route_does_not_fall_back_to_general_admin(adm):
    transport(adm, [DEPUTY])
    assert dispatch(adm, "new_private_route")[0] == 401


def test_duplicate_type_cannot_cross_route_boundary(adm, monkeypatch):
    transport(adm, [DEPUTY])
    consumer = Mock()
    monkeypatch.setitem(adm.ROUTES, "portfolio_full", consumer)
    assert dispatch(adm, "portfolio_full&type=notices")[0] == 401
    consumer.assert_not_called()


def test_nonadmin_cannot_use_general_site_admin(adm):
    transport(adm, [{"is_admin": False, "is_super_admin": True}])
    assert dispatch(adm, "notices")[0] == 401


@pytest.mark.parametrize("action", ["ban", "update"])
def test_member_update_never_returns_financial_profile_fields(adm, monkeypatch, action):
    monkeypatch.setattr(adm, "_svc_ready", lambda: True)
    monkeypatch.setattr(adm, "_caller_identity", lambda headers: {"id": "fixture-deputy"})
    monkeypatch.setattr(adm, "_audit", Mock())
    updated = {"id": "fixture-owner", "nickname": "updated", "seed_krw": 1000000,
               "broker_slug": "fixture-account", "max_order_krw": 200000,
               "daily_order_count_limit": 10, "order_enabled": True, "future_private_field": "private"}
    result = response([updated])
    result.text = json.dumps([updated])
    monkeypatch.setattr(adm.requests, "patch", Mock(return_value=result))
    handler = Mock(headers={"Authorization": "Bearer fixture-jwt"})
    body = {"action": action, "user_id": "fixture-owner", "nickname": "updated"}
    out = adm.handle_member_management(handler, "POST", body)
    assert out["_status"] == 200 and out["_body"]["ok"] is True
    member = out["_body"]["member"]
    assert member["id"] == "fixture-owner" and member["nickname"] == "updated"
    assert set(member) == set(adm._MEMBER_ADMIN_FIELDS)
    assert not (set(updated) - {"id", "nickname"}) & set(member)
