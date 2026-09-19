from unittest.mock import Mock

import pytest

from api.utils import gemini_cache as cache


@pytest.mark.parametrize("call_type", sorted(cache.RETIRED_REPORT_CALLS))
def test_retired_reports_never_create_cache_generate_or_record_usage(call_type, monkeypatch):
    client = Mock()
    make_cache = Mock(side_effect=AssertionError("cache must not be created"))
    monkeypatch.setattr(cache, "get_or_create_cache", make_cache)
    with pytest.raises(cache.ReportGenerationRetired):
        cache.generate_with_cache(client, model="unused", contents="input",
                                  system_instruction="system", call_type=call_type)
    assert client.mock_calls == []
    make_cache.assert_not_called()


def test_unrelated_fact_extraction_is_not_retired():
    cache.require_active_report_call("dart_litigation")
    cache.require_active_report_call(None)


def test_public_default_returns_explicit_disabled_state_without_cost(monkeypatch):
    from api.reports import daily_public as public
    monkeypatch.setattr(public, "_log_brain_learning_safe", lambda _: None)
    charge = Mock(side_effect=AssertionError("no attempted call to charge"))
    caller = Mock(side_effect=AssertionError("no provider call"))
    monkeypatch.setattr(public, "_log_llm_cost_safe", charge)
    monkeypatch.setattr(public, "_default_gemini_caller", caller)
    generate = getattr(public.generate_daily_public_text, "__wrapped__", public.generate_daily_public_text)
    result = generate({})
    assert result["metadata"]["status"] == "disabled_by_policy"
    assert result["sections"]["verity_judgment"] == {}
    charge.assert_not_called()
    caller.assert_not_called()


def test_private_public_caller_cannot_bypass_policy():
    from api.reports.daily_public import _default_gemini_caller
    with pytest.raises(cache.ReportGenerationRetired):
        _default_gemini_caller("test")
