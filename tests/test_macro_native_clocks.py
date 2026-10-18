"""Offline native receipts: observation periods are not collection clocks."""
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from threading import Barrier, Lock, local

import pytest
import requests

from api.collectors import cape_multpl as C
from api.collectors import ecos_macro as E
from api.collectors import fred_macro as F
from api.utils.macro_provenance import copy_meta
from api.utils import macro_runtime as runtime


SERIES = {
    "VIXCLS": "vix_close", "DGS10": "dgs10", "DGS2": "dgs2",
    "CPILFESL": "core_cpi", "M2SL": "m2",
    "IRLTLT01KRA156N": "korea_gov_10y",
    "INTDSRKRM193N": "korea_discount_rate",
    "RECPROUSM156N": "us_recession_smoothed_prob",
    "UNRATE": "unemployment_rate", "UMCSENT": "consumer_sentiment",
    "BAMLH0A0HYM2": "hy_spread", "T10YIE": "breakeven_inflation_10y",
    "WALCL": "fed_balance_sheet",
}
LIMITS = [260, 260, 260, 16, 60, 36, 24, 8, 16, 16, 260, 260, 12]
BASE = datetime.fromisoformat("2026-10-18T12:00:00+09:00")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    calls = []

    def blocked(*args, **kwargs):
        calls.append("blocked")
        raise AssertionError("Network is forbidden in native clock tests")

    monkeypatch.setattr(requests.sessions.Session, "request", blocked)
    monkeypatch.setattr("socket.socket.connect", blocked)
    monkeypatch.setattr(F, "FRED_API_KEY", "offline-test")
    monkeypatch.setattr(E, "ECOS_API_KEY", "offline-test")
    monkeypatch.setattr(F, "_log_fred_health", lambda *a, **k: None)
    monkeypatch.setattr(E, "now_kst", lambda: BASE)
    yield
    assert calls == [], "Even swallowed network attempts must fail this test"


def cpi_rows():
    rows = []
    for i in range(25):
        month = 2024 * 12 + 8 + i
        rows.append({"TIME": f"{month // 12}{month % 12 + 1:02}",
                     "DATA_VALUE": str(100 + i + i * i / 100)})
    return rows


@pytest.fixture
def providers(monkeypatch):
    receipts, calls = {}, []
    clock = local()
    lock = Lock()

    def returned(name):
        with lock:
            clock.value = (BASE + timedelta(seconds=len(calls) + 1)).isoformat()
            calls.append(name)
            receipts[name] = clock.value

    def fred(series_id, limit):
        returned(series_id)
        return [((date(2026, 10, 16) - timedelta(days=i)).isoformat(), 100.0 - i)
                for i in range(limit)]

    def ecos(key, stat, cycle, start, end, item, first, last):
        returned(stat)
        if stat == E.KR_CPI_STAT:
            return cpi_rows()
        if stat == "722Y001":
            return [{"TIME": "202609", "DATA_VALUE": "2.5", "UNIT_NAME": "%"}]
        assert stat == "817Y002"
        return [{"TIME": "20261016", "DATA_VALUE": "3.15"}]

    def cape():
        returned("CAPE")
        return {"value": 38.2, "as_of": "2026-10-18T11:59:59+09:00",
                "source": "multpl.com (Shiller PE)"}

    monkeypatch.setattr(F, "_fetch_series", fred)
    monkeypatch.setattr(E, "_ecos_get", ecos)
    monkeypatch.setattr(C, "fetch_cape", cape)
    monkeypatch.setattr(F, "now_iso", lambda: clock.value)
    monkeypatch.setattr(E, "now_iso", lambda: clock.value)
    return receipts, calls


def test_fred_per_series_receipts_and_derivations(providers, monkeypatch):
    receipts, calls = providers
    fetch = F._fetch_series
    limits = []

    def tracked(series_id, limit):
        limits.append(limit)
        return fetch(series_id, limit)

    monkeypatch.setattr(F, "_fetch_series", tracked)
    block = F.get_fred_macro_block()
    assert sorted(calls) == sorted([*SERIES, "CAPE"])
    assert sorted(limits) == sorted(LIMITS)
    for series, key in SERIES.items():
        row = block[key]
        assert row["fetched_at"] == row["last_successful_at"] == receipts[series]
        assert row["source_as_of"] == row["date"] == "2026-10-16"
        assert row["source"] == "fred"
        assert row["stale"] is False and row["reused"] is False
    assert copy_meta(block["cpi_yoy"]) == copy_meta(block["core_cpi"])
    assert copy_meta(block["gdp_growth"]) == copy_meta(block["us_recession_smoothed_prob"])
    assert block["cpi_yoy"]["value"] == round((100 / 88 - 1) * 100, 2)
    assert block["gdp_growth"]["value"] == -5.5
    cape = block["cape"]
    assert cape["as_of"] == "2026-10-18T11:59:59+09:00"
    assert cape["fetched_at"] == cape["last_successful_at"] == receipts["CAPE"]
    assert cape["source_as_of"] is None
    assert cape["source_date_status"] == "missing" and cape["stale"] is True


