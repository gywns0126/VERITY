"""Offline IFRS extraction, currency isolation and legacy US-GAAP contracts."""
from copy import deepcopy

import pytest

from api.intelligence import us_financials as usf


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("IFRS tests must not call the network")
    monkeypatch.setattr(usf.requests, "get", forbidden)


def annual(value, year=2024, form="20-F", accn="0001193125-25-000001", **extra):
    return {"start": f"{year}-01-01", "end": f"{year}-12-31", "val": value,
            "fy": year, "fp": "FY", "form": form, "accn": accn, **extra}


def facts(tags, namespace="ifrs-full"):
    return {"cik": 1046179, "entityName": "IFRS fixture", "facts": {namespace: {
        tag: {"units": units} for tag, units in tags.items()
    }}}


def extract(payload, metric, currency="TWD", **kwargs):
    return usf.extract_metric_series(payload, metric, currency=currency, **kwargs)


@pytest.mark.parametrize("form", ["20-F", "20-F/A", "40-F", "40-F/A"])
def test_foreign_annual_forms_and_exact_source(form):
    row = extract(facts({"Revenue": {"TWD": [annual(120, form=form)]}}), "revenue")[0]
    assert row == {"start": "2024-01-01", "end": "2024-12-31", "fy": 2024, "fp": "FY", "form": form,
                   "is_annual": True, "val": 120, "accn": "0001193125-25-000001",
                   "filed": None, "source_url": None,
                   "tag": "Revenue", "namespace": "ifrs-full", "unit": "TWD", "currency": "TWD"}


@pytest.mark.parametrize("metric,tag", [
    ("gross_profit", "GrossProfit"),
    ("operating_income", "ProfitLossFromOperatingActivities"),
    ("pretax_income", "ProfitLossBeforeTax"),
    ("cash", "CashAndCashEquivalents"),
    ("long_term_debt", "LongtermBorrowings"),
    ("operating_cash_flow", "CashFlowsFromUsedInOperatingActivities"),
    ("capex", "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities"),
    ("total_assets", "Assets"),
    ("current_assets", "CurrentAssets"),
    ("current_liabilities", "CurrentLiabilities"),
    ("total_liabilities", "Liabilities"),
    ("retained_earnings", "RetainedEarnings"),
])
def test_canonical_tags(metric, tag):
    row = annual(50)
    if metric in usf.INSTANT_METRICS:
        row.pop("start")
    out = extract(facts({tag: {"TWD": [row]}}), metric)
    assert len(out) == 1
    assert (out[0]["val"], out[0]["tag"], out[0]["unit"]) == (50, tag, "TWD")


@pytest.mark.parametrize("metric,preferred,fallback", [
    ("net_income", "ProfitLossAttributableToOwnersOfParent", "ProfitLoss"),
    ("stockholders_equity", "EquityAttributableToOwnersOfParent", "Equity"),
])
def test_parent_concept_preferred_and_fallback_only_fills_gaps(metric, preferred, fallback):
    payload = facts({preferred: {"TWD": [annual(40, accn="a-001")]},
                     fallback: {"TWD": [annual(50, accn="z-002"), annual(30, year=2023)]}})
    rows = extract(payload, metric)
    assert [(r["val"], r["tag"]) for r in rows] == [(30, fallback), (40, preferred)]


def test_year_end_dedupe_uses_period_year_and_latest_restatement():
    rows = [annual(100, year=2023, fy=2024, accn="a-001"),
            annual(105, year=2023, fy=2025, accn="a-002"), annual(120)]
    out = extract(facts({"Revenue": {"TWD": rows}}), "revenue")
    assert [(r["end"], r["fy"], r["val"]) for r in out] == [
        ("2023-12-31", 2023, 105), ("2024-12-31", 2024, 120)]
    for row in rows:
        row.pop("start")
    out = extract(facts({"Assets": {"TWD": rows}}), "total_assets")
    assert len(out) == 2 and out[0]["val"] == 105


def test_native_currency_beats_stale_usd_and_preserves_input():
    payload = facts({tag: {"TWD": [annual(100, year=2024), annual(120, year=2025)],
                          "USD": [annual(4, year=2024)]}
                     for tag in ("Revenue", "Assets", "ProfitLoss", "Equity")})
    original = deepcopy(payload)
    out = usf.fetch_all_metrics(1046179, facts=payload, sic_pair=(3674, "Semiconductors"))
    assert out["meta"]["currency"] == "TWD"
    assert out["meta"]["namespace"] == "ifrs-full"
    assert {r["currency"] for rows in out["metrics"].values() for r in rows} == {"TWD"}
    assert out["metrics"]["revenue"][-1]["end"] == "2025-12-31"
    assert payload == original


def test_fact_counts_break_common_latest_currency_tie():
    payload = facts({"Revenue": {"USD": [annual(4)],
                                  "TWD": [annual(100, year=2023), annual(120)]}})
    assert usf._detect_currency(payload) == "TWD"


