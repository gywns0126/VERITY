"""
텔레그램 야간 묵음 (Quiet Hours) 게이트.

목적: KST 기준 야간 시간대 (default 23:00~07:00) 비-critical 메시지 차단.
범인은 새벽 firing 하는 cron들 (rss_scout 매 30분 / daily_analysis 시간당) — 누적 20+ 알림이 한 번에 쌓이는 문제.

bypass 정책:
  - send_message(..., bypass_quiet=True) 호출은 즉시 발송 (deadman / 자동매매 체결·실패 / VAMS 손절 / circuit breaker).
  - dedupe=False 강제 발송은 별 의미. quiet hours 는 dedupe 와 직교.

미래 (v1):
  - 야간 skip 카운터 / 메타 큐 → 아침 07:05 한 통 digest. 현재는 단순 suppress only.
"""
from __future__ import annotations
from datetime import datetime
from typing import Optional

from api.config import (
    TELEGRAM_QUIET_HOURS_ENABLED,
    TELEGRAM_QUIET_START_KST,
    TELEGRAM_QUIET_END_KST,
    now_kst,
)


def is_quiet_hours(now: Optional[datetime] = None) -> bool:
    """KST 기준 quiet hours 안인가."""
    if not TELEGRAM_QUIET_HOURS_ENABLED:
        return False

    s = TELEGRAM_QUIET_START_KST
    e = TELEGRAM_QUIET_END_KST
    if s == e:
        return False

    n = now or now_kst()
    h = n.hour
    if s < e:
        return s <= h < e
    return h >= s or h < e


def quiet_hours_label() -> str:
    """디버그/로그용. '23:00~07:00 KST' 형식."""
    return f"{TELEGRAM_QUIET_START_KST:02d}:00~{TELEGRAM_QUIET_END_KST:02d}:00 KST"
