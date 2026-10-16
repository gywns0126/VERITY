"""Exact-source accounting alignment diagnostics; no scalar policy changes."""
import copy
import math
from unittest.mock import patch

import pytest

from api.utils.source_alignment import (
    source_alignment, attach_source_alignment, field_evidence, sec_input, dart_input,
)


def _row(**changes):
    row = {"accn": "0000000001-26-000001", "filed": "2026-03-01",
           "form": "10-K", "start": "2025-01-01", "end": "2025-12-31", "val": 100}
    row.update(changes)
    return row


def _stock(value=50, row=None):
    raw = sec_input(row or _row(), ticker="ABC", cik="123", concept="Debt", instant=True)
    ev = field_evidence(value, source="SEC", ticker="ABC", issuer_id="0000000123",
                        definition="long_term_plus_short_borrowings_over_equity",
                        unit="percent", inputs=[raw])
    return {"ticker": "ABC", "currency": "USD", "sec_financials": {
        "debt_ratio": value, "_source_identity": {"cik": "123"}, "_source_evidence": {"debt_ratio": ev}}}


def _debt(stock):
    return source_alignment(stock)["fields"]["graham_value.debt_ratio"]


def test_legacy_numeric_coverage_is_not_source_alignment():
    result = source_alignment({"ticker": "ABC", "currency": "USD", "roe": 10, "debt_ratio": 0})
    assert result["status"] == "unknown"
    assert result["aligned_fields"] == 0
    assert result["is_truth_verified"] is False


def test_same_identity_period_unit_and_disclosure_align_without_certifying_truth():
    stock = _stock()
    prior = copy.deepcopy(stock)
    assert _debt(stock)["status"] == "aligned"
    assert stock == prior
    result = attach_source_alignment(stock)
    assert result is stock["source_alignment"]
    assert result["diagnostic_only"] is True
    assert {k: v for k, v in stock.items() if k != "source_alignment"} == prior


@pytest.mark.parametrize("key,value,reason", [
    ("ticker", "OTHER", "ticker_mismatch"),
    ("issuer_id", "999", "issuer_id_mismatch"),
    ("value", 51, "selected_value_mismatch"),
    ("unit", "ratio", "output_unit_mismatch"),
])
def test_wrong_selected_source_identity_is_mismatch(key, value, reason):
    stock = _stock()
    stock["sec_financials"]["_source_evidence"]["debt_ratio"][key] = value
    result = _debt(stock)
    assert result["status"] == "mismatch"
    assert reason in result["reasons"]


def test_missing_operand_is_unknown_not_assumed_zero():
    stock = _stock()
    stock["sec_financials"]["_source_evidence"]["debt_ratio"]["inputs"].append(None)
    assert _debt(stock)["status"] == "unknown"


def test_mixed_receipts_and_balance_dates_do_not_align():
    stock = _stock()
    inputs = stock["sec_financials"]["_source_evidence"]["debt_ratio"]["inputs"]
    second = copy.deepcopy(inputs[0]); second.update(document_id="0000000001-26-000002", end="2024-12-31")
    inputs.append(second)
    result = _debt(stock)
    assert result["status"] == "mismatch"
    assert {"mixed_disclosures", "mixed_accounting_periods"} <= set(result["reasons"])


def _flow_stock(start="2024-07-01", end="2025-06-30"):
    raw = sec_input(_row(start=start, end=end), ticker="ABC", cik="123", concept="Revenue")
    proof = field_evidence(100, source="SEC", ticker="ABC", issuer_id="0000000123",
                           definition="annual_revenue", unit="USD", inputs=[raw])
    return {"ticker": "ABC", "currency": "USD", "revenue": 100,
            "fundamental_source_evidence": {"revenue": proof}}


def test_noncalendar_actual_annual_dates_remain_unchanged():
    result = source_alignment(_flow_stock())["fields"]["stock.revenue"]
    assert result["status"] == "aligned"
    assert result["contexts"][0]["start"] == "2024-07-01"
    assert result["contexts"][0]["end"] == "2025-06-30"


