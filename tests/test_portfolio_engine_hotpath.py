"""Request-local public text reuse, with no selected-response cache."""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta
import importlib
import json
from pathlib import Path
import sys
import threading
import types
from unittest.mock import Mock

import pytest


CORE = Path(__file__).resolve().parents[1] / "vercel-api/api/portfolio_core"
POSITIONS = [{"market": "KR", "ticker": "001111"},
             {"market": "KR", "ticker": "002222"}]


@pytest.fixture
def engine(monkeypatch):
    package = types.ModuleType("engine_hotpath_test")
    package.__path__ = [str(CORE)]
    monkeypatch.setitem(sys.modules, package.__name__, package)
    module = importlib.import_module(package.__name__ + ".portfolio_engine")
    yield module
    module._reset_projection_cache_for_tests()
    for name in tuple(sys.modules):
        if name == package.__name__ or name.startswith(package.__name__ + "."):
            monkeypatch.delitem(sys.modules, name, raising=False)


@pytest.fixture
def documents(engine):
    ai = importlib.import_module(engine.__package__ + ".portfolio_ai_public")
    source = "source:dart:20260318000001"
    candidate = {
        "issuer_id": "KR:001111", "issuer_name": "합성제조사",
        "counterparty_id": "KR:002222", "counterparty_name": "합성고객사",
        "role": "customer", "quote": "주요 고객은 합성고객사입니다.",
        "source_id": source,
        "url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260318000001",
        "as_of": "2026-03-18", "status": "ai_candidate",
        "verification": "unreviewed-model-extraction", "evidence_scope": "historical-context",
        "current_validity": "not-inferred",
    }
    candidate["id"] = "automatic:ai:" + ai._digest(
        [source, candidate["issuer_id"], candidate["counterparty_id"], "customer"])[:24]
    candidate["revision"] = ai._digest(candidate)
    return {
        "universe_search.json": {"stocks": [
            {"ticker": "001111", "market": "KR", "name": "합성제조사"},
            {"ticker": "002222", "market": "KR", "name": "합성고객사"},
        ]},
        "stock_report_public.json": {"stocks": {"001111": {"name": "합성제조사", "facts": [
            {"metric": "revenue", "value": 123, "unit": "KRW",
             "as_of": "2025-12-31", "source": "DART"}]}}},
        "us_stock_report_public.json": {"stocks": {}},
        "member_map_ai_candidates.json": {"schema": "local-ai-review-v1",
            "candidates": [candidate],
            "coverage": {"input": 1, "accepted": 1, "rejected": 0, "skipped": 0}},
    }


def _bytes(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False).encode()


def _prepare(engine, documents):
    artifact = engine.build_prepared_business_index(documents)
    receipt = engine.prepared_business_publisher_receipt(artifact)
    engine.prepare_public_index(documents, "a" * 64, prepared_business_index=artifact,
        publisher_receipt=receipt,
        base_source_revision=artifact["base_projection"]["source_revision"])
    return artifact, receipt


def test_accepted_prepared_output_and_mutation_isolation(engine, documents, capsys):
    original = _bytes(documents)
    artifact, receipt = _prepare(engine, documents)
    assert "portfolio_prepared_projection status=accepted" in capsys.readouterr().err
    artifact_before, receipt_before = _bytes(artifact), _bytes(receipt)
    plain = engine.analyze_portfolio.__wrapped__(POSITIONS, documents, public_bundle_revision="a" * 64)
    cached = engine.analyze_portfolio(POSITIONS, documents, public_bundle_revision="a" * 64)
    assert cached["coverage"]["ai_review"]["status"] == "ready"
    assert _bytes(cached) == _bytes(plain)
    cached["companies"][0]["facts"].clear()
    cached["ai_review"]["candidates"][0]["quote"] = "local response edit"
    assert _bytes(engine.analyze_portfolio(POSITIONS, documents,
        public_bundle_revision="a" * 64)) == _bytes(plain)
    assert _bytes(documents) == original
    assert _bytes(artifact) == artifact_before
    assert _bytes(receipt) == receipt_before


