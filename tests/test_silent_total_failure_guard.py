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
import hashlib
import json
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.collectors import RSSScout  # noqa: E402
from api.intelligence import sec_8k_change_detector as s8k  # noqa: E402

_PARSE_LOCAL_XML = RSSScout.feedparser.parse


class _Parsed:
    """feedparser.parse 반환 흉내 — 네트워크 실패 시에도 예외 없이 빈 entries 다."""

    def __init__(self, entries):
        self.entries = entries
        self.status = 200
        self.version = "rss20" if entries else ""


@pytest.fixture(autouse=True)
def isolated_rss(monkeypatch, tmp_path):
    """Only temporary fixtures; never collect, notify, or write repository data."""
    for name, filename in [("NEWS_FLASH_PATH", "news_flash.json"),
                           ("RECEIPT_PATH", "metadata/rss_source_receipt.json"),
                           ("RAW_DATA_PATH", "raw_data.json"),
                           ("MAPPING_PATH", "mapping.json"),
                           ("ALIASES_PATH", "aliases.json"),
                           ("PORTFOLIO_PATH", "portfolio.json")]:
        monkeypatch.setattr(RSSScout, name, str(tmp_path / filename))
    monkeypatch.delenv("GITHUB_RUN_ID", raising=False)
    monkeypatch.delenv("GITHUB_RUN_ATTEMPT", raising=False)
    def forbidden(*a, **k):
        raise AssertionError("unexpected network or notification")
    monkeypatch.setattr(RSSScout.feedparser, "parse", forbidden)
    monkeypatch.setattr(RSSScout, "send_message", forbidden)


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
    receipt = json.loads((tmp_path / "metadata/rss_source_receipt.json").read_text())
    assert receipt["outcome"] == "all_feed_failure"
    assert receipt["asset"]["sha256"] == hashlib.sha256(b"[]").hexdigest()
    assert receipt["source_freshness_verified"] is False


def _feed(entries=(), status=200, bozo=False, version="rss20"):
    return SimpleNamespace(entries=list(entries), status=status, bozo=bozo, version=version)


@pytest.mark.parametrize("parsed,outcome", [
    (_feed([_entry(1)], status=503), "http_error"),
    (_feed([_entry(1)], bozo=True), "parse_error"),
    (_feed([], version=""), "parse_error"),
    (_feed([]), "success_empty"),
    (_feed([_entry(1)]), "success"),
])
def test_feed_receipt_classifies_actual_response(monkeypatch, parsed, outcome):
    monkeypatch.setattr(RSSScout.feedparser, "parse", lambda *a, **k: parsed)
    evidence = []
    rows, count = RSSScout._parse_feeds(evidence)
    assert len(evidence) == 3
    assert {f["outcome"] for f in evidence} == {outcome}
    assert count == (3 if outcome.startswith("success") else 0)
    assert all(f["started_at"] <= f["finished_at"] for f in evidence)
    if count == 0:
        assert rows == []


@pytest.mark.parametrize("terminal,expected", [(200, 3), (503, 0)])
def test_redirect_uses_terminal_status_not_feedparser_redirect_status(monkeypatch, terminal, expected):
    def redirected(*a, **kwargs):
        handler = kwargs["handlers"][0]
        handler.http_response(None, SimpleNamespace(getcode=lambda: 301))
        handler.https_response(None, SimpleNamespace(getcode=lambda: terminal))
        return _feed([], status=301)
    monkeypatch.setattr(RSSScout.feedparser, "parse", redirected)
    evidence = []
    _, successes = RSSScout._parse_feeds(evidence)
    assert successes == expected
    assert all(f["http_status"] == terminal for f in evidence)


@pytest.mark.parametrize("xml,outcome", [
    (b'<rss version="2.0"><channel><title>test</title></channel></rss>', "success_empty"),
    (b'<html><body>service unavailable</body></html>', "parse_error"),
    (b'<rss version="2.0"><channel><item><title>bad</title></channel>', "parse_error"),
])
def test_real_parser_local_xml_without_network(monkeypatch, xml, outcome):
    parsed = _PARSE_LOCAL_XML(xml)
    parsed.status = 200
    monkeypatch.setattr(RSSScout.feedparser, "parse", lambda *a, **k: parsed)
    evidence = []
    RSSScout._parse_feeds(evidence)
    assert {f["outcome"] for f in evidence} == {outcome}


def test_transport_error_receipt_has_no_exception_message(monkeypatch, tmp_path):
    def fail(*a, **k):
        raise OSError("sensitive-query-value")
    monkeypatch.setattr(RSSScout.feedparser, "parse", fail)
    assert RSSScout.run_rss_scout() == -1
    text = (tmp_path / "metadata/rss_source_receipt.json").read_text()
    receipt = json.loads(text)
    assert "sensitive-query-value" not in text
    assert {f["outcome"] for f in receipt["feeds"]} == {"transport_error"}
    assert not (tmp_path / "news_flash.json").exists()


