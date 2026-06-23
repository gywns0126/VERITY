"""earnings_surprise — Phase 1 PEAD 관측 신호 테스트 (2026-06-23).

RULE 7 준수: brain_input=False, weight=0. 합성 데이터만 사용 (API key 불필요).
다루는 항목:
  - KR OP 서프라이즈 수식 (_compute_op_surprise_pct)
  - KR 룩어헤드 제외 (compute_kr_surprise → [])
  - trail 스키마 (append 결과 JSONL 검증)
  - (ticker, report_quarter) 중복 방지
  - US normalize (Finnhub earnings_surprises → events)
"""
import json
import os
import tempfile
from typing import Any, Dict, List

import pytest

import api.intelligence.earnings_surprise as es


# ─── 1. KR 서프라이즈 수식 ────────────────────────────────────────────────────

def test_op_surprise_positive():
    """actual > est → 양수 서프라이즈."""
    pct = es._compute_op_surprise_pct(1100.0, 1000.0)
    assert pct is not None
    assert abs(pct - 10.0) < 0.001  # (1100-1000)/1000 * 100 = 10%


def test_op_surprise_negative():
    """actual < est → 음수 서프라이즈."""
    pct = es._compute_op_surprise_pct(900.0, 1000.0)
    assert pct is not None
    assert abs(pct - (-10.0)) < 0.001


def test_op_surprise_zero_est_excluded():
    """est = 0 → None (분모 guard)."""
    assert es._compute_op_surprise_pct(500.0, 0.0) is None


def test_op_surprise_near_zero_est_excluded():
    """|est| < 1 → None."""
    assert es._compute_op_surprise_pct(500.0, 0.5) is None


def test_op_surprise_none_inputs():
    assert es._compute_op_surprise_pct(None, 1000.0) is None
    assert es._compute_op_surprise_pct(1000.0, None) is None


def test_kr_helper_unit_conversion():
    """_kr_surprise_from_parts: DART 백만원 → 억원 변환 후 서프라이즈 계산."""
    # actual: 100,000 백만원 = 1,000 억원; est: 900 억원 → surprise = +11.11%
    actual_m = 100_000.0  # 백만원
    est_eok = 900.0       # 억원
    pct = es._kr_surprise_from_parts(actual_m, est_eok)
    assert pct is not None
    expected = (actual_m / 100.0 - est_eok) / abs(est_eok) * 100.0
    assert abs(pct - expected) < 0.001


# ─── 2. KR 룩어헤드 제외 ──────────────────────────────────────────────────────

def test_kr_surprise_returns_empty_for_look_ahead_guard():
    """compute_kr_surprise는 룩어헤드 오염 방지로 항상 빈 리스트 반환."""
    kr_stock = {
        "ticker": "005930",
        "currency": "KRW",
        "price": 75000,
        "consensus": {
            "operating_profit_estimate_bn": 350,
            "operating_profit_prior_year_bn": 280,
        },
    }
    result = es.compute_kr_surprise(kr_stock)
    assert isinstance(result, list)
    assert len(result) == 0, "KR join은 룩어헤드 가드 미충족으로 현재 skip 필수"


def test_kr_surprise_no_crash_on_missing_fields():
    """필드 누락 KR 종목도 예외 없이 빈 리스트."""
    assert es.compute_kr_surprise({}) == []
    assert es.compute_kr_surprise({"ticker": "000000"}) == []


# ─── 3. US normalize ─────────────────────────────────────────────────────────

def _us_stock(ticker: str, earnings_surprises: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "ticker": ticker,
        "currency": "USD",
        "price": 150.0,
        "earnings_surprises": earnings_surprises,
    }


def test_normalize_us_basic():
    """US 서프라이즈 → event 리스트 변환."""
    stock = _us_stock("AAPL", [
        {"period": "2024-09-28", "actual": 1.64, "estimate": 1.60, "surprise_pct": 2.5},
        {"period": "2024-06-29", "actual": 1.40, "estimate": 1.35, "surprise_pct": 3.7},
    ])
    events = es.normalize_us_surprise(stock)
    assert len(events) == 2
    ev = events[0]
    assert ev["ticker"] == "AAPL"
    assert ev["market"] == "US"
    assert ev["metric"] == "eps"
    assert ev["report_quarter"] == "2024-09-28"
    assert ev["surprise_pct"] == 2.5
    assert ev["est_source"] == "finnhub"
    assert ev["actual_source"] == "finnhub"
    assert ev["forward"] == {"d1": None, "d5": None, "d20": None, "d60": None}


def test_normalize_us_no_surprises():
    """earnings_surprises 없는 US 종목 → 빈 리스트."""
    assert es.normalize_us_surprise({"ticker": "AAPL", "currency": "USD"}) == []
    assert es.normalize_us_surprise({"ticker": "AAPL", "currency": "USD", "earnings_surprises": []}) == []


def test_normalize_us_missing_surprise_pct_skipped():
    """surprise_pct 없는 항목 → 제외."""
    stock = _us_stock("AAPL", [
        {"period": "2024-09-28", "actual": 1.64, "estimate": 1.60},  # no surprise_pct
        {"period": "2024-06-29", "actual": 1.40, "estimate": 1.35, "surprise_pct": 3.7},
    ])
    events = es.normalize_us_surprise(stock)
    assert len(events) == 1
    assert events[0]["report_quarter"] == "2024-06-29"


def test_normalize_us_no_ticker_skipped():
    """ticker 없는 stock → 빈 리스트."""
    stock = {
        "currency": "USD",
        "earnings_surprises": [{"period": "2024-09-28", "surprise_pct": 2.5}],
    }
    assert es.normalize_us_surprise(stock) == []


# ─── 4. trail 스키마 + 중복 방지 ────────────────────────────────────────────

def _make_stocks(tickers_and_surprises):
    stocks = []
    for ticker, surprises in tickers_and_surprises:
        stocks.append({
            "ticker": ticker, "currency": "USD", "price": 100.0,
            "earnings_surprises": surprises,
        })
    return stocks


def test_trail_schema(tmp_path):
    """run_shadow → trail JSONL 스키마 검증."""
    trail = tmp_path / "earnings_surprise.jsonl"

    # monkeypatch TRAIL_PATH
    orig = es.TRAIL_PATH
    es.TRAIL_PATH = str(trail)
    try:
        stocks = _make_stocks([
            ("NVDA", [{"period": "2024-09-28", "surprise_pct": 5.0}]),
        ])
        result = es.run_shadow(stocks)
        assert result["n_events"] == 1
        assert result["logged"] is True

        # 파일 내용 검증
        lines = trail.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        obj = json.loads(lines[0])
        assert obj["shadow"] is True
        assert obj["brain_input"] is False
        assert "caveat" in obj
        assert "ts_kst" in obj
        events = obj["events"]
        assert len(events) == 1
        ev = events[0]
        required_fields = {
            "ticker", "market", "report_quarter", "announce_date",
            "surprise_pct", "metric", "est_source", "actual_source",
            "entry_price", "forward",
        }
        assert required_fields.issubset(ev.keys()), f"누락 필드: {required_fields - ev.keys()}"
        fwd = ev["forward"]
        assert set(fwd.keys()) == {"d1", "d5", "d20", "d60"}
        assert all(v is None for v in fwd.values()), "stage 1에서 forward는 모두 null이어야 함"
    finally:
        es.TRAIL_PATH = orig


def test_quarter_dedup(tmp_path):
    """동일 (ticker, report_quarter) 중복 append 방지."""
    trail = tmp_path / "earnings_surprise.jsonl"
    orig = es.TRAIL_PATH
    es.TRAIL_PATH = str(trail)
    try:
        surprise = [{"period": "2024-09-28", "surprise_pct": 3.0}]
        stocks = _make_stocks([("AAPL", surprise)])

        r1 = es.run_shadow(stocks)
        assert r1["n_events"] == 1

        # 동일 stocks 재실행 → 중복 없음
        r2 = es.run_shadow(stocks)
        assert r2["n_events"] == 0, "동일 분기는 trail에 다시 추가되면 안 됨"

        lines = trail.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1, "trail에 라인이 1개여야 함 (중복 append 없음)"
    finally:
        es.TRAIL_PATH = orig


def test_quarter_dedup_different_quarters(tmp_path):
    """다른 분기는 모두 추가됨."""
    trail = tmp_path / "earnings_surprise.jsonl"
    orig = es.TRAIL_PATH
    es.TRAIL_PATH = str(trail)
    try:
        stocks1 = _make_stocks([("AAPL", [{"period": "2024-09-28", "surprise_pct": 3.0}])])
        stocks2 = _make_stocks([("AAPL", [{"period": "2024-06-29", "surprise_pct": -1.0}])])

        es.run_shadow(stocks1)
        r2 = es.run_shadow(stocks2)
        assert r2["n_events"] == 1, "다른 분기는 추가되어야 함"
    finally:
        es.TRAIL_PATH = orig


def test_brain_input_false(tmp_path):
    """trail 엔트리 brain_input=False 보장."""
    trail = tmp_path / "earnings_surprise.jsonl"
    orig = es.TRAIL_PATH
    es.TRAIL_PATH = str(trail)
    try:
        stocks = _make_stocks([("MSFT", [{"period": "2024-09-28", "surprise_pct": 1.5}])])
        es.run_shadow(stocks)
        obj = json.loads(trail.read_text(encoding="utf-8").strip())
        assert obj["brain_input"] is False, "brain_input은 반드시 False"
    finally:
        es.TRAIL_PATH = orig


def test_run_shadow_empty_stocks():
    """stocks가 비어있어도 예외 없음."""
    orig = es.TRAIL_PATH
    es.TRAIL_PATH = "/dev/null"  # 기록 안 함
    try:
        result = es.run_shadow([])
        assert result["n_events"] == 0
        assert result["logged"] is False
    finally:
        es.TRAIL_PATH = orig


def test_kr_stocks_produce_no_events_in_run_shadow(tmp_path):
    """KR 종목은 룩어헤드 가드로 trail 이벤트 0건."""
    trail = tmp_path / "earnings_surprise.jsonl"
    orig = es.TRAIL_PATH
    es.TRAIL_PATH = str(trail)
    try:
        kr_stocks = [
            {"ticker": "005930", "currency": "KRW", "price": 75000,
             "consensus": {"operating_profit_estimate_bn": 350}},
            {"ticker": "000660", "currency": "KRW", "price": 120000,
             "consensus": {"operating_profit_estimate_bn": 180}},
        ]
        result = es.run_shadow(kr_stocks)
        assert result["n_events"] == 0, "KR 종목은 현재 이벤트 0건이어야 함 (룩어헤드 가드)"
        assert result["logged"] is False
        assert not trail.exists(), "이벤트 0건이면 파일 생성 안 함"
    finally:
        es.TRAIL_PATH = orig
