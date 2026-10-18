"""Offline ECOS transport budgets, partial collection and native receipts."""
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
import requests

from api.collectors import ecos_macro as ecos
from api.utils import macro_runtime as runtime


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    attempts = []

    def blocked(*args, **kwargs):
        attempts.append(True)
        raise AssertionError("Network forbidden")

    monkeypatch.setattr(requests.sessions.Session, "request", blocked)
    monkeypatch.setattr("socket.socket.connect", blocked)
    monkeypatch.setattr(ecos, "ECOS_API_KEY", "offline-key")
    monkeypatch.setattr(ecos, "now_kst", lambda: datetime.fromisoformat("2026-10-18T12:00:00+09:00"))
    yield
    assert not attempts, "Even swallowed network attempts are failures"


def response(payload=None, status=200):
    return SimpleNamespace(status_code=status, json=lambda: payload)


def fetch():
    return ecos._ecos_get("offline-key", "722Y001", "M", "202410", "202610", "0101000", 1, 24)


def test_transient_timeout_spends_only_ecos_budget_and_restores_parent(monkeypatch, capsys):
    clock, calls = [100.0], []
    monkeypatch.setattr(runtime.time, "monotonic", lambda: clock[0])

    def get(url, **kwargs):
        calls.append((url.split("/")[-5], kwargs))
        clock[0] += sum(kwargs["timeout"])
        raise requests.exceptions.ConnectTimeout("https://private.invalid/offline-key")

    monkeypatch.setattr(ecos.requests, "get", get)
    with runtime.collection_budget(58):
        assert ecos.get_ecos_macro_block() == {"available": False}
        assert runtime.request_timeout(58) == pytest.approx(40)
    assert clock[0] == pytest.approx(118)
    assert len(calls) == 6
    assert [stat for stat, _ in calls] == ["722Y001", "722Y001", "901Y009", "901Y009", "817Y002", "817Y002"]
    assert all(0 < c["timeout"][0] <= 2 and 0 < c["timeout"][1] <= 3 for _, c in calls)
    assert all(c["allow_redirects"] is False for _, c in calls)
    assert runtime.request_timeout(100) == 100
    log = capsys.readouterr().err
    for label in ("policy_rate", "cpi", "gov_10y"):
        assert f"source=ecos:{label}" in log
    assert "ConnectTimeout" in log and "elapsed_ms=" in log
    assert "offline-key" not in log and "https://" not in log


@pytest.mark.parametrize("budget", [0, 0.5, 2])
def test_parent_deadline_wins_and_no_request_starts_after_expiry(monkeypatch, budget):
    clock, calls = [0.0], []
    monkeypatch.setattr(runtime.time, "monotonic", lambda: clock[0])

    def get(url, **kwargs):
        calls.append(kwargs["timeout"])
        clock[0] += sum(kwargs["timeout"])
        raise requests.exceptions.ReadTimeout("private")

    monkeypatch.setattr(ecos.requests, "get", get)
    with runtime.collection_budget(budget):
        assert ecos.get_ecos_macro_block() == {"available": False}
    assert len(calls) == (1 if budget else 0)
    if calls:
        assert sum(calls[0]) == pytest.approx(budget)


@pytest.mark.parametrize("failure", [requests.exceptions.ConnectTimeout,
                                    requests.exceptions.ReadTimeout,
                                    requests.exceptions.ConnectionError, 408, 429, 500, 502, 503, 504])
def test_transient_retry_is_once_and_success_keeps_list_contract(monkeypatch, failure):
    calls, closed = [], []
    row = {"TIME": "202609", "DATA_VALUE": "2.5"}

    def get(url, **kwargs):
        calls.append((url, kwargs))
        if len(calls) == 1:
            if isinstance(failure, type):
                raise failure("private")
            first = response(status=failure)
            first.close = lambda: closed.append(True)
            return first
        return response({"StatisticSearch": {"row": row}})

    monkeypatch.setattr(ecos.requests, "get", get)
    assert fetch() == [row]
    assert len(calls) == 2 and calls[0][0] == calls[1][0]
    assert calls[0][0].startswith(ecos.ECOS_BASE + "/")
    assert closed == ([] if isinstance(failure, type) else [True])


