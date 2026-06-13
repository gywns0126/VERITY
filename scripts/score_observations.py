#!/usr/bin/env python3
"""
score_observations.py — 관측-only 신호 trail(OBS_PATH) 채점 cron (decoupled, main.py 무편집).

2026-06-13 신설. 사전등록 spec docs/observation_signal_trails_spec_v0_2026_06_13.md 정합.
observation_prediction_trail.jsonl 의 eval_date 도달분(scored==false)을 실현 시장 index level diff 로
채점 → trail scored=true rewrite + (source, horizon) 집계 observation_ic_history.jsonl append.
daily 워크플로의 generate_predictions step 이후 step (생성 → 채점 순서). 관측 only — 결정 피드백 0(RULE 7).

market-level scorer (종목 scorer 와 별 모듈). graceful: 결손/예외 시 exit 0.
실현 snapshot 미존재분 = pending (다음 run 재시도, grace 14일).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root

from api.intelligence import observation_scoring as OS


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trail", default=None, help="trail 경로 override (테스트용)")
    ap.add_argument("--ic-history", default=None, help="ic_history 경로 override (테스트용)")
    args = ap.parse_args()

    try:
        summary = OS.score_observations(trail_path=args.trail, ic_history_path=args.ic_history)
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"[score_obs] 채점 실패 (graceful exit 0): {type(e).__name__}: {e}\n")
        return 0

    print(
        f"[score_obs] scored={summary.get('scored', 0)} "
        f"pending={summary.get('pending', 0)} "
        f"unscoreable={summary.get('unscoreable', 0)} "
        f"skipped_nonmarket={summary.get('skipped_nonmarket', 0)} "
        f"groups={summary.get('groups', 0)}"
    )
    if summary.get("scored", 0) == 0 and summary.get("pending", 0) == 0:
        sys.stderr.write("[score_obs] 채점 도달분 0 (eval_date 미도래 — 첫 단기 eval 생성+7일, 정상)\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
