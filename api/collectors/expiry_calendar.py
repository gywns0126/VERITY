"""
선물/옵션 만기일 캘린더 + 관망 로직
verity_brain.py의 macro_override에 직결
"""
from datetime import date, timedelta
from typing import Optional, List, Dict

# ── 2026년 KR 만기일 (연간 업데이트) ──────────────────────
KR_EXPIRY_2026 = {
    "option": [
        date(2026, 1, 8),  date(2026, 2, 12), date(2026, 3, 12),
        date(2026, 4, 9),  date(2026, 5, 14), date(2026, 6, 11),
        date(2026, 7, 9),  date(2026, 8, 13), date(2026, 9, 10),
        date(2026, 10, 8), date(2026, 11, 12), date(2026, 12, 10),
    ],
    "futures": [
        date(2026, 3, 12), date(2026, 6, 11),
        date(2026, 9, 10), date(2026, 12, 10),
    ],
}

# US 쿼드위칭 (3,6,9,12월 세번째 금요일)
US_QUAD_WITCHING_2026 = [
    date(2026, 3, 20), date(2026, 6, 19),
    date(2026, 9, 18), date(2026, 12, 18),
]

_POSITION_CAP = {"NORMAL": 1.0, "CAUTION": 0.5, "FULL_WATCH": 0.0}


def get_expiry_status(target_date: Optional[date] = None) -> dict:
    """
    특정 날짜의 만기 상태 반환.
    verity_brain.py에서 매 실행마다 호출.
    """
    today = target_date or date.today()

    upcoming_option = _next_expiry(today, KR_EXPIRY_2026["option"])
    upcoming_futures = _next_expiry(today, KR_EXPIRY_2026["futures"])
    upcoming_us = _next_expiry(today, US_QUAD_WITCHING_2026)

    days_to_option = (upcoming_option - today).days if upcoming_option else 99
    days_to_futures = (upcoming_futures - today).days if upcoming_futures else 99
    days_to_us = (upcoming_us - today).days if upcoming_us else 99

    is_option_expiry = today in KR_EXPIRY_2026["option"]
    is_futures_expiry = today in KR_EXPIRY_2026["futures"]
    is_quad_witching = is_option_expiry and is_futures_expiry
    is_us_quad = today in US_QUAD_WITCHING_2026

    in_kr_danger_window = days_to_option <= 3
    in_us_danger_window = days_to_us <= 3
    in_futures_window = days_to_futures <= 5

    # ── 관망 등급 결정 ──────────────────────────────
    if is_quad_witching or is_us_quad:
        watch_level = "FULL_WATCH"
        reason = "KR 선물+옵션 동시만기 (쿼드위칭)" if is_quad_witching else "US 쿼드위칭"
    elif is_futures_expiry:
        watch_level = "FULL_WATCH"
        reason = "KR 선물만기일"
    elif in_futures_window:
        watch_level = "CAUTION"
        reason = f"KR 선물만기 D-{days_to_futures}"
    elif is_option_expiry:
        watch_level = "CAUTION"
        reason = "KR 옵션만기일"
    elif in_kr_danger_window:
        watch_level = "CAUTION"
        reason = f"KR 옵션만기 D-{days_to_option}"
    elif in_us_danger_window:
        watch_level = "CAUTION"
        reason = f"US 쿼드위칭 D-{days_to_us}"
    else:
        watch_level = "NORMAL"
        reason = None

    return {
        "date": today.isoformat(),
        "watch_level": watch_level,
        "reason": reason,
        "is_option_expiry": is_option_expiry,
        "is_futures_expiry": is_futures_expiry,
        "is_quad_witching": is_quad_witching,
        "is_us_quad_witching": is_us_quad,
        "days_to_kr_option": days_to_option,
        "days_to_kr_futures": days_to_futures,
        "days_to_us_quad": days_to_us,
        "next_kr_option": upcoming_option.isoformat() if upcoming_option else None,
        "next_kr_futures": upcoming_futures.isoformat() if upcoming_futures else None,
        "next_us_quad": upcoming_us.isoformat() if upcoming_us else None,
        "chase_buy_allowed": watch_level == "NORMAL",
        "position_size_cap": _POSITION_CAP[watch_level],
    }


def get_annual_expiry_calendar(year: int = 2026) -> List[Dict]:
    """전체 연간 캘린더 반환 — earnings_calendar와 통합 가능."""
    calendar: List[Dict] = []
    for d in KR_EXPIRY_2026["option"]:
        is_futures = d in KR_EXPIRY_2026["futures"]
        calendar.append({
            "date": d.isoformat(),
            "type": "QUAD_WITCHING" if is_futures else "OPTION_EXPIRY",
            "kr_option": True,
            "kr_futures": is_futures,
            "danger_window_start": (d - timedelta(days=3)).isoformat(),
        })
    for d in US_QUAD_WITCHING_2026:
        calendar.append({
            "date": d.isoformat(),
            "type": "US_QUAD_WITCHING",
            "kr_option": False,
            "kr_futures": False,
            "danger_window_start": (d - timedelta(days=3)).isoformat(),
        })
    return sorted(calendar, key=lambda x: x["date"])


def _next_expiry(today: date, expiry_list: List[date]) -> Optional[date]:
    future = [d for d in expiry_list if d >= today]
    return min(future) if future else None
