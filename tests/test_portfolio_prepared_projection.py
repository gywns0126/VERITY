from __future__ import annotations

import base64
import gzip
import importlib
import json
from pathlib import Path
import sys
import types

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
