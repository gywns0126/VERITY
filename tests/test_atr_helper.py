"""ATR 헬퍼 함수 단위 테스트 — Phase 0 P-01/P-07."""
from __future__ import annotations

import gzip
import numpy as np
import pandas as pd
import pytest

from api.analyzers.technical import (
    ATR_MIGRATION_LOG_MAX_SIZE_BYTES,
    compute_atr_14d,
    compute_true_range,
    _rotate_migration_log_if_needed,
)


def _ohlc(n=30, base=10000.0, vol=0.02, seed=42):
    np.random.seed(seed)
    closes = [base]
    for _ in range(n - 1):
        closes.append(closes[-1] * (1 + np.random.normal(0, vol)))
    closes = pd.Series(closes)
    highs = closes * (1 + np.abs(np.random.normal(0, 0.01, n)))
    lows = closes * (1 - np.abs(np.random.normal(0, 0.01, n)))
    return highs, lows, closes


class TestComputeTrueRange:
    def test_standard_definition(self):
        close = pd.Series([100, 102, 99, 105, 103])
        high = pd.Series([101, 103, 100, 106, 104])
        low = pd.Series([99, 101, 98, 104, 102])
        tr = compute_true_range(high, low, close)
        # row 0 (prev_close NaN): max(H-L=2, NaN, NaN) = 2 (skipna)
        assert tr.iloc[0] == 2
        # row 1: H=103, L=101, prev_close=100 → max(2, |103-100|=3, |101-100|=1) = 3
        assert tr.iloc[1] == 3
        # row 2: H=100, L=98, prev_close=102 → max(2, 2, 4) = 4
        assert tr.iloc[2] == 4


class TestComputeAtr14d:
    def test_wilder_method(self):
        h, l, c = _ohlc(30)
        atr, pct, m = compute_atr_14d(h, l, c, method="wilder_ema_14")
        assert atr is not None
        assert atr > 0
        assert pct is not None
        assert 0 < pct < 50
        assert m == "wilder_ema_14"

    def test_sma_method(self):
        h, l, c = _ohlc(30)
        atr, pct, m = compute_atr_14d(h, l, c, method="sma_14")
        assert atr is not None
        assert m == "sma_14"

    def test_wilder_vs_sma_finite_diff(self):
        h, l, c = _ohlc(30)
        atr_w, _, _ = compute_atr_14d(h, l, c, method="wilder_ema_14")
        atr_s, _, _ = compute_atr_14d(h, l, c, method="sma_14")
        diff_pct = abs(atr_w - atr_s) / atr_s * 100
        # 일반적 5~30%, 50% 초과면 산출법 자체 버그 의심
        assert diff_pct < 50

    def test_insufficient_data_returns_none(self):
        h, l, c = _ohlc(10)  # < ATR_MIN_PERIOD=20
        atr, pct, _ = compute_atr_14d(h, l, c)
        assert atr is None
        assert pct is None

    def test_unknown_method_raises(self):
        h, l, c = _ohlc(30)
        with pytest.raises(ValueError, match="Unknown ATR method"):
            compute_atr_14d(h, l, c, method="invalid")

    def test_default_uses_env_method(self, monkeypatch):
        # method=None → ATR_METHOD 환경변수 (default wilder_ema_14)
        h, l, c = _ohlc(30)
        atr, _, m = compute_atr_14d(h, l, c, method=None)
        # default = wilder_ema_14 (config.py)
        assert m in ("wilder_ema_14", "sma_14")


class TestLogRotation:
    def test_no_rotation_below_threshold(self, tmp_path, monkeypatch):
        log_path = tmp_path / "log.jsonl"
        log_path.write_bytes(b"x" * 100)  # 100 bytes < 5MB
        monkeypatch.setattr(
            "api.analyzers.technical.ATR_MIGRATION_LOG_PATH", log_path
        )
        _rotate_migration_log_if_needed()
        assert log_path.exists()  # 그대로

    def test_rotation_at_5mb(self, tmp_path, monkeypatch):
        log_path = tmp_path / "log.jsonl"
        log_path.write_bytes(b"x" * (ATR_MIGRATION_LOG_MAX_SIZE_BYTES + 1024))
        monkeypatch.setattr(
            "api.analyzers.technical.ATR_MIGRATION_LOG_PATH", log_path
        )
        _rotate_migration_log_if_needed()
        # 원본 삭제됨
        assert not log_path.exists()
        # archive 디렉토리 생성 + .jsonl.gz 1개
        archive_dir = log_path.parent / "archive"
        assert archive_dir.exists()
        archives = list(archive_dir.glob("atr_migration_log_*.jsonl.gz"))
        assert len(archives) == 1

    def test_rotation_handles_missing_file(self, tmp_path, monkeypatch):
        # 파일이 없으면 noop
        log_path = tmp_path / "absent.jsonl"
        monkeypatch.setattr(
            "api.analyzers.technical.ATR_MIGRATION_LOG_PATH", log_path
        )
        _rotate_migration_log_if_needed()
        assert not log_path.exists()
