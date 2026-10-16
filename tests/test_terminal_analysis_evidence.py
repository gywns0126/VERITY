"""The authenticated terminal retains evidence references, not full input bodies."""
import importlib.util
import json
from pathlib import Path


def test_private_terminal_keeps_identity_and_differences_without_input_snapshots(monkeypatch):
    path = Path(__file__).resolve().parents[1] / "vercel-api/api/admin.py"
    spec = importlib.util.spec_from_file_location("terminal_evidence_test", path)
    admin = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(admin)
    run = {"run_id": "123", "run_attempt": "1", "scan_id": "gh:100:1"}
    scope = {"source_alignment": {"aligned_fields": 0, "field_count": 8, "status": "unknown"}}
    rec = {
        "ticker": "TEST", "currency": "USD",
        "evidence_snapshot": {"schema": "analysis-evidence-v1", "input_hash": "frozen-hash", "run": run,
                              "price": {"value": 0, "as_of": None, "source": None, "status": "unknown", "reasons": ["quote_timestamp_missing_or_invalid"]},
                              "input_snapshot": {"must_not_send": "full snapshot"}, "input_field_hashes": {"huge": "omit"}},
        "rec_price_evidence": {"value": 10, "status": "unknown", "quote_as_of": None, "run": run, "quote_reasons": ["legacy_origin_unavailable"]},
        "analysis_change": {"status": "changed", "changes": {
            "scores": {"before": {"brain_score": 0, "extra": "omit"}, "after": {"brain_score": 1}},
            "inputs": {"changed_fields": ["roe"], "raw_inputs": "omit"}, "unexpected": {"private": "omit"}}},
        "verity_brain": {"fact_score": {"coverage_scope": scope}},
    }
    monkeypatch.setattr(admin, "fetch_portfolio", lambda: {
        "recommendations": [rec], "analysis_changes": {"current_count": 1, "unresolved_count": 0, "raw": "omit"},
    })
    response = admin.handle_portfolio_terminal(None)
    assert response["_status"] == 200
    out = response["_body"]["recommendations"][0]
    assert out["evidence_snapshot"]["run"] == run
    assert out["evidence_snapshot"]["input_hash"] == "frozen-hash"
    assert out["evidence_snapshot"]["price"] == rec["evidence_snapshot"]["price"]
    assert "input_snapshot" not in out["evidence_snapshot"]
    assert "input_field_hashes" not in out["evidence_snapshot"]
    assert out["analysis_change"]["changes"] == {
        "scores": {"before": {"brain_score": 0}, "after": {"brain_score": 1}},
        "inputs": {"changed_fields": ["roe"]},
    }
    assert out["verity_brain"]["fact_score"]["coverage_scope"] == scope
    assert out["rec_price_evidence"]["quote_as_of"] is None
    assert out["rec_price_evidence"]["quote_reasons"] == ["legacy_origin_unavailable"]
    assert response["_body"]["analysis_changes"] == {"current_count": 1, "unresolved_count": 0}
    assert "input_snapshot" in rec["evidence_snapshot"]


def test_full_screen_response_does_not_expand_with_archived_input_size(monkeypatch):
    path = Path(__file__).resolve().parents[1] / "vercel-api/api/admin.py"
    spec = importlib.util.spec_from_file_location("full_evidence_test", path)
    admin = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(admin)
    rec = {"ticker": "TEST", "existing_detail": {"keep": True},
           "evidence_snapshot": {"input_hash": "exact-input-hash",
                                 "input_snapshot": {"body": "x" * 5_000_000}}}
    original = {"recommendations": [rec], "existing_full_field": {"keep": True}}
    monkeypatch.setattr(admin, "fetch_portfolio", lambda: original)
    response = admin.handle_portfolio_full(None)
    assert response["_status"] == 200
    body = response["_body"]
    assert len(json.dumps(body)) < 1000
    assert body["existing_full_field"] == original["existing_full_field"]
    assert body["recommendations"][0]["existing_detail"] == rec["existing_detail"]
    assert body["recommendations"][0]["evidence_snapshot"]["input_hash"] == "exact-input-hash"
    assert len(original["recommendations"][0]["evidence_snapshot"]["input_snapshot"]["body"]) == 5_000_000
