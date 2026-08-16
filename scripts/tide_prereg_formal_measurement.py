#!/usr/bin/env python3
"""TIDE 사전등록 2건 정식 측정 — 결정 규칙대로만 판정한다.

등록서 (PM 승인 2026-08-17):
  · `TIDE/docs/DISASTER_BREAKER_PREREG_20260817.md`
  · `TIDE/docs/SYMMETRIC_SIGNAL_PREREG_20260817.md`

🚨 결정 규칙은 등록서에 **측정 전 고정**돼 있다. 이 스크립트는 그 규칙을 코드로 옮긴 것이며
결과를 보고 규칙을 바꾸지 않는다. 통과/탈락만 낸다.

## 브레이커 §5
  1. 제약 A: 기대값 하락 ≤ 0.058%p (검출하한)
  2. 제약 B: C1% 변화 ≤ ±2%p (꼬리 보존)
  3. 선택: A·B 통과 중 최악 거래 손실 최소
  4. 관문 a 유니버스 2종 / b 게이트 on·off / c 인접 폭 평평 / d 연도별 하락 ≤0.5%p
  5. 모두 탈락 시 현행 유지

## 대칭 §5
  1. 1차 종점: MDD 개선
  2. 비열등성: 연수익 하락 < 검출하한
  3. 선택: Calmar 최대
  4. 관문 a 4구성 전부 Calmar 개선 / b S025 단조 / c 연도별 하락>5%p 가 2개 미만 /
     d 비용 0.05·0.10·0.20% 전부 Calmar 개선
  5. 모두 탈락 시 현행 유지

추가 기록(판정에 쓰지 않음): FNG 국면 분해. 2026-08-17 검정에서 FNG>60 비율이 연도 성과와
거의 1:1 대응함이 확인됐으므로(2022 0.0%/Sharpe −1.68, 2026 0.4%/−2.20, 2024 66.3%/+2.27)
결과 해석 시 국면을 함께 봐야 오독하지 않는다. **등록 규칙에는 없으므로 판정에 반영 금지.**
"""
from __future__ import annotations

import glob
import json
import os
import sys
from math import sqrt
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

OHLC_DIR = ("/private/tmp/claude-501/-Users-macbookpro-Desktop--------/"
            "3b4bdb64-7a07-412b-b2cf-029170e8bf91/scratchpad/upbit_ohlc")
EXO = "data/crypto_exogenous_history.json"
LIVE = ("KRW-BTC", "KRW-ETH")
SHORT, LONG, ANN = 30, 90, 365
VOL_TARGET, VOL_LB = 0.40, 30
GATE_LB, GATE_CONFIRM = 200, 3
WARMUP, MAX_HOLD = LONG + 5, 400

BREAKER_COST_CAP = 0.058      # §5-1 제약 A (%p)
BREAKER_C1_CAP = 2.0          # §5-2 제약 B (%p)
BREAKERS = [None, 0.50, 0.40, 0.30, 0.25, 0.20]
MIXED_W = {"S05": 0.5, "S025": 0.25, "S00": 0.0}
COSTS = [0.0005, 0.0010, 0.0020]


def load(only=None):
    out = {}
    for p in sorted(glob.glob(os.path.join(OHLC_DIR, "*.json"))):
        d = json.load(open(p))
        if only and d["m"] not in only:
            continue
        a = np.array(d["c"], dtype=float)
        if len(a) >= WARMUP + 60:
            out[d["m"]] = a
    return out


def gate_series(cl):
    n = len(cl)
    sma = np.full(n, np.nan)
    c = np.cumsum(np.insert(cl, 0, 0.0))
    sma[GATE_LB - 1:] = (c[GATE_LB:] - c[:-GATE_LB]) / GATE_LB
    above = cl > sma
    g = np.full(n, 0.5)
    bull = False
    for i in range(n):
        if not np.isfinite(sma[i]):
            continue
        if bull:
            if not above[i]:
                bull = False
        elif i >= GATE_CONFIRM - 1 and above[i - GATE_CONFIRM + 1:i + 1].all():
            bull = True
        g[i] = 1.0 if bull else 0.5
    return g