def test_fast_transient_failure_still_has_only_two_attempts(monkeypatch):
    calls = []

    def get(url, **kwargs):
        calls.append(url)
        return response(status=503)

    monkeypatch.setattr(ecos.requests, "get", get)
    assert fetch() == []
    assert len(calls) == 2


@pytest.mark.parametrize("mode", ["empty", "result", "malformed", "json", "ssl", "error", 301, 400, 401, 403, 404])
def test_permanent_or_empty_response_has_no_retry_or_success_clock(monkeypatch, capsys, mode):
    calls = []

    def get(url, **kwargs):
        calls.append(url)
        if mode == "ssl":
            raise requests.exceptions.SSLError("offline-key")
        if mode == "error":
            raise ValueError("offline-key")
        if mode == "json":
            return SimpleNamespace(status_code=200, json=lambda: (_ for _ in ()).throw(ValueError("offline-key")))
        payload = {"empty": {"StatisticSearch": {"row": []}},
                   "result": {"RESULT": {"CODE": "ERROR-100", "MESSAGE": "offline-key"}},
                   "malformed": ["offline-key"]}.get(mode)
        return response(payload, mode if isinstance(mode, int) else 200)

    monkeypatch.setattr(ecos.requests, "get", get)
    monkeypatch.setattr(ecos, "now_iso", lambda: pytest.fail("No successful receipt"))
    assert fetch() == []
    assert len(calls) == 1
    assert "offline-key" not in capsys.readouterr().err


def test_no_row_count_fallback_and_each_source_survives_another_failure(monkeypatch):
    stats = []

    def get(url, **kwargs):
        stat = url.split("/")[-5]
        stats.append(stat)
        if stat == "722Y001":
            return response(status=403)
        if stat == "901Y009":
            return response({"RESULT": {"CODE": "INFO-200"}})
        return response({"StatisticSearch": {"row": [{"TIME": "20261016", "DATA_VALUE": "3.15"}]}})

    monkeypatch.setattr(ecos.requests, "get", get)
    block = ecos.get_ecos_macro_block()
    assert stats == ["722Y001", "901Y009", "817Y002"]
    assert set(block) == {"available", "korea_gov_10y"}
    assert block["available"] is True


