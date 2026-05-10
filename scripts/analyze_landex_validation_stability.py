#!/usr/bin/env python3
"""LANDEX 메타-검증 silent 메트릭 안정성 분석.

RUNBOOK: docs/LANDEX_VALIDATION_RUNBOOK_5_12.md §3 의 *불변 계약* 4종 구현.

  CLI 인자 (불변):  --window-start / --window-end / --output
  입력 (불변):      data/metadata/landex_meta_validation.jsonl
  출력 schema (불변): n_cron_records / metric_stability{4} / p0_pass_rate_*  / verdict / verdict_reasoning
  exit code (불변): 0 ok / 1 partial / 2 unstable / 3 fail

  내부 임계 판정 로직은 *RUNBOOK 가변* — 5/26 정식 명세에서 재조정. 본 구현은 5/12
  mid-checkpoint 분포 관찰용 preliminary.

호출:
  5/12 mid: --window-start 2026-05-05 --window-end 2026-05-12 --output data/analysis/landex_validation_stability_20260512.json
  5/26 정식: --window-start 2026-05-05 --window-end 2026-05-26 --output data/analysis/landex_validation_stability_20260526.json
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = ROOT / "data" / "metadata" / "landex_meta_validation.jsonl"

# 4 metrics tracked (Sharpe 는 silent 기록은 되지만 RUNBOOK §3-3 의무 schema 4종이라 stability 추적 X)
METRICS = ("spearman_rank_ic", "rmse", "direction_accuracy", "quintile_spread_pct")

# 안정성 정의 (RUNBOOK §4-1) — 5/26 명세 시 재조정 가능
STABILITY_RATIO_THRESHOLD = 0.3


def _read_jsonl_window(path: Path, start: str, end: str) -> list[dict]:
    """jsonl 에서 timestamp[:10] ∈ [start, end] (포함) 인 row 만 읽음."""
    if not path.exists():
        return []
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = (r.get("timestamp") or "")[:10]
            if start <= ts <= end:
                rows.append(r)
    return rows


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _variance(xs: list[float], mean: float) -> float:
    """Sample variance (n-1 분모). n<2 면 0."""
    if len(xs) < 2:
        return 0.0
    return sum((x - mean) ** 2 for x in xs) / (len(xs) - 1)


def _stability_ratio(mean: float, variance: float) -> Optional[float]:
    """sqrt(variance) / |mean|. mean=0 면 None (정의 불가)."""
    if mean == 0:
        return None
    return math.sqrt(variance) / abs(mean)


def _is_stable(mean: float, variance: float) -> bool:
    """RUNBOOK §4-1: stability_ratio < 0.3 = 안정.

    edge: mean=0 + variance=0 → 안정 (분산 자체가 없음)
          mean=0 + variance>0 → 불안정 (분산은 있는데 중심이 0)
    """
    if mean == 0:
        return variance == 0
    ratio = _stability_ratio(mean, variance)
    return ratio is not None and ratio < STABILITY_RATIO_THRESHOLD


def _metric_stability(rows: list[dict], metric: str) -> dict:
    vals: list[float] = []
    for r in rows:
        v = (r.get("metrics") or {}).get(metric)
        if v is not None:
            try:
                vals.append(float(v))
            except (TypeError, ValueError):
                continue
    mean = _mean(vals)
    variance = _variance(vals, mean)
    return {
        "mean": round(mean, 6),
        "variance": round(variance, 6),
        "stable": _is_stable(mean, variance),
    }


def _p0_pass_rates(rows: list[dict]) -> tuple[float, float]:
    """(rate_4_of_4, rate_3_of_4) — n_cron_records 중 통과 비율."""
    if not rows:
        return 0.0, 0.0
    n = len(rows)
    n_4 = 0
    n_3 = 0
    for r in rows:
        passed = ((r.get("thresholds_evaluated") or {}).get("p0_passed_count") or 0)
        try:
            passed = int(passed)
        except (TypeError, ValueError):
            passed = 0
        if passed >= 4:
            n_4 += 1
        if passed >= 3:
            n_3 += 1
    return n_4 / n, n_3 / n


def _verdict(
    stability: dict,
    p0_3_rate: float,
    n_records: int,
) -> tuple[str, str]:
    """RUNBOOK §4 매트릭스 정합 — preliminary (5/26 명세 시 재조정).

    Returns: (verdict, reasoning)
    """
    if n_records == 0:
        return "fail", "no_records_in_window"

    unstable = [m for m in METRICS if not stability[m]["stable"]]
    n_unstable = len(unstable)

    # fail: P0 한번도 4중 3 통과 안 됨
    if p0_3_rate == 0:
        return "fail", f"p0_3_of_4 pass rate=0 across n={n_records} records (model may be unfit)"

    # unstable: 3+ 메트릭 불안정
    if n_unstable >= 3:
        return "unstable", f"{n_unstable}/4 metrics unstable (ratio >= {STABILITY_RATIO_THRESHOLD}): {unstable}"

    # partial: 1~2 불안정 또는 통과 변동
    if n_unstable >= 1 or p0_3_rate < 1.0:
        bits = []
        if n_unstable:
            bits.append(f"{n_unstable}/4 metrics unstable: {unstable}")
        if p0_3_rate < 1.0:
            bits.append(f"p0_3_of_4 pass rate={p0_3_rate:.2f}")
        return "partial", "; ".join(bits)

    # ok: 모두 안정 + 모든 record 4중 3 통과
    return "ok", f"all 4 metrics stable; n={n_records} all pass p0_3_of_4"


_EXIT_BY_VERDICT = {"ok": 0, "partial": 1, "unstable": 2, "fail": 3}


def analyze(window_start: str, window_end: str, jsonl_path: Path = DEFAULT_INPUT) -> dict:
    """순수 함수 — 결과 dict 반환. CLI / 테스트 양쪽에서 사용."""
    rows = _read_jsonl_window(jsonl_path, window_start, window_end)
    stability = {m: _metric_stability(rows, m) for m in METRICS}
    rate_4, rate_3 = _p0_pass_rates(rows)
    verdict, reasoning = _verdict(stability, rate_3, len(rows))
    return {
        "window_start": window_start,
        "window_end": window_end,
        "n_cron_records": len(rows),
        "metric_stability": stability,
        "p0_pass_rate_4_of_4": round(rate_4, 4),
        "p0_pass_rate_3_of_4": round(rate_3, 4),
        "verdict": verdict,
        "verdict_reasoning": reasoning,
    }


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--window-start", required=True, help="YYYY-MM-DD (포함)")
    p.add_argument("--window-end",   required=True, help="YYYY-MM-DD (포함)")
    p.add_argument("--output",       required=True, help="결과 JSON 출력 path")
    p.add_argument("--input", default=str(DEFAULT_INPUT),
                   help=f"jsonl 입력 (기본 {DEFAULT_INPUT.relative_to(ROOT)})")
    args = p.parse_args(argv)

    jsonl_path = Path(args.input)
    result = analyze(args.window_start, args.window_end, jsonl_path)

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    # 사용자 가시 한 줄 요약
    print(f"[landex stability] window={args.window_start}~{args.window_end} "
          f"n={result['n_cron_records']} verdict={result['verdict']} → {out}",
          file=sys.stderr)
    return _EXIT_BY_VERDICT[result["verdict"]]


if __name__ == "__main__":
    sys.exit(main())
