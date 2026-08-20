#!/usr/bin/env python3
"""유니버스 안정성 재측정 — G8(정규화 재설계) 선결 조건. 🚨 산식 변경 0.

왜 이 도구인가:
  외부 자문 Q8 이 G8 형태(Barra 재표준화 vs 랭크 재percentile) 선택의 결정 기준을
  지목했다 — **"선택은 유니버스 변동의 원인(방법론적으로 통제된 것인지, 데이터
  가용성에 따른 잡음인지)에 의해 좌우되어야 한다."**

  G11 진단(2026-08-21) 결과 우리 유니버스 불안정의 주원인은 **모드 분기 결함**이었고
  (`a0d6105f0`, 2026-08-20 — dispatch 가 모드를 못 실어 `full_us` 가 영영 안 돌아
  미장이 상위 10개로 잘림), 이미 수정됐다. 따라서 **수정 전 표본으로 Q8 기준에 답하면
  결함이 섞인 표본으로 답하는 것**이 된다.

🚨 RULE 13 ⑤ — 창 안에 변경 경계가 있다.
  기본 관측 창(81일)이 수정일(2026-08-20)을 가로지르므로, 이 도구는 **반드시
  경계 앞뒤를 갈라서** 보고한다. 한 덩어리 비율은 앞뒤가 섞여 현재를 말하지 않는다.
  ([[feedback_window_hides_change_boundary]] — 2026-08-19 하루 3회 같은 오독)

사용:
  python3 scripts/audit/universe_stability_check.py
  python3 scripts/audit/universe_stability_check.py --boundary 20260820
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import os
import statistics as st
import sys
from typing import Dict, List, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 모드 분기 수정 커밋 a0d6105f0 (2026-08-20 12:36). 그날 정기 run 부터 효과가 나타난다.
DEFAULT_BOUNDARY = "20260820"
# G8 판단에 필요한 최소 after 표본. 이 아래면 판정을 내지 않는다 (분모 부족 = 판정 보류)
MIN_AFTER_DAYS = 10


def load_days() -> List[Tuple[str, Dict[str, float]]]:
    out = []
    for p in sorted(glob.glob(os.path.join(ROOT, "data", "history", "*",
                                           "brain_results.json"))):
        try:
            with open(p, encoding="utf-8") as f:
                d = json.load(f)
        except Exception:  # noqa: BLE001
            continue
        m = {x["ticker"]: float(x["brain_score"])
             for x in (d.get("stocks") or [])
             if x.get("ticker") and isinstance(x.get("brain_score"), (int, float))}
        if len(m) >= 10:
            out.append((os.path.basename(os.path.dirname(p)), m))
    return out


def _pct(m: Dict[str, float]) -> Dict[str, float]:
    v = sorted(m.values())
    n = len(v)
    return {t: (sum(1 for x in v if x < s) + 0.5 * sum(1 for x in v if x == s)) / n
            for t, s in m.items()}


def _z(m: Dict[str, float]) -> Dict[str, float]:
    v = list(m.values())
    mu, sd = st.mean(v), st.pstdev(v)
    return {t: ((s - mu) / sd if sd > 0 else 0.0) for t, s in m.items()}


def churn(days, transform, cuts) -> Tuple[int, int]:
    """점수가 **불변**인 종목-쌍 중 등급이 바뀐 비율 — 유니버스가 만든 변화."""
    def g(x):
        for i, c in enumerate(cuts):
            if x >= c:
                return i
        return len(cuts)
    ch = tot = 0
    for i in range(1, len(days)):
        m0, m1 = days[i - 1][1], days[i][1]
        t0, t1 = transform(m0), transform(m1)
        for t in set(m0) & set(m1):
            if m0[t] != m1[t]:
                continue
            tot += 1
            if g(t0[t]) != g(t1[t]):
                ch += 1
    return ch, tot


def report(days, label: str) -> Dict[str, object]:
    n = len(days)
    if n < 2:
        print(f"\n[{label}] 일자 {n} — 분모 부족, 판정 보류")
        return {"days": n, "verdict": "insufficient"}

    cnt = collections.Counter()
    for _, m in days:
        for t in m:
            cnt[t] += 1
    always = sum(1 for c in cnt.values() if c >= n * 0.9)
    rare = sum(1 for c in cnt.values() if c < n * 0.1)
    sizes = [len(m) for _, m in days]
    adds, drops = [], []
    for i in range(1, n):
        a, b = set(days[i - 1][1]), set(days[i][1])
        adds.append(len(b - a))
        drops.append(len(a - b))

    print(f"\n[{label}] 일자 {n} ({days[0][0]} ~ {days[-1][0]})")
    print(f"  유니버스 N   min {min(sizes)} · 중앙 {st.median(sizes):.0f} · max {max(sizes)}"
          f"  (최대/최소 {max(sizes) / min(sizes):.1f}배)")
    print(f"  등장 종목 {len(cnt)}개 중 상시(90%+) **{always}** · 희귀(<10%) {rare}")
    print(f"  인접일 유입 중앙 {st.median(adds):.0f}/max {max(adds)}"
          f" · 이탈 중앙 {st.median(drops):.0f}/max {max(drops)}")

    cp, tp = churn(days, _pct, [0.95, 0.80, 0.50, 0.20])
    cz, tz = churn(days, _z, [1.5, 0.5, -0.5, -1.5])
    if tp:
        print(f"  점수 불변 종목-쌍 {tp}건 중 등급 변동 — "
              f"백분위 {cp / tp * 100:.1f}% · z 표준화 {cz / tz * 100:.1f}% · 절대임계 0.0%")
    return {"days": n, "universe_min": min(sizes), "universe_max": max(sizes),
            "always_present": always, "rare": rare, "tickers": len(cnt),
            "churn_pct_percentile": round(cp / tp * 100, 2) if tp else None,
            "churn_pct_zscore": round(cz / tz * 100, 2) if tz else None,
            "stable_pairs": tp}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--boundary", default=DEFAULT_BOUNDARY,
                    help="변경 경계 일자 YYYYMMDD (기본 = 모드 분기 수정일)")
    ap.add_argument("--json", help="결과 JSON 저장")
    args = ap.parse_args()

    days = load_days()
    if not days:
        print("❌ brain_results 이력 없음", file=sys.stderr)
        return 2

    before = [d for d in days if d[0] < args.boundary]
    after = [d for d in days if d[0] >= args.boundary]

    print("=" * 74)
    print(f"유니버스 안정성 재측정 — 경계 {args.boundary} (모드 분기 수정 `a0d6105f0`)")
    print("=" * 74)
    print("🚨 RULE 13 ⑤ — 창 안에 변경 경계가 있으므로 앞뒤를 갈라서 본다. "
          "한 덩어리 비율은 현재를 말하지 않는다.")

    res = {"boundary": args.boundary,
           "before": report(before, "수정 전"),
           "after": report(after, "수정 후")}

    print("\n" + "=" * 74)
    a = res["after"]
    if a.get("days", 0) < MIN_AFTER_DAYS:
        print(f"🚨 **판정 보류** — 수정 후 표본이 {a.get('days', 0)}일로 "
              f"최소 {MIN_AFTER_DAYS}일 미달이다.")
        print("   G8 형태(Barra 재표준화 vs 랭크 재percentile) 선택은 아직 하지 않는다 —")
        print("   Q8 기준(유니버스 변동이 방법론 통제인가 잡음인가)에 지금 답하면")
        print("   결함이 섞이거나 표본이 모자란 채로 답하는 것이 된다.")
    else:
        print("판정 재료 (🚨 이것이 답을 정하지 않는다 — G8 선택은 PM 결정):")
        print(f"  · 상시 종목 {a['always_present']}/{a['tickers']}")
        print(f"  · 유니버스 N {a['universe_min']}~{a['universe_max']}")
        print(f"  · 등급 churn 백분위 {a['churn_pct_percentile']}% · z {a['churn_pct_zscore']}%")
        print("  · 상시 비율이 높고 N 변동이 작아졌다면 '방법론 통제' 쪽,")
        print("    여전히 상시 0 이고 N 이 크게 변하면 '데이터 가용성 잡음' 쪽이다.")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=1)
        print(f"\n저장: {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
