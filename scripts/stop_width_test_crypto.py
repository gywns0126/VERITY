#!/usr/bin/env python3
"""손절선 검정 — 고정 % vs ATR 스케일. 크립토 대표본으로 VAMS 가설을 친다.

가설(PREREG_VAMS_STOPLOSS_ATR_PRIORITY_2026_08_16 §2):
  "ATR 이 종목별로 계산한 정상 등락폭을 고정 캡이 일괄로 덮는 구조가 틀렸다."

VAMS 반사실은 N=14, 한 사이클이었다. 여기서는 274종목 × 6.5년으로 친다.
크립토 30일 변동성 중앙값 78.7% = 현재 코스피 89.8% 와 같은 대역이라 유사 표본이다.

🚨 검증 못 하는 것: **갭 리스크**. 크립토는 24/7 이라 종가 갭이 없다.
   VAMS 손절이 -5% 인데 -10.1% 에 체결된 현상은 여기서 재현되지 않는다.
   따라서 이 검정은 "폭 vs 변동성 정합" 만 답한다.

설계:
  · 진입 = 20거래일 간격 systematic (진입 규칙이 아니라 **손절 규칙**을 시험)
  · 유동성 필터 = 진입 시점 직전 20일 중앙 거래대금 ≥ 1억 (룩어헤드 없음)
  · ATR = 진입 시점까지의 14일 True Range 근사(종가만 있으므로 |일간수익| 사용)
  · 청산 = 손절 도달 시 그날 종가, 아니면 +20거래일 종가
  · 비교의 핵심 = **평균 손절폭을 맞춘 뒤** 고정 vs ATR 을 본다
"""
from __future__ import annotations
import numpy as np
import pandas as pd

PARQUET = "/Users/macbookpro/Desktop/TIDE/data/cache_ohlcv.parquet"
HOLD = 20           # 최대 보유 거래일
ATR_N = 14
ENTRY_EVERY = 20    # 진입 샘플링 간격
MIN_VALUE = 1e8     # 진입 시점 유동성 하한(원)
WARMUP = 60         # ATR·유동성 계산용 최소 이력

FIXED = [0.05, 0.10, 0.15, 0.20]
ATR_K = [1.5, 2.0, 2.5, 3.0]


