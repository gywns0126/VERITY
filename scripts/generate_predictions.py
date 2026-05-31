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

from api.config import DATA_DIR
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
    if not recs:
        sys.stderr.write("[predict] recommendations 없음/빈값 — skip (graceful exit 0)\n")
        return 0

    summary = PL.run_prediction_layer(recs, macro if isinstance(macro, dict) else {}, path=args.out)
    print(
        f"[predict] logged {summary['total']} "
        f"(stock {summary['stock_predictions']} + sector {summary['sector_predictions']})"
    )
    if summary["total"] == 0:
        sys.stderr.write("[predict] 생성 0건 — verity_brain/sectors 결손 가능 (graceful)\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
