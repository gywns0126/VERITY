"""The retired Google path must not retry or fall back to another Google model.

The former 503/429 retry contract was superseded by the user provider ban on
2026-10-25. Even a successful injected client must make zero calls now.
"""
from unittest.mock import Mock

import pytest

from api.utils import gemini_cache as cache
from api.utils.google_provider_policy import GoogleProviderDisabled


@pytest.mark.parametrize("provider_error", [None, "503 UNAVAILABLE", "429 RESOURCE_EXHAUSTED", "400 INVALID_ARGUMENT"])
def test_retired_google_never_attempts_success_retry_or_fallback(provider_error, monkeypatch):
    client = Mock()
    if provider_error:
        client.models.generate_content.side_effect = RuntimeError(provider_error)
    sleep = Mock(side_effect=AssertionError("retired provider must not retry"))
    create = Mock(side_effect=AssertionError("retired provider must not create cache"))
    monkeypatch.setattr(cache.time, "sleep", sleep)
    monkeypatch.setattr(cache, "get_or_create_cache", create)
    monkeypatch.setenv("GEMINI_API_KEY", "dummy-never-sent")
    monkeypatch.setenv("GEMINI_MODEL_CHAT", "gemini-2.5-flash-lite")
    with pytest.raises(GoogleProviderDisabled):
        cache.generate_with_cache(client, model="gemini-2.5-flash", contents="x",
                                  system_instruction="s", call_type="fact-extraction")
    assert client.mock_calls == []
    sleep.assert_not_called()
    create.assert_not_called()