def test_valid_empty_feed_preserves_file_and_publication_dates(monkeypatch, tmp_path):
    flash = tmp_path / "news_flash.json"
    payload = b'[{"published_at":"2020-01-01","link":"old"}]'
    flash.write_bytes(payload)
    before = flash.stat().st_mtime_ns
    monkeypatch.setattr(RSSScout.feedparser, "parse", lambda *a, **k: _feed([]))
    assert RSSScout.run_rss_scout() == 0
    assert flash.read_bytes() == payload
    assert flash.stat().st_mtime_ns == before
    receipt = json.loads((tmp_path / "metadata/rss_source_receipt.json").read_text())
    assert receipt["outcome"] == "complete"
    assert receipt["new_rows"] == 0
    assert receipt["asset"]["disposition"] == "unchanged_no_new_rows"
    assert receipt["asset"]["sha256"] == hashlib.sha256(payload).hexdigest()
    assert receipt["clock_kind"] == "source_query_attempt"
    assert receipt["source_freshness_verified"] is False


def test_feed_replacement_does_not_reset_200_legacy_headlines(monkeypatch, tmp_path):
    flash = tmp_path / "news_flash.json"
    rows = [{"source": "Reuters" if index % 2 else "Yahoo Finance",
             "title": f"Historical headline {index}",
             "link": f"https://example.test/legacy/{index}",
             "published_at": "2020-01-01T12:00:00+09:00"}
            for index in range(200)]
    payload = json.dumps(rows, indent=2).encode()
    flash.write_bytes(payload)
    before = flash.stat().st_mtime_ns
    monkeypatch.setattr(RSSScout.feedparser, "parse", lambda *a, **k: _feed([]))

    assert RSSScout.run_rss_scout() == 0
    assert flash.read_bytes() == payload
    assert flash.stat().st_mtime_ns == before
    receipt = json.loads((tmp_path / "metadata/rss_source_receipt.json").read_text())
    assert receipt["asset"]["rows"] == 200
    assert receipt["asset"]["sha256"] == hashlib.sha256(payload).hexdigest()
    assert receipt["source_freshness_verified"] is False


def test_partial_feed_success_binds_written_list_and_keeps_article_time(monkeypatch, tmp_path):
    published = (2024, 1, 2, 3, 4, 5, 1, 2, 0)
    entry = RSSScout.feedparser.FeedParserDict(
        title="EXCLUSIVE a headline", link="https://example.test/new",
        published_parsed=published)
    responses = iter([_feed([entry]), _feed([], status=500), _feed([], bozo=True)])
    monkeypatch.setattr(RSSScout.feedparser, "parse", lambda *a, **k: next(responses))
    assert RSSScout.run_rss_scout() == 1
    flash = tmp_path / "news_flash.json"
    rows = json.loads(flash.read_bytes())
    assert isinstance(rows, list)
    assert rows[0]["published_at"] == "2024-01-02T12:04:05+09:00"
    assert set(rows[0]) == {"source", "title", "published_at", "link"}
    receipt = json.loads((tmp_path / "metadata/rss_source_receipt.json").read_text())
    assert receipt["outcome"] == "partial_failure"
    assert receipt["scope"]["successful_feeds"] == 1
    assert receipt["scope"]["expected_feeds"] == 3
    assert receipt["asset"]["sha256"] == hashlib.sha256(flash.read_bytes()).hexdigest()
    assert receipt["asset"]["disposition"] == "atomically_replaced"
    assert receipt["source_freshness_verified"] is False
    digest = RSSScout.verify_receipt()
    assert RSSScout.verify_receipt(digest) == digest
    flash.write_text("[]")
    with pytest.raises(ValueError, match="hash mismatch"):
        RSSScout.verify_receipt(digest)


def test_delivery_rejects_different_attempt_and_receipt(monkeypatch, tmp_path):
    (tmp_path / "news_flash.json").write_text("[]")
    monkeypatch.setenv("GITHUB_RUN_ID", "123")
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "1")
    monkeypatch.setattr(RSSScout.feedparser, "parse", lambda *a, **k: _feed([]))
    assert RSSScout.run_rss_scout() == 0
    digest = RSSScout.verify_receipt()
    with pytest.raises(ValueError, match="receipt changed"):
        RSSScout.verify_receipt("0" * 64)
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "2")
    with pytest.raises(ValueError, match="another attempt"):
        RSSScout.verify_receipt(digest)


