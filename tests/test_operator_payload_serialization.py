"""Transport compaction preserves source values and distinguishes byte hashes."""
from copy import deepcopy
import hashlib
import importlib.util
import json
import math
from pathlib import Path
from types import SimpleNamespace

import pytest

from api.utils.analysis_evidence import capture_analysis_inputs, verify_input_snapshot
from scripts import upload_operator_data_to_supabase as uploader
from scripts.ci.operator_portfolio_delivery import compact_portfolio_source, prepare_portfolio_delivery
from tests.test_operator_early_delivery import NOW, artifacts, upload_case


def test_compaction_preserves_nested_inputs_types_strings_and_canonical_input_hash():
    record = {"ticker": "A", "currency": "USD", "price": 0, "enabled": False,
              "dart_financials": {"raw": [{"value": 0, "missing": None, "audited": True}] * 100},
              "literal": "keep  two spaces\n한글 ☀", "integer": 9007199254740993, "negative_zero": -0.0}
    inputs = capture_analysis_inputs([record], {"macro": {"rate": 3.5}})
    evidence = {**inputs["records"][("A", "USD")], "hash_scope": "pre_brain_candidate_inputs_v1"}
    source = {"recommendations": [{**deepcopy(record), "evidence_snapshot": evidence}],
              "analysis_changes": {"known": 1}}
    original = json.dumps(source, ensure_ascii=False, indent=2).encode()
    body, manifest = compact_portfolio_source(original)
    saved = json.loads(body)
    assert saved == source
    assert len(body) < len(original)
    row = saved["recommendations"][0]
    assert row["enabled"] is False and type(row["price"]) is int
    assert row["integer"] == 9007199254740993
    assert math.copysign(1, row["negative_zero"]) == -1
    assert row["literal"] == record["literal"]
    assert verify_input_snapshot(row["evidence_snapshot"])
    assert row["evidence_snapshot"]["input_hash"] == evidence["input_hash"]
    assert manifest["producer_original_sha256"] == hashlib.sha256(original).hexdigest()
    assert manifest["archive_compact_sha256"] == hashlib.sha256(body).hexdigest()
    assert manifest["producer_original_bytes"] == len(original)
    assert manifest["archive_compact_bytes"] == len(body)
    assert manifest["producer_original_sha256"] != manifest["archive_compact_sha256"]
    assert compact_portfolio_source(body)[0] == body


def test_full_compaction_preserves_existing_nonfinite_acceptance():
    portfolio, scan = artifacts()
    portfolio["legacy_extra"] = {"nan": float("nan"), "inf": float("inf")}
    source = json.dumps(portfolio, indent=2).encode()
    compact, _ = compact_portfolio_source(source)
    result = prepare_portfolio_delivery(compact, scan, run_id="456", run_attempt="2",
        expected_scan_id="gh:123:1", analysis_mode="full", verity_mode="prod",
        phase="analysis_complete", now=NOW)
    saved = json.loads(result)
    assert math.isnan(saved["legacy_extra"]["nan"])
    assert saved["legacy_extra"]["inf"] == float("inf")
    assert saved["analysis_provenance"]["snapshot_sha256"] == hashlib.sha256(scan).hexdigest()
    assert saved["analysis_provenance"]["delivery"]["source_portfolio_sha256"] == hashlib.sha256(compact).hexdigest()


