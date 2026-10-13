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
    change_fetch = types.ModuleType("api.portfolio_core.portfolio_change_facts")
    change_fetch.fetch_public_changes = Mock(return_value=None)
    monkeypatch.setitem(sys.modules, "api.portfolio_core.portfolio_change_facts", change_fetch)
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
        "change_projection": None,
    }
    assert "jwt-a" not in repr(price_fetch.call_args)
    assert USER_A not in repr(price_fetch.call_args)


def test_optional_changes_use_identifiers_only_after_authentication(modules, monkeypatch):
    endpoint, storage = modules
    monkeypatch.setattr(endpoint, "fetch_public_sources", Mock(return_value=_bundle()))
    changes = sys.modules["api.portfolio_core.portfolio_change_facts"].fetch_public_changes
    changes.return_value = {"synthetic": "projected-change-data"}
    analysis = Mock(return_value={"schema": "alphaconsole-portfolio-v1"})
    monkeypatch.setattr(endpoint, "analyze_portfolio", analysis)
    positions = [{"ticker": "005930", "market": "KR"}]
    status, _, _ = endpoint.analyze_request(_request("jwt-a", {"positions": positions}))
    assert status == 200
    changes.assert_called_once_with(positions)
    assert analysis.call_args.kwargs["change_projection"] == changes.return_value
    assert USER_A not in repr(changes.call_args) and "jwt-a" not in repr(changes.call_args)
    changes.reset_mock()
    status, _, _ = endpoint.analyze_request(_request("invalid", {"positions": positions}))
    assert status == 401
    changes.assert_not_called()
    changes.side_effect = ValueError("private-error-canary")
    status, _, body = endpoint.analyze_request(_request("jwt-a", {"positions": positions}))
    assert status == 200 and "private-error-canary" not in repr(body)
    assert analysis.call_args.kwargs["change_projection"] is None
    storage.select.assert_not_called()


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

