"""test_tscv — Lopez de Prado Time-Series CV utilities 검증.

[[project_lopez_de_prado_tscv_2026_05_26]] 의 4 산식 단위 테스트.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from api.predictors.tscv import (
    combinatorial_purged_cv,
    meta_label,
    probability_of_backtest_overfitting,
    purged_kfold_split,
    triple_barrier_labels,
)


# ─── 1. purged_kfold_split ──────────────────────────────────


def test_purged_kfold_no_overlap():
    """train 과 test indices 겹침 0."""
    n = 100
    for train, test in purged_kfold_split(n, n_splits=5, embargo_pct=0.0):
        assert len(np.intersect1d(train, test)) == 0


def test_purged_kfold_embargo_buffer():
    """embargo 박은 후 test 직후 train 박음 X."""
    n = 100
    embargo_pct = 0.05
    embargo = int(n * embargo_pct)
    splits = list(purged_kfold_split(n, n_splits=5, embargo_pct=embargo_pct))
    # 첫 fold (k=0): test = [0, 20), train 시작점 = 20 + 5 = 25
    train_0, test_0 = splits[0]
    test_end_0 = test_0.max() + 1
    train_right_start = train_0[train_0 >= test_end_0].min() if (train_0 >= test_end_0).any() else None
    if train_right_start is not None:
        assert train_right_start >= test_end_0 + embargo


def test_purged_kfold_covers_all():
    """test indices union = 전체 (split 별 disjoint)."""
    n = 100
    all_test = np.concatenate([test for _, test in purged_kfold_split(n, n_splits=5, embargo_pct=0)])
    assert len(np.unique(all_test)) == n


def test_purged_kfold_invalid_args():
    with pytest.raises(ValueError):
        list(purged_kfold_split(100, n_splits=1))
    with pytest.raises(ValueError):
        list(purged_kfold_split(100, n_splits=5, embargo_pct=0.5))


# ─── 2. combinatorial_purged_cv ─────────────────────────────


def test_cpcv_path_count():
    """C(n_splits, n_test_splits) paths 생성."""
    paths = list(combinatorial_purged_cv(n_samples=120, n_splits=6, n_test_splits=2, embargo_pct=0.0))
    assert len(paths) == math.comb(6, 2)  # C(6, 2) = 15


def test_cpcv_disjoint_train_test():
    """각 path 의 train 박은 모든 test fold 와 disjoint."""
    for train, test_list in combinatorial_purged_cv(120, n_splits=6, n_test_splits=2, embargo_pct=0):
        for test in test_list:
            assert len(np.intersect1d(train, test)) == 0


def test_cpcv_invalid_args():
    with pytest.raises(ValueError):
        list(combinatorial_purged_cv(100, n_splits=3, n_test_splits=3))


# ─── 3. triple_barrier_labels ───────────────────────────────


def _synthetic_uptrend(n=100, drift=0.01, vol=0.01, seed=42):
    rng = np.random.RandomState(seed)
    rets = rng.normal(drift, vol, n)
    prices = 100 * np.exp(np.cumsum(rets))
    return pd.Series(prices, index=pd.date_range("2025-01-01", periods=n, freq="B"))


def test_triple_barrier_uptrend_skews_positive():
    """drift > 0 인 series 에서 label +1 박은 비율 > label -1."""
    prices = _synthetic_uptrend(n=100, drift=0.005, vol=0.005)
    df = triple_barrier_labels(prices, pt_multiplier=2.0, sl_multiplier=1.0, vertical_barrier_days=5)
    counts = df["label"].dropna().value_counts()
    assert counts.get(1, 0) >= counts.get(-1, 0), f"counts={counts.to_dict()}"


def test_triple_barrier_columns():
    prices = _synthetic_uptrend(n=80)
    df = triple_barrier_labels(prices, vertical_barrier_days=5)
    assert set(df.columns) == {"label", "exit_idx", "exit_price", "ret"}


def test_triple_barrier_too_short():
    short = pd.Series([100.0, 101.0, 102.0])
    with pytest.raises(ValueError):
        triple_barrier_labels(short, vertical_barrier_days=5, atr_lookback=14)


# ─── 4. meta_label ──────────────────────────────────────────


def test_meta_label_positive_pnl():
    """signal 박은 후 같은 방향 return 박은 trade 박음 = 1."""
    idx = pd.date_range("2025-01-01", periods=5, freq="D")
    signals = pd.Series([1, 1, -1, -1, 0], index=idx)
    returns = pd.Series([0.02, -0.01, -0.03, 0.01, 0.0], index=idx)
    meta = meta_label(signals, returns, min_return=0.0)
    # signal×ret = [+0.02, -0.01, +0.03, -0.01, 0] → take = [1, 0, 1, 0, 0]
    assert meta.tolist() == [1, 0, 1, 0, 0]


# ─── 5. PBO ─────────────────────────────────────────────────


def test_pbo_range():
    """PBO ∈ {0, 1} (quick proxy version)."""
    is_sharpes = np.array([1.5, 1.2, 0.8, 0.5, 0.3])
    os_sharpes = np.array([0.1, 0.5, 0.8, 1.0, 1.2])  # IS best 가 OS worst
    pbo = probability_of_backtest_overfitting(is_sharpes, os_sharpes)
    assert pbo == 1.0  # IS best 의 OS rank=0 < median=2.5 → overfit
