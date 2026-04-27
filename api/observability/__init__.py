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
                          save_jsonl: bool = True,
                          attach_to_portfolio: bool = True) -> Dict[str, Any]:
    """
    main() 끝에서 호출. portfolio 한 번 받아서 4개 측정 + jsonl 누적.

    Args:
      portfolio: 분석 끝난 portfolio dict (save_portfolio 직전/직후)
      save_jsonl: True 면 4개 jsonl 자동 누적. 테스트 시 False.
      attach_to_portfolio: True 면 portfolio["observability"] 에 슬림 요약 저장.
        Vercel API 가 portfolio.json 만 읽어서 대시보드 렌더링하기 위함.

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

    # 5. portfolio 에 슬림 요약 attach (Vercel API 노출용)
    if attach_to_portfolio and isinstance(portfolio, dict):
        try:
            portfolio["observability"] = _build_slim_summary(out)
        except Exception as e:  # noqa: BLE001
            logger.warning("observability: attach failed: %s", e)

    return out


def _build_slim_summary(out: Dict[str, Any]) -> Dict[str, Any]:
    """portfolio.observability 용 슬림 요약. raw_features 등 큰 데이터 제외."""
    from api.config import now_kst
    health = out.get("data_health") or {}
    drift = out.get("drift") or {}
    explanation = out.get("explanation") or {}
    trust = out.get("trust") or {}

    health_meta = health.get("_meta") or {}
    sources_slim = {}
    for k, v in health.items():
        if k == "_meta" or not isinstance(v, dict):
            continue
        sources_slim[k] = {
            "status": v.get("status"),
            "freshness_minutes": v.get("freshness_minutes"),
            "missing_pct": v.get("missing_pct"),
            "latency_ms_p50": v.get("latency_ms_p50"),
            "success_count_7d": v.get("success_count_7d"),
            "failure_count_7d": v.get("failure_count_7d"),
            "detail": (v.get("detail") or "")[:120],
        }

    return {
        "checked_at": now_kst().isoformat(),
        "data_health": {
            "overall_status": health_meta.get("overall_status"),
            "core_sources_ok": health_meta.get("core_sources_ok"),
            "sources_count": health_meta.get("sources_count"),
            "sources": sources_slim,
        },
        "drift": {
            "level": drift.get("level"),
            "overall_drift_score": drift.get("overall_drift_score"),
            "drifted_features": drift.get("drifted_features", []),
            "feature_drifts": drift.get("feature_drifts", {}),
            "comparable_count": drift.get("comparable_count", 0),
        },
        "explanation": {
            "avg_brain_score": explanation.get("avg_brain_score"),
            "positive_contributors": explanation.get("positive_contributors", []),
            "negative_contributors": explanation.get("negative_contributors", []),
            "vs_yesterday": explanation.get("vs_yesterday", {}),
        },
        "trust": {
            "verdict": trust.get("verdict"),
            "satisfied": trust.get("satisfied"),
            "total": trust.get("total"),
            "conditions": trust.get("conditions", {}),
            "details": trust.get("details", {}),
            "blocking_reasons": trust.get("blocking_reasons", []),
            "recommendation": trust.get("recommendation"),
        },
    }