def test_three_series_windows_calculations_and_individual_return_clocks(monkeypatch):
    calls, receipts = [], {}
    clock = [datetime.fromisoformat("2026-10-18T12:00:00+09:00")]
    cpi = [{"TIME": f"{(2024 * 12 + 8 + i) // 12}{(2024 * 12 + 8 + i) % 12 + 1:02}",
            "DATA_VALUE": str(100 + i + i * i / 100)} for i in range(25)]
    yields = [{"TIME": "20261015", "DATA_VALUE": "2.0"} for _ in range(260)]
    yields[-1] = {"TIME": "20261016", "DATA_VALUE": "3.15"}

    def get(url, **kwargs):
        parts = url.split("/")
        stat = parts[-5]
        calls.append(parts[-7:])
        clock[0] += timedelta(seconds=1)
        receipts[stat] = clock[0].isoformat()
        rows = {"722Y001": [{"TIME": "202609", "DATA_VALUE": "2.5"}],
                "901Y009": cpi, "817Y002": yields}[stat]
        return response({"StatisticSearch": {"row": rows}})

    monkeypatch.setattr(ecos.requests, "get", get)
    monkeypatch.setattr(ecos, "now_iso", lambda: clock[0].isoformat())
    block = ecos.get_ecos_macro_block()
    assert calls == [["1", "24", "722Y001", "M", "202410", "202610", "0101000"],
                     ["1", "100", "901Y009", "M", "202403", "202610", "0"],
                     ["1", "320", "817Y002", "D", "20250913", "20261018", "010210000"]]
    for key, stat in [("korea_policy_rate", "722Y001"), ("korea_cpi_axis", "901Y009"), ("korea_gov_10y", "817Y002")]:
        assert block[key]["fetched_at"] == block[key]["last_successful_at"] == receipts[stat]
    assert block["korea_policy_rate"]["source_as_of"] == "2026-09"
    assert block["korea_cpi_axis"]["date"] == "202609"
    assert block["korea_cpi_axis"]["window_months"] == 12
    yoy = [(float(cpi[i]["DATA_VALUE"]) / float(cpi[i - 12]["DATA_VALUE"]) - 1) * 100
           for i in range(12, 25)]
    from statistics import mean, stdev
    expected_z = (yoy[-1] - mean(yoy[:-1])) / stdev(yoy[:-1])
    assert block["korea_cpi_axis"]["yoy_pct"] == round(yoy[-1], 3)
    assert block["korea_cpi_axis"]["z"] == round(expected_z, 3)
    assert block["korea_cpi_axis"]["inflation_up"] is (expected_z > 0)
    assert block["korea_gov_10y"]["source_as_of"] == "2026-10-16"
    assert block["korea_gov_10y"]["yoy_pp"] == 1.15


@pytest.mark.parametrize("value", [None, "", ".", "NaN", "inf", "-inf"])
def test_missing_or_nonfinite_values_never_become_zero(monkeypatch, value):
    def get(url, **kwargs):
        return response({"StatisticSearch": {"row": [{"TIME": "202609", "DATA_VALUE": value}]}})

    monkeypatch.setattr(ecos.requests, "get", get)
    assert ecos.get_ecos_macro_block() == {"available": False}


def test_real_zero_is_preserved_and_missing_reference_omits_yoy(monkeypatch):
    def rows(key, stat, *args):
        if stat == "901Y009":
            return []
        if stat == "722Y001":
            return [{"TIME": "202609", "DATA_VALUE": "0"}]
        return [{"TIME": "20261015"}] * 259 + [{"TIME": "20261016", "DATA_VALUE": "3.15"}]

    monkeypatch.setattr(ecos, "_ecos_get", rows)
    block = ecos.get_ecos_macro_block()
    assert block["korea_policy_rate"]["value"] == 0
    assert block["korea_gov_10y"]["yoy_pp"] is None


def test_late_response_is_discarded_and_closed(monkeypatch):
    clock, closed = [0.0], []
    monkeypatch.setattr(runtime.time, "monotonic", lambda: clock[0])

    def get(url, **kwargs):
        clock[0] = 7
        result = response({"StatisticSearch": {"row": {"TIME": "202609", "DATA_VALUE": "2.5"}}})
        result.close = lambda: closed.append(True)
        return result

    monkeypatch.setattr(ecos.requests, "get", get)
    assert fetch() == []
    assert closed == [True]


def test_cleanup_failure_does_not_erase_success_or_block_later_series(monkeypatch):
    calls = []

    def fail_close():
        raise OSError("offline-key")

    def get(url, **kwargs):
        calls.append(url)
        result = response({"StatisticSearch": {"row": {"TIME": "202609", "DATA_VALUE": "2.5"}}})
        result.close = fail_close
        return result

    monkeypatch.setattr(ecos.requests, "get", get)
    block = ecos.get_ecos_macro_block()
    assert len(calls) == 3 and block["available"] is True


def test_no_key_starts_no_requests(monkeypatch):
    monkeypatch.setattr(ecos, "ECOS_API_KEY", "")
    monkeypatch.setattr(ecos.requests, "get", lambda *a, **k: pytest.fail("No key"))
    assert ecos.get_ecos_macro_block() == {"available": False}
