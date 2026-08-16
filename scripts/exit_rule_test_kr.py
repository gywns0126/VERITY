#!/usr/bin/env python3
"""청산 규칙 검정 — 익절이 손익비를 죽이는가. KR 대표본.

질문(PM 2026-08-16): "어떻게 하면 승률과 수익을 높일까"

VAMS 진단: 승률 26.1% · 손익비 0.81 · 거래당 −21,089원.
본전 조건 = 승률 26.1% 유지 시 손익비 **2.83** 필요(현재 0.81, 3.5배 부족).

의심: VAMS 는 부분청산 66건이 전부 `+1.0R lock in gains`(46) · `+2.0R scale out`(20) 이다.
**손실은 −5% 에서 자르고 이익은 +1R 에서 자른다** → 양쪽을 다 짧게 끊어 손익비가
구조적으로 1 아래에 갇힌다. 추세추종 원칙("손실 짧게, 이익 길게")의 정반대.

여기서 검정: 같은 손절선 아래 **청산 규칙만** 바꿔가며 손익비·기대값을 비교한다.
데이터 = data/kr_chart_daily (금융위 주식시세정보, 시가·고가·저가·종가).
고가가 있어야 트레일링·목표가 도달을 제대로 잰다 — 종가만으로는 과소 측정된다.
"""
from __future__ import annotations
import glob
import json
import numpy as np

CHUNKS = "/Users/macbookpro/Desktop/배리티 터미널/data/kr_chart_daily/chunk_*.json"
HOLD = 20
ENTRY_EVERY = 20
WARMUP = 30
MIN_TURNOVER = 3e8
STOP = 0.05          # VAMS profile_cap 과 동일. R = 5%


def load_entries():
    ent = []
    for f in sorted(glob.glob(CHUNKS)):
        for tk, v in json.load(open(f))["stocks"].items():
            c = v.get("c") or []
            if len(c) < WARMUP + HOLD + 5:
                continue
            a = np.array(c, dtype=float)
            o, hi, lo, cl, vol = a[:, 1], a[:, 2], a[:, 3], a[:, 4], a[:, 5]
            turn = cl * vol
            for i in range(WARMUP, len(cl) - HOLD, ENTRY_EVERY):
                if np.median(turn[i - 20:i]) < MIN_TURNOVER or cl[i] <= 0:
                    continue
                s = slice(i + 1, i + 1 + HOLD)
                ent.append((cl[i], hi[s], lo[s], cl[s]))
    return ent


def simulate(ent, rule):
    """rule(e, hi, lo, cl) -> 수익률(소수). 손절은 모든 규칙에 공통 적용."""
    out = np.array([rule(*x) for x in ent])
    win = out[out > 0]
    loss = out[out < 0]
    wr = len(win) / len(out) * 100
    aw = win.mean() * 100 if len(win) else 0.0
    al = -loss.mean() * 100 if len(loss) else 0.0
    ratio = aw / al if al else float("inf")
    return out, wr, aw, al, ratio


# ── 청산 규칙들 (손절 −5% 공통) ───────────────────────────────────────────
def _stop_idx(e, lo):
    h = np.where(lo <= e * (1 - STOP))[0]
    return h[0] if len(h) else None


def r_none(e, hi, lo, cl):
    """익절 없음 — 손절 또는 20일 종가."""
    j = _stop_idx(e, lo)
    return -STOP if j is not None else cl[-1] / e - 1


def r_target(mult, partial):
    """+mult×R 도달 시 partial 비율만 청산(나머지는 계속). partial=1.0 이면 전량."""
    def f(e, hi, lo, cl):
        tgt = e * (1 + STOP * mult)
        js = _stop_idx(e, lo)
        jt = np.where(hi >= tgt)[0]
        jt = jt[0] if len(jt) else None
        if jt is not None and (js is None or jt <= js):
            realized = partial * (STOP * mult)
            if partial >= 1.0:
                return realized
            rest_lo, rest_cl = lo[jt + 1:], cl[jt + 1:]
            if len(rest_cl) == 0:
                return realized + (1 - partial) * (STOP * mult)
            j2 = np.where(rest_lo <= e * (1 - STOP))[0]
            rest = -STOP if len(j2) else rest_cl[-1] / e - 1
            return realized + (1 - partial) * rest
        return -STOP if js is not None else cl[-1] / e - 1
    return f


def r_trail(t):
    """트레일링 — 고점 대비 t 하락 시 청산. 손절도 유지."""
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


def main() -> None:
    ent = load_entries()
    print(f"KR 청산 규칙 검정 — 진입 표본 {len(ent):,} · 손절 −{STOP*100:.0f}% 공통 · 최대 {HOLD}일")
    print()
    rules = [
        ("익절 없음(20일)", r_none),
        ("+1R 전량", r_target(1.0, 1.0)),
        ("+1R 절반 (VAMS 현행)", r_target(1.0, 0.5)),
        ("+2R 절반", r_target(2.0, 0.5)),
        ("+3R 절반", r_target(3.0, 0.5)),
        ("트레일링 −3%", r_trail(0.03)),
        ("트레일링 −5%", r_trail(0.05)),
        ("트레일링 −8%", r_trail(0.08)),
        ("트레일링 −12%", r_trail(0.12)),
    ]
    print(f"{'규칙':>22}{'승률':>8}{'평균수익':>10}{'평균손실':>10}{'손익비':>8}{'기대값':>10}")
    print("-" * 70)
    best = None
    for name, fn in rules:
        out, wr, aw, al, ratio = simulate(ent, fn)
        ev = out.mean() * 100
        print(f"{name:>22}{wr:>7.1f}%{aw:>9.2f}%{al:>9.2f}%{ratio:>8.2f}{ev:>9.3f}%")
        if best is None or ev > best[1]:
            best = (name, ev)
    print()
    print(f"최고 기대값: {best[0]}  ({best[1]:+.3f}%/거래)")
    print()
    print("## VAMS 본전 조건 대조 (승률 26.1% 기준 필요 손익비 2.83)")
    for name, fn in rules:
        out, wr, aw, al, ratio = simulate(ent, fn)
        need = (100 - wr) / wr if wr else float("inf")
        mark = "✅" if ratio >= need else "❌"
        print(f"  {mark} {name:>22} 승률 {wr:5.1f}% → 필요 손익비 {need:5.2f} · 실제 {ratio:5.2f}")


if __name__ == "__main__":
    main()
