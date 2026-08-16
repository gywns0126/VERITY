#!/usr/bin/env python3
"""TIDE 200d 레짐 게이트가 값을 하는가 — 라이브 구현 그대로 재현해 on/off 비교.

## 왜

2026-08-17 진입 타이밍 검정에서 "200d 게이트" 를 넣었더니 총수익이 급락했다. 그런데
그 구현은 **진입 완전 차단**이었고, TIDE 라이브 게이트는 **비중 0.5 축소**다.
즉 그 결과는 TIDE 게이트의 성적이 아니다. 여기서 라이브 구현 그대로 다시 잰다.

🚨 같은 세션에서 낸 오독 정정: `tide/config.py:71` 의 "누적수익의 약 90% 를 제거" 는
**게이트가 아니라 VOL_TARGET=0.20** 에 대한 기록이다(2026-07-27 에 0.40 으로 조정해 해소).
게이트 자체의 end-to-end 기여는 별도로 측정된 기록을 찾지 못했다.

## 라이브 구현 (origin/main:tide/signals/tsm.py:42-49, 148-175)

    REGIME_GATE_LOOKBACK = 200
    REGIME_GATE_CONFIRM_DAYS = 3
    REGIME_GATE_BULL = 1.0        # SMA 위에서 3일 연속 종가 마감
    REGIME_GATE_NON_BULL = 0.5    # 1일이라도 아래면 즉시 해제 (asymmetric exit)
    데이터 부족 → 0.5 (보수)

    weight = signal × gate × WEIGHT_PER_TICKER × min(1.0, VOL_TARGET/realized_vol)

## 설계

일별 비중 시뮬레이션(거래 단위 아님 — 게이트는 비중 승수라 그게 맞는 구조).
게이트 on/off 만 바꾸고 나머지는 전부 라이브 값 고정. 데이터 = 업비트 OHLC 종가.
"""
from __future__ import annotations

import glob
import json
import os
from math import sqrt

import numpy as np

OHLC_DIR = ("/private/tmp/claude-501/-Users-macbookpro-Desktop--------/"
            "3b4bdb64-7a07-412b-b2cf-029170e8bf91/scratchpad/upbit_ohlc")
LIVE = ("KRW-BTC", "KRW-ETH")

# origin/main:tide/config.py 정합
SHORT, LONG = 30, 90
WEIGHT_PER_TICKER = 0.5
VOL_TARGET, VOL_LB, ANN = 0.40, 30, 365
FEE = 0.0005
GATE_LB, GATE_CONFIRM, GATE_BULL, GATE_NON_BULL = 200, 3, 1.0, 0.5


def load(tickers):
    out = {}
    for p in sorted(glob.glob(os.path.join(OHLC_DIR, "*.json"))):
        d = json.load(open(p))
        if tickers and d["m"] not in tickers:
            continue
        out[d["m"]] = np.array(d["c"], dtype=float)
    return out


def gate_series(cl):
    """라이브 regime_gate_status 재현 — 3일 연속 확인 진입 / 1일 이탈 즉시 해제."""
    n = len(cl)
    sma = np.full(n, np.nan)
    c = np.cumsum(np.insert(cl, 0, 0.0))
    sma[GATE_LB - 1:] = (c[GATE_LB:] - c[:-GATE_LB]) / GATE_LB
    above = cl > sma
    g = np.full(n, GATE_NON_BULL)
    bull = False
    for i in range(n):
        if not np.isfinite(sma[i]):
            g[i] = GATE_NON_BULL          # 데이터 부족 → 보수
            continue
        if bull:
            if not above[i]:
                bull = False              # asymmetric exit: 1일도 아래면 즉시 해제
        else:
            if i >= GATE_CONFIRM - 1 and above[i - GATE_CONFIRM + 1:i + 1].all():
                bull = True
        g[i] = GATE_BULL if bull else GATE_NON_BULL
    return g


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
    scale = np.clip(np.where(vol > 0, VOL_TARGET / vol, 0.0), 0.0, 1.0)
    scale = np.nan_to_num(scale)
    gate = np.column_stack([gate_series(cl[:, j]) for j in range(cl.shape[1])])
    return keys, cl, rets, sig, scale, gate


def simulate(rets, w):
    ww = np.vstack([np.zeros((1, w.shape[1])), w[:-1]])
    gross = (ww * rets).sum(axis=1)
    turn = np.abs(ww - np.vstack([np.zeros((1, w.shape[1])), ww[:-1]])).sum(axis=1)
    return gross - turn * FEE


def stats(r):
    r = r[np.isfinite(r)]
    eq = np.cumprod(1 + r)
    sh = r.mean() / r.std() * sqrt(ANN) if r.std() else float("nan")
    cagr = (eq[-1] ** (ANN / len(r)) - 1) * 100
    mdd = (eq / np.maximum.accumulate(eq) - 1).min() * 100
    return sh, cagr, mdd, (eq[-1] - 1) * 100


def main() -> None:
    print("TIDE 200d 레짐 게이트 on/off — 라이브 구현 재현")
    print(f"  게이트: {GATE_LB}d SMA · 진입 {GATE_CONFIRM}일 확인 · bull {GATE_BULL} / non-bull {GATE_NON_BULL}")
    print(f"  나머지 라이브 고정: TSM {SHORT}/{LONG} · V{int(VOL_TARGET*100)} · VOL_LB {VOL_LB} · 편도 {FEE:.2%}")

    for label, tick in [("KRW-BTC + KRW-ETH (라이브 유니버스)", LIVE), ("유니버스 40종 (검정력)", None)]:
        keys, cl, rets, sig, scale, gate = build(load(tick))
        base_w = sig * scale * WEIGHT_PER_TICKER / max(1, len(keys) / 2)
        print(f"\n{'='*76}\n## {label} — 종목 {len(keys)} · {len(cl)}일")
        bull_frac = (gate >= GATE_BULL).mean() * 100
        print(f"  게이트 bull 비율 {bull_frac:.1f}% (나머지 기간은 비중 절반)")
        print(f"{'구성':>26}{'Sharpe':>9}{'연수익':>10}{'MDD':>9}{'누적':>12}")
        print("-" * 68)
        out = {}
        for name, w in [("게이트 ON (라이브)", base_w * gate), ("게이트 OFF", base_w)]:
            r = simulate(rets, w)
            out[name] = r
            sh, cg, md, cum = stats(r)
            print(f"{name:>26}{sh:>9.2f}{cg:>9.1f}%{md:>8.1f}%{cum:>11.0f}%")
        bh = rets.mean(axis=1)
        sh, cg, md, cum = stats(bh)
        print(f"{'매수보유':>26}{sh:>9.2f}{cg:>9.1f}%{md:>8.1f}%{cum:>11.0f}%")

        on, off = out["게이트 ON (라이브)"], out["게이트 OFF"]
        d = on - off
        t = d.mean() / (d.std() / sqrt(len(d))) if d.std() else float("nan")
        print()
        print(f"  차이(ON−OFF) 일평균 {d.mean()*1e4:+.2f}bp · t={t:+.2f} "
              f"{'(유의)' if abs(t) > 2 else '(유의하지 않음)'}")
        # 하락장에서 값을 하는가 — 게이트의 존재 이유
        dn = bh < 0
        print(f"  하락일({dn.sum()}일) 평균: ON {on[dn].mean()*100:+.3f}% vs OFF {off[dn].mean()*100:+.3f}%")
        print(f"  상승일({(~dn).sum()}일) 평균: ON {on[~dn].mean()*100:+.3f}% vs OFF {off[~dn].mean()*100:+.3f}%")


if __name__ == "__main__":
    main()
