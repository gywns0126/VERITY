#!/usr/bin/env python3
"""KR 검정 생존편향 재검 — 오늘 낸 청산·손절 결론이 상장폐지 종목을 넣어도 버티는가.

## 왜

2026-08-16 세션에서 `exit_rule_test_kr.py` / `stop_width_test_kr.py` 로 청산 규칙과
손절폭 결론을 냈다. 둘 다 입력이 `data/kr_chart_daily/chunk_*.json` = **생존 종목만**이다.
같은 날 크립토에서 생존편향(신규상장 218 vs 상폐 2)을 잡아냈으면서 정작 KR 쪽 자기 결론은
같은 검사를 통과시키지 않았다. 여기서 그걸 친다.

## 🚨 기간 불일치 — 그냥 합치면 틀린다

실측(2026-08-16):
  · 생존     3,000종목 · 봉 중앙 250 · **2025-05-22 ~ 2026-08-13** (약 15개월)
  · 상장폐지   415종목 · 봉 중앙 637 · **2020-01-02 ~ 2026-07-30** (6.5년)

두 집합의 기간이 다르다. 단순 합집합은 상장폐지 종목에 5년치 추가 구간을 얹어
"상폐 종목이 더 나쁘다"는 결론을 기간 차이만으로 만들어낸다. 따라서 **겹치는 창으로
양쪽을 자른 뒤** 비교한다. 상폐 종목 중 그 창에 실제 거래가 있던 것만 표본에 든다.

부수 확인: 생존 표본이 15개월 단일 구간이라는 것 자체가 한계다 — 오늘 낸 KR 결론은
전부 이 창 안의 결과이며 레짐 일반화 근거가 없다.
"""
from __future__ import annotations

import glob
import json

import numpy as np

LIVE = "data/kr_chart_daily/chunk_*.json"
DEAD = "data/kr_chart_delisted/*.json"
HOLD, ENTRY_EVERY, WARMUP = 20, 20, 30
MIN_TURNOVER = 3e8
STOP = 0.05


def load(pattern):
    out = {}
    for f in sorted(glob.glob(pattern)):
        for tk, v in json.load(open(f)).get("stocks", {}).items():
            c = v.get("c") or []
            if c:
                out[tk] = np.array(c, dtype=float)
    return out


def clip_window(arr, lo, hi):
    d = arr[:, 0]
    return arr[(d >= lo) & (d <= hi)]


def entries(book, lo, hi):
    """(진입가, 고가, 저가, 종가) — 창 안에서만. 생존/상폐 동일 절차."""
    ent = []
    for tk, raw in book.items():
        a = clip_window(raw, lo, hi)
        if len(a) < WARMUP + HOLD + 5:
            continue
        hi_, lo_, cl, vol = a[:, 2], a[:, 3], a[:, 4], a[:, 5]
        turn = cl * vol
        for i in range(WARMUP, len(cl) - HOLD, ENTRY_EVERY):
            if np.median(turn[i - 20:i]) < MIN_TURNOVER or cl[i] <= 0:
                continue
            s = slice(i + 1, i + 1 + HOLD)
            ent.append((cl[i], hi_[s], lo_[s], cl[s]))
    return ent


def _stop_idx(e, lo):
    h = np.where(lo <= e * (1 - STOP))[0]
    return h[0] if len(h) else None


def r_none(e, hi, lo, cl):
    return -STOP if _stop_idx(e, lo) is not None else cl[-1] / e - 1


def r_target(mult, partial):
    def f(e, hi, lo, cl):
        tgt = e * (1 + STOP * mult)
        js = _stop_idx(e, lo)
        jt = np.where(hi >= tgt)[0]
        jt = jt[0] if len(jt) else None
        if jt is not None and (js is None or jt <= js):
            realized = partial * (STOP * mult)
            if partial >= 1.0:
                return realized
            rlo, rcl = lo[jt + 1:], cl[jt + 1:]
            if len(rcl) == 0:
                return realized + (1 - partial) * (STOP * mult)
            j2 = np.where(rlo <= e * (1 - STOP))[0]
            return realized + (1 - partial) * (-STOP if len(j2) else rcl[-1] / e - 1)
        return -STOP if js is not None else cl[-1] / e - 1
    return f


