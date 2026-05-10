"""LANDEX 안정성 분석 스크립트 schema·verdict·exit code 정합 검증.

RUNBOOK 의 *불변 계약* 4종 보호:
  - CLI 인자 (--window-start / --window-end / --output)
  - 입력 (jsonl row schema)
  - 출력 JSON schema (의무 키 8종)
  - exit code (0/1/2/3 by verdict)
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "analyze_landex_validation_stability.py"

# 의무 출력 schema 키 (RUNBOOK §3-3)
_REQUIRED_KEYS = {
    "window_start", "window_end", "n_cron_records",
    "metric_stability",
    "p0_pass_rate_4_of_4", "p0_pass_rate_3_of_4",
    "verdict", "verdict_reasoning",
}
_REQUIRED_METRICS = {"spearman_rank_ic", "rmse", "direction_accuracy", "quintile_spread_pct"}
_VALID_VERDICTS = {"ok", "partial", "unstable", "fail"}


def _make_record(
    timestamp: str,
    spearman: float,
    rmse: float,
    direction: float,
    quintile: float,
    p0_passed: int,
) -> dict:
    """landex_meta_validation.py `_compute_silent_metrics()` 출력 정합 한 row."""
    return {
        "timestamp": f"{timestamp}T03:00:00+09:00",
        "horizon_weeks": 13,
        "n_districts": 25,
        "metrics": {
            "spearman_rank_ic": spearman,
            "spearman_pvalue": 0.05,
            "rmse": rmse,
            "market_volatility": 1.5,
            "direction_accuracy": direction,
            "quintile_spread_pct": quintile,
            "sharpe_long_only_q5": 0.4,
        },
        "thresholds_evaluated": {
            "spearman_pass": p0_passed >= 1,
            "rmse_pass": p0_passed >= 2,
            "direction_pass": p0_passed >= 3,
            "quintile_pass": p0_passed >= 4,
            "p0_passed_count": p0_passed,
            "would_pass_with_3_of_4": p0_passed >= 3,
        },
        "current_operational_verdict": "ready",
    }


def _run_script(jsonl: Path, start: str, end: str, out: Path) -> tuple[int, dict]:
    proc = subprocess.run(
        [
            sys.executable, str(SCRIPT),
            "--window-start", start,
            "--window-end", end,
            "--input", str(jsonl),
            "--output", str(out),
        ],
        capture_output=True, text=True, timeout=30,
    )
    if out.exists():
        return proc.returncode, json.loads(out.read_text(encoding="utf-8"))
    return proc.returncode, {}


def _assert_schema(result: dict) -> None:
    assert _REQUIRED_KEYS.issubset(result.keys()), f"missing keys: {_REQUIRED_KEYS - result.keys()}"
    assert _REQUIRED_METRICS.issubset(result["metric_stability"].keys()), \
        f"missing metrics: {_REQUIRED_METRICS - result['metric_stability'].keys()}"
    for m in _REQUIRED_METRICS:
        ms = result["metric_stability"][m]
        assert {"mean", "variance", "stable"}.issubset(ms.keys()), \
            f"metric_stability.{m} missing required sub-keys"
        assert isinstance(ms["stable"], bool)
    assert result["verdict"] in _VALID_VERDICTS
    assert isinstance(result["verdict_reasoning"], str) and result["verdict_reasoning"]


def test_no_records_in_window_returns_fail_exit_3(tmp_path: Path):
    """n=0 → verdict=fail / exit=3 (RUNBOOK §3-2 + §3-4)."""
    jsonl = tmp_path / "empty.jsonl"
    jsonl.write_text("", encoding="utf-8")
    out = tmp_path / "result.json"

    code, result = _run_script(jsonl, "2026-05-05", "2026-05-12", out)

    assert code == 3
    _assert_schema(result)
    assert result["verdict"] == "fail"
    assert result["n_cron_records"] == 0
    assert "no_records" in result["verdict_reasoning"]


def test_all_stable_all_pass_returns_ok_exit_0(tmp_path: Path):
    """모든 메트릭 안정 + 모든 record p0_3_of_4 통과 → ok / exit=0."""
    jsonl = tmp_path / "stable.jsonl"
    rows = [
        _make_record("2026-05-05", spearman=0.12, rmse=0.7, direction=0.62, quintile=1.1, p0_passed=4),
        _make_record("2026-05-12", spearman=0.13, rmse=0.7, direction=0.61, quintile=1.2, p0_passed=4),
        _make_record("2026-05-19", spearman=0.12, rmse=0.7, direction=0.62, quintile=1.1, p0_passed=3),
        _make_record("2026-05-26", spearman=0.13, rmse=0.7, direction=0.61, quintile=1.2, p0_passed=4),
    ]
    jsonl.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    out = tmp_path / "result.json"

    code, result = _run_script(jsonl, "2026-05-05", "2026-05-26", out)

    assert code == 0
    _assert_schema(result)
    assert result["verdict"] == "ok"
    assert result["n_cron_records"] == 4
    assert result["p0_pass_rate_3_of_4"] == 1.0
    assert all(result["metric_stability"][m]["stable"] for m in _REQUIRED_METRICS)


def test_unstable_three_metrics_returns_unstable_exit_2(tmp_path: Path):
    """3+ 메트릭 variance 폭주 → unstable / exit=2."""
    jsonl = tmp_path / "unstable.jsonl"
    rows = [
        _make_record("2026-05-05", spearman=0.05, rmse=0.5, direction=0.50, quintile=0.2, p0_passed=3),
        _make_record("2026-05-12", spearman=0.30, rmse=2.0, direction=0.80, quintile=3.0, p0_passed=3),
        _make_record("2026-05-19", spearman=0.10, rmse=0.5, direction=0.55, quintile=0.5, p0_passed=3),
        _make_record("2026-05-26", spearman=0.25, rmse=2.5, direction=0.85, quintile=2.5, p0_passed=3),
    ]
    jsonl.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    out = tmp_path / "result.json"

    code, result = _run_script(jsonl, "2026-05-05", "2026-05-26", out)

    assert code == 2
    _assert_schema(result)
    assert result["verdict"] == "unstable"
    n_unstable = sum(1 for m in _REQUIRED_METRICS if not result["metric_stability"][m]["stable"])
    assert n_unstable >= 3


def test_p0_never_pass_returns_fail_exit_3(tmp_path: Path):
    """모든 record p0_passed_count<3 → fail / exit=3 (모델 부적합 신호)."""
    jsonl = tmp_path / "fail.jsonl"
    rows = [
        _make_record("2026-05-05", spearman=0.12, rmse=0.7, direction=0.62, quintile=1.1, p0_passed=1),
        _make_record("2026-05-12", spearman=0.12, rmse=0.7, direction=0.62, quintile=1.1, p0_passed=2),
    ]
    jsonl.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    out = tmp_path / "result.json"

    code, result = _run_script(jsonl, "2026-05-05", "2026-05-12", out)

    assert code == 3
    _assert_schema(result)
    assert result["verdict"] == "fail"
    assert result["p0_pass_rate_3_of_4"] == 0.0


def test_window_filter_excludes_outside_dates(tmp_path: Path):
    """window 외 row 는 제외 (RUNBOOK §3-2)."""
    jsonl = tmp_path / "windowed.jsonl"
    rows = [
        _make_record("2026-05-04", spearman=0.99, rmse=99.0, direction=0.99, quintile=99.0, p0_passed=4),  # 제외
        _make_record("2026-05-05", spearman=0.12, rmse=0.7, direction=0.62, quintile=1.1, p0_passed=4),
        _make_record("2026-05-12", spearman=0.13, rmse=0.7, direction=0.61, quintile=1.2, p0_passed=4),
        _make_record("2026-05-13", spearman=0.99, rmse=99.0, direction=0.99, quintile=99.0, p0_passed=4),  # 제외
    ]
    jsonl.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    out = tmp_path / "result.json"

    code, result = _run_script(jsonl, "2026-05-05", "2026-05-12", out)

    assert result["n_cron_records"] == 2
    # 제외된 row 의 99 값이 mean 에 영향 안 미쳐야 함
    assert result["metric_stability"]["spearman_rank_ic"]["mean"] < 1.0
