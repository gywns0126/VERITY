#!/usr/bin/env python3
"""크립토 TSM 룩백 horizon 검정 — 학술 1~4주 vs TIDE 30/90일.

`docs/academic_grounding_library_2026_06_13.md` 영역 15 한계 목록:
    "크립토 TSM horizon: Liu-Tsyvinski 1~4주 vs TIDE 30/90일"
같은 지적이 191행에도 중복 기재돼 있으나 2026-06-13 이후 미해소. 이 스크립트가 그걸 친다.

배경:
  · Liu & Tsyvinski (2021, RFS 34(6):2689-2727) 가 크립토 TSM 을 확인한 구간 = **1~4주**
  · TIDE A5 라이브 = dual-lookback **30/90일** (약 4~13주) → 90일은 문헌 검증 범위 밖
  · 근거 없이 고른 값이면 과최적화 후보다

설계:
  · 유니버스 = KRW-BTC + KRW-ETH (TIDE 라이브 동일)
  · 신호 = dual-lookback TSM. signal = (r_short>0 + r_long>0)/2 ∈ {0, 0.5, 1.0}
  · vol-targeting = min(1, 0.40/실현변동성) — 라이브 config VOL_TARGET_ANNUAL=0.40
  · 비용 = 편도 0.05% (라이브 FEE_RATE. 백테스트가 쓰던 0.1% 아님 — 오늘 실측 정합)
  · IS 2020-01~2024-06 / OOS 2024-07~ (봉인)
  · 🚨 시행 횟수를 세어 **DSR** 로 보정한다. 격자 최고값을 그대로 믿지 않는다.
"""
from __future__ import annotations
import itertools
import numpy as np
import pandas as pd
from math import sqrt
from statistics import NormalDist

PARQUET = "/Users/macbookpro/Desktop/TIDE/data/cache_ohlcv.parquet"
TICKERS = ["KRW-BTC", "KRW-ETH"]
IS_END = "2024-06-30"
# 🚨 아래 3개는 TIDE origin/main:tide/config.py 와 정합해야 한다 (로컬 클론은 stale 상시).
#    2026-08-16 대조: FEE 편도 0.05% · VOL_TARGET_ANNUAL=0.40(7/27 PM 승인 0.20→0.40) · VOL_LOOKBACK=30
FEE = 0.0005
VOL_TARGET = 0.40
VOL_LOOKBACK = 30
ANN = 365

# 학술 구간(1~4주 = 7~28일)과 TIDE 구간(30~90일)을 모두 덮는 격자
SHORTS = [7, 10, 14, 21, 28, 30, 40, 60]
LONGS = [14, 21, 28, 30, 45, 60, 90, 120, 180]


def sharpe(r: np.ndarray) -> float:
    r = r[np.isfinite(r)]
    if len(r) < 60 or r.std() == 0:
        return float("nan")
    return float(r.mean() / r.std() * sqrt(ANN))


def mdd(r: np.ndarray) -> float:
    eq = np.cumprod(1 + r)
    return float((eq / np.maximum.accumulate(eq) - 1).min() * 100)


