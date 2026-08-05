#!/usr/bin/env python3
"""fscore_shadow_trail — B3 F-Score/Accrual shadow IC trail cron (관측 전용).

사전등록 = docs/PREREG_FSCORE_ACCRUAL_B3_2026_07_12.md (PM 승인 2026-07-12).
generate_predictions/score_predictions 와 동일한 decoupled cron 패턴 — main.py 무편집.

순서: observe(당일 단면 기록) → score(eval 도달분 채점) → aggregate(IC/ICIR 집계).
graceful: 결손·예외 시 exit 0 (파이프라인 fail 안 시킴). 관측은 부수효과다.

🚨 brain-input 0 — 이 trail 은 어떤 점수에도 입력되지 않는다 (등록 §3 검증축 분리).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.config import DATA_DIR  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-date", default=None, help="관측 기준일 override (테스트용)")
    ap.add_argument("--skip-observe", action="store_true", help="채점·집계만")
    args = ap.parse_args()

    try:
        from api.intelligence import fscore_shadow as FS
    except Exception as e:  # noqa: BLE001
        print(f"[b3_shadow] 모듈 로드 실패(무시): {type(e).__name__}: {e}")
        return 0

    try:
        if not args.skip_observe:
            recs_path = Path(DATA_DIR) / "recommendations.json"
            if not recs_path.exists():
                print("[b3_shadow] recommendations.json 없음 — 관측 skip")
            else:
                with open(recs_path, encoding="utf-8") as f:
                    analyzed = json.load(f)
                obs = FS.observe(analyzed, base_date=args.base_date)
                print(f"[b3_shadow] 관측 {obs}")

        sc = FS.score()
        print(f"[b3_shadow] 채점 {sc}")

        agg = FS.aggregate()
        for a in agg:
            print(f"  {a['signal']}/{a['horizon']}: N={a['n_cross_sections']} "
                  f"IC={a['ic_mean']} ICIR={a['icir']} hit={a['ic_hit_rate']} "
                  f"spread={a['expectancy_spread_pp']} · {a['label']}")
    except Exception as e:  # noqa: BLE001
        print(f"[b3_shadow] 실패(무시): {type(e).__name__}: {e}")
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
