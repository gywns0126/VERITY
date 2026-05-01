"""ATR 마이그레이션 분석 스크립트 단위 테스트 — 4 verdict 케이스 검증.

판정 매트릭스 (PHASE_0_RUNBOOK.md 사전 결정 2026-05-01):
  avg_diff_pct < 15% → ok
  15% ~ 20%          → monitoring
  > 20% (정상)       → fail
  > 20% (abnormal)   → monitoring_escape
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.analyze_atr_migration import (
    THRESHOLD_OK,
    THRESHOLD_MONITORING,
    analyze,
    compute_metrics,
    decide_verdict,
    detect_market_abnormal,
)


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────

def _write_log(log_path: Path, rows: list[dict]) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def _make_log_rows(diff_pcts: list[float], date: str = "2026-05-10") -> list[dict]:
    return [
        {
            "ticker": f"00{i:04d}",
            "timestamp": f"{date}T10:00:00",
            "atr_wilder": 1000.0,
            "atr_sma": 1000.0 / (1 + d / 100),
            "diff_pct": d,
        }
        for i, d in enumerate(diff_pcts)
    ]


def _write_history_normal(history_dir: Path, date: str = "2026-05-10") -> None:
    """정상 시장 (VIX 16, KOSPI -1%, KOSDAQ -1.5%)."""
    history_dir.mkdir(parents=True, exist_ok=True)
    snap = {
        "macro": {"vix": {"value": 16.0, "change_pct": -0.5}},
        "market_summary": {
            "kospi": {"value": 6500.0, "change_pct": -1.0},
            "kosdaq": {"value": 1190.0, "change_pct": -1.5},
        },
    }
    (history_dir / f"{date}.json").write_text(json.dumps(snap))


def _write_history_abnormal(history_dir: Path, date: str = "2026-05-10") -> None:
    """비정상 시장 (KOSPI +6%)."""
    history_dir.mkdir(parents=True, exist_ok=True)
    snap = {
        "macro": {"vix": {"value": 18.0, "change_pct": 0.5}},
        "market_summary": {
            "kospi": {"value": 6500.0, "change_pct": 6.5},  # |chg| > 5
            "kosdaq": {"value": 1190.0, "change_pct": 2.0},
        },
    }
    (history_dir / f"{date}.json").write_text(json.dumps(snap))


# ─────────────────────────────────────────────────────────────────────
# Test 1 — 정상 (avg_diff < 15%) → ok
# ─────────────────────────────────────────────────────────────────────

class TestVerdictOk:
    def test_ok_avg_diff_10pct(self, tmp_path):
        log_path = tmp_path / "atr_migration_log.jsonl"
        history_dir = tmp_path / "history"
        # avg = 10% (정상)
        _write_log(log_path, _make_log_rows([8.0, 10.0, 12.0, 9.0, 11.0]))
        _write_history_normal(history_dir)

        report = analyze(
            log_path=log_path, history_dir=history_dir,
            window_start="2026-05-09", window_end="2026-05-11",
        )
        assert report["verdict"] == "ok"
        assert report["metrics"]["avg_diff_pct"] == 10.0
        assert report["market_abnormal"] is False

    def test_ok_just_below_threshold(self, tmp_path):
        log_path = tmp_path / "log.jsonl"
        history_dir = tmp_path / "history"
        # avg = 14.9% (just below 15)
        _write_log(log_path, _make_log_rows([14.9] * 10))
        _write_history_normal(history_dir)
        report = analyze(log_path=log_path, history_dir=history_dir,
                         window_start="2026-05-09", window_end="2026-05-11")
        assert report["verdict"] == "ok"


# ─────────────────────────────────────────────────────────────────────
# Test 2 — 모니터링 (15% <= avg_diff < 20%)
# ─────────────────────────────────────────────────────────────────────

class TestVerdictMonitoring:
    def test_monitoring_avg_diff_17pct(self, tmp_path):
        log_path = tmp_path / "log.jsonl"
        history_dir = tmp_path / "history"
        # avg = 17%
        _write_log(log_path, _make_log_rows([15.0, 17.0, 19.0, 16.0, 18.0]))
        _write_history_normal(history_dir)

        report = analyze(log_path=log_path, history_dir=history_dir,
                         window_start="2026-05-09", window_end="2026-05-11")
        assert report["verdict"] == "monitoring"
        assert report["metrics"]["avg_diff_pct"] == 17.0
        assert report["market_abnormal"] is False

    def test_monitoring_at_lower_bound(self, tmp_path):
        log_path = tmp_path / "log.jsonl"
        history_dir = tmp_path / "history"
        _write_log(log_path, _make_log_rows([15.0] * 10))  # 정확히 15%
        _write_history_normal(history_dir)
        report = analyze(log_path=log_path, history_dir=history_dir,
                         window_start="2026-05-09", window_end="2026-05-11")
        assert report["verdict"] == "monitoring"

    def test_monitoring_just_below_fail(self, tmp_path):
        log_path = tmp_path / "log.jsonl"
        history_dir = tmp_path / "history"
        _write_log(log_path, _make_log_rows([19.9] * 10))  # 19.9% (just below 20)
        _write_history_normal(history_dir)
        report = analyze(log_path=log_path, history_dir=history_dir,
                         window_start="2026-05-09", window_end="2026-05-11")
        assert report["verdict"] == "monitoring"


# ─────────────────────────────────────────────────────────────────────
# Test 3 — 실패 (avg_diff >= 20%, market normal)
# ─────────────────────────────────────────────────────────────────────

class TestVerdictFail:
    def test_fail_avg_diff_25pct_market_normal(self, tmp_path):
        log_path = tmp_path / "log.jsonl"
        history_dir = tmp_path / "history"
        # avg = 25% (>20%)
        _write_log(log_path, _make_log_rows([22.0, 25.0, 28.0, 24.0, 26.0]))
        _write_history_normal(history_dir)  # 정상 시장

        report = analyze(log_path=log_path, history_dir=history_dir,
                         window_start="2026-05-09", window_end="2026-05-11")
        assert report["verdict"] == "fail"
        assert report["metrics"]["avg_diff_pct"] == 25.0
        assert report["market_abnormal"] is False
        assert "rollback_atr_to_sma" in report["recommendation"]

    def test_fail_at_threshold_20pct(self, tmp_path):
        log_path = tmp_path / "log.jsonl"
        history_dir = tmp_path / "history"
        _write_log(log_path, _make_log_rows([20.0] * 10))  # 정확히 20%
        _write_history_normal(history_dir)
        report = analyze(log_path=log_path, history_dir=history_dir,
                         window_start="2026-05-09", window_end="2026-05-11")
        assert report["verdict"] == "fail"


# ─────────────────────────────────────────────────────────────────────
# Test 4 — Escape (avg_diff >= 20%, market abnormal)
# ─────────────────────────────────────────────────────────────────────

class TestVerdictEscape:
    def test_escape_kospi_spike(self, tmp_path):
        log_path = tmp_path / "log.jsonl"
        history_dir = tmp_path / "history"
        # avg = 25% (would be fail) + KOSPI +6.5% spike
        _write_log(log_path, _make_log_rows([22.0, 25.0, 28.0, 24.0, 26.0]))
        _write_history_abnormal(history_dir)

        report = analyze(log_path=log_path, history_dir=history_dir,
                         window_start="2026-05-09", window_end="2026-05-11")
        assert report["verdict"] == "monitoring_escape"
        assert report["market_abnormal"] is True
        assert len(report["abnormal_signals"]) >= 1
        # rollback 보류
        assert "rollback 보류" in report["recommendation"] or "rollback" not in report["recommendation"].split("실행")[0]

    def test_escape_vix_high(self, tmp_path):
        log_path = tmp_path / "log.jsonl"
        history_dir = tmp_path / "history"
        _write_log(log_path, _make_log_rows([25.0] * 10))  # fail 후보
        # VIX > 30 일자 1개 + 정상 일자 1개
        history_dir.mkdir(parents=True, exist_ok=True)
        snap_high_vix = {
            "macro": {"vix": {"value": 35.0}},
            "market_summary": {"kospi": {"change_pct": -1.0}, "kosdaq": {"change_pct": -2.0}},
        }
        (history_dir / "2026-05-10.json").write_text(json.dumps(snap_high_vix))
        snap_normal = {
            "macro": {"vix": {"value": 16.0}},
            "market_summary": {"kospi": {"change_pct": -0.5}, "kosdaq": {"change_pct": -1.0}},
        }
        (history_dir / "2026-05-11.json").write_text(json.dumps(snap_normal))

        report = analyze(log_path=log_path, history_dir=history_dir,
                         window_start="2026-05-09", window_end="2026-05-12")
        assert report["verdict"] == "monitoring_escape"
        assert report["market_abnormal"] is True
        # VIX 신호 검출 확인
        vix_signals = [s for s in report["abnormal_signals"] if any("vix" in r for r in s["reasons"])]
        assert len(vix_signals) >= 1


# ─────────────────────────────────────────────────────────────────────
# 보조 — insufficient_data + 단위 helper 함수
# ─────────────────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_insufficient_data_empty_log(self, tmp_path):
        log_path = tmp_path / "log.jsonl"
        history_dir = tmp_path / "history"
        log_path.write_text("")  # 빈 로그
        _write_history_normal(history_dir)

        report = analyze(log_path=log_path, history_dir=history_dir,
                         window_start="2026-05-09", window_end="2026-05-11")
        assert report["verdict"] == "insufficient_data"

    def test_compute_metrics_basic(self):
        rows = _make_log_rows([10.0, 20.0, 30.0])
        m = compute_metrics(rows)
        assert m["sample_count"] == 3
        assert m["avg_diff_pct"] == 20.0
        assert m["max_diff_pct"] == 30.0

    def test_decide_verdict_market_abnormal_demotes_fail(self):
        # avg=25 + abnormal=True → escape
        result = decide_verdict({"avg_diff_pct": 25.0}, market_abnormal=True)
        assert result["verdict"] == "monitoring_escape"

    def test_decide_verdict_monitoring_unchanged_by_abnormal(self):
        # avg=17 + abnormal=True → monitoring (escape 적용 안 됨, 이미 monitoring)
        result = decide_verdict({"avg_diff_pct": 17.0}, market_abnormal=True)
        assert result["verdict"] == "monitoring"

    def test_detect_market_abnormal_returns_signals(self, tmp_path):
        history_dir = tmp_path / "history"
        _write_history_abnormal(history_dir, "2026-05-10")
        is_ab, signals = detect_market_abnormal(
            history_dir, "2026-05-09", "2026-05-11"
        )
        assert is_ab is True
        assert any("kospi" in r for s in signals for r in s["reasons"])

    def test_detect_market_normal_no_signals(self, tmp_path):
        history_dir = tmp_path / "history"
        _write_history_normal(history_dir)
        is_ab, signals = detect_market_abnormal(
            history_dir, "2026-05-09", "2026-05-11"
        )
        assert is_ab is False
        assert signals == []
