#!/usr/bin/env python3
"""
generate_predictions.py — daily Prediction Layer 생성 (decoupled, main.py 무편집).

2026-06-01 신설. 사전등록 spec docs/prediction_layer_spec_v0_2026_06_01.md 정합.
파이프라인 산출물(recommendations.json + macro_industry_alignment.json)을 읽어
prediction_trail.jsonl 에 cross-section 1벌 로깅. daily 워크플로의 main.py 이후 step.

graceful: 입력 결손 시 exit 0 (파이프라인 fail 안 시킴, RULE — 예측은 부수효과).
채점은 별도 cron (eval_date 도달분).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root (cockpit_aggregate 패턴)

from api.config import DATA_DIR, now_kst
from api.intelligence import prediction_layer as PL


def _load(path: str):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"[predict] load fail {path}: {type(e).__name__}: {e}\n")
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None, help="trail 경로 override (테스트용). 기본 = data/metadata/prediction_trail.jsonl")
    args = ap.parse_args()

    recs = _load(os.path.join(DATA_DIR, "recommendations.json"))
    macro = _load(os.path.join(DATA_DIR, "macro_industry_alignment.json"))

    if isinstance(recs, dict):
        recs = recs.get("recommendations") or recs.get("data") or []
    # 프로덕션 예측 (recs 결손 시 skip — 섀도우는 독립 진행)
    if recs:
        summary = PL.run_prediction_layer(recs, macro if isinstance(macro, dict) else {}, path=args.out)
        print(
            f"[predict] logged {summary['total']} "
            f"(stock {summary['stock_predictions']} + sector {summary['sector_predictions']})"
        )
        if summary["total"] == 0:
            sys.stderr.write("[predict] 생성 0건 — verity_brain/sectors 결손 가능 (graceful)\n")
    else:
        sys.stderr.write("[predict] recommendations 없음 — production skip (graceful)\n")

    # 섀도우 funnel 예측 (Shadow Funnel Scoring Spec v0 — 별도 trail, 프로덕션 무오염)
    shadow = _load(os.path.join(DATA_DIR, "metadata", "shadow_funnel_picks.json"))
    shadow_out = (args.out + ".shadow.jsonl") if args.out else None  # 테스트 시에도 섀도우 격리
    if isinstance(shadow, dict) and shadow.get("picks"):
        # scan_at 신선도 가드 (P2 #13): universe_scan miss 시 stale picks 재emit → IC 시계열 중복 왜곡 방지.
        scan_day = str(shadow.get("scan_at", ""))[:10]
        today = now_kst().strftime("%Y-%m-%d")
        if scan_day and scan_day < today:
            sys.stderr.write(
                f"[predict] shadow picks stale (scan_at={scan_day} < today={today}) — shadow skip (graceful)\n"
            )
        else:
            sh = PL.generate_shadow_predictions(shadow["picks"], path=shadow_out)
            print(
                f"[predict] shadow logged {len(sh)} "
                f"(funnel {len(shadow['picks'])} × {len(PL._HORIZONS)}h, source={PL._SHADOW_SOURCE}, "
                f"trail={'shadow_prediction_trail.jsonl' if not shadow_out else shadow_out})"
            )
    else:
        sys.stderr.write("[predict] shadow_funnel_picks 없음/빈값 — shadow skip (graceful)\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
