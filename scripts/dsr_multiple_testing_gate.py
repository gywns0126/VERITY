#!/usr/bin/env python3
"""다전략 동시 백테스트의 값어치 — 우리 데이터로 과최적화를 계량한다.

질문(PM 2026-08-16): "여러 트레이딩 방식을 동시에 백테스트 돌리면? 의미없으려나"

핵심 위험 = **다중검정**. 전략을 많이 돌릴수록 표본내 최고 Sharpe 는 실력이 아니라
운으로도 올라간다. Bailey-López de Prado 의 DSR/PBO 가 정확히 이걸 잰다.
여기서는 그 현상을 **우리 데이터에서 직접 관측**한다.

설계:
  · 유니버스 = KRW-BTC + KRW-ETH (TIDE 라이브와 동일)
  · IS = 2020-01 ~ 2024-06 · OOS = 2024-07 ~ 2026-07 (봉인)
  · 전략군 4종 × 파라미터 격자 = 수백 개 변형
      TSM(추세) / MA크로스 / 돌파 / 평균회귀
  · 측정: "IS 상위 K개를 뽑았을 때 그들의 OOS 성적" 을 K 를 늘려가며 본다
  · 그리고 시행 횟수를 반영한 **Deflated Sharpe Ratio** 를 계산한다
"""
from __future__ import annotations
import itertools
import numpy as np
import pandas as pd
from math import sqrt, log
from statistics import NormalDist

PARQUET = "/Users/macbookpro/Desktop/TIDE/data/cache_ohlcv.parquet"
TICKERS = ["KRW-BTC", "KRW-ETH"]
IS_END = "2024-06-30"
FEE = 0.001          # 왕복 근사 (TIDE 백테스트 가정과 동일)
ANN = 365


def sharpe(r: np.ndarray) -> float:
    r = r[np.isfinite(r)]
    if len(r) < 30 or r.std() == 0:
        return float("nan")
    return float(r.mean() / r.std() * sqrt(ANN))


def run(weights: pd.DataFrame, rets: pd.DataFrame) -> np.ndarray:
    """일별 포트폴리오 수익 = 전일 비중 × 당일 수익 − 회전 비용."""
    w = weights.shift(1).fillna(0.0)
    gross = (w * rets).sum(axis=1)
    turn = (w - w.shift(1).fillna(0.0)).abs().sum(axis=1)
    return (gross - turn * FEE).values


def strategies(close: pd.DataFrame):
    """4개 전략군 × 파라미터 격자 → (이름, 비중 DataFrame) 생성기."""
    rets = close.pct_change(fill_method=None)
    for s, l in itertools.product([10, 20, 30, 40, 60], [60, 90, 120, 180]):
        if s >= l:
            continue
        sig = ((close.pct_change(s, fill_method=None) > 0).astype(float)
               + (close.pct_change(l, fill_method=None) > 0).astype(float)) / 2.0
        yield f"TSM {s}/{l}", sig / len(TICKERS)
    for f, sl in itertools.product([5, 10, 20, 30], [50, 100, 150, 200]):
        if f >= sl:
            continue
        sig = (close.rolling(f).mean() > close.rolling(sl).mean()).astype(float)
        yield f"MA {f}/{sl}", sig / len(TICKERS)
    for n, k in itertools.product([20, 40, 60, 90], [0.0, 0.02, 0.05]):
        hi = close.rolling(n).max()
        sig = (close >= hi * (1 - k)).astype(float)
        yield f"돌파 {n}d/{k:.2f}", sig / len(TICKERS)
    for n, z in itertools.product([10, 20, 30], [1.0, 1.5, 2.0]):
        m = close.rolling(n).mean()
        sd = close.rolling(n).std()
        sig = (close < m - z * sd).astype(float)
        yield f"평균회귀 {n}d/{z}σ", sig / len(TICKERS)


def main() -> None:
    df = pd.read_parquet(PARQUET)
    close = df.xs("close", axis=1, level=1)[TICKERS].astype(float).dropna()
    rets = close.pct_change(fill_method=None).fillna(0.0)
    is_mask = np.asarray(close.index <= IS_END)
    print(f"유니버스 {TICKERS} · 전체 {len(close)}일")
    print(f"IS {close.index[0].date()}~{IS_END} ({is_mask.sum()}일) · "
          f"OOS {(~is_mask).sum()}일 (봉인)")
    print()

    rows = []
    for name, w in strategies(close):
        pnl = run(w, rets)
        s_is, s_oos = sharpe(pnl[is_mask]), sharpe(pnl[~is_mask])
        if np.isfinite(s_is) and np.isfinite(s_oos):
            rows.append((name, s_is, s_oos))
    rows.sort(key=lambda x: -x[1])
    n = len(rows)
    is_all = np.array([r[1] for r in rows])
    print(f"시험한 전략 변형 = {n}개")
    print(f"IS Sharpe 분포: 최고 {is_all.max():.2f} · 중앙 {np.median(is_all):.2f} · "
          f"표준편차 {is_all.std():.2f}")
    print()

    print("## IS 상위 K개를 뽑았을 때 실제 OOS 성적")
    print(f"{'K':>5}{'IS 평균':>10}{'OOS 평균':>11}{'열화':>10}{'OOS 음수 비율':>14}")
    print("-" * 52)
    for K in [1, 3, 5, 10, 20, 50, n]:
        if K > n:
            continue
        top = rows[:K]
        i = np.mean([t[1] for t in top]); o = np.mean([t[2] for t in top])
        neg = sum(1 for t in top if t[2] < 0) / K * 100
        print(f"{K:>5}{i:>10.2f}{o:>11.2f}{(o-i):>10.2f}{neg:>13.0f}%")
    print()

    best = rows[0]
    print(f"IS 1등: {best[0]}  IS {best[1]:.2f} → OOS {best[2]:.2f}")
    r_is = np.corrcoef([r[1] for r in rows], [r[2] for r in rows])[0, 1]
    print(f"IS Sharpe ↔ OOS Sharpe 상관: {r_is:+.3f}   (R² = {r_is**2:.3f})")
    print()

    # ── Deflated Sharpe Ratio (Bailey-López de Prado 2014) ──
    #   시행 횟수 N 을 반영해 "기대되는 최고 Sharpe" 를 구하고, 관측치가 그보다 유의한지 본다.
    e = 0.5772156649
    Z = NormalDist().inv_cdf
    exp_max = is_all.std() * ((1 - e) * Z(1 - 1.0 / n) + e * Z(1 - 1.0 / (n * np.e)))
    T = int(is_mask.sum())
    sr = best[1] / sqrt(ANN)                    # 일 단위로 환산
    sr0 = exp_max / sqrt(ANN)
    dsr = NormalDist().cdf((sr - sr0) * sqrt(T - 1) / 1.0)
    print("## Deflated Sharpe Ratio — 시행 횟수를 반영한 유의성")
    print(f"  시행 N={n} 이면 **운만으로 기대되는 최고 IS Sharpe** = {exp_max:.2f}")
    print(f"  실제 최고 IS Sharpe = {best[1]:.2f}")
    print(f"  DSR = {dsr:.3f}   ({'유의' if dsr > 0.95 else '유의하지 않음 — 운으로 설명 가능'})")


if __name__ == "__main__":
    main()
