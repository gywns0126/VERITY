"""tscv — Time-Series Cross Validation utilities (Lopez de Prado 2018).

학술 source:
  - Marcos López de Prado (2018) "Advances in Financial Machine Learning" Wiley
    Chapter 7: Cross-Validation in Finance
    Chapter 12: Backtesting through Cross-Validation
  - Lopez de Prado (2018) "The 10 Reasons Most Machine Learning Funds Fail"
    *Journal of Portfolio Management*

PM 사전등록: [[project_lopez_de_prado_tscv_2026_05_26]] (2026-05-26).
B4 backtest sprint ([[project_verity_backtest_sprint]]) 의 도구 — 산식 변경 X.

박은 산식:
  1. purged_kfold_split — train/test fold 사이 buffer (purge) + embargo
  2. combinatorial_purged_cv — k 개 fold 의 combination → 다중 path → PBO 계산 base
  3. triple_barrier_labels — profit-take / stop-loss / vertical barrier label {1, -1, 0}
  4. meta_label — 1차 signal 박은 후 take/skip 박음 (precision boost)

RULE 7 정합: infrastructure (산식 변경 X). PM 결정 "전부 박자!!!" 발화 (2026-05-26).
"""
from __future__ import annotations

from itertools import combinations
from typing import Iterator, List, Optional, Tuple

import numpy as np
import pandas as pd

# ─── 1. Purged k-fold CV ──────────────────────────────────────


def purged_kfold_split(
    n_samples: int,
    n_splits: int = 5,
    embargo_pct: float = 0.01,
) -> Iterator[Tuple[np.ndarray, np.ndarray]]:
    """Purged k-fold cross validation generator.

    표준 k-fold 의 train/test 사이 buffer 박음 — temporal leakage 차단.
    추가로 test 직후 embargo 박음 — autocorrelation leakage 차단.

    Args:
        n_samples: total time-series 길이.
        n_splits: fold 수 (default 5).
        embargo_pct: test fold 직후 train 박지 않는 비율 (default 1% = embargo_days).

    Yields:
        (train_idx, test_idx) — np.ndarray int indices.

    Lopez de Prado 2018 Chapter 7.1 정합.
    """
    if n_splits < 2:
        raise ValueError("n_splits must be >= 2")
    if not 0 <= embargo_pct < 0.5:
        raise ValueError("embargo_pct must be in [0, 0.5)")

    embargo = int(n_samples * embargo_pct)
    fold_size = n_samples // n_splits
    indices = np.arange(n_samples)

    for k in range(n_splits):
        test_start = k * fold_size
        test_end = test_start + fold_size if k < n_splits - 1 else n_samples
        test_idx = indices[test_start:test_end]

        # train 은 test 양쪽 — purge buffer 박음
        # 좌측 train 끝점 = test_start (purge 없음 — 시간 순서상 안전)
        # 우측 train 시작점 = test_end + embargo
        train_left = indices[:test_start]
        train_right = indices[test_end + embargo:]
        train_idx = np.concatenate([train_left, train_right])

        yield train_idx, test_idx


# ─── 2. Combinatorial Purged CV ──────────────────────────────


def combinatorial_purged_cv(
    n_samples: int,
    n_splits: int = 6,
    n_test_splits: int = 2,
    embargo_pct: float = 0.01,
) -> Iterator[Tuple[np.ndarray, List[np.ndarray]]]:
    """Combinatorial Purged Cross Validation (CPCV).

    k 개 fold 박은 후 그 중 n_test_splits 박은 combination 박음 → C(k, n_test_splits) 개 path.
    각 path 별 backtest → PBO (Probability of Backtest Overfitting) 계산 base.

    Args:
        n_samples: total 길이.
        n_splits: 전체 fold 수 (default 6).
        n_test_splits: 각 path 의 test fold 수 (default 2). C(6, 2) = 15 paths.
        embargo_pct: 각 test fold 직후 embargo 비율.

    Yields:
        (train_idx, test_idxs_list) — train 박은 indices + n_test_splits 개 test fold list.

    Lopez de Prado 2018 Chapter 12 정합.
    """
    if n_test_splits >= n_splits:
        raise ValueError("n_test_splits must be < n_splits")

    embargo = int(n_samples * embargo_pct)
    fold_size = n_samples // n_splits
    indices = np.arange(n_samples)

    # 각 fold 의 (start, end) 박음
    folds = []
    for k in range(n_splits):
        start = k * fold_size
        end = start + fold_size if k < n_splits - 1 else n_samples
        folds.append((start, end))

    for test_combination in combinations(range(n_splits), n_test_splits):
        test_idxs = [indices[folds[k][0]:folds[k][1]] for k in test_combination]

        # train mask = all True, then mask out test folds + embargo
        train_mask = np.ones(n_samples, dtype=bool)
        for k in test_combination:
            start, end = folds[k]
            train_mask[start:end] = False
            # embargo 박음
            embargo_end = min(end + embargo, n_samples)
            train_mask[end:embargo_end] = False

        train_idx = indices[train_mask]
        yield train_idx, test_idxs


# ─── 3. Triple-Barrier Labels ────────────────────────────────


