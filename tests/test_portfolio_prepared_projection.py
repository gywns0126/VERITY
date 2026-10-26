from __future__ import annotations

import base64
import gzip
import importlib
import json
from pathlib import Path
import sys
import types
from copy import deepcopy
from datetime import datetime, timedelta
from unittest.mock import Mock

import pytest


CORE = Path(__file__).resolve().parents[1] / "vercel-api" / "api" / "portfolio_core"


@pytest.fixture
def engine(monkeypatch):
    package = types.ModuleType("prepared_projection_test")
    package.__path__ = [str(CORE)]
    monkeypatch.setitem(sys.modules, package.__name__, package)
    module = importlib.import_module(package.__name__ + ".portfolio_engine")
    module._reset_projection_cache_for_tests()
    yield module
    module._reset_projection_cache_for_tests()
    for name in tuple(sys.modules):
        if name == package.__name__ or name.startswith(package.__name__ + "."):
            monkeypatch.delitem(sys.modules, name, raising=False)


@pytest.fixture
def documents():
    return {
        "universe_search.json": {"stocks": [
            {"ticker": "000001", "market": "KR", "name": "합성회사", "sector": "반도체"},
            {"ticker": "AAPL", "market": "US", "name": "Synthetic Systems"},
        ]},
        "stock_report_public.json": {"stocks": {"000001": {
            "name": "합성회사", "facts": [{"metric": "revenue", "value": 123,
                "unit": "KRW", "as_of": "2025-12-31", "source": "DART"}],
        }}},
        "us_stock_report_public.json": {"stocks": {"AAPL": {
            "name": "Synthetic Systems", "facts": [{"metric": "revenue", "value": 456,
                "unit": "USD", "as_of": "2025-12-31", "source": "SEC"}],
        }}},
    }


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True,
                      separators=(",", ":"), allow_nan=False,
                      default=lambda item: sorted(item) if isinstance(item, (set, frozenset))
                      else TypeError(type(item).__name__)).encode("utf-8")


def _seed(engine, documents):
    helper = importlib.import_module(engine.__package__ + ".portfolio_prepared_business")
    sources = importlib.import_module(engine.__package__ + ".portfolio_public_sources")
    artifact = engine.build_prepared_business_index(documents)
    receipt = engine.prepared_business_publisher_receipt(artifact)
    revisions = {name: helper.artifact_sha256(documents[name])
                 for name in sources.BASE_PROJECTION_FILES}
    source_revision = sources.base_projection_revision(revisions)
    return helper, sources, artifact, receipt, source_revision


def _run(engine, documents, artifact, receipt, source_revision):
    engine._reset_projection_cache_for_tests()
    return engine.prepare_public_index(
        documents, "a" * 64, prepared_business_index=artifact,
        publisher_receipt=receipt, base_source_revision=source_revision,
    )


def _replace_seed_payload(artifact, raw):
    artifact["base_projection"]["data"] = base64.b64encode(gzip.compress(raw, mtime=0)).decode("ascii")


def test_canonical_first_three_source_seed_is_accepted(engine, documents, capsys):
    helper, sources, artifact, receipt, source_revision = _seed(engine, documents)
    assert set(sources.BASE_PROJECTION_FILES) == set(documents)
    assert artifact["base_projection"]["source_revision"] == source_revision
    index = _run(engine, documents, artifact, receipt, source_revision)
    assert capsys.readouterr().err.splitlines()[0] == "portfolio_prepared_projection status=accepted"
    assert index["by_id"]["KR:000001"]["facts"][0]["source"] == "DART"
    assert index["by_id"]["US:AAPL"]["facts"][0]["source"] == "SEC"
    rows = helper.checked_base_projection(artifact, receipt, source_revision)
    assert _canonical(rows) == gzip.decompress(base64.b64decode(artifact["base_projection"]["data"]))


@pytest.mark.parametrize("mismatch", ["receipt", "code", "day", "source"])
def test_receipt_code_day_and_source_mismatch_fall_back(engine, documents, mismatch, capsys):
    helper, _sources, artifact, receipt, source_revision = _seed(engine, documents)
    if mismatch == "receipt":
        receipt["artifact_sha256"] = "0" * 64
    elif mismatch == "code":
        artifact["implementation_sha256"] = "0" * 64
        receipt = engine.prepared_business_publisher_receipt(artifact)
    elif mismatch == "day":
        artifact["utc_day"] = "2000-01-01"
        receipt = engine.prepared_business_publisher_receipt(artifact)
    else:
        source_revision = "f" * 64
    index = _run(engine, documents, artifact, receipt, source_revision)
    assert "portfolio_prepared_projection status=fallback" in capsys.readouterr().err
    assert set(index["by_id"]) == {"KR:000001", "US:AAPL"}
    assert helper.checked_base_projection(artifact, receipt, source_revision) is None


