#!/usr/bin/env python3
"""크립토 유니버스 확장 검정 — BTC/ETH 2개에서 274개로 늘리면 나아지는가.

## 배경

2026-08-16 horizon 검정 결론: 룩백 파라미터 선택에는 OOS 예측력이 없다(PBO 41.3%, R²=0.018).
그래서 "파라미터 말고 정보가 있는 축을 건드리라"는 결론이 나왔고, 그 1순위가 **유니버스**다.
TIDE 라이브는 KRW-BTC/ETH 2개뿐이라 횡단면 표본이 극단적으로 얇다.

## 🚨 생존편향 — 이 검정의 해석을 지배한다

같은 세션에서 측정: parquet 274 티커 중 **중도진입(신규상장) 218건 vs 중도이탈(상폐) 2건**.
업비트가 6.5년간 거래지원종료를 2건만 했을 리 없다. 이 비대칭은 "현재 상장 목록을 받아
과거를 백필" 방식의 지문이고, 결과적으로 **상장폐지된 코인이 표본에서 통째로 빠져 있다.**

편향 크기는 **이 데이터로 잴 수 없다** — 빠진 종목이 아예 없으므로. 학술 추정치만 있다
(Grobys et al. 2025, FMPM 39:443-476 — survivor 표본에서 t=0.75 로 zero 와 구분 불가).

따라서 이 검정은 **단측 결론만** 낼 수 있다:
  · 확장이 좋게 나오면 → 편향 탓일 수 있으므로 **채택 불가**
  · 확장이 나쁘게 나오면 → 편향이 밀어올리는데도 나쁘므로 **확정 기각**
후자만 결론으로 쓴다.

## 설계

  · 유동성 필터 = point-in-time (직전 30일 거래대금 중앙값). 전기간 평균 금지(룩어헤드).
  · 시계열(TSM): 유니버스 각 코인에 dual-lookback TSM, 동일가중
  · 횡단면(XS): 룩백 수익 상위 분위 롱 — Liu-Tsyvinski-Wu(2022)가 소형·비유동 집중을 경고한 축
  · 비용 = 편도 0.05%(라이브) 및 0.20%(알트 현실치) 양쪽
  · 게이트 = scripts/pbo_selection_gate.py 병기 (DSR 단독 금지)
"""
from __future__ import annotations

import sys
from math import sqrt
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pbo_selection_gate import selection_gate  # noqa: E402

PARQUET = "/Users/macbookpro/Desktop/TIDE/data/cache_ohlcv.parquet"
ANN = 365
VOL_TARGET, VOL_LB = 0.40, 30          # TIDE origin/main 정합
LIQ_LB = 30                            # 유동성 판정 룩백(일)
MIN_HIST = 120                         # 신규상장 직후 배제
SHORT, LONG = 30, 90                   # 라이브 룩백 고정 — 여기서는 유니버스만 바꾼다


def load():
    df = pd.read_parquet(PARQUET)
    close = df.xs("close", axis=1, level=1).astype(float)
    value = df.xs("value", axis=1, level=1).astype(float)   # 거래대금(원)
    return close, value


def stats(r: np.ndarray) -> tuple[float, float, float]:
    r = np.asarray(r)
    r = r[np.isfinite(r)]
    if len(r) < 60 or r.std() == 0:
        return float("nan"), float("nan"), float("nan")
    eq = np.cumprod(1 + r)
    return (float(r.mean() / r.std() * sqrt(ANN)),
            float((eq[-1] ** (ANN / len(r)) - 1) * 100),
            float((eq / np.maximum.accumulate(eq) - 1).min() * 100))


def tsm_weights(close: pd.DataFrame, elig: pd.DataFrame) -> pd.DataFrame:
    """dual-lookback TSM × vol-target, 자격 종목에 동일가중."""
    rets = close.pct_change(fill_method=None)
    sig = ((close.pct_change(SHORT, fill_method=None) > 0).astype(float)
           + (close.pct_change(LONG, fill_method=None) > 0).astype(float)) / 2.0
    scale = (VOL_TARGET / (rets.rolling(VOL_LB).std() * sqrt(ANN))).clip(upper=1.0)
    raw = (sig * scale).where(elig, 0.0).fillna(0.0)
    n = elig.sum(axis=1).replace(0, np.nan)
    return raw.div(n, axis=0).fillna(0.0)