def test_current_stays_compact_after_archive_annotation_and_legacy_guard(upload_case, monkeypatch):
    data, _, posts = upload_case
    document = json.loads((data / "portfolio.json").read_bytes())
    document["backtest_stats"] = {"periods": {"legacy": 99}}
    raw = json.dumps(document, indent=2).encode()
    (data / "portfolio.json").write_bytes(raw)
    monkeypatch.setattr(uploader.requests, "get", lambda *a, **kw: SimpleNamespace(
        status_code=200, json=lambda: {"public": False}, content=posts[0][1]["data"] if posts else raw))
    assert uploader.main() == 0
    archive = posts[0][1]["data"]; current = posts[-1][1]["data"]
    saved = json.loads(current); delivery = saved["analysis_provenance"]["delivery"]
    assert archive == json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode()
    assert current == json.dumps(saved, ensure_ascii=False, separators=(",", ":")).encode()
    assert saved["backtest_stats"]["evaluation_status"] == "legacy_requires_recalculation"
    assert delivery["archive"]["sha256"] == delivery["source_portfolio_sha256"] == hashlib.sha256(archive).hexdigest()
    assert delivery["source_serialization"]["producer_original_sha256"] == hashlib.sha256(raw).hexdigest()
    assert (data / "portfolio.json").read_bytes() == raw


def test_existing_authenticated_api_projection_retains_serialization_manifest(monkeypatch):
    path = Path(__file__).resolve().parents[1] / "vercel-api/api/admin.py"
    spec = importlib.util.spec_from_file_location("compact_delivery_api_test", path)
    admin = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(admin)
    _, manifest = compact_portfolio_source(b'{ "recommendations": [] }')
    portfolio = {"analysis_provenance": {"delivery": {"source_serialization": manifest}},
                 "recommendations": []}
    monkeypatch.setattr(admin, "fetch_portfolio", lambda: portfolio)
    for handler in (admin.handle_portfolio_terminal, admin.handle_portfolio_full):
        response = handler(None)
        assert response["_status"] == 200
        assert response["_body"]["analysis_provenance"] == portfolio["analysis_provenance"]


@pytest.mark.parametrize("payload,expected", [
    ({"code": "EntityTooLarge", "message": "SECRET private payload", "url": "SECRET"}, "EntityTooLarge"),
    ({"error": "InvalidMimeType", "message": "SECRET"}, "InvalidMimeType"),
    ({"code": "SECRET private payload", "error": {"code": "EntityTooLarge"}}, "unknown"),
    (["SECRET"], "unknown"),
])
def test_storage_diagnostic_is_fixed_allowlisted_metadata_only(capsys, payload, expected):
    uploader._storage_diagnostic("archive_upload", SimpleNamespace(status_code=400, json=lambda: payload), 58367929)
    captured = capsys.readouterr()
    assert "SECRET" not in captured.out + captured.err
    diagnostic = json.loads(captured.err.split("[operator_storage] ", 1)[1])
    assert diagnostic == {"stage": "archive_upload", "http_status": 400, "bytes": 58367929, "code": expected}


def test_actual_archive_and_current_failure_emit_codes_without_response_body(upload_case, monkeypatch, capsys):
    _, _, posts = upload_case
    def fail(url, **kw):
        posts.append((url, kw))
        return SimpleNamespace(status_code=400, text="SECRET", json=lambda: {
            "code": "EntityTooLarge", "message": "SECRET private payload"})
    monkeypatch.setattr(uploader.requests, "post", fail)
    monkeypatch.setattr(uploader.requests, "get", lambda *a, **kw: SimpleNamespace(
        status_code=200 if "/bucket/" in a[0] else 404, json=lambda: {"public": False}, content=b""))
    assert uploader.main() == 1
    captured = capsys.readouterr()
    assert "SECRET" not in captured.out + captured.err
    diagnostics = [json.loads(line.split("[operator_storage] ", 1)[1]) for line in captured.err.splitlines()
                   if line.startswith("[operator_storage] ")]
    assert {(row["stage"], row["http_status"], row["code"]) for row in diagnostics} >= {
        ("archive_upload", 400, "EntityTooLarge"), ("current_upload", 400, "EntityTooLarge"),
    }
    assert all(set(row) == {"stage", "http_status", "bytes", "code"} for row in diagnostics)
    assert next(row["bytes"] for row in diagnostics if row["stage"] == "archive_upload") == len(posts[0][1]["data"])
    assert next(row["bytes"] for row in diagnostics if row["stage"] == "current_upload") == len(posts[-1][1]["data"])
