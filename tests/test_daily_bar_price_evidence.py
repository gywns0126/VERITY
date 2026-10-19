"""A bar's provider timestamp is preserved without inventing a trade clock."""
import pandas as pd
import ast
from pathlib import Path
from api.collectors.stock_data import _daily_bar_price_metadata
from api.utils.analysis_evidence import _quote


def stock(index="2026-10-16T00:00:00-04:00"):
    frame = pd.DataFrame({"Close": [100.]}, index=pd.DatetimeIndex([index]))
    return {"price": 100., **_daily_bar_price_metadata(frame, 100.)}


def test_provider_bar_clock_is_not_capture_or_trade_clock():
    result = _quote(stock(), "2026-10-17T12:00:00Z")
    assert result["as_of"] is None
    assert result["bar_as_of"] == "2026-10-16T00:00:00-04:00"
    assert result["time_kind"] == "daily_bar_start"
    assert result["source"] == "yfinance.history"
    assert result["adjustment"] == "auto_adjust"
    assert result["status"] == "unknown"
    assert "daily_bar_timestamp_is_not_trade_timestamp" in result["reasons"]


def test_naive_index_is_not_given_an_invented_timezone():
    result = _quote(stock("2026-10-16"), "2026-10-17T12:00:00Z")
    assert result["bar_as_of"] is None
    assert result["bar_date"] == "2026-10-16"
    assert "daily_bar_timestamp_missing_or_invalid" in result["reasons"]


def test_replaced_price_cannot_keep_unrelated_bar_provenance():
    data = stock()
    data["price"] = 101
    result = _quote(data, "2026-10-17T12:00:00Z")
    assert result["bar_as_of"] is None
    assert result["source"] == result["adjustment"] == "unknown"
    assert "daily_bar_value_mismatch" in result["reasons"]


def test_future_bar_is_not_confirmed_trade_evidence():
    result = _quote(stock(), "2026-10-15T12:00:00Z")
    assert result["status"] == "unknown"
    assert "daily_bar_timestamp_after_capture" in result["reasons"]


def test_private_api_projection_keeps_bar_evidence_not_full_input():
    path = Path(__file__).resolve().parents[1] / "vercel-api/api/admin.py"
    node = next(n for n in ast.parse(path.read_text()).body
                if isinstance(n, ast.FunctionDef) and n.name == "_terminal_analysis_evidence")
    namespace = {}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), namespace)
    quote = _quote(stock(), "2026-10-17T12:00:00Z")
    out = namespace["_terminal_analysis_evidence"]({
        "evidence_snapshot": {"price": quote, "input_snapshot": {"private": "must not leak"}},
        "rec_price_evidence": {**quote, "schema": "rec-price-evidence-v1"}})
    assert out["evidence_snapshot"]["price"] == quote
    assert "input_snapshot" not in out["evidence_snapshot"]
    assert out["rec_price_evidence"]["bar_as_of"] == quote["bar_as_of"]
