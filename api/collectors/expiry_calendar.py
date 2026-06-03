"""
선물/옵션 만기일 캘린더 + 관망 로직
verity_brain.py의 macro_override에 직결
"""
from datetime import date, timedelta
from typing import Optional, List, Dict

from api.config import now_kst

# ── 만기일 = 연도 무관 룰 기반 자동 산출 (2026-06-03 정정) ──────────────────
#   이전: KR_EXPIRY_2026 / US_QUAD_WITCHING_2026 하드코드 dict (연도 무관 참조) →
#   2027-01-01 부터 _next_expiry 가 전부 None → 영구 NORMAL → 만기 강등 silent dead.
#   정정: KRX 규정 = KR 옵션 매월 둘째 목요일 / KR 선물(주식) 3·6·9·12월 둘째 목요일 /
#   US 쿼드위칭 3·6·9·12월 셋째 금요일. 2026 하드코드와 100% 일치 검증 후 대체.
#   ⚠ 휴장 겹침 시 KRX 는 직전 영업일로 만기 — 2026 은 무보정 일치였으나, 미래 연도
#   휴장 겹침 보정은 market_calendar 영업일 헬퍼로 후속 큐잉 (feedback_weekday_check).
_THURSDAY = 3
_FRIDAY = 4
_QUARTER_MONTHS = (3, 6, 9, 12)

_POSITION_CAP = {"NORMAL": 1.0, "CAUTION": 0.5, "FULL_WATCH": 0.0}


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """해당 월의 n번째 weekday(0=Mon..6=Sun) 날짜."""
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + timedelta(days=offset + (n - 1) * 7)


def _kr_option_expiries(year: int) -> List[date]:
    """KR 옵션 만기 = 매월 둘째 목요일."""
    return [_nth_weekday(year, m, _THURSDAY, 2) for m in range(1, 13)]


def _kr_futures_expiries(year: int) -> List[date]:
    """KR 선물 만기 = 3·6·9·12월 둘째 목요일."""
    return [_nth_weekday(year, m, _THURSDAY, 2) for m in _QUARTER_MONTHS]


def _us_quad_witching(year: int) -> List[date]:
    """US 쿼드위칭 = 3·6·9·12월 셋째 금요일."""
    return [_nth_weekday(year, m, _FRIDAY, 3) for m in _QUARTER_MONTHS]


def _expiry_lists(today: date) -> Dict[str, List[date]]:
    """today 기준 당해+익년 만기일 (연말 경계에서 다음 만기 탐색 보장)."""
    yrs = (today.year, today.year + 1)
    return {
        "option": [d for y in yrs for d in _kr_option_expiries(y)],
        "futures": [d for y in yrs for d in _kr_futures_expiries(y)],
        "us": [d for y in yrs for d in _us_quad_witching(y)],
    }


def get_expiry_status(target_date: Optional[date] = None) -> dict:
    """
    특정 날짜의 만기 상태 반환.
    verity_brain.py에서 매 실행마다 호출.
    """
    today = target_date or now_kst().date()

    exp = _expiry_lists(today)
    upcoming_option = _next_expiry(today, exp["option"])
    upcoming_futures = _next_expiry(today, exp["futures"])
    upcoming_us = _next_expiry(today, exp["us"])

    days_to_option = (upcoming_option - today).days if upcoming_option else 99
    days_to_futures = (upcoming_futures - today).days if upcoming_futures else 99
    days_to_us = (upcoming_us - today).days if upcoming_us else 99

    is_option_expiry = today in exp["option"]
    is_futures_expiry = today in exp["futures"]
    is_quad_witching = is_option_expiry and is_futures_expiry
    is_us_quad = today in exp["us"]

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
    """전체 연간 캘린더 반환 — earnings_calendar와 통합 가능. (2026-06-03: year 인자 실사용)"""
    calendar: List[Dict] = []
    option_list = _kr_option_expiries(year)
    futures_list = _kr_futures_expiries(year)
    for d in option_list:
        is_futures = d in futures_list
        calendar.append({
            "date": d.isoformat(),
            "type": "QUAD_WITCHING" if is_futures else "OPTION_EXPIRY",
            "kr_option": True,
            "kr_futures": is_futures,
            "danger_window_start": (d - timedelta(days=3)).isoformat(),
        })
    for d in _us_quad_witching(year):
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