@pytest.mark.parametrize("start", ["2025-01-01", "2025-04-01"])
def test_quarter_and_cumulative_rows_inside_10k_are_not_annual(start):
    result = source_alignment(_flow_stock(start=start))["fields"]["stock.revenue"]
    assert result["status"] == "mismatch"
    assert "annual_quarter_or_cumulative_definition_mismatch" in result["reasons"]


def test_currency_mismatch_and_missing_duration_are_explicit():
    stock = _flow_stock(start=None)
    stock["fundamental_source_evidence"]["revenue"]["inputs"][0]["unit"] = "CAD"
    result = source_alignment(stock)["fields"]["stock.revenue"]
    assert result["status"] == "mismatch"
    assert {"source_currency_mismatch", "duration_start_or_end_missing"} <= set(result["reasons"])


@pytest.mark.parametrize("value", [True, False, math.nan, math.inf])
def test_nonfinite_and_boolean_are_not_measurements(value):
    assert source_alignment({"ticker": "ABC", "currency": "USD", "revenue": value})["fields"]["stock.revenue"]["status"] == "missing"


def test_observed_zero_aligns_and_missing_zero_operand_does_not():
    stock = _stock(value=0)
    # Graham uses its existing truthy fallback: a SEC zero selects top-level zero.
    stock["sec_financials"]["_source_evidence"]["debt_ratio"]["inputs"][0]["raw_value"] = 0
    stock["debt_ratio"] = 0
    stock["fundamental_source_evidence"] = {"debt_ratio": stock["sec_financials"]["_source_evidence"]["debt_ratio"]}
    assert _debt(stock)["status"] == "aligned"
    stock["fundamental_source_evidence"]["debt_ratio"]["inputs"][0]["raw_value"] = None
    assert _debt(stock)["status"] == "unknown"


def test_dart_dates_are_actual_and_missing_dates_are_not_calendar_inferred():
    row = {"stock_code": "005930", "corp_code": "00126380", "rcept_no": "20260301000001",
           "reprt_code": "11011", "sj_div": "IS", "fs_div": "CFS", "currency": "KRW",
           "account_id": "ifrs-full_Revenue", "thstrm_dt": "2024.07.01 ~ 2025.06.30", "thstrm_amount": "0"}
    inp = dart_input(row)
    assert (inp["start"], inp["end"]) == ("2024-07-01", "2025-06-30")
    del row["thstrm_dt"]
    assert dart_input(row)["start"] is None
    assert dart_input(row)["end"] is None


def test_sec_producer_preserves_exact_legacy_selection_without_changing_scalar():
    from api.collectors import sec_edgar
    # Existing selector chooses this 90-day row from 10-K. Diagnose, do not silently fix.
    payload = {"facts": {"us-gaap": {"NetIncomeLoss": {"units": {"USD": [_row(start="2025-10-01")]}}}}}
    class Response:
        def raise_for_status(self): pass
        def json(self): return payload
    with patch.object(sec_edgar, "_resolve_cik", return_value="0000000123"), patch.object(sec_edgar, "_throttle"), patch.object(sec_edgar._SESSION, "get", return_value=Response()):
        result = sec_edgar.get_financial_facts("ABC", "test")
    assert result["net_income"] == 100
    evidence = result["_source_evidence"]["net_income"]
    assert evidence["inputs"][0]["start"] == "2025-10-01"
    stock = {"ticker": "ABC", "currency": "USD", "net_income": 100, "fundamental_source_evidence": {"net_income": evidence}}
    assert source_alignment(stock)["fields"]["stock.net_income"]["status"] == "mismatch"