def test_common_latest_coverage_beats_larger_stale_fact_count():
    payload = facts({tag: {"USD": [annual(4, year=y) for y in range(2010, 2025)],
                          "TWD": [annual(120, year=2025)]}
                     for tag in ("Revenue", "Assets", "ProfitLoss")})
    assert usf._detect_currency(payload) == "TWD"


def test_no_cross_currency_fallback_or_money_from_share_units():
    payload = facts({"Revenue": {"TWD": [annual(120)]},
                     "ProfitLoss": {"USD": [annual(4)]},
                     "GrossProfit": {"USD/shares": [annual(2)], "shares": [annual(3)]}})
    out = usf.fetch_all_metrics(1046179, facts=payload, sic_pair=(None, None))
    assert out["meta"]["currency"] == "TWD"
    assert out["metrics"]["net_income"] == []
    assert out["metrics"]["gross_profit"] == []
    assert extract(facts({"Revenues": {"USD": [annual(4, form="10-K")]}},
                         namespace="us-gaap"), "revenue") == []


@pytest.mark.parametrize("currency", ["TWD", "USD"])
def test_ifrs_eps_not_promoted_to_adr_eps_and_share_units_preserved(currency):
    payload = facts({"DilutedEarningsLossPerShare": {f"{currency}/shares": [annual(2)]},
                     "AdjustedWeightedAverageShares": {"shares": [annual(1000)]}})
    assert extract(payload, "eps_diluted", currency) == []
    rows = extract(payload, "diluted_shares", currency)
    assert rows[0]["val"] == 1000 and rows[0]["unit"] == "shares"
    assert rows[0]["currency"] is None


def test_6k_does_not_invent_annual_or_quarterly_data_or_currency():
    payload = facts({"Revenue": {"TWD": [annual(120)],
                                  "USD": [annual(4, year=2025, form="6-K")]},
                     "Assets": {"USD": [annual(30, year=2025, form="6-K")]}})
    assert usf._detect_currency(payload) == "TWD"
    assert extract(payload, "revenue", "USD") == []
    assert extract(payload, "total_assets", "USD") == []


def test_missing_or_unmapped_tags_are_graceful():
    payload = facts({"PropertyPlantAndEquipmentGross": {"TWD": [annual(90)]}})
    out = usf.build_ticker_snapshot("TEST", 1046179, facts=payload, sic_pair=(None, None))
    assert set(out["series_annual"]) == set(usf.TAG_ALIASES)
    assert all(not rows for rows in out["series_annual"].values())
    assert len(out["_errors"]) == len(usf.TAG_ALIASES)


def test_financial_revenue_override_still_extracts_ifrs_revenue():
    payload = facts({"Revenue": {"USD": [annual(120)]}})
    out = usf.fetch_all_metrics(1046179, facts=payload, sic_pair=(6021, "Bank"))
    assert out["metrics"]["revenue"][0]["val"] == 120
    assert out["metrics"]["revenue"][0]["tag"] == "Revenue"


def test_non_usd_ifrs_snapshot_keeps_fcf_native_and_does_not_mix_usd_market_cap():
    values = {"Revenue": 120, "ProfitLossFromOperatingActivities": 30,
              "ProfitLoss": 20, "Equity": 100, "Assets": 200,
              "Liabilities": 100, "CurrentAssets": 100, "CurrentLiabilities": 50,
              "RetainedEarnings": 40, "CashFlowsFromUsedInOperatingActivities": 40,
              "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities": 10}
    payload = facts({tag: {"TWD": [annual(value)]} for tag, value in values.items()})
    out = usf.build_ticker_snapshot("TEST", 1046179, market_cap=1e12,
                                    facts=payload, sic_pair=(3674, "Semiconductors"))
    assert out["derived"]["fcf"] == 30
    assert out["derived"]["fcf_currency"] == "TWD"
    assert "fcf_usd" not in out["derived"]
    assert out["derived"]["altman_z"]["model_variant"] == "altman_zpp_book"
    assert out["derived"]["operating_margin_pct"] == 25


def test_usgaap_rows_units_aliases_and_eps_remain_legacy():
    payload = facts({"Revenues": {"USD": [annual(120, form="10-K")]},
                     "EarningsPerShareDiluted": {"USD/shares": [annual(2, form="10-K")]},
                     "WeightedAverageNumberOfDilutedSharesOutstanding": {"shares": [annual(1000, form="10-K")]}},
                    namespace="us-gaap")
    payload["facts"]["ifrs-full"] = {"Revenue": {"units": {"USD": [annual(999)]}}}
    assert usf._detect_currency(payload) == "USD"
    row = extract(payload, "revenue", "USD")[0]
    assert row == {"start": "2024-01-01", "end": "2024-12-31", "fy": 2024, "fp": "FY", "form": "10-K",
                   "is_annual": True, "val": 120, "accn": "0001193125-25-000001", "tag": "Revenues",
                   "filed": None, "source_url": None, "unit": "USD"}
    assert extract(payload, "eps_diluted", "USD")[0]["val"] == 2
    assert extract(payload, "eps_diluted", "TWD") == []
    assert extract(payload, "diluted_shares", "USD")[0]["val"] == 1000


