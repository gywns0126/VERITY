"""Offline targeted report seeds, namespace proof and official-IR annual overlays."""
import copy
import json
from pathlib import Path
import socket

import pytest

from api.builders import us_stock_report_public_builder as builder

ROOT = Path(__file__).resolve().parents[1]
PROOF_KEYS = {"cik", "accession", "form", "period_end", "tag", "source_url", "currency_verified"}


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("No network in report regression tests")
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def cache(currency="TWD", form="20-F", namespace="ifrs-full"):
    tags = ("Revenue", "ProfitLossFromOperatingActivities", "ProfitLossAttributableToOwnersOfParent")
    if namespace == "us-gaap":
        tags = ("Revenues", "OperatingIncomeLoss", "NetIncomeLoss")
    return {"ticker": "TEST", "meta": {"cik": 1046179, "currency": currency, "namespace": namespace},
            "series_annual": {key: [{"end": f"{y}-12-31", "val": value, "form": form,
                "tag": tag, "namespace": namespace, "unit": currency,
                "accn": "0001046179-26-000001", "fp": "FY", "is_annual": True}
                for y, value in [(2023, 100), (2024, 200)]]
                for key, tag in zip(("revenue", "operating_income", "net_income"), tags)}}


@pytest.mark.parametrize("currency", ["TWD", "MXN", "ARS"])
@pytest.mark.parametrize("tag", ["Revenue", "RevenueFromContractsWithCustomers"])
def test_ifrs_proof_has_closed_keys_and_known_native_units(tmp_path, monkeypatch, currency, tag):
    doc = cache(currency)
    doc["series_annual"]["revenue"][-1]["tag"] = tag
    write_json(tmp_path / "data/us_financials/TEST.json", doc)
    monkeypatch.setattr(builder, "_ROOT", str(tmp_path))
    fs, fin = builder._load_us_annual_pack("TEST")
    assert fin["currency"] == currency
    for point in fs:
        assert set(point["metric_sources"]) == {"revenue", "op", "net"}
        for proof in point["metric_sources"].values():
            assert set(proof) == PROOF_KEYS and proof["currency_verified"] is True
    assert fs[-1]["metric_sources"]["revenue"]["tag"] == tag


@pytest.mark.parametrize("currency,form,namespace", [
    ("USD", "20-F", "ifrs-full"), ("CAD", "10-K", "us-gaap"),
    ("USD", "40-F/A", "us-gaap"), ("CAD", "6-K", "us-gaap"),
    ("USD", None, "us-gaap"),
])
def test_annual_label_uses_form_not_currency(tmp_path, monkeypatch, currency, form, namespace):
    write_json(tmp_path / "data/us_financials/TEST.json", cache(currency, form, namespace))
    monkeypatch.setattr(builder, "_ROOT", str(tmp_path))
    fs, fin = builder._load_us_annual_pack("TEST")
    title = fin["groups"][0]["title"]
    if form in builder._ANNUAL_SOURCE_FORMS:
        assert f"연간 {form}" in title
    else:
        assert "제출 양식 미확인" in title
        assert all("metric_sources" not in p for p in fs)


@pytest.mark.parametrize("namespace,tag,form", [
    ("us-gaap", "Revenue", "20-F"), ("custom", "Revenue", "20-F"),
    ("ifrs-full", "Revenues", "20-F"), ("ifrs-full", "Revenue", "6-K"),
])
def test_namespace_and_6k_gate_do_not_invent_sec_proof(tmp_path, monkeypatch, namespace, tag, form):
    doc = cache(form=form)
    doc["meta"]["namespace"] = namespace
    for row in doc["series_annual"]["revenue"]:
        row.update(namespace=namespace, tag=tag)
    write_json(tmp_path / "data/us_financials/TEST.json", doc)
    monkeypatch.setattr(builder, "_ROOT", str(tmp_path))
    fs, _ = builder._load_us_annual_pack("TEST")
    assert fs[-1]["revenue"] == 200
    assert all("revenue" not in p.get("metric_sources", {}) for p in fs)


def supplement(currency="CAD"):
    return {"currency": currency, "period_end": "2025-12-31", "source_label": "기업 연차보고서 원문 수동 보충",
            "source_url": "https://www.cn.ca/annual.pdf", "fs": [
                {"year": year, "currency": currency, "revenue": year * 1000000, "op": 0, "net": -100,
                 "manual_source": {"page": 72, "original_unit": "millions", "multiplier": 1000000,
                                   "net_basis": "consolidated net income", "private": "must not leak"}}
                for year in (2023, 2024, 2025)]}