def test_duplicate_checks_reuse_only_within_each_request(engine, documents, monkeypatch):
    _prepare(engine, documents)
    sources = importlib.import_module(engine.__package__ + ".portfolio_public_sources")
    original, calls = sources._safe_text_uncached, Counter()

    def counted(value, limit):
        calls[(value, limit)] += 1
        return original(value, limit)

    monkeypatch.setattr(sources, "_safe_text_uncached", counted)
    engine.analyze_portfolio.__wrapped__(POSITIONS, documents, public_bundle_revision="a" * 64)
    baseline_count = sum(calls.values())
    assert calls[("합성제조사", 160)] > 1
    for positions in (POSITIONS, POSITIONS[:1], POSITIONS):
        calls.clear()
        result = engine.analyze_portfolio(positions, documents, public_bundle_revision="a" * 64)
        assert calls[("합성제조사", 160)] == 1
        assert sum(calls.values()) < baseline_count
        assert len(result["companies"]) == len(positions)
        assert sources._TEXT_CACHE.get() is None


@pytest.mark.parametrize("quote", ["person@example.com", "<script>private</script>", "x" * 10001])
def test_rejected_public_text_still_rejects(engine, documents, quote):
    _prepare(engine, documents)
    changed = deepcopy(documents)
    changed["member_map_ai_candidates.json"]["candidates"][0]["quote"] = quote
    ai = importlib.import_module(engine.__package__ + ".portfolio_ai_public")
    row = changed["member_map_ai_candidates.json"]["candidates"][0]
    row["revision"] = ai._digest({k: v for k, v in row.items() if k != "revision"})
    # The selected join must recheck even an already prepared bundle.
    plain = engine.analyze_portfolio.__wrapped__(POSITIONS, changed, public_bundle_revision="a" * 64)
    result = engine.analyze_portfolio(POSITIONS, changed, public_bundle_revision="a" * 64)
    assert result["coverage"]["ai_review"]["status"] == "rejected"
    assert _bytes(result) == _bytes(plain)


def test_cache_restores_parent_context_even_after_join_exception(engine, documents, monkeypatch):
    _prepare(engine, documents)
    sources = importlib.import_module(engine.__package__ + ".portfolio_public_sources")
    calls = Counter()
    original = sources._safe_text_uncached

    def counted(value, limit):
        calls[(value, limit)] += 1
        return original(value, limit)

    def fail(*args, **kwargs):
        sources.safe_public_text("request marker", 160)
        sources.safe_public_text("request marker", 160)
        raise RuntimeError("synthetic join failure")

    monkeypatch.setattr(sources, "_safe_text_uncached", counted)
    monkeypatch.setattr(engine, "project_market_context", fail)
    with sources._temporary_public_text_cache():
        parent = sources._TEXT_CACHE.get()
        with pytest.raises(RuntimeError, match="synthetic join failure"):
            engine.analyze_portfolio(POSITIONS, documents, public_bundle_revision="a" * 64)
        assert sources._TEXT_CACHE.get() is parent
        sources.safe_public_text("request marker", 160)
        assert calls[("request marker", 160)] == 2
    assert sources._TEXT_CACHE.get() is None


def test_prepared_source_mismatch_keeps_fallback(engine, documents, capsys):
    artifact, receipt = _prepare(engine, documents)
    engine._reset_projection_cache_for_tests()
    engine.prepare_public_index(documents, "b" * 64, prepared_business_index=artifact,
        publisher_receipt=receipt, base_source_revision="f" * 64)
    assert "portfolio_prepared_projection status=fallback" in capsys.readouterr().err
    result = engine.analyze_portfolio(POSITIONS, documents, public_bundle_revision="b" * 64)
    assert _bytes(result) == _bytes(engine.analyze_portfolio.__wrapped__(
        POSITIONS, documents, public_bundle_revision="b" * 64))


def test_concurrent_selections_have_distinct_cleared_text_caches(engine, documents, monkeypatch):
    _prepare(engine, documents)
    sources = importlib.import_module(engine.__package__ + ".portfolio_public_sources")
    original = engine.project_market_context
    barrier = threading.Barrier(2, timeout=5)
    caches = []

    def overlapping_join(*args, **kwargs):
        caches.append(sources._TEXT_CACHE.get())
        barrier.wait()
        return original(*args, **kwargs)

    monkeypatch.setattr(engine, "project_market_context", overlapping_join)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda position: engine.analyze_portfolio(
            [position], documents, public_bundle_revision="a" * 64), POSITIONS))
    assert [result["companies"][0]["id"] for result in results] == ["KR:001111", "KR:002222"]
    assert len(caches) == 2 and caches[0] is not caches[1]
    assert all(cache.cache_info().currsize == 0 for cache in caches)
    assert sources._TEXT_CACHE.get() is None