@pytest.mark.parametrize("failure", [None, "source-version", "candidate-revision", "foreign-issuer", "private-field"])
def test_prepared_company_judgment_delivery_is_selected_and_optional(modules, monkeypatch, failure):
    # Synthetic raw+review fixture exported by the closed producer; no paid calls.
    fixture = json.loads("{\"artifact\": {\"schema\": \"local-ai-review-v1\", \"candidates\": [{\"issuer_id\": \"KR:111111\", \"counterparty_id\": \"KR:222222\", \"role\": \"customer\", \"quote\": \"당사는 2025년 Synthetic A에 반도체 부품을 공급하며, Synthetic A는 당사의 주요 매출처입니다.\", \"source_id\": \"source:dart:20260312000001\", \"url\": \"https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260312000001\", \"as_of\": \"2026-03-12\", \"status\": \"ai_candidate\", \"verification\": \"unreviewed-model-extraction\", \"issuer_name\": \"Synthetic Issuer\", \"counterparty_name\": \"Synthetic A\", \"evidence_scope\": \"unspecified\", \"current_validity\": \"not-inferred\", \"id\": \"automatic:ai:a9a80936a5a6a21df5a6df3c\", \"revision\": \"1046e7bd3d55aa7df91ad89562942094cbb33379eeb1413fb6c97f11dd0fcdde\"}], \"coverage\": {\"input\": 1, \"accepted\": 1, \"rejected\": 0, \"skipped\": 0}, \"company_judgments\": {\"schema\": \"local-company-judgments-v1\", \"judgments\": [{\"record_id\": \"automatic:ai:a9a80936a5a6a21df5a6df3c\", \"base_read_revision\": 286347547104603, \"company_id\": \"KR:111111\", \"counterparty_id\": \"KR:222222\", \"source_id\": \"source:dart:20260312000001\", \"source_url\": \"https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260312000001\", \"published_on\": \"2026-03-12\", \"quote\": \"당사는 2025년 Synthetic A에 반도체 부품을 공급하며, Synthetic A는 당사의 주요 매출처입니다.\", \"scope_quote\": \"Synthetic A는 당사의 주요 매출처\", \"period_quote\": \"2025년\", \"status\": \"accepted\", \"reviewed_on\": \"2026-10-10\", \"review_reason\": \"원문 범위의 검토가 완료되었습니다.\", \"degree\": \"medium\", \"impact\": {\"direction\": \"unknown\", \"channel\": \"unknown\", \"condition\": null}, \"reason\": \"공개 원문에 연결된 회사별 검토입니다.\", \"review_trigger\": \"원문이나 검토 범위가 바뀌면 다시 확인합니다.\", \"missing_evidence\": [\"counter_evidence_not_searched\"], \"review_reasons\": [], \"revision\": \"8c890e894eeb1789098bc37fc840b47d04e6b98d4729aac14a84c43c52326d9a\", \"read_revision\": 2472324516605618, \"comparison\": {\"status\": \"first\", \"unavailable_reason\": null, \"changed_fields\": [], \"review_changed_fields\": [], \"previous\": null, \"current\": {\"source_version\": \"bedfda4412952e9f180c664a2b03c9ae516f8e5f7828cd6fd0b7528cf63f1d77\", \"judgment_revision\": \"167c1e868452d69fa47c29e7dae3ccccd6b15f2c6fbb57ec878f9ec927af8ca8\", \"review_revision\": \"8c890e894eeb1789098bc37fc840b47d04e6b98d4729aac14a84c43c52326d9a\", \"assessed_as_of\": \"2026-10-10\", \"reviewed_on\": \"2026-10-10\", \"reason\": \"공개 원문에 연결된 회사별 검토입니다.\", \"review_reason\": \"원문 범위의 검토가 완료되었습니다.\"}}, \"source_version\": \"bedfda4412952e9f180c664a2b03c9ae516f8e5f7828cd6fd0b7528cf63f1d77\"}]}}, \"catalog\": [{\"market\": \"KR\", \"ticker\": \"111111\", \"name\": \"Synthetic Issuer\"}, {\"market\": \"KR\", \"ticker\": \"222222\", \"name\": \"Synthetic A\"}]}")
    endpoint, sb = modules
    artifact = fixture["artifact"]
    row = artifact["company_judgments"]["judgments"][0]
    if failure == "source-version":
        row["source_version"] = "0" * 64
    elif failure == "candidate-revision":
        row["base_read_revision"] += 1
    elif failure == "foreign-issuer":
        row["company_id"] = row["counterparty_id"]
    elif failure == "private-field":
        row["member_notes"] = "PRIVATE_CANARY"
    sources = {"universe_search.json": {"stocks": fixture["catalog"]},
               "member_map_ai_candidates.json": artifact}
    monkeypatch.setattr(endpoint, "fetch_public_sources", Mock(return_value=_bundle(sources)))
    market, ticker = artifact["candidates"][0]["issuer_id"].split(":")
    status, _, result = endpoint.analyze_request(_request("jwt-a", {"positions": [{"market": market, "ticker": ticker}]}))
    assert status == 200 and len(result["companies"]) == 1
    assert result["ai_review"]["candidates"][0]["status"] == "ai_candidate"
    assert len(result["company_judgments"]["judgments"]) == (0 if failure else 1)
    if not failure:
        assert result["company_judgments"]["judgments"][0]["degree"] == "medium"
    assert "PRIVATE_CANARY" not in json.dumps(result)
    sb.select.assert_not_called()