def main() -> None:
    df = pd.read_parquet(PARQUET)
    close = df.xs("close", axis=1, level=1).astype(float)
    value = df.xs("value", axis=1, level=1).astype(float)

    ret = close.pct_change(fill_method=None)
    # 종가만 있어 True Range 를 |일간수익| 로 근사한다. ATR% = 평균 일간 변동폭.
    atr_pct = ret.abs().rolling(ATR_N).mean()
    liq = value.rolling(20).median()

    idx = close.index
    rows = []
    for i in range(WARMUP, len(idx) - HOLD, ENTRY_EVERY):
        px0 = close.iloc[i]
        ok = px0.notna() & (liq.iloc[i] >= MIN_VALUE) & atr_pct.iloc[i].notna() & (atr_pct.iloc[i] > 0)
        tickers = ok[ok].index
        if len(tickers) == 0:
            continue
        fwd = close.iloc[i + 1: i + 1 + HOLD][tickers]   # 진입 다음날부터
        entry = px0[tickers]
        a = atr_pct.iloc[i][tickers]
        for t in tickers:
            path = fwd[t].dropna()
            if len(path) < 5:
                continue
            e = float(entry[t])
            rows.append((t, idx[i], e, float(a[t]), path.values))

    print(f"진입 표본 {len(rows):,}건 · 종목 {len({r[0] for r in rows})} · "
          f"{rows[0][1].date()} ~ {rows[-1][1].date()}")
    print(f"ATR(14) 일간 평균변동폭 중앙값 {np.median([r[3] for r in rows])*100:.2f}%")
    print()

    def simulate(stop_frac_fn):
        """stop_frac_fn(atr) -> 손절 폭(양수 소수). 반환 = (수익률 배열, 손절발동률, 평균손절폭)"""
        outs, fired, widths = [], 0, []
        for _, _, e, a, path in rows:
            w = stop_frac_fn(a)
            widths.append(w)
            lvl = e * (1 - w)
            hit = np.where(path <= lvl)[0]
            if len(hit):
                outs.append(path[hit[0]] / e - 1.0)
                fired += 1
            else:
                outs.append(path[-1] / e - 1.0)
        return np.array(outs), fired / len(rows), float(np.mean(widths))

    print(f"{'규칙':>12}{'평균손절폭':>11}{'발동률':>8}{'평균수익':>10}{'중앙수익':>10}{'하위5%':>10}{'표준편차':>10}")
    print("-" * 74)
    results = {}
    for f in FIXED:
        o, fr, w = simulate(lambda a, f=f: f)
        results[f"고정 -{f*100:.0f}%"] = (w, fr, o)
        print(f"{'고정 -'+str(int(f*100))+'%':>12}{w*100:>10.1f}%{fr*100:>7.1f}%"
              f"{o.mean()*100:>9.2f}%{np.median(o)*100:>9.2f}%{np.percentile(o,5)*100:>9.2f}%{o.std()*100:>9.2f}%")
    for k in ATR_K:
        o, fr, w = simulate(lambda a, k=k: k * a)
        results[f"ATR x{k}"] = (w, fr, o)
        print(f"{'ATR x'+str(k):>12}{w*100:>10.1f}%{fr*100:>7.1f}%"
              f"{o.mean()*100:>9.2f}%{np.median(o)*100:>9.2f}%{np.percentile(o,5)*100:>9.2f}%{o.std()*100:>9.2f}%")
    o, fr, w = simulate(lambda a: 9.99)
    print(f"{'무손절':>12}{'-':>11}{fr*100:>7.1f}%"
          f"{o.mean()*100:>9.2f}%{np.median(o)*100:>9.2f}%{np.percentile(o,5)*100:>9.2f}%{o.std()*100:>9.2f}%")
    results["무손절"] = (np.nan, fr, o)

    # ── 핵심 비교: 평균 손절폭을 맞춘 뒤 고정 vs ATR ──
    print()
    print("## 핵심 — 평균 손절폭을 맞춘 짝비교 (같은 폭이면 스케일링이 이기는가)")
    print(f"{'짝':>28}{'폭차':>8}{'평균수익차':>12}{'하위5%차':>12}")
    print("-" * 62)
    for k in ATR_K:
        wa = results[f"ATR x{k}"][0]
        best, bd = None, 1e9
        for f in FIXED:
            d = abs(results[f"고정 -{f*100:.0f}%"][0] - wa)
            if d < bd:
                bd, best = d, f
        oa = results[f"ATR x{k}"][2]
        of = results[f"고정 -{best*100:.0f}%"][2]
        print(f"{f'ATR x{k} vs 고정 -{int(best*100)}%':>28}{bd*100:>7.1f}%p"
              f"{(oa.mean()-of.mean())*100:>11.2f}%p{(np.percentile(oa,5)-np.percentile(of,5))*100:>11.2f}%p")

    # ── 고변동 구간 한정 (코스피 현 국면 유사) ──
    print()
    print("## 고변동 구간 한정 (진입 시 ATR 상위 33%) — 현재 코스피 국면 유사")
    a_all = np.array([r[3] for r in rows])
    hi = a_all >= np.percentile(a_all, 67)
    print(f"   표본 {hi.sum():,}건 · ATR 하한 {np.percentile(a_all,67)*100:.2f}%/일")
    print(f"{'규칙':>12}{'평균수익':>10}{'하위5%':>10}")
    print("-" * 34)
    for key in ["고정 -5%", "고정 -10%", "ATR x2.0", "ATR x2.5", "무손절"]:
        o = results[key][2][hi]
        print(f"{key:>12}{o.mean()*100:>9.2f}%{np.percentile(o,5)*100:>9.2f}%")


if __name__ == "__main__":
    main()
