"""
ic_stats.py — IC(정보계수) 통계 모듈. Shadow Funnel Scoring Spec v0 산식 구현.

2026-06-08 신설. 사전등록: docs/shadow_funnel_scoring_spec_v0.md (PM 승인 2026-06-08).
방법론 출처 = Perplexity 7-답 (Grinold-Kahn / Richardson-Smith 1991 / Newey-West 1987 /
Bailey-López de Prado 2014 / Goodwin 1998).

순수 함수 (라이브 파이프라인 무의존). prediction_scoring + shadow 집계가 import.

산식 (스펙 §4):
  1. rank-IC = Kendall τ (주) + Spearman ρ (병기)         — 소표본 N<30 τ 신뢰 높음
  2. bootstrap CI = 2000 resample, 95%, seed 고정
  3. 시계열 t-stat = Newey-West (maxlags = max(h-1, ceil(0.75 T^(1/3))))
  4. 횡단면 보정 = SE × √(1+(N-1)ρ̄)  →  corrected-t = NW-t / √(1+(N-1)ρ̄)

statsmodels 미사용 (의존성 회피) — Newey-West 직접 구현.
"""
from __future__ import annotations

import math
from typing import Optional, Sequence

import numpy as np
from scipy import stats


# ── 1. per-period rank-IC ───────────────────────────────────────────────


def rank_ic(scores: Sequence[float], fwd_returns: Sequence[float], method: str = "kendall"):
    """단일 기간 cross-sectional rank-IC.

    method = 'kendall' (주, 소표본 권장) | 'spearman' (병기).
    유효쌍 < 3 또는 분산 0 이면 (None, None).
    반환 (ic, pvalue).
    """
    s = np.asarray(scores, dtype=float)
    r = np.asarray(fwd_returns, dtype=float)
    mask = np.isfinite(s) & np.isfinite(r)
    s, r = s[mask], r[mask]
    if len(s) < 3 or np.ptp(s) == 0 or np.ptp(r) == 0:
        return None, None
    if method == "kendall":
        ic, p = stats.kendalltau(s, r)
    elif method == "spearman":
        ic, p = stats.spearmanr(s, r)
    else:
        raise ValueError(f"unknown method: {method}")
    if not np.isfinite(ic):
        return None, None
    return float(ic), float(p)


# ── 2. bootstrap IC CI (소표본, 스펙 §4.2) ──────────────────────────────


def bootstrap_ic_ci(
    scores: Sequence[float],
    fwd_returns: Sequence[float],
    method: str = "kendall",   # 스펙 §4.1 primary = Kendall τ 정합 (rank_ic 기본과 통일)
    n_boot: int = 2000,
    ci: float = 0.95,
    seed: int = 20260608,
):
    """단일 기간 IC 의 bootstrap 신뢰구간. seed 고정 = 재현성.

    반환 (mean_ic, lo, hi). 유효쌍 < 3 이면 (None, None, None).
    """
    s = np.asarray(scores, dtype=float)
    r = np.asarray(fwd_returns, dtype=float)
    mask = np.isfinite(s) & np.isfinite(r)
    s, r = s[mask], r[mask]
    n = len(s)
    if n < 3:
        return None, None, None
    rng = np.random.default_rng(seed)
    boot = np.empty(n_boot)
    valid = 0
    for i in range(n_boot):
        idx = rng.integers(0, n, n)
        ss, rr = s[idx], r[idx]
        if np.ptp(ss) == 0 or np.ptp(rr) == 0:
            continue
        if method == "kendall":
            ic, _ = stats.kendalltau(ss, rr)
        else:
            ic, _ = stats.spearmanr(ss, rr)
        if np.isfinite(ic):
            boot[valid] = ic
            valid += 1
    if valid < 10:
        return None, None, None
    boot = boot[:valid]
    lo = float(np.percentile(boot, (1 - ci) / 2 * 100))
    hi = float(np.percentile(boot, (1 + ci) / 2 * 100))
    return float(boot.mean()), lo, hi


