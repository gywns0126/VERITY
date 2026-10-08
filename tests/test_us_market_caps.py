"""us_market_caps wire 검증 — load_market_caps + load_us_externals merge 우선순위.

[[project_us_financials_sec_edgar]] (a) market_cap wire. 네트워크 없음 (tmp 파일 monkeypatch).
FastInfo 오류 복구·rate-limit 경계·last-good 날짜·부분 재수집은 네트워크 mock 으로 검증.
"""
from __future__ import annotations

import json
import socket
import sys
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from api.builders import us_financials_builder as b
from api.collectors import yfinance_safe as safe
from scripts.us import fetch_us_market_caps as collector


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("network access forbidden in market-cap tests")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    monkeypatch.setattr(collector, "yf_ticker", blocked)
    monkeypatch.setattr(safe.time, "sleep", lambda _: None)
    monkeypatch.setattr(safe, "_state", {
        "rate_limit_count": 0, "last_rate_limit_ts": 0.0, "cooler_until_ts": 0.0,
    })


def _write_caps(tmp_path, caps: dict):
    p = tmp_path / "us_market_caps.json"
    p.write_text(json.dumps({"market_caps": caps}), encoding="utf-8")
    return p


def _write_portfolio(tmp_path, recs: list):
    p = tmp_path / "portfolio.json"
    p.write_text(json.dumps({"recommendations": recs}), encoding="utf-8")
    return p


def test_load_market_caps_filters_invalid(tmp_path, monkeypatch):
    caps = {"AAPL": 4.0e12, "BAD": "x", "ZERO": 0, "NEG": -5, "NAN": float("nan")}
    monkeypatch.setattr(b, "MARKET_CAPS_PATH", _write_caps(tmp_path, caps))
    out = b.load_market_caps()
    assert out == {"AAPL": 4.0e12}  # 비숫자/0/음수/NaN 제거


def test_load_market_caps_absent_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(b, "MARKET_CAPS_PATH", tmp_path / "missing.json")
    assert b.load_market_caps() == {}


def test_externals_sp1500_cap_wired(tmp_path, monkeypatch):
    # sp1500-only ticker(추천 밖)도 market_cap 받음 = 1490 size 미상 gap 닫힘.
    monkeypatch.setattr(b, "MARKET_CAPS_PATH", _write_caps(tmp_path, {"AAON": 11.2e9}))
    monkeypatch.setattr(b, "PORTFOLIO_PATH", _write_portfolio(tmp_path, []))
    ext = b.load_us_externals()
    assert ext["AAON"]["market_cap"] == 11.2e9
    assert ext["AAON"]["div_yield"] is None  # 배당은 portfolio 만 (1500 후속 큐)


def test_externals_portfolio_overlay_precedence(tmp_path, monkeypatch):
    # 추천 15 = 라이브 market_cap 우선 + div_yield overlay. caps 파일값을 portfolio 가 덮음.
    monkeypatch.setattr(b, "MARKET_CAPS_PATH", _write_caps(tmp_path, {"MSFT": 3.0e12}))
    monkeypatch.setattr(b, "PORTFOLIO_PATH", _write_portfolio(
        tmp_path, [{"ticker": "MSFT", "market_cap": 3.5e12, "div_yield": 0.7}]))
    ext = b.load_us_externals()
    assert ext["MSFT"]["market_cap"] == 3.5e12   # portfolio 라이브 우선
    assert ext["MSFT"]["div_yield"] == 0.7


def test_externals_portfolio_null_cap_falls_back_to_caps_file(tmp_path, monkeypatch):
    # portfolio 에 종목 있으나 market_cap 결손 → caps 파일값 유지 (덮어쓰며 None 만들지 않음).
    monkeypatch.setattr(b, "MARKET_CAPS_PATH", _write_caps(tmp_path, {"CRM": 2.5e11}))
    monkeypatch.setattr(b, "PORTFOLIO_PATH", _write_portfolio(
        tmp_path, [{"ticker": "CRM", "market_cap": None, "div_yield": None}]))
    ext = b.load_us_externals()
    assert ext["CRM"]["market_cap"] == 2.5e11


def test_fast_info_success_does_not_fetch_info(monkeypatch):
    class Stock:
        fast_info = SimpleNamespace(market_cap=42e9)

        @property
        def info(self):
            pytest.fail("successful FastInfo must not request quote info")

    monkeypatch.setattr(collector, "yf_ticker", lambda _: Stock())
    assert collector.fetch_market_cap("GOOD") == 42e9


