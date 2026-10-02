"""Annual OAuth response boundaries; mocked RPC, not deployed DB proof."""
import pytest
from urllib.parse import urlencode
from tests.test_content_oauth import (m, local_only, token_form, refresh_form, post,
                                authorization, assert_error)


@pytest.mark.parametrize("client", list(m.CLIENTS))
@pytest.mark.parametrize("grant", ["authorization_code", "refresh_token"])
@pytest.mark.parametrize("lifetime,allowed", [
    (2592000, True), (2592001, True), (31535999, True), (31536000, True),
    (31536001, False), (None, False), (True, False), ("31536000", False),
])
def test_annual_boundary(local_only, client, grant, lifetime, allowed):
    local_only.side_effect = None
    local_only.return_value = {"status": "allowed", "expires_in": 3600,
                              "refresh_expires_in": lifetime}
    form = (refresh_form(client_id=client) if grant == "refresh_token" else
            token_form(client_id=client, redirect_uri=m.CLIENTS[client]["redirect_uri"]))
    if allowed:
        status, body, _ = post("token", form)
        assert status == 200
        assert body["expires_in"] == 3600
        assert body["refresh_expires_in"] == lifetime
    else:
        assert_error(400, "invalid_grant", post, "token", form)


@pytest.mark.parametrize("client", list(m.CLIENTS))
def test_annual_consent_explains_absolute_expiry(local_only, client):
    params = authorization(client_id=client, redirect_uri=m.CLIENTS[client]["redirect_uri"])
    status, page, _ = m.process("GET", "/api/content_oauth?" +
                              urlencode({"op": "authorize", **params}), {}, b"")
    assert status == 200
    for text in ("365일", "최대 1시간", "연장되지 않습니다", "초대코드 만료·취소",
                 "기존 연결의 만료일은 유지"):
        assert text in page
    local_only.assert_not_called()
