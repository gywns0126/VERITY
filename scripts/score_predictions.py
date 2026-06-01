#!/usr/bin/env python3
"""
score_predictions.py — Prediction Layer 채점 cron (decoupled, main.py 무편집).

2026-06-01 신설. 사전등록 spec docs/prediction_layer_spec_v0_2026_06_01.md §9.3 정합.
prediction_trail.jsonl 의 eval_date 도달분(scored==false)을 실현 시장 결과로 채점 →
trail scored=true rewrite + (target_type, horizon) 집계 prediction_ic_history.jsonl append.
daily 워크플로의 generate_predictions step 이후 step (생성 → 채점 순서).

graceful: 결손/예외 시 exit 0 (파이프라인 fail 안 시킴). 채점 = 부수효과.
실현 가격 미존재(eval 직후 snapshot 미생성)분 = pending (다음 run 재시도, grace 14일).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root

from api.intelligence import prediction_scoring as PS


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trail", default=None, help="trail 경로 override (테스트용)")
    ap.add_argument("--ic-history", default=None, help="ic_history 경로 override (테스트용)")
    args = ap.parse_args()

    try:
        summary = PS.score_predictions(trail_path=args.trail, ic_history_path=args.ic_history)
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"[score] 채점 실패 (graceful exit 0): {type(e).__name__}: {e}\n")
        return 0

    print(
        f"[score] scored={summary.get('scored', 0)} "
        f"pending={summary.get('pending', 0)} "
        f"unscoreable={summary.get('unscoreable', 0)} "
        f"sector_deferred={summary.get('deferred_sector', 0)} "
        f"groups={summary.get('groups', 0)}"
    )
    if summary.get("scored", 0) == 0 and summary.get("pending", 0) == 0:
        sys.stderr.write("[score] 채점 도달분 0 (eval_date 미도래 — 첫 단기 eval 6/8 예정, 정상)\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