# ── 3. Newey-West (중첩 horizon 자기상관, 스펙 §4.3) ────────────────────


def _auto_maxlags(T: int, horizon_days: int) -> int:
    """maxlags = max(h-1, ceil(0.75 * T^(1/3)))."""
    auto = int(math.ceil(0.75 * (T ** (1.0 / 3.0)))) if T > 0 else 0
    return max(horizon_days - 1, auto, 0)


def newey_west_tstat(ic_series: Sequence[float], horizon_days: int) -> dict:
    """IC 시계열 평균의 Newey-West 보정 t-stat (mean=0 검정).

    NW var(mean) = (1/T)[γ0 + 2 Σ_{l=1}^{L}(1 - l/(L+1)) γl],  γl = lag-l 자기공분산.
    반환 {mean_ic, nw_se, nw_tstat, maxlags, T}. T<2 이면 t=None.
    """
    x = np.asarray([v for v in ic_series if v is not None and np.isfinite(v)], dtype=float)
    T = len(x)
    if T < 2:
        return {"mean_ic": float(x.mean()) if T else None, "nw_se": None,
                "nw_tstat": None, "maxlags": 0, "T": T}
    mean = float(x.mean())
    d = x - mean
    gamma0 = float(np.dot(d, d) / T)
    # degenerate 가드: (near-)constant 시리즈 = float dust 분산 → 허위 거대 t-stat 차단 (nit #7).
    if gamma0 <= 1e-18 or math.sqrt(gamma0) < 1e-9 * (abs(mean) + 1.0):
        return {"mean_ic": mean, "nw_se": 0.0, "nw_tstat": None, "maxlags": 0, "T": T}
    L = min(_auto_maxlags(T, horizon_days), T - 1)
    s = gamma0
    for l in range(1, L + 1):
        w = 1.0 - l / (L + 1.0)  # Bartlett kernel
        gl = float(np.dot(d[l:], d[:-l]) / T)
        s += 2.0 * w * gl
    long_run_var = max(s, 0.0)
    nw_se = math.sqrt(long_run_var / T) if long_run_var > 0 else 0.0
    nw_t = mean / nw_se if nw_se > 0 else None
    return {"mean_ic": mean, "nw_se": nw_se, "nw_tstat": nw_t, "maxlags": L, "T": T}


def quick_tstat_adj(ic_series: Sequence[float], horizon_days: int) -> Optional[float]:
    """빠른 sanity: 일반 t / √h (중첩 근사 보정, 스펙 §4)."""
    x = np.asarray([v for v in ic_series if v is not None and np.isfinite(v)], dtype=float)
    T = len(x)
    if T < 2:
        return None
    sd = x.std(ddof=1)
    if sd == 0:
        return None
    raw_t = x.mean() / (sd / math.sqrt(T))
    return float(raw_t / math.sqrt(max(horizon_days, 1)))


# ── 4. 횡단면 상관 보정 / effective N (스펙 §4.4) ────────────────────────


def effective_n_from_corr(corr_matrix: np.ndarray) -> Optional[float]:
    """N_eff = N / (1 + (N-1) ρ̄), ρ̄ = 평균 pairwise 상관 (off-diagonal)."""
    C = np.asarray(corr_matrix, dtype=float)
    N = C.shape[0]
    if N < 2:
        return float(N)
    iu = np.triu_indices(N, k=1)
    off = C[iu]
    off = off[np.isfinite(off)]
    if len(off) == 0:
        return float(N)
    rho_bar = float(off.mean())
    denom = 1.0 + (N - 1) * rho_bar
    if denom <= 0:
        return float(N)  # 음상관 과보정 방지 (보수적으로 N 유지)
    return N / denom


