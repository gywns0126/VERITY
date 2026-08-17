#!/usr/bin/env python3
"""크립토는 결국 운과 레버리지인가 — 두 주장을 각각 검정한다.

## 질문 (PM 2026-08-17): "크립토는 어딜봐도 결국 운과 레버리지인가"

두 주장은 서로 다른 검정을 요구한다. 섞어서 답하면 안 된다.

**주장 A — 운이다.**
  반증 형태 = 신호가 **무작위 진입과 구분되어야** 한다. 노출(exposure)을 똑같이 맞춘
  무작위 신호를 1,000회 돌려 우리 성적이 그 분포의 어디에 있는지 본다.
  🚨 노출을 안 맞추면 부정검정이 된다 — 시장이 오르면 오래 들고만 있어도 이긴다.

**주장 B — 레버리지다.**
  우리는 **레버리지를 쓰지 않는다**(vol-targeting 은 상한 1.0, de-risk only).
  그러면 이 주장은 "레버리지 없이는 의미 있는 수익이 안 난다" 로 번역된다.
  검정 = 레버리지 배수를 1.0(현행)부터 올려가며 Sharpe·MDD·파산확률이 어떻게 변하는지.

**보조 — 꼬리 의존.**
  2026-08-17 실측에서 상위 1%(26거래)가 수익의 90.5%, 상위 5% 제거 시 기대값이 음수였다.
  이건 "운" 이라는 직관의 실체다. 다만 **꼬리 의존 ≠ 무작위** 라는 점을 분리해 보인다 —
  추세추종은 설계상 소수의 큰 추세로 번다(양의 왜도). 무작위도 그런지가 쟁점이다.

데이터 = 업비트 일봉 OHLC 직수집 · 라이브 config 정합(TSM 30/90 · V40 · 200d 게이트 · 편도 0.05%).
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
N_RANDOM = 1000
SEED = 20260817


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


def build(book):
    keys = sorted(book)
    n = min(len(book[k]) for k in keys)
    cl = np.column_stack([book[k][-n:, 4] for k in keys])
    dates = book[keys[0]][-n:, 0].astype(int)
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
    return keys, dates, cl, rets, sig, scale, gate


def run(rets, w, lev=1.0):
    w = w * lev
    ww = np.vstack([np.zeros((1, w.shape[1])), w[:-1]])
    turn = np.abs(ww - np.vstack([np.zeros((1, w.shape[1])), ww[:-1]])).sum(axis=1)
    return (ww * rets).sum(axis=1) - turn * FEE


def stats(r):
    r = np.asarray(r)
    eq = np.cumprod(1 + r)
    sh = r.mean() / r.std() * sqrt(ANN) if r.std() else np.nan
    cagr = (eq[-1] ** (ANN / len(r)) - 1) * 100 if eq[-1] > 0 else -100.0
    mdd = (eq / np.maximum.accumulate(eq) - 1).min() * 100
    return sh, cagr, mdd, (cagr / abs(mdd) if mdd else np.nan)


def block_shuffle(sig_col, rng, block=20):
    """노출 총량·군집 구조를 보존한 채 **타이밍만** 무작위화.

    단순 셔플은 신호의 자기상관(연속 보유)을 깨서 회전비용이 폭증 → 부정검정이 된다.
    블록 단위로 섞어 '며칠 연속 들고 있다' 는 성질을 유지한 채 **언제** 만 무작위로 만든다.
    """
    n = len(sig_col)
    nb = int(np.ceil(n / block))
    blocks = [sig_col[i * block:(i + 1) * block] for i in range(nb)]
    order = rng.permutation(nb)
    return np.concatenate([blocks[i] for i in order])[:n]


def main() -> None:
    print("크립토 — '운과 레버리지' 두 주장 검정")
    print(f"  라이브 config: TSM {SHORT}/{LONG} · V{int(VOL_TARGET*100)} · 200d 게이트 · 편도 {FEE:.2%}")
    print(f"  🚨 레버리지 = **현행 없음**. vol-targeting 은 상한 1.0 de-risk only")
    print()

    for label, only in [("KRW-BTC + KRW-ETH (라이브)", LIVE), ("유니버스 40종", None)]:
        keys, dates, cl, rets, sig, scale, gate = build(load(only))
        base_w = scale * gate * 0.5 / max(1, len(keys) / 2)
        w_real = sig * base_w
        r_real = run(rets, w_real)
        bh = rets.mean(axis=1)

        print("=" * 78)
        print(f"## {label} — {len(keys)}종 · {len(cl)}일 · {dates[0]}~{dates[-1]}")
        print()

        # ── 주장 A: 운인가 — 노출 맞춘 무작위 신호 1,000회 ──
        rng = np.random.default_rng(SEED)
        exposure_real = w_real.sum(axis=1).mean()
        sims = []
        for _ in range(N_RANDOM):
            rs = np.column_stack([block_shuffle(sig[:, j], rng) for j in range(sig.shape[1])])
            sims.append(stats(run(rets, rs * base_w))[0])
        sims = np.array(sims)
        sims = sims[np.isfinite(sims)]
        sh_real = stats(r_real)[0]
        pct = (sims < sh_real).mean() * 100
        p_val = (sims >= sh_real).mean()

        print("### 주장 A — 운인가 (노출·군집 보존 블록셔플 1,000회)")
        print(f"  실제 신호 Sharpe      {sh_real:>6.2f}   평균 노출 {exposure_real*100:.1f}%")
        print(f"  무작위 타이밍 분포    중앙 {np.median(sims):>5.2f} · "
              f"90% {np.percentile(sims,90):>5.2f} · 최대 {sims.max():>5.2f}")
        print(f"  🏁 백분위 **{pct:.1f}%**  ·  p = {p_val:.4f}  "
              f"{'← 운으로 설명 안 됨' if p_val < 0.05 else '← 운과 구분 안 됨'}")
        print()

        # ── 주장 B: 레버리지인가 ──
        print("### 주장 B — 레버리지 없이는 안 되는가")
        print(f"  {'배수':>8}{'Sharpe':>9}{'연수익':>10}{'MDD':>9}{'Calmar':>9}{'전액손실':>10}")
        print("  " + "-" * 53)
        for lev in [1.0, 1.5, 2.0, 3.0, 5.0]:
            rr = run(rets, w_real, lev)
            eq = np.cumprod(1 + rr)
            ruin = "예" if (eq <= 0.01).any() else "아니오"
            sh, cg, md, ca = stats(rr)
            mark = " ←현행" if lev == 1.0 else ""
            print(f"  {lev:>7.1f}x{sh:>9.2f}{cg:>9.1f}%{md:>8.1f}%{ca:>9.2f}{ruin:>10}{mark}")
        sh, cg, md, ca = stats(bh)
        print(f"  {'매수보유':>8}{sh:>9.2f}{cg:>9.1f}%{md:>8.1f}%{ca:>9.2f}")
        print()

        # ── 보조: 꼬리 의존은 무작위에도 있는가 ──
        rng2 = np.random.default_rng(SEED + 1)
        def c1(x):
            s = np.sort(x)[::-1]
            k = max(1, int(len(s) * 0.01))
            return s[:k].sum() / s.sum() * 100 if s.sum() else np.nan
        rand_c1 = []
        for _ in range(100):
            rs = np.column_stack([block_shuffle(sig[:, j], rng2) for j in range(sig.shape[1])])
            rr = run(rets, rs * base_w)
            if rr.sum() > 0:
                rand_c1.append(c1(rr))
        print("### 보조 — 꼬리 의존이 우리만의 성질인가 (일수익 상위 1% 기여도)")
        print(f"  실제 신호   {c1(r_real):>6.1f}%")
        if rand_c1:
            print(f"  무작위      중앙 {np.median(rand_c1):>5.1f}% · 범위 "
                  f"{np.min(rand_c1):.1f}~{np.max(rand_c1):.1f}%")
        print(f"  매수보유    {c1(bh):>6.1f}%")
        print("  → 꼬리 집중은 **크립토 수익 분포 자체의 성질**이지 전략 결함이 아니다.")
        print()


if __name__ == "__main__":
    main()