def main() -> None:
    df = pd.read_parquet(PARQUET)
    close = df.xs("close", axis=1, level=1)[TICKERS].astype(float).dropna()
    rets = close.pct_change(fill_method=None).fillna(0.0)
    realized = rets.rolling(VOL_LOOKBACK).std() * sqrt(ANN)
    is_mask = np.asarray(close.index <= IS_END)

    print(f"크립토 TSM horizon 검정 — {TICKERS} · {close.index[0].date()}~{close.index[-1].date()}")
    print(f"IS {is_mask.sum()}일 / OOS {(~is_mask).sum()}일 · vol-target {VOL_TARGET:.0%} · 편도 {FEE:.2%}")
    print(f"격자 = short {SHORTS} × long {LONGS}")
    print()

    rows = []
    for s, l in itertools.product(SHORTS, LONGS):
        if s >= l:
            continue
        sig = ((close.pct_change(s, fill_method=None) > 0).astype(float)
               + (close.pct_change(l, fill_method=None) > 0).astype(float)) / 2.0
        scale = (VOL_TARGET / realized).clip(upper=1.0).fillna(0.0)
        w = (sig * scale / len(TICKERS)).shift(1).fillna(0.0)
        gross = (w * rets).sum(axis=1)
        turn = (w - w.shift(1).fillna(0.0)).abs().sum(axis=1)
        pnl = (gross - turn * FEE).values
        s_is, s_oos = sharpe(pnl[is_mask]), sharpe(pnl[~is_mask])
        if np.isfinite(s_is) and np.isfinite(s_oos):
            rows.append((s, l, s_is, s_oos, mdd(pnl[~is_mask])))

    n = len(rows)
    is_all = np.array([r[2] for r in rows])
    rows_sorted = sorted(rows, key=lambda x: -x[2])

    print(f"## 시행 {n}개 변형")
    print(f"IS Sharpe: 최고 {is_all.max():.2f} · 중앙 {np.median(is_all):.2f} · 표준편차 {is_all.std():.2f}")
    print()

    print("## IS 상위 8")
    print(f"{'short/long':>12}{'IS':>8}{'OOS':>8}{'OOS MDD':>10}{'구간':>12}")
    print("-" * 52)
    for s, l, a, b, m in rows_sorted[:8]:
        band = "학술 1~4주" if l <= 28 else ("혼합" if s <= 28 else "TIDE 대역")
        print(f"{f'{s}/{l}':>12}{a:>8.2f}{b:>8.2f}{m:>9.1f}%{band:>12}")
    print()

    # ── 학술 구간 vs TIDE 구간 ──
    acad = [r for r in rows if r[1] <= 28]                 # long ≤ 4주
    tide = [r for r in rows if r[0] >= 28 and r[1] >= 60]  # TIDE 대역
    print("## 구간별 집계")
    print(f"{'구간':>16}{'변형':>6}{'IS 평균':>10}{'OOS 평균':>11}{'OOS 최고':>10}")
    print("-" * 54)
    for label, grp in [("학술 1~4주(long≤28)", acad), ("TIDE 대역(s≥28,l≥60)", tide), ("전체", rows)]:
        if not grp:
            continue
        print(f"{label:>16}{len(grp):>6}{np.mean([g[2] for g in grp]):>10.2f}"
              f"{np.mean([g[3] for g in grp]):>11.2f}{max(g[3] for g in grp):>10.2f}")
    print()

    cur = next((r for r in rows if r[0] == 30 and r[1] == 90), None)
    if cur:
        rank_is = sorted(rows, key=lambda x: -x[2]).index(cur) + 1
        rank_oos = sorted(rows, key=lambda x: -x[3]).index(cur) + 1
        print(f"## 라이브 30/90 의 위치")
        print(f"  IS Sharpe {cur[2]:.2f} → {n}개 중 {rank_is}위")
        print(f"  OOS Sharpe {cur[3]:.2f} → {n}개 중 {rank_oos}위 · OOS MDD {cur[4]:.1f}%")
        print()

    # ── DSR ──
    e = 0.5772156649
    Z = NormalDist().inv_cdf
    exp_max = is_all.std() * ((1 - e) * Z(1 - 1.0 / n) + e * Z(1 - 1.0 / (n * np.e)))
    T = int(is_mask.sum())
    best = rows_sorted[0]
    dsr = NormalDist().cdf((best[2] / sqrt(ANN) - exp_max / sqrt(ANN)) * sqrt(T - 1))
    print("## DSR — 시행 횟수 보정")
    print(f"  시행 {n}회면 운만으로 기대되는 최고 IS Sharpe = {exp_max:.2f}")
    print(f"  실제 최고 = {best[2]:.2f} ({best[0]}/{best[1]})")
    print(f"  DSR = {dsr:.3f} → {'유의' if dsr > 0.95 else '유의하지 않음 — 격자 최고값을 채택하면 안 된다'}")
    print()
    r_corr = np.corrcoef([r[2] for r in rows], [r[3] for r in rows])[0, 1]
    print(f"  IS↔OOS 상관 {r_corr:+.3f} (R²={r_corr**2:.3f})")


if __name__ == "__main__":
    main()
