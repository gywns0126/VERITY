"""
validate_comom_decay.py — CoMOM forward 모멘텀 decay 검증 (CoMOM 파이프라인 §6).

2026-06-14 신설. Lou-Polk(2022) 핵심검정: 높은 CoMOM(t)(=모멘텀에 차익거래 자본 집중)
→ 이후 1~2년 모멘텀 스프레드(winner−loser) 수익 *하락*. build_comom.py 가 저장한
comom_monthly(comom + fwd_wml_4q/8q)에 대해 회귀/레짐/순위상관으로 측정.

🚨 관측/측정 only (RULE 7) — 점수/brain 결정 wire 0. 라이선스: 로컬 전용 실행.

통계 (메모리 검증설계 + ic_stats.py 규율 정합):
  - **NW HAC OLS**: fwd = a + b·CoMOM + e, Newey-West(Bartlett) HAC SE on b.
    중첩 forward 윈도(4/8분기) → 잔차 자기상관 → OLS SE 과소추정 회피.
  - **비선형 레짐**: CoMOM 5분위별 forward 평균(선형IC 단독 금지, 메모리). 단조감소 기대.
  - **Spearman**: 순위상관(부호 robustness).
  - N=분기(109) — 검정력 한계 명시(예비결과, N<252 IC 게이트 전).
"""
from __future__ import annotations

import argparse
import math
import os
import sys
from typing import Dict, Optional

import numpy as np
import pandas as pd

PARQUET_DEFAULT = os.path.expanduser("~/VERITY_data_lake/comom_factor_monthly.parquet")

# 팩터별 forward 부호 기대 (Perplexity 자문) — 측정값과 대조용, 가정 아님
FACTOR_HYPOTHESIS = {
    "momentum": "positive-feedback → 높은 CoMOM=이후 모멘텀수익 하락 기대(slope<0)",
    "value": "negative-feedback(차익거래=가격 적정화) → 부호 agnostic(오히려 +가능)",
    "quality": "부호 agnostic(자문상 미확정) — 측정으로 판정",
}


def _auto_maxlags(T: int, horizon_q: int) -> int:
    """ic_stats 규율 정합: max(horizon-1, ceil(0.75 T^(1/3)))."""
    auto = int(math.ceil(0.75 * (T ** (1.0 / 3.0)))) if T > 0 else 0
    return max(horizon_q - 1, auto, 0)


def nw_ols(x: np.ndarray, y: np.ndarray, horizon_q: int) -> Dict[str, Optional[float]]:
    """y = a + b·x + e 단순회귀, Newey-West(Bartlett) HAC SE on slope b.

    cov(β) = (X'X)^{-1} S (X'X)^{-1},  S = Σ u_t u_t' + Σ_l w_l (G_l + G_l'),
    u_t = x_t·e_t (score), w_l = 1 − l/(L+1) Bartlett.
    """
    mask = np.isfinite(x) & np.isfinite(y)
    x, y = x[mask], y[mask]
    T = len(x)
    if T < 8:
        return {"n": T, "slope": None, "nw_se": None, "nw_t": None, "r2": None, "maxlags": 0}
    X = np.column_stack([np.ones(T), x])
    XtX = X.T @ X
    XtX_inv = np.linalg.inv(XtX)
    beta = XtX_inv @ (X.T @ y)
    resid = y - X @ beta
    u = X * resid[:, None]                 # T×2 score
    S = u.T @ u
    L = _auto_maxlags(T, horizon_q)
    for l in range(1, L + 1):
        w = 1.0 - l / (L + 1.0)
        G = u[l:].T @ u[:-l]
        S += w * (G + G.T)
    cov = XtX_inv @ S @ XtX_inv
    se_b = math.sqrt(cov[1, 1]) if cov[1, 1] > 0 else None
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = 1.0 - float(np.sum(resid ** 2)) / ss_tot if ss_tot > 0 else None
    return {
        "n": T, "slope": float(beta[1]), "nw_se": se_b,
        "nw_t": (float(beta[1]) / se_b) if se_b else None,
        "r2": r2, "maxlags": L,
    }


