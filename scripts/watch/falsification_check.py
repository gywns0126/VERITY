#!/usr/bin/env python3
"""
falsification_check — 사전등록한 반증 조건을 기계적으로 훑는다.

2026-08-24 신설 (PM 지시). 계기 = PM 이 XE 를 매수한 직후 "매매 결정이 별로였나" 라고 물었고,
그 시점에 유일하게 값이 있는 일이 **무엇이 이 결정을 틀린 것으로 만들지를 미리 정해두는 것**
이었다. 가격이 더 빠진 뒤에 정하면 조건이 감정을 따라 움직인다.

🚨 **이 스크립트는 판정하지 않는다.** 사전등록된 임계와 현재 관측을 대조해 `trip / hold /
manual` 만 찍는다. 임계를 여기서 바꾸지 말 것 — 변경은 `pm_actions.jsonl` 에 사유와 함께
**새 행으로 append** 한다(원본 수정 금지).

입력 = private/decisions/pm_actions.jsonl (사전등록 · gitignore) +
       data/metadata/lockup_watch.jsonl (관측 · 공개)
🚨 private 은 public repo 에서 gitignore 라 **CI 에서는 조건이 안 잡힌다** — 오퍼레이터 로컬 전용.

usage: python scripts/watch/falsification_check.py [--ticker XE]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

_ROOT = str(Path(__file__).resolve().parent.parent.parent)
ACTIONS = os.path.join(_ROOT, "private", "decisions", "pm_actions.jsonl")
WATCH = os.path.join(_ROOT, "data", "metadata", "lockup_watch.jsonl")


def _rows(path: str) -> List[Dict[str, Any]]:
    try:
        with open(path, encoding="utf-8") as f:
            return [json.loads(l) for l in f if l.strip()]
    except (OSError, json.JSONDecodeError):
        return []


def _latest(rows: List[Dict[str, Any]], **eq: Any) -> Optional[Dict[str, Any]]:
    hits = [r for r in rows if all(r.get(k) == v for k, v in eq.items())]
    return hits[-1] if hits else None


def check_c1(crit: Dict[str, Any], obs: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """아마존 지분 — 🚨 pct 가 아니라 **shares** 로 본다.

    희석이 일어나면 매도 없이도 pct 가 내려간다. pct 하락을 매도로 읽으면 틀린다.
    """
    base = crit.get("baseline")
    if obs is None:
        return {"state": "no_obs", "detail": "관측 행 없음 — lockup_watch.jsonl 미생성"}
    holders = obs.get("holders") or []
    amzn = next((h for h in holders if "Amazon" in str(h.get("filer") or "")), None)
    if amzn is None:
        return {"state": "trip", "detail": f"13G 목록에서 아마존 이탈 (관측 {obs.get('holdings_as_of')})"}
    cur = amzn.get("shares")
    if cur is None or base is None:
        return {"state": "no_obs", "detail": "shares 결측 — 0 으로 채우지 않는다"}
    delta = int(cur) - int(base)
    pct = delta / int(base) * 100
    if delta >= 0:
        state = "hold"
    elif pct <= -20:
        state = "trip"
    else:
        state = "watch"      # 감소했으나 반증 임계(-20%) 미만 = 1차 경보
    return {"state": state, "baseline": base, "current": cur,
            "delta_shares": delta, "delta_pct": round(pct, 2),
            "pct_reported": amzn.get("pct"),
            "as_of": obs.get("holdings_as_of"),
            "detail": "🚨 pct 아닌 shares 기준 (희석으로도 pct 는 내려간다)"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", default="XE")
    a = ap.parse_args()
    tk = a.ticker

    acts = _rows(ACTIONS)
    if not acts:
        print(f"[falsify] {ACTIONS} 없음 — private 은 public repo 에서 gitignore 다. "
              f"오퍼레이터 로컬에서만 잡힌다.", file=sys.stderr)
        return 0
    reg = _latest(acts, ticker=tk, action="반증조건 사전등록")
    if not reg:
        print(f"[falsify] {tk} 사전등록 없음", file=sys.stderr)
        return 0
    obs = _latest(_rows(WATCH), ticker=tk)

    print(f"[falsify] {tk} — 사전등록 {reg['ts_kst'][:16]} · 관측 {(obs or {}).get('ts_kst','없음')[:16]}")
    trips = []
    for c in reg.get("criteria", []):
        if c["id"] == "C1":
            r = check_c1(c, obs)
            mark = {"hold": "·", "watch": "🔔", "trip": "🚨", "no_obs": "?"}[r["state"]]
            extra = (f"{r.get('current'):,}주 vs 기준 {r.get('baseline'):,}주 "
                     f"({r.get('delta_pct'):+.2f}%)" if r.get("current") else r["detail"])
            print(f"  {mark} {c['id']} {c['label']:16s} {r['state']:6s} {extra}")
            if r["state"] == "trip":
                trips.append(c["id"])
        else:
            print(f"  ○ {c['id']} {c['label']:16s} manual  {c['checked_by']}")
    nc = reg.get("not_covered") or []
    if nc:
        print(f"  ── 반증 축이 아닌 것 {len(nc)}: " + " · ".join(x.split(" —")[0] for x in nc))
    if trips:
        print(f"[falsify] 🚨 반증 성립: {trips} — 사전등록 임계 도달. 임계를 옮기지 말 것.",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
