"""Public-only prepared business index and private-response parity."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import importlib
import io
import json
import logging
import os
from pathlib import Path
import sys
import threading
import time
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


def test_prepared_public_index_skips_matching_and_preserves_response(engine, documents, monkeypatch, capsys):
    positions = [{"ticker": "001111", "market": "KR"},
                 {"ticker": "002222", "market": "KR"}]
    before = _bytes(engine.analyze_portfolio(positions, documents, public_bundle_revision="a" * 64))
    artifact = engine.build_prepared_business_index(documents)
    assert artifact["index"]["materials"]
    assert "portfolio_company_ids" not in _bytes(artifact).decode()
    receipt = engine.prepared_business_publisher_receipt(artifact)
    engine._reset_projection_cache_for_tests()
    monkeypatch.setattr(engine, "_business_material_index", Mock(side_effect=AssertionError("matcher ran")))
    capsys.readouterr()
    previous_disable = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        public_index = engine.prepare_public_index(
            documents, "a" * 64, prepared_business_index=artifact, publisher_receipt=receipt
        )
    finally:
        logging.disable(previous_disable)
    assert capsys.readouterr().err == "portfolio_prepared_business status=accepted\n"
    assert public_index["business_materials"] == artifact["index"]
    after = _bytes(engine.analyze_portfolio(positions, documents, public_bundle_revision="a" * 64))
    assert after == before


def test_prepared_fetch_is_once_per_revision_under_concurrent_requests(engine, documents):
    artifact = engine.build_prepared_business_index(documents)
    receipt = engine.prepared_business_publisher_receipt(artifact)
    calls = []
    start = threading.Barrier(4, timeout=5)

    def fetch():
        calls.append(True)
        time.sleep(0.02)
        return artifact, receipt

    def prepare(_):
        start.wait()
        return engine.prepare_public_index(
            documents, "a" * 64, prepared_business_fetcher=fetch
        )

    with ThreadPoolExecutor(max_workers=4) as pool:
        indexes = list(pool.map(prepare, range(4)))
    assert len(calls) == 1
    assert all(index is indexes[0] for index in indexes)
    assert indexes[0]["business_materials"] == artifact["index"]


def test_published_json_key_order_does_not_change_links_or_accept_duplicates(engine, documents):
    second = deepcopy(documents["kr_business_overview_public.json"]["rows"]["001111"])
    second.update(name="합성제조사", filed_at="20260317",
                  url="https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260317000002")
    documents["kr_business_overview_public.json"]["rows"]["004444"] = second
    documents["kr_business_overview_public.json"]["_meta"]["count"] = 2
    documents["universe_search.json"]["stocks"].append({
        "ticker": "004444", "market": "KR", "name": "합성제조사"})
    artifact = engine.build_prepared_business_index(documents)
    published = json.loads(json.dumps(artifact, sort_keys=True, ensure_ascii=True, separators=(",", ":")))
    assert list(artifact["index"]["materials"]) != list(published["index"]["materials"])
    prepared = engine.prepare_public_index(documents, "a" * 64)
    by_id = prepared["by_id"]
    revision = engine._business_index_revision(documents, by_id)
    checked = engine.checked_business_index(published, engine.prepared_business_publisher_receipt(published),
                                            revision, documents, by_id)
    assert checked == artifact["index"]
    published["index"]["by_company"]["KR:002222"].append(
        published["index"]["by_company"]["KR:002222"][0])
    assert engine.checked_business_index(published, engine.prepared_business_publisher_receipt(published),
                                         revision, documents, by_id) is None


@pytest.mark.parametrize("name,localized,accepted", [
    ("무관한신규회사", None, True),
    ("주식회사 합성고객", None, False),
    ("unrelated", "합성고객", False),
    ("다른업체", None, False),
])
def test_added_catalog_identity_reuses_only_when_business_result_is_unchanged(
        engine, documents, monkeypatch, name, localized, accepted):
    documents["universe_search.json"]["stocks"].append({
        "ticker": "003333", "market": "KR", "name": name, "name_ko": localized})
    artifact = json.loads(json.dumps(engine.build_prepared_business_index(documents),
                                   sort_keys=True, ensure_ascii=True, separators=(",", ":")))
    # A live filing makes a previously unresolved universe declaration usable.
    original_catalog = {row["id"]: row for row in artifact["catalog"] if row["id"] != "KR:003333"}
    artifact["catalog"] = list(original_catalog.values())
    artifact["source_revision"] = engine._business_index_revision(documents, original_catalog)
    artifact["index"] = engine._business_material_index(documents, original_catalog)
    current_catalog = {**original_catalog, "KR:003333": {
        "id": "KR:003333", "market": "KR", "name": name, "source_names": [name]}}
    receipt = engine.prepared_business_publisher_receipt(artifact)
    helper = importlib.import_module(engine.__package__ + ".portfolio_prepared_business")
    compatible = helper.compatible_catalog_revision(
        artifact, documents, current_catalog, engine._business_index_revision)
    assert (compatible is not None) is accepted
    baseline = engine._business_material_index(documents, current_catalog)
    cache = engine._ProjectedPublicIndexCache()
    built = Mock(wraps=engine._business_material_index)
    monkeypatch.setattr(engine, "_business_material_index", built)
    result = cache._business(documents, current_catalog, artifact, receipt)
    assert result == baseline
    assert built.call_count == (0 if accepted else 1)


@pytest.mark.parametrize("mutation", ["issuer", "rename", "removed", "changed-excerpt", "forged-receipt"])
def test_catalog_reuse_retains_identity_source_and_publisher_guards(engine, documents, mutation):
    artifact = engine.build_prepared_business_index(documents)
    receipt = engine.prepared_business_publisher_receipt(artifact)
    current = {row["id"]: deepcopy(row) for row in artifact["catalog"]}
    current["KR:003333"] = {"id": "KR:003333", "market": "KR", "name": "무관한신규회사", "source_names": ["무관한신규회사"]}
    if mutation == "issuer":
        source = documents["kr_business_overview_public.json"]["rows"].pop("001111")
        documents["kr_business_overview_public.json"]["rows"]["003333"] = source
    elif mutation == "rename":
        current["KR:001111"]["name"] = "다른발행사"
    elif mutation == "removed":
        current.pop("KR:002222")
    elif mutation == "changed-excerpt":
        documents["kr_business_overview_public.json"]["rows"]["001111"]["text"] += " 변경."
    else:
        receipt["artifact_sha256"] = "0" * 64
    cache = engine._ProjectedPublicIndexCache()
    result = cache._business(documents, current, artifact, receipt)
    assert result == engine._business_material_index(documents, current)
    assert result is not artifact["index"]


@pytest.mark.parametrize("change", ["presence", "local_day", "utc_day"])
def test_prepared_fetch_restarts_for_public_revision_boundary(engine, documents, monkeypatch, change):
    fetch_module = importlib.import_module(engine.__package__ + ".portfolio_public_fetch")
    source_revisions = {name: "a" * 64 for name in documents}
    before = fetch_module._index_revision(source_revisions)
    artifact = engine.build_prepared_business_index(documents)
    receipt = engine.prepared_business_publisher_receipt(artifact)
    fetch = Mock(return_value=(artifact, receipt))
    engine.prepare_public_index(documents, before, prepared_business_fetcher=fetch)

    if change == "presence":
        after = fetch_module._index_revision({**source_revisions, "portfolio.json": "a" * 64})
        changed_documents = {**documents, "portfolio.json": {}}
    elif change == "local_day":
        original_date = fetch_module.date

        class Tomorrow(original_date):
            @classmethod
            def today(cls):
                return original_date(2100, 1, 1)

        monkeypatch.setattr(fetch_module, "date", Tomorrow)
        after = fetch_module._index_revision(source_revisions)
        changed_documents = documents
    else:
        original_datetime = fetch_module.datetime

        class Tomorrow(original_datetime):
            @classmethod
            def now(cls, tz=None):
                return original_datetime(2100, 1, 1, tzinfo=tz)

        monkeypatch.setattr(fetch_module, "datetime", Tomorrow)
        after = fetch_module._index_revision(source_revisions)
        changed_documents = documents

    assert after != before
    engine.prepare_public_index(changed_documents, after, prepared_business_fetcher=fetch)
    assert fetch.call_count == 2


def test_prepared_diagnostic_rejects_dynamic_fields_and_cannot_break_response(engine, monkeypatch, capsys):
    engine._log_prepared_status("accepted member=private")
    assert capsys.readouterr().err == ""
    monkeypatch.setattr(engine, "print", Mock(side_effect=OSError("stderr unavailable")),
                        raising=False)
    engine._log_prepared_status("accepted")


@pytest.mark.parametrize("mutation", ["missing-receipt", "stale-receipt", "wrong-digest",
                                     "wrong-source", "wrong-version", "wrong-code",
                                     "changed-input", "broken-links", "extra-private-field"])
def test_invalid_preparation_uses_existing_matcher(engine, documents, monkeypatch, capsys, mutation):
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
    assert capsys.readouterr().err == "portfolio_prepared_business status=fallback_rejected\n"
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
    source_bytes = _bytes(documents)
    positions = [{"ticker": "000660", "market": "KR"},
                 {"ticker": "TSM", "market": "US"}]
    baseline = _bytes(engine.analyze_portfolio(positions, documents,
                                               public_bundle_revision="d" * 64))
    assert _bytes(documents) == source_bytes
    full_index = engine._PROJECTED_PUBLIC_INDEX.get(documents, "d" * 64)
    artifact = json.loads(json.dumps(engine.build_prepared_business_index(documents),
                                   sort_keys=True, ensure_ascii=True, separators=(",", ":")))
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
    result = engine.analyze_portfolio(positions, documents, public_bundle_revision="d" * 64)
    prepared = _bytes(result)
    assert prepared == baseline
    def change_response(value):
        if type(value) is dict:
            for child in list(value.values()):
                change_response(child)
            value.clear()
        elif type(value) is list:
            for child in value:
                change_response(child)
            value.clear()
    change_response(result)
    assert _bytes(documents) == source_bytes
    assert _bytes(engine.analyze_portfolio(positions, documents,
        public_bundle_revision="d" * 64)) == baseline


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
        engine, documents, monkeypatch, capsys):
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
    engine.prepare_public_index(documents, "e" * 64,
                                prepared_business_index=None, publisher_receipt=None)
    assert capsys.readouterr().err == ""
    clock[0] = 160.0
    assert helper.fetch_publisher_prepared_business() == (None, None)
    assert len(calls) == 4


@pytest.mark.parametrize("payload", [
    b'{"invalid":',
    b"[" * 40 + b"0" + b"]" * 40,
    b"[" * 1200 + b"0" + b"]" * 1200,
], ids=["malformed", "depth-40", "depth-1200"])
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
