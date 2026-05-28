#!/usr/bin/env python3
"""
n_counter.py — N (산식 안정 검증 거래일) counter cron

WHY: 메모 project_minimum_n_milestones_2026_05_18 정합. N = 산식 안정 검증
거래일 누적. RULE 7 + IC 통계 게이트 (Fama-MacBeth 252 / Bailey-Lopez 684)
박은 부분 박은 trail.

입력:
  - data/metadata/n_reset_policy.json (사용자 박은 정책, 5/28 박힘)

출력:
  - data/metadata/n_counter.json (현재 N + history + next_milestone)

동작:
  - 매일 cron N+1 박음 (calendar day + trading day 둘 다)
  - reset history 마지막 entry 박은 부분 박은 박은 박은 박은 today 박은 부분 박은 박은 박은 박은 N 계산
  - milestones (30 / 100 / 252 / 684) 박은 부분 박은 next milestone + 박은 부분 박은 박은 박은 박은 박은
  - trading day = weekday < 5 (월~금) 단순 박음. 박은 KR 휴장일 list 박지 X (별 sprint).

운영: .github/workflows/n_counter.yml 매일 KST 09:30
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict

_ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = _ROOT / "data" / "metadata" / "n_reset_policy.json"
COUNTER_PATH = _ROOT / "data" / "metadata" / "n_counter.json"
KST = timezone(timedelta(hours=9))


def _today_kst() -> date:
    return datetime.now(KST).date()


def _trading_days_between(start: date, end: date) -> int:
    """start (제외) ~ end (포함) trading day count. 단순 weekday < 5 박음."""
    if end < start:
        return 0
    n = 0
    cur = start + timedelta(days=1)
    while cur <= end:
        if cur.weekday() < 5:  # 0=월 ~ 4=금
            n += 1
        cur += timedelta(days=1)
    return n


def _load_policy() -> Dict[str, Any]:
    if not POLICY_PATH.exists():
        sys.exit(f"::error::n_reset_policy.json 부재 ({POLICY_PATH})")
    with POLICY_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def _next_milestone(n_trading: int, milestones: Dict[str, str]) -> Dict[str, Any]:
    """다음 milestone 박은 부분 박은 박은 박은 박은 박은 박은 박은 박은 박은 박은 박은 N 박은 부분 박은 박은 박은 박은."""
    thresholds = sorted([int(k.split("_")[1]) for k in milestones.keys() if k.startswith("n_")])
    for t in thresholds:
        if n_trading < t:
            return {
                "next_n": t,
                "days_remaining": t - n_trading,
                "label": milestones.get(f"n_{t}", "")[:100],
            }
    return {"next_n": None, "days_remaining": 0, "label": "all milestones reached"}


def main() -> int:
    policy = _load_policy()
    history = policy.get("history", [])
    milestones = policy.get("milestones", {})

    if not history:
        sys.exit("::error::n_reset_policy.json history 빈 list — reset entry 박지 X")

    last_reset = history[-1]
    last_reset_date = date.fromisoformat(last_reset["date"])
    today = _today_kst()

    n_calendar = (today - last_reset_date).days
    n_trading = _trading_days_between(last_reset_date, today)

    next_ms = _next_milestone(n_trading, milestones)

    counter = {
        "as_of": datetime.now(KST).isoformat(timespec="seconds"),
        "last_reset": {
            "date": last_reset["date"],
            "trigger": last_reset.get("trigger"),
            "note": last_reset.get("note"),
        },
        "n_calendar_days": n_calendar,
        "n_trading_days": n_trading,
        "next_milestone": next_ms,
        "history_count": len(history),
        "policy_version": policy.get("version"),
    }

    COUNTER_PATH.parent.mkdir(parents=True, exist_ok=True)
    with COUNTER_PATH.open("w", encoding="utf-8") as f:
        json.dump(counter, f, ensure_ascii=False, indent=2)

    print(f"n_counter 박힘: N_trading={n_trading} / N_calendar={n_calendar}")
    print(f"  last_reset: {last_reset['date']} ({last_reset.get('trigger')})")
    print(f"  next milestone: n_{next_ms['next_n']} ({next_ms['days_remaining']}일 남음)")
    print(f"                  → {next_ms['label']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
