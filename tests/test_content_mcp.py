"""Protocol/auth checks independent of any network, platform login or paid model."""
import importlib.util
import json
from pathlib import Path
import sys
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "vercel-api"))
import content_mcp as m
import content_oauth as oauth

HEADERS = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}


def call(method="tools/list", params=None, *, headers=None, authorize=None, feed=None):
    msg = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params is not None:
        msg["params"] = params
    return m.process_request("POST", headers or HEADERS, json.dumps(msg).encode(),
                             authorize_fn=authorize or (lambda h: None),
                             feed_fn=feed or (lambda: {"items": []}))


def test_closed_by_default_before_source(monkeypatch):
    monkeypatch.delenv("CONTENT_MCP_ENABLED", raising=False)
    feed = Mock()
    with pytest.raises(m.ServiceError) as error:
        call("tools/call", {"name": "search_content_candidates"}, authorize=m.authorize, feed=feed)
    assert error.value.status == 503
    feed.assert_not_called()


def test_initialize_and_readonly_inventory():
    status, body = call("initialize", {"protocolVersion": "2025-06-18"})
    assert status == 200
    assert body["result"]["protocolVersion"] == "2025-06-18"
    status, body = call()
    tools = body["result"]["tools"]
    assert {t["name"] for t in tools} == {"search_content_candidates", "get_content_evidence"}
    assert all(t["annotations"]["readOnlyHint"] for t in tools)
    assert all(not t["annotations"]["destructiveHint"] for t in tools)
    assert all(t["securitySchemes"] == [{"type": "oauth2", "scopes": ["content:read"]}] for t in tools)


def test_initialize_negotiates_supported_version():
    assert call("initialize", {"protocolVersion": "2099-01-01"})[1]["result"]["protocolVersion"] == m.VERSIONS[0]


def test_notifications_and_no_sse():
    kwargs = {"authorize_fn": lambda h: None}
    assert m.process_request("POST", HEADERS, b'{"jsonrpc":"2.0","method":"notifications/initialized"}', **kwargs) == (202, None)
    assert m.process_request("GET", {}, b"", **kwargs)[0] == 405


@pytest.mark.parametrize("headers,expected", [
    ({**HEADERS, "Origin": "https://evil.example"}, 403),
    ({**HEADERS, "Origin": "null"}, 403),
    ({**HEADERS, "Content-Type": "text/plain"}, 415),
    ({**HEADERS, "Accept": "application/json"}, 406),
    ({**HEADERS, "MCP-Protocol-Version": "invalid"}, 400),
])
def test_header_rejections(headers, expected):
    with pytest.raises(m.ServiceError) as error:
        call(headers=headers)
    assert error.value.status == expected


@pytest.mark.parametrize("args", [{"limit": True}, {"limit": 11}, {"days": 0},
    {"url": "https://evil.example"}, {"ticker": "ABC"}, {"topic": "a" * 81},
    {"topic": ""}, {"topic": " "}, {"topic": "a\nb"}])
def test_invalid_args_do_not_fetch(args):
    feed = Mock()
    _, body = call("tools/call", {"name": "search_content_candidates", "arguments": args}, feed=feed)
    assert body["error"]["code"] == -32602
    feed.assert_not_called()


def test_unknown_methods_and_tools():
    assert call("delete_everything")[1]["error"]["code"] == -32601
    feed = Mock()
    assert call("tools/call", {"name": "post_instagram"}, feed=feed)[1]["error"]["code"] == -32602
    feed.assert_not_called()
    assert call("tools/call", {"name": {"bad": "type"}}, feed=feed)[1]["error"]["code"] == -32602


@pytest.mark.parametrize("raw,code", [(b"not json", -32700), (b"[]", -32600),
    (b'{"jsonrpc":"2.0","id":true,"method":"ping"}', -32600)])
def test_invalid_jsonrpc(raw, code):
    status, body = m.process_request("POST", HEADERS, raw, authorize_fn=lambda h: None)
    assert status == 400 and body["error"]["code"] == code


def test_oversize_body():
    with pytest.raises(m.ServiceError) as error:
        m.process_request("POST", HEADERS, b"x" * (m.MAX_BODY + 1), authorize_fn=lambda h: None)
    assert error.value.status == 413


