"""Regression coverage for annual financial-series source precedence."""
import json
from collections import defaultdict
from pathlib import Path

import api.builders.stock_report_public_builder as builder


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

    metric_fields = {"net": "net_income", "op": "operating_profit"}
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
        series_row = next(row for row in result[ticker] if row["year"] == year)
        assert series_row[metric] == correction["after"]

    unrelated_series = result[unrelated_ticker]
    assert [row["year"] for row in unrelated_series] == [2024, 2026]
    assert unrelated_series[-1] == {
        "year": 2026, "revenue": 0, "op": -17, "net": 0,
    }
