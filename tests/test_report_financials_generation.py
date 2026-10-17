"""Regression coverage for annual financial-series source precedence."""
import json
from collections import defaultdict
from pathlib import Path

import api.builders.stock_report_public_builder as builder
import pytest


def test_fin_series_prefers_corrected_history_and_preserves_other_rows(monkeypatch):
    root = Path(builder._ROOT)
    manifest = json.loads(
        (root / "data/metadata/report_fin_history_corrections_20261017.json").read_text(
            encoding="utf-8"
        )
    )
    history_doc = json.loads(
        (root / "data/dart_kr_fin_history.json").read_text(encoding="utf-8")
    )
    corrections = manifest.get("rows")
    history_rows = history_doc.get("rows")
    assert isinstance(corrections, list) and corrections
    assert isinstance(history_rows, list)

    metric_fields = {"net": "net_income", "op": "operating_profit", "revenue": "revenue"}
    tickers = {str(row["ticker"]) for row in corrections}
    annual_history = [
        row for row in history_rows
        if isinstance(row, dict)
        and row.get("period") == "annual"
        and str(row.get("ticker") or "") in tickers
    ]

    # The checked-in correction manifest must describe the annual history actually
    # consumed by the generator; use the last source row for duplicate ticker/year keys.
    latest_history_by_key = {}
    for row in annual_history:
        latest_history_by_key[(str(row["ticker"]), int(row["fiscal_year"]))] = row
    stale_by_key = defaultdict(dict)
    for correction in corrections:
        ticker = str(correction["ticker"])
        year = int(correction["year"])
        metric = correction.get("metric", "net")
        assert metric in metric_fields
        history_row = latest_history_by_key[(ticker, year)]
        history_value = (history_row.get("fundamentals") or {}).get(metric_fields[metric])
        assert history_value == correction["after"]
        stale_by_key[(ticker, year)][metric_fields[metric]] = correction["before"]

    # Simulate older backfill cells using the manifest's reviewed prior values.
    # History remains the real local annual source and is appended after this fixture.
    backfill_rows = []
    for (ticker, year), stale_values in stale_by_key.items():
        template = latest_history_by_key[(ticker, year)]
        fundamentals = dict(template.get("fundamentals") or {})
        fundamentals.update(stale_values)
        backfill_rows.append({
            "ticker": ticker,
            "fiscal_year": year,
            "period": "annual",
            "fundamentals": fundamentals,
        })

    # Backfill-only, unregistered ticker exercises the loader's preservation of
    # unrelated coverage, the newest year, zero, and a negative reported value.
    unrelated_ticker = "999991"
    backfill_rows.extend([
        {"ticker": unrelated_ticker, "fiscal_year": 2024, "period": "annual",
         "fundamentals": {"revenue": 120, "operating_profit": 10, "net_income": -3}},
        {"ticker": unrelated_ticker, "fiscal_year": 2026, "period": "annual",
         "fundamentals": {"revenue": 0, "operating_profit": -17, "net_income": 0}},
    ])
    backfill_doc = {"rows": backfill_rows}
    selected_history_doc = {
        "rows": annual_history,
    }

    def load_fixture(path, default):
        if path == builder.DART_KR_BACKFILL_PATH:
            return backfill_doc
        if path == builder.DART_KR_FIN_HISTORY_PATH:
            return selected_history_doc
        return default

    monkeypatch.setattr(builder, "_load_json", load_fixture)
    result = builder._load_fin_series()

    for correction in corrections:
        ticker = str(correction["ticker"])
        year = int(correction["year"])
        metric = correction.get("metric", "net")
        if correction.get("publication_target") == "history_only":
            assert not any(row["year"] == year for row in result.get(ticker, []))
            continue
        series_row = next(row for row in result[ticker] if row["year"] == year)
        assert series_row[metric] == correction["after"]

    unrelated_series = result[unrelated_ticker]
    assert [row["year"] for row in unrelated_series] == [2024, 2026]
    assert unrelated_series[-1] == {
        "year": 2026, "revenue": 0, "op": -17, "net": 0,
    }


