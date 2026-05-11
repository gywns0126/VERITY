"""
시장 캘린더 helper (KR/US 휴장일, DST, 휴장 직후 첫 거래일 판정).

데이터 입력: data/calendar/{kr_holidays_2026.csv, us_holidays_2026.csv, dst_2026.csv}
출처: 2026-05-11 Perplexity fact-check + KRX/NYSE 공식 발표 일정.
연 1회 (12월) 새 연도 csv 추가 필요.

관련 메모리: project_market_info_density_map_2026
"""
from __future__ import annotations

import csv
import os
from datetime import date, datetime, timedelta
from functools import lru_cache
from typing import Iterable, Literal

try:
    from zoneinfo import ZoneInfo
    _KST = ZoneInfo("Asia/Seoul")
except Exception:
    _KST = None

Region = Literal["KR", "US"]

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CAL_DIR = os.path.join(_ROOT, "data", "calendar")


@lru_cache(maxsize=8)
def _load_holidays(region: Region) -> frozenset[date]:
    out: set[date] = set()
    prefix = {"KR": "kr_holidays_", "US": "us_holidays_"}[region]
    if not os.path.isdir(_CAL_DIR):
        return frozenset()
    for fn in os.listdir(_CAL_DIR):
        if not fn.startswith(prefix) or not fn.endswith(".csv"):
            continue
        with open(os.path.join(_CAL_DIR, fn), encoding="utf-8") as fp:
            for row in csv.DictReader(fp):
                d = row.get("date", "").strip()
                if not d:
                    continue
                try:
                    out.add(datetime.strptime(d, "%Y-%m-%d").date())
                except ValueError:
                    continue
    return frozenset(out)


@lru_cache(maxsize=8)
def _load_dst() -> dict[int, tuple[date, date]]:
    out: dict[int, tuple[date, date]] = {}
    path = os.path.join(_CAL_DIR, "dst_2026.csv")
    # 2026 단일 파일. 연도 확장 시 dst_YYYY.csv 추가하거나 단일 파일에 여러 row.
    candidates = []
    if os.path.isdir(_CAL_DIR):
        for fn in os.listdir(_CAL_DIR):
            if fn.startswith("dst_") and fn.endswith(".csv"):
                candidates.append(os.path.join(_CAL_DIR, fn))
    for p in candidates:
        with open(p, encoding="utf-8") as fp:
            for row in csv.DictReader(fp):
                if (row.get("region") or "").strip().upper() != "US":
                    continue
                try:
                    start = datetime.strptime(row["dst_start"].strip(), "%Y-%m-%d").date()
                    end = datetime.strptime(row["dst_end"].strip(), "%Y-%m-%d").date()
                except (KeyError, ValueError):
                    continue
                out[start.year] = (start, end)
    return out


def is_holiday(d: date, region: Region) -> bool:
    return d in _load_holidays(region)


def is_weekend(d: date) -> bool:
    return d.weekday() >= 5


def is_trading_day(d: date, region: Region) -> bool:
    return not is_weekend(d) and not is_holiday(d, region)


def previous_trading_day(d: date, region: Region, max_lookback: int = 10) -> date | None:
    cur = d - timedelta(days=1)
    for _ in range(max_lookback):
        if is_trading_day(cur, region):
            return cur
        cur -= timedelta(days=1)
    return None


def next_trading_day(d: date, region: Region, max_lookahead: int = 10) -> date | None:
    cur = d + timedelta(days=1)
    for _ in range(max_lookahead):
        if is_trading_day(cur, region):
            return cur
        cur += timedelta(days=1)
    return None


def is_first_trading_day_after_holiday(d: date, region: Region) -> bool:
    """오늘이 거래일이고, 어제(또는 직전 weekday)가 휴장이었으면 True.

    주말은 휴장 기간에 포함시켜 판정 — 즉 토·일이 끼어도 그 직전이 휴장이면 True.
    예: 추석 9/28~10/1 + 10/2 휴장 시, 10/5 (월) 가 True.
    예: 평범한 월요일은 직전이 토·일뿐이고 그 전 금요일이 거래일이면 False.
    """
    if not is_trading_day(d, region):
        return False
    cur = d - timedelta(days=1)
    saw_holiday = False
    for _ in range(10):
        if is_weekend(cur):
            cur -= timedelta(days=1)
            continue
        if is_holiday(cur, region):
            saw_holiday = True
            cur -= timedelta(days=1)
            continue
        return saw_holiday
    return saw_holiday


def is_us_dst(d: date) -> bool:
    table = _load_dst()
    rng = table.get(d.year)
    if not rng:
        return False
    start, end = rng
    return start <= d <= end


def now_kst() -> datetime:
    if _KST is None:
        return datetime.utcnow() + timedelta(hours=9)
    return datetime.now(_KST)


def today_kst() -> date:
    return now_kst().date()


if __name__ == "__main__":
    today = today_kst()
    print(f"today_kst={today}")
    print(f"is_trading_day KR={is_trading_day(today, 'KR')} US={is_trading_day(today, 'US')}")
    print(f"first_after_holiday KR={is_first_trading_day_after_holiday(today, 'KR')} US={is_first_trading_day_after_holiday(today, 'US')}")
    print(f"is_us_dst({today})={is_us_dst(today)}")
    print(f"prev KR={previous_trading_day(today, 'KR')} next KR={next_trading_day(today, 'KR')}")