def quintile_regime(df: pd.DataFrame, fwd_col: str) -> pd.DataFrame:
    """CoMOM 5분위별 forward 평균 (단조감소 = Lou-Polk 정합)."""
    d = df[["comom", fwd_col]].dropna().copy()
    if len(d) < 15:
        return pd.DataFrame()
    d["q"] = pd.qcut(d["comom"], 5, labels=["Q1(low)", "Q2", "Q3", "Q4", "Q5(high)"], duplicates="drop")
    g = d.groupby("q", observed=True)[fwd_col].agg(["mean", "median", "count"])
    return g


def spearman(x: pd.Series, y: pd.Series) -> Optional[float]:
    d = pd.concat([x, y], axis=1).dropna()
    if len(d) < 8:
        return None
    return round(float(d.corr(method="spearman").iloc[0, 1]), 4)


def validate(parquet: str = PARQUET_DEFAULT) -> Dict[str, object]:
    df = pd.read_parquet(parquet)
    if "factor" not in df.columns:        # 구 momentum-only 포맷 호환
        df["factor"] = "momentum"
    fwd_cols = sorted(c for c in df.columns if c.startswith("fwd_spread_") or c.startswith("fwd_wml_"))
    out: Dict[str, object] = {"factors": {}}
    for factor, g in df.groupby("factor"):
        g = g.sort_values("month_end").reset_index(drop=True)
        fres = {"n_quarters": len(g), "horizons": {}}
        for fc in fwd_cols:
            if fc not in g.columns:
                continue
            hq = int(fc.split("_")[-1].replace("q", ""))
            fres["horizons"][fc] = {
                "horizon_quarters": hq,
                "nw_ols": nw_ols(g["comom"].to_numpy(float), g[fc].to_numpy(float), horizon_q=hq),
                "spearman": spearman(g["comom"], g[fc]),
                "quintile": quintile_regime(g, fc),
            }
        out["factors"][factor] = fres
    return out


def _print(res: Dict[str, object]) -> None:
    print("[validate_comom_decay] CoMOM forward decay (관측 only, RULE 7) — 예비결과: N<252 IC 게이트 전, 검정력 한계.\n")
    for factor, fres in res["factors"].items():
        hyp = FACTOR_HYPOTHESIS.get(factor, "")
        print(f"########## {factor}  (N={fres['n_quarters']}분기) ##########")
        print(f"  가설: {hyp}")
        for fc, r in fres["horizons"].items():
            reg = r["nw_ols"]
            yr = r["horizon_quarters"] / 4
            st = "—" if reg["slope"] is None else f"{reg['slope']:+.4f}"
            se = "—" if reg["nw_se"] is None else f"{reg['nw_se']:.4f}"
            tt = "—" if reg["nw_t"] is None else f"{reg['nw_t']:+.2f}"
            r2 = "—" if reg["r2"] is None else f"{reg['r2']:.3f}"
            print(f"  --- forward {r['horizon_quarters']}분기(~{yr:.0f}년) ---")
            print(f"    NW-OLS slope b={st}  NW-SE={se}  NW-t={tt}  R²={r2}  (n={reg['n']}, maxlags={reg['maxlags']})")
            print(f"    Spearman(CoMOM, fwd) = {r['spearman']}")
            q = r["quintile"]
            if isinstance(q, pd.DataFrame) and not q.empty:
                cells = "  ".join(f"{idx.split('(')[0]}={row['mean']:+.3f}" for idx, row in q.iterrows())
                print(f"    5분위 forward 평균: {cells}")
        print()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--parquet", default=PARQUET_DEFAULT)
    args = ap.parse_args()
    try:
        _print(validate(args.parquet))
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"[validate_comom_decay] 실패: {type(e).__name__}: {e}\n")
        raise
