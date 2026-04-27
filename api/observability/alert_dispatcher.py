"""
Brain Observatory 알림 발송 (Phase 4).

룰 (spec §4.1):
  - 데이터 소스 status: ok → critical 즉시 푸시
  - drift level: ok → critical 즉시 푸시
  - trust verdict: ready → hold/manual_review 즉시 푸시
  - warning 누적: 1시간 후 푸시 (스팸 방지)

상태 추적: data/metadata/alert_state.json
  - 마지막 발송 fingerprint, 마지막 warning 시각, 마지막 push 시각

기존 telegram 통합: api.notifications.telegram.send_message
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from api.config import DATA_DIR, KST, now_kst

logger = logging.getLogger(__name__)

_STATE_PATH = os.path.join(DATA_DIR, "metadata", "alert_state.json")
WARNING_AGE_THRESHOLD_HOURS = 1


def _load_state() -> Dict[str, Any]:
    if not os.path.exists(_STATE_PATH):
        return {"last_topics": {}, "warnings_since": {}, "last_push_at": None}
    try:
        with open(_STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("alert_dispatcher: state load failed: %s", e)
        return {"last_topics": {}, "warnings_since": {}, "last_push_at": None}


def _save_state(state: Dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(_STATE_PATH), exist_ok=True)
        with open(_STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except OSError as e:
        logger.warning("alert_dispatcher: state save failed: %s", e)


def _parse_iso(s: Optional[str]) -> Optional[datetime]:
    if not s or not isinstance(s, str):
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _build_messages(health: Dict[str, Any],
                   drift: Dict[str, Any],
                   trust: Dict[str, Any],
                   state: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    검출된 알림 후보 list. 각 항목:
      {"topic": str, "level": "critical"|"warning", "message": str, "details": dict}
    """
    alerts: List[Dict[str, Any]] = []
    last_topics = state.get("last_topics") or {}

    # 1. data_health overall: critical 진입 또는 core_sources 장애
    health_meta = (health or {}).get("_meta") or {}
    overall = health_meta.get("overall_status")
    core_ok = health_meta.get("core_sources_ok", True)
    prev_overall = (last_topics.get("data_health") or {}).get("status")
    if overall == "critical" and prev_overall != "critical":
        bad = []
        for k, v in (health or {}).items():
            if k == "_meta" or not isinstance(v, dict):
                continue
            if v.get("status") == "critical":
                bad.append(k)
        alerts.append({
            "topic": "data_health",
            "level": "critical",
            "message": f"🔴 데이터 소스 장애: {', '.join(bad[:5]) if bad else '?'}",
            "details": {"bad_sources": bad, "core_sources_ok": core_ok},
        })
    elif overall == "warning":
        # warning 은 누적 검사
        alerts.append({
            "topic": "data_health",
            "level": "warning",
            "message": f"🟡 데이터 소스 경계 — overall={overall}",
            "details": {"core_sources_ok": core_ok},
        })

    # 2. drift level: critical
    drift_level = (drift or {}).get("level")
    drifted = (drift or {}).get("drifted_features") or []
    prev_drift = (last_topics.get("drift") or {}).get("level")
    if drift_level == "critical" and prev_drift != "critical":
        alerts.append({
            "topic": "drift",
            "level": "critical",
            "message": f"🔴 Feature drift 발생: {', '.join(drifted[:5])}",
            "details": {"score": (drift or {}).get("overall_drift_score"),
                       "drifted": drifted},
        })

    # 3. trust verdict: ready → hold/manual_review
    verdict = (trust or {}).get("verdict")
    prev_verdict = (last_topics.get("trust") or {}).get("verdict")
    if verdict == "hold":
        # 항상 즉시 푸시 (PDF 차단 시점)
        alerts.append({
            "topic": "trust",
            "level": "critical",
            "message": f"🔴 리포트 발행 차단: {(trust or {}).get('recommendation', '')}",
            "details": {"blocking": (trust or {}).get("blocking_reasons", []),
                       "satisfied": f"{(trust or {}).get('satisfied')}/{(trust or {}).get('total')}"},
        })
    elif verdict == "manual_review" and prev_verdict == "ready":
        # ready → manual_review 전환 시 1회 푸시
        alerts.append({
            "topic": "trust",
            "level": "warning",
            "message": f"🟡 리포트 검수 필요: {(trust or {}).get('recommendation', '')}",
            "details": {"blocking": (trust or {}).get("blocking_reasons", []),
                       "satisfied": f"{(trust or {}).get('satisfied')}/{(trust or {}).get('total')}"},
        })

    return alerts


