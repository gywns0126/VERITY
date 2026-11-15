"""Core snapshot equivalence and fail-closed generation tests; synthetic only."""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
import importlib
from pathlib import Path
import sys
import types

import pytest

CORE = Path(__file__).resolve().parents[1] / "vercel-api/api/portfolio_core"


@pytest.fixture
def modules(monkeypatch):
    package = types.ModuleType("company_snapshot_test")
    package.__path__ = [str(CORE)]
    monkeypatch.setitem(sys.modules, package.__name__, package)
    snapshot = importlib.import_module(package.__name__ + ".portfolio_company_snapshot")
    engine = importlib.import_module(package.__name__ + ".portfolio_engine")
    yield snapshot, engine
    for name in tuple(sys.modules):
        if name == package.__name__ or name.startswith(package.__name__ + "."):
            monkeypatch.delitem(sys.modules, name, raising=False)


@pytest.fixture
def documents():
    return {"universe_search.json": {"stocks": [
        {"ticker": "001111", "market": "KR", "name": "합성회사"},
        {"ticker": "SYNTH", "market": "US", "name": "Synthetic Systems"}]},
        "stock_report_public.json": {"stocks": {"001111": {"name": "합성회사", "facts": [
            {"metric": "revenue", "value": 123, "unit": "KRW", "as_of": "2025-12-31", "source": "DART"}]}}},
        "us_stock_report_public.json": {"stocks": {"SYNTH": {"name": "Synthetic Systems", "facts": []}}},
        "public_disclosure_feed.json": {"items": [{"ticker": "001111", "name": "합성회사", "disclosures": [
            {"title": "합성 공시", "date": "2026-10-01", "source_url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20261001000001"}]}]},
        "us_disclosure_feed.json": {"items": []},
        "kr_business_overview_public.json": {"_meta": {"count": 0, "generated_at": "2026-10-12T00:00:00Z"}, "rows": {}}}


def seed(modules, documents, tmp_path):
    snapshot, engine = modules
    artifact = engine.build_prepared_business_index(documents)
    receipt = engine.prepared_business_publisher_receipt(artifact)
    hashes = {name: snapshot.sha256(snapshot.encode(value)) for name, value in documents.items()}
    directory = tmp_path / "company-snapshots"
    manifest = snapshot.write_company_snapshots(artifact, receipt, directory, documents, hashes)
    calls = []
    def reader(filename, limit):
        calls.append(filename)
        raw = (snapshot.encode(receipt) if filename == snapshot.RECEIPT_FILENAME
               else (directory / filename.removeprefix(snapshot.BUCKET_PREFIX)).read_bytes())
        assert len(raw) <= limit
        return raw
    return manifest, directory, receipt, calls, reader


def test_selected_core_matches_existing_projector_and_preserves_dates(modules, documents, tmp_path):
    snapshot, engine = modules
    manifest, directory, receipt, calls, reader = seed(modules, documents, tmp_path)
    requested = [{"market": "KR", "ticker": "001111"}, {"market": "US", "ticker": "SYNTH"}]
    actual = snapshot.read_company_snapshot(requested, _reader=reader)
    expected = engine.analyze_portfolio(requested, documents, public_bundle_revision="a" * 64)
    assert actual["companies"] == expected["companies"]
    assert [{k: d[k] for k in ("id", "title", "url", "as_of", "kind", "source", "company_ids")}
            for d in actual["documents"]] == [{k: d[k] for k in ("id", "title", "url", "as_of", "kind", "source", "company_ids")}
                                            for d in expected["documents"]]
    assert actual["documents"][0]["as_of"] == "2026-10-01"
    assert actual["_meta"]["pending"] == ["relations", "judgments", "market-context", "prices", "changes"]
    assert len(calls) == 2 + len({snapshot.company_bucket("KR:001111"), snapshot.company_bucket("US:SYNTH")})
    assert "portfolio_public_business_index.json" not in calls


def test_writer_uses_disclosure_feed_not_only_three_source_base(modules, documents, tmp_path):
    snapshot, _ = modules
    _, directory, _, _, _ = seed(modules, documents, tmp_path)
    buckets = [snapshot.decode(p.read_bytes()) for p in directory.iterdir() if p.name != snapshot.RELEASE_FILE]
    company = next(body["companies"]["KR:001111"] for body in buckets if "KR:001111" in body["companies"])
    assert company["documents"][0]["id"] == "DART:20261001000001"


