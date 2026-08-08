# -*- coding: utf-8 -*-
"""증분 피드의 전량 실패 가드 — RSSScout(news_flash P0) · sec_8k_change_detector(P1).

🚨 #46 전수 점검(2026-08-08)에서 확정한 결함 2건. 둘 다 형태가 같았다:
   "신규 0건"(정상)과 "소스 전량 실패"(사고)를 같은 종료코드 0 으로 뭉갰다.
   산출 파일 mtime 만 갱신되니 신선도 보드는 통과시킨다 = 영구 미탐지.

   증분 피드라 산출 0건 자체는 정상일 수 있다. 그래서 가드는 행수가 아니라
   **조회 성공 수**에 건다. [[feedback_silent_total_failure_guard]]
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.collectors import RSSScout  # noqa: E402
from api.intelligence import sec_8k_change_detector as s8k  # noqa: E402


class _Parsed:
    """feedparser.parse 반환 흉내 — 네트워크 실패 시에도 예외 없이 빈 entries 다."""

    def __init__(self, entries):
        self.entries = entries


def _entry(i: int) -> dict:
    return {"title": f"헤드라인 {i}", "link": f"https://example.test/{i}"}


# ── RSSScout ────────────────────────────────────────────────────────────────

def test_parse_feeds_does_not_count_empty_feed_as_success(monkeypatch):
    """예외 없이 빈 응답이 와도 성공으로 세면 안 된다 — 이게 원래 결함이었다."""
    monkeypatch.setattr(RSSScout.feedparser, "parse", lambda *a, **k: _Parsed([]))
    rows, ok_feeds = RSSScout._parse_feeds()
    assert rows == []
    assert ok_feeds == 0


def test_parse_feeds_counts_feeds_with_entries(monkeypatch):
    monkeypatch.setattr(
        RSSScout.feedparser, "parse", lambda *a, **k: _Parsed([_entry(1)])
    )
    rows, ok_feeds = RSSScout._parse_feeds()
    assert ok_feeds == len(RSSScout.FEEDS)
    assert len(rows) == len(RSSScout.FEEDS)


def test_run_rss_scout_signals_total_failure(monkeypatch):
    """피드 전량 실패 = 음수 반환. 호출부가 exit 1 로 바꾼다."""
    monkeypatch.setattr(RSSScout.feedparser, "parse", lambda *a, **k: _Parsed([]))
    assert RSSScout.run_rss_scout() == -1


def test_run_rss_scout_does_not_touch_output_on_total_failure(monkeypatch, tmp_path):
    """전량 실패 시 산출 파일을 건드리지 않아야 한다 (mtime 갱신 = 보드 오통과)."""
    flash = tmp_path / "news_flash.json"
    flash.write_text("[]", encoding="utf-8")
    before = flash.stat().st_mtime_ns
    monkeypatch.setattr(RSSScout, "NEWS_FLASH_PATH", str(flash))
    monkeypatch.setattr(RSSScout.feedparser, "parse", lambda *a, **k: _Parsed([]))

    assert RSSScout.run_rss_scout() == -1
    assert flash.stat().st_mtime_ns == before


# ── sec_8k_change_detector ──────────────────────────────────────────────────

def test_fetch_recent_8k_returns_none_on_fetch_error(monkeypatch):
    """조회 실패는 None. 빈 리스트([])와 구분되어야 한다."""
    def _boom(*a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr(s8k.requests, "get", _boom)
    assert s8k._fetch_recent_8k("0000000320") is None


def test_detect_changes_reports_zero_fetch_success(monkeypatch):
    """전 ticker 조회 실패 → tickers_fetched_ok=0 (main 이 exit 1 로 바꾼다)."""
    monkeypatch.setattr(s8k, "_ticker_to_cik", lambda t: "0000000320")
    monkeypatch.setattr(s8k, "_fetch_recent_8k", lambda *a, **k: None)
    monkeypatch.setattr(s8k, "_load_cache", lambda: {"by_ticker": {}})
    monkeypatch.setattr(s8k, "_save_cache", lambda c: None)
    monkeypatch.setattr(s8k.time, "sleep", lambda s: None)

    result = s8k.detect_changes(["AAPL", "MSFT"])
    assert result["tickers_checked"] == 2
    assert result["tickers_fetched_ok"] == 0


def test_detect_changes_counts_successful_fetch_with_no_8k(monkeypatch):
    """조회는 됐고 8-K 만 없는 경우 = 정상. 성공으로 세야 한다."""
    monkeypatch.setattr(s8k, "_ticker_to_cik", lambda t: "0000000320")
    monkeypatch.setattr(s8k, "_fetch_recent_8k", lambda *a, **k: [])
    monkeypatch.setattr(s8k, "_load_cache", lambda: {"by_ticker": {}})
    monkeypatch.setattr(s8k, "_save_cache", lambda c: None)
    monkeypatch.setattr(s8k.time, "sleep", lambda s: None)

    result = s8k.detect_changes(["AAPL", "MSFT"])
    assert result["tickers_fetched_ok"] == 2
    assert result["new_filings_count"] == 0
