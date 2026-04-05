"""
VERITY — 일일 데이터 아카이빙

매 full 분석 후 portfolio.json 스냅샷을 data/history/YYYY-MM-DD.json 으로 저장.
주간/월간/분기 정기 리포트의 원천 데이터로 활용.
"""
from __future__ import annotations

import json
import os
import glob
from datetime import timedelta
from typing import Optional
from api.config import DATA_DIR, now_kst

HISTORY_DIR = os.path.join(DATA_DIR, "history")


def _ensure_dir():
    os.makedirs(HISTORY_DIR, exist_ok=True)


def archive_daily_snapshot(portfolio: dict) -> str:
    """오늘자 portfolio 스냅샷을 history/YYYY-MM-DD.json 으로 저장."""
    _ensure_dir()
    today = now_kst().strftime("%Y-%m-%d")
    path = os.path.join(HISTORY_DIR, f"{today}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(portfolio, f, ensure_ascii=False, default=str)
    return path


def load_snapshot(date_str: str) -> Optional[dict]:
    """특정 날짜(YYYY-MM-DD) 스냅샷 로드. 없으면 None."""
    path = os.path.join(HISTORY_DIR, f"{date_str}.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        txt = f.read().replace("NaN", "null")
        return json.loads(txt)


def load_snapshots_range(days: int) -> list[dict]:
    """최근 N일간의 스냅샷을 날짜 오름차순으로 로드."""
    _ensure_dir()
    today = now_kst().date()
    results = []
    for i in range(days, 0, -1):
        d = today - timedelta(days=i)
        snap = load_snapshot(d.strftime("%Y-%m-%d"))
        if snap:
            snap["_date"] = d.strftime("%Y-%m-%d")
            results.append(snap)
    today_snap = load_snapshot(today.strftime("%Y-%m-%d"))
    if today_snap:
        today_snap["_date"] = today.strftime("%Y-%m-%d")
        results.append(today_snap)
    return results


def list_available_dates() -> list[str]:
    """아카이빙된 날짜 목록을 오름차순으로."""
    _ensure_dir()
    files = glob.glob(os.path.join(HISTORY_DIR, "*.json"))
    dates = sorted(os.path.basename(f).replace(".json", "") for f in files)
    return dates


def cleanup_old_snapshots(keep_days: int = 400):
    """오래된 스냅샷 정리 (기본 400일 보관)."""
    _ensure_dir()
    cutoff = (now_kst().date() - timedelta(days=keep_days)).strftime("%Y-%m-%d")
    for f in glob.glob(os.path.join(HISTORY_DIR, "*.json")):
        date_str = os.path.basename(f).replace(".json", "")
        if date_str < cutoff:
            os.remove(f)
