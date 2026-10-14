"""Backend watch collection preserves the private console ownership boundary."""
from unittest.mock import Mock

import pytest

from api.collectors.operator_watchlist import fetch_operator_watch_items


OWNER = "11111111-1111-4111-8111-111111111111"
GROUP = "22222222-2222-4222-8222-222222222222"
OTHER = "33333333-3333-4333-8333-333333333333"


def configure(monkeypatch, rows, statuses=None, key="legacy-service-key"):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", key)
    monkeypatch.setenv("SUPABASE_ANON_KEY", "not-the-backend-key")
    session = Mock()
    session.__enter__ = Mock(return_value=session)
    session.__exit__ = Mock(return_value=False)
    statuses = statuses or [200] * len(rows)
    session.get.side_effect = [Mock(status_code=status, json=Mock(return_value=row))
                               for row, status in zip(rows, statuses)]
    monkeypatch.setattr("api.collectors.operator_watchlist.requests.Session", lambda: session)
    return session


def valid_rows():
    return [
        [{"id": OWNER, "is_admin": True, "is_super_admin": True}],
        [{"id": GROUP, "user_id": OWNER}],
        [{"group_id": GROUP, "ticker": "TEST", "name": "Test", "market": "us"}],
    ]


@pytest.mark.parametrize("key", ["legacy-service-key", "sb_secret_test-only"])
def test_only_verified_owner_groups_are_requested_and_private_fields_removed(monkeypatch, key):
    session = configure(monkeypatch, valid_rows(), key=key)
    assert fetch_operator_watch_items() == [{"ticker": "TEST", "name": "Test", "market": "us"}]
    calls = session.get.call_args_list
    assert calls[0].kwargs["params"]["is_admin"] == "eq.true"
    assert calls[0].kwargs["params"]["is_super_admin"] == "eq.true"
    assert calls[1].kwargs["params"]["user_id"] == f"eq.{OWNER}"
    assert calls[2].kwargs["params"]["group_id"] == f"in.({GROUP})"
    for call in calls:
        assert call.kwargs["allow_redirects"] is False
        assert call.kwargs["headers"]["apikey"] == key
        assert ("Authorization" in call.kwargs["headers"]) == (not key.startswith("sb_secret_"))


@pytest.mark.parametrize("owners", [[], [{"id": OWNER, "is_admin": True, "is_super_admin": False}],
                                      valid_rows()[0] * 2])
def test_unresolved_or_non_owner_profile_stops_before_group_query(monkeypatch, owners):
    session = configure(monkeypatch, [owners])
    assert fetch_operator_watch_items() == []
    assert session.get.call_count == 1


@pytest.mark.parametrize("stage", [1, 2])
def test_response_from_another_owner_is_rejected(monkeypatch, stage):
    rows = valid_rows()
    rows[stage][0]["user_id" if stage == 1 else "group_id"] = OTHER
    session = configure(monkeypatch, rows)
    assert fetch_operator_watch_items() == []
    assert session.get.call_count == stage + 1


def test_auth_failure_is_sanitized_and_does_not_fall_back_to_anon(monkeypatch, caplog):
    session = configure(monkeypatch, [{"message": "private-upstream-body"}], statuses=[401])
    assert fetch_operator_watch_items() == []
    assert session.get.call_count == 1
    assert "status=401" in caplog.text
    assert "private-upstream-body" not in caplog.text
    assert "legacy-service-key" not in caplog.text


def test_missing_backend_key_does_not_query(monkeypatch):
    session = configure(monkeypatch, [])
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY")
    assert fetch_operator_watch_items() == []
    session.get.assert_not_called()


def test_existing_item_cap_is_explicit_when_saturated(monkeypatch, caplog):
    rows = valid_rows()
    rows[2] *= 201
    configure(monkeypatch, rows)
    assert len(fetch_operator_watch_items()) == 200
    assert "selected=200 available_at_least=201" in caplog.text