@pytest.mark.parametrize("offset,accepted", [(-1, True), (1, False)])
def test_exact_current_parent_survives_midnight_without_inventing_source_freshness(modules, documents, tmp_path, offset, accepted):
    snapshot, _ = modules
    manifest, directory, parent, _, reader = seed(modules, documents, tmp_path)
    day = (datetime.now(timezone.utc) + timedelta(days=offset)).date().isoformat()
    parent["utc_day"] = manifest["utc_day"] = day
    manifest["parent_receipt_sha256"] = snapshot.sha256(snapshot.encode(parent))
    for entry in manifest["buckets"].values():
        body = snapshot.decode((directory / (entry["sha256"] + ".json")).read_bytes())
        body["utc_day"] = day
        raw = snapshot.encode(body)
        entry.update(sha256=snapshot.sha256(raw), bytes=len(raw))
        (directory / (entry["sha256"] + ".json")).write_bytes(raw)
    (directory / snapshot.RELEASE_FILE).write_bytes(snapshot.encode(manifest))
    if accepted:
        result = snapshot.read_company_snapshot([{"market": "KR", "ticker": "001111"}], _reader=reader)
        assert result["_meta"]["utc_day"] == day
        assert result["documents"][0]["as_of"] == "2026-10-01"
    else:
        with pytest.raises(ValueError):
            snapshot.read_company_snapshot([{"market": "KR", "ticker": "001111"}], _reader=reader)


@pytest.mark.parametrize("reason", ["parent", "day", "code", "projection", "source", "bucket-bytes", "count", "selected-id"])
def test_rejects_mixed_or_corrupt_generation(modules, documents, tmp_path, reason):
    snapshot, _ = modules
    manifest, directory, receipt, _, reader = seed(modules, documents, tmp_path)
    if reason == "parent": receipt["artifact_sha256"] = "c" * 64
    if reason == "day": manifest["utc_day"] = (datetime.now(timezone.utc) - timedelta(days=1)).date().isoformat()
    if reason == "code": manifest["implementation_sha256"] = "d" * 64
    if reason == "projection": manifest["projection_sha256"] = "e" * 64
    if reason == "source": manifest["source_sha256"].pop("stock_report_public.json")
    if reason == "count": manifest["company_count"] += 1
    if reason == "bucket-bytes":
        entry = manifest["buckets"][snapshot.company_bucket("KR:001111")]
        (directory / (entry["sha256"] + ".json")).write_bytes(b"{}")
    (directory / snapshot.RELEASE_FILE).write_bytes(snapshot.encode(manifest))
    positions = [{"market": "KR", "ticker": "999999" if reason == "selected-id" else "001111"}]
    with pytest.raises(ValueError): snapshot.read_company_snapshot(positions, _reader=reader)


def test_old_result_mutation_cannot_modify_public_bucket_or_next_request(modules, documents, tmp_path):
    snapshot, _ = modules
    _, _, _, _, reader = seed(modules, documents, tmp_path)
    selected = [{"market": "KR", "ticker": "001111"}]
    first = snapshot.read_company_snapshot(selected, _reader=reader)
    first["companies"][0]["facts"][0]["value"] = -999
    first["documents"][0]["title"] = "changed privately"
    second = snapshot.read_company_snapshot(selected, _reader=reader)
    assert second["companies"][0]["facts"][0]["value"] == 123
    assert second["documents"][0]["title"] == "합성 공시"


@pytest.mark.parametrize("positions", [[], [{"market": "KR", "ticker": "001111", "memo": "private"}],
    [{"market": "US", "ticker": "../source"}], [{"market": "KR", "ticker": "SYNTH"}],
    [{"market": "KR", "ticker": "001111"}] * 31])
def test_invalid_selection_never_reads_public_assets(modules, positions):
    snapshot, _ = modules
    def forbidden(*_): raise AssertionError("network before input validation")
    with pytest.raises(ValueError): snapshot.read_company_snapshot(positions, _reader=forbidden)


def test_duplicate_and_nonfinite_json_rejected(modules):
    snapshot, _ = modules
    for raw in (b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":Infinity}'):
        with pytest.raises(ValueError): snapshot.decode(raw)


def test_request_path_cannot_choose_origin_or_path(modules):
    snapshot, _ = modules
    for filename in ("../private.json", "https://evil.test/x", snapshot.BUCKET_PREFIX + "x.json"):
        with pytest.raises(ValueError): snapshot._read(filename, 10)
