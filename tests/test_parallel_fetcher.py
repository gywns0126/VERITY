"""parallel_fetcher 단위 테스트 — 가드 + 캐시 (외부 호출 mock)."""
from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pandas as pd
import pytest

from api.collectors import parallel_fetcher as pf


# ─────────────────────────────────────────────────────────────────────
# KR max_workers 가드 (결정 8)
# ─────────────────────────────────────────────────────────────────────

class TestKrMaxWorkersGuard:
    def test_at_30_ok(self):
        pf._enforce_kr_workers(30)  # no raise

    def test_at_31_raises(self):
        with pytest.raises(ValueError, match="P50 hung risk"):
            pf._enforce_kr_workers(31)

    def test_at_50_raises(self):
        with pytest.raises(ValueError, match="cannot exceed 30"):
            pf._enforce_kr_workers(50)

    def test_fetch_kr_ohlcv_rejects_50w(self):
        with pytest.raises(ValueError):
            pf.fetch_kr_ohlcv_parallel(["005930"], max_workers=50)


# ─────────────────────────────────────────────────────────────────────
# OHLCV 캐시 (결정 8 — 같은 영업일 1회 호출)
# ─────────────────────────────────────────────────────────────────────

class TestOhlcvCache:
    def test_cache_path_structure(self, monkeypatch, tmp_path):
        monkeypatch.setattr(pf, "K2_OHLCV_CACHE_DIR", tmp_path / "k2")
        p = pf._cache_path("005930", "20260430")
        assert "20260430" in str(p)
        assert "005930" in str(p)
        assert str(p).endswith(".pkl")

    def test_cache_miss_returns_none(self, monkeypatch, tmp_path):
        monkeypatch.setattr(pf, "K2_OHLCV_CACHE_DIR", tmp_path / "k2")
        assert pf._read_cache("005930", "20260430") is None

    def test_cache_write_then_read(self, monkeypatch, tmp_path):
        monkeypatch.setattr(pf, "K2_OHLCV_CACHE_DIR", tmp_path / "k2")
        df = pd.DataFrame({"close": list(range(60))})
        pf._write_cache("005930", "20260430", df)
        cached = pf._read_cache("005930", "20260430")
        assert cached is not None
        assert len(cached) == 60

    def test_corrupted_cache_graceful(self, monkeypatch, tmp_path):
        monkeypatch.setattr(pf, "K2_OHLCV_CACHE_DIR", tmp_path / "k2")
        bad = pf._cache_path("005930", "20260430")
        bad.parent.mkdir(parents=True, exist_ok=True)
        bad.write_text("not a pickle file")
        # 손상된 캐시는 None 반환 + 자동 삭제
        result = pf._read_cache("005930", "20260430")
        assert result is None


# ─────────────────────────────────────────────────────────────────────
# Adaptive degradation — 첫 호출 30s 초과 → P20
# ─────────────────────────────────────────────────────────────────────

class TestAdaptiveFallback:
    def test_no_fallback_for_max_20(self, monkeypatch, tmp_path):
        # max_workers=20 부터는 fallback 안 함 (이미 20 이하)
        monkeypatch.setattr(pf, "K2_OHLCV_CACHE_DIR", tmp_path / "k2")
        df = pd.DataFrame({"close": list(range(60))})

        def fast_fetch(t, s, e, b):
            return t, df, False

        monkeypatch.setattr(pf, "_kr_fetch_one_ohlcv", fast_fetch)
        result = pf.fetch_kr_ohlcv_parallel(["005930", "000660"], max_workers=20)
        assert result["fallback_triggered"] is False
        assert result["workers_used"] == 20

    def test_fast_call_no_fallback(self, monkeypatch, tmp_path):
        monkeypatch.setattr(pf, "K2_OHLCV_CACHE_DIR", tmp_path / "k2")
        df = pd.DataFrame({"close": list(range(60))})

        def fast_fetch(t, s, e, b):
            return t, df, False

        monkeypatch.setattr(pf, "_kr_fetch_one_ohlcv", fast_fetch)
        result = pf.fetch_kr_ohlcv_parallel(["005930", "000660"], max_workers=30)
        assert result["fallback_triggered"] is False
        assert result["workers_used"] == 30
        assert result["success_count"] == 2


# ─────────────────────────────────────────────────────────────────────
# Fail rate alert (결정 8)
# ─────────────────────────────────────────────────────────────────────

class TestFailRateAlert:
    def test_fail_rate_below_1pct_no_alert(self, monkeypatch, tmp_path):
        monkeypatch.setattr(pf, "K2_OHLCV_CACHE_DIR", tmp_path / "k2")
        df = pd.DataFrame({"close": list(range(60))})

        def all_ok(t, s, e, b):
            return t, df, False

        monkeypatch.setattr(pf, "_kr_fetch_one_ohlcv", all_ok)
        alerts = []
        result = pf.fetch_kr_ohlcv_parallel(
            [f"00000{i}" for i in range(20)],
            max_workers=10,
            on_alert=lambda lvl, p: alerts.append((lvl, p)),
        )
        assert result["fail_rate_alert_fired"] is False
        assert all(a[0] != "CRITICAL" for a in alerts)

    def test_fail_rate_over_1pct_fires_alert(self, monkeypatch, tmp_path):
        monkeypatch.setattr(pf, "K2_OHLCV_CACHE_DIR", tmp_path / "k2")
        # 5/20 = 25% fail
        df = pd.DataFrame({"close": list(range(60))})

        def mixed(t, s, e, b):
            if t.endswith("5") or t.endswith("0"):  # ~5/20 fail
                return t, None, False
            return t, df, False

        monkeypatch.setattr(pf, "_kr_fetch_one_ohlcv", mixed)
        alerts = []
        result = pf.fetch_kr_ohlcv_parallel(
            [f"00000{i}" for i in range(20)],
            max_workers=10,
            on_alert=lambda lvl, p: alerts.append((lvl, p)),
        )
        assert result["fail_rate"] > 0.01
        assert result["fail_rate_alert_fired"] is True
        assert any(a[0] == "CRITICAL" for a in alerts)
        crit = next(a for a in alerts if a[0] == "CRITICAL")
        assert crit[1]["event"] == "kr_fail_rate_exceeded"


# ─────────────────────────────────────────────────────────────────────
# US batch
# ─────────────────────────────────────────────────────────────────────

class TestUsBatch:
    def test_empty_returns_zero(self):
        result = pf.fetch_us_price_batch([])
        assert result["success_count"] == 0
        assert result["fail_count"] == 0


class TestEnforceCalled:
    def test_fetch_kr_calls_enforce(self):
        # max_workers=31 → ValueError before any network call
        with pytest.raises(ValueError):
            pf.fetch_kr_ohlcv_parallel(["005930"], max_workers=31)
