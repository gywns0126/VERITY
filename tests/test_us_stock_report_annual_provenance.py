"""Offline annual-value/provenance binding; synthetic caches stay in memory."""
from __future__ import annotations

import copy
import io
import json
import math
from pathlib import Path
import socket
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from api.builders import us_stock_report_public_builder as builder

CIK = "0001045810"
ACCESSION = "0001045810-26-000021"
SOURCE_KEYS = {"cik", "accession", "form", "period_end", "tag", "source_url", "currency_verified"}
METRICS = {"revenue": ("revenue", "Revenues"), "op": ("operating_income", "OperatingIncomeLoss"),
           "net": ("net_income", "NetIncomeLoss")}


def row(end, value, tag="Revenues", **extra):
    return {"end": end, "val": value, "accn": ACCESSION, "form": "10-K", "tag": tag,
            "fy": 2026, "fp": "FY", "is_annual": True, **extra}


def document():
    return {"ticker": "TEST", "meta": {"cik": 1045810, "currency": "USD"}, "series_annual": {
        "revenue": [row("2024-12-31", 100), row("2025-12-31", 200)],
        "operating_income": [row("2024-12-31", 20, "OperatingIncomeLoss"), row("2025-12-31", 50, "OperatingIncomeLoss")],
        "net_income": [row("2024-12-31", 10, "NetIncomeLoss"), row("2025-12-31", 30, "NetIncomeLoss")],
    }}


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("network is forbidden")
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)


def load(monkeypatch, doc, ticker="TEST"):
    payload = json.dumps(doc)
    expected = ROOT / "data" / "us_financials" / f"{ticker}.json"
    def read_cache(path, mode="r", **kwargs):
        assert Path(path) == expected and mode == "r"
        return io.StringIO(payload)
    monkeypatch.setattr(builder, "open", read_cache, raising=False)
    return builder._load_us_annual_pack(ticker)


def without_sources(series):
    return [{key: value for key, value in point.items() if key != "metric_sources"} for point in series]


def test_optional_closed_sources_preserve_values_financials_and_ignore_private_extras(monkeypatch):
    doc = document()
    doc["series_annual"]["revenue"][-1].update({"memo": "synthetic private marker", "filed_at": "invented",
                                              "source_url": "https://invalid.example/private"})
    series, financials = load(monkeypatch, doc)
    assert without_sources(series) == [
        {"year": 2024, "revenue": 100.0, "op": 20.0, "net": 10.0, "currency": "USD"},
        {"year": 2025, "revenue": 200.0, "op": 50.0, "net": 30.0, "currency": "USD"},
    ]
    assert financials == {"period": "2025", "values": {"매출": "$200", "순이익": "$30"}, "groups": [
        {"title": "손익계산서 (연간 10-K)", "rows": [{"k": "매출", "v": "$200"},
         {"k": "영업이익", "v": "$50"}, {"k": "순이익", "v": "$30"}, {"k": "영업이익률", "v": "25.0%"}]}]}
    for point in series:
        assert set(point["metric_sources"]) == set(METRICS)
        for metric, (_, tag) in METRICS.items():
            assert point["metric_sources"][metric] == {
                "cik": CIK, "accession": ACCESSION, "form": "10-K", "period_end": f"{point['year']}-12-31",
                "tag": tag, "currency_verified": True,
                "source_url": f"https://www.sec.gov/Archives/edgar/data/1045810/000104581026000021/{ACCESSION}-index.htm",
            }
    assert "private" not in json.dumps(series) and "filed_at" not in json.dumps(series)
    legacy = copy.deepcopy(doc)
    for rows in legacy["series_annual"].values():
        for record in rows:
            for key in ("accn", "form", "tag"):
                record.pop(key)
    old_series, old_financials = load(monkeypatch, legacy)
    assert old_series == without_sources(series) and old_financials == financials


