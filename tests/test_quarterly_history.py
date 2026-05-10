"""
quarterly_history 회귀 테스트 — 5,000 raw snapshot 분기 jsonl 적재.

검증:
- snapshot 핵심 14개 필드 적재
- ticker 결손 라인 skip
- 분기 파일명 (YYYY-Qn) 정확
- silent 실패 차단 (logged=True/False stderr)
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.utils.quarterly_history import (
    append_universe_snapshot,
    _quarter_filename,
    _output_path,
)


KST = timezone(timedelta(hours=9))


def test_quarter_filename():
    """3월 = Q1, 4월 = Q2, 7월 = Q3, 10월 = Q4."""
    assert _quarter_filename(datetime(2026, 1, 15)) == "2026-Q1"
    assert _quarter_filename(datetime(2026, 3, 31)) == "2026-Q1"
    assert _quarter_filename(datetime(2026, 4, 1)) == "2026-Q2"
    assert _quarter_filename(datetime(2026, 6, 30)) == "2026-Q2"
    assert _quarter_filename(datetime(2026, 7, 1)) == "2026-Q3"
    assert _quarter_filename(datetime(2026, 9, 30)) == "2026-Q3"
    assert _quarter_filename(datetime(2026, 10, 1)) == "2026-Q4"
    assert _quarter_filename(datetime(2026, 12, 31)) == "2026-Q4"


def test_append_universe_snapshot_writes_jsonl(tmp_path):
    """5,000 raw → 분기 jsonl append. ticker 결손 라인 skip."""
    stocks = [
        {"ticker": "005930", "name": "삼성전자", "market": "KOSPI", "currency": "KRW",
         "price": 70000, "per": 12.5, "pbr": 1.3, "roe": 12.0, "roa": 8.0,
         "gross_margins": 35.0, "operating_cashflow": 5e9},
        {"ticker": "AAPL", "name": "Apple", "market": "NASDAQ", "currency": "USD",
         "price": 180.0, "per": 28.0, "roe": 150.0, "free_cashflow": 1e11},
        {"name": "no_ticker"},  # ticker 결손 → skip
    ]
    result = append_universe_snapshot(
        stocks,
        run_at_iso="2026-05-10T19:00:00+09:00",
        output_root=tmp_path,
    )
    assert result["logged"] is True
    assert result["appended_n"] == 2
    assert result["skipped_n"] == 1

    # 분기 파일명 확인 (5월 = Q2)
    expected_path = tmp_path / "2026-Q2.jsonl"
    assert expected_path.exists()
    lines = expected_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2

    # 첫 종목 schema 검증 — sparkline / trends 같은 큰 필드 미적재
    entry1 = json.loads(lines[0])
    assert entry1["ticker"] == "005930"
    assert entry1["per"] == 12.5
    assert entry1["roa"] == 8.0
    assert entry1["gross_margins"] == 35.0
    assert "sparkline" not in entry1
    assert "trends" not in entry1
    assert entry1["ts"] == "2026-05-10T19:00:00+09:00"

    # AAPL — None 필드 (pbr 등) 는 미적재
    entry2 = json.loads(lines[1])
    assert entry2["ticker"] == "AAPL"
    assert entry2["free_cashflow"] == 1e11
    assert "pbr" not in entry2  # 입력에 없으면 jsonl 에도 없음


def test_append_handles_empty_stocks(tmp_path):
    """빈 리스트 → 적재 0건, logged=True (파일은 비어있음)."""
    result = append_universe_snapshot(
        [],
        run_at_iso="2026-05-10T19:00:00+09:00",
        output_root=tmp_path,
    )
    assert result["logged"] is True
    assert result["appended_n"] == 0


def test_multiple_appends_accumulate(tmp_path):
    """같은 분기에 여러 run = 누적 append (시계열 build-up)."""
    stocks_run1 = [{"ticker": "X1", "per": 10}]
    stocks_run2 = [{"ticker": "X1", "per": 11}, {"ticker": "X2", "per": 20}]
    append_universe_snapshot(stocks_run1, run_at_iso="2026-05-10T15:30:00+09:00", output_root=tmp_path)
    append_universe_snapshot(stocks_run2, run_at_iso="2026-05-11T15:30:00+09:00", output_root=tmp_path)

    lines = (tmp_path / "2026-Q2.jsonl").read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 3  # 1 + 2 누적
    # 시계열 정합 — 같은 ticker X1 의 per 변화 추적 가능
    x1_entries = [json.loads(l) for l in lines if json.loads(l)["ticker"] == "X1"]
    assert len(x1_entries) == 2
    assert x1_entries[0]["per"] == 10
    assert x1_entries[1]["per"] == 11
