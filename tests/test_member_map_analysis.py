"""Local contract tests for the authenticated public-source analysis endpoint."""
from __future__ import annotations

import importlib.util
import io
import json
import logging
from pathlib import Path
import subprocess
import sys
import types
from unittest.mock import Mock

import pytest


ROOT = Path(__file__).resolve().parents[1]
API_DIR = ROOT / "vercel-api" / "api"
# Exercise the exact package shipped to Vercel, including its generated imports.
INTELLIGENCE_DIR = API_DIR / "portfolio_core"
USER_A = "11111111-1111-4111-8111-111111111111"
USER_B = "22222222-2222-4222-8222-222222222222"
ALLOWED_ORIGIN = "https://app.example"
ANALYSIS_ORIGIN = "https://project-yw131.vercel.app"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def modules(monkeypatch, tmp_path):
    helper_directory = API_DIR
    if not (API_DIR / "cors_helper.py").is_file():
        # This candidate worktree marks the tracked helper skip-worktree. Load
        # the exact Git blob through a normal package path, as deployment does.
        tracked_helper = subprocess.run(
            ["git", "show", "HEAD:vercel-api/api/cors_helper.py"],
            cwd=ROOT,
            check=True,
            stdout=subprocess.PIPE,
        ).stdout
        helper_directory = tmp_path / "tracked-api"
        helper_directory.mkdir()
        (helper_directory / "cors_helper.py").write_bytes(tracked_helper)

    package = types.ModuleType("api")
    package.__path__ = [str(API_DIR), str(helper_directory)]
    monkeypatch.setitem(sys.modules, "api", package)
    monkeypatch.delitem(sys.modules, "api.cors_helper", raising=False)
    monkeypatch.delitem(sys.modules, "cors_helper", raising=False)
    monkeypatch.setenv("API_ALLOWED_ORIGINS", ALLOWED_ORIGIN)

    sb = types.ModuleType("api.supabase_client")
    sb.verify_jwt = Mock(side_effect=lambda token: {
        "jwt-a": USER_A,
        "jwt-b": USER_B,
    }.get(token))
    sb.select = Mock(side_effect=AssertionError("member storage must not be read"))
    monkeypatch.setitem(sys.modules, "api.supabase_client", sb)

    validation = _load(
        "api.member_map_state_validation", API_DIR / "member_map_state_validation.py"
    )
    monkeypatch.setitem(sys.modules, "api.member_map_state_validation", validation)
    member_state = _load("api.member_map_state", API_DIR / "member_map_state.py")
    monkeypatch.setitem(sys.modules, "api.member_map_state", member_state)

    core = types.ModuleType("api.portfolio_core")
    core.__path__ = [str(INTELLIGENCE_DIR)]
    monkeypatch.setitem(sys.modules, "api.portfolio_core", core)
    public_sources = _load(
        "api.portfolio_core.portfolio_public_sources",
        INTELLIGENCE_DIR / "portfolio_public_sources.py",
    )
    prices = _load(
        "api.portfolio_core.portfolio_prices",
        INTELLIGENCE_DIR / "portfolio_prices.py",
    )
    evidence = _load(
        "api.portfolio_core.portfolio_evidence",
        INTELLIGENCE_DIR / "portfolio_evidence.py",
    )
    engine = _load(
        "api.portfolio_core.portfolio_engine",
        INTELLIGENCE_DIR / "portfolio_engine.py",
    )
    public_fetch = _load(
        "api.portfolio_core.portfolio_public_fetch",
        INTELLIGENCE_DIR / "portfolio_public_fetch.py",
    )
    price_fetch = types.ModuleType("api.portfolio_core.portfolio_price_fetch")
    price_fetch.fetch_public_prices = Mock(return_value={})
    monkeypatch.setitem(sys.modules, "api.portfolio_core.portfolio_public_sources", public_sources)
    monkeypatch.setitem(sys.modules, "api.portfolio_core.portfolio_prices", prices)
    monkeypatch.setitem(sys.modules, "api.portfolio_core.portfolio_evidence", evidence)
    monkeypatch.setitem(sys.modules, "api.portfolio_core.portfolio_engine", engine)
    monkeypatch.setitem(sys.modules, "api.portfolio_core.portfolio_public_fetch", public_fetch)
    monkeypatch.setitem(sys.modules, "api.portfolio_core.portfolio_price_fetch", price_fetch)

    endpoint = _load("api.member_map_analysis", API_DIR / "member_map_analysis.py")
    monkeypatch.setitem(sys.modules, "api.member_map_analysis", endpoint)
    return endpoint, sb


