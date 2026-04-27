"""
VERITY Brain Observatory — 측정 모듈 (Phase 1).

선행 문서:
  docs/BRAIN_MONITOR_SPEC.md (Phase 1 §1)
  docs/BRAIN_MONITOR_WIREFRAME.md

가드 정책 (spec §6):
  - 모든 진입점 try/except + logger.warning
  - 실패 시 None / 안전 기본값 반환, 메인 흐름 영향 0
  - 메타데이터 jsonl 누적 (1주일 후 의미 시작)
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from .data_health import check_data_health, persist_health
from .feature_drift import compute_drift, extract_features, persist_drift
from .explainability import explain_brain_score, persist_explanation
from .trust_score import report_readiness, persist_trust

logger = logging.getLogger(__name__)

__all__ = [
    "check_data_health",
    "compute_drift",
    "explain_brain_score",
    "report_readiness",
    "run_full_observability",
]


def run_full_observability(portfolio: Optional[dict],
                          save_jsonl: bool = True) -> Dict[str, Any]:
    """
    main() 끝에서 호출. portfolio 한 번 받아서 4개 측정 + jsonl 누적.

    Args:
      portfolio: 분석 끝난 portfolio dict (save_portfolio 직전/직후)
      save_jsonl: True 면 4개 jsonl 자동 누적. 테스트 시 False.

    Returns:
      {"data_health": ..., "drift": ..., "explanation": ..., "trust": ...}

    가드: 어떤 단계든 실패해도 메인 흐름 영향 0. 실패 모듈만 None.
    """
    out: Dict[str, Any] = {}

    # 1. data_health
    try:
        health = check_data_health(portfolio)
        out["data_health"] = health
        if save_jsonl:
            persist_health(health)
    except Exception as e:  # noqa: BLE001
        logger.warning("observability: data_health failed: %s", e, exc_info=True)
        out["data_health"] = None

    # 2. feature_drift (extract → compute → persist)
    today_features: Dict[str, float] = {}
    try:
        today_features = extract_features(portfolio)
        drift = compute_drift(today=today_features)
        out["drift"] = drift
        if save_jsonl and today_features:
            persist_drift(drift, today_features)
    except Exception as e:  # noqa: BLE001
        logger.warning("observability: drift failed: %s", e, exc_info=True)
        out["drift"] = None

    # 3. explainability
    try:
        explanation = explain_brain_score(portfolio)
        out["explanation"] = explanation
        if save_jsonl:
            persist_explanation(explanation, today_features)
    except Exception as e:  # noqa: BLE001
        logger.warning("observability: explainability failed: %s", e, exc_info=True)
        out["explanation"] = None

    # 4. trust_score (data_health + drift 결과 활용)
    try:
        trust = report_readiness(portfolio,
                                data_health=out.get("data_health"),
                                drift=out.get("drift"))
        out["trust"] = trust
        if save_jsonl:
            persist_trust(trust)
    except Exception as e:  # noqa: BLE001
        logger.warning("observability: trust failed: %s", e, exc_info=True)
        out["trust"] = None

    return out
