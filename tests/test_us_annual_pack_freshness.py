"""Offline annual source selection and coherent valuation inputs."""
import importlib.util
import json
from pathlib import Path
import socket

import pytest

PATH = Path(__file__).resolve().parents[1] / "api/builders/us_stock_report_public_builder.py"
spec = importlib.util.spec_from_file_location("annual_builder_under_test", PATH)
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("network forbidden")
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)


def pack(years, currency="USD", end=None):
    return {"fs": [{"year": y, "currency": currency, "revenue": y * 100, "op": y, "net": y}
                   for y in years],
            "fin": {"period": str(max(years)), "currency": currency,
                    **({"period_end": end} if end else {})},
            "fl": {"net_income": max(years), "equity": 5000,
                   "eps_diluted": max(years) / 100, "fcf_usd": 100}}


def choose(fresh, cached):
    return builder._prefer_richer_annual_pack(fresh["fs"], fresh["fin"], cached["fs"], cached["fin"])


def test_short_newer_history_wins_as_one_pack():
    fresh, cached = pack([2025, 2026]), pack(range(2015, 2026))
    assert choose(fresh, cached) == (fresh["fs"], fresh["fin"])


def test_stale_cache_cannot_replace_newer_compact_table():
    fresh, cached = pack(range(2015, 2026)), pack([2025, 2026])
    assert choose(fresh, cached) == (cached["fs"], cached["fin"])


def test_same_year_uses_period_end_before_history_length():
    fresh, cached = pack([2025, 2026], end="2026-09-30"), pack(range(2015, 2027), end="2026-06-30")
    assert choose(fresh, cached) == (fresh["fs"], fresh["fin"])


def test_equal_period_keeps_longer_distinct_history():
    fresh, cached = pack([2025, 2026]), pack([2023, 2024, 2025, 2026])
    assert choose(fresh, cached) == (cached["fs"], cached["fin"])


def test_duplicate_rows_do_not_count_as_longer_history():
    fresh, cached = pack([2026] * 10), pack([2025, 2026])
    assert choose(fresh, cached) == (cached["fs"], cached["fin"])


def test_currency_conflict_never_mixes_chart_and_table():
    fresh, cached = pack([2026], "CAD"), pack([2024, 2025, 2026], "USD")
    assert choose(fresh, cached) == (fresh["fs"], fresh["fin"])


def test_valuation_ties_match_display_selection_not_filing_fy_hint():
    rows = [{"end": "2025-06-30", "fy": 2025, "val": 100},
            {"end": "2025-06-30", "fy": 2026, "val": 999},
            {"end": "2024-06-30", "fy": 2027, "val": 88}]
    assert builder._latest_annual(rows) == builder._annual_by_year(rows)[2025] == 100


@pytest.mark.parametrize("change", ["older_eps", "mixed_cf_period", "wrong_derived_fcf"])
def test_valuation_and_fcf_bind_to_display_period(tmp_path, monkeypatch, change):
    def row(value, end="2026-06-30"):
        return {"end": end, "fy": 2026, "val": value}
    doc = {"meta": {"currency": "USD"}, "derived": {"fcf_usd": 60}, "series_annual": {
        "revenue": [row(200)], "operating_income": [row(50)], "net_income": [row(30)],
        "stockholders_equity": [row(100)], "eps_diluted": [row(4)],
        "operating_cash_flow": [row(80)], "capex": [row(20)]}}
    if change == "older_eps":
        doc["series_annual"]["eps_diluted"][0]["end"] = "2025-06-30"
        doc["series_annual"]["net_income"][0]["end"] = "2025-06-30"
    elif change == "mixed_cf_period":
        doc["series_annual"]["capex"][0]["end"] = "2025-06-30"
    else:
        doc["derived"]["fcf_usd"] = 999
    path = tmp_path / "data/us_financials/MSFT.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(doc))
    monkeypatch.setattr(builder, "_ROOT", str(tmp_path))
    result = builder._load_fin_latest("MSFT")
    assert result["equity"] == 100
    if change == "older_eps":
        assert result["eps_diluted"] is None and result["net_income"] is None
        assert result["fcf_usd"] == 60
    else:
        assert result["eps_diluted"] == 4 and result["net_income"] == 30
        assert result["fcf_usd"] is None