def test_latest_end_and_first_tie_keep_exact_row_not_latest_accession(monkeypatch):
    doc = document()
    first = row("2025-12-31", 321, accn="0001045810-25-000001", tag="SalesRevenueNet")
    doc["series_annual"]["revenue"] += [first, row("2025-12-31", 999, accn=ACCESSION)]
    # First existing row at this end wins, even over a newer accession/value.
    series, _ = load(monkeypatch, doc)
    assert series[-1]["revenue"] == 200
    assert series[-1]["metric_sources"]["revenue"]["tag"] == "Revenues"
    doc["series_annual"]["revenue"] = [doc["series_annual"]["revenue"][0], first,
        row("2025-12-31", 999), row("2025-06-30", 111)]
    series, _ = load(monkeypatch, doc)
    assert series[-1]["revenue"] == 321
    assert series[-1]["metric_sources"]["revenue"]["accession"] == first["accn"]
    assert series[-1]["metric_sources"]["revenue"]["tag"] == "SalesRevenueNet"
    assert builder._annual_by_year(doc["series_annual"]["revenue"]) == {2024: 100.0, 2025: 321.0}


def test_missing_winning_proof_never_falls_back_to_another_row_or_metric(monkeypatch):
    doc = document()
    doc["series_annual"]["revenue"][-1]["accn"] = "invalid"
    doc["series_annual"]["revenue"] += [row("2025-06-30", 150), row("2025-12-31", 999)]
    doc["series_annual"]["net_income"][-1].update({"end": "2025-09-30", "accn": "0001045810-25-000007"})
    series, _ = load(monkeypatch, doc)
    assert series[-1]["revenue"] == 200
    assert set(series[-1]["metric_sources"]) == {"op", "net"}
    assert series[-1]["metric_sources"]["net"]["period_end"] == "2025-09-30"
    assert series[-1]["metric_sources"]["net"]["accession"] == "0001045810-25-000007"


@pytest.mark.parametrize("field,value", [
    ("accn", None), ("accn", "000104581026000021"), ("accn", "0000000000-00-000000"),
    ("accn", ACCESSION + "/other"), ("form", "10-Q"), ("form", []),
    ("end", "2025-02-30"), ("end", "2025-12-31extra"), ("end", "20251231"),
    ("tag", "OperatingIncomeLoss"), ("tag", "DERIVED_NII+NoninterestIncome"), ("tag", {}),
    ("cik", "0000320193"), ("cik", True), ("ticker", "OTHER"), ("is_annual", False), ("fp", "Q4"),
])
def test_invalid_selected_row_proof_is_omitted_without_changing_selected_values(monkeypatch, field, value):
    doc = document()
    doc["series_annual"]["revenue"][-1][field] = value
    series, _ = load(monkeypatch, doc)
    expected = builder._annual_by_year(doc["series_annual"]["revenue"])
    assert {point["year"]: point["revenue"] for point in series if point["revenue"] is not None} == expected
    assert all("revenue" not in point.get("metric_sources", {}) for point in series if point["year"] != 2024)


@pytest.mark.parametrize("target,field,value", [
    ("doc", "ticker", "OTHER"), ("doc", "ticker", None), ("doc", "cik", 320193),
    ("meta", "cik", None), ("meta", "cik", True), ("meta", "cik", 0),
    ("meta", "cik", "1045810extra"), ("meta", "cik", "12345678901"),
])
def test_document_identity_conflicts_omit_sources_not_legacy_values(monkeypatch, target, field, value):
    doc = document()
    (doc if target == "doc" else doc["meta"])[field] = value
    series, _ = load(monkeypatch, doc)
    assert len(series) == 2 and series[-1]["revenue"] == 200
    assert all("metric_sources" not in point for point in series)