def _filter_warnings(alerts: List[Dict[str, Any]],
                    state: Dict[str, Any],
                    now: datetime) -> List[Dict[str, Any]]:
    """warning 은 1시간 누적 후 발송. critical 은 즉시."""
    warnings_since = state.get("warnings_since") or {}
    out: List[Dict[str, Any]] = []
    for a in alerts:
        if a["level"] == "critical":
            out.append(a)
            warnings_since.pop(a["topic"], None)
            continue
        # warning
        first_seen = _parse_iso(warnings_since.get(a["topic"]))
        if first_seen is None:
            warnings_since[a["topic"]] = now.isoformat()
            continue  # 1시간 대기 시작
        age_hours = (now - first_seen).total_seconds() / 3600
        if age_hours >= WARNING_AGE_THRESHOLD_HOURS:
            out.append(a)
            warnings_since[a["topic"]] = now.isoformat()  # 다음 1시간 대기 reset
    state["warnings_since"] = warnings_since
    return out


def _format_telegram(alert: Dict[str, Any]) -> str:
    lines = [f"<b>[VERITY Brain]</b> {alert['message']}"]
    d = alert.get("details") or {}
    for k, v in d.items():
        if isinstance(v, list):
            v = ", ".join(map(str, v[:5])) if v else "(없음)"
        lines.append(f"  · {k}: {v}")
    lines.append(f"\n시각: {now_kst().strftime('%Y-%m-%d %H:%M KST')}")
    lines.append("링크: /admin/brain-monitor")
    return "\n".join(lines)


def _send_one(alert: Dict[str, Any]) -> bool:
    """단일 알림 telegram 발송. 실패해도 메인 흐름 영향 X."""
    try:
        from api.notifications.telegram import send_message
        text = _format_telegram(alert)
        return bool(send_message(text, dedupe=True))
    except Exception as e:  # noqa: BLE001
        logger.warning("alert_dispatcher: send failed (%s): %s", alert.get("topic"), e)
        return False


def dispatch_alerts(health: Optional[Dict[str, Any]] = None,
                   drift: Optional[Dict[str, Any]] = None,
                   trust: Optional[Dict[str, Any]] = None,
                   send: bool = True) -> List[Dict[str, Any]]:
    """
    상태 변화 검출 + Telegram 푸시 + 상태 저장.

    Args:
      health, drift, trust: 4개 측정 모듈 결과 (slim 또는 full)
      send: False 면 발송 X (테스트/dry-run)

    Returns: 실제 발송된 알림 리스트
    """
    state = _load_state()
    now = now_kst()

    try:
        candidates = _build_messages(health or {}, drift or {}, trust or {}, state)
        to_send = _filter_warnings(candidates, state, now)

        sent: List[Dict[str, Any]] = []
        if send and to_send:
            for a in to_send:
                if _send_one(a):
                    sent.append(a)
        elif not send:
            sent = to_send  # dry-run 결과 반환

        # last_topics 갱신
        last_topics = state.get("last_topics") or {}
        last_topics["data_health"] = {"status": (health or {}).get("_meta", {}).get("overall_status")}
        last_topics["drift"] = {"level": (drift or {}).get("level")}
        last_topics["trust"] = {"verdict": (trust or {}).get("verdict")}
        state["last_topics"] = last_topics
        if sent:
            state["last_push_at"] = now.isoformat()
        _save_state(state)

        return sent
    except Exception as e:  # noqa: BLE001
        logger.warning("alert_dispatcher: dispatch error: %s", e, exc_info=True)
        return []