@pytest.mark.parametrize("newer", ["raw", "compact", "public"])
def test_resolver_binds_raw_valuation_to_selected_source(monkeypatch, newer):
    raw, compact, public = pack([2024, 2025]), pack([2023, 2024, 2025]), pack([2025])
    selected = {"raw": raw, "compact": compact, "public": public}[newer]
    selected.update(pack([2025, 2026]))
    monkeypatch.setattr(builder, "_load_us_annual_pack", lambda ticker: (raw["fs"], raw["fin"]))
    calls = []
    monkeypatch.setattr(builder, "_load_fin_latest", lambda ticker: calls.append(ticker) or raw["fl"])
    result = builder._resolve_us_annual_pack("MSFT", compact, public)
    assert (result["fs"], result["fin"]) == (selected["fs"], selected["fin"])
    assert result["fl"] == (selected["fl"] if newer != "public" else None)
    assert calls == (["MSFT"] if newer == "raw" else [])


def _prepare_main(tmp_path, monkeypatch, newer):
    raw, cached = pack([2024, 2025]), pack([2024, 2025])
    selected = raw if newer == "raw" else cached
    selected.update(pack([2025, 2026]))
    summary, output, compact = (tmp_path / name for name in ("summary.json", "report.json", "compact.json"))
    summary.write_text(json.dumps({"rows": [{"ticker": "MSFT", "entity_name": "Microsoft"}]}))
    compact.write_text(json.dumps({"stocks": {"MSFT": cached}}))
    monkeypatch.setattr(builder, "_ROOT", str(tmp_path))
    monkeypatch.setattr(builder, "FIN_COMPACT_PATH", str(compact))
    monkeypatch.setattr(builder, "GURU_SUPPLEMENT_PATH", str(tmp_path / "absent.json"))
    monkeypatch.setattr(builder, "EARN_PATTERN_PATH", str(tmp_path / "absent-pattern.json"))
    monkeypatch.setattr(builder, "_load_us_annual_pack", lambda ticker: (raw["fs"], raw["fin"]))
    monkeypatch.setattr(builder, "_load_fin_latest", lambda ticker: raw["fl"])
    for name in ("_load_universe_caps", "_load_sic_ko", "_load_name_ko", "_load_us_consensus",
                 "_load_major_holdings", "_load_us_disclosures"):
        monkeypatch.setattr(builder, name, lambda: {})
    monkeypatch.setattr(builder.sys, "argv", ["report", "--summary", str(summary), "--output", str(output)])
    return selected, output, compact


@pytest.mark.parametrize("newer", ["raw", "compact"])
def test_main_chart_table_eps_and_saved_fl_share_source(tmp_path, monkeypatch, newer):
    selected, output, compact = _prepare_main(tmp_path, monkeypatch, newer)
    assert builder.main() == 0
    stock = json.loads(output.read_text())["stocks"][0]
    saved = json.loads(compact.read_text())["stocks"]["MSFT"]
    assert stock["fin_series"][-1]["year"] == 2026
    assert stock["financials"]["period"] == "2026"
    assert stock["facts"]["EPS"] == f"${selected['fl']['eps_diluted']:,.2f}"
    assert saved["fl"] == selected["fl"]
    assert saved["fs"] == stock["fin_series"]


def test_compact_write_failure_returns_nonzero_and_preserves_report(tmp_path, monkeypatch):
    import builtins
    _, output, compact = _prepare_main(tmp_path, monkeypatch, "raw")
    original_report = json.dumps({"stocks": [{"ticker": "MSFT", "marker": "existing-report"}]}).encode()
    output.write_bytes(original_report)
    original_open = builtins.open

    def fail_compact_write(path, mode="r", *args, **kwargs):
        if str(path) == str(compact) and "w" in mode:
            raise OSError("injected compact write failure")
        return original_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", fail_compact_write)
    assert builder.main() != 0
    assert output.read_bytes() == original_report