def test_manual_overlay_only_newer_same_currency_preserves_existing_years():
    fs = [{"year": 2023, "currency": "CAD", "revenue": 100, "op": None, "net": 10,
           "metric_sources": {"revenue": {"sentinel": "unchanged"}}},
          {"year": 2024, "currency": "CAD", "revenue": 200, "op": None, "net": 20}]
    fin = {"period": "2024", "currency": "CAD", "groups": []}
    before = copy.deepcopy((fs, fin))
    merged, manual = builder._overlay_annual_supplement(fs, fin, supplement())
    assert merged[:2] == fs and (fs, fin) == before
    assert merged[-1]["revenue"] == 2025000000  # Not multiplied twice.
    assert "metric_sources" not in merged[-1]
    assert merged[-1]["manual_source"]["page"] == 72
    assert "private" not in merged[-1]["manual_source"]
    assert manual["source_url"] == "https://www.cn.ca/annual.pdf"
    assert manual["source_label"] == supplement()["source_label"]
    assert "수동 보충" in manual["groups"][0]["title"] and "40-F" not in str(manual)
    assert manual["groups"][0]["rows"][1]["v"] == "C$0"
    assert builder._overlay_annual_supplement(merged, manual, supplement()) == (merged, manual)
    assert builder._overlay_annual_supplement(fs, fin, supplement("MXN")) == (fs, fin)


@pytest.mark.parametrize("change", ["currency", "date", "url", "bool", "nan", "point_currency"])
def test_invalid_supplement_does_not_touch_financials(change):
    value = supplement()
    if change == "currency": value["currency"] = "UNKNOWN"
    if change == "date": value["period_end"] = "2025-02-30"
    if change == "url": value["source_url"] = "file:///private/document"
    for p in value["fs"]:
        if change == "bool": p["revenue"] = True
        if change == "nan": p["revenue"] = float("nan")
        if change == "point_currency": p["currency"] = "USD"
    assert builder._overlay_annual_supplement(None, None, value, "CAD") == (None, None)


@pytest.mark.parametrize("ticker", ["TSM", "KOF", "CNI"])
def test_main_handoff_shape_is_accepted_without_network(ticker):
    path = ROOT / "output/guru-portfolio-backfill-20261004/manual-annual-sources.json"
    if not path.is_file():
        pytest.skip("Optional local handoff not present; no replacement fetched")
    value = json.loads(path.read_text(encoding="utf-8"))[ticker]
    fs, fin = builder._overlay_annual_supplement(None, None, value, value["currency"])
    assert fin["period"] == "2025" and fin["currency"] == value["currency"]
    assert fin["manual_source"]["multiplier"] == value["fs"][-1]["manual_source"]["multiplier"]
    assert fin["source_url"] == value["source_url"]
    if fs:
        assert fs[-1]["revenue"] == value["fs"][-1]["revenue"]
        assert all("metric_sources" not in p for p in fs)


