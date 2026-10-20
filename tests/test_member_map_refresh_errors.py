"""Storage errors retain actionable codes, never server bodies or credentials."""
from pathlib import Path

import pytest

from api.collectors import member_map_refresh_store as storage


@pytest.mark.parametrize("status,code", [
    (401, "refresh-auth-rejected"), (403, "refresh-auth-rejected"),
    (429, "refresh-http-rate-limited"),
    (500, "refresh-http-unavailable"), (503, "refresh-http-unavailable"),
    (400, "refresh-http-failure"), (302, "refresh-http-failure"),
])
def test_http_error_does_not_read_body(status, code):
    class ErrorResponse:
        status_code = status

        @property
        def headers(self):
            pytest.fail("Error response headers/body must not be read")

    with pytest.raises(storage.RefreshStoreError) as raised:
        storage._read_json_response(ErrorResponse(), 1000, 0)
    assert storage.safe_error_code(raised.value) == code


@pytest.mark.parametrize("error,expected", [
    (storage.RefreshStoreError("refresh-http-unavailable"), "refresh-http-unavailable"),
    (storage.RefreshStoreError("refresh-state-rejected"), "refresh-state-rejected"),
    (storage.RefreshStoreError("private-credential"), "refresh-read-rejected"),
    (RuntimeError("private-credential"), "refresh-read-rejected"),
])
def test_read_propagates_only_safe_cause_without_retry_or_cache_mutation(monkeypatch, error, expected):
    calls = []

    def failed(*args, **kwargs):
        calls.append(1)
        raise error

    monkeypatch.setattr(storage, "_request_json", failed)
    store = storage.RefreshStore("synthetic-role")
    store._states = {"DART": {"last_success_at": "2026-10-20T00:00:00Z"}}
    store._state_revisions = {"DART": 7}
    with pytest.raises(storage.RefreshStoreError) as raised:
        store.read_states()
    assert str(raised.value) == expected
    assert calls == [1]
    assert store._state_revisions == {"DART": 7}
    assert store._states == {"DART": {"last_success_at": "2026-10-20T00:00:00Z"}}


def test_timeout_classified_without_credentials_or_request_retry(monkeypatch):
    calls = []

    class Session:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def request(self, *args, **kwargs):
            calls.append(1)
            raise storage.requests.exceptions.ReadTimeout("credential must not escape")

    monkeypatch.setattr(storage.requests, "Session", Session)
    with pytest.raises(storage.RefreshStoreError) as raised:
        storage._request_json("GET", storage.PROJECT_URL, headers={})
    assert storage.safe_error_code(raised.value) == "refresh-transport-timeout"
    assert calls == [1]


def test_error_vocabulary_and_api_mirror():
    for value in ("private-credential", None, [], 503):
        assert storage.safe_error_code(storage.RefreshStoreError(value)) == "refresh-unexpected-error"
    assert storage.safe_error_code(ValueError("refresh-http-unavailable")) == "refresh-unexpected-error"
    root = Path(__file__).resolve().parents[1]
    assert (root / "api/collectors/member_map_refresh_store.py").read_bytes() == (
        root / "vercel-api/api/portfolio_core/member_map_refresh_store.py").read_bytes()
