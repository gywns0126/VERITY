#!/usr/bin/env python3
"""크립토 외생 요인이 TIDE 를 오염·개선하는가 — 주식에 없는 축만 검정.

## 질문 (PM 2026-08-17)

"외부 세력에 의해 영향받는 경우가 있던데, 주식과 달리 여타 영향 요소가 있는지 확인 후 검증"

지금까지 TIDE 검정은 **가격만** 썼다. 크립토에는 주식에 대응물이 없는 외생 축이 있고
우리는 그걸 스냅샷으로만 갖고 있어 백테스트에 못 넣었다. `crypto_exogenous_history.py` 로
전 구간 시계열을 만들었으므로 여기서 처음 검정한다.

## 검정하는 것

  ① 🚨 **김치 프리미엄 오염** — TIDE 는 **업비트 원화**로 거래하는데 신호도 원화 가격으로
     계산한다. 김프가 출렁이면 원화 수익 ≠ 글로벌 수익이므로, 우리가 잡은 "추세" 가
     실제 시장 추세가 아니라 **환·프리미엄 변동**일 수 있다. 이게 사실이면 지금까지의
     모든 크립토 검정이 오염된다 — 가장 하중이 큰 축이라 먼저 친다.
  ② **펀딩비 극단** = 레버리지 쏠림. 주식에 만기 없는 영구계약이 없어 대응물이 없다.
     급락(=재난 브레이커 발동)을 선행하는가.
  ③ **FNG 극단** — 크립토 전용 심리지수.
  ④ **반감기 사이클 위치** — 공급 스케줄이 코드로 고정. 2025~26 부진이 사이클 국면인가.
  ⑤ **ETF 시대(2024-01-11~)** 전후 구조 변화.

각 축은 **조건부 성과**로 본다: 요인 분위별로 TIDE 수익이 다른가. 다르면 신호에 쓸 여지가
있고, 같으면 관측만 하면 된다.

🚨 이 스크립트는 **배선하지 않는다.** 신호 추가는 RULE 7 사전등록 별건이다.
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

EXO = "data/crypto_exogenous_history.json"
OHLC_DIR = ("/private/tmp/claude-501/-Users-macbookpro-Desktop--------/"
            "3b4bdb64-7a07-412b-b2cf-029170e8bf91/scratchpad/upbit_ohlc")
SHORT, LONG, ANN = 30, 90, 365
VOL_TARGET, VOL_LB, FEE = 0.40, 30, 0.0005
GATE_LB, GATE_CONFIRM = 200, 3


def load_exo():
    d = json.load(open(EXO))
    return {r["date"]: r for r in d["rows"]}, d["coverage"]


def load_ohlc(only=None):
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


def tide_returns(book):
    keys = sorted(book)
    n = min(len(book[k]) for k in keys)
    raw = book[keys[0]][-n:, 0].astype(int)
    dates = [f"{d//10000:04d}-{d//100%100:02d}-{d%100:02d}" for d in raw]
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
    w = sig * scale * gate * 0.5 / max(1, len(keys) / 2)
    ww = np.vstack([np.zeros((1, w.shape[1])), w[:-1]])
    turn = np.abs(ww - np.vstack([np.zeros((1, w.shape[1])), ww[:-1]])).sum(axis=1)
    r = (ww * rets).sum(axis=1) - turn * FEE
    return dates, r, cl, rets


def sharpe(r):
    r = np.asarray(r)
    r = r[np.isfinite(r)]
    return r.mean() / r.std() * sqrt(ANN) if len(r) > 30 and r.std() else float("nan")


def quintile_table(name, dates, r, exo, field, lag=1):
    """요인을 lag 일 지연시켜(룩어헤드 차단) 5분위로 나눠 다음날 수익 비교."""
    x, y = [], []
    for i in range(lag, len(dates)):
        v = exo.get(dates[i - lag], {}).get(field)
        if v is None or not np.isfinite(r[i]):
            continue
        x.append(v); y.append(r[i])
    if len(x) < 200:
        print(f"  {name}: 표본 {len(x)} — 부족")
        return
    x, y = np.array(x), np.array(y)
    qs = np.quantile(x, [0.2, 0.4, 0.6, 0.8])
    print(f"  {name} (표본 {len(x):,}일 · {lag}일 지연)")
    print(f"    {'분위':>6}{'요인 범위':>22}{'일수':>7}{'평균수익':>11}{'Sharpe':>9}")
    for k in range(5):
        lo = -np.inf if k == 0 else qs[k - 1]
        hi = np.inf if k == 4 else qs[k]
        m = (x >= lo) & (x < hi) if k < 4 else (x >= lo)
        if m.sum() < 30:
            continue
        rng = f"{x[m].min():.2f}~{x[m].max():.2f}"
        print(f"    {'Q'+str(k+1):>6}{rng:>22}{m.sum():>7}{y[m].mean()*1e4:>10.2f}bp{sharpe(y[m]):>9.2f}")
    lo_m = x <= qs[0]; hi_m = x >= qs[3]
    d = y[hi_m].mean() - y[lo_m].mean()
    se = sqrt(y[hi_m].var(ddof=1) / hi_m.sum() + y[lo_m].var(ddof=1) / lo_m.sum())
    print(f"    Q5−Q1 = {d*1e4:+.2f}bp · t={d/se:+.2f} "
          f"{'← 유의' if abs(d/se) > 2 else '(유의하지 않음)'}")
    print()


def main() -> None:
    exo, cov = load_exo()
    print("크립토 외생 요인 검정 — 주식에 없는 축만")
    print(f"  요인 시계열 {cov['days']}일 · {cov['range'][0]}~{cov['range'][1]}")
    print(f"  커버리지: FNG {cov['fng']} · 펀딩 {cov['funding_btc']} · 김치 {cov['kimchi']}")
    print()

    # ── ① 김치 프리미엄 오염 — 가장 하중이 큰 축 ──────────────────────────
    print("=" * 84)
    print("## ① 🚨 김치 프리미엄 오염 — 우리가 잡은 추세가 진짜 시장 추세인가")
    up = load_ohlc(["KRW-BTC"])["KRW-BTC"]
    updates = [f"{int(d)//10000:04d}-{int(d)//100%100:02d}-{int(d)%100:02d}" for d in up[:, 0]]
    kp = np.array([exo.get(d, {}).get("kimchi_premium_pct", np.nan) for d in updates], dtype=float)
    ok = np.isfinite(kp)
    print(f"  김프 관측 {ok.sum()}일 · 평균 {np.nanmean(kp):+.2f}% · 표준편차 {np.nanstd(kp):.2f}%p")
    print(f"  범위 {np.nanmin(kp):+.2f}% ~ {np.nanmax(kp):+.2f}%")
    krw_r = np.diff(up[:, 4]) / up[:-1, 4]
    dkp = np.diff(kp)
    m = np.isfinite(dkp) & np.isfinite(krw_r)
    # 원화 수익 = 글로벌 수익 + 김프 변화(근사). 김프 변화가 원화 수익의 몇 %를 설명하나
    var_share = np.nanvar(dkp[m] / 100) / np.nanvar(krw_r[m]) * 100
    print(f"  김프 일변화 표준편차 {np.nanstd(dkp[m]):.3f}%p vs 원화 일수익 표준편차 {np.nanstd(krw_r[m])*100:.3f}%")
    print(f"  → 김프 변동이 원화 수익 분산에서 차지하는 비중 ≈ **{var_share:.2f}%**")
    print(f"  상관(김프변화, 원화수익) = {np.corrcoef(dkp[m], krw_r[m])[0,1]:+.3f}")
    if var_share < 5:
        print("  판정: 오염 미미 — 원화 가격으로 계산한 신호를 계속 써도 된다")
    else:
        print("  🚨 판정: 오염 유의 — 신호를 글로벌 가격으로 계산해야 할 수 있다")
    print()

    # ── ②~⑤ 조건부 성과 ──────────────────────────────────────────────────
    for label, only in [("KRW-BTC + KRW-ETH (라이브)", ["KRW-BTC", "KRW-ETH"]),
                        ("유니버스 40종", None)]:
        dates, r, cl, rets = tide_returns(load_ohlc(only))
        print("=" * 84)
        print(f"## 조건부 성과 — {label} (TIDE 현행 · {len(dates)}일)")
        print()
        quintile_table("② 펀딩비(일간 합계)", dates, r, exo, "funding_btc_daily")
        quintile_table("③ 공포탐욕지수 FNG", dates, r, exo, "fng")
        quintile_table("④ 반감기 후 경과일", dates, r, exo, "days_since_halving")
        if only and "KRW-BTC" in only:
            quintile_table("⑤ 김치 프리미엄", dates, r, exo, "kimchi_premium_pct")

        era = np.array([exo.get(d, {}).get("etf_era") for d in dates])
        for lab, m in [("ETF 이전", era == False), ("ETF 이후(2024-01-11~)", era == True)]:
            m = np.array([bool(v) for v in m])
            if m.sum() > 60:
                print(f"  ⑥ {lab:>22}: {m.sum():>5}일 · Sharpe {sharpe(r[m]):>6.2f} · "
                      f"일평균 {r[m].mean()*1e4:+7.2f}bp")
        print()


if __name__ == "__main__":
    main()