def test_fast_info_mapping_compatibility(monkeypatch):
    monkeypatch.setattr(collector, "yf_ticker", lambda _: SimpleNamespace(fast_info={"marketCap": 7e9}))
    assert collector.fetch_market_cap("MAPPING") == 7e9


def test_empty_fast_attribute_does_not_repeat_alias(monkeypatch):
    class FastInfo:
        market_cap = None

        def __getitem__(self, key):
            pytest.fail("empty FastInfo must proceed to the independent quote source")

    monkeypatch.setattr(collector, "yf_ticker", lambda _: SimpleNamespace(
        fast_info=FastInfo(), info={"marketCap": 2e9}))
    assert collector.fetch_market_cap("EMPTY") == 2e9


def test_current_trading_period_error_uses_quote_field_once(monkeypatch):
    calls = []

    class FastInfo:
        @property
        def market_cap(self):
            calls.append("fast")
            raise KeyError("currentTradingPeriod")

        def __getitem__(self, key):
            pytest.fail("FastInfo alias would repeat the broken metadata path")

    class Stock:
        fast_info = FastInfo()

        @property
        def info(self):
            calls.append("info")
            return {"marketCap": 9e9}

    monkeypatch.setattr(collector, "yf_ticker", lambda _: Stock())
    assert collector.fetch_market_cap("RECOVER") == 9e9
    assert calls == ["fast", "info"]


@pytest.mark.parametrize("invalid", [None, 0, -1, float("nan"), float("inf"), -float("inf"), True, "bad"])
def test_invalid_fast_info_uses_valid_quote_field(monkeypatch, invalid):
    monkeypatch.setattr(collector, "yf_ticker", lambda _: SimpleNamespace(
        fast_info={"marketCap": invalid}, info={"marketCap": 3e9}))
    assert collector.fetch_market_cap("FALLBACK") == 3e9


@pytest.mark.parametrize("invalid", [None, 0, -1, float("nan"), float("inf"), True, "bad"])
def test_invalid_quote_field_remains_missing(monkeypatch, invalid):
    monkeypatch.setattr(collector, "yf_ticker", lambda _: SimpleNamespace(
        fast_info={}, info={"marketCap": invalid, "sharesOutstanding": 100, "currentPrice": 20}))
    assert collector.fetch_market_cap("MISSING") is None  # No shares × price estimate.


def test_non_rate_limit_quote_failure_does_not_retry(monkeypatch):
    calls = []

    class Stock:
        fast_info = {}

        @property
        def info(self):
            calls.append("info")
            raise ValueError("malformed quote")

    monkeypatch.setattr(collector, "yf_ticker", lambda _: Stock())
    assert collector.fetch_market_cap("FAIL") is None
    assert calls == ["info"]


@pytest.mark.parametrize("fail_at", ["fast", "info"])
def test_rate_limit_preserves_existing_bounded_backoff(monkeypatch, fail_at):
    calls = []

    class Stock:
        @property
        def fast_info(self):
            calls.append("fast")
            if fail_at == "fast":
                raise RuntimeError("429 Too Many Requests")
            return {}

        @property
        def info(self):
            calls.append("info")
            raise RuntimeError("429 Too Many Requests")

    monkeypatch.setattr(collector, "yf_ticker", lambda _: Stock())
    assert collector.fetch_market_cap("LIMITED") is None
    assert calls.count("fast") == safe.MAX_RETRIES + 1
    assert calls.count("info") == (safe.MAX_RETRIES + 1 if fail_at == "info" else 0)
    assert safe.get_state_snapshot()["rate_limit_count"] == safe.MAX_RETRIES + 1


def _run_collector(tmp_path, monkeypatch, existing, tickers, results, args=()):
    output = tmp_path / "caps.json"
    if existing is not None:
        output.write_text(json.dumps(existing), encoding="utf-8")
    universe = tmp_path / "universe.json"
    universe.write_text(json.dumps({"tickers": tickers}), encoding="utf-8")
    monkeypatch.setattr(collector, "OUTPUT_PATH", output)
    monkeypatch.setattr(collector, "SP1500_PATH", universe)
    monkeypatch.setattr(sys, "argv", ["fetch_us_market_caps.py", *args])
    attempted = []

    def fetch(ticker):
        attempted.append(ticker)
        return results[ticker]

    monkeypatch.setattr(collector, "fetch_market_cap", fetch)
    assert collector.main() == 0
    return attempted, json.loads(output.read_text(encoding="utf-8"))


