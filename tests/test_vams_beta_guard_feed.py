import numpy as np
import pandas as pd

from api.predictors.backtester import _beta_from_returns
from api.vams.engine import _guard_beta


def test_beta_matches_linear_market_exposure():
    idx = pd.date_range("2026-01-01", periods=100)
    market = pd.Series(np.linspace(-0.02, 0.02, 100), index=idx)
    stock = market * 1.25
    assert _beta_from_returns(stock, market) == 1.25


def test_beta_requires_enough_aligned_observations():
    idx = pd.date_range("2026-01-01", periods=59)
    values = pd.Series(np.linspace(-0.02, 0.02, 59), index=idx)
    assert _beta_from_returns(values, values) is None


def test_guard_reads_backtest_beta_without_top_level_score_input():
    assert _guard_beta({"backtest": {"beta": 1.17}}) == 1.17
    assert _guard_beta({"beta": None, "backtest": {"beta": 0.82}}) == 0.82
