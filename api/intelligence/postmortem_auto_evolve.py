"""postmortem_auto_evolve — postmortem 결과 → EWMA factor quarantine 산출 + ledger 적재.

🚨 현 상태 (2026-06-03 RULE 10 audit 정정): 이 모듈은 quarantined_factors / weight_adjustments
를 산출해 LEDGER_PATH 에 **적재·관측만** 한다. 산출물을 fact.py / verity_brain.py 의 실제
brain 점수에 반영하는 소비 hook 은 **의도적으로 미연결**이다 (이전 docstring "자동 반영" 표기는
과장 — 실제 적용 경로 0). 이유: 유효 학습 N 부족 (factor_decay IC 경로가 2026-05-23 PM 결정으로
동결된 것과 동일 맥락) → N<365 에서 misleading_factor 기반 자동 factor 끄기 = 곡선맞추기 위험
(RULE 7 / overfit guard). 적재된 ledger 는 향후 N 마일스톤 도달 시 적용 활성화의 입력 + 현재는
관측 trail. **적용(brain 반영) 활성화 = 유효 N 마일스톤 + PM 재승인 시에만** (factor_decay 동결
해제와 동기). 그 전까지 ledger 는 dead-end 가 아니라 의도된 관측 단계.

연관:
  - audit BRAIN_SELF_GROWTH P1-1
  - Perplexity NQ5 (2026-05-16): EWMA 1차 권장 (λ=0.94 RiskMetrics), 소샘플 적합
  - feedback_continuous_evolution (4가드)
  - api/intelligence/postmortem.py (postmortem 생성)
  - api/intelligence/strategy_evolver.py (룰 진화 큐)

핵심 로직:
1. postmortem.misleading_factors → EWMA 가중치 감쇠
2. SHAP sign consistency (sign 반전 detection)
3. 한국 소샘플(<10건) 환경 우선 EWMA + Bayesian Prior fallback

3-단계 적용:
- Step 1: EWMA 기반 IC 트래킹 (λ=0.94)
- Step 2: 가격 기반 factor — 빠른 반영 / 재무 factor — 분기 단위 prior shrinkage
- Step 3: postmortem 루프 자동화 (misleading factor → quarantine flag)
"""
from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional

from api.config import DATA_DIR, now_kst

LEDGER_PATH = os.path.join(DATA_DIR, "metadata", "postmortem_auto_evolve.jsonl")

# RiskMetrics 표준 EWMA λ
EWMA_LAMBDA = 0.94
# misleading factor 연속 검출 quarantine 임계
QUARANTINE_CONSECUTIVE = 3


def update_ewma(prev_ewma: Optional[float], new_observation: float,
                lambda_: float = EWMA_LAMBDA) -> float:
    """EWMA 업데이트.

    w_t = λ × w_{t-1} + (1-λ) × x_t

    prev_ewma None 이면 첫 관측치로 초기화.
    """
    if prev_ewma is None:
        return new_observation
    return round(lambda_ * prev_ewma + (1 - lambda_) * new_observation, 5)


def detect_sign_consistency_violation(
    factor_history: List[float],
    min_obs: int = 3,
) -> Dict[str, Any]:
    """SHAP sign consistency 위반 감지 (Two Sigma 패턴, Perplexity NQ5).

    동일 factor 가 상승/하락 구간에서 sign 반전 시 "Leaky Signal" 판정.

    Args:
        factor_history: 최근 N 관측 IC 값
        min_obs: 최소 관측 수

    Returns:
        {
            "violation": bool,
            "sign_changes": int,
            "consistency_score": float (0-1),
            "verdict": "stable" / "weakening" / "leaky",
        }
    """
    if len(factor_history) < min_obs:
        return {"violation": False, "sign_changes": 0,
                "consistency_score": 1.0, "verdict": "insufficient_data"}

    # sign 변화 카운트
    sign_changes = 0
    prev_sign = None
    for v in factor_history:
        if v == 0:
            continue
        s = 1 if v > 0 else -1
        if prev_sign is not None and s != prev_sign:
            sign_changes += 1
        prev_sign = s

    # consistency score = 1 - (sign_changes / max possible)
    max_changes = max(1, len(factor_history) - 1)
    consistency_score = round(1 - (sign_changes / max_changes), 3)

    # verdict
    if consistency_score >= 0.8:
        verdict = "stable"
    elif consistency_score >= 0.5:
        verdict = "weakening"
    else:
        verdict = "leaky"  # 부호 자주 반전 → quarantine 후보

    return {
        "violation": verdict == "leaky",
        "sign_changes": sign_changes,
        "consistency_score": consistency_score,
        "verdict": verdict,
    }