def r_trail(t):
    def f(e, hi, lo, cl):
        peak = e
        for k in range(len(cl)):
            peak = max(peak, hi[k])
            if lo[k] <= e * (1 - STOP):
                return -STOP
            if lo[k] <= peak * (1 - t):
                return max(peak * (1 - t) / e - 1, -STOP)
        return cl[-1] / e - 1
    return f


RULES = [
    ("익절 없음(20일)", r_none),
    ("+1R 전량", r_target(1.0, 1.0)),
    ("+1R 절반 (VAMS 현행)", r_target(1.0, 0.5)),
    ("+2R 절반", r_target(2.0, 0.5)),
    ("트레일링 −3%", r_trail(0.03)),
    ("트레일링 −5%", r_trail(0.05)),
    ("트레일링 −8%", r_trail(0.08)),
]


def summarize(ent, fn):
    out = np.array([fn(*x) for x in ent])
    win, loss = out[out > 0], out[out < 0]
    wr = len(win) / len(out) * 100
    aw = win.mean() * 100 if len(win) else 0.0
    al = -loss.mean() * 100 if len(loss) else 0.0
    return out.mean() * 100, wr, (aw / al if al else float("inf"))


def main() -> None:
    live, dead = load(LIVE), load(DEAD)
    lo = max(min(a[0, 0] for a in live.values()), min(a[0, 0] for a in dead.values()))
    lo = int(min(a[0, 0] for a in live.values()))          # 생존 시작일이 늦으므로 그것이 창 시작
    hi = int(min(max(a[-1, 0] for a in live.values()), max(a[-1, 0] for a in dead.values())))

    print("KR 생존편향 재검 — 오늘 낸 청산 결론이 상폐 종목을 넣어도 버티는가")
    print(f"  원본: 생존 {len(live):,}종목 / 상장폐지 {len(dead):,}종목")
    print(f"  🚨 겹치는 창으로 정렬 = {lo} ~ {hi}  (기간 불일치 보정)")
    print()

    e_live = entries(live, lo, hi)
    e_dead = entries(dead, lo, hi)
    e_all = e_live + e_dead
    n_dead_tk = sum(1 for tk, a in dead.items() if len(clip_window(a, lo, hi)) >= WARMUP + HOLD + 5)

    print(f"  창 안 진입 표본: 생존 {len(e_live):,} · 상폐 {len(e_dead):,} "
          f"(창에 걸린 상폐 종목 {n_dead_tk}개)")
    if not e_dead:
        print("  ⚠️ 창 안에 상폐 종목 표본이 0 — 재검 불가. 아래 결과는 생존 표본 그대로다.")
    else:
        print(f"  상폐 표본 비중 {len(e_dead)/len(e_all)*100:.2f}%")
    print()

    print(f"{'규칙':>22}{'생존만 기대값':>14}{'상폐포함':>11}{'차이':>9}{'상폐만':>10}")
    print("-" * 68)
    rows = []
    for name, fn in RULES:
        ev_l = summarize(e_live, fn)[0]
        ev_a = summarize(e_all, fn)[0] if e_dead else float("nan")
        ev_d = summarize(e_dead, fn)[0] if e_dead else float("nan")
        rows.append((name, ev_l, ev_a, ev_d))
        print(f"{name:>22}{ev_l:>13.3f}%{ev_a:>10.3f}%{ev_a-ev_l:>8.3f}%p{ev_d:>9.3f}%")

    print()
    b_l = max(rows, key=lambda r: r[1])
    print(f"  생존만 기준 최고: {b_l[0]} ({b_l[1]:+.3f}%)")
    if e_dead:
        b_a = max(rows, key=lambda r: r[2])
        print(f"  상폐 포함 최고:  {b_a[0]} ({b_a[2]:+.3f}%)")
        print(f"  → 결론 {'유지' if b_a[0] == b_l[0] else '**뒤집힘**'}")


if __name__ == "__main__":
    main()