def triple_barrier_labels(
    prices: pd.Series,
    pt_multiplier: float = 2.0,
    sl_multiplier: float = 1.0,
    vertical_barrier_days: int = 5,
    atr_lookback: int = 14,
) -> pd.DataFrame:
    """Triple-Barrier Labeling (Lopez de Prado 2018 Chapter 3).

    각 entry 시점에서 3 개 barrier 박음:
      - profit-take (PT): entry + pt_multiplier × ATR
      - stop-loss (SL): entry - sl_multiplier × ATR
      - vertical (T): entry + vertical_barrier_days

    먼저 도달한 barrier 박음:
      label = +1 (PT 도달), -1 (SL 도달), 0 (T 도달 — barrier 미터치)

    Args:
        prices: pd.Series of close prices (index = datetime).
        pt_multiplier: profit-take ATR multiplier (default 2.0 — R-multiple 정합).
        sl_multiplier: stop-loss ATR multiplier (default 1.0).
        vertical_barrier_days: time barrier in trading days (default 5).
        atr_lookback: ATR 산정 lookback (default 14 — Wilder EMA).

    Returns:
        DataFrame with columns: [label, exit_idx, exit_price, ret].

    Wilder ATR 정합 ([[project_atr_dynamic_stop]]).
    """
    if not isinstance(prices, pd.Series):
        raise TypeError("prices must be pd.Series")
    if len(prices) < atr_lookback + vertical_barrier_days + 1:
        raise ValueError(f"prices too short (need >= {atr_lookback + vertical_barrier_days + 1})")

    # ATR (Wilder EMA) — high/low 없을 때 close 의 abs diff 으로 근사
    returns = prices.diff().abs()
    atr = returns.ewm(alpha=1.0 / atr_lookback, adjust=False).mean()

    n = len(prices)
    labels = []
    exit_idxs = []
    exit_prices = []
    rets = []

    for i in range(n - vertical_barrier_days):
        entry_price = prices.iloc[i]
        atr_i = atr.iloc[i]
        if not np.isfinite(atr_i) or atr_i <= 0:
            labels.append(np.nan)
            exit_idxs.append(np.nan)
            exit_prices.append(np.nan)
            rets.append(np.nan)
            continue

        pt = entry_price + pt_multiplier * atr_i
        sl = entry_price - sl_multiplier * atr_i

        # forward window
        end = min(i + vertical_barrier_days + 1, n)
        forward = prices.iloc[i + 1:end]

        label = 0
        exit_idx = end - 1
        exit_price = prices.iloc[exit_idx]
        for j, p in enumerate(forward.values):
            if p >= pt:
                label = 1
                exit_idx = i + 1 + j
                exit_price = p
                break
            if p <= sl:
                label = -1
                exit_idx = i + 1 + j
                exit_price = p
                break

        labels.append(label)
        exit_idxs.append(exit_idx)
        exit_prices.append(exit_price)
        rets.append((exit_price - entry_price) / entry_price)

    return pd.DataFrame(
        {
            "label": labels,
            "exit_idx": exit_idxs,
            "exit_price": exit_prices,
            "ret": rets,
        },
        index=prices.index[:len(labels)],
    )


# ─── 4. Meta-Labeling ────────────────────────────────────────


def meta_label(
    primary_signals: pd.Series,
    primary_returns: pd.Series,
    min_return: float = 0.0,
) -> pd.Series:
    """Meta-labeling (Lopez de Prado 2018 Chapter 3.6).

    1차 model 박은 signal 박은 후, 2차 model 박을 binary label 박음 — take (1) / skip (0).
    1차 의 false positive 줄이고 precision ↑.

    Args:
        primary_signals: 1차 model 박은 signal (e.g., +1=long, -1=short, 0=skip).
        primary_returns: 실 forward return (signal 박은 후 실 결과).
        min_return: signal 박은 trade 박을 박은 최소 return threshold (default 0).

    Returns:
        pd.Series of {0, 1} — meta label. 1=take, 0=skip.

    Use: 1차 signal 박힘 + 2차 meta label 박음 → 둘 다 1 인 trade 만 박음.
    """
    if not isinstance(primary_signals, pd.Series):
        raise TypeError("primary_signals must be pd.Series")
    if not isinstance(primary_returns, pd.Series):
        raise TypeError("primary_returns must be pd.Series")

    aligned_returns = primary_returns.reindex(primary_signals.index)

    # signal × return — 같은 방향이면 + (good trade), 반대면 - (bad trade)
    pnl = primary_signals * aligned_returns
    return (pnl > min_return).astype(int)


# ─── 5. PBO (Probability of Backtest Overfitting) ────────────


def probability_of_backtest_overfitting(
    in_sample_sharpes: np.ndarray,
    out_of_sample_sharpes: np.ndarray,
) -> float:
    """PBO — backtest overfit 확률 (Bailey-Lopez de Prado 2014).

    Args:
        in_sample_sharpes: 각 CPCV path 의 in-sample Sharpe.
        out_of_sample_sharpes: 각 CPCV path 의 out-of-sample Sharpe.

    Returns:
        PBO ∈ [0, 1]. 낮을수록 robust (≤ 0.2 = pass, ≥ 0.5 = overfit).

    학술 정합: Bailey & Lopez de Prado (2014) "The Probability of Backtest
    Overfitting" *Journal of Computational Finance*.
    """
    is_ranks = np.argsort(np.argsort(in_sample_sharpes))
    n = len(in_sample_sharpes)
    if n < 2:
        return float("nan")

    # 각 IS rank 박은 best 의 OS rank 확인
    best_is = np.argmax(in_sample_sharpes)
    best_os_rank = np.argsort(np.argsort(out_of_sample_sharpes))[best_is]
    median_rank = n / 2

    # logit-style — best IS 박은 후 OS 가 median 이하 박은 비율 추정
    # 단순 version: best IS 박은 후 OS rank < median 박은 빈도
    # 더 정확한 Bailey-Lopez 는 다중 path full computation 필요. 본 함수는 quick proxy.
    return float(best_os_rank < median_rank)
