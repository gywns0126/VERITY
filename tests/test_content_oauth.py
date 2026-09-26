"""Local OAuth unit tests with fake RPC responses, not DB/integration proof.

These tests check validation and the RPC contract. They do not establish SQL
atomicity, code replay protection, persistent quotas, or deployed revocation.
No real credentials, DB, ChatGPT connection, or model API is used.
"""
import base64
import hashlib
import json
import re
import sys
from http.cookies import SimpleCookie
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "vercel-api"))
import content_oauth as m

ORIGIN = "https://content.example"
RESOURCE = ORIGIN + "/api/content_mcp"
ISSUER = ORIGIN + "/api/content_oauth"
VERIFIER = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
CHALLENGE = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
INVITE = "aninvite_" + "I" * 43
CODE = "ancode_" + "C" * 43
TOKEN = "ancontent_" + "T" * 43
REAL_RPC = m.rpc


@pytest.fixture(autouse=True)
def local_only(monkeypatch):
    monkeypatch.setenv("CONTENT_MCP_ENABLED", "1")
    monkeypatch.setenv("CONTENT_MCP_ORIGIN", ORIGIN)
    monkeypatch.setenv("CONTENT_MCP_CONSENT_SECRET", "S" * 43)
    monkeypatch.setenv("SUPABASE_URL", "https://local-unit-test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "fake-service-key-not-a-credential")
    monkeypatch.setattr(m, "_json_request", Mock(side_effect=AssertionError("No network in unit tests")))
    fake = Mock(side_effect=AssertionError("Unexpected RPC in unit test"))
    monkeypatch.setattr(m, "rpc", fake)
    return fake


@pytest.fixture
def clock(monkeypatch):
    now = [2_000_000_000]
    monkeypatch.setattr(m, "time", SimpleNamespace(time=lambda: now[0]))
    return now


def authorization(**changes):
    return {"client_id": m.CLIENT_ID, "response_type": "code", "redirect_uri": m.REDIRECT,
            "resource": RESOURCE, "scope": "content:read", "state": "draft & state=한글+?",
            "code_challenge": CHALLENGE, "code_challenge_method": "S256", **changes}


def token_form(**changes):
    return {"grant_type": "authorization_code", "code": CODE, "client_id": m.CLIENT_ID,
            "redirect_uri": m.REDIRECT, "resource": RESOURCE, "code_verifier": VERIFIER,
            **changes}


def post(op, data, headers=None):
    return m.process("POST", "/api/content_oauth?op=" + op,
                     {"Content-Type": "application/x-www-form-urlencoded", **(headers or {})},
                     urlencode(data).encode())


def consent(params=None):
    params = authorization() if params is None else params
    status, page, headers = m.process(
        "GET", "/api/content_oauth?" + urlencode({"op": "authorize", **params}), {}, b"")
    assert status == 200
    signed = re.search(r'name="consent" value="([^"]+)"', page).group(1)
    cookie = headers["Set-Cookie"].split(";", 1)[0]
    return signed, cookie, headers["Set-Cookie"]


def assert_error(status, code, fn, *args, **kwargs):
    with pytest.raises(m.ServiceError) as error:
        fn(*args, **kwargs)
    assert (error.value.status, error.value.code) == (status, code)


def sha(value):
    # Independent assertion: do not use the implementation's digest helper.
    return hashlib.sha256(value.encode("ascii")).hexdigest()


@pytest.mark.parametrize("kind,path", [
    ("server", "/.well-known/oauth-authorization-server/api/content_oauth"),
    ("resource", "/.well-known/oauth-protected-resource/api/content_mcp"),
    ("server", "/api/content_oauth?op=server"),
    ("resource", "/api/content_oauth?op=resource"),
])
def test_metadata(kind, path, local_only):
    status, body, headers = m.process("GET", path, {}, b"")
    assert status == 200 and headers == {}
    assert body["scopes_supported"] == ["content:read"]
    if kind == "resource":
        assert body["resource"] == RESOURCE
        assert body["authorization_servers"] == [ISSUER]
        assert body["bearer_methods_supported"] == ["header"]
    else:
        assert body["issuer"] == ISSUER
        assert body["authorization_endpoint"] == ISSUER + "?op=authorize"
        assert body["token_endpoint"] == ISSUER + "?op=token"
        assert body["response_types_supported"] == ["code"]
        assert body["grant_types_supported"] == ["authorization_code"]
        assert body["token_endpoint_auth_methods_supported"] == ["none"]
        assert body["code_challenge_methods_supported"] == ["S256"]
        assert body["authorization_response_iss_parameter_supported"] is True
        assert "registration_endpoint" not in body
    local_only.assert_not_called()


@pytest.mark.parametrize("key,value", [
    ("CONTENT_MCP_ENABLED", "0"), ("CONTENT_MCP_ENABLED", None),
    ("CONTENT_MCP_ORIGIN", ""), ("CONTENT_MCP_ORIGIN", "http://content.example"),
    ("CONTENT_MCP_ORIGIN", ORIGIN + "/"), ("CONTENT_MCP_ORIGIN", ORIGIN + "/path"),
    ("CONTENT_MCP_ORIGIN", "https://user@content.example"),
])
def test_configuration_fails_closed(monkeypatch, local_only, key, value):
    if value is None:
        monkeypatch.delenv(key, raising=False)
    else:
        monkeypatch.setenv(key, value)
    assert_error(503, "connection_not_configured", m.authenticate,
                 {"authorization": "Bearer " + TOKEN})
    local_only.assert_not_called()


@pytest.mark.parametrize("state", ["x", "x" * 1024, "한글 & next=ok+%"])
def test_valid_authorization_and_state_boundaries(state):
    params = authorization(state=state)
    assert m.validated_authorization(params, m.config()) == params
    assert m.challenge(VERIFIER) == CHALLENGE


@pytest.mark.parametrize("key,value", [
    ("redirect_uri", "https://evil.example/callback"),
    ("redirect_uri", m.REDIRECT + "?next=evil"), ("redirect_uri", m.REDIRECT + "/"),
    ("resource", "https://evil.example/api/content_mcp"), ("resource", RESOURCE + "/"),
    ("scope", ""), ("scope", "content:read content:write"),
    ("client_id", "other-client"), ("response_type", "token"),
    ("code_challenge_method", "plain"), ("code_challenge_method", "s256"),
    ("code_challenge", "A" * 42), ("code_challenge", "A" * 44),
    ("code_challenge", "A" * 42 + "+"),
    ("state", ""), ("state", "x" * 1025), ("state", "bad\nstate"),
    ("state", "bad\x00state"), ("state", "bad\x7fstate"), ("extra", "value"),
])
def test_invalid_authorization_never_redirects_or_calls_rpc(local_only, key, value):
    path = "/api/content_oauth?" + urlencode({"op": "authorize", **authorization(**{key: value})})
    assert_error(400, "invalid_authorization_request", m.process, "GET", path, {}, b"")
    local_only.assert_not_called()


@pytest.mark.parametrize("missing", list(authorization()))
def test_missing_authorization_fields(missing):
    params = authorization()
    del params[missing]
    assert_error(400, "invalid_authorization_request", m.validated_authorization, params, m.config())


@pytest.mark.parametrize("raw", ["state=a&state=b", "state=%FF", "state=" + "x" * 4097,
                                 "&".join(f"k{i}=v" for i in range(17))])
def test_form_ambiguity_and_invalid_encoding(raw):
    assert_error(400, "invalid_request", m.fields, raw)


def test_signed_consent_cookie_attributes_and_round_trip(clock, local_only):
    signed, cookie, set_cookie = consent()
    jar = SimpleCookie()
    jar.load(set_cookie)
    morsel = jar[m.COOKIE]
    assert m.COOKIE.startswith("__Host-")
    assert morsel["path"] == "/" and morsel["max-age"] == "300"
    assert morsel["secure"] and morsel["httponly"]
    assert morsel["samesite"] == "Lax" and not morsel["domain"]
    assert m.unseal(signed, cookie) == authorization()
    local_only.assert_not_called()


@pytest.mark.parametrize("damage", ["payload", "signature", "malformed", "missing-cookie",
                                    "wrong-cookie", "short-cookie"])
def test_consent_tamper_and_csrf_binding(clock, local_only, damage):
    signed, cookie, _ = consent()
    encoded, signature = signed.split(".")
    if damage == "payload":
        doc = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
        doc["params"]["resource"] = "https://evil.example/resource"
        signed = base64.urlsafe_b64encode(json.dumps(doc).encode()).decode().rstrip("=") + "." + signature
    elif damage == "signature":
        signed = encoded + "." + ("B" if signature[0] == "A" else "A") + signature[1:]
    elif damage == "malformed":
        signed = "not.a.valid.envelope"
    elif damage == "missing-cookie":
        cookie = ""
    elif damage == "wrong-cookie":
        cookie = m.COOKIE + "=" + "X" * 43
    else:
        cookie = m.COOKIE + "=short"
    assert_error(400, "invalid_or_expired_consent", post, "authorize",
                 {"consent": signed, "invite": INVITE, "decision": "allow"},
                 {"Origin": ORIGIN, "Cookie": cookie})
    local_only.assert_not_called()


@pytest.mark.parametrize("offset,accepted", [(299, True), (300, False), (301, False), (-2, False)])
def test_consent_expiry_boundary_and_future_rejection(clock, offset, accepted):
    signed, cookie, _ = consent()
    clock[0] += offset
    if accepted:
        assert m.unseal(signed, cookie) == authorization()
    else:
        assert_error(400, "invalid_or_expired_consent", m.unseal, signed, cookie)


@pytest.mark.parametrize("origin", [None, "null", "https://evil.example", ORIGIN + "/"])
def test_consent_requires_exact_origin(clock, local_only, origin):
    signed, cookie, _ = consent()
    headers = {"Cookie": cookie}
    if origin is not None:
        headers["Origin"] = origin
    assert_error(403, "invalid_consent", post, "authorize",
                 {"consent": signed, "invite": INVITE, "decision": "allow"}, headers)
    local_only.assert_not_called()


@pytest.mark.parametrize("key", ["", "short", "S" * 129, "+" * 43])
def test_consent_requires_configured_signing_secret(monkeypatch, key):
    monkeypatch.setenv("CONTENT_MCP_CONSENT_SECRET", key)
    assert_error(503, "connection_not_configured", consent)


@pytest.mark.parametrize("decision", ["allow", "deny"])
def test_allow_deny_redirect_preserves_issuer_state_and_clears_cookie(clock, local_only, decision):
    signed, cookie, _ = consent()
    local_only.side_effect = None
    local_only.return_value = {"status": "allowed"}
    status, body, headers = post("authorize",
        {"consent": signed, "invite": INVITE if decision == "allow" else "", "decision": decision},
        {"Origin": ORIGIN, "Cookie": cookie})
    target = urlsplit(headers["Location"])
    assert status == 303 and body == {}
    assert target._replace(query="").geturl() == m.REDIRECT
    query = parse_qs(target.query)
    assert query["iss"] == [ISSUER] and query["state"] == [authorization()["state"]]
    assert "Max-Age=0" in headers["Set-Cookie"]
    assert "Secure; HttpOnly; SameSite=Lax" in headers["Set-Cookie"]
    if decision == "deny":
        assert query == {"iss": [ISSUER], "state": [authorization()["state"]], "error": ["access_denied"]}
        local_only.assert_not_called()
    else:
        code = query["code"][0]
        assert set(query) == {"iss", "state", "code"}
        assert re.fullmatch(r"ancode_[A-Za-z0-9_-]{43}", code)
        local_only.assert_called_once_with("content_mcp_issue_code", {
            "p_invite_hash": sha(INVITE), "p_code_hash": sha(code), "p_client_id": m.CLIENT_ID,
            "p_redirect_uri": m.REDIRECT, "p_resource": RESOURCE, "p_scope": "content:read",
            "p_code_challenge": CHALLENGE})
        assert INVITE not in repr(local_only.call_args) and code not in repr(local_only.call_args)


@pytest.mark.parametrize("reply,status,code", [
    ({"status": "denied"}, 403, "invalid_invitation"),
    ({"status": "revoked"}, 403, "invalid_invitation"),
    ({}, 403, "invalid_invitation"), ({"status": "limited"}, 429, "request_limit_reached"),
])
def test_invite_rpc_denial_does_not_redirect(clock, local_only, reply, status, code):
    signed, cookie, _ = consent()
    local_only.side_effect = None
    local_only.return_value = reply
    assert_error(status, code, post, "authorize",
                 {"consent": signed, "invite": INVITE, "decision": "allow"},
                 {"Origin": ORIGIN, "Cookie": cookie})
    assert local_only.call_count == 1


@pytest.mark.parametrize("changes,status,code", [
    ({"invite": "website-login-token"}, 403, "invalid_invitation"),
    ({"invite": ""}, 403, "invalid_invitation"),
    ({"decision": "other"}, 400, "invalid_consent"),
    ({"extra": "value"}, 403, "invalid_consent"),
])
def test_invalid_consent_fields(clock, local_only, changes, status, code):
    signed, cookie, _ = consent()
    assert_error(status, code, post, "authorize",
                 {"consent": signed, "invite": INVITE, "decision": "allow", **changes},
                 {"Origin": ORIGIN, "Cookie": cookie})
    local_only.assert_not_called()


@pytest.mark.parametrize("explicit_scope", [False, True])
@pytest.mark.parametrize("origin", [None, "https://chatgpt.com", "https://chat.openai.com"])
def test_exchange_binds_hashes_resource_scope_and_pkce(local_only, explicit_scope, origin):
    local_only.side_effect = None
    local_only.return_value = {"status": "allowed", "expires_in": 3600}
    form = token_form(**({"scope": "content:read"} if explicit_scope else {}))
    status, body, _ = post("token", form, {"Origin": origin} if origin else {})
    assert status == 200
    assert set(body) == {"access_token", "token_type", "expires_in", "scope"}
    assert body["token_type"] == "Bearer" and body["scope"] == "content:read"
    assert body["expires_in"] == 3600
    token = body["access_token"]
    assert re.fullmatch(r"ancontent_[A-Za-z0-9_-]{43}", token)
    local_only.assert_called_once_with("content_mcp_exchange_code", {
        "p_code_hash": sha(CODE), "p_token_hash": sha(token), "p_scope": "content:read",
        "p_code_challenge": CHALLENGE, "p_client_id": m.CLIENT_ID,
        "p_redirect_uri": m.REDIRECT, "p_resource": RESOURCE})
    assert all(secret not in repr(local_only.call_args) for secret in (CODE, token, VERIFIER))


@pytest.mark.parametrize("key,value", [
    ("grant_type", "refresh_token"), ("client_id", "other"), ("redirect_uri", m.REDIRECT + "/"),
    ("resource", RESOURCE + "/"), ("scope", "content:read content:write"),
    ("scope", ""), ("client_secret", "not-accepted"), ("code", "website-token"),
    ("code", "ancode_" + "A" * 42), ("code", "ancode_" + "A" * 44),
    ("code_verifier", "a" * 42), ("code_verifier", "a" * 129), ("code_verifier", "+" * 43),
])
def test_invalid_exchange_fields_do_not_reach_rpc(local_only, key, value):
    assert_error(400, "invalid_grant", post, "token", token_form(**{key: value}))
    local_only.assert_not_called()


@pytest.mark.parametrize("missing", list(token_form()))
def test_missing_exchange_fields(local_only, missing):
    form = token_form()
    del form[missing]
    assert_error(400, "invalid_grant", post, "token", form)
    local_only.assert_not_called()


@pytest.mark.parametrize("headers", [{"Authorization": "Basic abc"},
    {"Authorization": "Bearer website-token"}, {"Origin": "null"},
    {"Origin": "https://evil.example"}, {"Origin": "https://chatgpt.com.evil.example"}])
def test_exchange_rejects_auth_header_and_untrusted_origin(local_only, headers):
    assert_error(400, "invalid_grant", post, "token", token_form(), headers)
    local_only.assert_not_called()


@pytest.mark.parametrize("reply", [{"status": "denied"}, {"status": "limited"}, {},
    {"status": "allowed"}, *[{"status": "allowed", "expires_in": value}
                            for value in (None, True, False, "3600", 1.5, 0, -1, 3601)]])
def test_exchange_denial_or_invalid_expiry_never_returns_token(local_only, reply):
    local_only.side_effect = None
    local_only.return_value = reply
    assert_error(400, "invalid_grant", post, "token", token_form())


def test_wrong_but_well_formed_verifier_is_bound_to_rpc_denial(local_only):
    wrong = "W" * 43
    local_only.side_effect = None
    local_only.return_value = {"status": "denied"}
    assert_error(400, "invalid_grant", post, "token", token_form(code_verifier=wrong))
    expected = base64.urlsafe_b64encode(hashlib.sha256(wrong.encode()).digest()).decode().rstrip("=")
    assert local_only.call_args.args[1]["p_code_challenge"] == expected != CHALLENGE


@pytest.mark.parametrize("auth", ["", "Bearer website-login-token", "bearer " + TOKEN,
    "Basic abc", "Bearer ancontent_" + "T" * 42, "Bearer ancontent_" + "T" * 44,
    "Bearer " + TOKEN + " ", "Bearer " + TOKEN + "\n"])
def test_authenticate_rejects_invalid_tokens_before_rpc(local_only, auth):
    assert_error(401, "unauthorized", m.authenticate, {"authorization": auth})
    local_only.assert_not_called()


@pytest.mark.parametrize("reply,status,code", [
    ({"status": "denied"}, 401, "unauthorized"), ({"status": "revoked"}, 401, "unauthorized"),
    ({"status": "expired"}, 401, "unauthorized"), ({}, 401, "unauthorized"),
    ({"status": True}, 401, "unauthorized"), ({"status": "limited"}, 429, "request_limit_reached"),
])
def test_authenticate_fails_closed_on_rpc_response(local_only, reply, status, code):
    local_only.side_effect = None
    local_only.return_value = reply
    assert_error(status, code, m.authenticate, {"authorization": "Bearer " + TOKEN})
    local_only.assert_called_once_with("content_mcp_consume_token", {
        "p_token_hash": sha(TOKEN), "p_resource": RESOURCE, "p_scope": "content:read"})


def test_invite_revocation_response_rechecked_without_cache(monkeypatch):
    # Simulated RPC decision change only; this does not test a real invite UPDATE.
    request = Mock(side_effect=[{"status": "allowed"}, {"status": "denied"}])
    monkeypatch.setattr(m, "rpc", REAL_RPC)
    monkeypatch.setattr(m, "_json_request", request)
    headers = {"authorization": "Bearer " + TOKEN}
    assert m.authenticate(headers) is None
    assert_error(401, "unauthorized", m.authenticate, headers)
    assert request.call_count == 2
    for call in request.call_args_list:
        assert call.args == ("https://local-unit-test.supabase.co/rest/v1/rpc/content_mcp_consume_token",)
        assert json.loads(call.kwargs["data"]) == {
            "p_token_hash": sha(TOKEN), "p_resource": RESOURCE, "p_scope": "content:read"}
        assert TOKEN not in call.kwargs["data"].decode()


@pytest.mark.parametrize("reply", [None, [], "allowed", True, 1])
def test_malformed_rpc_reply_is_unavailable_not_authenticated(monkeypatch, reply):
    monkeypatch.setattr(m, "rpc", REAL_RPC)
    monkeypatch.setattr(m, "_json_request", Mock(return_value=reply))
    assert_error(503, "access_check_unavailable", m.authenticate, {"authorization": "Bearer " + TOKEN})


@pytest.mark.parametrize("operation", ["authenticate", "token", "authorize"])
def test_rpc_unavailable_propagates_without_success(clock, local_only, operation):
    local_only.side_effect = m.ServiceError(503, "upstream_unavailable")
    if operation == "authenticate":
        assert_error(503, "upstream_unavailable", m.authenticate, {"authorization": "Bearer " + TOKEN})
    elif operation == "token":
        assert_error(503, "upstream_unavailable", post, "token", token_form())
    else:
        signed, cookie, _ = consent()
        assert_error(503, "upstream_unavailable", post, "authorize",
                     {"consent": signed, "invite": INVITE, "decision": "allow"},
                     {"Origin": ORIGIN, "Cookie": cookie})


@pytest.mark.parametrize("key,value", [("SUPABASE_URL", "https://evil.example"),
    ("SUPABASE_URL", ""), ("SUPABASE_SERVICE_ROLE_KEY", "")])
def test_rpc_configuration_rejected_before_network(monkeypatch, key, value):
    monkeypatch.setenv(key, value)
    request = Mock(side_effect=AssertionError("No network"))
    monkeypatch.setattr(m, "_json_request", request)
    assert_error(503, "connection_not_configured", REAL_RPC, "content_mcp_consume_token", {})
    request.assert_not_called()


@pytest.mark.parametrize("stage,expected_status", [("consent", 200), ("deny", 303)])
def test_adapter_consent_headers_allow_exact_callback(clock, local_only, stage, expected_status):
    """Exercise real adapter headers locally; not a browser CSP/navigation test."""
    import importlib.util
    from email.message import Message
    from io import BytesIO

    path = Path(__file__).resolve().parents[1] / "vercel-api/api/content_oauth.py"
    spec = importlib.util.spec_from_file_location("content_oauth_http_test", path)
    adapter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter)
    handler = object.__new__(adapter.handler)
    handler.headers = Message()
    handler.command = "GET"
    handler.path = "/api/content_oauth?" + urlencode({"op": "authorize", **authorization()})
    body = b""
    if stage == "deny":
        signed, cookie, _ = consent()
        handler.command = "POST"
        handler.path = "/api/content_oauth?op=authorize"
        body = urlencode({"consent": signed, "invite": "", "decision": "deny"}).encode()
        handler.headers["Content-Type"] = "application/x-www-form-urlencoded"
        handler.headers["Origin"] = ORIGIN
        handler.headers["Cookie"] = cookie
    handler.headers["Content-Length"] = str(len(body))
    handler.rfile, handler.wfile = BytesIO(body), BytesIO()
    handler.send_response, handler.send_header, handler.end_headers = Mock(), Mock(), Mock()

    handler._handle()

    handler.send_response.assert_called_once_with(expected_status)
    sent = handler.send_header.call_args_list
    assert [call.args[1] for call in sent if call.args[0] == "Referrer-Policy"] == ["strict-origin"]
    policies = [call.args[1] for call in sent if call.args[0] == "Content-Security-Policy"]
    assert len(policies) == 1
    directives = [part.strip().split() for part in policies[0].split(";") if part.strip()]
    assert [parts[1:] for parts in directives if parts[0] == "form-action"] == [
        ["'self'", "https://chatgpt.com/connector_platform_oauth_redirect"]]
    handler.send_header.assert_any_call("Cache-Control", "no-store")
    if stage == "deny":
        location = next(call.args[1] for call in sent if call.args[0] == "Location")
        target = urlsplit(location)
        assert target._replace(query="").geturl() == "https://chatgpt.com/connector_platform_oauth_redirect"
        assert parse_qs(target.query)["error"] == ["access_denied"]
    local_only.assert_not_called()
