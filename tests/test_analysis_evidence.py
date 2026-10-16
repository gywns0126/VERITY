"""Private observed differences and immutable recommendation input evidence."""
import ast
from copy import deepcopy
import json
from pathlib import Path
from datetime import datetime, timezone

import pytest

from api.utils.analysis_evidence import (
    attach_analysis_evidence, capture_analysis_inputs, capture_previous_analysis,
    verify_input_snapshot,
)


PROVENANCE = {"status": "completed", "analysis_completed_at": "2026-10-14T17:00:00+09:00",
              "analysis_run_id": "run1", "analysis_run_attempt": "1", "scan_id": "scan1"}
NOW = "2026-10-15T17:00:00+09:00"


def stock(ticker="A", currency="USD"):
    return {"ticker": ticker, "currency": currency, "price": 100, "rec_price": 90,
            "roe": 0, "fundamental_missing_fields": {"roe": False}, "recommendation": "BUY",
            "verity_brain": {"grade": "BUY", "brain_score": 70, "data_coverage": .8,
                             "fact_score": {"score": 65, "coverage_scope": {
                                 "component_states": {"graham_value": "measured"}}},
                             "sentiment_score": {"score": 75}}}


def attach(records, previous=None, new_ids=()):
    inputs = capture_analysis_inputs(records, {"macro": {"rate": 3}})
    summary = attach_analysis_evidence(records, previous or {}, inputs, PROVENANCE,
                                       NOW, "full", new_ids)
    return summary


def test_identical_records_preserve_all_values_and_compare_deterministically():
    old = [stock()]
    attach(old)
    previous = capture_previous_analysis({"recommendations": old, "analysis_provenance": PROVENANCE})
    records = [stock()]
    original = deepcopy(records)
    summary = attach(records, previous)
    assert summary["compared_count"] == summary["unchanged_count"] == 1
    assert records[0]["analysis_change"]["changes"] == {}
    assert records[0]["analysis_change"]["reasons"] == []
    assert {k: v for k, v in records[0].items() if k not in
            {"analysis_change", "evidence_snapshot", "rec_price_evidence"}} == original[0]
    assert verify_input_snapshot(records[0]["evidence_snapshot"])


def test_changed_grade_score_price_measurement_and_disclosure_are_observations():
    old = [stock()]
    old[0]["sec_financials"] = {"revenue": 10, "_source_evidence": {"receipt": "old"}}
    attach(old)
    previous = {"recommendations": old, "analysis_provenance": PROVENANCE}
    current = [stock()]
    current[0].update(price=110, recommendation="WATCH", roe=None,
                      fundamental_missing_fields={"roe": True},
                      sec_financials={"revenue": 10, "_source_evidence": {"receipt": "new"}})
    current[0]["verity_brain"].update(grade="WATCH", brain_score=60, data_coverage=.7)
    summary = attach(current, previous)
    changes = current[0]["analysis_change"]["changes"]
    assert summary["changed_count"] == 1
    assert set(changes) == {"grade", "recommendation", "scores", "price", "measurement", "inputs", "disclosures"}
    assert changes["scores"] == {"before": {"brain_score": 70, "fact_score": 65, "sentiment_score": 75},
                                 "after": {"brain_score": 60, "fact_score": 65, "sentiment_score": 75}}
    assert changes["disclosures"]["changed_fields"] == ["sec_financials"]
    assert "roe" in changes["inputs"]["changed_fields"]
    assert current[0]["analysis_change"]["observed_differences_only"] is True


def test_legacy_identical_price_does_not_invent_old_input_or_rec_origin():
    current = [stock()]
    summary = attach(current, {"recommendations": [stock()], "analysis_provenance": PROVENANCE})
    assert summary["compared_count"] == 1
    assert current[0]["analysis_change"]["reasons"] == [
        "previous_analysis_price_observation_unavailable", "previous_or_current_input_snapshot_unavailable"]
    evidence = current[0]["rec_price_evidence"]
    assert evidence["status"] == "unknown" and evidence["value"] == 90
    assert evidence["captured_at"] is None and evidence["quote_as_of"] is None
    assert evidence["source"] == evidence["adjustment"] == "unknown"


def test_first_rec_capture_and_quote_clock_are_distinct_and_origin_preserved():
    current = [stock()]
    current[0].update(rec_price=100, price_as_of="2026-10-14T20:00:00Z",
                      price_source="archive_fixture", price_adjustment="unadjusted")
    attach(current, new_ids={("A", "USD")})
    origin = deepcopy(current[0]["rec_price_evidence"])
    assert origin["captured_at"] == NOW
    assert origin["quote_as_of"] == "2026-10-14T20:00:00Z"
    next_rec = stock()
    next_rec.update(rec_price=100, price=120)
    attach([next_rec], {"recommendations": current, "analysis_provenance": PROVENANCE})
    assert next_rec["rec_price_evidence"] == origin
    assert next_rec["evidence_snapshot"]["price"]["as_of"] is None