def _documents():
    return {
        "universe_search.json": {
            "stocks": [
                {"ticker": "005930", "market": "KOSPI", "name": "삼성전자"},
                {"ticker": "AAPL", "market": "NASDAQ", "name": "Apple Inc."},
            ]
        }
    }


def _bundle(documents=None):
    docs = _documents() if documents is None else documents
    endpoint_names = sys.modules[
        "api.portfolio_core.portfolio_public_fetch"
    ].PUBLIC_SOURCE_FILES
    missing = [name for name in endpoint_names if name not in docs]
    available = len(endpoint_names) - len(missing)
    return {
        "documents": docs,
        "coverage": {
            "expected": len(endpoint_names),
            "available": available,
            "missing": missing,
            "status": "complete" if available == len(endpoint_names) else "partial" if available else "unavailable",
        },
        "revision": "a" * 64,
    }


def _request(token=None, payload=None, *, origin=ALLOWED_ORIGIN, raw=None):
    if raw is None:
        raw = b"" if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Origin": origin, "Content-Length": str(len(raw))}
    if token:
        headers["Authorization"] = "Bearer " + token
    return types.SimpleNamespace(headers=headers, rfile=io.BytesIO(raw))


def _invoke_http(endpoint, method, token=None, payload=None, *, origin=ALLOWED_ORIGIN):
    request = _request(token, payload, origin=origin)
    instance = object.__new__(endpoint.handler)
    instance.headers = request.headers
    instance.rfile = request.rfile
    instance.wfile = io.BytesIO()
    instance._headers_sent = []
    instance.send_response = lambda status: setattr(instance, "status", status)
    instance.send_header = lambda key, value: instance._headers_sent.append((key, value))
    instance.end_headers = lambda: None
    getattr(instance, method)()
    return instance, json.loads(instance.wfile.getvalue() or b"{}")


def test_two_verified_callers_receive_only_their_requested_selection(modules, monkeypatch):
    endpoint, sb = modules
    fetch = Mock(return_value=_bundle())
    monkeypatch.setattr(endpoint, "fetch_public_sources", fetch)

    status_a, headers_a, result_a = endpoint.analyze_request(_request(
        "jwt-a", {"positions": [{"ticker": "005930", "market": "KR"}]}
    ))
    status_b, headers_b, result_b = endpoint.analyze_request(_request(
        "jwt-b", {"positions": [{"ticker": "AAPL", "market": "US"}]}
    ))

    assert status_a == status_b == 200
    assert [row["id"] for row in result_a["companies"]] == ["KR:005930"]
    assert [row["id"] for row in result_b["companies"]] == ["US:AAPL"]
    assert result_a["schema"] == result_b["schema"] == "alphaconsole-portfolio-v1"
    assert headers_a["Cache-Control"].startswith("private, no-store")
    assert headers_b["Vary"] == "Authorization, Origin"
    rendered = json.dumps([result_a, result_b], ensure_ascii=False)
    for private in (USER_A, USER_B, "jwt-a", "jwt-b"):
        assert private not in rendered
    assert sb.verify_jwt.call_args_list == [(("jwt-a",),), (("jwt-b",),)]
    sb.select.assert_not_called()
    assert fetch.call_count == 2
    price_fetch = sys.modules["api.portfolio_core.portfolio_price_fetch"].fetch_public_prices
    assert price_fetch.call_args_list == [
        (([{"ticker": "005930", "market": "KR"}],),),
        (([{"ticker": "AAPL", "market": "US"}],),),
    ]
    assert "jwt-a" not in repr(price_fetch.call_args_list)
    assert USER_A not in repr(price_fetch.call_args_list)


