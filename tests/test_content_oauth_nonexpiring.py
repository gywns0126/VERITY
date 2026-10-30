"""Revocable indefinite Claude refresh responses; fake RPC, no credentials."""
import pytest
from urllib.parse import urlencode
from tests.test_content_oauth import (
    m, local_only, token_form, refresh_form, post, authorization, assert_error,
)


@pytest.mark.parametrize("grant", ["authorization_code", "refresh_token"])
def test_indefinite_claude_has_short_access_and_no_refresh_deadline(local_only, grant):
    local_only.side_effect = None
    local_only.return_value = {"status": "allowed", "expires_in": 3600,
                              "refresh_expires_in": None, "refresh_non_expiring": True}
    form = (refresh_form(client_id=m.CLAUDE_ID) if grant == "refresh_token" else
            token_form(client_id=m.CLAUDE_ID, redirect_uri=m.CLAUDE_REDIRECTS[0]))
    status, body, _ = post("token", form)
    assert status == 200
    assert set(body) == {"access_token", "token_type", "expires_in", "scope", "refresh_token"}
    assert body["expires_in"] == 3600 and body["scope"] == "content:read"


@pytest.mark.parametrize("client", list(m.CLIENTS))
@pytest.mark.parametrize("changes", [
    {"refresh_non_expiring": False}, {"refresh_non_expiring": 1},
    {"refresh_non_expiring": "true"}, {"refresh_non_expiring": None},
    {"refresh_expires_in": 31536000}, {"expires_in": 3601},
    {"expires_in": True}, {"expires_in": 0}, {"status": "denied"},
])
def test_indefinite_contract_fails_closed(local_only, client, changes):
    local_only.side_effect = None
    local_only.return_value = {"status": "allowed", "expires_in": 3600,
                              "refresh_expires_in": None, "refresh_non_expiring": True, **changes}
    assert_error(400, "invalid_grant", post, "token", refresh_form(client_id=client))


@pytest.mark.parametrize("client", [m.CLIENT_ID, "alphanest-content-perplexity"])
def test_other_clients_cannot_accept_indefinite_rpc_result(local_only, client):
    local_only.side_effect = None
    local_only.return_value = {"status": "allowed", "expires_in": 3600,
                              "refresh_expires_in": None, "refresh_non_expiring": True}
    assert_error(400, "invalid_grant", post, "token", refresh_form(client_id=client))


def test_missing_lifetime_is_not_inferred_as_indefinite(local_only):
    local_only.side_effect = None
    for result in ({"status": "allowed", "expires_in": 3600},
                   {"status": "allowed", "expires_in": 3600, "refresh_non_expiring": True}):
        local_only.return_value = result
        assert_error(400, "invalid_grant", post, "token", refresh_form(client_id=m.CLAUDE_ID))


@pytest.mark.parametrize("client", list(m.CLIENTS))
def test_consent_indefinite_option_is_only_for_claude(local_only, client):
    params = authorization(client_id=client, redirect_uri=m.CLIENTS[client]["redirect_uri"])
    status, page, _ = m.process("GET", "/api/content_oauth?" +
                              urlencode({"op": "authorize", **params}), {}, b"")
    assert status == 200
    assert ("직접 취소할 때까지 유지됩니다" in page) == (client == m.CLAUDE_ID)
    assert "최대 1시간" in page and "기존 연결의 만료일은 유지" in page
    local_only.assert_not_called()
