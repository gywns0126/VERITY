#!/usr/bin/env python3
"""창(window)으로 자른 집계를 **변경 경계에서 쪼개** 보여준다. (2026-08-19 신설)

## 왜 — 하루에 세 번 같은 오답을 냈다

시계열 원장을 "최근 N일" 로 자르고 그 안의 비율을 현재 상태로 읽었다. 그런데 그 창 안에
**코드/설정이 바뀐 시점**이 있으면, 앞뒤가 섞인 비율은 현재를 말하지 않는다.

| 내가 낸 답 | 실제 |
|---|---|
| `factor_version` 도장률 **402행 중 201** → "실질 1순위 결함" | 배포가 8/17 23:44. 배포 후 **100%**. 날짜로 자르고 **시각을 안 봤다** |
| LLM `stock_analysis` **30일 1,823회 $5.01** → "최대 절감 후보" | 스위치 OFF 가 8/16. 이후 **0회 $0** |
| `self_assets` cron_health **7일 fail 45~55%** → ALERT | FAIL 은 8/15~17 잔상. 8/17 이후만 보면 **8.2%** |

셋 다 **결함이 아닌 것을 결함으로**, 또는 **이미 고친 것을 미해결로** 보고했다.
공통 형태 = *창 안에 경계가 있는데 통짜로 셌다.*

🚨 RULE 13(분모 먼저)의 사각이다. 분모는 셌는데 **그 분모가 두 시기의 혼합**이었다.

## 쓰는 법

    python3 scripts/audit/window_split_at_boundary.py \
        --ledger data/metadata/prediction_trail.jsonl \
        --ts-field created_at \
        --boundary-path api/quant/factors/version.py \
        --field factor_version --days 3

`--boundary-path` 의 **마지막 커밋 시각**을 경계로 앞뒤를 나눠 센다. 경계를 직접 알 때는
`--boundary "2026-08-16T00:00:00+09:00"` 로 준다.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _parse_ts(v):
    if not isinstance(v, str):
        return None
    s = v[:-1] + "+00:00" if v.endswith("Z") else v
    try:
        d = datetime.fromisoformat(s)
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def boundary_from_path(path: str):
    """해당 경로의 **마지막 커밋 시각** = 변경 경계."""
    r = subprocess.run(["git", "-C", _ROOT, "log", "-1", "--format=%aI", "--", path],
                       capture_output=True, text=True)
    out = (r.stdout or "").strip()
    return _parse_ts(out) if out else None


def split(ledger: str, ts_field: str, boundary, field=None, days=None):
    rows = []
    with open(ledger, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
    now = datetime.now(timezone.utc)
    win = []
    for e in rows:
        d = _parse_ts(e.get(ts_field))
        if d is None:
            continue
        if days is not None and (now - d).total_seconds() > days * 86400:
            continue
        win.append((d, e))
    before = [e for d, e in win if d < boundary]
    after = [e for d, e in win if d >= boundary]

    def _stat(group):
        n = len(group)
        if not field:
            return {"n": n}
        filled = sum(1 for e in group if e.get(field) not in (None, "", [], {}))
        return {"n": n, "filled": filled, "pct": round(100.0 * filled / n, 1) if n else None}

    return {"boundary": boundary.isoformat(), "window_n": len(win),
            "before": _stat(before), "after": _stat(after)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ledger", required=True)
    ap.add_argument("--ts-field", required=True)
    ap.add_argument("--boundary")
    ap.add_argument("--boundary-path")
    ap.add_argument("--field")
    ap.add_argument("--days", type=float)
    a = ap.parse_args()

    b = _parse_ts(a.boundary) if a.boundary else (
        boundary_from_path(a.boundary_path) if a.boundary_path else None)
    if b is None:
        print("🚨 경계를 정하지 못했다 — --boundary 또는 --boundary-path 필요", file=sys.stderr)
        return 2

    r = split(os.path.join(_ROOT, a.ledger), a.ts_field, b, a.field, a.days)
    print(f"경계 = {r['boundary']}  · 창 내 {r['window_n']}행")
    for side in ("before", "after"):
        s = r[side]
        tail = f" · {a.field} 채움 {s['filled']}/{s['n']} = {s['pct']}%" if a.field and s["n"] else ""
        print(f"  {side:7} {s['n']:>6}행{tail}")
    ba, aa = r["before"], r["after"]
    if a.field and ba["n"] and aa["n"] and ba.get("pct") is not None:
        if abs((aa["pct"] or 0) - (ba["pct"] or 0)) >= 20:
            print("\n🚨 경계 앞뒤가 크게 다르다 — **통짜 비율을 현재 상태로 읽지 말 것**.")
            print(f"   현재 상태 = after 쪽 {aa['pct']}% (before {ba['pct']}% 는 옛 코드의 산물)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
