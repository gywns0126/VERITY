#!/usr/bin/env python3
"""멀티배거 워치 → 알파콘솔(오퍼레이터) 발행물. 🚨 산식 변경 0 · 신호 재계산 0.

`data/metadata/multibagger_watch.jsonl`(누적 로그)의 **최신 일자만** 잘라
`data/multibagger_watch.json` 으로 낸다. 소비 체인:

    이 스크립트 → data/multibagger_watch.json
      → scripts/upload_operator_data_to_supabase.py → _operator/multibagger_watch.json
      → vercel-api/api/admin.py ROUTES["multibagger"]
      → operator-web fetchOperator("multibagger") → MultibaggerPanel

🚨 **오퍼레이터 전용**이다. 공개 사이트·발행 파일·framer-components 에 싣지 않는다
(종목 상담·분석·추천 = 유사투자자문 회피, PM 2026-08-03).

🚨 **로깅 전용이라는 사실을 산출물이 스스로 말한다** (RULE 12 #2).
   생산자가 `note = "로깅 전용 — 결정 0 (active gate 2026-09)"` 를 달고 있으므로
   그대로 실어 UI 가 이를 판단 신호로 오인하지 않게 한다.

🚨 **커버리지도 자기신고한다.** `revenue_acceleration` 의 연속가속 방어는
`quarterly_revenue` 를 요구하는데 DART 백필이 미완(2026-08-21 기준 960/7,664)이라
대부분 "quarterly_history 미수집 (가속 연속성 평가 불가)" 상태다. 그 비율을 신고하지
않으면 화면이 "검증된 신호" 처럼 보인다.
"""
from __future__ import annotations

import collections
import json
import os
import sys
from typing import Any, Dict, List

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(ROOT, "data", "metadata", "multibagger_watch.jsonl")
OUT = os.path.join(ROOT, "data", "multibagger_watch.json")

# 화면에 싣는 상한. 오늘 실측 alert>=2 가 76종목이라 여유를 둔다.
TOP_N = 120
# 이 문자열이 reason 에 있으면 연속가속 방어가 죽은 상태 (백필 미완)
_UNCOVERED_MARK = "quarterly_history 미수집"


def _load_latest() -> tuple:
    if not os.path.exists(SRC):
        return "", []
    rows: List[Dict[str, Any]] = []
    with open(SRC, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    if not rows:
        return "", []
    latest = max((r.get("watch_date") or "") for r in rows)
    return latest, [r for r in rows if r.get("watch_date") == latest]


def build() -> Dict[str, Any]:
    latest, today = _load_latest()
    if not today:
        return {"_meta": {"error": "no_rows", "source": os.path.relpath(SRC, ROOT)}, "items": []}

    sig_names = sorted({k for r in today for k in (r.get("signals") or {})})
    fired = collections.Counter()
    uncovered = 0
    for r in today:
        sigs = r.get("signals") or {}
        for k, v in sigs.items():
            if isinstance(v, dict) and v.get("triggered"):
                fired[k] += 1
        acc = sigs.get("revenue_acceleration") or {}
        if _UNCOVERED_MARK in str(acc.get("reason") or ""):
            uncovered += 1

    ranked = sorted(
        today,
        key=lambda r: (
            -int(r.get("alert_count") or 0),
            -max((int((v or {}).get("score") or 0)
                  for v in (r.get("signals") or {}).values()
                  if isinstance(v, dict)), default=0),
        ),
    )

    items = []
    for r in ranked[:TOP_N]:
        sigs = r.get("signals") or {}
        items.append({
            "ticker": r.get("ticker"),
            "name": r.get("name"),
            "sector": r.get("sector"),
            "market_cap": r.get("market_cap"),
            "lynch_class": r.get("lynch_class"),
            "lynch_data_quality": r.get("lynch_data_quality"),
            "alert_count": r.get("alert_count"),
            # 발화한 신호만 싣는다 — 미발화까지 실으면 페이로드가 4배가 되고 화면에도 안 쓴다
            "fired": {k: {"score": v.get("score"), "reason": v.get("reason")}
                      for k, v in sigs.items()
                      if isinstance(v, dict) and v.get("triggered")},
        })

    n = len(today)
    return {
        "_meta": {
            # 🚨 분모 먼저 (RULE 13)
            "watch_date": latest,
            "universe_n": n,
            "published_n": len(items),
            "top_n_cap": TOP_N,
            "spec_version": (today[0].get("spec_version") if today else None),
            # 🚨 생산자의 자기신고를 그대로 옮긴다 — UI 가 판단 신호로 오인하지 않도록
            "producer_note": (today[0].get("note") if today else None),
            "decision_use": False,
            "decision_note": (
                "로깅 전용 — 이 패널은 관측이지 매매 판단이 아니다. "
                "생산자 note 의 active gate 이전에는 결정에 쓰지 않는다."
            ),
            "signals_defined": sig_names,
            "fired_counts": dict(fired),
            "alert_count_dist": dict(sorted(collections.Counter(
                int(r.get("alert_count") or 0) for r in today).items())),
            # 🚨 커버리지 자기신고 — 연속가속 방어가 죽은 비율
            "acceleration_uncovered_n": uncovered,
            "acceleration_uncovered_pct": round(uncovered / n * 100, 1) if n else None,
            "coverage_note": (
                "revenue_acceleration 의 연속가속 방어는 quarterly_revenue 를 요구한다. "
                "DART 분기매출 백필이 미완이면 그 방어가 꺼진 채 발화한다 — "
                "위 비율이 그 상태의 종목 수다."
            ),
            "operator_only": True,
            "source": os.path.relpath(SRC, ROOT),
        },
        "items": items,
    }


def main() -> int:
    data = build()
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    m = data["_meta"]
    size = os.path.getsize(OUT)
    print(f"[multibagger] {OUT} · {size:,}B")
    print(f"  watch_date {m.get('watch_date')} · 유니버스 {m.get('universe_n')} "
          f"→ 발행 {m.get('published_n')}")
    print(f"  발화: {m.get('fired_counts')}")
    print(f"  🚨 연속가속 방어 꺼짐 {m.get('acceleration_uncovered_n')}/{m.get('universe_n')} "
          f"= {m.get('acceleration_uncovered_pct')}%")
    print(f"  🚨 decision_use={m.get('decision_use')} — {m.get('producer_note')}")
    return 0 if data.get("items") else 1


if __name__ == "__main__":
    raise SystemExit(main())
