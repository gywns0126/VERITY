"""KI-9 — backtest_stats_history.jsonl 누적 (cross-link baseline source) 단위 테스트.

검증:
  - non-null hit_rate_14d 만 append (null 노이즈 회피)
  - 일자 dedupe (1일 1행 — 90일 mean 왜곡 방지)
  - end-to-end: 산출 파일이 BrainDistributionEvaluator.compute_baseline 에 먹힘
"""
from __future__ import annotations

import json
import os

from api.metadata import brain_learning as bl
from api.observability.cross_link_evaluators.brain_distribution_evaluator import (
    BrainDistributionEvaluator,
    COLD_START_BASELINE,
)


def _entry(date: str, ts: str, hit14, status="ok", hit30=None):
    return {
        "date": date,
        "timestamp": ts,
        "backtest_hit_rate_14d": hit14,
        "backtest_hit_rate_30d": hit30,
        "backtest_hit_rate_data_status": status,
    }


class TestAppendBacktestHistory:
    def test_appends_non_null(self, monkeypatch, tmp_path):
        p = tmp_path / "backtest_stats_history.jsonl"
        monkeypatch.setattr(bl, "_HISTORY_PATH", str(p))
        bl._append_backtest_history(_entry("2026-05-21", "2026-05-21T20:00:00+09:00", 0.52, hit30=0.48))
        rows = [json.loads(l) for l in p.read_text().splitlines()]
        assert len(rows) == 1
        assert rows[0]["hit_rate_14d"] == 0.52
        assert rows[0]["hit_rate_30d"] == 0.48
        assert rows[0]["updated_at"] == "2026-05-21T20:00:00+09:00"

    def test_skips_null(self, monkeypatch, tmp_path):
        p = tmp_path / "backtest_stats_history.jsonl"
        monkeypatch.setattr(bl, "_HISTORY_PATH", str(p))
        bl._append_backtest_history(_entry("2026-05-22", "2026-05-22T20:00:00+09:00", None, status="no_data"))
        assert not p.exists()  # null → 미생성

    def test_dedupe_same_day(self, monkeypatch, tmp_path):
        p = tmp_path / "backtest_stats_history.jsonl"
        monkeypatch.setattr(bl, "_HISTORY_PATH", str(p))
        bl._append_backtest_history(_entry("2026-05-21", "2026-05-21T20:00:00+09:00", 0.52))
        # 같은 날 재호출 (다른 값) → skip, first-write wins
        bl._append_backtest_history(_entry("2026-05-21", "2026-05-21T21:00:00+09:00", 0.99))
        rows = [json.loads(l) for l in p.read_text().splitlines()]
        assert len(rows) == 1 and rows[0]["hit_rate_14d"] == 0.52

    def test_end_to_end_feeds_baseline(self, monkeypatch, tmp_path):
        # 산출 파일이 compute_baseline 에 정상 소비되는지 (계약 정합).
        meta = tmp_path / "metadata"
        meta.mkdir()
        p = meta / "backtest_stats_history.jsonl"
        monkeypatch.setattr(bl, "_HISTORY_PATH", str(p))
        # 60일치 0.55 (COLD_START_LIMIT=50 초과 → baseline 활성)
        from datetime import datetime, timedelta
        base = datetime(2026, 5, 21)
        for i in range(60):
            d = (base - timedelta(days=i)).strftime("%Y-%m-%d")
            ts = (base - timedelta(days=i)).strftime("%Y-%m-%dT20:00:00+09:00")
            bl._append_backtest_history(_entry(d, ts, 0.55))
        ev = BrainDistributionEvaluator(data_dir=str(tmp_path))
        out = ev.compute_baseline(lookback_days=90)
        assert out["cold_start"] is False
        assert out["n_history"] == 60
        assert abs(out["baseline"] - 0.55) < 1e-6