def test_dart_producer_distinguishes_explicit_zero_from_default_zero():
    from api.collectors.dart_fundamentals import _extract_pl_bs_from_dart
    selected = {}
    row = {"sj_div": "IS", "account_id": "ifrs-full_Revenue", "thstrm_amount": "0"}
    parsed = _extract_pl_bs_from_dart({"list": [row]}, source_rows=selected)
    assert parsed["revenue"] == parsed["net_income"] == 0
    assert selected["revenue"] == row
    assert "net_income" not in selected


def test_missing_source_observation_never_claims_asof_alignment():
    stock = _stock()
    del stock["sec_financials"]["_source_evidence"]["debt_ratio"]["observed_at"]
    assert _debt(stock)["status"] == "unknown"


def test_filing_after_source_observation_is_mismatch():
    stock = _stock()
    stock["sec_financials"]["_source_evidence"]["debt_ratio"]["observed_at"] = "2025-01-01T00:00:00+00:00"
    assert "filing_after_source_observation" in _debt(stock)["reasons"]


def test_dart_actual_assignment_carries_only_its_source_proof(tmp_path):
    import json
    from datetime import datetime, timezone
    from api.utils.dart_pre_attach import attach_dart_to_stocks
    proof = {"value": 0, "source": "DART", "ticker": "005930", "inputs": []}
    snapshot = {"collected_at": datetime.now(timezone.utc).isoformat(), "fundamentals": {
        "005930": {"roe": 0, "debt_ratio": 25, "source": "DART", "_source_evidence": {"roe": proof}}}}
    path = tmp_path / "dart.json";path.write_text(json.dumps(snapshot))
    stock = {"ticker": "005930", "currency": "KRW", "roe": 0, "debt_ratio": 50,
             "fundamental_source_evidence": {"debt_ratio": {"source": "retained"}}}
    attach_dart_to_stocks([stock], path=path)
    assert stock["fundamental_source_evidence"]["roe"] == proof
    assert stock["fundamental_source_evidence"]["debt_ratio"] == {"source": "retained"}
    stock["fundamental_source_evidence"]["roe"]["inputs"].append("changed")
    assert proof["inputs"] == []


@pytest.mark.parametrize("identity", ["bad", [], 123, True])
def test_malformed_identity_does_not_abort_diagnostics(identity):
    stock = _stock()
    stock["sec_financials"]["_source_identity"] = identity
    assert _debt(stock)["status"] == "aligned"
    # Alignment remains evidence-internal, never independently truth-verified.
    assert source_alignment(stock)["is_truth_verified"] is False


def test_missing_sec_response_cik_is_unknown():
    stock = _stock()
    stock["sec_financials"]["_source_evidence"]["debt_ratio"]["inputs"][0]["issuer_id"] = None
    assert _debt(stock)["status"] == "unknown"


def test_differing_sec_response_cik_is_mismatch():
    stock = _stock()
    stock["sec_financials"]["_source_evidence"]["debt_ratio"]["inputs"][0]["issuer_id"] = "999"
    assert _debt(stock)["status"] == "mismatch"


@pytest.mark.parametrize("field,value", [
    ("document_id", ["bad"]), ("unit", {"bad": 1}),
    ("period_kind", ["annual"]), ("fs_div", ["CFS"]),
    ("raw_value", {"bad": 1}), ("filed", ["bad"]),
])
def test_malformed_source_metadata_cannot_change_or_abort_fact_scoring(field, value):
    from api.intelligence.factors.fact import _compute_fact_score
    stock = _stock()
    baseline = _compute_fact_score(copy.deepcopy(stock), portfolio={})
    stock["sec_financials"]["_source_evidence"]["debt_ratio"]["inputs"][0][field] = value
    result = _compute_fact_score(stock, portfolio={})
    alignment = result["coverage_scope"]["source_alignment"]["fields"]["graham_value.debt_ratio"]
    assert alignment["status"] == "unknown"
    for key in ("score", "components", "weights_effective", "data_coverage"):
        assert result[key] == baseline[key]