@pytest.mark.parametrize("meta_currency,unit,expected,currency", [
    (None, None, False, "USD"), (None, "USD", True, "USD"), (None, "CAD", False, "USD"),
    ("USD", None, True, "USD"), ("CAD", None, True, "CAD"), ("cad", "CAD", True, "CAD"),
    ("CAD", "USD", False, "CAD"), ("USD", "USD/shares", False, "USD"),
    ("USD", "shares", False, "USD"), ("XYZ", None, False, "XYZ"),
])
def test_currency_verification_never_certifies_default_or_conflicting_units(monkeypatch, meta_currency, unit, expected, currency):
    doc = document()
    if meta_currency is None:
        doc["meta"].pop("currency")
    else:
        doc["meta"]["currency"] = meta_currency
    if unit is not None:
        doc["series_annual"]["revenue"][-1]["unit"] = unit
    series, _ = load(monkeypatch, doc)
    assert series[-1]["currency"] == currency
    assert series[-1]["metric_sources"]["revenue"]["currency_verified"] is expected


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), True])
def test_nonfinite_or_boolean_values_keep_legacy_behavior_without_provenance(monkeypatch, value):
    doc = document()
    doc["series_annual"]["revenue"][-1]["val"] = value
    series, _ = load(monkeypatch, doc)
    actual = series[-1]["revenue"]
    assert math.isnan(actual) if isinstance(value, float) and math.isnan(value) else actual == float(value)
    assert "revenue" not in series[-1]["metric_sources"]


@pytest.mark.parametrize("form", ["10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A"])
def test_supported_annual_forms_comparative_years_and_agent_accessions(monkeypatch, form):
    doc = document()
    doc["series_annual"]["revenue"][-1].update({"form": form, "accn": "0001193125-26-000001", "val": 0})
    doc["series_annual"]["net_income"][-1]["val"] = -30
    series, _ = load(monkeypatch, doc)
    proof = series[-1]["metric_sources"]["revenue"]
    assert series[-1]["year"] == 2025 and proof["period_end"] == "2025-12-31"
    assert proof["form"] == form and proof["cik"] == CIK
    assert "/1045810/000119312526000001/" in proof["source_url"]
    assert series[-1]["revenue"] == 0 and series[-1]["net"] == -30
    assert "net" in series[-1]["metric_sources"]


def test_series_window_and_minimum_point_gate_are_unchanged(monkeypatch):
    doc = document()
    doc["series_annual"] = {"revenue": [row(f"{year}-12-31", year) for year in range(2010, 2026)]}
    series, _ = load(monkeypatch, doc)
    assert [point["year"] for point in series] == list(range(2014, 2026))
    doc["series_annual"]["revenue"] = doc["series_annual"]["revenue"][-1:]
    series, financials = load(monkeypatch, doc)
    assert series is None and financials["period"] == "2025"


def test_retained_nvda_cache_matches_every_selected_metric_and_does_not_invent_currency():
    path = ROOT / "data" / "us_financials" / "NVDA.json"
    if not path.is_file():
        pytest.skip("retained NVDA cache unavailable; synthetic tests do not fetch a replacement")
    raw_bytes = path.read_bytes()
    doc = json.loads(raw_bytes)
    series, _ = builder._load_us_annual_pack("NVDA")
    assert len(series) == 5
    assert "currency" not in doc["meta"]
    checked = 0
    for point in series:
        assert point["currency"] == "USD"
        for metric, (key, _) in METRICS.items():
            candidates = [r for r in doc["series_annual"][key] if int(r["end"][:4]) == point["year"]]
            selected = max(candidates, key=lambda r: r["end"])
            assert point[metric] == float(selected["val"])
            source = point["metric_sources"][metric]
            assert set(source) == SOURCE_KEYS
            assert (source["cik"], source["accession"], source["form"], source["period_end"], source["tag"]) == (
                CIK, selected["accn"], selected["form"], selected["end"], selected["tag"])
            assert "unit" not in selected and "currency" not in selected
            assert source["currency_verified"] is False
            checked += 1
    assert checked == 15
    assert path.read_bytes() == raw_bytes
