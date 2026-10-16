"""Reproduce the real pre-Brain producer's non-JSON Boolean without network IO."""
from copy import deepcopy
import json

import numpy as np
import pandas as pd
import pytest

from api.utils.analysis_evidence import (
    attach_analysis_evidence, capture_analysis_inputs, verify_input_snapshot,
)


@pytest.fixture
def actual_backtest_output(monkeypatch):
    from api.predictors import backtester
    x = np.arange(180)
    frame = pd.DataFrame({"Close": 100 + 8 * np.sin(x / 6) + x * .02},
                         index=pd.date_range("2025-01-01", periods=len(x)))
    class OfflineTicker:
        def history(self, **kwargs):
            return frame
    monkeypatch.setattr(backtester.yf, "Ticker", lambda *a, **k: OfflineTicker())
    monkeypatch.setattr(backtester, "_benchmark_returns", lambda *a: None)
    result = backtester.backtest_stock("FIXTURE")
    assert result["total_trades"] > 0
    assert result["recent_trades"]
    assert all(type(t["win"]) is np.bool_ for t in result["recent_trades"])
    return result


def test_actual_backtest_numpy_boolean_is_preserved_as_json_boolean(actual_backtest_output):
    record = {"ticker": "FIXTURE", "currency": "USD", "price": 100, "backtest": actual_backtest_output}
    before = deepcopy(record)
    captured = capture_analysis_inputs([record], {})
    result = captured["records"][("FIXTURE", "USD")]
    trades = result["input_snapshot"]["candidate"]["backtest"]["recent_trades"]
    for raw, normalized in zip(actual_backtest_output["recent_trades"], trades):
        assert type(normalized["win"]) is bool
        assert normalized["win"] == bool(raw["win"])
    assert record == before
    assert all(type(t["win"]) is np.bool_ for t in record["backtest"]["recent_trades"])
    evidence = {**result, "hash_scope": "pre_brain_candidate_inputs_v1"}
    assert verify_input_snapshot(json.loads(json.dumps(evidence, allow_nan=False)))


@pytest.mark.parametrize("count", [75, 90])
def test_actual_producer_batch_hashes_survive_save_shape_without_mutation(actual_backtest_output, count):
    records = [{"ticker": f"FIXTURE{i}", "currency": "USD", "price": 100, "rec_price": 90,
                "recommendation": "WATCH", "verity_brain": {"brain_score": 50, "grade": "WATCH"},
                "backtest": deepcopy(actual_backtest_output)} for i in range(count)]
    before = deepcopy(records)
    captured = capture_analysis_inputs(records, {"macro": {"observed": np.bool_(False)}})
    assert len(captured["records"]) == count
    attach_analysis_evidence(records, {}, captured, {}, "2026-10-16T17:00:00+09:00", "full")
    from api.vams.engine import _sanitize_nan, _slim_recommendations
    serialized = json.loads(json.dumps(_sanitize_nan(_slim_recommendations(records)), allow_nan=False))
    assert sum(verify_input_snapshot(r["evidence_snapshot"]) for r in serialized) == count
    for original, current in zip(before, records):
        assert {k: v for k, v in current.items() if k not in
                {"analysis_change", "evidence_snapshot", "rec_price_evidence"}} == original
        assert "recent_trades" not in serialized[0]["backtest"]
        assert current["evidence_snapshot"]["input_snapshot"]["context"]["macro"]["observed"] is False


def test_boolean_hashes_match_builtin_boolean_and_remain_distinct_from_numbers():
    def digest(value):
        return capture_analysis_inputs([{"ticker": "FIXTURE", "currency": "USD", "flag": value}], {})["records"][("FIXTURE", "USD")]["input_hash"]
    assert digest(np.bool_(True)) == digest(True)
    assert digest(np.bool_(False)) == digest(False)
    assert digest(True) != digest(1)
    assert digest(False) != digest(0)


@pytest.mark.parametrize("location", ["candidate", "context"])
def test_unknown_type_stays_rejected_with_path_and_type_only(location, capsys):
    class SecretValue:
        def __repr__(self):
            raise AssertionError("unsupported values must never be rendered")
        __str__ = __repr__
    record = {"ticker": "PRIVATE_ID_MUST_NOT_LOG", "currency": "USD"}
    portfolio = {}
    if location == "candidate":
        record["PRIVATE_PROVIDER_HEADLINE_MUST_NOT_LOG"] = [{"PRIVATE_NESTED_KEY_MUST_NOT_LOG": SecretValue()}]
        expected = "candidate.field[2][0].field[0]"
    else:
        portfolio["macro"] = {"PRIVATE_PROVIDER_HEADLINE_MUST_NOT_LOG": [SecretValue()]}
        expected = "context.macro.field[0][0]"
    with pytest.raises(TypeError):
        capture_analysis_inputs([record], portfolio)
    diagnostic = capsys.readouterr().err
    assert expected in diagnostic and "SecretValue" in diagnostic
    assert "PRIVATE_ID_MUST_NOT_LOG" not in diagnostic
    assert "PRIVATE_PROVIDER_HEADLINE_MUST_NOT_LOG" not in diagnostic
    assert "PRIVATE_NESTED_KEY_MUST_NOT_LOG" not in diagnostic
    assert "unsupported values must never be rendered" not in diagnostic


@pytest.mark.parametrize("value", [np.int64(1), np.array([True]), {True}])
def test_unproven_types_are_not_blanket_coerced(value, capsys):
    with pytest.raises(TypeError):
        capture_analysis_inputs([{"ticker": "FIXTURE", "currency": "USD", "unrecognized": value}], {})
    assert "candidate.field[2]" in capsys.readouterr().err


def test_only_fixed_producer_root_names_survive_in_diagnostic_path(capsys):
    with pytest.raises(TypeError):
        capture_analysis_inputs([{"ticker": "FIXTURE", "currency": "USD", "backtest": {
            "PRIVATE_PROVIDER_HEADLINE_MUST_NOT_LOG": [np.array([True])]}}], {})
    diagnostic = capsys.readouterr().err
    assert "candidate.backtest.field[0][0]" in diagnostic
    assert "PRIVATE_PROVIDER_HEADLINE_MUST_NOT_LOG" not in diagnostic
