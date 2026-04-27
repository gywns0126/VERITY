"""
Telegram 알림 발송 (Phase 4 에서 구현).

현재는 Phase 1 측정 모듈 결과 → 단순 로그 출력만 (실제 push X).
Phase 4 진입 시 기존 telegram 통합 + 상태 변화 검출 룰 + 스팸 방지 추가.

선행: docs/BRAIN_MONITOR_SPEC.md §4
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def dispatch_alerts(health: Dict[str, Any],
                   drift: Dict[str, Any],
                   trust: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Phase 4 placeholder. 현재는 로그만, 실제 발송 X.

    상태 변화 (ok→critical) 또는 verdict 가 hold/manual_review 일 때 알림 후보 반환.
    """
    alerts: List[Dict[str, Any]] = []

    try:
        # Trust verdict
        verdict = (trust or {}).get("verdict")
        if verdict in ("hold", "manual_review"):
            alerts.append({
                "level": "critical" if verdict == "hold" else "warning",
                "topic": "trust",
                "message": f"리포트 발행 {verdict}: {trust.get('recommendation', '')}",
                "blocking": trust.get("blocking_reasons", []),
            })

        # Drift critical
        if (drift or {}).get("level") == "critical":
            alerts.append({
                "level": "warning",
                "topic": "drift",
                "message": f"Feature drift 발생: {drift.get('drifted_features', [])}",
                "psi": drift.get("overall_drift_score"),
            })

        # Data health critical
        meta = (health or {}).get("_meta") or {}
        if meta.get("overall_status") == "critical" or not meta.get("core_sources_ok", True):
            alerts.append({
                "level": "critical",
                "topic": "data_health",
                "message": "데이터 소스 장애 감지",
                "core_sources_ok": meta.get("core_sources_ok"),
            })

        if alerts:
            logger.warning("alert_dispatcher: %d alerts pending (phase 4 dispatch 미구현)",
                          len(alerts))
        return alerts
    except Exception as e:  # noqa: BLE001
        logger.warning("alert_dispatcher: error: %s", e)
        return []
