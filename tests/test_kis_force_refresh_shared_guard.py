"""Cross-runner issuance guard: stale checkout must reuse shared truth.

Every HTTP call is mocked. No credentials, token cache, or live KIS endpoint
are read or written by this focused regression suite.
"""
import ast
from datetime import datetime, timedelta
from pathlib import Path
import textwrap
from unittest.mock import Mock

import pytest

from api.trading import kis_broker as kb


NOW = datetime(2026, 10, 14, 23, 30, tzinfo=kb.KST)


class _Clock(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW if tz else NOW.replace(tzinfo=None)


@pytest.fixture(autouse=True)
def _isolate_data_dir(monkeypatch):
    # Override the repo-wide collector-import fixture for broker-only tests.
    monkeypatch.setenv("KIS_SHARED_TOKEN", "1")
    monkeypatch.setenv("SUPABASE_URL", "https://example.invalid")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "fake-service-role")
    monkeypatch.setattr(kb, "datetime", _Clock)
    monkeypatch.setattr(kb.requests, "get", Mock(side_effect=AssertionError("unmocked GET")))
    monkeypatch.setattr(kb.requests, "post", Mock(side_effect=AssertionError("unmocked POST")))


@pytest.fixture
def broker(tmp_path):
    broker = kb.KISBroker.__new__(kb.KISBroker)
    broker.broker_slug = "operator"
    broker.app_key = "fake-app-key"
    broker.app_secret = "fake-app-secret"
    broker.base_url = "https://kis.example.invalid"
    broker._cache_only = False
    broker._token = None
    broker._token_expires = None
    broker._issued_date = ""
    broker._load_cached_token = Mock()
    broker._save_cached_token = Mock()
    broker._mark_issued_today = Mock()
    lock = tmp_path / ".kis_issued_date.txt"
    lock.write_text((NOW - timedelta(hours=25)).isoformat())
    broker._daily_lock_path = lambda: str(lock)
    return broker


def _shared_response(*, issued_at=None, expires_at=None):
    row = {
        "access_token": "existing-shared-token",
        "expires_at": expires_at or (NOW + timedelta(hours=23)).isoformat(),
        "issued_at": issued_at if issued_at is not None else (NOW - timedelta(hours=1)).isoformat(),
        "app_key_fp": kb._kis_app_key_fp("fake-app-key"),
    }
    response = Mock()
    response.json.return_value = [row]
    return response


@pytest.mark.parametrize("force_refresh", [False, True])
def test_recent_shared_token_overrides_stale_checkout(broker, monkeypatch, force_refresh):
    get = Mock(return_value=_shared_response())
    monkeypatch.setattr(kb.requests, "get", get)

    assert broker.authenticate(force_refresh=force_refresh) == "existing-shared-token"
    assert broker._last_auth_issued is False

    get.assert_called_once()
    kb.requests.post.assert_not_called()
    broker._mark_issued_today.assert_not_called()


def test_forced_refresh_cannot_issue_when_shared_store_unreachable(broker, monkeypatch):
    monkeypatch.setattr(kb.requests, "get", Mock(side_effect=kb.requests.Timeout("store unavailable")))

    with pytest.raises(RuntimeError):
        broker.authenticate(force_refresh=True)

    kb.requests.post.assert_not_called()
    broker._mark_issued_today.assert_not_called()


@pytest.mark.parametrize("issued_at", ["", "not-a-date", (NOW + timedelta(hours=1)).isoformat()])
def test_forced_refresh_unknown_or_future_issue_time_fails_closed(broker, monkeypatch, issued_at):
    monkeypatch.setattr(kb.requests, "get", Mock(return_value=_shared_response(issued_at=issued_at)))

    with pytest.raises(RuntimeError):
        broker.authenticate(force_refresh=True)

    kb.requests.post.assert_not_called()
    broker._mark_issued_today.assert_not_called()


@pytest.mark.parametrize("field,value", [
    ("access_token", ""), ("expires_at", ""),
    ("app_key_fp", ""), ("app_key_fp", "different-key-fingerprint"),
])
def test_forced_refresh_incomplete_or_mismatched_row_fails_closed(broker, monkeypatch, field, value):
    response = _shared_response()
    response.json.return_value[0][field] = value
    monkeypatch.setattr(kb.requests, "get", Mock(return_value=response))

    with pytest.raises(RuntimeError):
        broker.authenticate(force_refresh=True)

    kb.requests.post.assert_not_called()


def test_expired_shared_token_within_24h_blocks_second_issuance(broker, monkeypatch):
    response = _shared_response(
        issued_at=(NOW - timedelta(hours=20)).isoformat(),
        expires_at=(NOW - timedelta(minutes=1)).isoformat(),
    )
    monkeypatch.setattr(kb.requests, "get", Mock(return_value=response))

    with pytest.raises(RuntimeError):
        broker.authenticate(force_refresh=True)

    kb.requests.post.assert_not_called()


def test_expired_shared_token_after_24h_allows_mocked_issuance(broker, monkeypatch):
    get = Mock(return_value=_shared_response(
        issued_at=(NOW - timedelta(hours=25)).isoformat(),
        expires_at=(NOW - timedelta(hours=1)).isoformat(),
    ))
    response = Mock()
    response.json.return_value = {
        "access_token": "new-mocked-token",
        "access_token_token_expired": (NOW + timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S"),
    }
    post = Mock(return_value=response)
    publish = Mock()
    monkeypatch.setattr(kb.requests, "get", get)
    monkeypatch.setattr(kb.requests, "post", post)
    monkeypatch.setattr(kb, "_kis_publish_shared_token", publish)

    assert broker.authenticate(force_refresh=True) == "new-mocked-token"
    assert broker._last_auth_issued is True

    post.assert_called_once()
    assert post.call_args.args[0].endswith("/oauth2/tokenP")
    broker._mark_issued_today.assert_called_once()
    publish.assert_called_once()


@pytest.mark.parametrize("issued,changes_marker,raises", [
    (False, False, False), (True, True, False), (True, False, False),
    (True, False, True), (False, False, True),
])
def test_refresh_workflow_counts_issuance_even_if_persistence_failed(tmp_path, issued, changes_marker, raises):
    workflow = Path(__file__).parents[1] / ".github/workflows/kis_token_refresh.yml"
    python_body = workflow.read_text().split("python - <<'PYEOF'", 1)[1].split("PYEOF", 1)[0]
    tree = ast.parse(textwrap.dedent(python_body))
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "refresh_one")
    module = ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[]))
    lock = tmp_path / "daily_lock"
    lock.write_text("old-issuance-marker")
    fake = Mock()
    fake.is_configured = True
    fake._last_auth_issued = issued
    fake._is_recently_issued.return_value = False
    fake._daily_lock_path.return_value = str(lock)
    if raises:
        fake.authenticate.side_effect = RuntimeError("mocked authentication or persistence failure")
    elif changes_marker:
        fake.authenticate.side_effect = lambda **kwargs: lock.write_text("new-issuance-marker")
    else:
        fake.authenticate.return_value = "existing-token"
    namespace = {"KISBroker": Mock(return_value=fake)}
    exec(compile(module, str(workflow), "exec"), namespace)

    if raises and not issued:
        with pytest.raises(RuntimeError, match="mocked authentication"):
            namespace["refresh_one"]("operator")
    else:
        assert namespace["refresh_one"]("operator") is issued

    fake.authenticate.assert_called_once_with(force_refresh=True)
    kb.requests.get.assert_not_called()
    kb.requests.post.assert_not_called()
