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
    monkeypatch.setattr(module.requests.sessions.Session, "request", Mock(side_effect=AssertionError("network forbidden")))
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
    handler.send_header.assert_any_call("Access-Control-Allow-Origin", "*")
    handler.send_header.assert_any_call("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
    handler.send_header.assert_any_call("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Admin-Token")
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


@pytest.mark.parametrize("profile,expected", [
    (None, 503), ({}, 503), ([], 401), ([None], 503), ([OWNER, OWNER], 503),
    ([{}], 401), ([{"is_admin": True}], 401), ([{"is_super_admin": True}], 401),
    ([{"is_admin": 1, "is_super_admin": True}], 401),
    ([{"is_admin": True, "is_super_admin": "true"}], 401),
    ([{"is_admin": False, "is_super_admin": True}], 401),
])
def test_invalid_or_incomplete_profile_fails_closed(adm, monkeypatch, profile, expected):
    transport(adm, profile)
    consumer = Mock()
    monkeypatch.setitem(adm.ROUTES, "portfolio_full", consumer)
    status, body = dispatch(adm, "portfolio_full")
    assert status == expected
    assert body["error"] == ("auth_service_unavailable" if expected == 503 else "unauthorized")
    consumer.assert_not_called()


@pytest.mark.parametrize("user", [None, [], {}, {"id": " "}, {"id": 1}])
def test_invalid_user_fails_before_profile(adm, monkeypatch, user):
    adm.requests.get.side_effect = [response(user)]
    consumer = Mock()
    monkeypatch.setitem(adm.ROUTES, "portfolio_full", consumer)
    assert dispatch(adm, "portfolio_full") == (503, {"error": "auth_service_unavailable"})
    assert adm.requests.get.call_count == 1
    consumer.assert_not_called()
    adm._sec_note_unauthorized.assert_not_called()


@pytest.mark.parametrize("failure,expected", [
    (400, 401), (401, 401), (403, 401), (404, 401),
    (408, 503), (429, 503), (500, 503), (502, 503), (503, 503), (504, 503),
    (204, 503), (302, 503),
    ("timeout", 503), ("connection", 503), ("request", 503), ("invalid_json", 503),
    ("InvalidURL", 401), ("MissingSchema", 401), ("InvalidSchema", 401), ("InvalidHeader", 401),
])
@pytest.mark.parametrize("stage", ["user", "profile"])
@pytest.mark.parametrize("route,method", [
    ("portfolio_full", "GET"), ("notices", "GET"), ("notices", "POST"), ("notices", "DELETE"),
])
def test_auth_upstream_errors_stop_before_consumer(adm, monkeypatch, caplog, failure, expected, stage, route, method):
    sensitive = "fixture-jwt fixture-user fixture-anon private@example.invalid upstream-body"
    if isinstance(failure, int):
        failed = response({"detail": sensitive}, failure)
    elif failure == "invalid_json":
        failed = response(None)
        failed.json.side_effect = ValueError(sensitive)
    elif failure in ("InvalidURL", "MissingSchema", "InvalidSchema", "InvalidHeader"):
        failed = getattr(requests.exceptions, failure)(sensitive)
    else:
        error = {"timeout": requests.Timeout, "connection": requests.ConnectionError,
                 "request": requests.RequestException}[failure]
        failed = error(sensitive)
    adm.requests.get.side_effect = ([response({"id": "fixture-user"})] if stage == "profile" else []) + [failed]
    consumer = Mock()
    monkeypatch.setitem(adm.ROUTES if route in adm.ROUTES else adm.MOD_ROUTES, route, consumer)
    read_body = Mock(side_effect=AssertionError("must not read mutation body before auth"))
    monkeypatch.setattr(adm, "_read_body", read_body)
    status, body = dispatch(adm, route, method)
    assert status == expected
    consumer.assert_not_called()
    read_body.assert_not_called()
    adm.requests.sessions.Session.request.assert_not_called()
    assert adm.requests.get.call_count == (2 if stage == "profile" else 1)
    if expected == 503:
        assert body == {"error": "auth_service_unavailable"}
        adm._sec_note_unauthorized.assert_not_called()
        upstream_status = failure if isinstance(failure, int) else (200 if failure == "invalid_json" else None)
        assert caplog.messages == [f"admin auth service unavailable: stage={stage} status={upstream_status}"]
    else:
        assert body == {"error": "unauthorized", "reason": "unauthorized"}
        adm._sec_note_unauthorized.assert_called_once()
    for secret in sensitive.split():
        assert secret not in caplog.text


@pytest.mark.parametrize("stage", ["user", "profile"])
@pytest.mark.parametrize("method", ["GET", "POST", "DELETE"])
def test_auth_budget_exhaustion_is_unavailable(adm, monkeypatch, stage, method):
    timeouts = ([5] if stage == "profile" else []) + [adm._BudgetExceeded("authorize", 12.1)]
    monkeypatch.setattr(adm, "_t", Mock(side_effect=timeouts))
    adm.requests.get.side_effect = [response({"id": "fixture-user"})]
    consumer = Mock()
    route = "portfolio_full" if method == "GET" else "notices"
    monkeypatch.setitem(adm.ROUTES if method == "GET" else adm.MOD_ROUTES, route, consumer)
    assert dispatch(adm, route, method) == (503, {"error": "auth_service_unavailable"})
    assert adm.requests.get.call_count == (1 if stage == "profile" else 0)
    consumer.assert_not_called()
    adm._sec_note_unauthorized.assert_not_called()


def test_site_get_second_auth_gate_stops_before_consumer(adm, monkeypatch):
    adm.requests.get.side_effect = [response({"id": "fixture-user"}), response([DEPUTY]), requests.Timeout("fixture")]
    consumer = Mock()
    monkeypatch.setitem(adm.MOD_ROUTES, "notices", consumer)
    assert dispatch(adm, "notices") == (503, {"error": "auth_service_unavailable"})
    assert adm.requests.get.call_count == 3
    consumer.assert_not_called()
    adm._sec_note_unauthorized.assert_not_called()


@pytest.mark.parametrize("setting", ["SUPABASE_URL", "SUPABASE_ANON_KEY"])
def test_missing_auth_configuration_stays_unauthorized(adm, monkeypatch, setting):
    monkeypatch.setattr(adm, setting, "")
    assert dispatch(adm, "portfolio_full")[0] == 401
    adm.requests.get.assert_not_called()


def test_no_auth_configured_reason_preserved(adm, monkeypatch):
    monkeypatch.setattr(adm, "SUPABASE_URL", "")
    monkeypatch.setattr(adm, "ADMIN_BYPASS_TOKEN", "")
    assert dispatch(adm, "portfolio_full") == (401, {"error": "unauthorized", "reason": "no_auth_configured"})
    adm.requests.get.assert_not_called()


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
