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
    change_fetch = types.ModuleType("api.portfolio_core.portfolio_change_facts")
    change_fetch.fetch_public_changes = Mock(return_value=None)
    monkeypatch.setitem(sys.modules, "api.portfolio_core.portfolio_change_facts", change_fetch)
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


@pytest.mark.parametrize("point", (*range(32), 127))
def test_public_text_control_boundary_keeps_strip_order(point):
    sources = _load("public_text_control_test", INTELLIGENCE_DIR / "portfolio_public_sources.py")
    char = chr(point)
    for validate in (sources._safe_text, sources.safe_public_text):
        assert validate('가' + char + '나', 160) is None
        assert validate(char + '가' + char, 160) == ('가' if char.isspace() else None)


def test_public_text_unicode_length_and_existing_sensitive_boundaries():
    sources = _load("public_text_unicode_test", INTELLIGENCE_DIR / "portfolio_public_sources.py")
    for validate in (sources._safe_text, sources.safe_public_text):
        for value in ('한글😀', '가\x80나', '가\u2028나', '가\u2029나', '가\ud800나'):
            assert validate('  ' + value + '  ', len(value)) == value
            assert validate(value, len(value) - 1) is None
        for value in (None, 1, b'plain', 'sample@example.invalid', 'Bearer synthetic',
                      'sk-proj-syntheticvalue', '/Users/synthetic/example', '<b>자료</b>'):
            assert validate(value, 160) is None


def test_owned_public_catalog_reuses_fresh_projection_without_mutating_sources(endpoint):
    from copy import deepcopy
    sources = sys.modules['api.portfolio_core.portfolio_public_sources']
    from api.portfolio_core.portfolio_company_names import add_public_company_names, PublicSourceError
    documents = {'universe_search.json': {'stocks': [
        {'ticker': '005930', 'market': 'KR', 'name': 'Synthetic Company'}]}}
    before = deepcopy(documents)
    projected = sources.project_public_sources(documents)['companies']
    independent = add_public_company_names({}, projected)
    independent[0]['facts'].append({'synthetic': True})
    assert projected[0]['facts'] == []
    owned = add_public_company_names({}, projected, _owned_catalog=True)
    assert owned is projected
    owned[0]['documents'].append({'synthetic': True})
    assert documents == before
    assert sources.project_public_sources(documents)['companies'][0]['documents'] == []
    for flag in (0, 1, None, 'true'):
        with pytest.raises(PublicSourceError):
            add_public_company_names({}, projected, _owned_catalog=flag)


def test_business_matchers_reuse_only_unchanged_public_dependencies(endpoint, monkeypatch):
    from copy import deepcopy
    engine = sys.modules['api.portfolio_core.portfolio_engine']
    text = '당사의 주요 매출처는 합성고객, 다른업체입니다.'
    documents = {
        'universe_search.json': {'stocks': [
            {'ticker': '001111', 'market': 'KR', 'name': '합성회사'},
            {'ticker': '002222', 'market': 'KR', 'name': '합성고객'}]},
        'stock_report_public.json': {'stocks': [{'ticker': '001111', 'name': '합성회사',
            'facts': [{'metric': 'revenue', 'value': 100, 'unit': 'KRW',
                       'as_of': '2025-12-31', 'source': 'DART'}]}]},
        'kr_business_overview_public.json': {
            '_meta': {'count': 1, 'generated_at': '2026-10-12T00:00:00Z'},
            'rows': {'001111': {'name': '합성회사', 'text': text, 'chars': len(text),
                'fiscal_year': '2025', 'filed_at': '20260318', 'report': '사업보고서 (2025.12)',
                'url': 'https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260318000001',
                'truncated': False}}}}
    original = deepcopy(documents)
    build = Mock(wraps=engine._business_material_index)
    monkeypatch.setattr(engine, '_business_material_index', build)
    positions = [{'ticker': '001111', 'market': 'KR'}]
    first = engine.analyze_portfolio(positions, documents, public_bundle_revision='a'*64)
    changed = deepcopy(documents)
    changed['stock_report_public.json']['stocks'][0]['facts'][0]['value'] = 200
    changed['portfolio.json'] = {'headlines': []}
    second = engine.analyze_portfolio(positions, changed, public_bundle_revision='b'*64)
    assert build.call_count == 1
    assert second['companies'][0]['facts'][0]['value'] == 200
    assert first['companies'][0]['facts'][0]['value'] == 100
    second['automatic_evidence']['materials'][0]['evidence']['excerpt'] = 'caller-only edit'
    third = engine.analyze_portfolio(positions, changed, public_bundle_revision='c'*64)
    assert third['automatic_evidence']['materials'][0]['evidence']['excerpt'] == text
    assert build.call_count == 1
    renamed = deepcopy(changed)
    renamed['universe_search.json']['stocks'][1]['name'] = '다른고객'
    engine.analyze_portfolio(positions, renamed, public_bundle_revision='d'*64)
    assert build.call_count == 2
    revised = deepcopy(renamed)
    revised['kr_business_overview_public.json']['rows']['001111']['truncated'] = True
    engine.analyze_portfolio(positions, revised, public_bundle_revision='e'*64)
    assert build.call_count == 3
    assert documents == original
    engine.analyze_portfolio(positions, revised)  # No revision never reuses cache.
    assert build.call_count == 4