def test_new_rec_without_quote_timestamp_remains_unknown_despite_capture_time():
    record = stock()
    record["rec_price"] = record["price"]
    attach([record], new_ids={("A", "USD")})
    assert record["rec_price_evidence"]["status"] == "unknown"
    assert record["rec_price_evidence"]["captured_at"] == NOW
    assert record["rec_price_evidence"]["quote_as_of"] is None


def test_unproven_existing_origin_cannot_claim_captured_even_at_same_price():
    record = stock()
    record["rec_price_evidence"] = {"schema": "rec-price-evidence-v1", "ticker": "A",
                                    "currency": "USD", "value": 90, "status": "captured"}
    attach([record])
    assert record["rec_price_evidence"]["status"] == "unknown"
    assert record["rec_price_evidence"]["quote_as_of"] is None


def test_partial_previous_cross_currency_duplicates_and_missing_keep_denominators():
    previous = {"recommendations": [stock()], "analysis_provenance": {"status": "started"}}
    current = [stock(), stock("B"), {"ticker": "C", "price": None}]
    summary = attach(current, previous)
    assert summary["current_count"] == summary["unresolved_count"] == 3
    assert summary["compared_count"] == 0
    assert current[2]["evidence_snapshot"]["price"]["status"] == "missing"
    summary = attach([stock(currency="KRW")], {**previous, "analysis_provenance": PROVENANCE})
    assert summary["new_count"] == summary["removed_count"] == 1
    duplicates = [stock(), stock()]
    summary = attach(duplicates, {**previous, "analysis_provenance": PROVENANCE})
    assert summary["reasons"] == {"ambiguous_identity": 2}
    assert summary["compared_count"] == 0
    assert all(r["evidence_snapshot"]["input_hash"] is None for r in duplicates)


def test_capture_freezes_baseline_and_excludes_prior_snapshots_without_growth():
    records = [stock()]
    attach(records)
    portfolio = {"recommendations": records, "analysis_provenance": PROVENANCE}
    baseline = capture_previous_analysis(portfolio)
    before = json.dumps(records[0]["evidence_snapshot"]["input_snapshot"], sort_keys=True)
    attach(records, baseline)
    assert json.dumps(records[0]["evidence_snapshot"]["input_snapshot"], sort_keys=True) == before
    portfolio["recommendations"][0]["price"] = 999
    assert baseline["recommendations"][0]["price"] == 100


def test_previous_completed_observation_survives_later_realtime_price_updates():
    old = [stock()]
    attach(old)
    old[0]["price"] = 1234  # realtime may update the record without running Brain.
    current = [stock()]
    summary = attach(current, {"recommendations": old, "analysis_provenance": PROVENANCE})
    assert summary["unchanged_count"] == 1
    assert "price" not in current[0]["analysis_change"]["changes"]


