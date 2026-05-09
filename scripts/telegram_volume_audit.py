#!/usr/bin/env python3
"""telegram_volume_audit — quiet hours v0 효과 측정.

5/8 baseline ~50통/일 → 5/15 재측정 (project_telegram_quiet_hours_v0).
data/telegram_volume.jsonl 을 읽어 일별 outcome 분포 + baseline 비교 + verdict 출력.

사용:
  python scripts/telegram_volume_audit.py                 # 전체
  python scripts/telegram_volume_audit.py --since 7       # 직전 7일
  python scripts/telegram_volume_audit.py --baseline 50   # baseline 통수 비교
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any, Dict, List

LEDGER_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "telegram_volume.jsonl",
)


def _load_ledger() -> List[Dict[str, Any]]:
    if not os.path.isfile(LEDGER_PATH):
        return []
    out: List[Dict[str, Any]] = []
    with open(LEDGER_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def _date_kst(ts: str) -> str:
    return (ts or "")[:10]


def _aggregate(entries: List[Dict[str, Any]]) -> Dict[str, Counter]:
    by_date: Dict[str, Counter] = defaultdict(Counter)
    for e in entries:
        d = _date_kst(e.get("ts_kst", ""))
        if not d:
            continue
        by_date[d][str(e.get("outcome") or "unknown")] += 1
        by_date[d]["__total__"] += 1
        if e.get("bypass_quiet"):
            by_date[d]["__bypass__"] += 1
    return by_date


def _verdict(daily_sent_avg: float, baseline: float) -> str:
    if baseline <= 0:
        return "no_baseline"
    ratio = daily_sent_avg / baseline
    if ratio < 0.5:
        return "✅ PASS — 50% 미만 통수 (quiet hours v0 효과적)"
    elif ratio < 0.8:
        return "🟡 MARGINAL — 50~80% 구간 (v0 일부 효과, v1 검토)"
    else:
        return "🔴 FAIL — 80% 이상 (v1 rate-limit/digest 즉시 진입)"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--since", type=int, default=0, help="직전 N일만 (0=전체)")
    p.add_argument("--baseline", type=float, default=50.0, help="baseline 통수/일")
    args = p.parse_args()

    entries = _load_ledger()
    if not entries:
        print(f"[audit] {LEDGER_PATH} 비어있음 — 적재 hook 실행 후 재측정")
        return 1

    if args.since > 0:
        cutoff = (datetime.utcnow().date()).isoformat()
        # 단순 string 비교 (KST 일자 기준 그대로)
        from datetime import timedelta
        cutoff_d = (datetime.utcnow().date() - timedelta(days=args.since)).isoformat()
        entries = [e for e in entries if _date_kst(e.get("ts_kst", "")) >= cutoff_d]

    by_date = _aggregate(entries)

    if not by_date:
        print("[audit] 기간 내 entry 없음")
        return 1

    dates = sorted(by_date.keys())
    print(f"\n=== telegram volume audit ({dates[0]} ~ {dates[-1]}, {len(dates)}일) ===\n")
    print(f"{'date':<12} {'sent':>5} {'quiet':>6} {'dedupe':>7} {'fail':>5} {'total':>6} {'bypass':>7}")
    print("-" * 60)

    sent_total = 0
    for d in dates:
        c = by_date[d]
        sent = c.get("sent", 0)
        quiet = c.get("quiet_skip", 0)
        dedupe = c.get("dedupe_skip", 0)
        fail = c.get("api_fail", 0) + c.get("exception", 0) + c.get("no_token", 0)
        total = c.get("__total__", 0)
        bypass = c.get("__bypass__", 0)
        sent_total += sent
        print(f"{d:<12} {sent:>5} {quiet:>6} {dedupe:>7} {fail:>5} {total:>6} {bypass:>7}")

    avg_sent = sent_total / len(dates)
    print("-" * 60)
    print(f"avg sent/일: {avg_sent:.1f} (baseline {args.baseline:.0f})")
    print(f"verdict: {_verdict(avg_sent, args.baseline)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
