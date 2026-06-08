"""
prediction_trail.py — VERITY Prediction Layer 예측 로깅 primitive.

2026-06-01 신설. 사전등록 spec (docs/prediction_layer_spec_v0_2026_06_01.md) 정합.
모든 예측을 append-only forward-only 로 기록 → 채점 cron 이 eval_date 도달분 실현결과로 채점.
"진짜 산출물 = 채점되는 trail" (RULE 7 / win condition). llm_cost.py 패턴 미러.

forward-only: created_at < eval_date 강제 (look-ahead bias 차단).
horizon: short(1~5거래일) / mid(1~3개월) / long(6~12개월). eval_date = created + horizon 상한.
"""
from __future__ import annotations

import json
import os
from datetime import timedelta
from typing import Any, Dict, Optional

from api.config import DATA_DIR, now_kst

_PATH = os.path.join(DATA_DIR, "metadata", "prediction_trail.jsonl")
# 섀도우 funnel 예측 = 별도 trail (물리 분리). 프로덕션 scorer 가 섀도우를 절대 pool 하지 않도록
# (Shadow Funnel Scoring Spec v0 §5 source 분리 + §1 프로덕션 무오염). prediction_scoring.py 무변경 유지.
SHADOW_PATH = os.path.join(DATA_DIR, "metadata", "shadow_prediction_trail.jsonl")

# horizon → eval 까지 캘린더 일수 (상한 기준: 단 1주 / 중 3개월 / 장 12개월)
HORIZON_DAYS = {"short": 7, "mid": 90, "long": 365}
VALID_HORIZONS = tuple(HORIZON_DAYS)
VALID_DIRECTIONS = ("up", "down", "neutral")
VALID_TARGET_TYPES = ("sector", "stock")


def log_prediction(
    target_type: str,
    target: str,
    horizon: str,
    direction: str,
    pred_score: float,
    confidence: float,
    signals: Dict[str, Any],
    rank: Optional[int] = None,
    low_confidence: bool = False,
    spec_version: str = "v0",
    source: Optional[str] = None,
    path: Optional[str] = None,
) -> Dict[str, Any]:
    """예측 1건 로깅 (append-only, forward-only). 실패해도 caller 진행 (예측 = 부수효과)."""
    if horizon not in HORIZON_DAYS:
        raise ValueError(f"horizon must be one of {VALID_HORIZONS}, got {horizon!r}")
    if direction not in VALID_DIRECTIONS:
        raise ValueError(f"direction must be one of {VALID_DIRECTIONS}, got {direction!r}")
    if target_type not in VALID_TARGET_TYPES:
        raise ValueError(f"target_type must be one of {VALID_TARGET_TYPES}, got {target_type!r}")

    target_path = path or _PATH
    now = now_kst()
    eval_dt = now + timedelta(days=HORIZON_DAYS[horizon])
    created_iso = now.strftime("%Y-%m-%dT%H:%M:%S+09:00")
    eval_date = eval_dt.strftime("%Y-%m-%d")

    # source 구분 시 pred_id 충돌 회피 (프로덕션 vs 섀도우 동일 ticker/horizon).
    pid = f"{now.strftime('%Y%m%d')}-{target}-{horizon}"
    if source:
        pid += f"-{source.split('.')[0]}"  # "shadow_funnel.v0" → suffix "shadow_funnel"

    entry = {
        "pred_id": pid,
        "created_at": created_iso,
        "spec_version": spec_version,
        "source": source or "production",   # IC 집계 source 분리 (Shadow Funnel Scoring Spec v0 §5)
        "target_type": target_type,
        "target": target,
        "horizon": horizon,
        "eval_date": eval_date,          # 채점 시점 (created < eval = forward-only)
        "direction": direction,
        "rank": rank,                    # 섹터 로테이션 rank (stock 은 None)
        "pred_score": round(float(pred_score), 4),
        "confidence": round(float(confidence), 4),
        "low_confidence": bool(low_confidence),  # 단기 섹터 등 학술지지 낮은 케이스 (PPL Q4)
        "signals": signals,              # 근거 신호 (RULE 6 자기 자산 출처)
        # 채점 cron 산출 (eval_date 도달 시):
        "scored": False,
        "realized_return": None,
        "hit": None,
        "ic_contrib": None,
    }

    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    with open(target_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry
