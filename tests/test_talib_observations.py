"""talib_observations observation-only 계측 테스트 (2026-06-09).

talib 설치/미설치 양쪽에서 graceful + divergence/캔들/insufficient 분기 검증.
🚨 observation-only — 점수 미반영 계약 확인.
"""
import numpy as np
import pandas as pd

from api.analyzers.talib_observations import (
    _TALIB_AVAILABLE,
    compute_talib_observations,
)


def _synthetic_hist(n: int = 80, seed_base: float = 100.0) -> pd.DataFrame:
    """결정론적 합성 OHLCV (Math.random 없이)."""
    closes = [seed_base + 5.0 * np.sin(i / 6.0) + i * 0.2 for i in range(n)]
    rows = []
    for i, cl in enumerate(closes):
        op = closes[i - 1] if i > 0 else cl
        hi = max(op, cl) + 1.0
        lo = min(op, cl) - 1.0
        rows.append({"Open": op, "High": hi, "Low": lo, "Close": cl, "Volume": 1000 + i})
    return pd.DataFrame(rows)


def test_graceful_when_talib_missing_or_present():
    """미설치면 available=False, 설치면 핵심 키 존재 — 둘 다 예외 없이."""
    out = compute_talib_observations(_synthetic_hist())
    assert isinstance(out, dict)
    assert "available" in out
    if not _TALIB_AVAILABLE:
        assert out["available"] is False
        assert out.get("reason") == "talib_not_installed"


def test_full_observation_when_available():
    if not _TALIB_AVAILABLE:
        return  # 미설치 환경 skip
    out = compute_talib_observations(_synthetic_hist(80))
    assert out["available"] is True
    assert out.get("n") == 80
    # 핵심 지표 산출 (None 또는 float)
    for k in ("rsi", "macd_hist", "atr", "stoch_k"):
        assert k in out
    assert isinstance(out.get("candle_patterns"), dict)
    assert isinstance(out.get("divergence_vs_self"), dict)


def test_divergence_computed_against_self():
    if not _TALIB_AVAILABLE:
        return
    # 일부러 빗나간 self 값 전달 → divergence 큼
    out = compute_talib_observations(
        _synthetic_hist(80), self_rsi=0.0, self_macd_hist=0.0, self_atr=1.0
    )
    div = out.get("divergence_vs_self", {})
    assert "rsi_abs" in div and div["rsi_abs"] >= 0
    assert "atr_pct" in div


def test_insufficient_history():
    if not _TALIB_AVAILABLE:
        return
    out = compute_talib_observations(_synthetic_hist(20))
    assert out["available"] is True
    assert out.get("insufficient_history") is True


def test_missing_columns_graceful():
    if not _TALIB_AVAILABLE:
        return
    bad = pd.DataFrame({"Close": [1.0, 2.0, 3.0]})  # OHLC 누락
    out = compute_talib_observations(bad)
    assert out["available"] is True
    assert out.get("error") == "missing_ohlc_columns"


def test_observation_only_contract():
    """반환 dict 에 점수/등급 필드가 없어야 (observation-only 계약)."""
    out = compute_talib_observations(_synthetic_hist(80))
    forbidden = {"score", "brain_score", "technical_score", "grade", "weight"}
    assert forbidden.isdisjoint(out.keys())
