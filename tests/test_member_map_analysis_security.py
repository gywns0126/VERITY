"""Independent adversarial tests for the member-map portfolio sidecar.

These tests use the real handler, source projector, and portfolio engine with
synthetic public artifacts only.  They intentionally do not exercise browser
transport or any member-state persistence path.
"""
from __future__ import annotations

import ast
import importlib.util
import io
import json
import logging
from pathlib import Path
import re
import sys
import types
from unittest.mock import Mock

import pytest


ROOT = Path(__file__).resolve().parents[1]
API_DIR = ROOT / "vercel-api" / "api"
# Exercise the deployed package, not a broader local source-only checkout.
INTELLIGENCE_DIR = API_DIR / "portfolio_core"
CALLER_A = "11111111-1111-4111-8111-111111111111"
CALLER_B = "22222222-2222-4222-8222-222222222222"
ORIGIN = "https://app.example"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def endpoint(monkeypatch):
    package = types.ModuleType("api")
    package.__path__ = [str(API_DIR)]
    monkeypatch.setitem(sys.modules, "api", package)

    storage = types.ModuleType("api.supabase_client")
    storage.verify_jwt = Mock(side_effect=lambda token: {
        "token-a": CALLER_A, "token-b": CALLER_B,
    }.get(token))
    storage.select = Mock(side_effect=AssertionError("member storage read"))
    storage.upsert = Mock(side_effect=AssertionError("member storage write"))
    monkeypatch.setitem(sys.modules, "api.supabase_client", storage)

    validation = _load(
        "api.member_map_state_validation", API_DIR / "member_map_state_validation.py"
    )
    monkeypatch.setitem(sys.modules, "api.member_map_state_validation", validation)
    state = _load("api.member_map_state", API_DIR / "member_map_state.py")
    monkeypatch.setitem(sys.modules, "api.member_map_state", state)

    cors = types.ModuleType("api.cors_helper")
    cors.resolve_origin = lambda value: value if value == ORIGIN else ""
    monkeypatch.setitem(sys.modules, "api.cors_helper", cors)

    core = types.ModuleType("api.portfolio_core")
    core.__path__ = [str(INTELLIGENCE_DIR)]
    monkeypatch.setitem(sys.modules, "api.portfolio_core", core)
    sources = _load(
        "api.portfolio_core.portfolio_public_sources",
        INTELLIGENCE_DIR / "portfolio_public_sources.py",
    )
    evidence = _load(
        "api.portfolio_core.portfolio_evidence",
        INTELLIGENCE_DIR / "portfolio_evidence.py",
    )
    prices = _load(
        "api.portfolio_core.portfolio_prices",
        INTELLIGENCE_DIR / "portfolio_prices.py",
    )
    engine = _load(
        "api.portfolio_core.portfolio_engine", INTELLIGENCE_DIR / "portfolio_engine.py"
    )
    fetch = _load(
        "api.portfolio_core.portfolio_public_fetch",
        INTELLIGENCE_DIR / "portfolio_public_fetch.py",
    )
    monkeypatch.setitem(sys.modules, "api.portfolio_core.portfolio_public_sources", sources)
    monkeypatch.setitem(sys.modules, "api.portfolio_core.portfolio_evidence", evidence)
    monkeypatch.setitem(sys.modules, "api.portfolio_core.portfolio_prices", prices)
    monkeypatch.setitem(sys.modules, "api.portfolio_core.portfolio_engine", engine)
    monkeypatch.setitem(sys.modules, "api.portfolio_core.portfolio_public_fetch", fetch)
    price_fetch = types.ModuleType("api.portfolio_core.portfolio_price_fetch")
    price_fetch.fetch_public_prices = Mock(return_value={})
    monkeypatch.setitem(sys.modules, "api.portfolio_core.portfolio_price_fetch", price_fetch)
    analysis = _load("api.member_map_analysis", API_DIR / "member_map_analysis.py")
    monkeypatch.setitem(sys.modules, "api.member_map_analysis", analysis)
    return analysis, storage


def _request(token, payload, *, origin=ORIGIN):
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return types.SimpleNamespace(
        headers={
            "Origin": origin,
            "Authorization": "Bearer " + token,
            "Content-Length": str(len(raw)),
        },
        rfile=io.BytesIO(raw),
    )


def _bundle(documents):
    files = sys.modules[
        "api.portfolio_core.portfolio_public_fetch"
    ].PUBLIC_SOURCE_FILES
    missing = [name for name in files if name not in documents]
    return {"documents": documents, "coverage": {
        "expected": len(files), "available": len(files) - len(missing), "missing": missing,
        "status": "complete" if not missing else "partial" if documents else "unavailable",
    }, "revision": "a" * 64}


def _public_documents():
    return {
        "universe_search.json": {"stocks": [{
            "ticker": "005930", "market": "KOSPI", "name": "Safe Company",
            "owner_id": "owner-secret-should-not-project",
            "member_email": "private.person@example.invalid",
            "access_token": "not-a-real-token-but-private-input",
        }]},
        "stock_report_public.json": {"stocks": [{
            "ticker": "005930",
            "disclosures": [{
                "title": "owner_id private.person@example.invalid",
                "date": "2026-01-31",
                "source_url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260131000001",
            }],
        }]},
    }


def test_public_cors_wildcard_excludes_analysis_endpoint_and_python_variant():
    config = json.loads((ROOT / "vercel-api" / "vercel.json").read_text(encoding="utf-8"))
    wildcard_rules = [
        rule for rule in config["headers"]
        if any(
            header == {"key": "Access-Control-Allow-Origin", "value": "*"}
            for header in rule.get("headers", [])
        )
    ]
    assert len(wildcard_rules) == 1
    source = wildcard_rules[0]["source"]
    pattern = re.compile(source)

    assert not pattern.fullmatch("/api/member_map_analysis")
    assert not pattern.fullmatch("/api/member_map_analysis.py")
    assert not pattern.fullmatch("/api/member_map_analysis/anything")
    assert pattern.fullmatch("/api/public-health")


