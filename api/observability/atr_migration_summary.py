"""
ATR Migration Summary — Phase 0 (SMA→Wilder EMA) 검증 데이터.

portfolio.json 의 `atr_migration` key 에 기록됨. AdminDashboard CardATRMigration
이 fetch 해서 운영 가시성 제공.

Phase 0 verdict (5/16) 까지 outlier 추세 + diff 분포 추적.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from api.config import now_kst  # tz-aware KST (datetime.now() naive 금지, RULE)
from typing import Any, Dict, List

LOG_PATH = Path("data/metadata/atr_migration_log.jsonl")
COUNTER_PATH = Path("data/metadata/atr_migration_outlier_counter.json")
OUTLIER_DIFF_PCT_THRESHOLD = 30.0


def _load_counter() -> Dict[str, Any]:
    if not COUNTER_PATH.exists():
        return {"date": "", "tickers": [], "alerted": False}
    try:
        return json.loads(COUNTER_PATH.read_text())
    except Exception:
        return {"date": "", "tickers": [], "alerted": False}


def _read_recent_log(days: int = 7) -> List[Dict[str, Any]]:
    if not LOG_PATH.exists():
        return []
    # 비교 대상 dt=fromisoformat(split('+')) = naive → cutoff 도 naive KST 로 유지
    cutoff = now_kst().replace(tzinfo=None) - timedelta(days=days)
    out: List[Dict[str, Any]] = []
    try:
        with LOG_PATH.open() as f:
            for line in f:
                try:
                    rec = json.loads(line)
                    ts = rec.get("timestamp", "")
                    if not ts:
                        continue
                    dt = datetime.fromisoformat(ts.split("+")[0])
                    if dt >= cutoff:
                        out.append(rec)
                except Exception:
                    continue
    except Exception:
        return []
    return out


def compute_atr_migration_summary() -> Dict[str, Any]:
    """ATR 마이그레이션 V0 요약 — 오늘 outlier + 7일 분포."""
    counter = _load_counter()
    recent = _read_recent_log(days=7)

    # 오늘 outlier
    today_tickers = counter.get("tickers") or []
    today_count = len(today_tickers)

    # 7일 outlier (≥30% diff) — unique 단위
    outliers_7d_set: Dict[str, Dict[str, Any]] = {}
    diffs: List[float] = []
    for r in recent:
        diff = r.get("diff_pct")
        if diff is None:
            continue
        diffs.append(abs(float(diff)))
        if abs(diff) >= OUTLIER_DIFF_PCT_THRESHOLD:
            t = r.get("ticker", "")
            if not t:
                continue
            # 해당 ticker 의 *최신 record* 보관
            if t not in outliers_7d_set or r.get("timestamp", "") > outliers_7d_set[t].get("timestamp", ""):
                outliers_7d_set[t] = r

    # diff 분포
    diff_distribution = {
        "total_records": len(diffs),
        "outlier_count_7d": len(outliers_7d_set),
        "max_diff_pct": round(max(diffs), 2) if diffs else 0.0,
        "median_diff_pct": round(sorted(diffs)[len(diffs) // 2], 2) if diffs else 0.0,
    }

    # outlier ticker 상세 (최대 10건, diff_pct 큰 순)
    outlier_details = sorted(
        outliers_7d_set.values(),
        key=lambda r: abs(float(r.get("diff_pct") or 0)),
        reverse=True,
    )[:10]
    outlier_compact = [
        {
            "ticker": r.get("ticker"),
            "atr_wilder_pct": r.get("atr_wilder_pct"),
            "atr_sma_pct": r.get("atr_sma_pct"),
            "diff_pct": r.get("diff_pct"),
            "last_seen": (r.get("timestamp") or "")[:16],
        }
        for r in outlier_details
    ]

    return {
        "as_of": now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "phase": "phase_0",  # 5/16 verdict 까지
        "verdict_date": "2026-05-16",
        "today": {
            "date": counter.get("date", ""),
            "outlier_count": today_count,
            "outlier_tickers": today_tickers[:20],
            "alerted": bool(counter.get("alerted", False)),
            "threshold": 5,
        },
        "last_7d": diff_distribution,
        "outlier_details": outlier_compact,
        "model_meta": {
            "wilder_ema_period": 14,
            "sma_period": 14,
            "outlier_threshold_pct": OUTLIER_DIFF_PCT_THRESHOLD,
            "version": "v0",
        },
    }