@pytest.mark.parametrize("with_cache", [False, True])
def test_main_missing_class_fallback_survives_seed_and_refresh(tmp_path, monkeypatch, with_cache):
    summary = tmp_path / "summary.json"
    output = tmp_path / "report.json"
    compact = tmp_path / "compact.json"
    seed = tmp_path / "seed.json"
    live_row = {"ticker": "LIVE", "entity_name": "Live", "revenue_yoy_pct_annual": 5}
    target_row = {"ticker": "TEST", "entity_name": "Target", "revenue_yoy_pct_annual": 10}
    target_meta = {"currency": "TWD", "sic_description": "Target sector"}
    old_fs = [{"year": y, "currency": "TWD", "revenue": y, "op": 1, "net": 1} for y in (2022, 2023)]
    target = {"row": target_row, "meta": target_meta, "fs": old_fs, "fin": None,
              "supplement": supplement("TWD")}
    write_json(summary, {"rows": [live_row]})
    write_json(seed, {"stocks": {"TEST": target, "LIVE": {"row": {"ticker": "LIVE", "entity_name": "WRONG"}}}})
    current_fs = [{**p, "revenue": 333} for p in old_fs]
    unrelated = {"fs": [], "fin": {"sentinel": 1}}
    write_json(compact, {"stocks": {"TEST": {"fs": current_fs, "fl": None}, "UNRELATED": unrelated}})
    seed_bytes = seed.read_bytes()
    if with_cache:
        write_json(tmp_path / "data/us_financials/TEST.json", cache())
    monkeypatch.setattr(builder, "_ROOT", str(tmp_path))
    monkeypatch.setattr(builder, "FIN_COMPACT_PATH", str(compact))
    monkeypatch.setattr(builder, "GURU_SUPPLEMENT_PATH", str(seed))
    monkeypatch.setattr(builder, "_COMPACT_CACHE", None)
    monkeypatch.setattr(builder, "EARN_PATTERN_PATH", str(tmp_path / "no-patterns.json"))
    for name in ("_load_universe_caps", "_load_sic_ko", "_load_name_ko", "_load_us_consensus",
                 "_load_major_holdings", "_load_us_disclosures"):
        monkeypatch.setattr(builder, name, lambda: {})
    monkeypatch.setattr(builder.sys, "argv", ["report", "--summary", str(summary), "--output", str(output)])
    assert builder._compact_store()["TEST"]["fs"] == current_fs
    for _ in range(2):
        assert builder.main() == 0
        stocks = {s["ticker"]: s for s in json.loads(output.read_text())["stocks"]}
        assert set(stocks) == {"LIVE", "TEST"}
        assert stocks["LIVE"]["name"] == "Live"
        assert stocks["TEST"]["financials"]["period"] == "2025"
        assert "PER" not in stocks["TEST"]["facts"]
        first = stocks["TEST"]["fin_series"][0]
        assert first["revenue"] == (100 if with_cache else 333)
        saved = json.loads(compact.read_text())["stocks"]
        assert saved["UNRELATED"] == unrelated
        assert saved["TEST"]["row"] == target_row and saved["TEST"]["meta"] == target_meta
        assert saved["TEST"]["supplement"] == target["supplement"]
        assert seed.read_bytes() == seed_bytes


def test_only_explicit_missing_rows_expand_universe():
    live = {"ticker": "GOOG", "entity_name": "keep"}
    compact = {"GOOG": {"row": {"ticker": "GOOG", "entity_name": "replace"}},
               "GOOGL": {"row": {"ticker": "GOOGL"}, "meta": {"sic_description": "Alphabet"}},
               "UNTARGETED": {"fs": []}, "MISMATCH": {"row": {"ticker": "OTHER"}}}
    rows, metas = builder._targeted_compact_rows([live], compact)
    assert rows == [live, {"ticker": "GOOGL"}]
    assert metas["GOOGL"] == {"sic_description": "Alphabet"}


@pytest.mark.parametrize("ticker", ["FNV", "KGC", "TECK"])
@pytest.mark.parametrize("current_year,currency,prefer", [
    (2025, "CAD", True), (2026, "CAD", False), (2025, "USD", False),
])
def test_same_year_thin_compact_uses_whole_deeper_native_seed(
        tmp_path, monkeypatch, ticker, current_year, currency, prefer):
    current = {"fs": None, "fin": {"period": str(current_year), "currency": currency,
                                  "values": {"sentinel": "current"}}, "fl": {"sentinel": 1}}
    seed_pack = {"fs": [{"year": y, "currency": "CAD", "revenue": y} for y in (2023, 2024, 2025)],
                 "fin": {"period": "2025", "currency": "CAD", "values": {"sentinel": "seed"}}, "fl": None,
                 "row": {"ticker": ticker}}
    compact, seed = tmp_path / "compact.json", tmp_path / "seed.json"
    write_json(compact, {"stocks": {ticker: current}})
    write_json(seed, {"stocks": {ticker: seed_pack}})
    monkeypatch.setattr(builder, "FIN_COMPACT_PATH", str(compact))
    monkeypatch.setattr(builder, "GURU_SUPPLEMENT_PATH", str(seed))
    merged = builder._read_compact_inputs()[ticker]
    expected = seed_pack if prefer else current
    assert {k: merged[k] for k in ("fs", "fin", "fl")} == {k: expected[k] for k in ("fs", "fin", "fl")}


def test_same_year_exact_period_end_precedes_history_depth():
    current = {"fs": [{"year": 2025, "currency": "CAD", "period_end": "2025-12-31"}]}
    seed = {"fs": [{"year": 2024, "currency": "CAD"},
                   {"year": 2025, "currency": "CAD", "period_end": "2025-09-30"}]}
    assert not builder._prefer_seed_financial_pack(current, seed)
    seed["fs"][-1]["period_end"] = "2025-12-31"
    assert builder._prefer_seed_financial_pack(current, seed)


