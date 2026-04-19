"""
VERITY — Brain 결과 90일 보존 + 3일 후 실현 수익률 백필.

목적
----
red_flag_penalty / overrides 등 Brain 로직의 precision/recall 을 누적 데이터로 재검증.
기존 archiver.py 의 풀 스냅샷(history/YYYY-MM-DD.json, ~MB)과는 별도로,
Brain 핵심 필드만 추린 슬림 스냅샷을 일자별 디렉터리에 보관한다.

저장 구조
--------
data/history/YYYYMMDD/brain_results.json

스키마
------
{
    "date": "20260419",
    "saved_at": ISO8601,
    "stocks": [
        {
            "ticker": str,
            "name": str,
            "market": "KR" | "US",
            "price": float,                  # 저장 시점 종가 (수익률 baseline)
            "brain_score": float,
            "grade": str,
            "red_flags": dict,               # auto_avoid / downgrade / has_critical / downgrade_count
            "overrides_applied": list,
            "actual_return_3d": float | null # 저장 +3 calendar days 후 백필
        },
        ...
    ]
}

보존 정책
--------
- save_brain_snapshot: 매 full/quick 실행 후 호출 (당일 폴더 덮어씀)
- cleanup_old_brain_snapshots: 90일 초과 디렉터리 자동 삭제
- backfill_actual_returns: 3일 전 스냅샷의 actual_return_3d 채워넣기
"""
from __future__ import annotations

import json
import os
import re
import shutil
from datetime import timedelta
from typing import Optional

from api.config import DATA_DIR, now_kst

HISTORY_ROOT = os.path.join(DATA_DIR, "history")
BRAIN_FILE = "brain_results.json"
KEEP_DAYS = 90
BACKFILL_LAG_DAYS = 3

_DATE_DIR_RE = re.compile(r"^\d{8}$")


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _slim_stock(stock: dict) -> Optional[dict]:
    """recommendations[*] → 브레인 슬림 dict. ticker 없으면 None."""
    ticker = stock.get("ticker")
    if not ticker:
        return None
    vb = stock.get("verity_brain") or {}
    return {
        "ticker": ticker,
        "name": stock.get("name"),
        "market": stock.get("market"),
        "price": stock.get("price"),
        "brain_score": vb.get("brain_score"),
        "grade": vb.get("grade"),
        "red_flags": vb.get("red_flags") or {},
        "overrides_applied": stock.get("overrides_applied") or [],
        "actual_return_3d": None,
    }


def _atomic_write(path: str, payload: dict) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, default=str)
    os.replace(tmp, path)


def save_brain_snapshot(portfolio: dict) -> Optional[str]:
    """오늘자 브레인 슬림 스냅샷 저장. 경로 반환 (recommendations 비면 None)."""
    recs = portfolio.get("recommendations") or []
    stocks = [s for s in (_slim_stock(r) for r in recs) if s]
    if not stocks:
        return None

    now = now_kst()
    date_str = now.strftime("%Y%m%d")
    day_dir = os.path.join(HISTORY_ROOT, date_str)
    _ensure_dir(day_dir)
    path = os.path.join(day_dir, BRAIN_FILE)

    payload = {
        "date": date_str,
        "saved_at": now.isoformat(),
        "stocks": stocks,
    }
    _atomic_write(path, payload)
    return path


def _list_date_dirs() -> list[str]:
    if not os.path.isdir(HISTORY_ROOT):
        return []
    return sorted(d for d in os.listdir(HISTORY_ROOT) if _DATE_DIR_RE.match(d))


def cleanup_old_brain_snapshots(keep_days: int = KEEP_DAYS) -> int:
    """90일 초과 일자별 폴더 삭제. 삭제된 폴더 수 반환."""
    cutoff = (now_kst().date() - timedelta(days=keep_days)).strftime("%Y%m%d")
    removed = 0
    for d in _list_date_dirs():
        if d < cutoff:
            try:
                shutil.rmtree(os.path.join(HISTORY_ROOT, d))
                removed += 1
            except OSError:
                pass
    return removed


def _load_snapshot(date_str: str) -> Optional[dict]:
    path = os.path.join(HISTORY_ROOT, date_str, BRAIN_FILE)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.loads(f.read().replace("NaN", "null"))
    except (OSError, json.JSONDecodeError):
        return None


def backfill_actual_returns(
    portfolio: dict,
    lag_days: int = BACKFILL_LAG_DAYS,
) -> tuple[int, int]:
    """lag_days 전 스냅샷의 actual_return_3d 를 오늘 가격으로 채운다.

    반환: (filled_count, total_in_lag_snapshot). 스냅샷 부재 시 (0, 0).
    """
    target_date = (now_kst().date() - timedelta(days=lag_days)).strftime("%Y%m%d")
    snap = _load_snapshot(target_date)
    if not snap:
        return 0, 0

    today_prices: dict[str, float] = {}
    for r in portfolio.get("recommendations") or []:
        tkr = r.get("ticker")
        px = r.get("price")
        if not tkr or px in (None, 0):
            continue
        try:
            today_prices[tkr] = float(px)
        except (TypeError, ValueError):
            continue

    filled = 0
    stocks = snap.get("stocks") or []
    for s in stocks:
        if s.get("actual_return_3d") is not None:
            continue
        tkr = s.get("ticker")
        base = s.get("price")
        if not tkr or base in (None, 0):
            continue
        cur = today_prices.get(tkr)
        if cur is None:
            continue
        try:
            base_f = float(base)
            if base_f == 0:
                continue
            s["actual_return_3d"] = (cur - base_f) / base_f
            filled += 1
        except (TypeError, ValueError, ZeroDivisionError):
            continue

    if filled:
        path = os.path.join(HISTORY_ROOT, target_date, BRAIN_FILE)
        _atomic_write(path, snap)

    return filled, len(stocks)
