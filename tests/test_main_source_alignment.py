"""Main connects provenance to exact Brain inputs and persisted private records."""
import ast
from copy import deepcopy
import json
from pathlib import Path

import pytest

from api.utils import source_alignment


@pytest.fixture
def main_module():
    import api.main as main
    return main


def test_hook_preserves_every_existing_field_and_refreshes_each_record(main_module):
    records = [{"ticker": "A", "currency": "USD", "debt_ratio": 0,
                "recommendation": "BUY", "verity_brain": {"brain_score": 71, "grade": "BUY"},
                "source_alignment": {"status": "aligned", "obsolete": True}},
               {"ticker": "000001", "currency": "KRW", "roe": 5}]
    original = deepcopy(records)
    counts = main_module._attach_source_alignment_to_records(records)
    assert counts == {"processed": 2, "attached": 2, "failed": 0}
    for old, new in zip(original, records):
        assert {k: v for k, v in new.items() if k != "source_alignment"} == {
            k: v for k, v in old.items() if k != "source_alignment"}
        assert new["source_alignment"]["is_truth_verified"] is False
        assert new["source_alignment"]["diagnostic_only"] is True
        assert new["source_alignment"] == source_alignment.source_alignment(new)
        assert "obsolete" not in new["source_alignment"]


def test_failed_validation_clears_stale_alignment_without_changing_score(main_module, monkeypatch):
    def fail(stock):
        raise ValueError("fixture error")

    monkeypatch.setattr(source_alignment, "attach_source_alignment", fail)
    record = {"ticker": "A", "price": 100, "recommendation": "BUY",
              "verity_brain": {"brain_score": 71, "grade": "BUY"},
              "source_alignment": {"status": "aligned", "aligned_fields": 8}}
    original = deepcopy(record)
    counts = main_module._attach_source_alignment_to_records([record])
    assert counts == {"processed": 1, "attached": 0, "failed": 1}
    assert record["source_alignment"]["status"] == "unknown"
    assert record["source_alignment"]["error_type"] == "ValueError"
    assert record["verity_brain"] == original["verity_brain"]
    assert record["price"] == original["price"]
    assert record["recommendation"] == original["recommendation"]


def test_private_save_preserves_alignment_in_full_and_slim_records(main_module, monkeypatch, tmp_path):
    from api.vams import engine
    from api.trading import account_profile
    monkeypatch.setattr(engine, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(engine, "PORTFOLIO_PATH", str(tmp_path / "portfolio.json"))
    monkeypatch.setattr(engine, "RECOMMENDATIONS_PATH", str(tmp_path / "recommendations.json"))
    monkeypatch.setattr(engine, "VERITY_MODE", "prod")
    monkeypatch.setattr(main_module, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(main_module, "_orig_save_portfolio", engine.save_portfolio)
    monkeypatch.setattr(account_profile, "annotate_recommendations", lambda records: records)
    records = [{"ticker": "A", "currency": "USD", "debt_ratio": 0,
                "recommendation": "WATCH", "verity_brain": {"brain_score": 50}}]
    main_module._attach_source_alignment_to_records(records)
    main_module.save_portfolio({"recommendations": records})
    full = json.loads((tmp_path / "recommendations.json").read_text())
    slim = json.loads((tmp_path / "portfolio.json").read_text())["recommendations"]
    assert full[0]["source_alignment"] == slim[0]["source_alignment"] == records[0]["source_alignment"]
    assert full[0]["verity_brain"] == {"brain_score": 50}
    assert slim[0]["recommendation"] == "WATCH"


def test_main_hooks_final_brain_input_and_final_analysis_output():
    tree = ast.parse((Path(__file__).resolve().parents[1] / "api/main.py").read_text())
    main = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "main")
    calls = [node for node in ast.walk(main) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)]
    hooks = [node for node in calls if node.func.id == "_attach_source_alignment_to_records"]
    assert [ast.unparse(node.args[0]) for node in sorted(hooks, key=lambda node: node.lineno)] == ["candidates", "analyzed"]
    brain = next(node for node in calls if node.func.id == "verity_brain_analyze")
    assert hooks[0].lineno < brain.lineno
    assignment = next(node for node in ast.walk(main) if isinstance(node, ast.Assign)
                      and ast.unparse(node.value) == "analyzed"
                      and any(ast.unparse(target) == "portfolio['recommendations']" for target in node.targets))
    assert brain.lineno < hooks[1].lineno < assignment.lineno