@pytest.mark.parametrize("live_feed", [False, True])
def test_main_disclosure_fallback_and_historical_coverage(tmp_path, monkeypatch, live_feed):
    summary, output, compact, seed = [tmp_path / f"{n}.json" for n in ("summary", "report", "compact", "seed")]
    historical = {"ticker": "EA", "entity_name": "Historical", "revenue_yoy_pct_annual": 1}
    old_disc, fresh_disc = [{"title": "seed disclosure"}], [{"title": "fresh feed"}]
    coverage = {"sec_latest_annual_period": "2025-03-31", "annual_point_count": 3}
    write_json(summary, {"rows": []})
    write_json(compact, {"stocks": {}})
    write_json(seed, {"stocks": {"EA": {"row": historical,
        "meta": {"historical_ticker": True, "historical_ticker_note": "과거 보유 공시·재무 자료",
                 "sic_description": "Software"}, "disclosures": old_disc, "data_coverage": coverage}}})
    before = seed.read_bytes()
    monkeypatch.setattr(builder, "_ROOT", str(tmp_path))
    monkeypatch.setattr(builder, "FIN_COMPACT_PATH", str(compact))
    monkeypatch.setattr(builder, "GURU_SUPPLEMENT_PATH", str(seed))
    monkeypatch.setattr(builder, "EARN_PATTERN_PATH", str(tmp_path / "missing-patterns.json"))
    for name in ("_load_universe_caps", "_load_sic_ko", "_load_name_ko", "_load_us_consensus", "_load_major_holdings"):
        monkeypatch.setattr(builder, name, lambda: {})
    monkeypatch.setattr(builder, "_load_us_disclosures", lambda: {"EA": fresh_disc} if live_feed else {})
    monkeypatch.setattr(builder.sys, "argv", ["report", "--summary", str(summary), "--output", str(output)])
    for _ in range(2):
        assert builder.main() == 0
        stock = json.loads(output.read_text())["stocks"][0]
        assert stock["disclosures"] == (fresh_disc if live_feed else old_disc)
        assert stock["business"].startswith("과거 티커 · ")
        assert stock["data_coverage"] == {**coverage, "historical_ticker": True, "note": "과거 보유 공시·재무 자료"}
        assert seed.read_bytes() == before


def test_manual_comparatives_bind_point_dates_separately_from_document_date():
    value = supplement()
    value["fs"][0]["period_end"] = "2023-09-30"
    fs, fin = builder._overlay_annual_supplement(None, None, value, "CAD")
    assert [p["manual_source"]["period_end"] for p in fs] == [
        "2023-09-30", "2024-12-31", "2025-12-31"]
    assert all(p["manual_source"]["document_period_end"] == "2025-12-31" for p in fs)
    assert fin["manual_source"]["period_end"] == "2025-12-31"
    value["fs"][0]["period_end"] = "2024-09-30"  # Wrong point year cannot masquerade as 2023.
    fs, _ = builder._overlay_annual_supplement(None, None, value, "CAD")
    assert [p["year"] for p in fs] == [2024, 2025]


def test_legacy_untyped_no_form_cache_keeps_legacy_label(tmp_path, monkeypatch):
    doc = cache("USD", None, "us-gaap")
    doc["meta"].pop("namespace")
    for series in doc["series_annual"].values():
        for row in series:
            row.pop("namespace")
            row.pop("form")
    write_json(tmp_path / "data/us_financials/TEST.json", doc)
    monkeypatch.setattr(builder, "_ROOT", str(tmp_path))
    _, fin = builder._load_us_annual_pack("TEST")
    assert fin["groups"][0]["title"] == "손익계산서 (연간 10-K)"


