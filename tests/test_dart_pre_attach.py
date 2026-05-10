"""dart_pre_attach 회귀 테스트 — DART batch snapshot fast path attach."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.utils.dart_pre_attach import (
    load_dart_fundamentals_kr,
    attach_dart_to_stocks,
)


KST = timezone(timedelta(hours=9))


def _write_snapshot(path: Path, *, hours_ago: int = 1, fundamentals: dict = None):
    ts = (datetime.now(KST) - timedelta(hours=hours_ago)).isoformat()
    snap = {
        "collected_at": ts,
        "fundamentals": fundamentals or {},
        "diagnostics": {"ok": True},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")


def test_load_dart_fundamentals_kr_missing_file(tmp_path):
    """파일 미존재 → None."""
    result = load_dart_fundamentals_kr(path=tmp_path / "missing.json")
    assert result is None


def test_load_dart_fundamentals_kr_fresh(tmp_path):
    """1시간 전 snapshot → cache hit."""
    p = tmp_path / "dart.json"
    _write_snapshot(p, hours_ago=1, fundamentals={"005930": {"per": 12.5, "source": "DART"}})
    result = load_dart_fundamentals_kr(path=p)
    assert result is not None
    assert "005930" in result


def test_load_dart_fundamentals_kr_stale(tmp_path):
    """10일 전 snapshot → stale (max_stale_days=8 기본) → None."""
    p = tmp_path / "dart.json"
    _write_snapshot(p, hours_ago=24 * 10, fundamentals={"X": {}})
    result = load_dart_fundamentals_kr(path=p, max_stale_days=8)
    assert result is None


def test_attach_dart_boosts_weak_yfinance_fields(tmp_path):
    """DART 1순위 — yfinance per=0 일 때 DART per 으로 보강."""
    p = tmp_path / "dart.json"
    _write_snapshot(p, hours_ago=1, fundamentals={
        "005930": {"per": 12.5, "pbr": 1.3, "roe": 12.0, "debt_ratio": 25.0,
                   "op_margin": 15.0, "source": "DART", "report_date": "2025-12-31"},
    })
    stocks = [
        {"ticker": "005930", "currency": "KRW", "per": 0, "pbr": 0, "roe": 0,
         "debt_ratio": 0, "operating_margin": 0},
    ]
    result = attach_dart_to_stocks(stocks, path=p)
    assert result["cache_hit"] is True
    assert result["attached_n"] == 1
    assert result["kr_total_n"] == 1
    # DART 값 보강 확인
    assert stocks[0]["per"] == 12.5
    assert stocks[0]["pbr"] == 1.3
    assert stocks[0]["roe"] == 12.0
    assert stocks[0]["debt_ratio"] == 25.0
    assert stocks[0]["operating_margin"] == 15.0
    # DART-only 필드
    assert stocks[0]["dart_report_date"] == "2025-12-31"
    assert stocks[0]["dart_source"] == "DART"


def test_attach_dart_preserves_strong_yfinance_fields(tmp_path):
    """yfinance per 정확히 박혀 있으면 (가격 의존) 그대로 유지."""
    p = tmp_path / "dart.json"
    _write_snapshot(p, hours_ago=1, fundamentals={
        "005930": {"per": 8.0, "source": "DART"},
    })
    stocks = [{"ticker": "005930", "currency": "KRW", "per": 12.5}]
    attach_dart_to_stocks(stocks, path=p)
    # yfinance per (12.5) 우선 유지
    assert stocks[0]["per"] == 12.5
    # source 메타는 항상 attach
    assert stocks[0]["dart_source"] == "DART"


def test_attach_dart_skips_us_stocks(tmp_path):
    """USD currency 종목 = 미국 — DART 매핑 X."""
    p = tmp_path / "dart.json"
    _write_snapshot(p, hours_ago=1, fundamentals={"AAPL": {"per": 25}})
    stocks = [
        {"ticker": "AAPL", "currency": "USD", "per": 28},
        {"ticker": "005930", "currency": "KRW", "per": 0},
    ]
    result = attach_dart_to_stocks(stocks, path=p)
    assert result["kr_total_n"] == 1  # AAPL 제외
    # AAPL 미터치
    assert stocks[0]["per"] == 28
    assert "dart_source" not in stocks[0]


def test_attach_dart_no_cache_returns_zero(tmp_path):
    """cache miss (파일 X) → attached_n=0, cache_hit=False."""
    stocks = [{"ticker": "005930", "currency": "KRW", "per": 0}]
    result = attach_dart_to_stocks(stocks, path=tmp_path / "missing.json")
    assert result["cache_hit"] is False
    assert result["attached_n"] == 0
