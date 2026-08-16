#!/usr/bin/env python3
"""TIDE 진입 확인일수 검정 — 신호 즉시 진입 vs N일 확인 후 진입. 포트폴리오 단위.

## 왜 다시 하나

`crypto_entry_timing_test.py`(거래 단위)에서 "3~5일 대기" 가 강해 보였다:
거래 2,560→1,233, 평균 6.27%→12.33%, 총수익 −5%.

그런데 **거래 단위 합계는 자본을 재지 않는다.** 거래 수가 절반이면 그동안 자본이 노는데
거래별 수익 합은 그걸 반영하지 않는다. 실제로 쓸 수 있는 결론이려면 **일별 비중
포트폴리오**로 재야 한다. 여기서 그걸 한다.

구현 형태도 바꾼다. "N일 대기" 를 TIDE 에 넣는 자연스러운 방식 = 신호에 **confirm_days**
를 거는 것이다(레짐 게이트가 이미 쓰는 패턴, `REGIME_GATE_CONFIRM_DAYS=3`).
즉 신호가 N일 연속 양수여야 진입하고, 이탈은 즉시(asymmetric) — 게이트와 동일 문법.

## 🚨 이 세션에서 낸 오류 2건 (같은 뿌리)

1. 레짐 게이트를 **진입 완전 차단**으로 구현 → "총수익 −78%" 라는 잘못된 경보.
   라이브는 **비중 0.5 축소**다. 바로잡으니 게이트는 MDD 를 줄이는 정상 장치였다.
2. `config.py:71` 의 "누적수익 약 90% 제거" 를 게이트 기록으로 오독. 실제로는
   **VOL_TARGET=0.20** 기록이며 7/27 에 0.40 으로 조정해 해소된 건이다.

둘 다 "라이브 구현을 읽지 않고 내 머릿속 모델로 재현" 해서 생겼다.
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
LIVE = ("KRW-BTC", "KRW-ETH")
SHORT, LONG = 30, 90
WEIGHT_PER_TICKER = 0.5
VOL_TARGET, VOL_LB, ANN = 0.40, 30, 365
FEE = 0.0005
GATE_LB, GATE_CONFIRM = 200, 3
CONFIRMS = [1, 2, 3, 5, 7, 10, 14]


def load(tickers=None):
    out = {}
    for p in sorted(glob.glob(os.path.join(OHLC_DIR, "*.json"))):
        d = json.load(open(p))
        if tickers and d["m"] not in tickers:
            continue
        out[d["m"]] = np.array(d["c"], dtype=float)
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


def confirm(sig, days):
    """신호가 days 일 연속 양수여야 진입. 이탈은 즉시(asymmetric) — 게이트와 동일 문법."""
    if days <= 1:
        return sig.copy()
    out = np.zeros_like(sig)
    for j in range(sig.shape[1]):
        on = False
        s = sig[:, j]
        for i in range(len(s)):
            if s[i] <= 0:
                on = False
            elif not on and i >= days - 1 and (s[i - days + 1:i + 1] > 0).all():
                on = True
            out[i, j] = s[i] if on else 0.0
    return out


def build(book):
    keys = sorted(book)
    n = min(len(book[k]) for k in keys)
    cl = np.column_stack([book[k][-n:, 4] for k in keys])
    rets = np.zeros_like(cl)
    rets[1:] = cl[1:] / cl[:-1] - 1.0
    sig = np.zeros_like(cl)
    sig[SHORT:] += (cl[SHORT:] > cl[:-SHORT]).astype(float)
    sig[LONG:] += (cl[LONG:] > cl[:-LONG]).astype(float)
    sig /= 2.0
    sig[:LONG] = 0.0
    vol = np.full_like(cl, np.nan)
    for j in range(cl.shape[1]):
        for i in range(VOL_LB, len(cl)):
            vol[i, j] = rets[i - VOL_LB:i, j].std() * sqrt(ANN)
    scale = np.nan_to_num(np.clip(np.where(vol > 0, VOL_TARGET / vol, 0.0), 0.0, 1.0))
    gate = np.column_stack([gate_series(cl[:, j]) for j in range(cl.shape[1])])
    return keys, cl, rets, sig, scale, gate


def simulate(rets, w):
    ww = np.vstack([np.zeros((1, w.shape[1])), w[:-1]])
    turn = np.abs(ww - np.vstack([np.zeros((1, w.shape[1])), ww[:-1]])).sum(axis=1)
    return (ww * rets).sum(axis=1) - turn * FEE


def stats(r):
    eq = np.cumprod(1 + r)
    sh = r.mean() / r.std() * sqrt(ANN) if r.std() else float("nan")
    cagr = (eq[-1] ** (ANN / len(r)) - 1) * 100
    mdd = (eq / np.maximum.accumulate(eq) - 1).min() * 100
    return sh, cagr, mdd, cagr / abs(mdd) if mdd else float("nan")


def main() -> None:
    print("TIDE 진입 확인일수 — 포트폴리오 단위 (거래 단위 합계의 자본 착시 제거)")
    print(f"  라이브 고정: TSM {SHORT}/{LONG} · V{int(VOL_TARGET*100)} · 레짐게이트 ON · 편도 {FEE:.2%}")

    for label, tick in [("KRW-BTC + KRW-ETH (라이브)", LIVE), ("유니버스 40종 (검정력)", None)]:
        keys, cl, rets, sig, scale, gate = build(load(tick))
        print(f"\n{'='*74}\n## {label} — 종목 {len(keys)} · {len(cl)}일")
        print(f"{'진입 확인':>12}{'Sharpe':>9}{'연수익':>10}{'MDD':>9}{'Calmar':>9}{'평균노출':>10}{'회전':>9}")
        print("-" * 68)
        cols, labels = [], []
        for d in CONFIRMS:
            s2 = confirm(sig, d)
            w = s2 * scale * gate * WEIGHT_PER_TICKER / max(1, len(keys) / 2)
            r = simulate(rets, w)
            sh, cg, md, ca = stats(r)
            expo = w.sum(axis=1).mean() * 100
            turn = np.abs(np.diff(w.sum(axis=1))).sum() / len(w) * 365 * 100
            cols.append(r); labels.append(f"{d}일")
            mark = " ←라이브" if d == 1 else ""
            print(f"{f'{d}일':>12}{sh:>9.2f}{cg:>9.1f}%{md:>8.1f}%{ca:>9.2f}{expo:>9.1f}%{turn:>8.0f}%{mark}")

        from pbo_selection_gate import pbo_cscv, effective_trials
        M = np.column_stack(cols)
        ne, mc = effective_trials(M)
        p = pbo_cscv(M, s_blocks=10)
        print()
        print(f"  선택 게이트: 변형 {len(CONFIRMS)} · 상관 {mc:.3f} · N_eff {ne:.1f} · "
              f"PBO {p:.1%} → " + ("선택 유효" if p < 0.30 else "경계" if p < 0.50 else "FAIL"))

        # 기간 안정성 — 전반/후반
        h = len(cols[0]) // 2
        print(f"  {'':>12}{'전반 Sharpe':>14}{'후반 Sharpe':>14}")
        for d, r in zip(CONFIRMS, cols):
            print(f"  {f'{d}일':>12}{stats(r[:h])[0]:>13.2f}{stats(r[h:])[0]:>13.2f}")


if __name__ == "__main__":
    main()
