"""
기술적 지표 분석 엔진 v2 (Sprint 3)
- Wilder RSI (지수 스무딩)
- 거래량 방향 구분 (상승/하락 동반)
- 추세 강도 판단 (ADX 근사)
- 데드크로스 탐지

Phase 0 (2026-05-01) — ATR 표준화 마이그레이션 (P-01 ~ P-09 patch).
ATR 산출 헬퍼 함수 분리 + Wilder EMA 표준 + A/B 비교 로깅.
환경변수 정의는 api/config.py 단일 위치 (P-01).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

import pandas as pd
import yfinance as yf

# Phase 0 (P-01): 환경변수는 config.py 단일 정의 사용. 모듈 변수 재정의 X.
from api.config import (
    ATR_METHOD,
    ATR_MIGRATION_LOGGING,
    ATR_MIGRATION_START_DATE,
    ATR_MIN_PERIOD,
)

log = logging.getLogger(__name__)

ATR_MIGRATION_LOG_PATH = Path("data/metadata/atr_migration_log.jsonl")


def compute_true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    """True Range 표준 정의: TR = max(H-L, |H-prevC|, |L-prevC|)."""
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1).dropna()
    return tr


def compute_atr_14d(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    method: str | None = None,
):
    """14-period ATR 산출 (Phase 0 헬퍼, P-01).

    Args:
        method: "wilder_ema_14" (default) | "sma_14" (legacy/rollback).
                None 이면 환경변수 ATR_METHOD 사용.

    Returns:
        (atr_value, atr_pct, method_used) 튜플. 데이터 부족 시 (None, None, method).
    """
    if method is None:
        method = ATR_METHOD

    min_period = ATR_MIN_PERIOD
    if len(close) < min_period or len(high) < min_period or len(low) < min_period:
        return None, None, method

    tr = compute_true_range(high, low, close)
    if len(tr) < 14:
        return None, None, method

    if method == "wilder_ema_14":
        # Wilder smoothing: alpha = 1/14, adjust=False
        atr_val = tr.ewm(alpha=1 / 14, adjust=False).mean().iloc[-1]
    elif method == "sma_14":
        # Legacy SMA (rollback 전용)
        atr_val = tr.rolling(14).mean().iloc[-1]
    else:
        raise ValueError(f"Unknown ATR method: {method}")

    if pd.notna(atr_val) and atr_val > 0:
        price = float(close.iloc[-1])
        atr_pct = round(atr_val / price * 100, 2) if price > 0 else None
        return round(float(atr_val), 4), atr_pct, method

    return None, None, method


def compute_atr_with_ab_comparison(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    ticker: str = "unknown",
):
    """A/B 비교 로깅 (Phase 0 마이그레이션 14일).

    Wilder + SMA 둘 다 산출 후 차이 jsonl append. Wilder 결과 반환.
    P-05 가드 함수 (_should_log_migration) 가 호출 여부 결정 — 본 함수는 단순 산출+로깅.
    """
    atr_wilder, atr_wilder_pct, _ = compute_atr_14d(high, low, close, method="wilder_ema_14")

    if atr_wilder is None:
        return None, None, "wilder_ema_14"

    atr_sma, atr_sma_pct, _ = compute_atr_14d(high, low, close, method="sma_14")
    if atr_sma is None or atr_sma <= 0:
        return atr_wilder, atr_wilder_pct, "wilder_ema_14"

    diff_pct = (atr_wilder - atr_sma) / atr_sma * 100

    try:
        ATR_MIGRATION_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with ATR_MIGRATION_LOG_PATH.open("a") as f:
            f.write(json.dumps({
                "ticker": ticker,
                "timestamp": datetime.now().isoformat(),
                "atr_wilder": atr_wilder,
                "atr_sma": atr_sma,
                "atr_wilder_pct": atr_wilder_pct,
                "atr_sma_pct": atr_sma_pct,
                "diff_pct": round(diff_pct, 2),
            }) + "\n")
    except Exception as e:
        log.warning(f"ATR migration log write failed: {e}")

    if abs(diff_pct) > 30:
        log.warning(
            f"ATR migration big diff: ticker={ticker}, "
            f"wilder={atr_wilder:.4f}, sma={atr_sma:.4f}, diff={diff_pct:.1f}%"
        )

    return atr_wilder, atr_wilder_pct, "wilder_ema_14"


def _calc_rsi(series: pd.Series, period: int = 14) -> float:
    """Wilder RSI — 지수이동평균 기반 (표준 구현)"""
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)

    first_avg_gain = gain.iloc[1:period + 1].mean()
    first_avg_loss = loss.iloc[1:period + 1].mean()

    avg_gains = [first_avg_gain]
    avg_losses = [first_avg_loss]
    for i in range(period + 1, len(series)):
        ag = (avg_gains[-1] * (period - 1) + gain.iloc[i]) / period
        al = (avg_losses[-1] * (period - 1) + loss.iloc[i]) / period
        avg_gains.append(ag)
        avg_losses.append(al)

    if not avg_gains or avg_losses[-1] == 0:
        return 50.0
    rs = avg_gains[-1] / avg_losses[-1] if avg_losses[-1] != 0 else 100
    rsi = 100 - (100 / (1 + rs))
    return round(float(rsi), 2) if pd.notna(rsi) else 50.0


def _calc_macd(series: pd.Series):
    ema12 = series.ewm(span=12, adjust=False).mean()
    ema26 = series.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    histogram = macd_line - signal_line
    return (
        round(float(macd_line.iloc[-1]), 2),
        round(float(signal_line.iloc[-1]), 2),
        round(float(histogram.iloc[-1]), 2),
    )


def analyze_technical(ticker_yf: str) -> dict:
    """
    종목의 기술적 지표 분석
    반환:
      ma5, ma20, ma60, ma120, rsi, macd, macd_signal, macd_hist,
      bb_upper, bb_lower, bb_position,
      vol_ratio, signals[], technical_score (0~100)
    """
    try:
        t = yf.Ticker(ticker_yf)
        hist = t.history(period="1y")
        if hist.empty or len(hist) < 20:
            return _empty_result()
    except Exception:
        return _empty_result()

    close = hist["Close"].dropna()
    volume = hist["Volume"].dropna()
    high = hist["High"].dropna()
    low = hist["Low"].dropna()

    if len(close) < 5:
        return _empty_result()

    price = float(close.iloc[-1])

    # Sprint 11 결함 3 후속 (2026-05-01): ATR_14d 직접 산출.
    # True Range = max(H-L, |H-prevC|, |L-prevC|), ATR = SMA(TR, 14).
    # _apply_volatility_adj 가 atr_14d_pct 우선 사용 — volatility_20d proxy 보다 정확.
    atr_14d = None
    atr_14d_pct = None
    if len(close) >= 15 and len(high) >= 15 and len(low) >= 15:
        prev_close = close.shift(1)
        tr = pd.concat([
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ], axis=1).max(axis=1).dropna()
        if len(tr) >= 14:
            atr_val = tr.rolling(14).mean().iloc[-1]
            if pd.notna(atr_val) and atr_val > 0:
                atr_14d = round(float(atr_val), 4)
                atr_14d_pct = round(atr_14d / price * 100, 2) if price > 0 else None

    def _safe_ma(n):
        if len(close) < n:
            return price
        val = close.rolling(n).mean().iloc[-1]
        return float(val) if pd.notna(val) else price

    ma5 = _safe_ma(5)
    ma20 = _safe_ma(20)
    ma60 = _safe_ma(60)
    ma120 = _safe_ma(120)

    rsi = _calc_rsi(close)
    macd_val, macd_sig, macd_hist = _calc_macd(close)

    bb_mid = close.rolling(20).mean()
    bb_std = close.rolling(20).std()
    bb_u_val = (bb_mid + 2 * bb_std).iloc[-1]
    bb_l_val = (bb_mid - 2 * bb_std).iloc[-1]
    bb_upper = float(bb_u_val) if pd.notna(bb_u_val) else price * 1.05
    bb_lower = float(bb_l_val) if pd.notna(bb_l_val) else price * 0.95
    bb_range = bb_upper - bb_lower
    bb_position = round((price - bb_lower) / bb_range * 100, 1) if bb_range > 0 else 50.0

    vol_avg20 = float(volume.rolling(20).mean().iloc[-1])
    vol_today = float(volume.iloc[-1])
    vol_ratio = round(vol_today / vol_avg20, 2) if vol_avg20 > 0 else 1.0

    price_change = (close.iloc[-1] - close.iloc[-2]) / close.iloc[-2] * 100 if len(close) >= 2 else 0
    vol_direction = "up" if price_change > 0.3 else "down" if price_change < -0.3 else "flat"

    trend_strength = 0
    if len(close) >= 20:
        ma20_slope = (ma20 - float(close.rolling(20).mean().iloc[-5])) / ma20 * 100 if ma20 > 0 else 0
        if ma20_slope > 1:
            trend_strength = 2
        elif ma20_slope > 0.3:
            trend_strength = 1
        elif ma20_slope < -1:
            trend_strength = -2
        elif ma20_slope < -0.3:
            trend_strength = -1

    signals = []
    score = 50

    if price > ma20 > ma60:
        signals.append("정배열")
        score += 10
    elif price < ma20 < ma60:
        signals.append("역배열")
        score -= 10

    if len(close) >= 20:
        prev_ma5 = close.rolling(5).mean().iloc[-2]
        prev_ma20 = close.rolling(20).mean().iloc[-2]
        if pd.notna(prev_ma5) and pd.notna(prev_ma20):
            if ma5 > ma20 and float(prev_ma5) <= float(prev_ma20):
                signals.append("골든크로스(5/20)")
                score += 15
            elif ma5 < ma20 and float(prev_ma5) >= float(prev_ma20):
                signals.append("데드크로스(5/20)")
                score -= 12

    if rsi <= 30:
        signals.append(f"RSI 과매도({rsi})")
        score += 15
    elif rsi <= 40:
        signals.append(f"RSI 저점접근({rsi})")
        score += 8
    elif rsi >= 70:
        signals.append(f"RSI 과매수({rsi})")
        score -= 10
    elif rsi >= 60:
        score += 3

    if macd_hist > 0 and macd_val > macd_sig:
        signals.append("MACD 매수시그널")
        score += 10
    elif macd_hist < 0 and macd_val < macd_sig:
        signals.append("MACD 매도시그널")
        score -= 8

    if bb_position <= 10:
        signals.append("볼린저 하단터치")
        score += 12
    elif bb_position >= 90:
        signals.append("볼린저 상단터치")
        score -= 5

    if vol_ratio >= 3.0:
        if vol_direction == "up":
            signals.append("거래폭증+상승")
            score += 10
        elif vol_direction == "down":
            signals.append("거래폭증+하락(투매)")
            score -= 8
        else:
            signals.append("거래폭증")
            score += 3
    elif vol_ratio >= 1.5:
        if vol_direction == "up":
            signals.append("거래증가+상승")
            score += 5
        else:
            signals.append("거래증가")
            score += 2

    if trend_strength >= 2:
        signals.append("강한 상승추세")
        score += 5
    elif trend_strength <= -2:
        signals.append("강한 하락추세")
        score -= 5

    score = max(0, min(100, score))

    return {
        "price": round(price, 0),
        "ma5": round(ma5, 0),
        "ma20": round(ma20, 0),
        "ma60": round(ma60, 0),
        "ma120": round(ma120, 0),
        "rsi": rsi,
        "macd": macd_val,
        "macd_signal": macd_sig,
        "macd_hist": macd_hist,
        "bb_upper": round(bb_upper, 0),
        "bb_lower": round(bb_lower, 0),
        "bb_position": bb_position,
        "vol_ratio": vol_ratio,
        "vol_direction": vol_direction,
        "trend_strength": trend_strength,
        "price_change_pct": round(float(price_change), 2),
        "atr_14d": atr_14d,
        "atr_14d_pct": atr_14d_pct,
        "signals": signals,
        "technical_score": score,
    }


def _empty_result() -> dict:
    return {
        "price": 0, "ma5": 0, "ma20": 0, "ma60": 0, "ma120": 0,
        "rsi": 50, "macd": 0, "macd_signal": 0, "macd_hist": 0,
        "bb_upper": 0, "bb_lower": 0, "bb_position": 50,
        "vol_ratio": 1.0, "atr_14d": None, "atr_14d_pct": None,
        "signals": [], "technical_score": 50,
    }
