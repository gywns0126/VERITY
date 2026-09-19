from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "vercel-api" / "api"
sys.path.insert(0, str(API))
from report_us_financials import us_periods


def _source_row(tag, end, accession, form, value, **extra):
    return {"tag": tag, "end": end, "accn": accession, "form": form,
            "val": value, **extra}


def _raw(currency="USD", cik=18230):
    accession = "0000018230-26-000046"
    return {
        "ticker": "CAT", "meta": {"cik": cik, "currency": currency},
        "series_annual": {},
        "series_quarterly": {
            "revenue": [_source_row("Revenues", "2026-06-30", accession, "10-Q", 20543)],
            "operating_income": [_source_row("OperatingIncomeLoss", "2026-06-30", accession, "10-Q", 4296)],
            "net_income": [_source_row("ProfitLoss", "2026-06-30", accession, "10-Q", 3593)],
            "operating_cash_flow": [_source_row("NetCashProvidedByUsedInOperatingActivities", "2026-06-30", accession, "10-Q", 2704)],
            "capex": [_source_row("PaymentsToAcquirePropertyPlantAndEquipment", "2026-06-30", accession, "10-Q", 728)],
        },
    }


def _facts(cik=18230, currency="USD"):
    accession = "0000018230-26-000046"
    concepts = {
        "Revenues": [("2026-01-01", 37958), ("2026-04-01", 20543)],
        "OperatingIncomeLoss": [("2026-01-01", 7600), ("2026-04-01", 4296)],
        "ProfitLoss": [("2026-01-01", 6200), ("2026-04-01", 3593)],
        "NetCashProvidedByUsedInOperatingActivities": [("2026-01-01", 4500)],
        "PaymentsToAcquirePropertyPlantAndEquipment": [("2026-01-01", 1400)],
    }
    return {"cik": cik, "facts": {"us-gaap": {
        tag: {"units": {currency: [{
            "start": start, "end": "2026-06-30", "val": value,
            "accn": accession, "fy": 2026, "fp": "Q2", "form": "10-Q",
            "filed": "2026-08-05",
        } for start, value in values]}}
        for tag, values in concepts.items()
    }}}


def test_companyfacts_restores_quarter_and_ytd_with_exact_provenance():
    rows = us_periods(_raw(), _facts())
    assert [(row["period_kind"], row["start"]) for row in rows] == [
        ("ytd", "2026-01-01"), ("quarter", "2026-04-01")]
    ytd, quarter = rows
    assert ytd["revenue"] == 37958 and ytd["ocf"] == 4500 and ytd["capex"] == 1400
    assert quarter["revenue"] == 20543 and quarter["op"] == 4296 and quarter["net"] == 3593
    assert quarter["ocf"] is None and quarter["capex"] is None
    assert quarter["currency"] == "USD" and quarter["fs_div"] == "ENTITY"
    assert quarter["scope_basis"] == (
        "SEC entity-wide company facts (consolidation not separately verified)"
    )
    assert quarter["accession"] == "0000018230-26-000046"
    assert quarter["source_url"].endswith("0000018230-26-000046-index.html")
    assert quarter["metric_sources"]["revenue"] == {
        "tag": "Revenues", "start": "2026-04-01", "end": "2026-06-30",
        "unit": "USD", "accession": "0000018230-26-000046",
        "source_url": quarter["source_url"],
    }


def test_stale_blob_period_does_not_block_current_companyfacts_period():
    raw = _raw()
    stale_accession = "0000018230-26-000021"
    raw["series_quarterly"]["operating_cash_flow"] = [
        _source_row("NetCashProvidedByUsedInOperatingActivities", "2026-03-31",
                    stale_accession, "10-Q", 1870)
    ]
    rows = us_periods(raw, _facts())
    current_ytd = next(row for row in rows
                       if row["end"] == "2026-06-30" and row["period_kind"] == "ytd")
    assert current_ytd["ocf"] == 4500
    assert current_ytd["metric_sources"]["ocf"]["accession"] == "0000018230-26-000046"


def test_companyfacts_expansion_is_limited_to_latest_five_years():
    raw = _raw()
    facts = _facts()
    rows = facts["facts"]["us-gaap"]["Revenues"]["units"]["USD"]
    rows.extend([
        {**rows[-1], "start": "2021-01-01", "end": "2021-12-31",
         "form": "10-K", "fp": "FY", "fy": 2021,
         "accn": "0000018230-22-000001", "filed": "2022-02-01", "val": 100},
        {**rows[-1], "start": "2020-01-01", "end": "2020-12-31",
         "form": "10-K", "fp": "FY", "fy": 2020,
         "accn": "0000018230-21-000001", "filed": "2021-02-01", "val": 90},
    ])
    periods = us_periods(raw, facts)
    assert any(row["end"] == "2021-12-31" for row in periods)
    assert all(row["end"] != "2020-12-31" for row in periods)


