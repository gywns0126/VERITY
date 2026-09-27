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


def call(method="tools/list", params=None, *, headers=None, authorize=None, feed=None, original=None,
         company=None, public=None):
    msg = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params is not None:
        msg["params"] = params
    return m.process_request("POST", headers or HEADERS, json.dumps(msg).encode(),
                             authorize_fn=authorize or (lambda h: None),
                             feed_fn=feed or (lambda: {"items": []}),
                             original_fn=original or (lambda receipt: {"original_status": "unavailable"}),
                             company_fn=company or (lambda ticker: {"ticker": ticker}),
                             public_fn=public or (lambda source: {"source": source}))


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
    assert {t["name"] for t in tools} == {"search_content_candidates", "get_content_evidence",
                                         "get_company_content_evidence", "get_public_content"}
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


def example_feed():
    return {"items": [{"ticker": "083650", "name": "예시 기업", "disclosures": [{
        "title": "[정정]단일판매ㆍ공급계약체결", "date": "2026-09-23",
        "is_correction": True,
        "source_url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260923900749",
    }]}]}


def test_original_only_after_auth_and_exact_feed_membership():
    original = Mock()
    for args in ({"id": "20260923999999"}, {"id": "https://evil.example"}):
        call("tools/call", {"name": "get_content_evidence", "arguments": args},
             feed=example_feed, original=original)
    call("tools/call", {"name": "search_content_candidates"}, feed=example_feed, original=original)
    original.assert_not_called()
    with pytest.raises(m.ServiceError):
        call("tools/call", {"name": "get_content_evidence", "arguments": {"id": "20260923900749"}},
             authorize=Mock(side_effect=m.ServiceError(401, "denied")), feed=example_feed, original=original)
    original.assert_not_called()


def test_original_provenance_is_not_market_freshness_or_latest_revision():
    original = Mock(return_value={"receipt_id": "20260923900749", "original_status": "available",
        "source_checked_at": "2026-09-27T03:00:00+00:00", "excerpt": "계약금액 변경"})
    _, response = call("tools/call", {"name": "get_content_evidence", "arguments": {"id": "20260923900749"}},
                       feed=example_feed, original=original)
    evidence = response["result"]["structuredContent"]
    item = evidence["items"][0]
    original.assert_called_once_with("20260923900749")
    assert item["original_document"]["excerpt"] == "계약금액 변경"
    for row in (item, evidence):
        assert row["source_checked_at"] == original.return_value["source_checked_at"]
        assert row["evidence_basis"] == "original_excerpt_and_title"
        assert row["freshness_status"] == "unknown"
        assert row["latest_revision_verified"] is False
        assert row["breaking_eligible"] is False


@pytest.mark.parametrize("status", ["unavailable", "unsupported"])
def test_original_failure_preserves_explicit_title_only_fallback(status):
    _, response = call("tools/call", {"name": "get_content_evidence", "arguments": {"id": "20260923900749"}},
                       feed=example_feed, original=lambda receipt: {"original_status": status})
    evidence = response["result"]["structuredContent"]
    assert evidence["evidence_basis"] == "title_only"
    assert evidence["source_checked_at"] is None
    assert evidence["items"][0]["original_document"]["original_status"] == status


@pytest.mark.parametrize("name,args", [
    ("get_company_content_evidence", {"ticker": "005930"}),
    ("get_company_content_evidence", {"ticker": "BRK.B"}),
    ("get_public_content", {"source": "news"}),
    ("get_public_content", {"source": "briefing"}),
])
def test_public_routes_are_authenticated_without_disclosure_fetch(name, args):
    feed, original, company, public = Mock(), Mock(), Mock(return_value={"ok": 1}), Mock(return_value={"ok": 1})
    _, response = call("tools/call", {"name": name, "arguments": args}, feed=feed,
                       original=original, company=company, public=public)
    assert response["result"]["structuredContent"] == {"ok": 1}
    (company if "ticker" in args else public).assert_called_once_with(next(iter(args.values())))
    feed.assert_not_called()
    original.assert_not_called()
    company.reset_mock(); public.reset_mock()
    with pytest.raises(m.ServiceError):
        call("tools/call", {"name": name, "arguments": args}, company=company, public=public,
             authorize=Mock(side_effect=m.ServiceError(401, "denied")))
    company.assert_not_called(); public.assert_not_called()


@pytest.mark.parametrize("name,args", [
    ("get_company_content_evidence", {}),
    ("get_company_content_evidence", {"ticker": "../../secret"}),
    ("get_company_content_evidence", {"ticker": "aapl"}),
    ("get_company_content_evidence", {"ticker": "005930", "url": "https://evil.test"}),
    ("get_public_content", {"source": "portfolio"}),
    ("get_public_content", {"source": []}),
    ("get_public_content", {"source": "news", "user_id": "x"}),
])
def test_public_route_arguments_fail_before_fetch(name, args):
    company, public = Mock(), Mock()
    _, result = call("tools/call", {"name": name, "arguments": args}, company=company, public=public)
    assert result["error"]["code"] == -32602
    company.assert_not_called(); public.assert_not_called()


def test_public_source_failure_is_tool_error_without_payload_or_stale_data():
    _, response = call("tools/call", {"name": "get_public_content", "arguments": {"source": "news"}},
                       public=Mock(side_effect=m.PublicSourceError("sensitive upstream detail")))
    assert response["result"]["isError"] is True
    assert "structuredContent" not in response["result"]
    assert "sensitive" not in json.dumps(response)