@pytest.mark.parametrize("pending", [True, False, None, "true"])
def test_seed_native_chart_guard_retains_data_without_affecting_other_rows(tmp_path, monkeypatch, pending):
    summary, output, compact, seed = [tmp_path / f"{n}.json" for n in ("summary", "report", "compact", "seed")]
    tickers = {"CNI": "CAD", "TSM": "TWD", "KOF": "MXN", "TECK": "CAD"}
    targets = {}
    for ticker, currency in tickers.items():
        targets[ticker] = {"row": {"ticker": ticker},
            "meta": {"currency": currency, "native_chart_pending": pending},
            "fs": [{"year": y, "currency": currency, "revenue": y * 1000000, "op": 1, "net": 1}
                   for y in (2024, 2025)],
            "fin": {"period": "2025", "currency": currency,
                    "values": {"매출": builder._ccy_sym(currency) + "2B"},
                    "groups": [{"title": "Annual", "rows": [{"k": "영업이익", "v": "-" + builder._ccy_sym(currency) + "0"}]}],
                    "source_url": "https://official.example/annual.pdf"},
            "data_coverage": {"annual_point_count": 2}}
    # A native-series-only target must survive the existing empty-shell filter.
    targets["TECK"]["fin"] = None
    usd_fs = [{"year": y, "currency": "USD", "revenue": y} for y in (2024, 2025)]
    write_json(summary, {"rows": [{"ticker": "USD"}]})
    write_json(compact, {"stocks": {"USD": {"fs": usd_fs, "fin": None}}})
    write_json(seed, {"stocks": targets})
    seed_bytes = seed.read_bytes()
    monkeypatch.setattr(builder, "_ROOT", str(tmp_path))
    monkeypatch.setattr(builder, "FIN_COMPACT_PATH", str(compact))
    monkeypatch.setattr(builder, "GURU_SUPPLEMENT_PATH", str(seed))
    monkeypatch.setattr(builder, "EARN_PATTERN_PATH", str(tmp_path / "missing-patterns.json"))
    for name in ("_load_universe_caps", "_load_sic_ko", "_load_name_ko", "_load_us_consensus",
                 "_load_major_holdings", "_load_us_disclosures"):
        monkeypatch.setattr(builder, name, lambda: {})
    monkeypatch.setattr(builder, "_load_universe_caps", lambda: {
        "CNI": {"market_cap": 5000000000}, "USD": {"market_cap": 5000000000}})
    monkeypatch.setattr(builder.sys, "argv", ["report", "--summary", str(summary), "--output", str(output)])
    for _ in range(2):
        assert builder.main() == 0
        stocks = {s["ticker"]: s for s in json.loads(output.read_text())["stocks"]}
        assert set(stocks) == {*tickers, "USD"}
        assert stocks["USD"]["fin_series"] == usd_fs and "fin_series_native" not in stocks["USD"]
        assert stocks["USD"]["header"]["market_cap"] == "$5.0B"
        assert stocks["CNI"]["header"]["market_cap"] == "$5.0B"
        for ticker in tickers:
            stock = stocks[ticker]
            series_key = "fin_series_native" if pending is True else "fin_series"
            assert stock[series_key] == targets[ticker]["fs"]
            assert ("fin_series" not in stock) is (pending is True)
            if pending is True:
                assert stock["data_coverage"]["annual_chart_pending"] is True
            else:
                assert "annual_chart_pending" not in stock["data_coverage"]
            if ticker != "TECK":
                expected = builder._native_financials_iso(targets[ticker]["fin"]) if pending is True else targets[ticker]["fin"]
                assert stock["financials"] == expected
                if pending is True:
                    assert all("$" not in value for value in stock["financials"]["values"].values())
                    assert all("$" not in row["v"] for g in stock["financials"]["groups"] for row in g["rows"])
                assert stock["financials"]["source_url"] == targets[ticker]["fin"]["source_url"]
            saved = json.loads(compact.read_text())["stocks"][ticker]
            assert saved["fs"] == targets[ticker]["fs"]
        assert seed.read_bytes() == seed_bytes


@pytest.mark.parametrize("currency", ["CAD", "TWD", "MXN"])
def test_native_financials_iso_preserves_sign_zero_and_sources_not_usd(currency):
    symbol = builder._ccy_sym(currency)
    source = {"source_url": "https://official.example/report?currency=$", "period_end": "2025-12-31"}
    fin = {"currency": currency, "values": {"매출": symbol + "2B", "순이익": "-" + symbol + "0"},
           "groups": [{"title": "Official IR", "rows": [
               {"k": "매출", "v": symbol + "2B"}, {"k": "영업이익", "v": "-" + symbol + "0"},
               {"k": "EPS", "v": "+" + symbol + "0.00"}, {"k": "margin", "v": "20%"}]}],
           "manual_source": source, "source_url": source["source_url"]}
    original = copy.deepcopy(fin)
    result = builder._native_financials_iso(fin)
    assert result["values"] == {"매출": currency + " 2B", "순이익": "-" + currency + " 0"}
    assert [r["v"] for r in result["groups"][0]["rows"]] == [
        currency + " 2B", "-" + currency + " 0", "+" + currency + " 0.00", "20%"]
    assert all("$" not in value for value in result["values"].values())
    assert all("$" not in r["v"] for r in result["groups"][0]["rows"])
    assert result["manual_source"] == source and result["source_url"] == source["source_url"]
    assert fin == original
    usd = {**fin, "currency": "USD", "values": {"매출": "$2B"}}
    assert builder._native_financials_iso(usd) == usd
