#!/usr/bin/env python3
"""H2 — 거시 축이 만든 **종목 간 차등**이 수익 차를 예측했나. (사전등록 §3 단계 2)

## 왜 H2 만 검정 가능한가

H1(타이밍)은 못 잰다 — 승수 시계열의 자기상관 lag1 = 0.878 이라 유효 표본이 5.4 이고,
|t|=2 검출에 |r| ≥ 1.085 가 필요하다(상관은 1을 못 넘는다). §11 에서 착수하지 않기로 했다.

H2 는 다르다. **횡단면**이라 하루에 수십 개 관측이 생기고, 날짜는 클러스터가 된다.
그리고 거시 4축 중 **횡단면 차등이 있는 축은 `valuation_penalty` 하나뿐**이다
(83일 원장: cape·yield 는 횡단면 std=0 이 83/83, valuation 은 0/83).

## 🚨 먼저 신고할 것 — 이 축은 대부분 0이다

실측(2026-08-19): `valuation_penalty` 고유값 9개 · **0인 종목 비율 80%**.
즉 "횡단면 차등이 있다" 는 말은 맞지만, 실제로는 **소수 종목만 페널티를 받는** 형태다.
검정력이 거기서 결정되므로 결과보다 **검출하한을 먼저** 낸다.

## 설계

  · 패널 = `data/history/YYYY-MM-DD.json` → recommendations[].{ticker, current_price,
    macro_multiplier.valuation_penalty}
  · forward return = 같은 티커의 h 거래일 뒤 `current_price` 대비 수익률
  · 지표 = 날짜별 Spearman IC(penalty, fwd_ret), 날짜 클러스터로 평균·SE
  · 🚨 **부호 기대**: penalty 는 고PBR 벌점이다. 정보가 있다면 페널티가 큰 종목의
    forward 수익이 **낮아야** 하므로 **IC < 0** 이 기대 방향이다.
  · 🚨 **중첩 보정**: h일 forward 를 매일 계산하면 관측이 겹친다. 겹치지 않는
    표본(h일 간격 추출)으로도 함께 낸다 — 둘이 크게 다르면 중첩이 정밀도를 부풀린 것이다.
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys
from collections import defaultdict
from typing import Dict, List, Tuple

import numpy as np

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HISTORY = os.path.join(_ROOT, "data", "history", "20??-??-??.json")
HORIZON = 20          # 거래일. VAMS 프로파일 보유기간 10~21일과 정합


def load_panel() -> Tuple[List[str], Dict[str, Dict[str, Dict[str, float]]]]:
    """→ (날짜 오름차순, {date: {ticker: {'pen': x, 'px': y}}})"""
    panel: Dict[str, Dict[str, Dict[str, float]]] = {}
    for f in sorted(glob.glob(HISTORY)):
        m = re.search(r"(\d{4}-\d{2}-\d{2})\.json$", f)
        if not m:
            continue
        try:
            with open(f, encoding="utf-8") as fh:
                recs = json.load(fh).get("recommendations")
        except (OSError, ValueError):
            continue
        if not isinstance(recs, list):
            continue
        day: Dict[str, Dict[str, float]] = {}
        for r in recs:
            if not isinstance(r, dict):
                continue
            tk = r.get("ticker")
            px = r.get("current_price")
            mm = r.get("macro_multiplier")
            if not tk or not isinstance(px, (int, float)) or px <= 0:
                continue
            if not isinstance(mm, dict):
                continue
            pen = mm.get("valuation_penalty")
            if not isinstance(pen, (int, float)):
                continue
            day[str(tk)] = {"pen": float(pen), "px": float(px)}
        if day:
            panel[m.group(1)] = day
    return sorted(panel), panel


def spearman(a: np.ndarray, b: np.ndarray) -> float:
    ra = np.argsort(np.argsort(a)).astype(float)
    rb = np.argsort(np.argsort(b)).astype(float)
    ra -= ra.mean(); rb -= rb.mean()
    d = np.sqrt((ra ** 2).sum() * (rb ** 2).sum())
    return float((ra * rb).sum() / d) if d else float("nan")


def compute_ics(dates: List[str], panel, horizon: int, stride: int = 1):
    """→ ([(date, ic, n)], 제외 사유 카운터) — stride>1 이면 중첩 없는 표본.

    🚨 제외 분모를 **반드시 함께 반환**한다. 2026-08-19 실측에서 후보 63일 중 7일만
    통과했는데, 분모를 안 보고 그 7일의 |t|=4.39 를 유의하다고 읽을 뻔했다(RULE 13).
    """
    out = []
    drop = {"공통티커부족": 0, "고유penalty부족": 0}
    for i in range(0, len(dates) - horizon, stride):
        d0, d1 = dates[i], dates[i + horizon]
        cur, fut = panel[d0], panel[d1]
        common = [t for t in cur if t in fut]
        pens, rets = [], []
        for t in common:
            p0, p1 = cur[t]["px"], fut[t]["px"]
            if p0 > 0 and p1 > 0:
                pens.append(cur[t]["pen"])
                rets.append(p1 / p0 - 1.0)
        if len(pens) < 20:
            drop["공통티커부족"] += 1
            continue
        a, b = np.array(pens), np.array(rets)
        if np.unique(a).size < 3:          # 그날 차등이 사실상 없으면 순위가 무의미
            drop["고유penalty부족"] += 1
            continue
        ic = spearman(a, b)
        if np.isfinite(ic):
            out.append((d0, ic, len(pens)))
    return out, drop


def _independent_windows(ic_dates: List[str], horizon: int) -> int:
    """겹치지 않는 forward 창의 개수 — 이게 진짜 독립 관측 수다.

    🚨 연속된 날짜들은 20일 forward 가 거의 같은 구간을 본다. 날짜 수를 표본 수로
    쓰면 정밀도가 통째로 부풀려진다(2026-08-19 실측: 날짜 7 → 독립 창 2).
    """
    if not ic_dates:
        return 0
    idx = sorted(ic_dates)
    kept, last = 1, idx[0]
    from datetime import date as _d
    def _dt(x):
        y, m, dd = (int(v) for v in x.split("-"))
        return _d(y, m, dd)
    for d in idx[1:]:
        if (_dt(d) - _dt(last)).days >= horizon:   # 달력일 근사 — 보수적으로 셈
            kept += 1
            last = d
    return kept


def report(label: str, res, horizon: int, candidates: int):
    ics, drop = res
    print(f"  {label}")
    print(f"    🚨 분모: 후보 {candidates}일 → 통과 **{len(ics)}일** "
          f"(제외 {dict(drop)})")
    if len(ics) < 2:
        print("    표본 부족 — 산출 불가")
        return None
    v = np.array([x[1] for x in ics])
    n_ind = _independent_windows([x[0] for x in ics], horizon)
    se = v.std(ddof=1) / np.sqrt(len(v))
    se_ind = v.std(ddof=1) / np.sqrt(max(n_ind, 1))
    print(f"    날짜 {len(v)} · 평균 종목 {np.mean([x[2] for x in ics]):.0f}"
          f" · 🚨 **독립 창 {n_ind}개**")
    print(f"    IC 평균 {v.mean():+.4f}")
    print(f"      날짜 기준 SE {se:.4f} (|t|={abs(v.mean()/se) if se else float('nan'):.2f}) "
          f"← 중첩 때문에 부풀려진 값")
    if n_ind >= 2:
        print(f"      독립창 기준 SE {se_ind:.4f} "
              f"(|t|={abs(v.mean()/se_ind) if se_ind else float('nan'):.2f}) ← 정본")
    print(f"    🚨 검출하한(독립창 기준): |IC| ≥ {2*se_ind:.4f}")
    return v.mean(), se_ind, 2 * se_ind, n_ind


def main() -> int:
    dates, panel = load_panel()
    if len(dates) <= HORIZON:
        print(f"날짜 {len(dates)} ≤ 지평 {HORIZON} — 검정 불가")
        return 0

    # ── 분모·전제 신고 먼저 (RULE 13) ──────────────────────────────────
    print("═" * 68)
    print("H2 — valuation_penalty 횡단면 차등의 수익 예측력")
    print("═" * 68)
    print(f"패널 {len(dates)}일 · {dates[0]} ~ {dates[-1]} · 지평 {HORIZON}거래일")
    allpen = np.array([v["pen"] for d in dates for v in panel[d].values()])
    print(f"관측 {len(allpen):,} (일평균 {len(allpen)/len(dates):.0f}종목)")
    print(f"🚨 penalty = 0 인 관측 비율 **{(allpen==0).mean()*100:.1f}%** "
          f"· 고유값 {np.unique(np.round(allpen,5)).size}개 · 최대 {allpen.max():.4f}")
    print("   → 소수 종목만 벌점을 받는 형태다. 검정력이 여기서 결정된다.")
    print(f"기대 부호: penalty 는 고PBR 벌점이므로 정보가 있다면 **IC < 0**")

    print("\n── 결과 ──")
    cand = len(dates) - HORIZON
    ov = report(f"① 매일 (중첩 있음, {HORIZON}일 forward)",
                compute_ics(dates, panel, HORIZON, stride=1), HORIZON, cand)
    nv = report(f"② {HORIZON}일 간격 (중첩 없음)",
                compute_ics(dates, panel, HORIZON, stride=HORIZON), HORIZON,
                len(range(0, cand, HORIZON)))

    print("\n── 판정 ──")
    if ov is None:
        print("❌ **검정 불가** — 표본이 성립하지 않는다.")
        return 0
    mean, se_ind, floor, n_ind = ov

    if n_ind < 3:
        print(f"❌ **검정 불가.** 독립 창이 {n_ind}개뿐이다.")
        print(f"   IC 평균은 {mean:+.4f} 로 기대 부호(음수)이나, 이 숫자에 유의성을 붙일 수 없다.")
        print("   🚨 통과한 날짜들이 한 구간에 몰려 있어 20일 forward 가 사실상 같은 시장")
        print("      국면을 본다. 날짜 수를 표본 수로 쓰면 정밀도가 통째로 부풀려진다.")
        print("   원인 = 추천 유니버스가 20일 사이에 크게 회전해 같은 종목을 추적할 수 있는")
        print("      날이 드물다(제외 사유 1위 = 공통 티커 부족).")
        print("   → **'효과가 없다' 가 아니라 '이 패널로는 못 잰다'** 다. 시점은 지어내지 않는다.")
        print("      재개 조건 = 서로 겹치지 않는 창이 최소 20개 (유니버스 회전이 느려지거나")
        print("      보유 종목 기준 패널로 바꾸면 빨라질 수 있다 — 별도 설계 사안).")
        return 0

    sig = abs(mean) >= floor
    if sig and mean < 0:
        print(f"✅ 기대 부호로 유의 (독립창 {n_ind}개 기준) — 재현 확인 후 등록 검토")
    elif sig:
        print("🚨 유의하나 **부호가 기대와 반대**다 — 페널티가 큰 종목이 더 올랐다")
    else:
        print(f"❌ 검출 미달. |IC {mean:+.4f}| < 하한 {floor:.4f}")
        print("   🚨 '효과가 없다' 가 아니라 **'이 표본으로는 이 크기를 못 본다'** 다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