def _first_close_history(corrected=True):
    row = {"ticker": "489790", "name": "한화비전", "fiscal_year": 2024,
           "period": "annual", "fundamentals": {
               "revenue": 493322362934 if corrected else None,
               "operating_profit": -120362075,
               "net_income": 3210792631 if corrected else 31701255717}}
    if corrected:
        row.update(corp_code="01867758", period_kind="inception_partial",
                   start="2024-09-01", end="2024-12-31", currency="KRW", fs_div="CFS",
                   accession="20250317000812", filed="2025-03-17", source_column="제 1 기",
                   source_url="https://dart.fss.or.kr/report/viewer.do?rcpNo=20250317000812&dcmNo=10415585&eleId=21&offset=273070&length=19363&dtd=dart4.xsd",
                   source_sha256="3adf9e10ce84dc053c73264f9721f14d4a306da7ca828cb3f6eaf83846d01bf3")
    return row


@pytest.mark.parametrize("corrected", [False, True])
def test_first_four_months_never_enter_year_only_series_or_valuation(monkeypatch, corrected, capsys):
    first = _first_close_history(corrected)
    latest = {"ticker": "489790", "fiscal_year": 2025, "period": "annual",
              "fundamentals": {"revenue": 1790921869125, "operating_profit": 162267204336,
                               "net_income": 42619753835}}
    unrelated = [{"ticker": "999991", "fiscal_year": year, "period": "annual",
                  "fundamentals": {"revenue": 100, "operating_profit": 10, "net_income": -3}}
                 for year in (2024, 2025)]
    backfill = {"rows": [{"ticker": "489790", "fiscal_year": 2024, "period": "annual",
                          "fundamentals": {"revenue": None, "operating_profit": -120362075,
                                           "net_income": 31701255717}}, *unrelated]}
    history = {"rows": [first, latest]}
    monkeypatch.setattr(builder, "_load_json", lambda path, default: backfill if path == builder.DART_KR_BACKFILL_PATH
                        else history if path == builder.DART_KR_FIN_HISTORY_PATH else default)
    series = builder._load_fin_series()
    assert series["489790"] == [{"year": 2025, "revenue": 1790921869125,
                                  "op": 162267204336, "net": 42619753835}]
    assert [row["year"] for row in series["999991"]] == [2024, 2025]
    valuation = builder._valuation_map({}, {"489790": {"mktcap": 1000000000000}}, series)
    assert valuation["489790"]["_per_in"]["fiscal_year"] == 2025
    assert valuation["489790"]["_psr_in"]["fiscal_year"] == 2025
    bad = dict(first, fundamentals={**first["fundamentals"], "net_income": 31701255717 if corrected else 0})
    history["rows"][0] = bad
    with pytest.raises(ValueError, match="489790 first-period"):
        builder._load_fin_series()
    quarantined = set()
    held = builder._load_fin_series(quarantined)
    assert quarantined == {"489790"}
    assert "489790" not in held
    assert held["999991"] == series["999991"]
    assert "quarantine 489790" in capsys.readouterr().err


def test_identified_2024_partial_fundamentals_never_precedes_valid_2025_or_ttm():
    cap = {"489790": {"mktcap": 1000000000000, "shares": 50000000}}
    old = {"489790": {"report_date": "2024-12-31", "reprt_code": "11011",
                      "net_income": 31701255717, "revenue": 493322362934,
                      "total_assets": 1000000000000, "debt_ratio": 100}}
    annual = {"489790": [{"year": 2025, "revenue": 1790921869125, "op": 162267204336,
                          "net": 42619753835}]}
    value = builder._valuation_map(old, cap, annual)["489790"]
    assert value["_per_in"]["fiscal_year"] == 2025
    assert value["_psr_in"]["fiscal_year"] == 2025
    assert "PBR" not in value and "BPS" not in value
    ttm = {"489790": {"net_income_ttm": 50000000000, "equity": 400000000000,
                      "quarter_end": "2025-09-30"}}
    value = builder._valuation_map(old, cap, annual, ttm)["489790"]
    assert value["_per_in"]["basis"] == "ttm"
    assert value["_pbr_in"]["basis"] == "point_in_time"
    current = {"489790": {**old["489790"], "report_date": "2025",
                          "revenue": 1790921869125, "net_income": 42619753835,
                          "operating_profit": 162267204336}}
    value = builder._valuation_map(current, cap, annual, ttm)["489790"]
    assert value["_per_in"]["fiscal_year"] == "2025"
    assert value["_per_in"]["net_income"] == 42619753835.0
    assert value["_psr_in"]["revenue"] == 1790921869125.0


