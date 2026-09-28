"""Order auth dependency failures must stop both balance reads and order execution."""
import importlib.util
import io
import json
from pathlib import Path
import sys
import types
from unittest.mock import Mock

import pytest
import requests


ROOT = Path(__file__).resolve().parents[1]
SENSITIVE = "fixture-jwt fixture-user fixture-anon fixture-service upstream-private-body"
PROFILE = {
    "order_enabled": True, "broker_slug": "fixture_account",
    "max_order_krw": 200_000, "daily_order_count_limit": 5, "seed_krw": 1_000_000,
}
ORDER = {
    "ticker": "005930", "side": "BUY", "qty": 1,
    "price": 70_000, "order_type": "00", "market": "kr",
    "broker_slug": "untrusted_account",
}
UNAVAILABLE = (503, {"error": "auth_service_unavailable"})


def load_module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "vercel-api/api" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def order(monkeypatch):
    # Load the real helper, with only synthetic credentials and blocked transports.
    for key, value in {
        "SUPABASE_URL": "https://auth.example.invalid", "SUPABASE_ANON_KEY": "fixture-anon",
        "SUPABASE_SERVICE_ROLE_KEY": "", "RAILWAY_SHARED_SECRET": "fixture-service",
        "RAILWAY_URL": "https://railway.example.invalid", "ORDER_POLICY_MODE": "advised",
        "ORDER_ALLOW_MEMORY_FALLBACK": "0",
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(requests.sessions.Session, "request", Mock(side_effect=AssertionError("network forbidden")))
    monkeypatch.setattr(requests, "get", Mock(side_effect=AssertionError("unexpected GET")))
    monkeypatch.setattr(requests, "post", Mock(side_effect=AssertionError("unexpected POST")))
    sb = load_module("api.supabase_client", "supabase_client.py")
    api_pkg = types.ModuleType("api")
    api_pkg.__path__ = []
    api_pkg.supabase_client = sb
    monkeypatch.setitem(sys.modules, "api", api_pkg)
    monkeypatch.setitem(sys.modules, "api.supabase_client", sb)
    module = load_module("order_auth_under_test", "order.py")
    yield module
    requests.sessions.Session.request.assert_not_called()


def response(body, status=200):
    result = requests.Response()
    result.status_code = status
    result.url = "https://auth.example.invalid/fixture"
    result._content = json.dumps(body).encode()
    return result


def failure_response(failure):
    if isinstance(failure, int):
        return response({"detail": SENSITIVE}, failure)
    if failure == "invalid_json":
        result = response(None)
        result._content = SENSITIVE.encode()
        return result
    return getattr(requests.exceptions, failure)(SENSITIVE)


def dispatch(order, method="GET", headers=None, market="kr"):
    handler = object.__new__(order.handler)
    handler.path = f"/api/order?market={market}&broker_slug=untrusted_account"
    raw = json.dumps(ORDER).encode()
    handler.headers = {
        "Content-Length": str(len(raw)), "X-Verity-Broker": "untrusted_account",
        **({"Authorization": "Bearer fixture-jwt"} if headers is None else headers),
    }
    handler.rfile = Mock(wraps=io.BytesIO(raw))
    handler.wfile = io.BytesIO()
    handler.send_response = Mock()
    handler.send_header = Mock()
    handler.end_headers = Mock()
    getattr(handler, "do_" + method)()
    handler.send_response.assert_called_once()
    return (handler.send_response.call_args.args[0], json.loads(handler.wfile.getvalue())), handler


def assert_auth_stopped(order, handler, calls):
    handler.rfile.read.assert_not_called()
    requests.post.assert_not_called()
    assert requests.get.call_count == calls
    for call in requests.get.call_args_list:
        assert call.args[0].startswith(order.sb.SUPABASE_URL + "/")
        assert call.kwargs["allow_redirects"] is False
    assert order._ORDER_DEDUPE == {} and order._DAILY_ORDER_COUNT == {}


@pytest.mark.parametrize("method", ["GET", "POST"])
@pytest.mark.parametrize("stage", ["user", "profile"])
@pytest.mark.parametrize("failure", [
    408, 429, 500, 502, 503, 504, 204, 302, 404,
    "Timeout", "ConnectionError", "RequestException", "invalid_json",
    "InvalidURL", "MissingSchema", "InvalidSchema", "InvalidHeader",
])
def test_dependency_failure_is_503_before_any_consumer(order, caplog, method, stage, failure):
    requests.get.side_effect = (
        [response({"id": "fixture-user"})] if stage == "profile" else []
    ) + [failure_response(failure)]
    result, handler = dispatch(order, method)
    assert result == UNAVAILABLE
    assert_auth_stopped(order, handler, 2 if stage == "profile" else 1)
    assert caplog.messages == [f"order auth service unavailable: stage={stage}"]
    for secret in SENSITIVE.split():
        assert secret not in json.dumps(result) + caplog.text


@pytest.mark.parametrize("method", ["GET", "POST"])
@pytest.mark.parametrize("payload", [None, [], {}, {"id": " "}, {"id": 1}, {"id": ["fixture-user"]}])
def test_malformed_verified_user_is_unavailable(order, method, payload):
    requests.get.side_effect = [response(payload)]
    result, handler = dispatch(order, method)
    assert result == UNAVAILABLE
    assert_auth_stopped(order, handler, 1)


@pytest.mark.parametrize("method", ["GET", "POST"])
@pytest.mark.parametrize("profile", [
    None, {}, [None], [PROFILE, PROFILE],
    [{**PROFILE, "order_enabled": "true"}], [{**PROFILE, "order_enabled": 1}],
    [{**PROFILE, "broker_slug": 123}], [{**PROFILE, "max_order_krw": "bad"}],
    [{**PROFILE, "daily_order_count_limit": "bad"}], [{**PROFILE, "seed_krw": "1.5"}],
])
def test_malformed_profile_is_unavailable(order, method, profile):
    requests.get.side_effect = [response({"id": "fixture-user"}), response(profile)]
    result, handler = dispatch(order, method)
    assert result == UNAVAILABLE
    assert_auth_stopped(order, handler, 2)


@pytest.mark.parametrize("method", ["GET", "POST"])
@pytest.mark.parametrize("setting", ["SUPABASE_URL", "SUPABASE_ANON_KEY"])
def test_missing_configuration_is_unavailable(order, monkeypatch, method, setting):
    monkeypatch.setattr(order.sb, setting, "")
    result, handler = dispatch(order, method)
    assert result == UNAVAILABLE
    assert_auth_stopped(order, handler, 0)


@pytest.mark.parametrize("method", ["GET", "POST"])
def test_missing_railway_secret_still_blocks_before_auth(order, monkeypatch, method):
    monkeypatch.setattr(order, "_RAILWAY_SHARED_SECRET", "")
    result, handler = dispatch(order, method)
    assert result[0] == 503
    assert_auth_stopped(order, handler, 0)


@pytest.mark.parametrize("method", ["GET", "POST"])
@pytest.mark.parametrize("headers", [{}, {"Authorization": "Basic fixture"}, {"Authorization": "Bearer "}])
def test_missing_bearer_remains_401(order, method, headers):
    result, handler = dispatch(order, method, headers)
    assert result == (401, {"error": "Unauthorized"})
    assert_auth_stopped(order, handler, 0)


@pytest.mark.parametrize("method", ["GET", "POST"])
@pytest.mark.parametrize("status", [400, 401, 403])
def test_invalid_jwt_remains_401(order, method, status):
    requests.get.side_effect = [response({"error": "invalid JWT"}, status)]
    result, handler = dispatch(order, method)
    assert result == (401, {"error": "Invalid token"})
    assert_auth_stopped(order, handler, 1)


@pytest.mark.parametrize("method", ["GET", "POST"])
@pytest.mark.parametrize("status,profile", [
    (200, []), (200, [{}]), (200, [{**PROFILE, "order_enabled": False}]),
    (401, {"error": "denied"}), (403, {"error": "denied"}),
])
def test_missing_profile_or_permission_remains_403(order, method, status, profile):
    requests.get.side_effect = [response({"id": "fixture-user"}), response(profile, status)]
    result, handler = dispatch(order, method)
    assert result == (403, {"error": "Order not permitted for this account"})
    assert_auth_stopped(order, handler, 2)


@pytest.mark.parametrize("method", ["GET", "POST"])
@pytest.mark.parametrize("slug", [None, "", " ", "invalid/account"])
def test_broker_link_is_required(order, method, slug):
    profile = {key: value for key, value in PROFILE.items() if key != "broker_slug"}
    if slug is not None:
        profile["broker_slug"] = slug
    requests.get.side_effect = [response({"id": "fixture-user"}), response([profile])]
    result, handler = dispatch(order, method)
    assert result[0] == 403 and result[1]["error"] == "Broker account not linked"
    assert_auth_stopped(order, handler, 2)


@pytest.mark.parametrize("market", ["kr", "us"])
def test_valid_auth_reads_only_verified_broker_account(order, market):
    requests.get.side_effect = [response({"id": "fixture-user"}), response([PROFILE]), response({"balance": []})]
    result, _ = dispatch(order, market=market)
    assert result == (200, {"balance": []})
    auth, profile, railway = requests.get.call_args_list
    assert auth.args[0] == order.sb.SUPABASE_URL + "/auth/v1/user"
    assert auth.kwargs["headers"] == {"apikey": "fixture-anon", "Authorization": "Bearer fixture-jwt"}
    assert profile.args[0] == order.sb.SUPABASE_URL + "/rest/v1/profiles"
    assert profile.kwargs["params"] == {
        "id": "eq.fixture-user",
        "select": "order_enabled,max_order_krw,daily_order_count_limit,broker_slug,seed_krw",
        "limit": "1",
    }
    assert profile.kwargs["headers"]["Authorization"] == "Bearer fixture-jwt"
    assert railway.args[0] == order._RAILWAY_URL + "/api/order"
    assert railway.kwargs["params"] == {"market": market}
    assert railway.kwargs["headers"] == {
        "Content-Type": "application/json", "X-Service-Auth": "fixture-service",
        "X-Verity-User-Id": "fixture-user", "X-Verity-Broker": "fixture_account",
    }
    requests.post.assert_not_called()


def test_auth_success_and_failure_are_never_cached(order):
    requests.get.side_effect = [
        response({"id": "fixture-user"}), response([PROFILE]), response({"balance": []}),
        requests.Timeout(SENSITIVE),
        response({"id": "fixture-user"}), response([]),
        response({"id": "fixture-user"}), response([PROFILE]), response({"balance": []}),
    ]
    assert dispatch(order)[0][0] == 200
    assert dispatch(order)[0] == UNAVAILABLE
    assert dispatch(order)[0][0] == 403
    assert dispatch(order)[0][0] == 200
    assert requests.get.call_count == 9
    requests.post.assert_not_called()


@pytest.mark.parametrize("gate,expected", [("allow", 200), ("policy", 409), ("ledger", 429)])
def test_authenticated_post_keeps_policy_and_ledger_gates(order, monkeypatch, gate, expected):
    monkeypatch.setattr(order, "_kr_market_open", lambda: gate != "policy")
    monkeypatch.setattr(order, "_download_moderation", Mock(return_value=None))
    requests.get.side_effect = [
        response({"id": "fixture-user"}), response([PROFILE]),
        response({"output1": [], "output2": [{"dnca_tot_amt": "1000000", "tot_evlu_amt": "1000000"}]}),
        response({"quotes": {"005930": {"price": 70000}}, "asof": order.datetime.now(order.timezone.utc).isoformat()}),
    ]
    requests.post.side_effect = [
        response({"ok": gate != "ledger", "reason": "daily_limit"}), response({"success": True}),
    ]
    result, _ = dispatch(order, "POST")
    assert result[0] == expected
    assert requests.post.call_count == {"allow": 2, "policy": 0, "ledger": 1}[gate]
    if gate != "policy":
        reserve = requests.post.call_args_list[0]
        assert reserve.args[0].endswith("/rest/v1/rpc/reserve_order_slot")
        assert reserve.kwargs["json"]["p_daily_limit"] == PROFILE["daily_order_count_limit"]
    if gate == "allow":
        executed = requests.post.call_args_list[1]
        assert executed.args[0] == order._RAILWAY_URL + "/api/order"
        assert executed.kwargs["json"] == {key: ("buy" if key == "side" else value) for key, value in ORDER.items() if key != "broker_slug"}
        assert executed.kwargs["headers"]["X-Verity-Broker"] == "fixture_account"
        assert "Authorization" not in executed.kwargs["headers"]
        assert result[1]["order_policy"]["mode"] == "advised"


@pytest.mark.parametrize("failure", [400, 401, 403, 429, 503, "Timeout", "InvalidURL", "invalid_json"])
def test_legacy_verify_jwt_failures_still_return_none(order, failure):
    requests.get.side_effect = [failure_response(failure)]
    assert order.sb.verify_jwt("fixture-jwt") is None


@pytest.mark.parametrize("payload,expected", [
    (None, None), ([], None), ({}, None), ({"id": 1}, 1), ({"id": " "}, " "),
    ({"id": "fixture-user"}, "fixture-user"),
])
def test_legacy_verify_jwt_payload_semantics_are_unchanged(order, payload, expected):
    requests.get.side_effect = [response(payload)]
    assert order.sb.verify_jwt("fixture-jwt") == expected


@pytest.mark.parametrize("strict", [False, True])
def test_empty_jwt_never_calls_upstream(order, strict):
    assert order.sb.verify_jwt("", strict=strict) is None
    requests.get.assert_not_called()


def test_legacy_missing_configuration_still_returns_none(order, monkeypatch):
    monkeypatch.setattr(order.sb, "SUPABASE_URL", "")
    assert order.sb.verify_jwt("fixture-jwt") is None
    requests.get.assert_not_called()


def test_select_strict_status_check_is_opt_in(order):
    requests.get.side_effect = [response([PROFILE], 302), response([PROFILE], 302)]
    assert order.sb.select("profiles", {}) == [PROFILE]
    with pytest.raises(order.sb.AuthServiceUnavailable):
        order.sb.select("profiles", {}, strict=True)