def test_business_cache_key_covers_utc_day_and_identity_but_opts_out_safely(endpoint, monkeypatch):
    from copy import deepcopy
    from datetime import datetime, timezone
    engine = sys.modules['api.portfolio_core.portfolio_engine']
    class Clock:
        day = 13
        @classmethod
        def now(cls, tz):
            assert tz is timezone.utc
            return datetime(2026, 10, cls.day, tzinfo=tz)
    monkeypatch.setattr(engine, 'datetime', Clock)
    catalog = {'KR:001111': {'id': 'KR:001111', 'market': 'KR',
        'name': '합성회사', 'source_names': ['합성회사']}}
    baseline = engine._business_index_revision({}, catalog)
    assert baseline is not None
    financial = deepcopy(catalog)
    financial['KR:001111']['facts'] = [{'value': 999}]
    assert engine._business_index_revision({}, financial) == baseline
    for field, value in (('name', '다른회사'), ('market', 'US'),
                         ('id', 'KR:003333'), ('source_names', ['합성회사', '다른상호'])):
        changed = deepcopy(catalog)
        changed['KR:001111'][field] = value
        assert engine._business_index_revision({}, changed) != baseline
    Clock.day = 14
    assert engine._business_index_revision({}, catalog) != baseline
    assert engine._business_index_revision({'kr_business_overview_public.json': {}}, catalog) is None
    assert engine._business_index_revision({}, {str(i): catalog['KR:001111'] for i in range(50001)}) is None
    engine._PROJECTED_PUBLIC_INDEX.clear()
    assert engine._PROJECTED_PUBLIC_INDEX._business_index is None
    assert engine._PROJECTED_PUBLIC_INDEX._business_revision is None


def test_business_market_context_nested_returns_do_not_mutate_reused_index(endpoint):
    from copy import deepcopy
    import sys

    engine = sys.modules['api.portfolio_core.portfolio_engine']

    def mutable_ids(value):
        seen, pending = set(), [value]
        while pending:
            current = pending.pop()
            if isinstance(current, (dict, list)) and id(current) not in seen:
                seen.add(id(current))
                pending.extend(current.values() if isinstance(current, dict) else current)
        return seen

    text = ('당사의 주요 매출처는 합성고객입니다. '
            '당사는 제품 가격이 환율 변동에 따라 변동합니다. '
            '당사는 전력을 구매하고 있습니다. '
            '당사는 항만 터미널을 운영하고 있습니다.')
    documents = {
        'universe_search.json': {'stocks': [
            {'ticker': '001111', 'market': 'KR', 'name': '합성회사'},
            {'ticker': '002222', 'market': 'KR', 'name': '합성고객'}]},
        'stock_report_public.json': {'stocks': [{
            'ticker': '001111', 'name': '합성회사',
            'facts': [{'metric': 'revenue', 'value': 100, 'unit': 'KRW',
                       'as_of': '2025-12-31', 'source': 'DART'}]}]},
        'kr_business_overview_public.json': {
            '_meta': {'count': 1, 'generated_at': '2026-10-12T00:00:00Z'},
            'rows': {'001111': {
                'name': '합성회사', 'text': text, 'chars': len(text),
                'fiscal_year': '2025', 'filed_at': '20260318',
                'report': '사업보고서 (2025.12)',
                'url': 'https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260318000001',
                'truncated': False}}},
        'macro_snapshot.json': {'macro': {'usd_krw': {
            'status': 'ok', 'value': 1400, 'change_pct': 0,
            'data_date': '2026-10-13'}}},
    }
    original = deepcopy(documents)
    positions = [{'ticker': '001111', 'market': 'KR'}]
    engine._reset_projection_cache_for_tests()
    try:
        first = engine.analyze_portfolio(
            positions, documents, public_bundle_revision='a' * 64)
        cached = engine._PROJECTED_PUBLIC_INDEX._business_index
        cached_context = cached['market_context']
        cached_before = deepcopy(cached_context)
        first_context = first['market_context']
        assert mutable_ids(first_context).isdisjoint(mutable_ids(cached_context))
        first_items = {item['id']: item for item in first_context['items']}
        for identifier in ('market:fx:usd_krw',
                           'market:power-context:electricity-input',
                           'market:infrastructure-context:port-operation'):
            ref = first_items[identifier]['filing_refs'][0]
            assert ref['channels']
            ref['channels'][0]['quote'] = 'synthetic-private-canary'
            ref['channels'].append({'synthetic_private_canary': True})
        assert cached_context == cached_before

        changed = deepcopy(documents)
        changed['stock_report_public.json']['stocks'][0]['facts'][0]['value'] = 200
        second = engine.analyze_portfolio(
            positions, changed, public_bundle_revision='b' * 64)
        assert engine._PROJECTED_PUBLIC_INDEX._business_index is cached
        assert second['companies'][0]['facts'][0]['value'] == 200
        assert first['companies'][0]['facts'][0]['value'] == 100
        assert 'synthetic-private-canary' not in repr(second)
        assert 'synthetic_private_canary' not in repr(second)
        assert mutable_ids(second['market_context']).isdisjoint(mutable_ids(cached_context))
        assert mutable_ids(second['market_context']).isdisjoint(mutable_ids(first_context))
        fresh = engine.analyze_portfolio(positions, changed)
        assert second['market_context'] == fresh['market_context']
        assert cached_context == cached_before
        assert documents == original
    finally:
        engine._reset_projection_cache_for_tests()
