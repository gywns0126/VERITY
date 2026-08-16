#!/usr/bin/env python3
"""재난 브레이커 실행 가능성 — 얼마나 자주 봐야 실효가 있는가.

## 왜 이 검정이 필요해졌나 (2026-08-17)

사전등록 정식 측정에서 **−20% 브레이커가 통과**했다(최악 −60.1%→−20.1%). 그런데 그 측정은
**장중 저가 터치 = 지정가 스톱 주문**을 가정했다. 라이브 반영을 시작하며 두 가지가 드러났다.

1. 🚨 **업비트 API 는 스톱 주문을 지원하지 않는다.** 1차 자료 확인(docs.upbit.com 주문 API):
   `ord_type` = `limit` / `price` / `market` / `best` 4개뿐이고 조건부 주문 파라미터가 없다.
   `time_in_force`(IOC/FOK/Post Only) 와 `smp_type` 도 스톱 기능이 아니다.
   우리 클라이언트(`tide/data/upbit_client.py`)도 시장가 매수·매도만 구현돼 있다.
2. 🚨 **TIDE 는 하루 1회 사이클**이라 그 방식으로는 최악을 못 막는다. 실측:

       체결 방식              BTC/ETH 최악    40종 최악
       지정가 스톱(등록 가정)     −20.1%        −20.1%
       하루 1회 종가 판정        −28.3%        −57.1%

   40종은 −60.1% → −57.1% 로 **3%p 개선에 그친다**. 크립토는 하루 안에 −20% 를 크게
   넘겨 빠지므로, 다음 사이클에는 이미 늦는다.

즉 **등록 §5 제약 A·B 는 통과하지만 §5-3 의 목적(최악 손실 최소)을 달성하지 못한다.**
"통과했으니 넣는다" 로 가면 **작동하지 않는 안전장치**를 달고 안심하게 된다.

## 이 스크립트가 답하는 것

스톱 주문이 없다면 남은 수단은 **폴링 주기 단축**뿐이다. 그래서 묻는다 —
**몇 시간마다 확인하면 −20% 브레이커가 실효를 갖는가?**

데이터 = 업비트 60분봉 직수집(BTC/ETH 각 75,600봉, 2018~2026).
거래 구간은 일봉 신호로 정하고(라이브와 동일), 그 안에서 폴링 주기별로 체결을 시뮬레이션한다.
"장중 저가" 는 이론 상한(= 지정가 스톱이 있었다면)이며 실행 가능한 값이 아니다.
"""
from __future__ import annotations

import glob
import json
import os
from math import sqrt

import datetime as dtm
import numpy as np

H1_DIR = ("/private/tmp/claude-501/-Users-macbookpro-Desktop--------/"
          "3b4bdb64-7a07-412b-b2cf-029170e8bf91/scratchpad/upbit_h1")
D1_DIR = ("/private/tmp/claude-501/-Users-macbookpro-Desktop--------/"
          "3b4bdb64-7a07-412b-b2cf-029170e8bf91/scratchpad/upbit_ohlc")
LIVE = ("KRW-BTC", "KRW-ETH")
SHORT, LONG = 30, 90
GATE_LB, GATE_CONFIRM = 200, 3
WARMUP, MAX_HOLD = LONG + 5, 400
FEE_RT = 0.001
BREAKER = 0.20
POLLS = [24, 12, 8, 6, 4, 2, 1]          # 확인 주기(시간)


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


def load_pair(mkt):
    """🚨 업비트 일봉과 분봉은 기준일이 다르다 (2026-08-17 실측으로 확인).

    일봉 `candle_date_time_kst` = **UTC 기준일** 캔들 (KST 09:00 ~ 익일 09:00).
    분봉 `candle_date_time_kst` = KST 실제 시각.
    분봉을 KST 자정으로 묶으면 **하루가 어긋난다.**

    실측 반례: 2020-03-12 일봉 저가 5,980,000 인데 분봉 KST 3/12 최저는 7,266,000 이고
    5,980,000 은 분봉 KST 3/13 에 나타난다. 이 오정렬로 전체 2,800일 중 **24.6%** 에서
    "일봉 저가 < 분봉 최저저가" 라는 불가능한 관계가 만들어졌다.

    → 분봉을 **UTC 기준일**(KST − 9h)로 묶어 일봉과 정렬한다.
    """
    d1 = np.array(json.load(open(os.path.join(D1_DIR, f"{mkt}.json")))["c"], dtype=float)
    h1 = json.load(open(os.path.join(H1_DIR, f"{mkt}_60.json")))["c"]
    kst = np.array([dtm.datetime.fromisoformat(r[0]) for r in h1])
    utc = kst - dtm.timedelta(hours=9)
    hd = np.array([int(t.strftime("%Y%m%d")) for t in utc])   # 일봉과 같은 기준일
    hh = np.array([t.hour for t in utc])                       # UTC 시(0~23)
    hlow = np.array([r[2] for r in h1], dtype=float)
    hclose = np.array([r[3] for r in h1], dtype=float)
    return d1, hd, hh, hlow, hclose