@pytest.fixture
def contract_case(engine):
    helper = importlib.import_module(engine.__package__ + ".portfolio_contract_facts")
    receipt = "20260318000001"
    url = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=" + receipt
    html = """<html><head><title>합성제조사/단일판매ㆍ공급계약체결/(2026.03.18)</title></head>
    <body><div class="xforms"><table>
    <tr><td>1. 판매ㆍ공급계약 구분</td><td>제품공급</td></tr>
    <tr><td>- 체결계약명</td><td>합성장비 공급계약</td></tr>
    <tr><td>3. 계약상대</td><td>합성고객사</td></tr>
    <tr><td>5. 계약기간</td><td>시작일</td><td>2026-03-18</td></tr>
    <tr><td>종료일</td><td>2027-03-18</td></tr>
    <tr><td>7. 계약(수주)일자</td><td>2026-03-17</td></tr>
    </table></div></body></html>""".encode("euc-kr")
    fact = helper.parse_contract_facts(html, receipt_no=receipt, issuer_id="KR:001111",
        issuer_name="합성제조사", filed_on="2026-03-18", main_url=url,
        viewer_url="https://dart.fss.or.kr/report/viewer.do?rcpNo=" + receipt
            + "&dcmNo=12345678&eleId=0&offset=0&length=0&dtd=HTML",
        observed_at="2026-03-19T00:00:00Z")
    artifact = {"contract_facts": [fact], "documentFamilies": [], "contract_terminations": []}
    catalog = {
        "KR:001111": {"id": "KR:001111", "name": "합성제조사", "source_names": ["합성제조사"],
            "facts": [], "documents": [{"id": "DART:" + receipt, "url": url,
                "source": "DART", "kind": "disclosure", "as_of": "2026-03-18",
                "title": "단일판매ㆍ공급계약체결"}]},
        "KR:002222": {"id": "KR:002222", "name": "합성고객사", "source_names": ["합성고객사"],
            "facts": [], "documents": []},
    }
    return {"member_map_auto_evidence.json": artifact}, catalog


def test_contract_cache_reuses_equal_inputs_and_selected_results_are_isolated(engine, contract_case, monkeypatch):
    documents, catalog = contract_case
    original_documents, original_catalog = _bytes(documents), _bytes(catalog)
    built = Mock(wraps=engine.index_contract_events)
    monkeypatch.setattr(engine, "index_contract_events", built)
    cache = engine._ProjectedPublicIndexCache()
    first = cache._contracts(documents, catalog)
    assert len(first["events"]) == 1
    changed = deepcopy(documents)
    changed["macro_snapshot.json"] = {"changed": "public context"}
    changed["member_map_auto_evidence.json"]["unrelated_public_field"] = 1
    new_catalog = deepcopy(catalog)
    new_catalog["KR:001111"]["facts"] = [{"public financial fact": 321}]
    second = cache._contracts(changed, new_catalog)
    assert second is first
    built.assert_called_once()
    selected = engine.select_contract_events(second, ["KR:001111"])
    selected["items"][0]["documents"][0]["title"] = "local response edit"
    assert _bytes(first) == _bytes(built._mock_wraps(documents["member_map_auto_evidence.json"], list(catalog.values())))
    assert _bytes(documents) == original_documents and _bytes(catalog) == original_catalog


@pytest.mark.parametrize("change", ["contract_facts", "documentFamilies", "contract_terminations",
    "name", "source_names", "document_title", "document_url", "document_date", "document_capture",
    "document_added", "document_removed", "alias_owner", "catalog_order", "document_order"])
def test_contract_cache_invalidates_every_consumed_input(engine, contract_case, monkeypatch, change):
    documents, catalog = contract_case
    original = engine.index_contract_events
    built = Mock(wraps=original)
    monkeypatch.setattr(engine, "index_contract_events", built)
    cache = engine._ProjectedPublicIndexCache()
    cache._contracts(documents, catalog)
    changed, companies = deepcopy(documents), deepcopy(catalog)
    company = companies["KR:001111"]
    if change in ("contract_facts", "documentFamilies", "contract_terminations"):
        changed["member_map_auto_evidence.json"][change].append({})
    elif change == "name":
        company["name"] = "다른이름"
    elif change == "source_names":
        company["source_names"] = ["다른이름"]
    elif change == "alias_owner":
        companies["KR:003333"] = {"id": "KR:003333", "name": "합성고객사",
                                 "source_names": ["합성고객사"], "documents": []}
    elif change == "document_added":
        companies["KR:002222"]["documents"] = deepcopy(company["documents"])
    elif change == "document_removed":
        company["documents"] = []
    elif change == "catalog_order":
        companies = dict(reversed(list(companies.items())))
    elif change == "document_order":
        other = {**company["documents"][0], "id": "DART:20260318000002"}
        company["documents"] = [other, *company["documents"]]
    else:
        key, value = {"document_title": ("title", "다른공시"),
            "document_url": ("url", "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260318000002"),
            "document_date": ("as_of", "2026-03-19"),
            "document_capture": ("capture_archive", "retained-public-capture")}[change]
        company["documents"][0][key] = value
    result = cache._contracts(changed, companies)
    assert built.call_count == 2
    assert _bytes(result) == _bytes(original(changed["member_map_auto_evidence.json"], list(companies.values())))