def test_validated_public_prices_are_forwarded_without_private_fields(modules, monkeypatch):
    endpoint, _ = modules
    source = _bundle()
    price_documents = {"synthetic": "public-price-documents"}
    price_module = sys.modules["api.portfolio_core.portfolio_price_fetch"]
    price_fetch = Mock(return_value=price_documents)
    monkeypatch.setattr(price_module, "fetch_public_prices", price_fetch)
    monkeypatch.setattr(endpoint, "fetch_public_sources", Mock(return_value=source))
    analysis = Mock(return_value={"schema": "alphaconsole-portfolio-v1"})
    monkeypatch.setattr(endpoint, "analyze_portfolio", analysis)

    status, _headers, payload = endpoint.analyze_request(_request(
        "jwt-a", {"positions": [{"ticker": "005930", "market": "KR"}]}
    ))

    assert status == 200
    assert payload["schema"] == "alphaconsole-portfolio-v1"
    price_fetch.assert_called_once_with([{"ticker": "005930", "market": "KR"}])
    assert analysis.call_args.args == (
        [{"ticker": "005930", "market": "KR"}], source["documents"]
    )
    assert analysis.call_args.kwargs == {
        "public_bundle_revision": source["revision"],
        "price_documents": price_documents,
    }
    assert "jwt-a" not in repr(price_fetch.call_args)
    assert USER_A not in repr(price_fetch.call_args)


def test_price_source_failure_preserves_analysis_with_empty_price_documents(
    modules, monkeypatch, caplog
):
    endpoint, _ = modules
    price_module = sys.modules["api.portfolio_core.portfolio_price_fetch"]
    monkeypatch.setattr(
        price_module, "fetch_public_prices",
        Mock(side_effect=RuntimeError("jwt-a private failure detail")),
    )
    monkeypatch.setattr(endpoint, "fetch_public_sources", Mock(return_value=_bundle()))

    with caplog.at_level(logging.WARNING):
        status, _headers, payload = endpoint.analyze_request(_request(
            "jwt-a", {"positions": [{"ticker": "005930", "market": "KR"}]}
        ))

    assert status == 200
    assert payload["schema"] == "alphaconsole-portfolio-v1"
    assert payload["companies"]
    assert "private failure detail" not in caplog.text
    assert "jwt-a" not in caplog.text
    assert "[price_source_unavailable]" in caplog.text


def test_invalid_price_fetch_result_degrades_to_empty_documents(modules, monkeypatch):
    endpoint, _ = modules
    price_module = sys.modules["api.portfolio_core.portfolio_price_fetch"]
    monkeypatch.setattr(price_module, "fetch_public_prices", Mock(return_value=[]))
    monkeypatch.setattr(endpoint, "fetch_public_sources", Mock(return_value=_bundle()))
    analysis = Mock(return_value={"schema": "alphaconsole-portfolio-v1"})
    monkeypatch.setattr(endpoint, "analyze_portfolio", analysis)

    status, _headers, payload = endpoint.analyze_request(_request(
        "jwt-a", {"positions": [{"ticker": "005930", "market": "KR"}]}
    ))

    assert status == 200
    assert payload["schema"] == "alphaconsole-portfolio-v1"
    assert analysis.call_args.kwargs["price_documents"] == {}


@pytest.mark.parametrize("payload", [
    {"positions": [{"ticker": "005930", "market": "KR"}], "user_id": USER_B},
    {"positions": [{"ticker": "005930", "market": "KR", "shares": 10}]},
    {"positions": [{"ticker": "005930", "market": "KOSPI"}]},
    {"positions": []},
    {"positions": [{"ticker": "005930", "market": "KR"}] * 31},
])
def test_private_or_noncanonical_fields_are_rejected_before_fetch(modules, monkeypatch, payload):
    endpoint, _ = modules
    fetch = Mock(side_effect=AssertionError("fetch must not run"))
    monkeypatch.setattr(endpoint, "fetch_public_sources", fetch)
    status, _headers, result = endpoint.analyze_request(_request("jwt-a", payload))
    assert status == 400
    assert result["error"] in {"invalid_request", "invalid_positions"}
    fetch.assert_not_called()
    sys.modules["api.portfolio_core.portfolio_price_fetch"].fetch_public_prices.assert_not_called()


