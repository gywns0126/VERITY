"""Offline budget, partial-result and receipt contracts for bond collection."""
import builtins
from collections import Counter
from threading import Event, Lock
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest
import requests

from api.collectors import bonddata, bondus, yieldcurve
from api.utils import macro_runtime as runtime


class Response:
    def __init__(self, body=None, status=200):
        self.body = body or {}
        self.status_code = status

    def json(self):
        return self.body


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    """No real provider calls or sleeps, including an accidental request path."""
    clock = [0.0]
    unexpected = []

    def forbidden(*args, **kwargs):
        unexpected.append(True)
        raise AssertionError("real HTTP disabled")

    monkeypatch.setattr(requests.sessions.Session, "request", forbidden)
    monkeypatch.setattr(runtime.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(bondus.time, "sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds))
    stamp = "2026-10-18T12:00:00+09:00"
    now = datetime(2026, 10, 18, 12, tzinfo=timezone(timedelta(hours=9)))
    monkeypatch.setattr(bonddata, "now_kst", lambda: now)
    monkeypatch.setattr(yieldcurve, "now_kst", lambda: now)
    monkeypatch.setattr(bonddata, "now_iso", lambda: stamp)
    monkeypatch.setattr(bondus, "now_iso", lambda: stamp)
    monkeypatch.setattr(bonddata, "ECOS_API_KEY", "fixture-ecos-secret")
    monkeypatch.setattr(bondus, "FRED_API_KEY", "fixture-fred-secret")
    monkeypatch.delenv("KRX_ID", raising=False)
    monkeypatch.delenv("KRX_PW", raising=False)
    yield clock
    assert not unexpected, "an unmocked provider call was attempted"


def ecos_response(value="3.5", day="20261016"):
    return Response({"StatisticSearch": {"row": [{"TIME": day, "DATA_VALUE": value}]}})


def fred_response(value="4.0", day="2026-10-16"):
    return Response({"observations": [{"value": value, "date": day}]})


@pytest.mark.parametrize("credentials", [{}, {"KRX_ID": "user"}, {"KRX_PW": "pw"},
                                         {"KRX_ID": " ", "KRX_PW": "pw"}])
def test_krx_gate_precedes_import_and_network(monkeypatch, credentials, capsys):
    for key, value in credentials.items():
        monkeypatch.setenv(key, value)
    original = builtins.__import__
    imported = []

    def guarded(name, *args, **kwargs):
        if name.startswith("pykrx"):
            imported.append(name)
            raise AssertionError("credential gate did not run")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    assert bonddata._pykrx_bond_yields() == {}
    assert imported == []
    assert "skipped_no_credentials" in capsys.readouterr().err


def test_authenticated_krx_cannot_start_an_unbounded_transport(monkeypatch, capsys):
    monkeypatch.setenv("KRX_ID", "fixture-user")
    monkeypatch.setenv("KRX_PW", "fixture-password")
    assert bonddata._pykrx_bond_yields() == {}
    log = capsys.readouterr().err
    assert "skipped_unbounded_transport" in log
    assert "fixture-user" not in log and "fixture-password" not in log


def test_ecos_keeps_the_nine_existing_series_and_native_receipts(monkeypatch):
    requested = []

    def get(url, **kwargs):
        assert 0 < sum(kwargs["timeout"]) <= runtime.request_timeout(25)
        assert kwargs["allow_redirects"] is False
        requested.append(url.rsplit("/", 1)[-1])
        return ecos_response()

    monkeypatch.setattr(requests, "get", get)
    out = bonddata.get_bond_market_summary()
    assert requested == ["010190000", "010195000", "010200000", "010200001", "010210000",
                         "010220000", "010230000", "010300000", "010320000"]
    assert out["available"] is True and out["partial"] is False
    for point in out["curve"] + list(out["kr_corp_spreads"]["grades"].values()):
        assert point["as_of"] == "20261016"
        assert point["source_as_of"] == "2026-10-16"
        assert point["fetched_at"] == point["last_successful_at"] == "2026-10-18T12:00:00+09:00"
    assert out["curve_as_of"] == out["kr_corp_spreads"]["date"] == "20261016"
    assert out["kr_corp_spreads"]["grades"]["AA-"]["spread_vs_3y"] == 0


def test_kr_budget_keeps_completed_tenors_and_stops_new_requests(monkeypatch, offline, capsys):
    calls = []

    def get(url, **kwargs):
        remaining = runtime.request_timeout(25)
        assert sum(kwargs["timeout"]) <= remaining + 1e-9
        calls.append(kwargs["timeout"])
        if len(calls) == 1:
            offline[0] += 1
            return ecos_response()
        offline[0] += sum(kwargs["timeout"])
        raise requests.Timeout("https://fixture.invalid/fixture-ecos-secret")

    monkeypatch.setattr(requests, "get", get)
    out = bonddata.get_bond_market_summary()
    assert offline[0] == pytest.approx(25)
    assert len(calls) == 5
    assert out["available"] and out["partial"] and out["stale"]
    assert [p["tenor"] for p in out["curve"]] == ["1Y"]
    log = capsys.readouterr().err
    assert "elapsed_ms=" in log
    assert "https://" not in log and "fixture-ecos-secret" not in log


@pytest.mark.parametrize("provider", ["kr", "us"])
def test_parent_deadline_stops_even_the_first_request(monkeypatch, provider):
    called = []
    monkeypatch.setattr(requests, "get", lambda *a, **kw: called.append(kw))
    with runtime.collection_budget(0):
        out = (bonddata.get_bond_market_summary() if provider == "kr"
               else bondus.get_us_bond_summary())
    assert out["available"] is False and out["stale"] is True
    assert called == []


@pytest.mark.parametrize("day,value", [("20991018", "3"), ("", "3"),
                                       ("20261016", "NaN"), ("20261301", "3")])
def test_ecos_rejects_invalid_future_and_nonfinite_points(monkeypatch, day, value):
    monkeypatch.setattr(requests, "get", lambda *a, **kw: ecos_response(value, day))
    assert bonddata._ecos_fetch_point("817Y002", "010200000") is None


def test_ecos_truncated_response_stays_missing(monkeypatch):
    body = {"StatisticSearch": {"row": [{"TIME": "20261016", "DATA_VALUE": "3"}] * 80}}
    monkeypatch.setattr(requests, "get", lambda *a, **kw: Response(body))
    assert bonddata._ecos_fetch_point("817Y002", "010200000") is None


def test_ecos_selects_latest_valid_row_and_keeps_tuple_contract(monkeypatch):
    rows = [{"TIME": "20261015", "DATA_VALUE": "3.1"},
            {"TIME": "20990101", "DATA_VALUE": "9.9"},
            {"TIME": "20261016", "DATA_VALUE": "3.2"}]
    monkeypatch.setattr(requests, "get", lambda *a, **kw: Response({"StatisticSearch": {"row": rows}}))
    assert bonddata._ecos_fetch_point("817Y002", "010200000") == (3.2, "20261016")


def test_fred_complete_curve_and_credit_keep_individual_receipts(monkeypatch):
    requested = []

    def get(url, **kwargs):
        assert sum(kwargs["timeout"]) <= runtime.request_timeout(25)
        requested.append(kwargs["params"]["series_id"])
        return fred_response()

    monkeypatch.setattr(requests, "get", get)
    out = bondus.get_us_bond_summary()
    assert Counter(requested) == Counter(
        [series for _, series in bondus._TREASURY_SERIES] + list(bondus._CREDIT_SERIES.values()))
    assert out["available"] and not out["partial"] and not out["stale"]
    assert len(out["curve"]) == 11
    assert out["spread_2y_10y"] == out["spread_3m_10y"] == 0
    assert out["credit_spreads"]["us_hy_risk"] == "MODERATE"
    for point in out["curve"] + list(out["credit_spreads_meta"].values()):
        assert point["as_of"] == "2026-10-16"
        assert point["fetched_at"] == point["last_successful_at"] == "2026-10-18T12:00:00+09:00"


def test_fred_shared_budget_includes_retries_and_backoff(monkeypatch, offline, capsys):
    calls, sleeps = [], []

    def sleep(seconds):
        assert seconds <= runtime.request_timeout(25)
        sleeps.append(seconds)
        offline[0] += seconds

    def get(url, **kwargs):
        assert sum(kwargs["timeout"]) <= runtime.request_timeout(25) + 1e-9
        calls.append(kwargs["params"]["series_id"])
        offline[0] += sum(kwargs["timeout"])
        raise requests.Timeout("https://fixture.invalid?api_key=fixture-fred-secret")

    monkeypatch.setattr(requests, "get", get)
    monkeypatch.setattr(bondus.time, "sleep", sleep)
    with runtime.collection_budget(25):
        assert bondus._fetch_latest_point("DGS10", retries=99) is None
    assert offline[0] == pytest.approx(25)
    assert len(calls) == 4 and sleeps == pytest.approx([0.6, 1.2, 1.8])
    log = capsys.readouterr().err
    assert "https://" not in log and "fixture-fred-secret" not in log


@pytest.mark.parametrize("status,expected_calls", [(400, 1), (429, 3), (503, 3)])
def test_fred_retries_only_transient_http_errors(monkeypatch, status, expected_calls):
    calls = []

    def get(*args, **kwargs):
        calls.append(True)
        return Response(status=status)

    monkeypatch.setattr(requests, "get", get)
    assert bondus._fetch_latest("DGS10") is None
    assert len(calls) == expected_calls


def test_fred_public_float_and_unknown_observation_contract(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **kw: fred_response(day=None))
    assert bondus._fetch_latest("DGS10") == 4.0
    point = bondus._fetch_latest_point("DGS10")
    assert "as_of" not in point and point["source_as_of"] is None and point["stale"]


def test_fred_ignores_future_and_nonfinite_rows(monkeypatch):
    body = {"observations": [{"date": "2099-01-01", "value": "7"},
                             {"date": "2026-10-17", "value": "NaN"},
                             {"date": "2026-10-16", "value": "4.1"}]}
    monkeypatch.setattr(requests, "get", lambda *a, **kw: Response(body))
    point = bondus._fetch_latest_point("DGS10")
    assert point["value"] == 4.1 and point["as_of"] == "2026-10-16"


def test_us_missing_credentials_starts_no_request(monkeypatch):
    monkeypatch.setattr(bondus, "FRED_API_KEY", "")
    assert bondus.get_us_bond_summary()["available"] is False


@pytest.mark.parametrize("failed_market", ["kr", "us"])
def test_country_failure_preserves_other_current_data(monkeypatch, failed_market, capsys):
    def fail():
        raise RuntimeError("https://fixture.invalid/DO_NOT_LOG")

    for market, module, function in [("kr", bonddata, "get_bond_market_summary"),
                                     ("us", bondus, "get_us_bond_summary")]:
        monkeypatch.setattr(module, function, fail if market == failed_market else
                            lambda: {"curve": [{"tenor": "10Y", "yield": 4,
                                                "as_of": "2026-10-16"}]})
    out = yieldcurve.get_full_yield_curve_data()
    good = "us" if failed_market == "kr" else "kr"
    assert out["available"] and out["stale"] and out["partial"]
    assert out["availability"][failed_market]["available"] is False
    assert out["yield_curves"][good]["curve"][0]["yield"] == 4
    assert "DO_NOT_LOG" not in capsys.readouterr().err


def test_both_country_budgets_fit_outer_and_keep_us_success(monkeypatch, offline):
    calls = []

    def get(url, **kwargs):
        calls.append(url.startswith("https://ecos.bok.or.kr/"))
        if calls[-1]:
            offline[0] += sum(kwargs["timeout"])
            raise requests.Timeout("fixture")
        offline[0] += 0.1
        return fred_response()

    monkeypatch.setattr(requests, "get", get)
    with runtime.collection_budget(58):
        out = yieldcurve.get_full_yield_curve_data()
    assert offline[0] == pytest.approx(26.4)
    assert len(out["yield_curves"]["us"]["curve"]) == 11
    assert out["available"] and out["partial"] and out["stale"]


def test_carry_preserves_point_block_and_credit_receipts_without_mutating_previous(monkeypatch):
    receipt = "2026-10-15T12:00:00+09:00"
    point = {"tenor": "3Y", "yield": 3.8, "as_of": "20261014",
             "fetched_at": receipt, "last_successful_at": receipt, "reused": False,
             "source_as_of": "2026-10-14", "source": "ecos", "receipt": {"provider": "fixture"}}
    previous = {
        "yield_curves": {market: {"curve": [deepcopy(point)], "curve_as_of": "20261014",
                                   "fetched_at": receipt, "last_successful_at": receipt}
                         for market in ("kr", "us")},
        "kr_corp_spreads": {"date": "20261014", "collected_at": receipt,
                            "grades": {"AA-": {"yield": 4.5, "as_of": "20261014"}}},
        "credit_spreads": {"us_ig_oas": 1.0},
        "credit_spreads_meta": {"us_ig_oas": {"as_of": "2026-10-14", "fetched_at": receipt}},
    }
    before = deepcopy(previous)
    monkeypatch.setattr(bonddata, "get_bond_market_summary", lambda: {})
    monkeypatch.setattr(bondus, "get_us_bond_summary", lambda: {})
    out = yieldcurve.get_full_yield_curve_data(previous)
    assert out["available"] is False and out["stale"] and out["partial"]
    for block in out["yield_curves"].values():
        carried = block["curve"][0]
        assert carried["as_of"] == "20261014" and carried["stale"] and carried["reused"]
        assert carried["fetched_at"] == carried["last_successful_at"] == receipt
        assert carried["receipt"] == {"provider": "fixture"}
        assert block["fetched_at"] == block["last_successful_at"] == receipt
    assert out["kr_corp_spreads"]["date"] == "20261014"
    assert out["kr_corp_spreads"]["collected_at"] == receipt
    assert out["credit_spreads_meta"]["us_ig_oas"]["fetched_at"] == receipt
    assert previous == before


def test_partial_forward_fill_preserves_fresh_point_and_prior_receipt():
    fresh = {"tenor": "2Y", "yield": 3.5, "as_of": "20261016", "fetched_at": "new"}
    old = {"tenor": "10Y", "yield": 4.0, "as_of": "20261014", "fetched_at": "old"}
    merged, carried = yieldcurve._forward_fill_curve([fresh], [old], ["2Y", "10Y"])
    assert merged[0] == fresh
    assert merged[1]["fetched_at"] == "old" and merged[1]["as_of"] == "20261014"
    assert carried == ["10Y"]


def test_partial_us_credit_carries_each_missing_value_risk_and_original_receipt(monkeypatch):
    old_stamp, new_stamp = "2026-10-15T12:00:00+09:00", "2026-10-18T12:00:00+09:00"
    previous = {
        "credit_spreads": {"us_ig_oas": 1.2, "us_ig_risk": "MODERATE", "us_bbb_oas": 1.5,
                           "us_hy_oas": 6.1, "us_hy_risk": "HIGH"},
        "credit_spreads_meta": {key: {"as_of": "2026-10-14", "fetched_at": old_stamp,
                                      "last_successful_at": old_stamp, "source": "fred"}
                                for key in bondus._CREDIT_SERIES},
    }
    before = deepcopy(previous)
    fresh = {"credit_spreads": {"us_ig_oas": 0.8, "us_ig_risk": "LOW"},
             "credit_spreads_meta": {"us_ig_oas": {"as_of": "2026-10-16", "fetched_at": new_stamp}}}
    monkeypatch.setattr(bonddata, "get_bond_market_summary", lambda: {})
    monkeypatch.setattr(bondus, "get_us_bond_summary", lambda: fresh)
    out = yieldcurve.get_full_yield_curve_data(previous)
    assert out["credit_spreads"] == {**previous["credit_spreads"], **fresh["credit_spreads"]}
    assert out["credit_spreads_meta"]["us_ig_oas"] == fresh["credit_spreads_meta"]["us_ig_oas"]
    for key in ("us_bbb_oas", "us_hy_oas"):
        meta = out["credit_spreads_meta"][key]
        assert meta["fetched_at"] == meta["last_successful_at"] == old_stamp
        assert meta["as_of"] == "2026-10-14" and meta["stale"] and meta["reused"]
    assert out["stale_credit_spreads"] == ["us_bbb_oas", "us_hy_oas"]
    assert out["available"] and out["partial"] and out["stale"]
    assert previous == before


def test_partial_kr_credit_carries_only_failed_grade_and_its_clocks(monkeypatch):
    old_stamp, new_stamp = "2026-10-15T12:00:00+09:00", "2026-10-18T12:00:00+09:00"
    previous = {"kr_corp_spreads": {
        "date": "20261014", "collected_at": old_stamp, "last_successful_at": old_stamp,
        "grades": {"AA-": {"yield": 4.1, "as_of": "20261014"},
                   "BBB-": {"yield": 9.9, "as_of": "20261014", "spread_vs_3y": 6.1,
                            "fetched_at": old_stamp, "last_successful_at": old_stamp}},
    }}
    before = deepcopy(previous)
    fresh_grade = {"yield": 4.0, "as_of": "20261016", "spread_vs_3y": 0.2,
                   "fetched_at": new_stamp, "last_successful_at": new_stamp}
    monkeypatch.setattr(bonddata, "get_bond_market_summary", lambda: {"kr_corp_spreads": {
        "date": "20261016", "collected_at": new_stamp, "grades": {"AA-": fresh_grade}}})
    monkeypatch.setattr(bondus, "get_us_bond_summary", lambda: {})
    out = yieldcurve.get_full_yield_curve_data(previous)
    block = out["kr_corp_spreads"]
    assert block["grades"]["AA-"] == fresh_grade
    assert block["grades"]["BBB-"] == {**previous["kr_corp_spreads"]["grades"]["BBB-"], "stale": True}
    assert block["collected_at"] == block["last_successful_at"] == old_stamp
    assert block["stale"] and block["stale_grades"] == ["BBB-"]
    assert out["available"] and out["partial"] and out["stale"]
    assert previous == before


def test_fresh_credit_value_does_not_inherit_an_old_risk_label(monkeypatch):
    monkeypatch.setattr(bonddata, "get_bond_market_summary", lambda: {})
    monkeypatch.setattr(bondus, "get_us_bond_summary", lambda: {"credit_spreads": {"us_hy_oas": 4.0}})
    out = yieldcurve.get_full_yield_curve_data({"credit_spreads": {"us_hy_oas": 8.0, "us_hy_risk": "EXTREME"}})
    assert out["credit_spreads"] == {"us_hy_oas": 4.0}


def test_complete_current_collection_is_not_permanently_marked_stale(monkeypatch):
    def get(url, **kwargs):
        return ecos_response() if url.startswith("https://ecos.bok.or.kr/") else fred_response()

    monkeypatch.setattr(requests, "get", get)
    out = yieldcurve.get_full_yield_curve_data()
    assert out["available"] and not out["partial"] and not out["stale"]
    assert all(s["available"] and not s["stale"] for s in out["availability"].values())


def test_history_helper_honors_parent_budget_and_keeps_list_contract(monkeypatch):
    timeouts = []

    def get(*args, **kwargs):
        timeouts.append(kwargs["timeout"])
        return fred_response()

    monkeypatch.setattr(requests, "get", get)
    with runtime.collection_budget(0.5):
        assert bondus._fetch_series_points("DGS10") == [("2026-10-16", 4.0)]
    assert 0 < sum(timeouts[0]) <= 0.5
    with runtime.collection_budget(0):
        assert bondus._fetch_series_points("DGS10") == []
    assert len(timeouts) == 1


@pytest.mark.parametrize("previous", [[], ["malformed"], "legacy-invalid"])
def test_nonobject_previous_snapshot_does_not_discard_new_collection(monkeypatch, previous):
    monkeypatch.setattr(bonddata, "get_bond_market_summary", lambda: {})
    monkeypatch.setattr(bondus, "get_us_bond_summary", lambda: {
        "curve": [{"tenor": "10Y", "yield": 4, "as_of": "2026-10-16"}]})
    out = yieldcurve.get_full_yield_curve_data(previous)
    assert out["available"] and out["yield_curves"]["us"]["curve"][0]["yield"] == 4


def test_slow_first_us_source_cannot_starve_long_maturities_or_credit(monkeypatch):
    """A blocked first attempt leaves other workers free for every later field."""
    series = [sid for _, sid in bondus._TREASURY_SERIES] + list(bondus._CREDIT_SERIES.values())
    all_started, lock = Event(), Lock()
    calls, active, peak = Counter(), [0], [0]

    def fetch(sid, **kwargs):
        with lock:
            calls[sid] += 1
            first_attempt = calls[sid] == 1
            active[0] += 1
            peak[0] = max(peak[0], active[0])
            if len(calls) == len(series):
                all_started.set()
        try:
            assert 0 < runtime.request_timeout(25) <= 25
            if sid == series[0]:
                if first_attempt:
                    assert kwargs["retries"] == 1
                    assert all_started.wait(2), "later fields were starved"
                else:
                    assert len(calls) == 14, "retry ran before all first attempts"
                return None
            return {"value": 4.0, "as_of": "2026-10-16", "source_as_of": "2026-10-16",
                    "source": "fred", "fetched_at": "2026-10-18T12:00:00+09:00",
                    "last_successful_at": "2026-10-18T12:00:00+09:00", "stale": False}
        finally:
            with lock:
                active[0] -= 1

    monkeypatch.setattr(bondus, "_fetch_latest_point", fetch)
    out = bondus.get_us_bond_summary()
    assert set(calls) == set(series) and calls[series[0]] == 2
    assert all(calls[sid] == 1 for sid in series[1:])
    assert 2 <= peak[0] <= 4
    assert out["partial"] and out["stale"]
    assert out["missing_tenors"] == ["1M"] and out["missing_credit"] == []
    assert len(out["curve"]) == 10 and len(out["credit_spreads_meta"]) == 3
    assert out["curve"][-1]["tenor"] == "30Y"
    assert out["curve"][-1]["fetched_at"] == "2026-10-18T12:00:00+09:00"
