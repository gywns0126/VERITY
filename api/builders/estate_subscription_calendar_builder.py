"""
estate_subscription_calendar_builder.py — SubscriptionCalendar 데이터 빌더 (ESTATE D)

청약홈 분양정보 row 1건 → 5종 event 로 분해해 시간축 캘린더를 만든다. 이벤트별 책임:
    recruit       모집공고일       RCRIT_PBLANC_DE
    application   청약접수 기간   RCEPT_BGNDE ~ RCEPT_ENDDE
    announcement  당첨자발표일     PRZWNER_PRESNATN_DE
    contract      계약체결 기간   CNTRCT_CNCLS_BGNDE ~ CNTRCT_CNCLS_ENDDE
    move_in       입주예정월       MVN_PREARNGE_YM (YYYYMM → 그 달 1일로 표기)

이렇게 분해하는 사유:
    - 캘린더 시각화는 "오늘 무엇이 일어나는가" 가 핵심. 한 분양이 모집~입주까지 1~2년 늘어지므로
      row-as-event 패턴 (단일 dot) 으론 캘린더 의미 부족.
    - 5종 분해 = 시간축 위 5 dot. 각 dot 이 사용자 의사결정 게이트와 정합.
        recruit       → "지금 공고 났는가" (입찰 의향 형성)
        application   → "지금 접수 받는가" (구매 결정 시간 압축)
        announcement  → "당첨/탈락 결과 언제" (소유권 분기)
        contract      → "계약 데드라인" (현금 흐름 trigger)
        move_in       → "공급 충격 시점" (LANDEX 가격 reaction 시작점 = 미래 분석 input)

산식 / 가중치 없음 — 단순 이벤트 timeline. PolicyShock 처럼 magnitude 모델 v0 박지 않음
([[feedback_estate_density_first]] — 단순 시작, 가중 후순위).

거짓말 트랩:
    T1·T9  fabricate·silent X — 실패 시 events=[]
    T2     mock X — collector 실 응답만 사용
    T29    source_url 절대 — PBLANC_URL 그대로
"""
from __future__ import annotations

import json
import logging
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

from api.collectors.subscription_collector import (
    DEFAULT_LOOKBACK_DAYS,
    DEFAULT_LOOKFORWARD_DAYS,
    collect_subscriptions,
)

logger = logging.getLogger(__name__)

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUTPUT_PATH = os.path.join(_REPO_ROOT, "data", "estate_subscription_calendar.json")

KST = timezone(timedelta(hours=9))
SCHEMA_VERSION = "1.0"
NAMESPACE = "estate"

EVENT_TYPES = ("recruit", "application", "announcement", "contract", "move_in")

HIGH_IMPACT_SUPPLY_THRESHOLD = 1000  # TOT_SUPLY_HSHLDCO ≥ 1000 = LANDEX 영향 후보 (자체 임계 v0)


def build(
    now: Optional[datetime] = None,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    lookforward_days: int = DEFAULT_LOOKFORWARD_DAYS,
    _collect: Optional[Callable] = None,
) -> Dict[str, Any]:
    """collector 결과 → calendar payload. 실패 시에도 항상 dict (T1)."""
    now = now or datetime.now(timezone.utc)
    collect = _collect or collect_subscriptions

    try:
        rows = collect(lookback_days=lookback_days, lookforward_days=lookforward_days, now=now)
    except Exception as e:
        logger.error("subscription_calendar: collect raised: %s — events=[]", e)
        rows = []

    events: List[Dict[str, Any]] = []
    for r in rows:
        events.extend(_explode_events(r))

    # 윈도우 필터 — 과거 lookback 부터 향후 lookforward 사이의 이벤트만 노출
    cutoff_past = (now - timedelta(days=lookback_days)).date()
    cutoff_future = (now + timedelta(days=lookforward_days)).date()
    events = [e for e in events if _in_window(e, cutoff_past, cutoff_future)]
    events.sort(key=lambda e: e["date_start"])

    by_month: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {
            "count": 0,
            "by_event_type": defaultdict(int),
            "regions": defaultdict(int),
            "total_supply": 0,
        }
    )
    by_region: Dict[str, int] = defaultdict(int)

    for e in events:
        month = e["date_start"][:7]
        cell = by_month[month]
        cell["count"] += 1
        cell["by_event_type"][e["event_type"]] += 1
        cell["regions"][e["region"]] += 1
        if e.get("total_supply"):
            cell["total_supply"] += e["total_supply"]
        by_region[e["region"]] += 1

    # high-impact upcoming: 향후 30일 + recruit 이벤트 + 공급 ≥ 1000
    horizon = (now + timedelta(days=30)).date().isoformat()
    today = now.date().isoformat()
    upcoming_high_impact = [
        e for e in events
        if e["event_type"] == "recruit"
        and today <= e["date_start"] <= horizon
        and (e.get("total_supply") or 0) >= HIGH_IMPACT_SUPPLY_THRESHOLD
    ]

    return {
        "schema_version": SCHEMA_VERSION,
        "fetched_at": now.astimezone(KST).isoformat(timespec="seconds"),
        "namespace": NAMESPACE,
        "window": {"past_days": lookback_days, "future_days": lookforward_days},
        "total_subscriptions": len(rows),
        "events": events,
        "by_month": {k: _finalize_month(v) for k, v in by_month.items()},
        "by_region": dict(by_region),
        "upcoming_high_impact": upcoming_high_impact,
    }


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    payload = build()
    _write_json_atomic(OUTPUT_PATH, payload)
    logger.info(
        "main: wrote %s (subs=%d events=%d high_impact=%d)",
        OUTPUT_PATH,
        payload["total_subscriptions"],
        len(payload["events"]),
        len(payload["upcoming_high_impact"]),
    )
    return 0


