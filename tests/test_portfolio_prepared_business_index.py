"""Public-only prepared business index and private-response parity."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import importlib
import io
import json
import os
from pathlib import Path
import sys
import types
from unittest.mock import Mock

import pytest


CORE = Path(__file__).resolve().parents[1] / "vercel-api" / "api" / "portfolio_core"


@pytest.fixture
def engine(monkeypatch):
    package = types.ModuleType("prepared_business_test")
    package.__path__ = [str(CORE)]
    monkeypatch.setitem(sys.modules, package.__name__, package)
    module = importlib.import_module(package.__name__ + ".portfolio_engine")
    module._reset_projection_cache_for_tests()
    yield module
    for name in tuple(sys.modules):
        if name == package.__name__ or name.startswith(package.__name__ + "."):
            monkeypatch.delitem(sys.modules, name, raising=False)


@pytest.fixture
def documents():
    text = "당사의 주요 매출처는 합성고객, 다른업체입니다. 당사는 원재료를 구매하고 있습니다."
    return {
        "universe_search.json": {"stocks": [
            {"ticker": "001111", "market": "KR", "name": "합성회사"},
            {"ticker": "002222", "market": "KR", "name": "합성고객"},
        ]},
        "kr_business_overview_public.json": {
            "_meta": {"count": 1, "generated_at": "2026-10-12T00:00:00Z"},
            "rows": {"001111": {
                "name": "합성회사", "text": text, "chars": len(text),
                "fiscal_year": "2025", "filed_at": "20260318",
                "report": "사업보고서 (2025.12)",
                "url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260318000001",
                "truncated": False,
            }},
        },
    }


def _bytes(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False).encode()


def test_prepared_public_index_skips_matching_and_preserves_response(engine, documents, monkeypatch, caplog):
    positions = [{"ticker": "001111", "market": "KR"},
                 {"ticker": "002222", "market": "KR"}]
    before = _bytes(engine.analyze_portfolio(positions, documents, public_bundle_revision="a" * 64))
    artifact = engine.build_prepared_business_index(documents)
    assert artifact["index"]["materials"]
    assert "portfolio_company_ids" not in _bytes(artifact).decode()
    receipt = engine.prepared_business_publisher_receipt(artifact)
    engine._reset_projection_cache_for_tests()
    monkeypatch.setattr(engine, "_business_material_index", Mock(side_effect=AssertionError("matcher ran")))
    with caplog.at_level("INFO", logger=engine.__name__):
        public_index = engine.prepare_public_index(
            documents, "a" * 64, prepared_business_index=artifact, publisher_receipt=receipt
        )
    assert [record.message for record in caplog.records if record.name == engine.__name__] == [
        "portfolio_prepared_business status=accepted"
    ]
    assert public_index["business_materials"] == artifact["index"]
    after = _bytes(engine.analyze_portfolio(positions, documents, public_bundle_revision="a" * 64))
    assert after == before


@pytest.mark.parametrize("mutation", ["missing-receipt", "stale-receipt", "wrong-digest",
                                     "wrong-source", "wrong-version", "wrong-code",
                                     "changed-input", "broken-links", "extra-private-field"])
def test_invalid_preparation_uses_existing_matcher(engine, documents, monkeypatch, mutation):
    artifact = engine.build_prepared_business_index(documents)
    candidate, inputs = deepcopy(artifact), deepcopy(documents)
    receipt = engine.prepared_business_publisher_receipt(candidate)
    if mutation == "missing-receipt":
        receipt = None
    elif mutation == "stale-receipt":
        receipt["utc_day"] = "2000-01-01"
    elif mutation == "wrong-digest":
        candidate["index"]["coverage"]["status"] = "forged"
    elif mutation == "wrong-source":
        candidate["source_revision"] = "0" * 64
        receipt = engine.prepared_business_publisher_receipt(candidate)
    elif mutation == "wrong-version":
        candidate["matcher_version"] = "old"
        receipt = engine.prepared_business_publisher_receipt(candidate)
    elif mutation == "wrong-code":
        candidate["implementation_sha256"] = "0" * 64
        receipt = engine.prepared_business_publisher_receipt(candidate)
    elif mutation == "changed-input":
        inputs["universe_search.json"]["stocks"][1]["name"] = "다른고객"
    elif mutation == "broken-links":
        candidate["index"]["by_company"] = {}
        receipt = engine.prepared_business_publisher_receipt(candidate)
    elif mutation == "extra-private-field":
        next(iter(candidate["index"]["materials"].values()))["private_note"] = "never publish"
        receipt = engine.prepared_business_publisher_receipt(candidate)
    build = Mock(wraps=engine._business_material_index)
    monkeypatch.setattr(engine, "_business_material_index", build)
    prepared = engine.prepare_public_index(
        inputs, "b" * 64, prepared_business_index=candidate, publisher_receipt=receipt
    )
    assert build.call_count == 1
    assert prepared["business_materials"]["coverage"]["status"] != "forged"


def test_utc_day_invalidates_prepared_business_index(engine, documents, monkeypatch):
    artifact = engine.build_prepared_business_index(documents)
    receipt = engine.prepared_business_publisher_receipt(artifact)
    today = datetime.now(timezone.utc).date()

    class Tomorrow:
        @classmethod
        def now(cls, tz):
            assert tz is timezone.utc
            return datetime(today.year, today.month, today.day, tzinfo=tz) + timedelta(days=1)

    monkeypatch.setattr(engine, "datetime", Tomorrow)
    build = Mock(wraps=engine._business_material_index)
    monkeypatch.setattr(engine, "_business_material_index", build)
    engine.prepare_public_index(documents, "c" * 64,
                                prepared_business_index=artifact, publisher_receipt=receipt)
    assert build.call_count == 1


def test_saved_16_public_artifacts_preserve_response_bytes(engine):
    root = os.environ.get("PORTFOLIO_REPLAY_PUBLIC_DIR")
    if not root:
        pytest.skip("set PORTFOLIO_REPLAY_PUBLIC_DIR for local public-artifact replay")
    from prepared_business_test.portfolio_public_sources import PUBLIC_SOURCE_FILES

    source_dir = Path(root)
    names = [name for name in PUBLIC_SOURCE_FILES if (source_dir / name).is_file()]
    assert len(names) == len(PUBLIC_SOURCE_FILES) == 16
    documents = {name: json.loads((source_dir / name).read_text(encoding="utf-8"))
                 for name in names}
    positions = [{"ticker": "000660", "market": "KR"},
                 {"ticker": "TSM", "market": "US"}]
    baseline = _bytes(engine.analyze_portfolio(positions, documents,
                                               public_bundle_revision="d" * 64))
    full_index = engine._PROJECTED_PUBLIC_INDEX.get(documents, "d" * 64)
    artifact = engine.build_prepared_business_index(documents)
    from prepared_business_test.portfolio_prepared_business import BUSINESS_SOURCE_FILES
    assert len(BUSINESS_SOURCE_FILES) == 6
    assert artifact["source_revision"] == engine._business_index_revision(
        documents, full_index["by_id"]
    )
    assert artifact["index"] == full_index["business_materials"]
    engine._reset_projection_cache_for_tests()
    original = engine._business_material_index

    def unexpected_match(*_args, **_kwargs):
        raise AssertionError("saved-bundle matcher ran despite accepted preparation")

    engine._business_material_index = unexpected_match
    try:
        engine.prepare_public_index(documents, "d" * 64, prepared_business_index=artifact,
                                    publisher_receipt=engine.prepared_business_publisher_receipt(artifact))
    finally:
        engine._business_material_index = original
    prepared = _bytes(engine.analyze_portfolio(positions, documents,
                                               public_bundle_revision="d" * 64))
    assert prepared == baseline


def test_fixed_public_transport_is_bounded_and_never_reads_member_inputs(engine, documents):
    helper = importlib.import_module(engine.__package__ + ".portfolio_prepared_business")
    artifact = engine.build_prepared_business_index(documents)
    receipt = engine.prepared_business_publisher_receipt(artifact)
    requested = []

    def reader(name, limit):
        requested.append((name, limit))
        return artifact if name == helper.ARTIFACT_FILENAME else receipt

    actual_artifact, actual_receipt = helper.fetch_publisher_prepared_business(_reader=reader)
    assert sorted(requested) == sorted([
        (helper.ARTIFACT_FILENAME, helper.ARTIFACT_MAX_BYTES),
        (helper.RECEIPT_FILENAME, helper.RECEIPT_MAX_BYTES),
    ])
    assert actual_artifact == artifact and actual_receipt == receipt
    actual_artifact["source_revision"] = "caller edit"
    assert artifact["source_revision"] != "caller edit"

    def missing(_name, _limit):
        raise TimeoutError("fixed public source unavailable")

    assert helper.fetch_publisher_prepared_business(_reader=missing) == (None, None)


def test_failed_fixed_public_reads_are_negative_cached_for_at_most_one_minute(
        engine, documents, monkeypatch, caplog):
    helper = importlib.import_module(engine.__package__ + ".portfolio_prepared_business")
    helper._FETCH_CACHE = None
    calls = []
    clock = [100.0]

    def missing(name, _limit):
        calls.append(name)
        raise TimeoutError("unavailable")

    monkeypatch.setattr(helper, "_read_fixed_public_json", missing)
    monkeypatch.setattr(helper.time, "monotonic", lambda: clock[0])
    assert helper.fetch_publisher_prepared_business() == (None, None)
    assert helper.fetch_publisher_prepared_business() == (None, None)
    assert len(calls) == 2
    with caplog.at_level("INFO", logger=engine.__name__):
        engine.prepare_public_index(documents, "e" * 64,
                                    prepared_business_index=None, publisher_receipt=None)
    assert [record.message for record in caplog.records if record.name == engine.__name__] == [
        "portfolio_prepared_business status=fallback_missing"
    ]
    clock[0] = 160.0
    assert helper.fetch_publisher_prepared_business() == (None, None)
    assert len(calls) == 4


@pytest.mark.parametrize("payload", [
    b'{"invalid":',
    b"[" * 40 + b"0" + b"]" * 40,
    b"[" * 1200 + b"0" + b"]" * 1200,
])
def test_malformed_or_deep_public_json_falls_back(engine, documents, monkeypatch, payload):
    helper = importlib.import_module(engine.__package__ + ".portfolio_prepared_business")

    class Response(io.BytesIO):
        status = 200
        headers = {}

        def geturl(self):
            return helper.PUBLIC_BLOB_BASE_URL + helper.ARTIFACT_FILENAME

    class Opener:
        def open(self, request, timeout):
            assert timeout == helper.FETCH_TIMEOUT_SECONDS == 2
            assert request.full_url == helper.PUBLIC_BLOB_BASE_URL + helper.ARTIFACT_FILENAME
            return Response(payload)

    monkeypatch.setattr(helper.urllib.request, "build_opener", lambda *_args: Opener())
    candidate, receipt = helper.fetch_publisher_prepared_business(
        _reader=lambda _name, limit: helper._read_fixed_public_json(
            helper.ARTIFACT_FILENAME, limit))
    assert (candidate, receipt) == (None, None)
    fallback = engine.prepare_public_index(documents, "f" * 64,
                                           prepared_business_index=candidate,
                                           publisher_receipt=receipt)
    assert fallback["business_materials"]["coverage"]["status"] == "complete"


def test_copy_and_validation_recursion_fall_back(engine, documents, monkeypatch):
    helper = importlib.import_module(engine.__package__ + ".portfolio_prepared_business")
    artifact = engine.build_prepared_business_index(documents)
    receipt = engine.prepared_business_publisher_receipt(artifact)
    monkeypatch.setattr(helper, "deepcopy", Mock(side_effect=RecursionError("deep")))
    assert helper.fetch_publisher_prepared_business(
        _reader=lambda name, _limit: artifact if name == helper.ARTIFACT_FILENAME else receipt
    ) == (None, None)
    helper._FETCH_CACHE = (artifact, receipt)
    helper._FETCH_EXPIRES_AT = helper.time.monotonic() + 60
    assert helper.fetch_publisher_prepared_business() == (None, None)

    deep = []
    node = deep
    for _ in range(40):
        child = []
        node.append(child)
        node = child
    artifact["index"]["market_context"]["coverage"]["deep"] = deep
    receipt = engine.prepared_business_publisher_receipt(artifact)
    build = Mock(wraps=engine._business_material_index)
    monkeypatch.setattr(engine, "_business_material_index", build)
    engine.prepare_public_index(documents, "a" * 64,
                                prepared_business_index=artifact, publisher_receipt=receipt)
    assert build.call_count == 1