def test_authentication_and_origin_rejections_happen_before_fetch(modules, monkeypatch):
    endpoint, sb = modules
    fetch = Mock()
    monkeypatch.setattr(endpoint, "fetch_public_sources", fetch)
    payload = {"positions": [{"ticker": "005930", "market": "KR"}]}

    unauthenticated = endpoint.analyze_request(_request(None, payload))
    hostile_origin = endpoint.analyze_request(
        _request("jwt-a", payload, origin="https://evil.example")
    )
    assert unauthenticated[0:3:2] == (401, {"error": "authentication_required"})
    assert hostile_origin[0:3:2] == (403, {"error": "origin_not_allowed"})
    assert sb.verify_jwt.call_count == 0  # Neither request reaches JWT verification.
    fetch.assert_not_called()
    sys.modules["api.portfolio_core.portfolio_price_fetch"].fetch_public_prices.assert_not_called()


def test_origin_uses_tracked_api_helper_import_path(modules):
    endpoint, _ = modules
    assert endpoint._resolve_origin(ALLOWED_ORIGIN) == ALLOWED_ORIGIN
    assert endpoint._resolve_origin("https://evil.example") == ""
    helper = sys.modules["api.cors_helper"]
    assert Path(helper.__file__).name == "cors_helper.py"
    assert "cors_helper" not in sys.modules


def test_known_analysis_origin_is_exact_and_not_host_reflected(modules):
    endpoint, _ = modules
    assert endpoint._resolve_origin(ANALYSIS_ORIGIN) == ANALYSIS_ORIGIN
    for rejected in (
        "https://evil.project-yw131.vercel.app",
        "https://project-yw131.vercel.app.evil.example",
        "http://project-yw131.vercel.app",
        "https://project-yw131.vercel.app:443",
    ):
        assert endpoint._resolve_origin(rejected) == ""

    request = _request(
        "jwt-a",
        {"positions": [{"ticker": "005930", "market": "KR"}]},
        origin=ANALYSIS_ORIGIN,
    )
    error, headers = endpoint._origin_result(request)
    assert error is None
    assert headers["Access-Control-Allow-Origin"] == ANALYSIS_ORIGIN


def test_all_sources_failed_is_503_not_an_empty_analysis(modules, monkeypatch):
    endpoint, _ = modules
    monkeypatch.setattr(endpoint, "fetch_public_sources", lambda: _bundle({}))
    status, headers, payload = endpoint.analyze_request(_request(
        "jwt-a", {"positions": [{"ticker": "005930", "market": "KR"}]}
    ))
    assert (status, payload) == (503, {"error": "public_sources_unavailable"})
    assert headers["CDN-Cache-Control"] == "no-store"
    assert headers["Vercel-CDN-Cache-Control"] == "no-store"
    sys.modules["api.portfolio_core.portfolio_price_fetch"].fetch_public_prices.assert_not_called()


def test_source_exception_is_not_reflected_or_logged(modules, monkeypatch, caplog):
    endpoint, _ = modules
    secret = "https://private.invalid/raw?Authorization=Bearer-secret"
    monkeypatch.setattr(
        endpoint, "fetch_public_sources", Mock(side_effect=RuntimeError(secret))
    )
    with caplog.at_level(logging.WARNING):
        status, _headers, payload = endpoint.analyze_request(_request(
            "jwt-a", {"positions": [{"ticker": "005930", "market": "KR"}]}
        ))
    assert (status, payload) == (503, {"error": "public_sources_unavailable"})
    assert "private.invalid" not in caplog.text
    assert "Bearer-secret" not in caplog.text
    assert "[source_unavailable]" in caplog.text


