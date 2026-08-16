#!/usr/bin/env python3
"""재난 브레이커 — 포트폴리오 종점 재판정. 등록서 §9 근거 산출.

## 왜

`DISASTER_BREAKER_PREREG_20260817.md` §5 는 종점을 **거래별 최악 손실**로 잡았고, 그 기준으로
−20% 가 통과했다(40종 최악 −60.1%→−20.1%). 그런데 구현 단계에서 업비트 API 스톱 미지원이
드러나 "인프라를 지어야 하나" 로 넘어갔다.

인프라를 논하기 전에 물어야 할 것이 남아 있었다 —
**브레이커가 완벽하게 체결된다면 계좌에 얼마나 값을 하는가.**

여기서 그걸 잰다. 체결은 장중 저가 터치(=이상적 지정가 스톱)로 두고, 실행 가능성 제약을
전부 무시한 **상한** 을 낸다. 이 상한이 작으면 인프라 논의 자체가 불필요하다.

## 결과 (등록서 §9 에 반영)

라이브 유니버스(BTC/ETH)에서 완벽 체결을 가정해도 MDD 가 −25.4% → −25.7% 로 **악화**한다.
개별 거래 −60% 는 이미 vol-targeting 으로 비중이 줄어든 포지션이라, 잘라도 계좌 낙폭이
움직이지 않고 회복 구간만 놓친다. → 브레이커 기각, 인프라 불필요.

🚨 **교훈 = 종점을 거래 단위로 잡으면 포트폴리오에 없는 개선을 쫓는다.**
같은 함정이 같은 날 두 번 나왔다(진입 확인일수 / 본 등록). 앞으로 산식·규칙 등록의
1차 종점은 포트폴리오 단위로 잡는다.
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
SHORT, LONG, ANN = 30, 90, 365
VOL_TARGET, VOL_LB, FEE = 0.40, 30, 0.0005
GATE_LB, GATE_CONFIRM = 200, 3


def load(only=None):
    out = {}
    for p in sorted(glob.glob(os.path.join(OHLC_DIR, "*.json"))):
        d = json.load(open(p))
        if only and d["m"] not in only:
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


def portfolio(book, breaker=None):
    """breaker = 장중 저가 터치 시 즉시 비중 0 + 신호 소멸까지 래치(이상적 체결 = 상한)."""
    keys = sorted(book)
    n = min(len(book[k]) for k in keys)
    cl = np.column_stack([book[k][-n:, 4] for k in keys])
    lo = np.column_stack([book[k][-n:, 3] for k in keys])
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
    w = sig * scale * gate * 0.5 / max(1, len(keys) / 2)
    if breaker is not None:
        for j in range(cl.shape[1]):
            e, latched = None, False
            for i in range(len(cl)):
                if w[i, j] <= 0:
                    e, latched = None, False
                    continue
                if latched:
                    w[i, j] = 0.0
                    continue
                if e is None:
                    e = cl[i, j]
                if lo[i, j] <= e * (1 - breaker):
                    w[i, j] = 0.0
                    latched = True
    ww = np.vstack([np.zeros((1, w.shape[1])), w[:-1]])
    turn = np.abs(ww - np.vstack([np.zeros((1, w.shape[1])), ww[:-1]])).sum(axis=1)
    return (ww * rets).sum(axis=1) - turn * FEE


def stats(r):
    eq = np.cumprod(1 + r)
    return (r.mean() / r.std() * sqrt(ANN), (eq[-1] ** (ANN / len(r)) - 1) * 100,
            (eq / np.maximum.accumulate(eq) - 1).min() * 100)


def main() -> None:
    print("재난 브레이커 — 포트폴리오 종점 (완벽 체결 가정 = 실효 상한)")
    print("  실행 가능성 제약을 전부 무시한 상한. 이게 작으면 인프라 논의가 불필요하다.")
    for lab, only in [("KRW-BTC + KRW-ETH (라이브)", LIVE), ("유니버스 40종", None)]:
        book = load(only)
        print(f"\n## {lab}")
        print(f"{'구성':>18}{'Sharpe':>9}{'연수익':>9}{'MDD':>9}{'Calmar':>9}")
        print("-" * 54)
        for name, b in [("브레이커 없음(현행)", None), ("−20% 완벽체결", 0.20),
                        ("−30% 완벽체결", 0.30), ("−40% 완벽체결", 0.40)]:
            sh, cg, md = stats(portfolio(book, b))
            print(f"{name:>18}{sh:>9.2f}{cg:>8.1f}%{md:>8.1f}%{cg/abs(md):>9.2f}")
    print()
    print("  🚨 판정: 라이브 유니버스에서 완벽 체결도 MDD 를 못 줄인다 → 브레이커 기각.")
    print("     개별 거래 최악은 이미 vol-targeting 으로 비중이 줄어든 포지션이라")
    print("     계좌 낙폭에 거의 전달되지 않는다. 등록서 §9 참조.")


if __name__ == "__main__":
    main()