def test_failed_refresh_preserves_last_good_value_and_original_date(tmp_path, monkeypatch):
    old = "2026-09-01T08:00:00+09:00"
    attempted, doc = _run_collector(tmp_path, monkeypatch, {
        "market_caps": {"OLD": 5e9, "UNTOUCHED": 4e9},
        "market_cap_as_of": {"OLD": old, "UNTOUCHED": old},
        "failed_tickers": ["NEW"],
    }, ["OLD", "NEW"], {"OLD": None, "NEW": 8e9})
    assert attempted == ["OLD", "NEW"]
    assert doc["market_caps"] == {"OLD": 5e9, "UNTOUCHED": 4e9, "NEW": 8e9}
    assert doc["market_cap_as_of"]["OLD"] == old
    assert doc["market_cap_as_of"]["UNTOUCHED"] == old
    assert datetime.fromisoformat(doc["market_cap_as_of"]["NEW"]) > datetime.fromisoformat(old)
    assert doc["failed_tickers"] == ["OLD"]


def test_legacy_date_unknown_and_nonfinite_values_removed(tmp_path, monkeypatch):
    _, doc = _run_collector(tmp_path, monkeypatch, {
        "generated_at": "2026-10-06T00:00:00+09:00",
        "market_caps": {"OLD": 7e9, "INF": float("inf"), "BOOL": True, "NAN": float("nan")},
    }, ["OLD", "INF"], {"OLD": None, "INF": float("inf")})
    assert doc["market_caps"] == {"OLD": 7e9}
    assert doc["market_cap_as_of"] == {"OLD": None}
    assert doc["failed_tickers"] == ["INF", "OLD"]


def test_retry_only_filters_before_limit_and_keeps_other_failures(tmp_path, monkeypatch):
    attempted, doc = _run_collector(tmp_path, monkeypatch, {
        "market_caps": {"GOOD": 4e9, "RETRY": 5e9},
        "failed_tickers": ["RETRY", "OUTSIDE"],
    }, ["GOOD", "MISSING", "MISSING", "RETRY"], {"MISSING": 6e9}, ["--retry-only", "--limit", "1"])
    assert attempted == ["MISSING"]
    assert doc["failed_tickers"] == ["OUTSIDE", "RETRY"]


def test_stale_selection_includes_unknown_and_failures_and_respects_offset(tmp_path, monkeypatch):
    now = datetime.now(collector.KST)
    old = (now - timedelta(days=60)).isoformat()
    fresh = now.isoformat()
    attempted, doc = _run_collector(tmp_path, monkeypatch, {
        "market_caps": {"FRESH": 1e9, "OLD": 2e9, "UNKNOWN": 3e9, "FAILED": 4e9},
        "market_cap_as_of": {"FRESH": fresh, "OLD": old, "FAILED": fresh},
        "failed_tickers": ["FAILED"],
    }, ["FRESH", "OLD", "UNKNOWN", "FAILED", "MISSING"],
        {"UNKNOWN": 5e9, "FAILED": 6e9}, ["--stale-days", "30", "--offset", "1", "--limit", "2"])
    assert attempted == ["UNKNOWN", "FAILED"]
    assert doc["market_cap_as_of"]["OLD"] == old
    assert doc["failed_tickers"] == []


def test_retry_only_noop_does_not_rewrite_snapshot(tmp_path, monkeypatch):
    existing = {"generated_at": "old", "market_caps": {"GOOD": 1e9}}
    attempted, doc = _run_collector(tmp_path, monkeypatch, existing, ["GOOD"], {}, ["--retry-only"])
    assert attempted == []
    assert doc == existing


def test_unreadable_existing_file_is_not_overwritten_or_fetched(tmp_path, monkeypatch):
    output = tmp_path / "broken.json"
    output.write_text("{broken", encoding="utf-8")
    monkeypatch.setattr(collector, "OUTPUT_PATH", output)
    monkeypatch.setattr(sys, "argv", ["fetch_us_market_caps.py", "--ticker", "ANY"])
    assert collector.main() == 1
    assert output.read_text(encoding="utf-8") == "{broken"