@pytest.mark.parametrize("source_date", ["", "not-a-date", "2026-02-30", "2026-10-19"])
def test_fred_invalid_dates_do_not_erase_success_clock(monkeypatch, source_date):
    monkeypatch.setattr(F, "_fetch_series", lambda series, limit:
                        [(source_date, 3.0)] if series == "DGS10" else [])
    monkeypatch.setattr(C, "fetch_cape", lambda: None)
    monkeypatch.setattr(F, "now_iso", lambda: BASE.isoformat())
    block = F.get_fred_macro_block()
    assert set(block) == {"available", "dgs10"}
    row = block["dgs10"]
    assert row["date"] == source_date
    assert row["source_as_of"] is None and row["stale"] is True
    assert row["last_successful_at"] == BASE.isoformat()


def test_fred_empty_and_no_key_do_not_invent_success(monkeypatch):
    monkeypatch.setattr(F, "_fetch_series", lambda *args: [])
    monkeypatch.setattr(C, "fetch_cape", lambda: None)
    monkeypatch.setattr(F, "now_iso", lambda: pytest.fail("No successful fetch"))
    assert F.get_fred_macro_block() == {"available": False}
    monkeypatch.setattr(F, "FRED_API_KEY", "")
    assert F.get_fred_macro_block() == {"available": False, "error": "no_api_key"}


def test_fred_partial_insufficient_history_omits_uncomputed_indicators(monkeypatch):
    monkeypatch.setattr(F, "_fetch_series", lambda series, limit:
                        [("2026-10-16", 3.0)]
                        if series in {"DGS10", "CPILFESL", "M2SL"} else [])
    monkeypatch.setattr(C, "fetch_cape", lambda: None)
    monkeypatch.setattr(F, "now_iso", lambda: BASE.isoformat())
    block = F.get_fred_macro_block()
    assert set(block) == {"available", "dgs10"}
    assert block["dgs10"]["last_successful_at"] == BASE.isoformat()


@pytest.mark.parametrize("mode", ["ok", "http", "timeout", "empty"])
def test_fetch_series_retains_list_contract(monkeypatch, mode):
    calls = []

    def get(url, **kwargs):
        calls.append(kwargs)
        if mode == "timeout":
            raise requests.exceptions.Timeout()
        return SimpleNamespace(status_code=503 if mode == "http" else 200, text="",
                               json=lambda: {"observations": [] if mode == "empty" else
                                             [{"date": "2026-10-16", "value": "3.5"}]})

    monkeypatch.setattr(F.requests, "get", get)
    result = F._fetch_series("DGS10", 260)
    assert type(result) is list
    assert result == ([("2026-10-16", 3.5)] if mode == "ok" else [])
    assert len(calls) == 1 and calls[0]["timeout"] == 20


def test_ecos_receipts_month_precision_and_merge(providers):
    receipts, calls = providers
    block = E.get_ecos_macro_block()
    assert calls == ["722Y001", E.KR_CPI_STAT, "817Y002"]
    for key, stat in [("korea_policy_rate", "722Y001"),
                      ("korea_cpi_axis", E.KR_CPI_STAT), ("korea_gov_10y", "817Y002")]:
        row = block[key]
        assert row["fetched_at"] == row["last_successful_at"] == receipts[stat]
        assert row["source"] == "ecos" and row["reused"] is False
        assert row["stale"] is False
        if key != "korea_gov_10y":
            assert row["date"] == "202609"
            assert row["source_as_of"] == "2026-09"
            assert row["source_period_kind"] == "month"
        else:
            assert row["date"] == row["source_as_of"] == "2026-10-16"
    fred = {"available": False}
    E.merge_ecos_into_fred(fred, block)
    for key in block.keys() - {"available"}:
        assert copy_meta(fred[key]) == copy_meta(block[key])


@pytest.mark.parametrize("source_date", [None, "202613", "bad"])
def test_ecos_policy_unknown_date_has_receipt_only(monkeypatch, source_date):
    monkeypatch.setattr(E, "_ecos_get", lambda key, stat, *args:
                        [{"TIME": source_date, "DATA_VALUE": "2.5"}]
                        if stat == "722Y001" else [])
    monkeypatch.setattr(E, "now_iso", lambda: BASE.isoformat())
    block = E.get_ecos_macro_block()
    assert set(block) == {"available", "korea_policy_rate"}
    row = block["korea_policy_rate"]
    assert row["source_as_of"] is None and row["stale"] is True
    assert row["last_successful_at"] == BASE.isoformat()