def test_contract_cache_is_latest_only_cleared_and_day_bound(engine, contract_case, monkeypatch):
    documents, catalog = contract_case
    built = Mock(wraps=engine.index_contract_events)
    monkeypatch.setattr(engine, "index_contract_events", built)
    cache = engine._ProjectedPublicIndexCache()
    cache._contracts(documents, catalog)
    changed = deepcopy(catalog)
    changed["KR:002222"]["source_names"].append("다른공개별칭")
    cache._contracts(documents, changed)
    cache._contracts(documents, catalog)
    assert built.call_count == 3  # No historical catalog/index accumulation.

    class Tomorrow:
        @staticmethod
        def now(tz=None):
            return datetime.now(tz) + timedelta(days=1)

    monkeypatch.setattr(engine, "datetime", Tomorrow)
    cache._contracts(documents, catalog)
    assert built.call_count == 4
    cache.clear()
    assert cache._contract_index is None and cache._contract_revision is None
    cache._contracts(documents, catalog)
    assert built.call_count == 5


def test_changing_public_bundle_reuses_contracts_through_engine_lock(engine, documents, monkeypatch):
    artifact, receipt = _prepare(engine, documents)
    built = Mock(wraps=engine.index_contract_events)
    monkeypatch.setattr(engine, "index_contract_events", built)
    changed = deepcopy(documents)
    changed["macro_snapshot.json"] = {}
    first = engine._PROJECTED_PUBLIC_INDEX._index["contract_events"]
    first_news = engine._PROJECTED_PUBLIC_INDEX._index["news_names"]
    second = engine.prepare_public_index(changed, "b" * 64,
        prepared_business_index=artifact, publisher_receipt=receipt,
        base_source_revision=artifact["base_projection"]["source_revision"])
    assert second["contract_events"] is first
    assert second["news_names"] is first_news
    built.assert_not_called()
    response = _bytes(engine.analyze_portfolio(POSITIONS, changed, public_bundle_revision="b" * 64))
    engine._reset_projection_cache_for_tests()
    full = engine.prepare_public_index(changed, "b" * 64,
        prepared_business_index=artifact, publisher_receipt=receipt,
        base_source_revision=artifact["base_projection"]["source_revision"])
    assert _bytes(full["contract_events"]) == _bytes(second["contract_events"])
    assert _bytes(engine.analyze_portfolio(POSITIONS, changed, public_bundle_revision="b" * 64)) == response


@pytest.mark.parametrize("rows", [None, [{}] * 1001])
def test_malformed_or_unbounded_contract_inputs_never_reuse_prior_index(engine, contract_case, monkeypatch, rows):
    documents, catalog = contract_case
    built = Mock(wraps=engine.index_contract_events)
    monkeypatch.setattr(engine, "index_contract_events", built)
    cache = engine._ProjectedPublicIndexCache()
    cache._contracts(documents, catalog)
    changed = deepcopy(documents)
    changed["member_map_auto_evidence.json"]["contract_facts"] = rows
    cache._contracts(changed, catalog)
    cache._contracts(changed, catalog)
    assert built.call_count == 3
    assert cache._contract_index is None and cache._contract_revision is None


def test_us_names_invalidate_contracts_but_us_documents_do_not(engine, contract_case, monkeypatch):
    documents, catalog = contract_case
    catalog["US:SYNTH"] = {"id": "US:SYNTH", "name": "Synthetic Company", "documents": []}
    original = engine.index_contract_events
    built = Mock(wraps=original)
    monkeypatch.setattr(engine, "index_contract_events", built)
    cache = engine._ProjectedPublicIndexCache()
    first = cache._contracts(documents, catalog)
    changed = deepcopy(catalog)
    changed["US:SYNTH"]["documents"] = [{"id": "unconsumed-public-us-document"}]
    assert cache._contracts(documents, changed) is first
    assert built.call_count == 1
    changed["US:SYNTH"]["name"] = "합성제조사"
    actual = cache._contracts(documents, changed)
    assert built.call_count == 2
    assert _bytes(actual) == _bytes(original(documents["member_map_auto_evidence.json"], list(changed.values())))
