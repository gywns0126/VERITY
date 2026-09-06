# -*- coding: utf-8 -*-
"""sec_companyfacts_bulk — 벌크 전환 계약 테스트.

전환의 전제는 하나다: **주입 경로가 HTTP 경로와 같은 산출을 낸다.**
그게 깨지면 5,324종목을 채워도 기존 1,502종목과 다른 물건이 섞인 레이크가 된다.
"""
from __future__ import annotations

import io
import json
import os
import sys
import zipfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.collectors import sec_companyfacts_bulk as bulk  # noqa: E402
from api.intelligence import us_financials as usf  # noqa: E402


# ── 주입 경로 = 파싱 로직 재사용 ───────────────────────────────────────────
def test_injection_params_exist():
    """facts/sic_pair 주입으로 HTTP 를 건너뛸 수 있어야 한다."""
    import inspect
    for fn in (usf.fetch_all_metrics, usf.build_ticker_snapshot):
        p = inspect.signature(fn).parameters
        assert "facts" in p and "sic_pair" in p, fn.__name__


def test_bulk_reuses_parser_not_reimplements():
    """🚨 직접 파싱하면 같은 스키마가 아니라 다른 산출물이 된다."""
    src = open(bulk.__file__, encoding="utf-8").read()
    assert "build_ticker_snapshot" in src
    # 태그 alias·파생 계산을 자체 구현하지 않았는지
    for bad in ("us-gaap:", "TAG_ALIASES =", "def compute_derived", "def extract_metric_series"):
        assert bad not in src, f"자체 구현 발견: {bad}"


def test_fetch_all_metrics_uses_injected_facts(monkeypatch):
    """facts 를 주면 HTTP 를 부르지 않는다."""
    called = {"n": 0}
    monkeypatch.setattr(usf, "fetch_companyfacts",
                        lambda cik: called.__setitem__("n", called["n"] + 1) or {})
    usf.fetch_all_metrics(320193, facts={"facts": {}}, sic_pair=(3571, "PC"))
    assert called["n"] == 0


def test_fetch_all_metrics_empty_facts_is_error():
    """빈 facts 를 '정상 0건' 으로 통과시키면 안 된다."""
    r = usf.fetch_all_metrics(1, facts={}, sic_pair=(None, None))
    assert "_error" in r


# ── 헤더 (2026-08-08 실사고) ───────────────────────────────────────────────
def test_headers_have_no_accept_encoding():
    """🚨 urllib 은 gzip 응답을 자동 해제하지 않아 JSON 파싱이 깨진다."""
    h = bulk._headers()
    assert "Accept-Encoding" not in h
    assert "@" in h["User-Agent"], "SEC 는 연락처 UA 를 요구한다"


# ── 커버리지 결손 분류 ─────────────────────────────────────────────────────
def test_missing_reasons_are_separated():
    """🚨 결손 사유를 뭉뚱그리면 뭘 고쳐야 할지 모른다 — no_cik 과 no_facts 는 다른 문제다."""
    src = open(bulk.__file__, encoding="utf-8").read()
    assert "no_cik" in src and "no_facts" in src
    assert "사유를 단정하지 않는다" in src


def test_total_failure_exits_nonzero():
    """오늘 us_chart_daily 학습 — 전량 실패를 성공으로 끝내지 않는다."""
    src = open(bulk.__file__, encoding="utf-8").read()
    assert "전량 실패" in src and "return 1" in src


# ── zip 판독 ───────────────────────────────────────────────────────────────
def _zip_with(cik: int, payload: dict, path):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(f"CIK{cik:010d}.json", json.dumps(payload))
    return str(path)


def test_collect_skips_ticker_absent_from_zip(tmp_path, monkeypatch):
    zp = _zip_with(320193, {"cik": 320193, "facts": {}}, tmp_path / "b.zip")
    monkeypatch.setattr(bulk, "OUT_DIR", str(tmp_path / "out"))
    monkeypatch.setattr(bulk, "META_PATH", str(tmp_path / "meta.json"))
    monkeypatch.setattr(bulk, "load_universe", lambda: ["AAPL", "ZZZZ"])
    monkeypatch.setattr(bulk, "load_ticker_cik", lambda: {"AAPL": 320193, "ZZZZ": 999999})
    monkeypatch.setattr(bulk, "fetch_sic", lambda cik: (3571, "PC"))
    monkeypatch.setattr(usf, "build_ticker_snapshot",
                        lambda t, c, **k: {"ticker": t, "meta": {}, "series_annual": {}})
    r = bulk.collect(zp, skip_sic=True)
    assert r["fetched_now"] == 1 and r["no_facts"] == 1