# ─────────────────────────────────────────────────
# Event explosion
# ─────────────────────────────────────────────────

def _explode_events(row: Dict[str, Any]) -> List[Dict[str, Any]]:
    """청약 row → 최대 5개 event. 각 필드 비어있으면 skip."""
    house_id = (row.get("HOUSE_MANAGE_NO") or "").strip()
    if not house_id:
        return []

    base = {
        "house_manage_no": house_id,
        "pblanc_no": (row.get("PBLANC_NO") or "").strip(),
        "house_nm": (row.get("HOUSE_NM") or "").strip(),
        "address": (row.get("HSSPLY_ADRES") or "").strip(),
        "region": (row.get("SUBSCRPT_AREA_CODE_NM") or "전국").strip(),
        "business_entity": (row.get("BSNS_MBY_NM") or "").strip(),
        "total_supply": _safe_int(row.get("TOT_SUPLY_HSHLDCO")),
        "speclt_rdn_earth": (row.get("SPECLT_RDN_EARTH_AT") or "").strip() == "Y",
        "rent_secd_nm": (row.get("RENT_SECD_NM") or "").strip() or None,
        "source_url": (row.get("PBLANC_URL") or row.get("HMPG_ADRES") or "").strip(),
    }

    events: List[Dict[str, Any]] = []

    if d := _normalize_date(row.get("RCRIT_PBLANC_DE")):
        events.append({**base, "id": f"{house_id}_recruit", "event_type": "recruit",
                       "date_start": d, "date_end": None})

    s = _normalize_date(row.get("RCEPT_BGNDE"))
    e = _normalize_date(row.get("RCEPT_ENDDE"))
    if s:
        events.append({**base, "id": f"{house_id}_application", "event_type": "application",
                       "date_start": s, "date_end": e})

    if d := _normalize_date(row.get("PRZWNER_PRESNATN_DE")):
        events.append({**base, "id": f"{house_id}_announcement", "event_type": "announcement",
                       "date_start": d, "date_end": None})

    s = _normalize_date(row.get("CNTRCT_CNCLS_BGNDE"))
    e = _normalize_date(row.get("CNTRCT_CNCLS_ENDDE"))
    if s:
        events.append({**base, "id": f"{house_id}_contract", "event_type": "contract",
                       "date_start": s, "date_end": e})

    if mvn := _normalize_month(row.get("MVN_PREARNGE_YM")):
        events.append({**base, "id": f"{house_id}_move_in", "event_type": "move_in",
                       "date_start": mvn, "date_end": None})

    return events


def _finalize_month(cell: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "count": cell["count"],
        "by_event_type": dict(cell["by_event_type"]),
        "regions": dict(cell["regions"]),
        "total_supply": cell["total_supply"],
    }


def _in_window(event: Dict[str, Any], past: Any, future: Any) -> bool:
    try:
        d = datetime.strptime(event["date_start"], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return False
    return past <= d <= future


def _normalize_date(raw: Any) -> Optional[str]:
    """API 응답 날짜 → YYYY-MM-DD. 빈/잘못된 값 → None."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    # 응답 포맷 = "YYYY-MM-DD" (PublicDataReader 실측). 일부 row 가 YYYYMMDD 일 가능성 대비.
    try:
        if len(s) == 10 and s[4] == "-" and s[7] == "-":
            datetime.strptime(s, "%Y-%m-%d")
            return s
        if len(s) == 8 and s.isdigit():
            return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    except ValueError:
        return None
    return None


def _normalize_month(raw: Any) -> Optional[str]:
    """MVN_PREARNGE_YM (YYYYMM 또는 YYYY-MM) → 해당 월 1일 (YYYY-MM-01)."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    try:
        if len(s) == 6 and s.isdigit():
            return f"{s[:4]}-{s[4:6]}-01"
        if len(s) == 7 and s[4] == "-":
            datetime.strptime(s, "%Y-%m")
            return f"{s}-01"
    except ValueError:
        return None
    return None


def _safe_int(raw: Any) -> Optional[int]:
    if raw is None or raw == "":
        return None
    try:
        return int(str(raw).replace(",", "").strip())
    except (ValueError, TypeError):
        return None


def _write_json_atomic(path: str, data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


if __name__ == "__main__":
    raise SystemExit(main())
