#!/usr/bin/env python3
"""ATR Phase 1.1 4-cell 백테스트 wrapper — 2026-05-16 ATR verdict=OK 후속.

목적: ATR(period, multiplier) 4 조합 sweep 으로 large stop_loss 75.6% finding
정량 baseline 정정. 현 default 14×2.5 가 진짜 최적인지 검증.

Cells:
  (14, 2.5) — Phase 1.1 default (baseline)
  (14, 3.0) — multiplier 완화 → false stop 감소 vs holding 손실 확대 trade-off
  (22, 2.5) — period 길게 → 변동성 smoother, signal lag vs noise 감소
  (22, 3.0) — 보수적 조합 — small caps 손절 회피

각 cell 동일 universe (--stratified-100) 동일 기간 (2020-2025 6년) 실행.
결과: data/analysis/atr_4cell_sweep_<date>.json + 콘솔 markdown 요약.

사용:
  python scripts/run_atr_4cell_sweep.py                    # stratified 100 (≈ 15-20분)
  python scripts/run_atr_4cell_sweep.py --quick            # limit 30 빠른 smoke
  python scripts/run_atr_4cell_sweep.py --cells 14,2.5     # 단일 cell

근거: docs/BRAIN_SIGNAL_INTEGRATION_PLAN_v0.1.md / project_atr_dynamic_stop /
      project_r_multiple_exit / queue id 57ac6bd0.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = REPO_ROOT / "data" / "analysis"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_CELLS: List[Tuple[int, float]] = [
    (14, 2.5),
    (14, 3.0),
    (22, 2.5),
    (22, 3.0),
]


def run_cell(period: int, mult: float, args: argparse.Namespace) -> dict:
    """단일 cell 실행 — analyze_5r_sample_feasibility.py 호출.

    ATR_PERIOD / ATR_MULTIPLIER 는 모듈 상수라 env 로 override 불가능. 따라서
    환경변수 ATR_STOP_MULTIPLIER 만 적용되고 period 는 14 고정.
    period != 14 cell 은 결과 not_supported 표기 (technical.compute_atr_14d 확장 필요).
    """
    cell_id = f"{period}x{mult:.1f}"
    print(f"\n{'='*60}")
    print(f"  CELL [{cell_id}]  ATR period={period}, multiplier={mult}")
    print(f"{'='*60}")

    if period != 14:
        # compute_atr_14d 가 14 고정 — period 22 cell 은 후속 확장 필요.
        # 지금 단계에선 not_supported 표기 + recommendation 출력만.
        return {
            "cell_id": cell_id,
            "atr_period": period,
            "atr_multiplier": mult,
            "status": "not_supported",
            "reason": (
                "api/analyzers/technical.compute_atr_14d 가 14 고정. period 22 는 "
                "compute_atr_n 헬퍼 확장 후 진입 가능 (Phase 1.3 prerequisite)."
            ),
        }

    cmd = [
        "python3", str(REPO_ROOT / "scripts" / "analyze_5r_sample_feasibility.py"),
        "--start", args.start,
        "--end", args.end,
        "--quiet",
    ]
    if args.quick:
        cmd += ["--limit", "30"]
    else:
        cmd += ["--stratified-100"]
    # output path 명시
    cell_out = OUTPUT_DIR / f"atr_cell_{cell_id}_{datetime.now():%Y%m%d_%H%M%S}.json"
    cmd += ["--output", str(cell_out)]

    env_override = {"ATR_STOP_MULTIPLIER": str(mult)}
    import os
    env = dict(os.environ); env.update(env_override)

    t0 = time.time()
    print(f"  cmd: {' '.join(cmd)}")
    print(f"  env: ATR_STOP_MULTIPLIER={mult}")
    print(f"  out: {cell_out}")
    try:
        proc = subprocess.run(
            cmd, env=env, cwd=str(REPO_ROOT),
            capture_output=True, text=True, timeout=1800,  # 30min cap
        )
        elapsed = round(time.time() - t0, 1)
        if proc.returncode != 0:
            return {
                "cell_id": cell_id,
                "atr_period": period,
                "atr_multiplier": mult,
                "status": "error",
                "elapsed_s": elapsed,
                "stderr_tail": proc.stderr[-500:],
            }
        if not cell_out.exists():
            return {
                "cell_id": cell_id,
                "atr_period": period,
                "atr_multiplier": mult,
                "status": "no_output",
                "elapsed_s": elapsed,
            }
        with open(cell_out, "r", encoding="utf-8") as f:
            cell_data = json.load(f)
        # 핵심 metric 발췌 — analyze_5r 출력은 metrics 하위 nested dict.
        # (옛 버전은 top-level get → 전부 null. 5/16 buggy run 원인.)
        m = cell_data.get("metrics", {}) or {}
        params = cell_data.get("params", {}) or {}
        slr = m.get("stop_loss_rate")          # 0~1 ratio
        hit = m.get("5r_hit_rate")             # 0~1 ratio
        return {
            "cell_id": cell_id,
            "atr_period": period,
            "atr_multiplier": mult,
            "status": "ok",
            "elapsed_s": elapsed,
            "output_path": str(cell_out),
            # universe_source = fallback_whitelist 면 KRX_API_KEY 누락 degrade (PM 데이터 무효).
            "universe_source": params.get("universe_source"),
            "n_unique_tickers": m.get("n_5r_unique_tickers"),
            "verdict": cell_data.get("verdict"),
            "n_entries": m.get("total_entries_simulated"),
            "total_5r_hits": m.get("total_5r_hits"),
            "total_stop_loss": m.get("total_stop_loss"),
            "hit_rate_5r_pct": round(hit * 100, 2) if isinstance(hit, (int, float)) else None,
            "stop_loss_pct": round(slr * 100, 2) if isinstance(slr, (int, float)) else None,
        }
    except subprocess.TimeoutExpired:
        return {
            "cell_id": cell_id,
            "atr_period": period,
            "atr_multiplier": mult,
            "status": "timeout",
            "elapsed_s": round(time.time() - t0, 1),
        }
    except Exception as e:
        return {
            "cell_id": cell_id,
            "atr_period": period,
            "atr_multiplier": mult,
            "status": "exception",
            "elapsed_s": round(time.time() - t0, 1),
            "exception": str(e),
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="ATR Phase 1.1 4-cell sweep")
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default="2025-12-31")
    parser.add_argument(
        "--cells", default=None,
        help="콤마 분리 cell 목록 (예: '14,2.5;14,3.0'). None=4 default cell"
    )
    parser.add_argument(
        "--quick", action="store_true",
        help="--limit 30 빠른 smoke (cell 당 ~3-5분)"
    )
    args = parser.parse_args()

    if args.cells:
        cells = []
        for part in args.cells.split(";"):
            p, m = part.split(",")
            cells.append((int(p.strip()), float(m.strip())))
    else:
        cells = DEFAULT_CELLS

    print(f"=== ATR 4-cell sweep ===")
    print(f"period: {args.start} ~ {args.end}")
    print(f"cells:  {cells}")
    print(f"mode:   {'quick (--limit 30)' if args.quick else 'stratified-100'}")

    results = []
    for period, mult in cells:
        results.append(run_cell(period, mult, args))

    # 합계 리포트
    summary_path = OUTPUT_DIR / f"atr_4cell_sweep_{datetime.now():%Y%m%d_%H%M%S}.json"
    report = {
        "generated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "period": {"start": args.start, "end": args.end},
        "mode": "quick" if args.quick else "stratified-100",
        "cells": results,
        "baseline_reference": (
            "풀스캔 v2 large stop_loss 75.6% finding (Phase 1.1 baseline) — "
            "Phase 0.5 결정 19건 + project_atr_dynamic_stop memory."
        ),
        "limitations": [
            "period 22 cells = not_supported (compute_atr_14d 가 14 고정, Phase 1.3 확장 필요)",
            "각 cell stratified-100 = 100 ticker 표본. 전체 universe sweep 은 후속",
        ],
    }
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*60}")
    print(f"=== 4-cell sweep SUMMARY ===")
    print(f"{'='*60}")
    print(f"{'cell':<10} {'status':<14} {'n_tickers':<10} {'verdict':<10} {'5r_hit':<9} {'stop_loss':<10} {'elapsed':<8}")
    print("-" * 80)
    for r in results:
        cell = r["cell_id"]
        status = r["status"]
        n = r.get("n_unique_tickers", "-")
        v = r.get("verdict", "-")
        hit = r.get("hit_rate_5r_pct", "-")
        hit_str = f"{hit}%" if isinstance(hit, (int, float)) else str(hit)
        sl = r.get("stop_loss_pct", "-")
        sl_str = f"{sl}%" if isinstance(sl, (int, float)) else str(sl)
        elap = r.get("elapsed_s", "-")
        print(f"{cell:<10} {status:<14} {str(n):<10} {str(v):<10} {hit_str:<9} {sl_str:<10} {str(elap):<8}")

    print(f"\n[saved] {summary_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