def test_collect_records_no_cik_separately(tmp_path, monkeypatch):
    zp = _zip_with(320193, {"cik": 320193}, tmp_path / "b.zip")
    monkeypatch.setattr(bulk, "OUT_DIR", str(tmp_path / "out"))
    monkeypatch.setattr(bulk, "META_PATH", str(tmp_path / "meta.json"))
    monkeypatch.setattr(bulk, "load_universe", lambda: ["AAPL", "NOCIK"])
    monkeypatch.setattr(bulk, "load_ticker_cik", lambda: {"AAPL": 320193})
    monkeypatch.setattr(usf, "build_ticker_snapshot",
                        lambda t, c, **k: {"ticker": t, "meta": {}, "series_annual": {}})
    r = bulk.collect(zp, skip_sic=True)
    assert r["no_cik"] == 1


def test_collect_is_idempotent(tmp_path, monkeypatch):
    """이미 있는 종목은 건너뛴다 — 재실행이 SEC 를 다시 때리지 않는다."""
    out = tmp_path / "out"
    out.mkdir()
    (out / "AAPL.json").write_text("{}", encoding="utf-8")
    zp = _zip_with(320193, {"cik": 320193}, tmp_path / "b.zip")
    monkeypatch.setattr(bulk, "OUT_DIR", str(out))
    monkeypatch.setattr(bulk, "META_PATH", str(tmp_path / "meta.json"))
    monkeypatch.setattr(bulk, "load_universe", lambda: ["AAPL"])
    monkeypatch.setattr(bulk, "load_ticker_cik", lambda: {"AAPL": 320193})
    r = bulk.collect(zp, skip_sic=True)
    assert r["fetched_now"] == 0 and r["have"] == 1


def test_submission_indexes_include_latest_inline_financial_filing(tmp_path):
    recent = {
        "form": ["8-K", "10-Q", "10-K"],
        "filingDate": ["2026-08-02", "2026-07-29", "2025-11-06"],
        "reportDate": ["", "2026-06-30", "2025-09-30"],
        "accessionNumber": ["A", "Q", "K"],
        "primaryDocument": ["a.htm", "q.htm", "k.htm"],
        "isXBRL": [0, 1, 1],
        "isInlineXBRL": [0, 1, 1],
    }
    zp = _zip_with(1403161, {
        "sic": "6199",
        "sicDescription": "Finance Services",
        "filings": {"recent": recent},
    }, tmp_path / "submissions.zip")
    sic, filings = bulk.submission_indexes_from_zip(zp, {1403161})
    assert sic[1403161] == (6199, "Finance Services")
    assert filings[1403161] == {
        "form": "10-Q",
        "filing_date": "2026-07-29",
        "report_date": "2026-06-30",
        "accession": "Q",
        "primary_document": "q.htm",
        "is_xbrl": True,
        "is_inline_xbrl": True,
    }


def test_collect_uses_inline_fallback_when_latest_accession_is_missing(tmp_path, monkeypatch):
    zp = _zip_with(320193, {"cik": 320193, "facts": {"us-gaap": {}}}, tmp_path / "b.zip")
    monkeypatch.setattr(bulk, "OUT_DIR", str(tmp_path / "out"))
    monkeypatch.setattr(bulk, "META_PATH", str(tmp_path / "meta.json"))
    monkeypatch.setattr(bulk, "load_universe", lambda: ["AAPL"])
    monkeypatch.setattr(bulk, "load_ticker_cik", lambda: {"AAPL": 320193})
    monkeypatch.setattr(bulk.time, "sleep", lambda _: None)
    filing = {
        "form": "10-Q", "filing_date": "2026-08-01", "report_date": "2026-06-30",
        "accession": "NEW", "primary_document": "q.htm", "is_inline_xbrl": True,
    }
    overlay = {
        "facts": {"us-gaap": {"Assets": {"units": {"USD": [{
            "end": "2026-06-30", "val": 10, "accn": "NEW", "fy": 2026,
            "fp": "Q2", "form": "10-Q",
        }]}}}},
        "_inline_meta": {"fact_count": 1, "source_url": "https://sec.test/q.htm"},
    }
    from api.collectors import sec_inline_xbrl as inline
    monkeypatch.setattr(inline, "fetch_inline_xbrl", lambda cik, row: overlay)
    seen = {}
    def _build(ticker, cik, *, facts, sic_pair):
        seen["facts"] = facts
        return {"ticker": ticker, "meta": {}, "series_annual": {}, "series_quarterly": {}}
    monkeypatch.setattr(usf, "build_ticker_snapshot", _build)
    result = bulk.collect(zp, skip_sic=True, filing_index={320193: filing})
    assert result["inline_fallback_ok"] == 1
    assert inline.has_accession(seen["facts"], "NEW") is True
    saved = json.loads((tmp_path / "out" / "AAPL.json").read_text(encoding="utf-8"))
    assert saved["meta"]["latest_filing_sync"]["status"] == "inline_fallback"


def test_universe_is_single_source():
    """유니버스 정의가 두 곳에 갈리면 축마다 커버리지가 어긋난다."""
    src = open(bulk.__file__, encoding="utf-8").read()
    assert "from api.collectors.us_chart_history import load_universe" in src