def enable(monkeypatch):
    monkeypatch.setenv("CONTENT_MCP_ENABLED", "1")
    monkeypatch.setenv("CONTENT_MCP_ORIGIN", "https://content.example")
    monkeypatch.setenv("SUPABASE_URL", "https://testproject.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-secret")


def test_separate_token_and_atomic_access_check(monkeypatch):
    enable(monkeypatch)
    rpc = Mock(return_value={"status": "allowed"})
    monkeypatch.setattr(oauth, "_json_request", rpc)
    token = "ancontent_" + "A" * 43
    m.authorize({"authorization": "Bearer " + token})
    payload = json.loads(rpc.call_args.kwargs["data"])
    assert len(payload["p_token_hash"]) == 64
    assert token not in rpc.call_args.kwargs["data"].decode()
    with pytest.raises(m.ServiceError) as error:
        m.authorize({"authorization": "Bearer website-login-token"})
    assert error.value.status == 401
    assert rpc.call_count == 1


@pytest.mark.parametrize("reply,status", [({"status": "denied"}, 401),
    ({"status": "limited"}, 429), ({}, 401), ([], 503)])
def test_revocation_quota_and_invalid_rpc_fail_closed(monkeypatch, reply, status):
    enable(monkeypatch)
    monkeypatch.setattr(oauth, "_json_request", lambda *a, **k: reply)
    with pytest.raises(m.ServiceError) as error:
        m.authorize({"authorization": "Bearer ancontent_" + "A" * 43})
    assert error.value.status == status


def test_upstream_failure_is_tool_error_not_stale_success():
    feed = Mock(side_effect=m.ServiceError(503, "upstream_unavailable"))
    _, body = call("tools/call", {"name": "search_content_candidates"}, feed=feed)
    assert body["result"]["isError"] is True
    assert "structuredContent" not in body["result"]


def test_expired_cache_not_returned_when_fetch_fails(monkeypatch):
    monkeypatch.setattr(m, "_feed_cache", {"items": [{"old": True}]})
    monkeypatch.setattr(m, "_feed_deadline", 0)
    monkeypatch.setattr(m, "_json_request", Mock(side_effect=m.ServiceError(503, "unavailable")))
    with pytest.raises(m.ServiceError):
        m.load_feed()


def test_no_redirects():
    assert m._NoRedirect().redirect_request(None, None, 302, "", {}, "https://evil.example") is None


def test_entrypoint_has_private_no_store_and_no_auth_logging():
    spec = importlib.util.spec_from_file_location("content_http", ROOT / "vercel-api/api/content_mcp.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    from io import BytesIO
    from email.message import Message
    h = object.__new__(module.handler)
    h.headers = Message()
    h.headers["Content-Length"] = "0"
    h.command = "GET"
    h.rfile, h.wfile = BytesIO(), BytesIO()
    h.send_response, h.send_header, h.end_headers = Mock(), Mock(), Mock()
    h._handle()
    h.send_header.assert_any_call("Cache-Control", "private, no-store")
    assert b"connection_not_configured" in h.wfile.getvalue()


def test_unauthorized_http_advertises_resource_metadata(monkeypatch):
    enable(monkeypatch)
    spec = importlib.util.spec_from_file_location("content_http_challenge", ROOT / "vercel-api/api/content_mcp.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    from io import BytesIO
    from email.message import Message
    h = object.__new__(module.handler)
    h.headers, h.command = Message(), "POST"
    h.rfile, h.wfile = BytesIO(), BytesIO()
    h.send_response, h.send_header, h.end_headers = Mock(), Mock(), Mock()
    h._handle()
    h.send_response.assert_called_once_with(401)
    h.send_header.assert_any_call("WWW-Authenticate",
        'Bearer resource_metadata="https://content.example/.well-known/oauth-protected-resource/api/content_mcp", scope="content:read"')


def test_discovery_routes_preserve_deploy_guard():
    config = json.loads((ROOT / "vercel-api/vercel.json").read_text())
    routes = {r["source"]: r["destination"] for r in config["rewrites"]}
    assert routes["/.well-known/oauth-authorization-server/api/content_oauth"] == "/api/content_oauth?op=server"
    assert routes["/.well-known/oauth-protected-resource/api/content_mcp"] == "/api/content_oauth?op=resource"
    assert "git diff --quiet $B HEAD -- vercel-api/" in config["ignoreCommand"]