@pytest.mark.parametrize("tag,units", [
    ("NetIncreaseDecreaseInSalesAndTransferPricesAndProductionCosts", {"ARS": [annual(10, year=2017)]}),
    ("Revenues", {"USD": []}),
    ("Revenues", {"USD": [annual(10, year=2025, form="6-K")]}),
])
def test_incidental_or_unusable_usgaap_does_not_hide_ifrs(tag, units):
    payload = facts({"Revenue": {"USD": [annual(120)]}})
    payload["facts"]["us-gaap"] = {tag: {"units": units}}
    assert usf._financial_namespace(payload) == "ifrs-full"
    out = usf.fetch_all_metrics(1046179, facts=payload, sic_pair=(None, None))
    assert out["metrics"]["revenue"][0]["val"] == 120


def test_obsolete_usgaap_revenue_yields_to_current_ifrs_contract_revenue():
    payload = facts({"Revenue": {"MXN": [annual(100, year=2021)]},
                     "RevenueFromContractsWithCustomers": {"MXN": [annual(120)]},
                     "Assets": {"MXN": [annual(200)]}})
    payload["facts"]["us-gaap"] = {"Revenues": {"units": {"MXN": [annual(110, year=2023)]}}}
    out = usf.fetch_all_metrics(1046179, facts=payload, sic_pair=(None, None))
    assert out["meta"]["namespace"] == "ifrs-full"
    assert out["meta"]["currency"] == "MXN"
    assert out["metrics"]["revenue"][-1]["tag"] == "RevenueFromContractsWithCustomers"
    assert out["metrics"]["revenue"][-1]["val"] == 120
    assert out["metrics"]["revenue"][-1]["end"] == "2024-12-31"


def test_current_usgaap_core_remains_preferred_to_older_ifrs():
    payload = facts({"Revenue": {"USD": [annual(100, year=2023)]}})
    payload["facts"]["us-gaap"] = {"Revenues": {"units": {"USD": [annual(120, form="10-K")]}}}
    assert usf._financial_namespace(payload) == "us-gaap"
    assert extract(payload, "revenue", "USD")[0]["val"] == 120


def test_equal_date_current_core_coverage_beats_single_incidental_core_tag():
    payload = facts({"Revenue": {"USD": [annual(120)]}, "Assets": {"USD": [annual(200)]}})
    payload["facts"]["us-gaap"] = {"Revenues": {"units": {"USD": [annual(100)]}}}
    assert usf._financial_namespace(payload) == "ifrs-full"


@pytest.mark.parametrize("cad_years,usd_years", [([2024, 2025], [2024]), ([2023, 2024], [2024])])
def test_usgaap_primary_cad_beats_convenience_usd(cad_years, usd_years):
    payload = facts({tag: {"CAD": [annual(120, year=y, form="40-F") for y in cad_years],
                          "USD": [annual(90, year=y, form="40-F") for y in usd_years]}
                     for tag in ("Revenues", "OperatingIncomeLoss", "NetIncomeLoss", "Assets")},
                    namespace="us-gaap")
    out = usf.fetch_all_metrics(1, facts=payload, sic_pair=(None, None))
    assert out["meta"]["currency"] == "CAD"
    for metric in ("revenue", "operating_income", "net_income"):
        assert len(out["metrics"][metric]) == len(cad_years)
        assert out["metrics"][metric][-1]["val"] == 120
    assert usf._detect_currency(facts({"Revenues": {"USD": [annual(90, form="10-K")]}},
                                    namespace="us-gaap")) == "USD"


def test_usgaap_cad_6k_keeps_currency_metadata_but_no_annual_or_quarterly_series():
    payload = facts({tag: {"CAD": [annual(120, year=2025, form="6-K")]}
                     for tag in ("Revenues", "OperatingIncomeLoss", "NetIncomeLoss", "Assets")},
                    namespace="us-gaap")
    out = usf.build_ticker_snapshot("CNI", 16868, facts=payload, sic_pair=(None, None))
    assert out["meta"]["currency"] == "CAD"
    assert all(not rows for rows in out["series_annual"].values())
    assert all(not rows for rows in out["series_quarterly"].values())


def test_ifrs_contract_revenue_alias_extends_history_without_replacing_total_revenue():
    payload = facts({"Revenue": {"CAD": [annual(100, year=2018), annual(140, year=2025)]},
                     "RevenueFromContractsWithCustomers": {"CAD": [annual(120, year=2024),
                                                                     annual(130, year=2025)]}})
    out = extract(payload, "revenue", "CAD")
    assert [(r["end"], r["val"]) for r in out] == [
        ("2018-12-31", 100), ("2024-12-31", 120), ("2025-12-31", 140)]