def test_annual_and_native_currency_are_preserved():
    accession = "0000049938-26-000009"
    raw = {
        "ticker": "IMO", "meta": {"cik": 49938, "currency": "CAD"},
        "series_annual": {"revenue": [
            _source_row("Revenues", "2025-12-31", accession, "10-K", 47078)
        ]}, "series_quarterly": {},
    }
    facts = {"cik": 49938, "facts": {"us-gaap": {"Revenues": {"units": {"CAD": [{
        "start": "2025-01-01", "end": "2025-12-31", "val": 47078,
        # Filing FY can differ from the comparative period's end year.
        "accn": accession, "fy": 2026, "fp": "FY", "form": "10-K",
        "filed": "2026-02-18",
    }]}}}}}
    assert us_periods(raw, facts)[0] | {"metric_sources": {}} == {
        "year": 2025, "start": "2025-01-01", "end": "2025-12-31",
        "period_kind": "annual", "currency": "CAD", "fs_div": "ENTITY",
        "scope_basis": "SEC entity-wide company facts (consolidation not separately verified)",
        "source_url": ("https://www.sec.gov/Archives/edgar/data/49938/"
                       "000004993826000009/0000049938-26-000009-index.html"),
        "filed": "2026-02-18", "accession": accession,
        "revenue": 47078, "op": None, "net": None, "ocf": None,
        "capex": None, "metric_sources": {},
    }


def test_metrics_from_different_accessions_never_merge_and_latest_filing_wins():
    raw = _raw()
    old = "0000018230-26-000045"
    raw["series_quarterly"]["revenue"].append(
        _source_row("Revenues", "2026-06-30", old, "10-Q", 20000))
    facts = _facts()
    revenue_rows = facts["facts"]["us-gaap"]["Revenues"]["units"]["USD"]
    revenue_rows.append({**revenue_rows[-1], "val": 20000, "accn": old, "filed": "2026-08-04"})
    rows = us_periods(raw, facts)
    quarter = next(row for row in rows if row["period_kind"] == "quarter")
    assert quarter["accession"] == "0000018230-26-000046"
    assert quarter["revenue"] == 20543
    assert all(row["accession"] != old for row in rows)


def test_same_latest_filing_with_conflicting_tags_is_excluded():
    raw = _raw()
    accession = "0000018230-26-000046"
    raw["series_quarterly"]["revenue"].append(
        _source_row("SalesRevenueNet", "2026-06-30", accession, "10-Q", 99999))
    facts = _facts()
    facts["facts"]["us-gaap"]["SalesRevenueNet"] = {"units": {"USD": [{
        "start": "2026-04-01", "end": "2026-06-30", "val": 99999,
        "accn": accession, "fy": 2026, "fp": "Q2", "form": "10-Q",
        "filed": "2026-08-05",
    }]}}
    quarter = next(row for row in us_periods(raw, facts)
                   if row["period_kind"] == "quarter")
    assert quarter["revenue"] is None
    assert "revenue" not in quarter["metric_sources"]
    assert quarter["op"] == 4296


def test_net_income_never_substitutes_for_missing_operating_income():
    raw = _raw()
    raw["series_quarterly"]["operating_income"] = []
    facts = _facts()
    quarter = next(row for row in us_periods(raw, facts) if row["period_kind"] == "quarter")
    assert quarter["net"] == 3593
    assert quarter["op"] is None
    assert "op" not in quarter["metric_sources"]


def test_cik_mismatch_and_ambiguous_or_wrong_unit_are_rejected():
    with pytest.raises(ValueError, match="companyfacts_cik_mismatch"):
        us_periods(_raw(), _facts(cik=999))
    assert us_periods(_raw(currency="CAD"), _facts(currency="USD")) == []
    facts = _facts()
    facts["facts"]["us-gaap"]["Revenues"]["units"] = {"USD/shares": []}
    rows = us_periods(_raw(), facts)
    assert all(row["revenue"] is None for row in rows)
    raw = _raw(currency="")
    facts = _facts()
    facts["facts"]["us-gaap"]["Revenues"]["units"]["CAD"] = list(
        facts["facts"]["us-gaap"]["Revenues"]["units"]["USD"])
    rows = us_periods(raw, facts)
    assert all(row["revenue"] is None for row in rows)


def test_future_published_rows_work_without_companyfacts_but_do_not_claim_cfs():
    raw = _raw()
    for source_key, rows in raw["series_quarterly"].items():
        for row in rows:
            row.update(start="2026-04-01", unit="USD", filed="2026-08-05", fy=2026)
    rows = us_periods(raw)
    assert len(rows) == 1
    assert rows[0]["period_kind"] == "quarter"
    assert rows[0]["fs_div"] is None
    assert rows[0]["scope_basis"] is None


def test_existing_producer_preserves_start_and_unit():
    path = ROOT / "api" / "intelligence" / "us_financials.py"
    spec = importlib.util.spec_from_file_location("usf_report_provenance", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    facts = {"facts": {"us-gaap": {"Revenues": {"units": {"CAD": [{
        "start": "2025-01-01", "end": "2025-12-31", "val": 100,
        "accn": "0000000001-26-000001", "fy": 2025, "fp": "FY",
        "form": "10-K", "filed": "2026-02-01",
    }]}}}}}
    row = module.extract_metric_series(facts, "revenue", currency="CAD")[0]
    assert row["start"] == "2025-01-01"
    assert row["unit"] == "CAD"