def test_real_private_save_preserves_full_input_and_hash_after_slimming(monkeypatch, tmp_path):
    import api.main as main
    from api.vams import engine
    from api.trading import account_profile
    for name, value in {"DATA_DIR": str(tmp_path), "PORTFOLIO_PATH": str(tmp_path / "portfolio.json"),
                        "RECOMMENDATIONS_PATH": str(tmp_path / "recommendations.json"), "VERITY_MODE": "prod"}.items():
        monkeypatch.setattr(engine, name, value)
    monkeypatch.setattr(main, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(main, "_orig_save_portfolio", engine.save_portfolio)
    monkeypatch.setattr(account_profile, "annotate_recommendations", lambda records: records)
    records = [stock()]
    records[0].update(dart_financials={"raw": [0, None]}, quant_factors={"axis": 10})
    attach(records)
    main.save_portfolio({"recommendations": records})
    for file in ("portfolio.json", "recommendations.json"):
        saved = json.loads((tmp_path / file).read_text())
        saved = saved["recommendations"] if isinstance(saved, dict) else saved
        assert saved[0]["evidence_snapshot"] == records[0]["evidence_snapshot"]
        assert verify_input_snapshot(saved[0]["evidence_snapshot"])
        assert saved[0]["evidence_snapshot"]["input_snapshot"]["candidate"]["dart_financials"] == {"raw": [0, None]}


def test_main_capture_and_attach_order_uses_existing_price_formula():
    tree = ast.parse((Path(__file__).resolve().parents[1] / "api/main.py").read_text())
    main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main")
    calls = [n for n in ast.walk(main) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
    line = lambda name: next(n.lineno for n in calls if n.func.id == name)
    assert line("load_previous_analysis_baseline") < line("capture_analysis_inputs") < line("verity_brain_analyze")
    assert line("verity_brain_analyze") < line("attach_analysis_evidence")
    rec_price = next(n for n in ast.walk(main) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                     and ast.unparse(n.func) == "_rec.setdefault" and ast.literal_eval(n.args[0]) == "rec_price")
    assert ast.unparse(rec_price) == "_rec.setdefault('rec_price', _prev_rec_price_map.get(_rec.get('ticker'), _price))"
    assert rec_price.lineno < line("attach_analysis_evidence")


@pytest.mark.parametrize("value", [None, float("nan"), float("inf"), True, False, 0, -1, "100"])
def test_invalid_price_is_missing_only_in_diagnostic_metadata(value):
    record = stock()
    record.update(price=value, price_source="fixture", price_as_of="2026-10-15T00:00:00Z",
                  price_adjustment=False)
    attach([record])
    quote = record["evidence_snapshot"]["price"]
    assert quote["status"] == "missing" and quote["value"] is None
    assert "price_missing_or_invalid" in quote["reasons"]
    assert record["price"] is value


@pytest.mark.parametrize("timestamp", ["bad", "2026-10-15", "2026-10-15T12:00:00", 123, {},
                                        "2026-10-16T00:00:00Z"])
def test_invalid_or_future_quote_clock_is_never_captured(timestamp):
    record = stock()
    record.update(price_source="fixture", price_as_of=timestamp, price_adjustment=False)
    attach([record])
    assert record["evidence_snapshot"]["price"]["status"] == "unknown"


@pytest.mark.parametrize("corruption", ["identity", "input", "hash", "field_hash", "scope", "context_hash"])
def test_corrupt_prior_snapshot_does_not_assert_input_or_disclosure_changes(corruption):
    old = [stock()]
    old[0]["sec_financials"] = {"revenue": 10}
    attach(old)
    snapshot = old[0]["evidence_snapshot"]
    if corruption == "identity":
        snapshot["currency"] = "KRW"
    elif corruption == "input":
        snapshot["input_snapshot"]["candidate"]["roe"] = 999
    elif corruption == "hash":
        snapshot["input_hash"] = "bad"
    elif corruption == "field_hash":
        snapshot["input_field_hashes"]["roe"] = "bad"
    elif corruption == "context_hash":
        snapshot["context_hash"] = "bad"
    else:
        snapshot["hash_scope"] = "other"
    current = [stock()]
    current[0]["sec_financials"] = {"revenue": 20}
    attach(current, {"recommendations": old, "analysis_provenance": PROVENANCE})
    change = current[0]["analysis_change"]
    assert "inputs" not in change["changes"] and "disclosures" not in change["changes"]
    assert "previous_or_current_input_snapshot_unavailable" in change["reasons"]


def test_actual_main_failure_handler_replaces_every_partial_and_stale_diagnostic():
    from api.utils.analysis_evidence import mark_analysis_evidence_unavailable
    records = [stock(), stock("B")]
    attach(records)
    old_scalars = [(r["price"], r["rec_price"], deepcopy(r["verity_brain"])) for r in records]
    def partial_failure(records, *args):
        records[0]["evidence_snapshot"] = {"partial_new": True}
        raise ValueError("fixture")
    tree = ast.parse((Path(__file__).resolve().parents[1] / "api/main.py").read_text())
    block = next(n for n in ast.walk(tree) if isinstance(n, ast.Try)
                 and ast.unparse(n.body[0]).startswith("portfolio['analysis_changes'] = attach_analysis_evidence"))
    namespace = {"portfolio": {"analysis_provenance": PROVENANCE}, "analyzed": records,
                 "_previous_analysis_evidence": {}, "_analysis_input_evidence": {},
                 "_new_rec_price_ids": set(), "mode": "full",
                 "now_kst": lambda: datetime(2026, 10, 15, 17, tzinfo=timezone.utc),
                 "attach_analysis_evidence": partial_failure,
                 "mark_analysis_evidence_unavailable": mark_analysis_evidence_unavailable}
    exec(compile(ast.Module(body=[block], type_ignores=[]), "main-evidence-hook", "exec"), namespace)
    summary = namespace["portfolio"]["analysis_changes"]
    assert summary["unresolved_count"] == 2 and summary["compared_count"] == 0
    for rec, scalars in zip(records, old_scalars):
        assert rec["analysis_change"]["status"] == "unavailable"
        assert rec["analysis_change"]["reasons"] == ["diagnostic_capture_failed"]
        assert rec["evidence_snapshot"]["input_hash"] is None
        assert "input_snapshot" not in rec["evidence_snapshot"]
        assert rec["rec_price_evidence"]["reason"] == "diagnostic_capture_failed"
        assert rec["evidence_snapshot"]["run"]["run_id"] == "run1"
        assert (rec["price"], rec["rec_price"], rec["verity_brain"]) == scalars