def test_committed_pair_must_exactly_match_saved_bytes(monkeypatch, tmp_path):
    import subprocess
    (tmp_path / "news_flash.json").write_text("[]")
    monkeypatch.setattr(RSSScout.feedparser, "parse", lambda *a, **k: _feed([]))
    RSSScout.run_rss_scout()
    digest = RSSScout.verify_receipt()
    paths = {"HEAD:data/metadata/rss_source_receipt.json":
             (tmp_path / "metadata/rss_source_receipt.json").read_bytes(),
             "HEAD:data/news_flash.json": b"[]"}
    seen = []
    def show(args, **kwargs):
        seen.append(args)
        return SimpleNamespace(stdout=paths[args[2]])
    monkeypatch.setattr(subprocess, "run", show)
    assert RSSScout.verify_receipt(digest, committed=True) == digest
    assert len(seen) == 2
    assert all(args[:2] == ["git", "show"] for args in seen)
    paths["HEAD:data/news_flash.json"] = b"[{}]"
    with pytest.raises(ValueError, match="committed receipt/output mismatch"):
        RSSScout.verify_receipt(digest, committed=True)


def test_duplicate_or_filtered_rows_are_normal_zero_not_new_source_dates(monkeypatch, tmp_path):
    (tmp_path / "news_flash.json").write_text('[{"link":"https://example.test/1"}]')
    entries = [_entry(1), _entry(2)]
    monkeypatch.setattr(RSSScout.feedparser, "parse", lambda *a, **k: _feed(entries))
    assert RSSScout.run_rss_scout() == 0
    receipt = json.loads((tmp_path / "metadata/rss_source_receipt.json").read_text())
    assert receipt["outcome"] == "complete"
    assert receipt["new_rows"] == 0
    assert all(f["entries_without_source_date"] == 2 for f in receipt["feeds"])
    assert receipt["source_freshness_verified"] is False


@pytest.mark.parametrize("case,outcome,count,disposition", [
    ("complete_new", "complete", 1, "atomically_replaced"),
    ("complete_zero", "complete", 0, "unchanged_no_new_rows"),
    ("partial", "partial_failure", 1, "atomically_replaced"),
    ("failed", "all_feed_failure", -1, "preserved_after_failure"),
])
def test_saved_pair_hashes_across_collection_outcomes(
        monkeypatch, tmp_path, case, outcome, count, disposition):
    flash = tmp_path / "news_flash.json"
    original = b'[{"link":"old","published_at":"2020-01-01"}]'
    flash.write_bytes(original)
    before = flash.stat().st_mtime_ns
    entry = RSSScout.feedparser.FeedParserDict(
        title="EXCLUSIVE receipt fixture", link="https://example.test/receipt")
    good = _feed([] if case == "complete_zero" else [entry])
    bad = _feed([], status=503)
    responses = iter([bad, bad, bad] if case == "failed" else
                     [good, bad, bad] if case == "partial" else [good, good, good])
    monkeypatch.setattr(RSSScout.feedparser, "parse", lambda *a, **k: next(responses))
    assert RSSScout.run_rss_scout() == count
    saved_receipt = (tmp_path / "metadata/rss_source_receipt.json").read_bytes()
    receipt = json.loads(saved_receipt)
    saved_asset = flash.read_bytes()
    assert receipt["producer"] == "RSSScout"
    assert receipt["schema_version"] == 1
    assert receipt["outcome"] == outcome
    assert receipt["clock_kind"] == "source_query_attempt"
    assert receipt["source_freshness_verified"] is False
    assert receipt["started_at"] <= receipt["finished_at"]
    assert len(receipt["feeds"]) == receipt["scope"]["expected_feeds"] == 3
    assert receipt["asset"] == {
        "path": "data/news_flash.json", "disposition": disposition,
        "status": "bound", "sha256": hashlib.sha256(saved_asset).hexdigest(),
        "rows": len(json.loads(saved_asset)),
    }
    receipt_hash = hashlib.sha256(saved_receipt).hexdigest()
    assert RSSScout.verify_receipt(receipt_hash) == receipt_hash
    assert not (tmp_path / "news_flash.json.tmp").exists()
    if case in {"complete_zero", "failed"}:
        assert saved_asset == original
        assert flash.stat().st_mtime_ns == before


def test_atomic_receipt_failure_preserves_prior_receipt(monkeypatch, tmp_path):
    receipt = tmp_path / "metadata/rss_source_receipt.json"
    receipt.parent.mkdir()
    receipt.write_bytes(b"previous receipt")
    before = receipt.stat().st_mtime_ns
    (tmp_path / "news_flash.json").write_text("[]")
    monkeypatch.setattr(RSSScout.feedparser, "parse", lambda *a, **k: _feed([]))
    def fail_replace(*a, **k):
        raise OSError("save failed")
    monkeypatch.setattr(RSSScout.os, "replace", fail_replace)
    with pytest.raises(OSError, match="save failed"):
        RSSScout.run_rss_scout()
    assert receipt.read_bytes() == b"previous receipt"
    assert receipt.stat().st_mtime_ns == before
    assert list(receipt.parent.iterdir()) == [receipt]


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
