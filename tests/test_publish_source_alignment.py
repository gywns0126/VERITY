"""Operator source diagnostics are removed only from the publication copy."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path

import pytest


ACTION = Path(__file__).resolve().parents[1] / ".github/actions/publish-data"


def load(name):
    spec = importlib.util.spec_from_file_location(name, ACTION / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def record():
    return {"ticker": "A", "price": 100, "recommendation": "WATCH",
            "source_alignment": {"status": "partial", "fields": {"private_definition": {}}},
            "analysis_change": {"changes": {"grade": {"before": "WATCH", "after": "BUY"}}},
            "evidence_snapshot": {"input_snapshot": {"private_input": 1}, "input_hash": "fixture"},
            "rec_price_evidence": {"value": 90, "source": "private_fixture"},
            "fundamental_source_evidence": {"roe": {"source": "DART"}},
            "sec_financials": {"revenue": 1000, "roe": 5,
                               "_source_evidence": {"roe": {"private_definition": "net_income/equity"}},
                               "_source_identity": {"cik": "0000000001", "ticker": "A"}}}


def assert_public_record(rec):
    assert rec == {"ticker": "A", "price": 100, "recommendation": "WATCH",
                   "sec_financials": {"revenue": 1000, "roe": 5}}


@pytest.mark.parametrize("shape", ["list", "portfolio", "ticker_map"])
def test_public_recommendation_shapes_remove_only_diagnostic_fields(tmp_path, shape):
    rec = record()
    source = [rec] if shape == "list" else {"recommendations": [rec]} if shape == "portfolio" else {"A": rec}
    private = tmp_path / "private.json"
    private.write_text(json.dumps(source))
    original_bytes = private.read_bytes()
    publication = tmp_path / "public.json"
    publication.write_bytes(original_bytes)
    assert load("sanitize_recommendations").main(str(publication)) == 0
    public = json.loads(publication.read_text())
    result = public[0] if shape == "list" else public["recommendations"][0] if shape == "portfolio" else public["A"]
    assert_public_record(result)
    assert private.read_bytes() == original_bytes
    assert json.loads(private.read_text()) == source


def test_public_portfolio_pipeline_strips_diagnostics_and_preserves_news(tmp_path):
    source = {"recommendations": [record()], "headlines": [{"title": "news"}],
              "analysis_changes": {"current_count": 1, "changed_count": 1},
              "source_alignment": {"status": "partial"},
              "fundamental_source_evidence": {"private": True}}
    private_copy = deepcopy(source)
    path = tmp_path / "portfolio.json"
    path.write_text(json.dumps(source))
    assert load("sanitize_recommendations").main(str(path)) == 0
    assert load("sanitize_portfolio_public").main(str(path)) == 0
    public = json.loads(path.read_text())
    assert_public_record(public["recommendations"][0])
    assert public["headlines"] == [{"title": "news"}]
    assert "source_alignment" not in public
    assert "fundamental_source_evidence" not in public
    assert "analysis_changes" not in public
    assert source == private_copy


def test_in_memory_sanitizer_does_not_mutate_private_sec_evidence():
    source = record()
    private_copy = deepcopy(source)
    assert_public_record(load("sanitize_recommendations")._sanitize_rec(source))
    assert source == private_copy