def test_tainted_public_artifacts_are_projected_before_private_response(endpoint, monkeypatch):
    analysis, storage = endpoint
    secrets = (
        "owner-secret-should-not-project", "private.person@example.invalid",
        "not-a-real-token-but-private-input", "owner_id",
    )
    monkeypatch.setattr(analysis, "fetch_public_sources", Mock(return_value=_bundle(_public_documents())))

    status, headers, response = analysis.analyze_request(_request(
        "token-a", {"positions": [{"ticker": "005930", "market": "KR"}]}
    ))

    assert status == 200
    assert headers["Cache-Control"] == "private, no-store, max-age=0"
    rendered = json.dumps(response, ensure_ascii=False)
    assert response["companies"] == [{
        "id": "KR:005930", "ticker": "005930", "market": "KR",
        "name": "Safe Company", "facts": [], "document_ids": [],
    }]
    assert response["documents"] == []
    assert not any(value in rendered for value in secrets)
    price_fetch = sys.modules["api.portfolio_core.portfolio_price_fetch"].fetch_public_prices
    price_fetch.assert_called_once_with([{"ticker": "005930", "market": "KR"}])
    assert "token-a" not in repr(price_fetch.call_args)
    assert CALLER_A not in repr(price_fetch.call_args)
    storage.select.assert_not_called()
    storage.upsert.assert_not_called()


def test_unknown_or_tampered_source_contract_never_becomes_an_analysis(endpoint, monkeypatch):
    analysis, _storage = endpoint
    fetch = Mock(return_value=_bundle({
        "universe_search.json": {"stocks": []},
        "member_export.json": {"rows": [{"owner_id": CALLER_B}]},
    }))
    monkeypatch.setattr(analysis, "fetch_public_sources", fetch)

    status, _headers, response = analysis.analyze_request(_request(
        "token-a", {"positions": [{"ticker": "005930", "market": "KR"}]}
    ))

    assert (status, response) == (503, {"error": "public_sources_unavailable"})
    assert CALLER_B not in json.dumps(response)
    fetch.assert_called_once_with()
    sys.modules["api.portfolio_core.portfolio_price_fetch"].fetch_public_prices.assert_not_called()


@pytest.mark.parametrize("field", ("owner_id", "user_id", "tenant_id", "member_id"))
def test_tampered_identity_fields_are_rejected_before_public_read(endpoint, monkeypatch, field):
    analysis, storage = endpoint
    fetch = Mock(side_effect=AssertionError("public fetch must not run"))
    monkeypatch.setattr(analysis, "fetch_public_sources", fetch)
    injected = "attacker-private-value"

    status, _headers, response = analysis.analyze_request(_request("token-a", {
        "positions": [{"ticker": "005930", "market": "KR"}], field: injected,
    }))

    assert (status, response) == (400, {"error": "invalid_request"})
    assert injected not in json.dumps(response)
    fetch.assert_not_called()
    sys.modules["api.portfolio_core.portfolio_price_fetch"].fetch_public_prices.assert_not_called()
    storage.select.assert_not_called()
    storage.upsert.assert_not_called()


def test_results_are_request_local_and_handler_has_no_storage_or_access_log_path(endpoint, monkeypatch, caplog):
    analysis, storage = endpoint
    source = _bundle({"universe_search.json": {"stocks": [
        {"ticker": "005930", "market": "KOSPI", "name": "KR Safe"},
        {"ticker": "AAPL", "market": "NASDAQ", "name": "US Safe"},
    ]}})
    monkeypatch.setattr(analysis, "fetch_public_sources", Mock(return_value=source))
    status_a, _headers_a, result_a = analysis.analyze_request(_request(
        "token-a", {"positions": [{"ticker": "005930", "market": "KR"}]}
    ))
    result_a["companies"][0]["name"] = "mutated-only-in-caller-a"
    status_b, _headers_b, result_b = analysis.analyze_request(_request(
        "token-b", {"positions": [{"ticker": "AAPL", "market": "US"}]}
    ))

    assert status_a == status_b == 200
    assert result_b["companies"] == [{
        "id": "US:AAPL", "ticker": "AAPL", "market": "US",
        "name": "US Safe", "facts": [], "document_ids": [],
    }]
    assert "mutated-only-in-caller-a" not in json.dumps(result_b)
    price_fetch = sys.modules["api.portfolio_core.portfolio_price_fetch"].fetch_public_prices
    assert price_fetch.call_args_list == [
        (([{"ticker": "005930", "market": "KR"}],),),
        (([{"ticker": "AAPL", "market": "US"}],),),
    ]
    assert "token-a" not in repr(price_fetch.call_args_list)
    assert "token-b" not in repr(price_fetch.call_args_list)
    assert CALLER_A not in repr(price_fetch.call_args_list)
    assert CALLER_B not in repr(price_fetch.call_args_list)
    storage.select.assert_not_called()
    storage.upsert.assert_not_called()

    tree = ast.parse((API_DIR / "member_map_analysis.py").read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
            imported.update(node.module + "." + alias.name for alias in node.names)
    forbidden = ("requests", "urllib", "api.supabase_client", "sqlite3", "boto3")
    assert not any(name == item or name.startswith(item + ".") for name in imported for item in forbidden)
    with caplog.at_level(logging.INFO):
        instance = object.__new__(analysis.handler)
        instance.log_message("Authorization: Bearer %s positions=%s", "token-a", "005930")
    assert "token-a" not in caplog.text
    assert "005930" not in caplog.text
