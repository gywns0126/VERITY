"""Web adapter contract: synthetic facts only; no auth/provider/network calls."""
import importlib.util
import io
import json
from pathlib import Path
import sys
import types
from unittest.mock import Mock

import pytest


@pytest.fixture
def endpoint(monkeypatch):
    for name in ("SUPABASE_URL", "SUPABASE_ANON_KEY", "ADMIN_BYPASS_TOKEN"):
        monkeypatch.setenv(name, "")
    monkeypatch.setattr(sys, "path", list(sys.path))
    path = Path(__file__).resolve().parents[1] / "vercel-api/api/operator_ask.py"
    spec = importlib.util.spec_from_file_location("operator_web_endpoint", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module.requests, "get", Mock(side_effect=AssertionError("network forbidden")))
    return module


def request(endpoint, path, method="GET"):
    handler = object.__new__(endpoint.handler)
    handler.path = path
    handler.headers = {}
    handler.wfile = io.BytesIO()
    handler.send_response = Mock()
    handler.send_header = Mock()
    handler.end_headers = Mock()
    getattr(handler, "do_" + method)()
    return handler.send_response.call_args.args[0], json.loads(handler.wfile.getvalue())


def install_core(monkeypatch, endpoint, facts):
    core = types.ModuleType("operator_core")
    ask = Mock(return_value={"facts": facts, "facts_text": "fixture facts", "_meta": {
        "contract": "operator-facts-v2", "llm_calls": 0, "legacy_chain_retired": True,
    }})
    core.operator_ask = types.SimpleNamespace(ask=ask)
    monkeypatch.setitem(sys.modules, "operator_core", core)
    monkeypatch.setattr(endpoint, "_authorize", lambda _: (True, "fixture"))
    return ask


@pytest.mark.parametrize("status,ticker,count", [
    ("ready", "JEPQ", 1), ("partial", "JEPQ", 2),
    ("empty", "JEPQ", 0), ("unresolved", None, 0),
])
def test_status_coverage_diagnostics_survive_http(endpoint, monkeypatch, status, ticker, count):
    coverage = {"total": 4, "applicable": 3, "checked": 3, "hit": 1,
                "no_record": 1, "unavailable": 1, "skipped": 1, "sources": [
                    {"source": "fixture", "label": "fixture", "status": "unavailable", "reason": "dns_error", "as_of": None},
                ]}
    diagnostics = [{"source": "example.invalid/report.json", "status": "unavailable", "reason": "dns_error"}]
    facts = {"ticker": ticker, "sections": [{"label": "fixture"}] * count,
             "coverage": coverage, "missing": ["fixture"], "_meta": {
                 "status": status, "fetch_diagnostics": diagnostics, "collected_at": "2026-09-27",
             }}
    ask = install_core(monkeypatch, endpoint, facts)
    code, body = request(endpoint, "/api/operator_ask?ticker=JEPQ&llm=1")
    assert code == 200
    assert body["status"] == status
    assert body["sections"] == facts["sections"]
    assert body["coverage"] == coverage
    assert body["fetch_diagnostics"] == diagnostics
    assert body["collected_at"] == "2026-09-27"
    assert body["legacy_llm_retired"] is True
    assert body["contract"]["llm_calls"] == 0
    assert "answer" not in body and "synthesis" not in body
    ask.assert_called_once_with("JEPQ", "", facts_only=True)


def test_legacy_payload_is_not_declared_ready(endpoint, monkeypatch):
    install_core(monkeypatch, endpoint, {"ticker": "JEPQ", "sections": [{}] * 30})
    _, body = request(endpoint, "/api/operator_ask?ticker=JEPQ")
    assert body["status"] == "partial"
    assert body["coverage"] is None
    assert body["fetch_diagnostics"] == []


def test_missing_ticker_is_unresolved_even_with_inconsistent_meta(endpoint, monkeypatch):
    install_core(monkeypatch, endpoint, {"ticker": None, "_meta": {"status": "ready"}})
    _, body = request(endpoint, "/api/operator_ask?ticker=fixture")
    assert body["status"] == "unresolved"


def test_auth_is_required_before_core(endpoint):
    code, body = request(endpoint, "/api/operator_ask?ticker=JEPQ")
    assert code == 401 and body["error"] == "unauthorized"
    endpoint.requests.get.assert_not_called()


def test_empty_query_does_not_call_core(endpoint, monkeypatch):
    ask = install_core(monkeypatch, endpoint, {})
    code, _ = request(endpoint, "/api/operator_ask")
    assert code == 400
    ask.assert_not_called()