def test_unexpected_identity_failure_is_generic_and_never_fetches(modules, monkeypatch, caplog):
    endpoint, _ = modules
    secret = "Bearer private-jwt-from-auth-exception"
    fetch = Mock()
    monkeypatch.setattr(endpoint, "_identity", Mock(side_effect=RuntimeError(secret)))
    monkeypatch.setattr(endpoint, "fetch_public_sources", fetch)
    with caplog.at_level(logging.WARNING):
        status, headers, payload = endpoint.analyze_request(_request(
            "jwt-a", {"positions": [{"ticker": "005930", "market": "KR"}]}
        ))
    assert (status, payload) == (503, {"error": "authentication_unavailable"})
    assert headers["Cache-Control"].startswith("private, no-store")
    assert secret not in caplog.text
    assert "[authentication_unavailable]" in caplog.text
    fetch.assert_not_called()


def test_send_replaces_unserializable_and_oversized_payloads_with_bounded_error(
    modules, monkeypatch, caplog
):
    endpoint, _ = modules
    monkeypatch.setattr(endpoint, "_MAX_RESPONSE_BYTES", 128)
    response = object.__new__(endpoint.handler)
    response.wfile = io.BytesIO()
    response._headers_sent = []
    response.send_response = lambda status: setattr(response, "status", status)
    response.send_header = lambda key, value: response._headers_sent.append((key, value))
    response.end_headers = lambda: None
    headers = endpoint._headers(ALLOWED_ORIGIN)

    with caplog.at_level(logging.WARNING):
        endpoint._send(response, (200, headers, {"private": object()}))
    assert response.status == 503
    assert json.loads(response.wfile.getvalue()) == {"error": "analysis_unavailable"}
    assert int(dict(response._headers_sent)["Content-Length"]) <= 128
    assert "[serialization_unavailable]" in caplog.text

    response.wfile = io.BytesIO()
    response._headers_sent = []
    with caplog.at_level(logging.WARNING):
        endpoint._send(response, (200, headers, {"data": "x" * 129}))
    assert response.status == 503
    assert json.loads(response.wfile.getvalue()) == {"error": "analysis_unavailable"}
    assert int(dict(response._headers_sent)["Content-Length"]) <= 128
    assert "[response_too_large]" in caplog.text


def test_send_ignores_client_disconnect_without_retry_or_payload_logging(modules):
    endpoint, _ = modules

    class _Disconnected:
        def write(self, _body):
            raise BrokenPipeError("private transport detail")

    response = object.__new__(endpoint.handler)
    response.wfile = _Disconnected()
    response.send_response = lambda status: setattr(response, "status", status)
    response.send_header = lambda _key, _value: None
    response.end_headers = lambda: None
    endpoint._send(response, (200, endpoint._headers(), {"schema": "test"}))
    assert response.status == 200


def test_get_is_405_and_response_headers_are_private(modules):
    endpoint, _ = modules
    response, payload = _invoke_http(endpoint, "do_GET")
    headers = dict(response._headers_sent)
    assert (response.status, payload) == (405, {"error": "method_not_allowed"})
    assert headers["Allow"] == "POST, OPTIONS"
    assert headers["Cache-Control"] == "private, no-store, max-age=0"
    assert headers["Vary"] == "Authorization, Origin"
    assert headers["Access-Control-Allow-Origin"] == ALLOWED_ORIGIN


def test_duplicate_json_keys_and_malformed_fetch_contract_fail_closed(modules, monkeypatch):
    endpoint, _ = modules
    fetch = Mock(return_value={
        "documents": {"../../private.json": {}},
        "coverage": {},
        "revision": "a" * 64,
    })
    monkeypatch.setattr(endpoint, "fetch_public_sources", fetch)
    duplicate = b'{"positions":[],"positions":[{"ticker":"005930","market":"KR"}]}'
    status, _headers, payload = endpoint.analyze_request(_request("jwt-a", raw=duplicate))
    assert (status, payload) == (400, {"error": "invalid_request"})
    fetch.assert_not_called()

    status, _headers, payload = endpoint.analyze_request(_request(
        "jwt-a", {"positions": [{"ticker": "005930", "market": "KR"}]}
    ))
    assert (status, payload) == (503, {"error": "public_sources_unavailable"})
