"""Claude registration regressions; fake DB replies, no production credentials."""
import pytest
from tests.test_content_oauth import (
    m, authorization, token_form, refresh_form, post, consent, assert_error,
    local_only, clock, ORIGIN, INVITE, CHATGPT, PERPLEXITY, CHALLENGE,
)

CLAUDE = "alphanest-content-claude"
CALLBACKS = [
    "https://claude.ai/api/mcp/auth_callback",
    "https://claude.com/api/mcp/auth_callback",
    "http://localhost:8765/callback",
    "http://127.0.0.1:8765/callback",
    "http://localhost:1/callback",
    "http://127.0.0.1:65535/callback",
]


@pytest.mark.parametrize("uri", CALLBACKS)
def test_claude_consent_and_exchange(clock, local_only, uri):
    params = authorization(client_id=CLAUDE, redirect_uri=uri)
    signed, cookie, _ = consent(params)
    local_only.side_effect = None
    local_only.return_value = {"status": "allowed"}
    status, _, headers = post("authorize", {"consent": signed, "invite": INVITE, "decision": "allow"},
                              {"Origin": ORIGIN, "Cookie": cookie})
    assert status == 303 and headers["Location"].startswith(uri + "?")
    assert local_only.call_args.args[1]["p_redirect_uri"] == uri
    local_only.return_value = {"status": "allowed", "expires_in": 3600, "refresh_expires_in": 2592000}
    assert post("token", token_form(client_id=CLAUDE, redirect_uri=uri))[0] == 200
    # Full URI including port is sent unchanged for exact database binding.
    assert local_only.call_args.args[1]["p_redirect_uri"] == uri
    assert local_only.call_args.args[1]["p_code_challenge"] == CHALLENGE


@pytest.mark.parametrize("uri", [
    "http://localhost/callback", "http://localhost:0/callback", "http://localhost:65536/callback",
    "http://localhost:08765/callback", "http://localhost:+8765/callback",
    "http://localhost:8765/callback/", "http://localhost:8765/callback?x=1",
    "http://localhost:8765/callback#x", "http://localhost:8765/callback\n",
    "http://localhost.evil.test:8765/callback", "http://localhost@evil.test:8765/callback",
    "http://evil.test@localhost:8765/callback", "http://127.0.0.2:8765/callback",
    "http://0.0.0.0:8765/callback", "http://127.1:8765/callback",
    "https://localhost:8765/callback", "http://localhost:8765/%63allback",
    "https://claude.ai/api/mcp/auth_callback?x=1", "https://claude.ai.evil.test/api/mcp/auth_callback",
    "https://claude.com/api/mcp/auth_callback/", "https://chatgpt.com/connector_platform_oauth_redirect",
])
def test_claude_invalid_callbacks_fail_before_rpc(local_only, uri):
    assert_error(400, "invalid_authorization_request", m.validated_authorization,
                 authorization(client_id=CLAUDE, redirect_uri=uri), m.config())
    assert_error(400, "invalid_grant", post, "token", token_form(client_id=CLAUDE, redirect_uri=uri))
    local_only.assert_not_called()


@pytest.mark.parametrize("client", [CHATGPT, PERPLEXITY])
@pytest.mark.parametrize("uri", CALLBACKS)
def test_other_clients_cannot_use_claude_callbacks(local_only, client, uri):
    assert not m.valid_redirect(client, uri)
    assert_error(400, "invalid_grant", post, "token", token_form(client_id=client, redirect_uri=uri))
    local_only.assert_not_called()


@pytest.mark.parametrize("origin", [None, "https://claude.ai", "https://claude.com"])
def test_claude_refresh_binding(local_only, origin):
    local_only.side_effect = None
    local_only.return_value = {"status": "allowed", "expires_in": 60, "refresh_expires_in": 120}
    status, body, _ = post("token", refresh_form(client_id=CLAUDE), {"Origin": origin} if origin else {})
    assert status == 200 and body["refresh_expires_in"] == 120
    assert local_only.call_args.args[0] == "content_mcp_rotate_refresh"
    assert local_only.call_args.args[1]["p_client_id"] == CLAUDE


def test_claude_display_and_expiry(clock, local_only):
    from urllib.parse import urlencode
    _, page, _ = m.process("GET", "/api/content_oauth?" + urlencode({
        "op": "authorize", **authorization(client_id=CLAUDE, redirect_uri=CALLBACKS[0])}), {}, b"")
    assert "Claude에" in page and "ChatGPT에" not in page
    assert "만료일은 연장되지 않습니다" in page
    assert "다시 승인해야 합니다" in page
    local_only.assert_not_called()


@pytest.mark.parametrize("changes", [
    {"code_challenge_method": "plain"}, {"code_challenge": "short"},
    {"scope": "content:write"}, {"resource": "https://evil.test/api/content_mcp"},
    {"state": ""}, {"response_type": "token"},
])
def test_claude_does_not_relax_pkce_resource_scope(local_only, changes):
    assert_error(400, "invalid_authorization_request", m.validated_authorization,
                 authorization(client_id=CLAUDE, redirect_uri=CALLBACKS[0], **changes), m.config())
    local_only.assert_not_called()


@pytest.mark.parametrize("origin", ["null", "https://claude.ai.evil.test", "https://chatgpt.com", "http://localhost:8765"])
def test_claude_untrusted_token_origin(local_only, origin):
    assert_error(400, "invalid_grant", post, "token", refresh_form(client_id=CLAUDE), {"Origin": origin})
    local_only.assert_not_called()