def xs_weights(close: pd.DataFrame, elig: pd.DataFrame, top_frac: float = 0.2) -> pd.DataFrame:
    """횡단면 모멘텀 — 룩백 수익 상위 top_frac 롱, 동일가중."""
    mom = close.pct_change(LONG, fill_method=None).where(elig)
    rank = mom.rank(axis=1, pct=True, ascending=False)
    pick = (rank <= top_frac) & elig
    n = pick.sum(axis=1).replace(0, np.nan)
    return pick.astype(float).div(n, axis=0).fillna(0.0)


def run(w: pd.DataFrame, rets: pd.DataFrame, fee: float) -> np.ndarray:
    ww = w.shift(1).fillna(0.0)
    gross = (ww * rets.fillna(0.0)).sum(axis=1)
    turn = (ww - ww.shift(1).fillna(0.0)).abs().sum(axis=1)
    return (gross - turn * fee).values


def main() -> None:
    close, value = load()
    rets = close.pct_change(fill_method=None)
    idx = close.index

    # point-in-time 유동성 (룩어헤드 없음: shift(1) 로 당일 정보 배제)
    liq = value.rolling(LIQ_LB).median().shift(1)
    hist_ok = close.notna().cumsum() >= MIN_HIST

    print("크립토 유니버스 확장 검정")
    print(f"  {idx[0].date()}~{idx[-1].date()} · {len(idx)}일 · 티커 {close.shape[1]}")
    print(f"  룩백 {SHORT}/{LONG} 고정(라이브) · vol-target {VOL_TARGET:.0%} · 유동성 PIT {LIQ_LB}일 중앙값")
    print()
    print("  🚨 생존편향: 신규상장 218 vs 상폐 2 — 상폐 코인이 표본에 없다.")
    print("     결과가 좋게 나오면 편향 탓일 수 있어 채택 불가. 나쁘게 나올 때만 확정 기각.")
    print()

    live_mask = pd.DataFrame(
        np.tile([c in ("KRW-BTC", "KRW-ETH") for c in close.columns], (len(idx), 1)),
        index=idx, columns=close.columns,
    ) & close.notna()

    tiers = {
        "BTC/ETH (라이브)": lambda: live_mask,
        "거래대금 ≥100억": lambda: (liq >= 1e10) & hist_ok & close.notna(),
        "거래대금 ≥30억": lambda: (liq >= 3e9) & hist_ok & close.notna(),
        "거래대금 ≥10억": lambda: (liq >= 1e9) & hist_ok & close.notna(),
        "전체(필터 없음)": lambda: hist_ok & close.notna(),
    }

    for fee, felab in [(0.0005, "편도 0.05% (라이브 BTC/ETH)"), (0.002, "편도 0.20% (알트 현실치)")]:
        print(f"## 비용 {felab}")
        print(f"{'유니버스':>20}{'평균종목':>9}{'TSM Sharpe':>12}{'연수익':>9}{'MDD':>9}{'XS Sharpe':>11}")
        print("-" * 71)
        for name, fn in tiers.items():
            elig = fn().reindex(index=idx, columns=close.columns).fillna(False)
            navg = elig.sum(axis=1).mean()
            if navg < 1:
                continue
            s_ts = stats(run(tsm_weights(close, elig), rets, fee))
            if navg >= 5:
                s_xs = stats(run(xs_weights(close, elig), rets, fee))[0]
                xs_txt = f"{s_xs:>11.2f}"
            else:
                xs_txt = f"{'—':>11}"
            print(f"{name:>20}{navg:>9.0f}{s_ts[0]:>12.2f}{s_ts[1]:>8.1f}%{s_ts[2]:>8.1f}%{xs_txt}")
        print()

    # ── 게이트: 유동성 임계를 '파라미터'로 보고 선택 정당성 검정 ──
    print("## 유동성 임계 선택도 과최적화인가 — PBO 게이트")
    cols, labels = [], []
    for thr in [3e8, 5e8, 1e9, 2e9, 3e9, 5e9, 1e10, 2e10, 5e10]:
        elig = ((liq >= thr) & hist_ok & close.notna()).fillna(False)
        if elig.sum(axis=1).mean() < 2:
            continue
        cols.append(run(tsm_weights(close, elig), rets, 0.002))
        labels.append(f"≥{thr/1e8:.0f}억")
    if len(cols) >= 3:
        M = np.array(cols).T
        bench = rets[["KRW-BTC", "KRW-ETH"]].mean(axis=1).fillna(0.0).values
        rep = selection_gate(M, labels, benchmark=bench)
        print(rep.render())


if __name__ == "__main__":
    main()