def test_ecos_empty_has_no_row_count_retry_or_success_clock(monkeypatch):
    calls = []

    def empty(*args):
        calls.append((args[1], args[-1]))
        return []

    monkeypatch.setattr(E, "_ecos_get", empty)
    monkeypatch.setattr(E, "now_iso", lambda: pytest.fail("No successful fetch"))
    assert E.get_ecos_macro_block() == {"available": False}
    assert calls == [("722Y001", 24), (E.KR_CPI_STAT, 100), ("817Y002", 320)]


def test_ecos_successful_retry_uses_its_own_receipt(monkeypatch):
    clock = {"value": BASE.isoformat()}
    calls = []
    expected = {}

    counts = {}
    def get(url, **kwargs):
        stat = url.split("/")[-5]
        calls.append((stat, url))
        clock["value"] = (BASE + timedelta(seconds=len(calls))).isoformat()
        counts[stat] = counts.get(stat, 0) + 1
        if stat == E.KR_CPI_STAT:
            return SimpleNamespace(status_code=200, json=lambda: {"StatisticSearch": {"row": []}})
        if counts[stat] == 1:
            return SimpleNamespace(status_code=503)
        expected[stat] = clock["value"]
        return SimpleNamespace(status_code=200, json=lambda: {"StatisticSearch": {"row": [
            {"TIME": "202609" if stat == "722Y001" else "20261016", "DATA_VALUE": "3.0"}]}})

    monkeypatch.setattr(E.requests, "get", get)
    monkeypatch.setattr(E, "now_iso", lambda: clock["value"])
    block = E.get_ecos_macro_block()
    assert len(calls) == 5 and "korea_cpi_axis" not in block
    assert block["korea_policy_rate"]["last_successful_at"] == expected["722Y001"]
    assert block["korea_gov_10y"]["last_successful_at"] == expected["817Y002"]
    assert expected["722Y001"] != expected["817Y002"]
    assert calls[0][1] == calls[1][1] and calls[3][1] == calls[4][1]


def test_macro_integration_all_25_clock_paths(providers, monkeypatch):
    from api.collectors import macro_data as M
    from api.quant import cross_asset_corr as corr

    def quote(*args, **kwargs):
        return {"value": 100.0, "change_pct": 0.0}

    for name in ("_get_usd_krw", "_get_fx", "_get_commodity", "_get_index_change",
                 "_get_index_change_fred"):
        monkeypatch.setattr(M, name, quote)
    monkeypatch.setattr(M, "_get_commodity_bundle", lambda: {})
    monkeypatch.setattr(M, "_get_micro_signals", lambda: [])
    monkeypatch.setattr(corr, "compute_cross_asset_corr", lambda: {"available": False})
    result = M.get_macro_indicators()
    receipts, calls = providers
    native_keys = {*SERIES.values(), "cape", "cpi_yoy", "gdp_growth",
                   "korea_policy_rate", "korea_cpi_axis"}
    assert result["fred"].keys() - {"available"} == native_keys
    paths = {f"fred.{key}": result["fred"][key] for key in native_keys}
    paths.update({f"ecos.{key}": row for key, row in result["ecos"].items()
                  if key != "available"})
    for key in ("hy_spread", "breakeven_inflation_10y", "fed_balance_sheet", "yield_spread"):
        paths[key] = result[key]
    assert len(paths) == 25
    for path, row in paths.items():
        assert row["fetched_at"] == row["last_successful_at"], path
        assert row["fetched_at"] in receipts.values(), path
        assert row["reused"] is False, path
        assert row["stale"] is (path == "fred.cape"), path
    for series, key in SERIES.items():
        source = "817Y002" if key == "korea_gov_10y" else series
        assert result["fred"][key]["fetched_at"] == receipts[source]
    for key in ("hy_spread", "breakeven_inflation_10y", "fed_balance_sheet"):
        assert copy_meta(result[key]) == copy_meta(result["fred"][key])
    for top, native in (("us_10y", "dgs10"), ("us_2y", "dgs2")):
        assert result[top]["fetched_at"] == result["fred"][native]["fetched_at"]
    assert result["yield_spread"]["fetched_at"] == min(receipts["DGS10"], receipts["DGS2"])
    assert result["yield_spread"]["source_as_of"] == "2026-10-16"
    assert len(calls) == 17  # 13 FRED, CAPE, 3 ECOS; no extra source requests.


