#!/usr/bin/env python3
"""R3 — 문헌 4축의 **변별 소멸** 감시. (2026-08-18, PREREG_BASELINE_V1_LITERATURE §7-C)

## 왜 두 기준인가

§7-C 최초안은 "고유값 ≤ 2" 였다. 실측하니 현재 고유값이 **28 / 17 / 26 / 23** 이라
2 까지 떨어지려면 사실상 완전 상수화 이후다 — 걸릴 때는 이미 늦다. 그래서 5 로 올리려다
한 가지를 더 봤다: **고유값 임계는 N 에 의존한다.** 지금은 운영 풀이 56 종목이라
17~28 이 나오지만, 풀이 10 종목으로 줄면 고유값도 자연히 줄어 **정상 운영이 오탐**된다.

그래서 N 무관한 기준을 하나 더 둔다 — **최빈값 점유율**. 한 값이 종목 대부분을 덮으면
그 축은 변별하지 않는 것이고, 이건 풀 크기와 무관하다.

실측(2026-08-18, N=56): 최빈 점유 graham 10.7% · canslim 23.2% · quality 16.1% ·
volatility 17.9%. 최악이 23.2% 라 임계 50% 까지 여유가 26.8%p 다.

## 판정

축 하나라도 아래 중 하나면 R3 발동:
  · 고유값 ≤ 5           (절대 바닥 — 완전 상수화 직전)
  · 최빈값 점유 > 50%     (N 무관 — 한 값이 과반을 덮음)

🚨 이건 **점수를 바꾸지 않는다.** 관측·신고 전용이다.
"""
from __future__ import annotations

import collections
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

AXES = ("graham_value", "canslim_growth", "quant_quality", "quant_volatility")
MIN_UNIQUE = 5        # 이하면 발동 (절대 바닥)
MAX_MODAL_SHARE = 0.50  # 초과면 발동 (N 무관)
MIN_SAMPLE = 10       # 이 미만이면 판정 보류 — 표본이 적으면 무엇이든 상수처럼 보인다


def collect(portfolio: dict) -> dict:
    out = {a: [] for a in AXES}
    for rec in (portfolio.get("recommendations") or []):
        comp = (((rec.get("verity_brain") or {}).get("fact_score") or {})
                .get("components") or {})
        for a in AXES:
            v = comp.get(a)
            if isinstance(v, (int, float)):
                out[a].append(float(v))
    return out


def audit(portfolio: dict) -> dict:
    vals = collect(portfolio)
    rows, fired = [], []
    for a in AXES:
        v = vals[a]
        n = len(v)
        if n < MIN_SAMPLE:
            rows.append({"axis": a, "n": n, "verdict": "판정 보류(표본 부족)"})
            continue
        cnt = collections.Counter(v)
        uniq = len(cnt)
        share = cnt.most_common(1)[0][1] / n
        why = []
        if uniq <= MIN_UNIQUE:
            why.append(f"고유값 {uniq} ≤ {MIN_UNIQUE}")
        if share > MAX_MODAL_SHARE:
            why.append(f"최빈 점유 {share:.1%} > {MAX_MODAL_SHARE:.0%}")
        rows.append({"axis": a, "n": n, "unique": uniq,
                     "modal_share": round(share, 4),
                     "verdict": "🚨 변별 소멸" if why else "정상",
                     "why": why})
        if why:
            fired.append(f"{a}: {' · '.join(why)}")
    return {"rows": rows, "fired": fired,
            "severity": "FAIL" if fired else "OK",
            "note": "R3 관측 전용 — 점수 변경 없음 (PREREG_BASELINE_V1_LITERATURE §7-C)"}


def main() -> int:
    path = os.path.join(_ROOT, "data", "portfolio.json")
    try:
        with open(path, encoding="utf-8") as f:
            pf = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"[axis_discrimination] 산출물 없음/파손 — skip: {e}")
        return 0
    r = audit(pf)
    print(f"[axis_discrimination] {r['severity']}")
    for row in r["rows"]:
        if "unique" in row:
            print(f"  {row['axis']:18} N {row['n']:>3} · 고유값 {row['unique']:>3} · "
                  f"최빈 {row['modal_share']:.1%}  {row['verdict']}")
        else:
            print(f"  {row['axis']:18} N {row['n']:>3} · {row['verdict']}")
    for f_ in r["fired"]:
        print(f"  🚨 {f_}", file=sys.stderr)
    return 1 if r["fired"] else 0


if __name__ == "__main__":
    sys.exit(main())