def cross_correction_multiplier(corr_matrix: np.ndarray) -> float:
    """corrected-t = NW-t / √(1+(N-1)ρ̄). 승수 √(1+(N-1)ρ̄) 반환 (≥1로 클램프)."""
    C = np.asarray(corr_matrix, dtype=float)
    N = C.shape[0]
    if N < 2:
        return 1.0
    iu = np.triu_indices(N, k=1)
    off = C[iu]
    off = off[np.isfinite(off)]
    if len(off) == 0:
        return 1.0
    rho_bar = float(off.mean())
    val = 1.0 + (N - 1) * rho_bar
    return math.sqrt(val) if val > 1.0 else 1.0


# ── 5. 풀 스택 결합 (스펙 §4 최종 판정 t-stat) ──────────────────────────


def corrected_ic_summary(
    ic_series: Sequence[float],
    horizon_days: int,
    return_matrix: Optional[np.ndarray] = None,
) -> dict:
    """IC 시계열 + (옵션)기간×종목 수익률 행렬 → 보정 요약.

    return_matrix (T, N) 주면 평균 횡단 상관으로 cross-correction 적용.
    반환: mean_ic / nw_tstat / cross_mult / n_eff / final_tstat / quick_tstat / maxlags / T.
    """
    nw = newey_west_tstat(ic_series, horizon_days)
    out = {
        "mean_ic": nw["mean_ic"],
        "nw_tstat": nw["nw_tstat"],
        "maxlags": nw["maxlags"],
        "T": nw["T"],
        "quick_tstat": quick_tstat_adj(ic_series, horizon_days),
        "cross_mult": 1.0,
        "n_eff": None,
        "final_tstat": nw["nw_tstat"],
    }
    if return_matrix is not None and nw["nw_tstat"] is not None:
        R = np.asarray(return_matrix, dtype=float)
        if R.ndim == 2 and R.shape[1] >= 2 and R.shape[0] >= 2:
            corr = np.corrcoef(R.T)
            mult = cross_correction_multiplier(corr)
            out["cross_mult"] = mult
            out["n_eff"] = effective_n_from_corr(corr)
            out["final_tstat"] = nw["nw_tstat"] / mult if mult > 0 else nw["nw_tstat"]
    return out


# ── 6. 두 전략 IC 비교 (스펙 §5, paired) ────────────────────────────────


def paired_ic_test(ic_a: Sequence[float], ic_b: Sequence[float]) -> dict:
    """기간별 paired Wilcoxon signed-rank (A=shadow vs B=production).

    같은 기간/유니버스 → paired 필수. 반환 {n_pairs, median_diff, wilcoxon_stat, pvalue, a_better}.
    """
    a = np.asarray(ic_a, dtype=float)
    b = np.asarray(ic_b, dtype=float)
    m = min(len(a), len(b))
    a, b = a[:m], b[:m]
    mask = np.isfinite(a) & np.isfinite(b)
    a, b = a[mask], b[mask]
    diff = a - b
    nz = diff[diff != 0]
    if len(nz) < 6:  # Wilcoxon 최소 표본 (zero-diff 제외 후)
        return {"n_pairs": int(len(diff)), "effective_n": int(len(nz)),
                "median_diff": float(np.median(diff)) if len(diff) else None,
                "wilcoxon_stat": None, "pvalue": None, "a_better": None,
                "note": "표본 부족 (nonzero diff<6) — 검정 불가"}
    # zero-diff 가드와 정합되게 nonzero diff 만 검정 (P2 #9: full-array 호출 시 scipy 내부 drop ↔ 보고 n 불일치).
    # alternative='greater' = H1 median(diff)>0 (A=shadow 우위) 단측.
    stat, p = stats.wilcoxon(nz, alternative="greater")
    med = float(np.median(diff))
    return {"n_pairs": int(len(diff)), "effective_n": int(len(nz)), "median_diff": med,
            "wilcoxon_stat": float(stat), "pvalue": float(p),
            "a_better": bool(p < 0.05)}
