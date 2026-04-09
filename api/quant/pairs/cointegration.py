"""
공적분 검정 모듈 — 통계적 차익거래의 수학적 기반

학술 근거:
  - Engle & Granger (1987): 두 비정상 시계열이 선형결합 시 정상(stationary)이면 공적분 관계
  - Johansen (1988): 다변량 공적분 검정
  - Vidyamurthy (2004): Pairs Trading — 공적분 기반 실전 전략

구현:
  1. Engle-Granger 2단계 검정 (OLS 잔차 → ADF 검정)
  2. 스프레드 반감기 추정 (Ornstein-Uhlenbeck)
  3. 상관관계 + 공적분 이중 필터
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


def adf_test(series: np.ndarray, max_lag: int = 10) -> Dict[str, Any]:
    """
    Augmented Dickey-Fuller 검정 (순수 구현, statsmodels 불필요).

    H0: 단위근 존재 (비정상)
    H1: 정상 시계열

    반환: test_statistic, p_value_approx, is_stationary
    """
    n = len(series)
    if n < 20:
        return {"test_statistic": 0, "p_value_approx": 1.0, "is_stationary": False}

    y = np.array(series, dtype=float)
    dy = np.diff(y)

    best_lag = min(max_lag, int(np.floor(n ** (1/3))))

    y_lag = y[best_lag:-1]
    dy_dep = dy[best_lag:]
    min_len = min(len(y_lag), len(dy_dep))
    y_lag = y_lag[:min_len]
    dy_dep = dy_dep[:min_len]

    X_parts = [y_lag.reshape(-1, 1), np.ones((min_len, 1))]
    for lag in range(1, best_lag + 1):
        if lag < len(dy):
            lagged = dy[best_lag - lag:best_lag - lag + min_len]
            if len(lagged) == min_len:
                X_parts.append(lagged.reshape(-1, 1))

    X = np.hstack(X_parts)

    try:
        beta = np.linalg.lstsq(X, dy_dep, rcond=None)[0]
        residuals = dy_dep - X @ beta
        se = np.sqrt(np.sum(residuals**2) / (len(residuals) - len(beta)))

        xtx_inv = np.linalg.inv(X.T @ X)
        se_beta = se * np.sqrt(np.diag(xtx_inv))

        gamma = beta[0]
        t_stat = gamma / se_beta[0] if se_beta[0] > 0 else 0

        # MacKinnon 임계값 근사 (5% 유의수준)
        critical_1 = -3.43
        critical_5 = -2.86
        critical_10 = -2.57

        if t_stat < critical_1:
            p_approx = 0.005
        elif t_stat < critical_5:
            p_approx = 0.03
        elif t_stat < critical_10:
            p_approx = 0.07
        else:
            p_approx = min(0.5, 0.1 + (t_stat - critical_10) * 0.1)

        return {
            "test_statistic": round(float(t_stat), 4),
            "p_value_approx": round(float(p_approx), 4),
            "is_stationary": t_stat < critical_5,
            "critical_values": {"1%": critical_1, "5%": critical_5, "10%": critical_10},
            "lags_used": best_lag,
        }
    except (np.linalg.LinAlgError, ValueError):
        return {"test_statistic": 0, "p_value_approx": 1.0, "is_stationary": False}


def engle_granger_test(
    series_a: np.ndarray,
    series_b: np.ndarray,
) -> Dict[str, Any]:
    """
    Engle-Granger 2단계 공적분 검정.

    Step 1: OLS 회귀 (A = alpha + beta * B + epsilon)
    Step 2: 잔차에 ADF 검정 → 정상이면 공적분 관계

    반환: is_cointegrated, hedge_ratio, spread, adf_result, half_life
    """
    a = np.array(series_a, dtype=float)
    b = np.array(series_b, dtype=float)

    min_len = min(len(a), len(b))
    a = a[:min_len]
    b = b[:min_len]

    if min_len < 60:
        return {
            "is_cointegrated": False,
            "hedge_ratio": 0,
            "adf_result": {"test_statistic": 0, "p_value_approx": 1.0},
            "half_life": None,
            "reason": "데이터 부족 (최소 60일)",
        }

    nan_mask = ~(np.isnan(a) | np.isnan(b))
    a = a[nan_mask]
    b = b[nan_mask]

    if len(a) < 60:
        return {
            "is_cointegrated": False,
            "hedge_ratio": 0,
            "adf_result": {"test_statistic": 0, "p_value_approx": 1.0},
            "half_life": None,
            "reason": "유효 데이터 부족",
        }

    # Step 1: OLS
    X = np.column_stack([b, np.ones(len(b))])
    try:
        beta = np.linalg.lstsq(X, a, rcond=None)[0]
    except np.linalg.LinAlgError:
        return {
            "is_cointegrated": False,
            "hedge_ratio": 0,
            "adf_result": {"test_statistic": 0, "p_value_approx": 1.0},
            "half_life": None,
            "reason": "OLS 실패",
        }

    hedge_ratio = float(beta[0])
    intercept = float(beta[1])
    spread = a - hedge_ratio * b - intercept

    # Step 2: ADF on spread
    adf_result = adf_test(spread)

    # Half-life (OU process)
    half_life = _estimate_half_life(spread)

    # 상관관계
    correlation = float(np.corrcoef(a, b)[0, 1]) if len(a) > 2 else 0

    return {
        "is_cointegrated": adf_result["is_stationary"],
        "hedge_ratio": round(hedge_ratio, 4),
        "intercept": round(intercept, 4),
        "correlation": round(correlation, 4),
        "adf_result": adf_result,
        "half_life": half_life,
        "spread_stats": {
            "mean": round(float(np.mean(spread)), 4),
            "std": round(float(np.std(spread)), 4),
            "current_zscore": round(float((spread[-1] - np.mean(spread)) / np.std(spread)), 4) if np.std(spread) > 0 else 0,
        },
    }


def _estimate_half_life(spread: np.ndarray) -> Optional[float]:
    """
    Ornstein-Uhlenbeck 프로세스 반감기 추정.
    dS = theta * (mu - S) * dt
    반감기 = -ln(2) / ln(1 + theta)

    반환: 영업일 단위 반감기 (None if 추정 불가)
    """
    if len(spread) < 20:
        return None

    y = spread[1:]
    y_lag = spread[:-1]

    X = np.column_stack([y_lag, np.ones(len(y_lag))])
    try:
        beta = np.linalg.lstsq(X, y, rcond=None)[0]
    except np.linalg.LinAlgError:
        return None

    phi = beta[0]
    if phi >= 1 or phi <= 0:
        return None

    half_life = -np.log(2) / np.log(phi)
    return round(float(half_life), 1) if 1 < half_life < 500 else None


def compute_spread_zscore(
    series_a: np.ndarray,
    series_b: np.ndarray,
    hedge_ratio: float,
    intercept: float = 0,
    lookback: int = 60,
) -> Dict[str, Any]:
    """
    현재 스프레드의 Z-Score 계산.

    반환: zscore, spread, mean, std, signal
    """
    a = np.array(series_a, dtype=float)
    b = np.array(series_b, dtype=float)
    min_len = min(len(a), len(b))
    a = a[:min_len]
    b = b[:min_len]

    spread = a - hedge_ratio * b - intercept
    window = spread[-lookback:] if len(spread) >= lookback else spread

    mean = float(np.mean(window))
    std = float(np.std(window))

    if std <= 0:
        return {"zscore": 0, "signal": "NEUTRAL", "spread": float(spread[-1])}

    current = float(spread[-1])
    zscore = (current - mean) / std

    if zscore <= -2.0:
        signal = "STRONG_BUY_SPREAD"
        label = "스프레드 극단 축소 — 롱 A / 숏 B"
    elif zscore <= -1.0:
        signal = "BUY_SPREAD"
        label = "스프레드 하방 이탈"
    elif zscore >= 2.0:
        signal = "STRONG_SELL_SPREAD"
        label = "스프레드 극단 확대 — 숏 A / 롱 B"
    elif zscore >= 1.0:
        signal = "SELL_SPREAD"
        label = "스프레드 상방 이탈"
    else:
        signal = "NEUTRAL"
        label = "스프레드 정상 범위"

    return {
        "zscore": round(zscore, 3),
        "spread": round(current, 4),
        "mean": round(mean, 4),
        "std": round(std, 4),
        "signal": signal,
        "label": label,
    }