def test_fred_two_worker_bound_and_completion_clocks(monkeypatch, capsys):
    barrier = Barrier(2)
    lock = Lock()
    clock = local()
    active = 0
    peak = 0
    calls, completed = [], {}

    def fetch(series_id, limit):
        nonlocal active, peak
        with lock:
            index = len(calls)
            calls.append((series_id, limit))
            active += 1
            peak = max(peak, active)
        if index < 12:
            barrier.wait(timeout=3)
        with lock:
            clock.value = (BASE + timedelta(seconds=len(completed) + 1)).isoformat()
            completed[series_id] = clock.value
            active -= 1
        return [("2026-10-16", 3.0)] * limit

    monkeypatch.setattr(F, "_fetch_series", fetch)
    monkeypatch.setattr(F, "now_iso", lambda: clock.value)
    monkeypatch.setattr(C, "fetch_cape", lambda: None)
    block = F.get_fred_macro_block()
    assert peak == 2 and active == 0
    assert sorted(calls) == sorted(zip(SERIES, LIMITS))
    for series, key in SERIES.items():
        assert block[key]["fetched_at"] == completed[series]
    stderr = capsys.readouterr().err
    for series in SERIES:
        assert f"source=fred:{series} phase=end" in stderr
    assert stderr.count("elapsed_ms=") == 13


def test_fred_deadline_context_reaches_workers_and_stops_queued_http(monkeypatch):
    barrier = Barrier(2)
    clock = {"mono": 0.0}
    calls = []
    monkeypatch.setattr(runtime.time, "monotonic", lambda: clock["mono"])
    monkeypatch.setattr(F, "now_iso", lambda: BASE.isoformat())
    monkeypatch.setattr(C, "fetch_cape", lambda: pytest.fail("CAPE after budget"))

    def get(url, **kwargs):
        calls.append((kwargs["params"]["series_id"], kwargs["timeout"]))
        barrier.wait(timeout=3)
        clock["mono"] = 2.0
        return SimpleNamespace(status_code=200, json=lambda: {
            "observations": [{"date": "2026-10-16", "value": "3.0"}]})

    monkeypatch.setattr(F.requests, "get", get)
    with runtime.collection_budget(1):
        block = F.get_fred_macro_block()
    assert len(calls) == 2
    assert all(timeout == 1 for _, timeout in calls)
    assert set(block) == {"available", "vix_close", "dgs10"}


def test_expired_budget_prevents_direct_fred_and_ecos_http(monkeypatch):
    calls = []
    monkeypatch.setattr(requests, "get", lambda *a, **k: calls.append("HTTP"))
    with runtime.collection_budget(0):
        assert F._fetch_series("DGS10", 260) == []
        assert E.get_ecos_macro_block() == {"available": False}
    assert calls == []


def test_ecos_remaining_budget_blocks_fallback_and_later_sources(monkeypatch, capsys):
    clock = {"mono": 0.0}
    timeouts = []
    monkeypatch.setattr(runtime.time, "monotonic", lambda: clock["mono"])

    def get(url, **kwargs):
        timeouts.append(kwargs["timeout"])
        clock["mono"] = 3.0
        raise requests.exceptions.Timeout("private-key-url-must-not-appear")

    monkeypatch.setattr(E.requests, "get", get)
    with runtime.collection_budget(2):
        assert E.get_ecos_macro_block() == {"available": False}
    assert len(timeouts) == 1 and sum(timeouts[0]) == pytest.approx(2)
    stderr = capsys.readouterr().err
    assert "private-key-url" not in stderr
    assert "Timeout" in stderr and "CollectionDeadline" in stderr


@pytest.mark.parametrize("mode", ["http", "exception", "worker"])
def test_fred_error_logs_exclude_response_bodies_and_exception_messages(monkeypatch, capsys, mode):
    reasons = []
    secret = "private-key-url-must-not-appear"
    monkeypatch.setattr(F, "_log_fred_health", lambda *a, **k: reasons.append(a))

    def fail(*args, **kwargs):
        raise ValueError(secret)

    if mode == "worker":
        monkeypatch.setattr(F, "_fetch_series", fail)
        monkeypatch.setattr(C, "fetch_cape", lambda: None)
        assert F.get_fred_macro_block() == {"available": False}
    else:
        monkeypatch.setattr(F.requests, "get", fail if mode == "exception" else
                            lambda *a, **k: SimpleNamespace(status_code=403, text=secret))
        assert F._fetch_series("DGS10", 260) == []
    assert secret not in repr(reasons) + capsys.readouterr().err