def test_lynch_does_not_use_first_four_months_as_growth_denominator(monkeypatch):
    from api.builders import kr_lynch_class_builder as lynch
    from api.intelligence import lynch_classifier

    seen = {}
    def classify(stock):
        seen["stock"] = stock
        return {"class": "SLOW", "data_quality": "ok"}
    monkeypatch.setattr(lynch_classifier, "classify_lynch_kr", classify)
    first = _first_close_history()
    latest = {"ticker": "489790", "fiscal_year": 2025, "period": "annual",
              "fundamentals": {"revenue": 1790921869125, "operating_profit": 162267204336}}
    inputs = {"dart_kr_fin_history.json": {"rows": [first, latest]},
              "krx_mktcap.json": {"map": {"489790": {"mktcap": 1000000000000, "close": 1000}}}}
    monkeypatch.setattr(lynch, "_load", lambda name, default=None: inputs.get(name, default))
    lynch.build()
    assert seen["stock"]["revenue_growth"] is None
    assert seen["stock"]["revenue_growth_fy"] is None
    assert seen["stock"]["operating_margin"] == pytest.approx(162267204336 / 1790921869125 * 100)


def test_lynch_quarantines_only_bad_first_close_and_keeps_unrelated(monkeypatch, capsys):
    from api.builders import kr_lynch_class_builder as lynch
    from api.intelligence import lynch_classifier

    first = _first_close_history()
    first.pop("source_sha256")
    other = {"ticker": "999991", "fiscal_year": 2025, "period": "annual",
             "fundamentals": {"revenue": 100, "operating_profit": 10}}
    inputs = {"dart_kr_fin_history.json": {"rows": [first, other]},
              "krx_mktcap.json": {"map": {"489790": {"mktcap": 1000, "close": 10},
                                          "999991": {"mktcap": 1000, "close": 10}}}}
    monkeypatch.setattr(lynch, "_load", lambda name, default=None: inputs.get(name, default))
    monkeypatch.setattr(lynch_classifier, "classify_lynch_kr",
                        lambda stock: {"class": "SLOW", "data_quality": "ok"})
    output = lynch.build()
    assert set(output["by_ticker"]) == {"999991"}
    assert output["_meta"]["count"] == 1
    assert "quarantine 489790" in capsys.readouterr().err


@pytest.mark.parametrize("ticker,revenue,gross,operating,net,status", [
    ("000210", 5326721292281, 1126332936404, 298546039560, -96298295176, "conflict"),
    ("041190", 162866987251, 0, 0, 110544592503, "unverified_zero"),
    ("100790", 239848243971, 0, 0, 30930410145, "unverified_zero"),
])
def test_received_sga_zero_is_not_published_as_verified_zero(ticker, revenue, gross, operating, net, status):
    # Exact inputs sampled from the checked-in KR fundamentals feed; source verification is separate.
    fund = {"revenue": revenue, "gross_profit": gross, "operating_profit": operating,
            "net_income": net, "sga": 0}
    before = dict(fund)
    output = builder._financials(fund)
    rows = {row["k"]: row for group in output["groups"] for row in group["rows"]}
    sga = rows["판매비와관리비"]
    assert sga["status"] == status and sga["received_value"] == "0", ticker
    assert sga["v"] == "미확인 (수신값 0)" and fund == before, ticker
    assert rows["순이익"]["v"] == builder._fmt_won_signed(net)
