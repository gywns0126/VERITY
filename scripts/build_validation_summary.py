#!/usr/bin/env python3
"""
build_validation_summary.py — 모든 forward trail 검증 상태 집계 cron (decoupled).

2026-06-13 신설. 사전등록 spec docs/validation_summary_spec_v0_2026_06_13.md 정합.
score_predictions step 이후 실행 (채점 → 집계 순서). 기존 *_ic_history 산출물을
read-only 재집계 → data/validation_summary.json. 신규 산식 0 / 결정 피드백 0 (RULE 7).

graceful: 결손/예외 시 exit 0 (파이프라인 fail 안 시킴). 집계 = 부수효과.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root

from api.observability import validation_summary as VS


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None, help="출력 경로 override (테스트용)")
    args = ap.parse_args()

    try:
        summary = VS.write_summary(out_path=args.out)
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"[validation_summary] 집계 실패 (graceful exit 0): "
                         f"{type(e).__name__}: {e}\n")
        return 0

    g = summary.get("gate", {})
    print(
        f"[validation_summary] best_signal_n={g.get('best_signal_n')} "
        f"progress={g.get('progress_pct')}% "
        f"signals={len(summary.get('signals', []))}"
    )
    if summary.get("_write_error"):
        sys.stderr.write(f"[validation_summary] write 경고: {summary['_write_error']}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