@pytest.mark.parametrize("corruption", ["malformed", "concatenated", "over_max"])
def test_malformed_concatenated_and_over_limit_streams_fall_back(
        engine, documents, monkeypatch, corruption, capsys):
    helper, _sources, artifact, receipt, source_revision = _seed(engine, documents)
    raw = gzip.decompress(base64.b64decode(artifact["base_projection"]["data"]))
    if corruption == "malformed":
        artifact["base_projection"]["data"] = "%%%"
    elif corruption == "concatenated":
        packed = gzip.compress(raw, mtime=0) + gzip.compress(b"[]", mtime=0)
        artifact["base_projection"]["data"] = base64.b64encode(packed).decode("ascii")
    else:
        monkeypatch.setattr(helper, "_BASE_MAX_BYTES", max(1, len(raw) - 1))
    receipt = engine.prepared_business_publisher_receipt(artifact)
    index = _run(engine, documents, artifact, receipt, source_revision)
    assert "portfolio_prepared_projection status=fallback" in capsys.readouterr().err
    assert set(index["by_id"]) == {"KR:000001", "US:AAPL"}
    assert helper.checked_base_projection(artifact, receipt, source_revision) is None


@pytest.mark.parametrize("corruption", ["duplicate_id", "extra_member_field"])
def test_duplicate_identity_and_extra_member_field_are_rejected(
        engine, documents, corruption, capsys):
    helper, _sources, artifact, receipt, source_revision = _seed(engine, documents)
    rows = json.loads(gzip.decompress(base64.b64decode(artifact["base_projection"]["data"])))
    if corruption == "duplicate_id":
        rows.append(dict(rows[0]))
    else:
        rows[0]["member_id"] = "synthetic-only"
    _replace_seed_payload(artifact, _canonical(rows))
    receipt = engine.prepared_business_publisher_receipt(artifact)
    index = _run(engine, documents, artifact, receipt, source_revision)
    assert "portfolio_prepared_projection status=fallback" in capsys.readouterr().err
    assert set(index["by_id"]) == {"KR:000001", "US:AAPL"}
    assert helper.checked_base_projection(artifact, receipt, source_revision) is None


def test_live_disclosure_and_calendar_merge_match_full_projection_and_isolate_mutation(
        engine, documents):
    documents["public_disclosure_feed.json"] = {"items": [{
        "ticker": "000001", "market": "KR", "name": "합성회사",
        "disclosures": [{"title": "합성 정기공시", "date": "2026-10-20",
            "source_url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20261020000001"}],
    }]}
    documents["calendar_public.json"] = {"events": [{
        "ticker": "000001", "market": "KR", "type": "disclosure",
        "date": "2026-10-21", "date_estimated": False, "title": "합성 일정공시",
        "url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20261021000001",
    }]}
    original_documents = _canonical(documents)
    _helper, _sources, artifact, receipt, source_revision = _seed(engine, documents)
    seeded = _run(engine, documents, artifact, receipt, source_revision)
    seeded_response = engine.analyze_portfolio(
        [{"ticker": "000001", "market": "KR"}, {"ticker": "AAPL", "market": "US"}],
        documents, public_bundle_revision="a" * 64,
    )
    response_before_mutation = _canonical(seeded_response)
    seeded_response["companies"][0]["facts"].clear()
    assert _canonical(engine.analyze_portfolio(
        [{"ticker": "000001", "market": "KR"}, {"ticker": "AAPL", "market": "US"}],
        documents, public_bundle_revision="a" * 64,
    )) == response_before_mutation
    assert len(seeded["by_id"]["KR:000001"]["documents"]) == 2
    engine._reset_projection_cache_for_tests()
    full = engine.prepare_public_index(documents, "a" * 64)
    full_response = engine.analyze_portfolio(
        [{"ticker": "000001", "market": "KR"}, {"ticker": "AAPL", "market": "US"}],
        documents, public_bundle_revision="a" * 64,
    )
    assert _canonical(seeded) == _canonical(full)
    assert response_before_mutation == _canonical(full_response)
    assert _canonical(documents) == original_documents


def test_missing_first_three_sources_keeps_base_projection_disabled(engine, documents):
    helper = importlib.import_module(engine.__package__ + ".portfolio_prepared_business")
    partial = {"universe_search.json": documents["universe_search.json"]}
    artifact = engine.build_prepared_business_index(partial)
    assert artifact["base_projection"] is None
    assert helper.pack_base_projection(partial) is None
    index = engine.prepare_public_index(partial, "b" * 64,
                                        prepared_business_index=artifact,
                                        publisher_receipt=engine.prepared_business_publisher_receipt(artifact))
    assert set(index["by_id"]) == {"KR:000001", "US:AAPL"}


