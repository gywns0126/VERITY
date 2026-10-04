"""Share-class fanout keeps daily-index reads and ticker caps unchanged."""
from datetime import date, datetime, timezone
import json
from types import SimpleNamespace

import pytest

from api.builders import us_financials_incremental as incremental


CIK = 1652044


@pytest.fixture
def summaries(tmp_path, monkeypatch):
    paths = [tmp_path / "summary.json", tmp_path / "smallcap.json"]
    rows = [
        [{"ticker": "GOOG", "cik": CIK}, {"ticker": "GOOGL", "cik": str(CIK)},
         {"ticker": "INVALID", "cik": "bad"}, {"ticker": "NO_CIK"}],
        [{"ticker": "GOOG", "cik": CIK}, {"ticker": "GOOGL", "cik": CIK}],
    ]
    for path, records in zip(paths, rows):
        path.write_text(json.dumps({"rows": records}), encoding="utf-8")
    monkeypatch.setattr(incremental, "SUMMARY_PATHS", [str(path) for path in paths])
    return paths


def test_universe_preserves_classes_and_deduplicates_summary_overlap(summaries):
    assert incremental._universe_cik_map() == {CIK: ["GOOG", "GOOGL"]}


@pytest.mark.parametrize("cap,dry_run,failed", [
    (2, False, None), (1, False, None), (2, True, None), (2, False, "GOOG"),
])
def test_main_fans_out_classes_with_ticker_cap_and_safe_cursor(
        summaries, monkeypatch, cap, dry_run, failed):
    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            value = cls(2026, 10, 2, 18, tzinfo=timezone.utc)
            return value.astimezone(tz) if tz is not None else value.replace(tzinfo=None)

    index_reads, builds, patterns, states = [], [], [], []

    def fetch_day(day):
        index_reads.append(day)
        return [(CIK, "10-K"), (CIK, "10-Q"), (999999, "10-K")]

    def collect(command, **kwargs):
        assert command[-2] == "--ticker"
        ticker = command[-1]
        builds.append(ticker)
        return SimpleNamespace(returncode=int(ticker == failed), stdout="",
                               stderr="ERROR" if ticker == failed else "saved snapshot")

    def unexpected_network(*args, **kwargs):
        pytest.fail("Network calls are forbidden in this regression")

    monkeypatch.setattr(incremental, "datetime", FrozenDatetime)
    monkeypatch.setattr(incremental, "_load_state", lambda: {"last_processed": "2026-09-30"})
    monkeypatch.setattr(incremental, "_fetch_day_filers", fetch_day)
    monkeypatch.setattr(incremental, "_append_patterns", patterns.extend)
    monkeypatch.setattr(incremental, "_save_state", states.append)
    monkeypatch.setattr(incremental.subprocess, "run", collect)
    monkeypatch.setattr(incremental.requests, "get", unexpected_network)
    monkeypatch.setattr(incremental.time, "sleep", lambda seconds: None)
    args = ["incremental", "--cap", str(cap)] + (["--dry-run"] if dry_run else [])
    monkeypatch.setattr(incremental.sys, "argv", args)

    assert incremental.main() == int(failed is not None)
    assert index_reads == [date(2026, 10, 1)]
    expected = ["GOOG", "GOOGL"][:cap]
    assert builds == ([] if dry_run else expected)
    if dry_run:
        assert patterns == states == []
    else:
        assert patterns == [
            ("GOOG", "10-K", "2026-10-01"), ("GOOGL", "10-K", "2026-10-01"),
            ("GOOG", "10-Q", "2026-10-01"), ("GOOGL", "10-Q", "2026-10-01"),
        ]
        assert len(states) == 1
        assert states[0]["last_run_tickers"] == [tk for tk in expected if tk != failed]
        assert states[0]["last_processed"] == (
            "2026-10-01" if cap == 2 and failed is None else "2026-09-30")


def test_daily_index_request_once_even_with_multiple_forms(monkeypatch):
    requests = []

    def get(url, **kwargs):
        requests.append(url)
        return SimpleNamespace(status_code=200, text=(
            f"{CIK}|Alphabet|10-K|2026-10-01|a.txt\n"
            f"{CIK}|Alphabet|10-Q|2026-10-01|b.txt\n"
            f"{CIK}|Alphabet|8-K|2026-10-01|c.txt\n"))

    monkeypatch.setattr(incremental.requests, "get", get)
    assert incremental._fetch_day_filers(date(2026, 10, 1)) == [(CIK, "10-K"), (CIK, "10-Q")]
    assert len(requests) == 1


@pytest.mark.parametrize("form", ["20-F", "20-F/A", "40-F", "40-F/A"])
def test_foreign_annual_forms_refresh_without_admitting_6k(monkeypatch, form):
    calls = []

    def get(url, **kwargs):
        calls.append(url)
        return SimpleNamespace(status_code=200, text=(
            f"{CIK}|Foreign issuer|{form}|2026-10-01|a.txt\n"
            f"{CIK}|Foreign issuer|6-K|2026-10-01|b.txt\n"
            f"{CIK}|Foreign issuer|6-K/A|2026-10-01|c.txt\n"))

    monkeypatch.setattr(incremental.requests, "get", get)
    assert incremental._fetch_day_filers(date(2026, 10, 1)) == [(CIK, form)]
    assert len(calls) == 1
