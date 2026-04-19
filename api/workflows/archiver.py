"""
VERITY — 일일 데이터 아카이빙

매 full/quick 분석 후 portfolio.json 스냅샷을 두 곳에 저장한다.

1) history/YYYY-MM-DD.json  — 그날의 "최종본" (기존 호환, 당일 마지막 실행이 덮어씀)
2) history/runs/YYYY-MM-DD_HHMM_{mode}.json — 실행별 감사 로그 (덮어쓰기 금지)

Postmortem·Evolver·backtest_archive 는 (1) 을 그대로 사용하고,
(2) 는 Brain 점수/등급/추천의 중간 변화 추적·감사용으로 남긴다.
"""
from __future__ import annotations

import json
import os
import glob
from datetime import timedelta
from typing import Optional
from api.config import DATA_DIR, now_kst

HISTORY_DIR = os.path.join(DATA_DIR, "history")
RUNS_DIR = os.path.join(HISTORY_DIR, "runs")


def _ensure_dir():
    os.makedirs(HISTORY_DIR, exist_ok=True)
    os.makedirs(RUNS_DIR, exist_ok=True)


def archive_daily_snapshot(portfolio: dict, mode: Optional[str] = None) -> str:
    """오늘자 portfolio 스냅샷을 저장한다.

    - history/YYYY-MM-DD.json 은 당일 최종본(덮어쓰기).
    - history/runs/YYYY-MM-DD_HHMM_{mode}.json 은 실행별 감사 로그(보존).

    반환값은 기존 호환을 위해 "당일 최종본" 경로.
    """
    _ensure_dir()
    now = now_kst()
    today = now.strftime("%Y-%m-%d")
    stamp = now.strftime("%H%M")
    safe_mode = (mode or "run").replace("/", "_").replace(" ", "_")

    canonical = os.path.join(HISTORY_DIR, f"{today}.json")
    with open(canonical, "w", encoding="utf-8") as f:
        json.dump(portfolio, f, ensure_ascii=False, default=str)

    run_path = os.path.join(RUNS_DIR, f"{today}_{stamp}_{safe_mode}.json")
    try:
        with open(run_path, "w", encoding="utf-8") as f:
            json.dump(portfolio, f, ensure_ascii=False, default=str)
    except Exception:
        pass

    return canonical


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


def cleanup_old_snapshots(keep_days: int = 400, keep_runs_days: int = 90):
    """오래된 스냅샷 정리.

    - 캐논(YYYY-MM-DD.json): 기본 400일 보관.
    - 실행별(runs/YYYY-MM-DD_HHMM_*.json): 기본 90일 보관 (용량 보호).
    """
    _ensure_dir()
    today = now_kst().date()
    cutoff_daily = (today - timedelta(days=keep_days)).strftime("%Y-%m-%d")
    cutoff_runs = (today - timedelta(days=keep_runs_days)).strftime("%Y-%m-%d")

    for f in glob.glob(os.path.join(HISTORY_DIR, "*.json")):
        date_str = os.path.basename(f).replace(".json", "")
        if len(date_str) == 10 and date_str < cutoff_daily:
            try:
                os.remove(f)
            except OSError:
                pass

    for f in glob.glob(os.path.join(RUNS_DIR, "*.json")):
        name = os.path.basename(f)
        date_str = name[:10]
        if len(date_str) == 10 and date_str < cutoff_runs:
            try:
                os.remove(f)
            except OSError:
                pass