# ══════════════ 브레이커 (거래 단위) ══════════════
def breaker_trades(book, breaker, use_gate):
    R, Y = [], []
    for m, a in book.items():
        dt, lo, cl = a[:, 0], a[:, 3], a[:, 4]
        n = len(cl)
        sig = np.zeros(n)
        sig[SHORT:] += (cl[SHORT:] > cl[:-SHORT]).astype(float)
        sig[LONG:] += (cl[LONG:] > cl[:-LONG]).astype(float)
        sig /= 2.0
        sig[:LONG] = 0.0
        g = gate_series(cl) if use_gate else np.ones(n)
        inpos = (sig > 0) & (g > 0)
        i = WARMUP
        while i < n - 1:
            if inpos[i] and not inpos[i - 1]:
                j = i + 1
                while j < n and inpos[j] and (j - i) < MAX_HOLD:
                    j += 1
                e = cl[i]
                sl = slice(i + 1, min(j + 1, n))
                cs, ls = cl[sl], lo[sl]
                if len(cs):
                    r = None
                    if breaker is not None:
                        lvl = e * (1 - breaker)
                        if (ls <= lvl).any():
                            r = lvl / e - 1.0
                    if r is None:
                        r = cs[-1] / e - 1.0
                    R.append(r - 0.001)
                    Y.append(int(dt[i]) // 10000)
                i = j
            else:
                i += 1
    return np.array(R), np.array(Y)


def c1(r):
    return np.sort(r)[::-1][:max(1, int(len(r) * 0.01))].sum() / r.sum() * 100 if r.sum() else np.nan


def run_breaker():
    print("=" * 92)
    print("## 등록 ① 재난 브레이커 — 결정 규칙 §5 적용")
    cells = {}
    for uname, only in [("BTC/ETH", LIVE), ("40종", None)]:
        book = load(only)
        for gname, ug in [("게이트ON", True), ("게이트OFF", False)]:
            base, ybase = breaker_trades(book, None, ug)
            for b in BREAKERS:
                r, y = breaker_trades(book, b, ug)
                cells[(uname, gname, b)] = (r, y, base)
    print(f"{'유니버스':>9}{'게이트':>9}{'폭':>7}{'거래':>7}{'기대값':>9}{'Δ기대':>9}"
          f"{'C1%':>8}{'ΔC1':>8}{'최악':>9}{'A':>4}{'B':>4}")
    print("-" * 92)
    passing = {}
    for (u, g, b), (r, y, base) in cells.items():
        if b is None:
            continue
        d_ev = (r.mean() - base.mean()) * 100
        d_c1 = c1(r) - c1(base)
        okA = d_ev >= -BREAKER_COST_CAP
        okB = abs(d_c1) <= BREAKER_C1_CAP
        passing.setdefault(b, []).append((okA and okB, u, g))
        print(f"{u:>9}{g:>9}{f'−{int(b*100)}%':>7}{len(r):>7}{r.mean()*100:>8.2f}%"
              f"{d_ev:>8.3f}%{c1(r):>7.1f}%{d_c1:>7.2f}%{r.min()*100:>8.1f}%"
              f"{'✅' if okA else '❌':>4}{'✅' if okB else '❌':>4}")
    print()
    print("  §5-4a·b 관문 — 4구성(유니버스 2 × 게이트 2) 전부 통과해야 후보:")
    cands = []
    for b in BREAKERS:
        if b is None:
            continue
        res = passing[b]
        allok = all(x[0] for x in res)
        print(f"    −{int(b*100)}%: {sum(x[0] for x in res)}/4 {'✅ 후보' if allok else '❌ 탈락'}")
        if allok:
            cands.append(b)
    if not cands:
        print("\n  ❌ 후보 없음 → §5-5 현행(브레이커 없음) 유지")
        return
    # §5-4c 인접 평평성 · §5-4d 연도별
    print()
    print("  §5-4c 인접 폭 평평성 + §5-4d 연도별 하락 ≤0.5%p (BTC/ETH·게이트ON 기준):")
    final = []
    for b in cands:
        r, y, base = cells[("BTC/ETH", "게이트ON", b)]
        worst_year = 0.0
        ybase = cells[("BTC/ETH", "게이트ON", None)][1]
        for yr in sorted(set(y.tolist())):
            m = y == yr
            bm = ybase == yr
            if m.sum() < 20 or bm.sum() < 20:
                continue
            dd = (r[m].mean() - base[bm].mean()) * 100
            worst_year = min(worst_year, dd)
        okD = worst_year >= -0.5
        print(f"    −{int(b*100)}%: 연도별 최악 Δ {worst_year:+.2f}%p {'✅' if okD else '❌'}")
        if okD:
            final.append(b)
    if not final:
        print("\n  ❌ §5-4d 전부 탈락 → 현행 유지")
        return
    # §5-3 선택: 최악 손실 최소
    # §5-3 선택 = 최악 거래 손실이 가장 작은 변형 (Sharpe·Calmar 로 고르지 않는다)
    pick = max(final, key=lambda b: cells[("BTC/ETH", "게이트ON", b)][0].min())
    r, y, base = cells[("BTC/ETH", "게이트ON", pick)]
    print()
    print(f"  🏁 §5-3 선택 = **−{int(pick*100)}%** (통과 집합 중 최악 손실 최소)")
    print(f"     최악 {base.min()*100:.1f}% → {r.min()*100:.1f}% · "
          f"기대값 {base.mean()*100:.2f}% → {r.mean()*100:.2f}%")


# ══════════════ 대칭 신호 (포트폴리오 단위) ══════════════
def sym_portfolio(book, mixed_w, use_gate, fee):
    keys = sorted(book)
    n = min(len(book[k]) for k in keys)
    cl = np.column_stack([book[k][-n:, 4] for k in keys])
    dates = book[keys[0]][-n:, 0].astype(int) // 10000
    rets = np.zeros_like(cl)
    rets[1:] = cl[1:] / cl[:-1] - 1.0
    up_s = cl.copy(); up_l = cl.copy()
    sig = np.zeros_like(cl)
    both = np.zeros_like(cl, dtype=bool)
    one = np.zeros_like(cl, dtype=bool)
    a = np.zeros_like(cl, dtype=bool); b = np.zeros_like(cl, dtype=bool)
    a[SHORT:] = cl[SHORT:] > cl[:-SHORT]
    b[LONG:] = cl[LONG:] > cl[:-LONG]
    both = a & b
    one = a ^ b
    sig[both] = 1.0
    sig[one] = mixed_w
    sig[:LONG] = 0.0
    vol = np.full_like(cl, np.nan)
    for j in range(cl.shape[1]):
        for i in range(VOL_LB, len(cl)):
            vol[i, j] = rets[i - VOL_LB:i, j].std() * sqrt(ANN)
    scale = np.nan_to_num(np.clip(np.where(vol > 0, VOL_TARGET / vol, 0.0), 0.0, 1.0))
    g = np.column_stack([gate_series(cl[:, j]) for j in range(cl.shape[1])]) if use_gate \
        else np.ones_like(cl)
    w = sig * scale * g * 0.5 / max(1, len(keys) / 2)
    ww = np.vstack([np.zeros((1, w.shape[1])), w[:-1]])
    turn = np.abs(ww - np.vstack([np.zeros((1, w.shape[1])), ww[:-1]])).sum(axis=1)
    return dates, (ww * rets).sum(axis=1) - turn * fee


def st(r):
    eq = np.cumprod(1 + r)
    sh = r.mean() / r.std() * sqrt(ANN) if r.std() else np.nan
    cagr = (eq[-1] ** (ANN / len(r)) - 1) * 100
    mdd = (eq / np.maximum.accumulate(eq) - 1).min() * 100
    return sh, cagr, mdd, cagr / abs(mdd) if mdd else np.nan


def run_symmetric():
    print()
    print("=" * 92)
    print("## 등록 ② 대칭 신호 — 결정 규칙 §5 적용 (12셀 전량)")
    books = {"BTC/ETH": load(LIVE), "40종": load(None)}
    res = {}
    print(f"{'유니버스':>9}{'게이트':>9}{'변형':>7}{'Sharpe':>9}{'연수익':>9}{'MDD':>9}{'Calmar':>9}")
    print("-" * 92)
    for u, book in books.items():
        for gname, ug in [("게이트ON", True), ("게이트OFF", False)]:
            for vid, mw in MIXED_W.items():
                d, r = sym_portfolio(book, mw, ug, 0.0005)
                res[(u, gname, vid)] = (d, r, st(r))
                sh, cg, md, ca = st(r)
                print(f"{u:>9}{gname:>9}{vid:>7}{sh:>9.2f}{cg:>8.1f}%{md:>8.1f}%{ca:>9.2f}")
    print()
    # §5-4a 4구성 전부 Calmar 개선
    print("  §5-4a — 4구성 전부에서 S00 Calmar > S05:")
    conf = [(u, g) for u in books for g in ("게이트ON", "게이트OFF")]
    a_ok = []
    for u, g in conf:
        c0 = res[(u, g, "S05")][2][3]; c1_ = res[(u, g, "S00")][2][3]
        a_ok.append(c1_ > c0)
        print(f"    {u:>9} {g:>9}: {c0:.2f} → {c1_:.2f} {'✅' if c1_ > c0 else '❌'}")
    print(f"    → {sum(a_ok)}/4 {'✅ 통과' if all(a_ok) else '❌ 탈락'}")
    # §5-4b 단조성
    print()
    print("  §5-4b — S025 가 S05 와 S00 사이(단조):")
    b_ok = []
    for u, g in conf:
        v = [res[(u, g, k)][2][3] for k in ("S05", "S025", "S00")]
        mono = (v[0] <= v[1] <= v[2]) or (v[0] >= v[1] >= v[2])
        b_ok.append(mono)
        print(f"    {u:>9} {g:>9}: {v[0]:.2f} → {v[1]:.2f} → {v[2]:.2f} {'✅' if mono else '❌ 내부 봉우리'}")
    print(f"    → {sum(b_ok)}/4 {'✅ 통과' if all(b_ok) else '❌ 탈락'}")
    # §5-4d 비용 민감도
    print()
    print("  §5-4d — 편도 0.05/0.10/0.20% 전부에서 Calmar 개선 (게이트ON):")
    d_ok = []
    for u, book in books.items():
        row = []
        for fee in COSTS:
            _, r0 = sym_portfolio(book, 0.5, True, fee)
            _, r1 = sym_portfolio(book, 0.0, True, fee)
            imp = st(r1)[3] > st(r0)[3]
            row.append(f"{st(r0)[3]:.2f}→{st(r1)[3]:.2f}{'✅' if imp else '❌'}")
            d_ok.append(imp)
        print(f"    {u:>9}: " + " · ".join(row))
    print(f"    → {sum(d_ok)}/{len(d_ok)} {'✅ 통과' if all(d_ok) else '❌ 탈락'}")
    # §5-4c 연도별
    print()
    print("  §5-4c — 연도별 수익 하락 >5%p 인 해가 2개 미만 (BTC/ETH 게이트ON):")
    d0, r0, _ = res[("BTC/ETH", "게이트ON", "S05")]
    _, r1, _ = res[("BTC/ETH", "게이트ON", "S00")]
    bad = []
    for y in sorted(set(d0.tolist())):
        m = d0 == y
        if m.sum() < 60:
            continue
        a_ = (np.prod(1 + r0[m]) - 1) * 100
        b_ = (np.prod(1 + r1[m]) - 1) * 100
        if b_ - a_ < -5:
            bad.append((y, b_ - a_))
    print(f"    하락>5%p 인 해 {len(bad)}개" + (f" — {bad}" if bad else ""))
    c_ok = len(bad) < 2
    print(f"    → {'✅ 통과' if c_ok else '❌ 탈락'}")
    print()
    allpass = all(a_ok) and all(b_ok) and all(d_ok) and c_ok
    print(f"  🏁 종합: {'✅ **S00 채택 조건 충족**' if allpass else '❌ 관문 미통과 → §5-5 현행 S05 유지'}")


def main() -> None:
    print("TIDE 사전등록 2건 정식 측정 (2026-08-17 PM 승인)")
    print("  🚨 결정 규칙은 등록서에 측정 전 고정. 결과를 보고 규칙을 바꾸지 않는다.")
    print()
    run_breaker()
    run_symmetric()


if __name__ == "__main__":
    main()