@pytest.mark.parametrize("mode", [
    "ok", "public_sources", "prices", "changes", "projection",
    "empty_sources", "bad_prices", "bad_projection",
])
def test_stage_timing_is_fixed_metadata_only(modules, monkeypatch, capsys, caplog, mode):
    endpoint, storage = modules
    secret = "private-account-quote-jwt-a-stack-canary"
    source = Mock(return_value=_bundle({}) if mode == "empty_sources" else _bundle())
    price = sys.modules["api.portfolio_core.portfolio_price_fetch"].fetch_public_prices
    changes = sys.modules["api.portfolio_core.portfolio_change_facts"].fetch_public_changes
    projection = Mock(return_value={"schema": "alphaconsole-portfolio-v1", "private": secret})
    targets = {"public_sources": source, "prices": price, "changes": changes, "projection": projection}
    if mode in targets:
        targets[mode].side_effect = RuntimeError(secret)
    if mode == "bad_prices":
        price.return_value = []
    if mode == "bad_projection":
        projection.return_value = {}
    monkeypatch.setattr(endpoint, "fetch_public_sources", source)
    monkeypatch.setattr(endpoint, "analyze_portfolio", projection)
    ticks = iter(range(8))
    monkeypatch.setattr(endpoint, "time", types.SimpleNamespace(monotonic=lambda: next(ticks)))
    status, headers, _ = endpoint.analyze_request(_request(
        "jwt-a", {"positions": [{"ticker": "005930", "market": "KR"}]}))
    captured = capsys.readouterr()
    stages = ["public_sources"] if mode in ("public_sources", "empty_sources") else [
        "public_sources", "prices", "changes", "projection"]
    error_stage = {"empty_sources": "public_sources", "bad_prices": "prices",
                   "bad_projection": "projection"}.get(mode, mode)
    assert captured.out == ""
    assert captured.err.splitlines() == [
        f"member_map_stage stage={stage} status={'error' if stage == error_stage else 'ok'} elapsed_ms=1000"
        for stage in stages]
    assert status == (503 if mode in ("public_sources", "empty_sources", "projection", "bad_projection") else 200)
    assert headers == endpoint._headers(ALLOWED_ORIGIN)
    for value in (secret, USER_A, USER_B, "jwt-a", "005930", "AAPL", "Traceback", "Bearer"):
        assert value not in captured.err + captured.out + caplog.text
    assert all(record.exc_info is None and record.stack_info is None for record in caplog.records)
    storage.select.assert_not_called()


@pytest.mark.parametrize("mode,status", [
    ("unauthenticated", 401), ("invalid-token", 401), ("identity-error", 503),
    ("invalid-input", 400), ("private-field", 400), ("origin", 403),
])
def test_early_rejection_never_starts_stage_logging(modules, monkeypatch, capsys, caplog, mode, status):
    endpoint, storage = modules
    secret = "private-auth-token-quote-canary"
    clock, source = Mock(), Mock()
    monkeypatch.setattr(endpoint, "_stage_clock", clock)
    monkeypatch.setattr(endpoint, "fetch_public_sources", source)
    if mode == "identity-error":
        monkeypatch.setattr(endpoint, "_identity", Mock(side_effect=RuntimeError(secret)))
    payload = {"positions": [{"ticker": "005930", "market": "KR"}]}
    if mode == "invalid-input":
        payload["positions"] = []
    elif mode == "private-field":
        payload["member_id"] = secret
    token = None if mode == "unauthenticated" else secret if mode == "invalid-token" else "jwt-a"
    request = _request(token, payload, origin="https://evil.example" if mode == "origin" else ALLOWED_ORIGIN)
    assert endpoint.analyze_request(request)[0] == status
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""
    assert secret not in caplog.text
    assert all(record.exc_info is None and record.stack_info is None for record in caplog.records)
    clock.assert_not_called()
    source.assert_not_called()
    storage.select.assert_not_called()


@pytest.mark.parametrize("failure", ["clock", "stderr"])
def test_timing_failure_never_changes_response(modules, monkeypatch, capsys, caplog, failure):
    endpoint, storage = modules
    secret = "private-timing-error-never-exposed"
    monkeypatch.setattr(endpoint, "fetch_public_sources", Mock(return_value=_bundle()))
    expected = {"schema": "alphaconsole-portfolio-v1"}
    monkeypatch.setattr(endpoint, "analyze_portfolio", Mock(return_value=expected))
    if failure == "clock":
        monkeypatch.setattr(endpoint, "time", types.SimpleNamespace(monotonic=Mock(side_effect=RuntimeError(secret))))
    else:
        sink = types.SimpleNamespace(write=Mock(side_effect=RuntimeError(secret)))
        monkeypatch.setattr(endpoint, "sys", types.SimpleNamespace(stderr=sink))
    result = endpoint.analyze_request(_request("jwt-a", {"positions": [{"ticker": "005930", "market": "KR"}]}))
    assert result == (200, endpoint._headers(ALLOWED_ORIGIN), expected)
    captured = capsys.readouterr()
    assert captured.err == captured.out == ""
    assert secret not in caplog.text
    storage.select.assert_not_called()


def test_timing_helper_rejects_non_fixed_labels(modules, capsys):
    endpoint, _ = modules
    endpoint._log_stage_timing("private-user-token", 0, "ok")
    endpoint._log_stage_timing("prices", 0, "private-quote")
    endpoint._log_stage_timing("prices", None, "ok")
    assert capsys.readouterr().err == ""