def test_changed_live_feed_reuses_only_stable_public_subindexes(engine, documents, monkeypatch):
    documents["stock_flow_5d.json"] = {"flows": {"000001": [{
        "date": "2026-10-20", "foreign_net": 1, "inst_net": 2}]}}
    helper, _sources, artifact, receipt, source_revision = _seed(engine, documents)
    first = _run(engine, documents, artifact, receipt, source_revision)
    template = engine._PROJECTED_PUBLIC_INDEX._base_template
    # Check the FIRST build too: aliases/flows must not mutate the template.
    template_bytes = _canonical(helper.checked_base_projection(artifact, receipt, source_revision))
    assert _canonical(template) == template_bytes
    changed = deepcopy(documents)
    changed["public_disclosure_feed.json"] = {"items": [{
        "ticker": "000001", "market": "KR", "name": "합성회사",
        "disclosures": [{"title": "새 합성 공시", "date": "2026-10-21",
            "source_url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20261021000001"}],
    }]}
    changed["stock_flow_5d.json"]["flows"]["000001"][0]["foreign_net"] = 7
    positions = [{"ticker": "000001", "market": "KR"}, {"ticker": "AAPL", "market": "US"}]
    with monkeypatch.context() as scoped:
        # Failed/unavailable later publisher reads cannot erase previously
        # checked same-source public templates. No re-decode or alias rebuild.
        scoped.setattr(engine, "checked_base_projection", Mock(side_effect=AssertionError("decoded again")))
        scoped.setattr(engine, "checked_business_index", Mock(side_effect=AssertionError("receipt checked again")))
        scoped.setattr(engine, "public_news_name_catalog", Mock(side_effect=AssertionError("aliases rebuilt")))
        second = engine.prepare_public_index(changed, "b" * 64, base_source_revision=source_revision)
        assert second["business_materials"] is first["business_materials"]
        assert second["news_names"] is first["news_names"]
        assert second["by_id"]["KR:000001"]["documents"][0]["as_of"] == "2026-10-21"
        assert _canonical(template) == template_bytes
        response = engine.analyze_portfolio(positions, changed, public_bundle_revision="b" * 64)
        response_bytes = _canonical(response)
        response["companies"][0]["facts"][0]["value"] = -999
        response["companies"][0]["document_ids"].clear()
        response["documents"][0]["title"] = "private local edit"
        assert _canonical(engine.analyze_portfolio(
            positions, changed, public_bundle_revision="b" * 64)) == response_bytes
        assert _canonical(template) == template_bytes
    engine._reset_projection_cache_for_tests()
    full = engine.prepare_public_index(changed, "b" * 64)
    assert _canonical(full) == _canonical(second)
    assert _canonical(engine.analyze_portfolio(
        positions, changed, public_bundle_revision="b" * 64)) == response_bytes


def test_base_source_change_invalidates_template_and_aliases(engine, documents, monkeypatch):
    _helper, sources, artifact, receipt, revision = _seed(engine, documents)
    _run(engine, documents, artifact, receipt, revision)
    original = engine.public_news_name_catalog
    calls = Mock(wraps=original)
    monkeypatch.setattr(engine, "public_news_name_catalog", calls)
    changed = deepcopy(documents)
    changed["universe_search.json"]["stocks"][0]["name_ko"] = "새 합성 별칭"
    revisions = {name: engine.prepared_business_index_sha256(changed[name])
                 for name in sources.BASE_PROJECTION_FILES}
    index = engine.prepare_public_index(changed, "c" * 64,
        prepared_business_index=artifact, publisher_receipt=receipt,
        base_source_revision=sources.base_projection_revision(revisions))
    calls.assert_called_once()
    assert "새 합성 별칭" in {row["name"] for row in original(changed, list(index["by_id"].values()))}
    assert index["by_id"]["KR:000001"]["facts"]


def test_missing_base_binding_never_reuses_localized_news_aliases(engine, documents, monkeypatch):
    calls = Mock(wraps=engine.public_news_name_catalog)
    monkeypatch.setattr(engine, "public_news_name_catalog", calls)
    first = engine.prepare_public_index(documents, "d" * 64)
    changed = deepcopy(documents)
    changed["universe_search.json"]["stocks"][0]["name_ko"] = "새 합성 별칭"
    second = engine.prepare_public_index(changed, "e" * 64)
    assert calls.call_count == 2
    assert first["news_names"] != second["news_names"]


def test_cached_base_cannot_cross_the_publisher_utc_day(engine, documents, monkeypatch, capsys):
    helper, _sources, artifact, receipt, revision = _seed(engine, documents)
    _run(engine, documents, artifact, receipt, revision)
    capsys.readouterr()

    class Tomorrow:
        @staticmethod
        def now(tz=None):
            return datetime.now(tz) + timedelta(days=1)

    monkeypatch.setattr(engine, "datetime", Tomorrow)
    monkeypatch.setattr(helper, "datetime", Tomorrow)
    checked = Mock(wraps=engine.checked_base_projection)
    monkeypatch.setattr(engine, "checked_base_projection", checked)
    engine.prepare_public_index(documents, "f" * 64,
        prepared_business_index=artifact, publisher_receipt=receipt, base_source_revision=revision)
    checked.assert_called_once()
    assert "portfolio_prepared_projection status=fallback" in capsys.readouterr().err
