"""Private diagnostic baseline never becomes an analysis/scoring input."""
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from api.utils.analysis_baseline import load_previous_analysis_baseline


def test_private_completed_baseline_is_separate_and_exact_fixed_path(monkeypatch):
    from api.intelligence import ticker_facts
    local = {"recommendations": [{"ticker": "A", "currency": "USD", "price": 1}]}
    original = deepcopy(local)
    private = {"recommendations": [{"ticker": "A", "currency": "USD", "price": 2}],
               "analysis_provenance": {"status": "completed", "analysis_run_id": "old"}}
    paths = []
    monkeypatch.setattr(ticker_facts, "_private_json", lambda path: paths.append(path) or private)
    result = load_previous_analysis_baseline(local)
    assert paths == ["_operator/portfolio_full.json"]
    assert result["baseline_source"] == "private_storage"
    assert result["recommendations"][0]["price"] == 2
    result["recommendations"][0]["price"] = 3
    assert private["recommendations"][0]["price"] == 2
    assert local == original


@pytest.mark.parametrize("response", [None, {}, [], {"recommendations": [], "analysis_provenance": {"status": "started"}},
                                       {"recommendations": [1], "analysis_provenance": {"status": "completed"}}])
def test_unavailable_or_invalid_private_baseline_uses_labeled_legacy_only(monkeypatch, response):
    from api.intelligence import ticker_facts
    monkeypatch.setattr(ticker_facts, "_private_json", lambda path: response)
    local = {"recommendations": [{"ticker": "A", "currency": "USD", "price": 1}]}
    result = load_previous_analysis_baseline(local)
    assert result["baseline_source"] == "legacy_local"
    assert result["baseline_reason"]
    assert result["recommendations"] == local["recommendations"]


def test_auth_failure_has_no_response_text_logging_and_current_run_rejected(monkeypatch, capsys):
    from api.intelligence import ticker_facts
    def fail(path):
        raise PermissionError("private-secret-fixture")
    monkeypatch.setattr(ticker_facts, "_private_json", fail)
    assert load_previous_analysis_baseline({})["baseline_reason"] == "private_baseline_unavailable"
    assert "private-secret-fixture" not in str(capsys.readouterr())
    monkeypatch.setenv("GITHUB_RUN_ID", "1")
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "2")
    monkeypatch.setattr(ticker_facts, "_private_json", lambda path: {
        "recommendations": [], "analysis_provenance": {"status": "completed", "analysis_run_id": "1", "analysis_run_attempt": "2"}})
    assert load_previous_analysis_baseline({})["baseline_reason"] == "private_baseline_is_current_run"


def test_actual_private_reader_authorized_get_and_context_restored(monkeypatch):
    from api.intelligence import ticker_facts
    monkeypatch.setenv("SUPABASE_URL", "https://private-fixture.example")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role-fixture")
    monkeypatch.delenv("OPERATOR_BUCKET", raising=False)
    private = {"recommendations": [], "analysis_provenance": {"status": "completed"}}
    calls = []
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self): return json.dumps(private).encode()
    def open_request(request, timeout):
        calls.append((request.full_url, request.get_method(), dict(request.header_items())))
        return Response()
    def build_opener(*handlers):
        assert any(isinstance(h, ticker_facts._PrivateNoRedirect) for h in handlers)
        return SimpleNamespace(open=open_request)
    monkeypatch.setattr(ticker_facts.urllib.request, "build_opener", build_opener)
    private_token = ticker_facts._INCLUDE_PRIVATE.set(True)
    original_memo = {"_operator/portfolio_full.json": {"stale": True}}
    memo_token = ticker_facts._PRIVATE_DOCS.set(original_memo)
    try:
        baseline = load_previous_analysis_baseline({})
        assert baseline["baseline_source"] == "private_storage"
        assert len(calls) == 1
        assert calls[0][:2] == ("https://private-fixture.example/storage/v1/object/verity-reports/_operator/portfolio_full.json", "GET")
        assert calls[0][2]["Apikey"] == "service-role-fixture"
        assert calls[0][2]["Authorization"] == "Bearer service-role-fixture"
        assert calls[0][2]["Cache-control"] == "no-cache"
        assert ticker_facts._INCLUDE_PRIVATE.get() is True
        assert ticker_facts._PRIVATE_DOCS.get() is original_memo
    finally:
        ticker_facts._PRIVATE_DOCS.reset(memo_token)
        ticker_facts._INCLUDE_PRIVATE.reset(private_token)


def test_explicit_private_disabled_context_is_respected_without_transport(monkeypatch):
    from api.intelligence import ticker_facts
    monkeypatch.setattr(ticker_facts.urllib.request, "urlopen", lambda *a, **k: pytest.fail("private context disabled"))
    monkeypatch.setattr(ticker_facts.urllib.request, "build_opener", lambda *a, **k: pytest.fail("private context disabled"))
    token = ticker_facts._INCLUDE_PRIVATE.set(False)
    try:
        assert load_previous_analysis_baseline({})["baseline_source"] == "legacy_local"
        assert ticker_facts._INCLUDE_PRIVATE.get() is False
    finally:
        ticker_facts._INCLUDE_PRIVATE.reset(token)


def test_wrong_bucket_never_calls_private_reader(monkeypatch):
    from api.intelligence import ticker_facts
    monkeypatch.setenv("OPERATOR_BUCKET", "public-fixture")
    monkeypatch.setattr(ticker_facts, "_private_json", lambda path: pytest.fail("wrong-bucket request"))
    assert load_previous_analysis_baseline({})["baseline_reason"] == "private_bucket_identity_mismatch"
