#!/usr/bin/env python3
"""크립토 TSM 롱숏 검정 — 하락 신호에서 숏을 치면 나아지는가.

## 질문 (PM 2026-08-17): "하락이 예측되면 리버스로 투자하던가"

**이미 짚힌 구멍이다.** TIDE `research/ensemble_mr_t4a_2026_05_30.md:38` (3개월 전):

    TSM/MR 모두 long-only 구조 → 시장 폭락 시 둘 다 손실.
    ensemble = pure aggregation, not diversification.

배리티 라이브러리 193행에도 같은 지적이 있다 — "학술 모멘텀 = 롱숏 spread 알파인데
종목당 0~100 점수로 변환(long-short construction 부재)".

그리고 정전 논문이 원래 롱숏이다. MOP(2012, JFE 104(2):228-250)의 TSM 은 과거 수익 **부호**
에 따라 long/short 을 정하는 구조이고, TIDE 는 그중 음수 구간을 **현금(flat)** 으로 접은
long-flat 변형이다. 즉 우리는 학술 원형의 절반만 구현하고 있다.

2026 실측이 이 구멍을 정확히 가리킨다 — BTC/ETH 매수보유 −34.2% 인데 TIDE 는 −8.2% 로
방어만 했다. 숏이 있었으면 그 구간이 수익이었을 수 있다.

## 설계

  · 신호 = 대칭 TSM. sig = (sign(r_30) + sign(r_90))/2 ∈ {−1, −0.5, 0, +0.5, +1}
      long-flat(현행) = 음수 구간을 0 으로 접음
      long-short      = 그대로 사용
      short-only      = 양수 구간을 0 으로 접음 (숏 다리 단독 기여 확인용)
  · vol-targeting 은 |sig| 에 적용. 레짐 게이트는 on/off 둘 다 낸다
  · 🚨 **펀딩비** — 무기한선물 숏은 펀딩을 주고받는다. 하락장에선 숏이 받는 경우가 많으나
    뒤집힐 수 있어 0(낙관) / 일 0.01%(비관, 연 3.65% 비용) 양쪽을 낸다.
  · 연도별 분해가 핵심이다 — 질문이 "나쁜 해를 구제하는가" 이므로.
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


def build(book):
    keys = sorted(book)
    n = min(len(book[k]) for k in keys)
    cl = np.column_stack([book[k][-n:, 4] for k in keys])
    dates = book[keys[0]][-n:, 0].astype(int) // 10000
    rets = np.zeros_like(cl)
    rets[1:] = cl[1:] / cl[:-1] - 1.0
    # 🚨 신호 두 종류를 분리한다 — 안 그러면 변경 두 개가 섞인다.
    #   cur = 현행 boolean. 한쪽만 양수면 **0.5**(half long). {0, 0.5, 1.0}
    #   sym = 대칭 sign. 한쪽만 양수면 **0**(상쇄). {−1, −0.5, 0, 0.5, 1.0}
    #   현행→대칭롱플랫 = '혼합 구간 처리' 변경 / 대칭롱플랫→롱숏 = '숏 다리' 추가
    cur = np.zeros_like(cl)
    cur[SHORT:] += (cl[SHORT:] > cl[:-SHORT]).astype(float)
    cur[LONG:] += (cl[LONG:] > cl[:-LONG]).astype(float)
    cur /= 2.0
    cur[:LONG] = 0.0
    sym = np.zeros_like(cl)
    sym[SHORT:] += np.sign(cl[SHORT:] - cl[:-SHORT])
    sym[LONG:] += np.sign(cl[LONG:] - cl[:-LONG])
    sym /= 2.0
    sym[:LONG] = 0.0
    vol = np.full_like(cl, np.nan)
    for j in range(cl.shape[1]):
        for i in range(VOL_LB, len(cl)):
            vol[i, j] = rets[i - VOL_LB:i, j].std() * sqrt(ANN)
    scale = np.nan_to_num(np.clip(np.where(vol > 0, VOL_TARGET / vol, 0.0), 0.0, 1.0))
    gate = np.column_stack([gate_series(cl[:, j]) for j in range(cl.shape[1])])
    return keys, dates, rets, cur, sym, scale, gate


def simulate(rets, w, funding=0.0):
    ww = np.vstack([np.zeros((1, w.shape[1])), w[:-1]])
    turn = np.abs(ww - np.vstack([np.zeros((1, w.shape[1])), ww[:-1]])).sum(axis=1)
    fund = np.clip(-ww, 0, None).sum(axis=1) * funding      # 숏 노출에만 부과
    return (ww * rets).sum(axis=1) - turn * FEE - fund


def stats(r):
    r = r[np.isfinite(r)]
    eq = np.cumprod(1 + r)
    sh = r.mean() / r.std() * sqrt(ANN) if r.std() else float("nan")
    cagr = (eq[-1] ** (ANN / len(r)) - 1) * 100
    mdd = (eq / np.maximum.accumulate(eq) - 1).min() * 100
    return sh, cagr, mdd, cagr / abs(mdd) if mdd else float("nan")


def main() -> None:
    print("크립토 TSM 롱숏 검정 — 하락 구간에 숏을 치면 나아지는가")
    print(f"  대칭 신호 sign(r{SHORT}) + sign(r{LONG}) · V{int(VOL_TARGET*100)} · 편도 {FEE:.2%}")

    for label, tick in [("KRW-BTC + KRW-ETH (라이브)", LIVE), ("유니버스 40종", None)]:
        keys, dates, rets, cur, sym, scale, gate = build(load(tick))
        nz = max(1, len(keys) / 2)
        variants = {}
        for gname, g in [("게이트 ON", gate), ("게이트 OFF", np.ones_like(gate))]:
            base = scale * g * WEIGHT_PER_TICKER / nz
            variants[f"① 현행 롱플랫 {gname}"] = cur * base
            variants[f"② 대칭 롱플랫 {gname}"] = np.clip(sym, 0, None) * base
            variants[f"③ 대칭 롱숏 {gname}"] = sym * base
            variants[f"④ 숏온리 {gname}"] = np.clip(sym, None, 0) * base

        print(f"\n{'='*88}\n## {label} — 종목 {len(keys)} · {len(rets)}일 · {dates.min()}~{dates.max()}")
        print(f"{'구성':>24}{'Sharpe':>9}{'연수익':>9}{'MDD':>9}{'Calmar':>8}"
              f"{'펀딩0.01%적용':>14}{'평균노출':>9}")
        print("-" * 88)
        keep = {}
        for name, w in variants.items():
            r0 = simulate(rets, w, 0.0)
            r1 = simulate(rets, w, 0.0001)
            sh, cg, md, ca = stats(r0)
            sh1 = stats(r1)[0]
            keep[name] = r0
            print(f"{name:>24}{sh:>9.2f}{cg:>8.1f}%{md:>8.1f}%{ca:>8.2f}{sh1:>13.2f}"
                  f"{np.abs(w).sum(axis=1).mean()*100:>8.1f}%")
        bh = rets.mean(axis=1)
        sh, cg, md, ca = stats(bh)
        print(f"{'매수보유':>24}{sh:>9.2f}{cg:>8.1f}%{md:>8.1f}%{ca:>8.2f}")

        # ── 연도별 — 질문의 핵심 ──
        print()
        print("  연도별 수익 (%) — 나쁜 해를 구제하는가")
        cols = ["① 현행 롱플랫 게이트 ON", "② 대칭 롱플랫 게이트 ON",
                "③ 대칭 롱숏 게이트 ON", "④ 숏온리 게이트 ON"]
        print(f"  {'연도':>6}" + "".join(f"{c.replace(' 게이트 ON','').replace('① ','').replace('② ','').replace('③ ','').replace('④ ',''):>13}" for c in cols) + f"{'매수보유':>11}")
        print("  " + "-" * 74)
        for y in sorted(set(dates.tolist())):
            m = dates == y
            if m.sum() < 60:
                continue
            row = "".join(f"{(np.prod(1+keep[c][m])-1)*100:>12.1f}%" for c in cols)
            print(f"  {y:>6}{row}{(np.prod(1+bh[m])-1)*100:>10.1f}%")

        from pbo_selection_gate import pbo_cscv
        M = np.column_stack([keep[c] for c in cols])
        print()
        print(f"  선택 게이트 PBO {pbo_cscv(M, s_blocks=10):.1%}")


if __name__ == "__main__":
    main()