def simulate(mkt, poll_hours):
    """poll_hours=None → 장중 저가(이론 상한). 24 → 하루 1회 종가. 그 외 → n시간마다 종가 확인."""
    d1, hd, hh, hlow, hclose = load_pair(mkt)
    dts, lo, cl = d1[:, 0].astype(int), d1[:, 3], d1[:, 4]
    n = len(cl)
    sig = np.zeros(n)
    sig[SHORT:] += (cl[SHORT:] > cl[:-SHORT]).astype(float)
    sig[LONG:] += (cl[LONG:] > cl[:-LONG]).astype(float)
    sig /= 2.0
    sig[:LONG] = 0.0
    g = gate_series(cl)
    inpos = (sig > 0) & (g > 0)

    out = []
    i = WARMUP
    while i < n - 1:
        if inpos[i] and not inpos[i - 1]:
            j = i + 1
            while j < n and inpos[j] and (j - i) < MAX_HOLD:
                j += 1
            e = cl[i]
            lvl = e * (1 - BREAKER)
            end = min(j, n - 1)
            r = None
            if poll_hours is None:                       # 이론 상한 = 지정가 스톱
                seg = lo[i + 1:end + 1]
                if len(seg) and (seg <= lvl).any():
                    r = lvl / e - 1.0
            else:
                d_lo, d_hi = dts[i + 1], dts[end]
                m = (hd >= d_lo) & (hd <= d_hi) & (hh % poll_hours == 0)
                px = hclose[m]
                hit = np.where(px <= lvl)[0]
                if len(hit):
                    r = px[hit[0]] / e - 1.0
            if r is None:
                r = cl[end] / e - 1.0
            out.append(r - FEE_RT)
            i = j
        else:
            i += 1
    return np.array(out)


def main() -> None:
    print("재난 브레이커 −20% — 확인 주기별 실효성")
    print("  🚨 업비트 API 는 스톱 주문 미지원(ord_type = limit/price/market/best).")
    print("     따라서 '지정가 스톱' 행은 실행 불가한 이론 상한이며 비교 기준일 뿐이다.")
    print(f"  데이터 = 업비트 60분봉 직수집 · 신호는 일봉(라이브 동일) · 왕복 {FEE_RT*100:.2f}%")
    print()
    print(f"{'확인 주기':>14}{'BTC 최악':>11}{'BTC 기대값':>13}{'ETH 최악':>11}{'ETH 기대값':>13}{'실행':>8}")
    print("-" * 72)
    rows = []
    for poll in [24, 12, 8, 6, 4, 2, 1]:
        vals = {}
        for m in LIVE:
            r = simulate(m, poll)
            vals[m] = (r.min() * 100, r.mean() * 100)
        lab = "하루 1회(현행)" if poll == 24 else f"{poll}시간마다"
        feas = "현행" if poll == 24 else f"cron {24//poll}회/일"
        rows.append((poll, vals))
        print(f"{lab:>14}{vals['KRW-BTC'][0]:>10.1f}%{vals['KRW-BTC'][1]:>12.2f}%"
              f"{vals['KRW-ETH'][0]:>10.1f}%{vals['KRW-ETH'][1]:>12.2f}%{feas:>8}")
    vals = {m: (simulate(m, None).min() * 100, simulate(m, None).mean() * 100) for m in LIVE}
    print(f"{'지정가 스톱':>14}{vals['KRW-BTC'][0]:>10.1f}%{vals['KRW-BTC'][1]:>12.2f}%"
          f"{vals['KRW-ETH'][0]:>10.1f}%{vals['KRW-ETH'][1]:>12.2f}%{'❌불가':>8}")
    print()
    base = {m: simulate(m, 24) for m in LIVE}
    print("  판정 기준: 브레이커 목적은 '최악 손실 상한'. 최악이 −20%대에 수렴해야 실효.")
    for poll, vals in rows:
        ok = all(vals[m][0] >= -25.0 for m in LIVE)
        if ok:
            print(f"  🏁 최악이 −25% 이내로 들어오는 최소 빈도 = **{poll}시간마다** "
                  f"(일 {24//poll}회 실행)")
            break
    else:
        print("  ❌ 시험한 어떤 빈도로도 −25% 이내에 들어오지 않는다")


if __name__ == "__main__":
    main()
