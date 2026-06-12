"""fdf — Fractionally Differentiated Features (FFD, fixed-width window).

학술 source:
  - López de Prado (2018) "Advances in Financial Machine Learning" Wiley, Ch 5
    "Fractionally Differentiated Features"

PM 사전등록: [[project_b4_sprint_tools_2026_05_27]] (2026-05-27).
B4 sprint 진입 (2026-06-12) 구현.

WHY: 표준 1차 차분 (returns) = stationarity 확보하나 memory 전부 손실.
가격 level = memory 보존하나 비정상 (non-stationary). Fractional
differentiation d ∈ (0, 1) = 둘 사이 — stationarity + memory 동시.

산식 (AFML Ch 5.4 — binomial 급수 가중치):
    w_0 = 1
    w_k = -w_{k-1} × (d - k + 1) / k
    X̃_t = Σ_k w_k · X_{t-k}

FFD (fixed-width window, AFML 5.5): |w_k| < threshold 인 꼬리 가중치 절단
→ 고정 폭 window. expanding window 방식의 음의 drift 결함 회피 (AFML 정공법).

ADF 검정: statsmodels 가용 시 수행, 부재 시 검정 skip + 명시 반환
(graceful — 모듈 자체는 무의존 numpy only).

RULE 7 정합: infrastructure (feature engineering 도구, 산식 자체 X).
"""
from __future__ import annotations

from typing import Dict, Optional

import numpy as np
import pandas as pd

__all__ = ["get_ffd_weights", "frac_diff_ffd", "min_ffd_d"]


def get_ffd_weights(d: float, threshold: float = 1e-5, max_width: int = 10_000) -> np.ndarray:
    """FFD 가중치 — |w_k| >= threshold 인 항만 (AFML Ch 5.5 getWeights_FFD).

    w_0 = 1; w_k = -w_{k-1} × (d - k + 1) / k

    Args:
        d: 차분 차수 ∈ [0, 1]. d=0 → 항등 (w=[1]), d=1 → 1차 차분 (w=[1, -1]).
        threshold: 가중치 절단 임계 (default 1e-5, AFML 예제 정합).
        max_width: window 폭 상한 (무한 루프 가드).

    Returns:
        np.ndarray — [w_0, w_1, ..., w_{K-1}] (시간 역순으로 적용: w_k → X_{t-k}).
    """
    if not 0.0 <= d <= 1.0:
        raise ValueError(f"d must be in [0, 1], got {d}")
    weights = [1.0]
    k = 1
    while k < max_width:
        w = -weights[-1] * (d - k + 1) / k
        if abs(w) < threshold:
            break
        weights.append(w)
        k += 1
    return np.array(weights)


def frac_diff_ffd(series: pd.Series, d: float, threshold: float = 1e-5) -> pd.Series:
    """고정폭 window fractional differentiation (AFML Ch 5.5 fracDiff_FFD).

    Args:
        series: 가격 level (index 보존). NaN 은 forward-fill 하지 않음 — 호출자 책임.
        d: 차분 차수 ∈ [0, 1].
        threshold: 가중치 절단 임계.

    Returns:
        pd.Series — 앞 (window-1) 개는 NaN (가중치 폭 미충족 구간).
    """
    if not isinstance(series, pd.Series):
        raise TypeError("series must be pd.Series")
    w = get_ffd_weights(d, threshold)
    width = len(w)
    values = series.to_numpy(dtype=float)
    n = len(values)
    out = np.full(n, np.nan)
    if n >= width:
        # w[0]·X_t + w[1]·X_{t-1} + ... = correlate with reversed weights
        out[width - 1:] = np.convolve(values, w, mode="valid")
    return pd.Series(out, index=series.index, name=f"ffd_{d:g}")


def _adf_pvalue(values: np.ndarray) -> Optional[float]:
    """ADF p-value — statsmodels 가용 시. 부재 시 None (graceful)."""
    try:
        from statsmodels.tsa.stattools import adfuller
    except ImportError:
        return None
    clean = values[np.isfinite(values)]
    if len(clean) < 30:
        return None
    try:
        return float(adfuller(clean, autolag="AIC")[1])
    except Exception:
        return None


def min_ffd_d(
    series: pd.Series,
    d_grid: Optional[np.ndarray] = None,
    adf_alpha: float = 0.05,
    threshold: float = 1e-5,
) -> Dict:
    """stationarity (ADF) 통과하는 최소 d 탐색 (AFML Ch 5 plotMinFFD 정공법).

    d 낮을수록 memory 보존 ↑ — ADF 통과하는 최소 d 가 최적 feature.

    Returns:
        {
          "min_d": float|None,        # ADF 통과 최소 d (statsmodels 부재 시 None)
          "adf_available": bool,
          "grid": [{"d", "adf_pvalue", "corr_with_price", "n_valid"}, ...],
        }

    corr_with_price = 변환 결과와 원 가격의 상관 (memory 보존 정도 지표,
    ADF 부재 환경에서도 산출).
    """
    if d_grid is None:
        d_grid = np.arange(0.0, 1.01, 0.05)

    price = series.to_numpy(dtype=float)
    grid_out = []
    min_d = None
    adf_available = _adf_pvalue(np.diff(price)) is not None  # probe

    for d in d_grid:
        transformed = frac_diff_ffd(series, float(d), threshold)
        tv = transformed.to_numpy()
        mask = np.isfinite(tv) & np.isfinite(price)
        n_valid = int(mask.sum())
        corr = float(np.corrcoef(tv[mask], price[mask])[0, 1]) if n_valid >= 3 else None
        pval = _adf_pvalue(tv) if adf_available else None
        grid_out.append({
            "d": round(float(d), 2),
            "adf_pvalue": round(pval, 4) if pval is not None else None,
            "corr_with_price": round(corr, 4) if corr is not None else None,
            "n_valid": n_valid,
        })
        if min_d is None and pval is not None and pval < adf_alpha:
            min_d = round(float(d), 2)

    return {"min_d": min_d, "adf_available": adf_available, "grid": grid_out}
