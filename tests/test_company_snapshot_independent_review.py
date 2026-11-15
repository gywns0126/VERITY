"""Independent reader contract regressions; synthetic fixtures and no network."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import socket
import subprocess

import pytest


fixture_path = Path(__file__).with_name("test_portfolio_company_snapshot.py")
spec = importlib.util.spec_from_file_location("snapshot_review_fixture", fixture_path)
fixture_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture_module)
modules = fixture_module.modules
documents = fixture_module.documents
seed = fixture_module.seed


@pytest.fixture(autouse=True)
def deny_network(monkeypatch):
    def rejected(*_args, **_kwargs):
        raise AssertionError("independent review must not use network")
    monkeypatch.setattr(socket, "create_connection", rejected)
    monkeypatch.setattr(socket.socket, "connect", rejected)


def selected():
    return [{"market": "KR", "ticker": "001111"}]


def test_review_positive_control_accepts_writer_output(modules, documents, tmp_path):
    snapshot, _ = modules
    _, _, _, _, reader = seed(modules, documents, tmp_path)
    result = snapshot.read_company_snapshot(selected(), _reader=reader)
    assert result["companies"][0]["facts"][0]["value"] == 123
    assert result["documents"][0]["url"].startswith("https://")


def test_review_writer_hash_must_bind_exact_published_parent_bytes(modules, documents, tmp_path):
    snapshot, engine = modules
    artifact = engine.build_prepared_business_index(documents)
    receipt = engine.prepared_business_publisher_receipt(artifact)
    published_parent = json.dumps(receipt, indent=2).encode("utf-8")
    assert snapshot.decode(published_parent) == receipt
    hashes = {name: snapshot.sha256(snapshot.encode(value)) for name, value in documents.items()}
    directory = tmp_path / "pretty-parent"
    manifest = snapshot.write_company_snapshots(
        artifact, receipt, directory, documents, hashes, parent_raw=published_parent)
    assert manifest["parent_receipt_sha256"] == snapshot.sha256(published_parent)

    def actual_reader(filename, limit):
        raw = (published_parent if filename == snapshot.RECEIPT_FILENAME else
               (directory / filename.removeprefix(snapshot.BUCKET_PREFIX)).read_bytes())
        assert len(raw) <= limit
        return raw

    # Exact raw bytes are now part of the writer contract, not an encoding assumption.
    assert snapshot.read_company_snapshot(selected(), _reader=actual_reader)["companies"]


def test_review_writer_rejects_parent_raw_for_different_receipt(modules, documents, tmp_path):
    snapshot, engine = modules
    artifact = engine.build_prepared_business_index(documents)
    receipt = engine.prepared_business_publisher_receipt(artifact)
    hashes = {name: snapshot.sha256(snapshot.encode(value)) for name, value in documents.items()}
    mismatched = {**receipt, "artifact_sha256": "0" * 64}
    with pytest.raises(ValueError, match="parent bytes rejected"):
        snapshot.write_company_snapshots(artifact, receipt, tmp_path / "mismatch",
                                        documents, hashes, parent_raw=snapshot.encode(mismatched))


@pytest.mark.parametrize("malformation", ["fact-extra", "fact-source", "document-url", "company-name"])
def test_review_hash_correct_bucket_must_reject_invalid_selected_schema(
        modules, documents, tmp_path, malformation):
    snapshot, _ = modules
    manifest, directory, _, _, reader = seed(modules, documents, tmp_path)
    key = snapshot.company_bucket("KR:001111")
    entry = manifest["buckets"][key]
    body = snapshot.decode((directory / (entry["sha256"] + ".json")).read_bytes())
    company = body["companies"]["KR:001111"]
    if malformation == "fact-extra":
        company["facts"][0]["unexpected_review_field"] = "not in public fact schema"
    elif malformation == "fact-source":
        company["facts"][0]["source"] = {"unexpected": "object"}
    elif malformation == "document-url":
        company["documents"][0]["url"] = "javascript:review_fixture"
    else:
        company["name"] = []
    raw = snapshot.encode(body)
    digest = snapshot.sha256(raw)
    (directory / (digest + ".json")).write_bytes(raw)
    entry.update(sha256=digest, bytes=len(raw))
    (directory / snapshot.RELEASE_FILE).write_bytes(snapshot.encode(manifest))
    # Integrity is self-consistent; selected semantic schema must still be checked.
    with pytest.raises(ValueError):
        snapshot.read_company_snapshot(selected(), _reader=reader)


def test_review_claim_subset_requires_delivered_document_guard(modules):
    snapshot, _ = modules
    docs = [{"id": "review:%03d" % i, "title": "Synthetic %03d" % i,
             "url": "https://example.org/review/%03d" % i,
             "as_of": "2026-10-01", "kind": "disclosure", "source": "Synthetic"}
            for i in range(60)]
    row = {"id": "KR:001111", "ticker": "001111", "market": "KR",
           "name": "Synthetic", "facts": [], "documents": docs}
    requested = [{**selected()[0], "id": row["id"]}]
    manifest = {"source_revision": "a" * 64, "utc_day": "2026-11-15"}
    before = snapshot.compose_core_payload([row], requested, manifest, "b" * 64)
    later = deepcopy(row)
    later["documents"].append({**docs[0], "id": "review:new", "title": "New",
                                "url": "https://example.org/review/new",
                                "as_of": "2026-11-15"})
    after = snapshot.compose_core_payload([later], requested, manifest, "c" * 64)
    # This uses the same 60-document cap as the existing full analysis route.
    prior_claims = set(before["_meta"]["core_claims"]["companies"][row["id"]])
    next_claims = set(after["_meta"]["core_claims"]["companies"][row["id"]])
    assert prior_claims <= next_claims
    visible = {d["id"] for d in before["documents"]}
    delivered = {d["id"] for d in after["documents"]}
    # Preserve the original counterexample: composition correctly keeps its cap.
    assert visible - delivered == {"review:000"}
    helper = Path(__file__).resolve().parents[1] / "scripts/member-map/company-core-client.cjs"
    script = """
const denied=()=>{throw Error('network forbidden in review guard test')};
globalThis.fetch=denied;require('node:net').Socket.prototype.connect=denied;
const fs=require('node:fs');
const {compatibleCoreGraph}=require(process.argv[1]);
const x=JSON.parse(fs.readFileSync(0,'utf8'));
console.log(JSON.stringify({missing:compatibleCoreGraph(x.core,x.full,x.missing),
                           retained:compatibleCoreGraph(x.core,x.full,x.retained)}));
"""
    inputs = {"core": {"graph": {"documents": before["documents"]},
                       "claims": before["_meta"]["core_claims"]},
              "full": {"claims": after["_meta"]["core_claims"]},
              "missing": {"documents": after["documents"]},
              "retained": {"documents": before["documents"]}}
    completed = subprocess.run(["node", "-e", script, str(helper)], input=json.dumps(inputs),
                               text=True, capture_output=True, check=True, timeout=10)
    assert json.loads(completed.stdout) == {"missing": False, "retained": True}