def apply_postmortem_to_factor_weights(
    postmortem: Dict[str, Any],
    current_ewma_state: Dict[str, float],
) -> Dict[str, Any]:
    """postmortem.misleading_factors → factor 가중치 EWMA 감쇠 적용.

    Args:
        postmortem: portfolio.postmortem (status/misleading_factors/lesson)
        current_ewma_state: {factor_name: ewma_value} (직전 상태)

    Returns:
        {
            "ewma_state_new": {factor: new_ewma, ...},
            "weight_adjustments": {factor: multiplier, ...},
            "quarantined_factors": [list],
            "reason": str,
        }
    """
    if postmortem.get("status") in ("clean", "no_failures"):
        return {
            "ewma_state_new": dict(current_ewma_state),
            "weight_adjustments": {},
            "quarantined_factors": [],
            "reason": f"postmortem clean ({postmortem.get('message', '')})",
        }

    misleading = postmortem.get("misleading_factors") or {}
    if not isinstance(misleading, dict) or not misleading:
        return {
            "ewma_state_new": dict(current_ewma_state),
            "weight_adjustments": {},
            "quarantined_factors": [],
            "reason": "misleading_factors empty",
        }

    new_ewma = dict(current_ewma_state)
    weight_adjustments: Dict[str, float] = {}
    quarantined: List[str] = []

    for factor, severity in misleading.items():
        # severity → 음수 IC observation 으로 EWMA 갱신
        try:
            sev_float = float(severity)
        except (TypeError, ValueError):
            sev_float = -0.05  # default penalty

        prev = current_ewma_state.get(factor)
        # 음수 IC 신호 (misleading = factor 가 잘못 도움)
        new_val = update_ewma(prev, -abs(sev_float))
        new_ewma[factor] = new_val

        # EWMA < -0.02 = persistent misleading → quarantine
        if new_val < -0.02:
            quarantined.append(factor)
            weight_adjustments[factor] = 0.3  # floor 30%
        elif new_val < 0:
            weight_adjustments[factor] = 0.7  # mild penalty
        else:
            weight_adjustments[factor] = 1.0

    return {
        "ewma_state_new": new_ewma,
        "weight_adjustments": weight_adjustments,
        "quarantined_factors": quarantined,
        "reason": (
            f"misleading {len(misleading)} factor 감쇠 / "
            f"quarantine {len(quarantined)} ({', '.join(quarantined[:3])})"
        ),
    }


def evaluate_and_persist(portfolio: Dict[str, Any]) -> Dict[str, Any]:
    """end-to-end: portfolio.postmortem → EWMA 적용 → ledger 적재.

    이전 ewma_state 는 ledger 마지막 entry 에서 복원 (없으면 빈 dict).
    """
    postmortem = portfolio.get("postmortem") or {}

    # 이전 ewma_state 복원
    prev_state: Dict[str, float] = {}
    if os.path.exists(LEDGER_PATH):
        try:
            with open(LEDGER_PATH, "r", encoding="utf-8") as f:
                lines = f.readlines()
            if lines:
                last = json.loads(lines[-1])
                prev_state = last.get("ewma_state_new", {})
        except Exception:
            pass

    result = apply_postmortem_to_factor_weights(postmortem, prev_state)

    # ledger 적재
    try:
        os.makedirs(os.path.dirname(LEDGER_PATH), exist_ok=True)
        entry = {
            "ts_kst": now_kst().isoformat(),
            "postmortem_status": postmortem.get("status"),
            "ewma_lambda": EWMA_LAMBDA,
            **result,
        }
        with open(LEDGER_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        import sys
        sys.stderr.write(f"[postmortem_auto_evolve] ledger 적재 실패: {e}\n")

    return result
