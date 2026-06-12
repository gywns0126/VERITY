"""pbo — Probability of Backtest Overfitting (CSCV full implementation).

학술 source:
  - Bailey, Borwein, López de Prado, Zhu (2014) "The Probability of Backtest
    Overfitting" *Journal of Computational Finance* (SSRN 2326253)
  - López de Prado (2018) "Advances in Financial Machine Learning" Ch 11-12

PM 사전등록: [[project_mlfinlab_pbo_precision_2026_05_27]] (2026-05-27).
B4 sprint 진입 (2026-06-12) 구현. 기존 `api/predictors/tscv.py`
`probability_of_backtest_overfitting` = quick proxy (binary, 단일 비교) —
본 모듈 = full CSCV. proxy 는 호환 보존 (병존).

산출 절차 (CSCV — Combinatorially Symmetric Cross-Validation):
  1. 성과 행렬 M (T×N): T 관측 (일별 수익률) × N 전략 trial
  2. 행을 S 개 (짝수) 연속 부분행렬로 분할
  3. C(S, S/2) 개 조합 — 각 조합 c 의 선택 블록 = IS (J), 보집합 = OOS (J̄)
  4. 각 c: IS 성과 (Sharpe) 최대 전략 n* 선정
  5. n* 의 OOS 상대 rank ω̄_c = (rank_asc(n*) + 1) / (N + 1) ∈ (0, 1)
  6. logit λ_c = ln(ω̄_c / (1 − ω̄_c))
  7. **PBO = #{c : λ_c ≤ 0} / #C** — IS 최적 전략이 OOS 에서 중앙값 이하로
     떨어지는 조합 비율 (λ≤0 ⟺ ω̄≤0.5 ⟺ OOS rank 하위 절반)

해석 밴드 (tscv.py quick proxy 와 동일 유지):
  PBO ≤ 0.2 = robust / 0.2~0.5 = 주의 / ≥ 0.5 = overfit

RULE 7 정합: infrastructure (검증 도구, 산식 자체 X). cycle reject 게이트
wire 시 PBO cutoff 임계 = PM 사전등록 별도 의무.
"""
from __future__ import annotations

import math
from itertools import combinations
from typing import Dict, List, Optional, Sequence

import numpy as np

__all__ = ["cscv_pbo", "PBO_PASS", "PBO_OVERFIT"]

PBO_PASS = 0.2      # tscv.py quick proxy 밴드 정합
PBO_OVERFIT = 0.5


def _block_bounds(T: int, S: int) -> List[tuple]:
    """T 행을 S 개 연속 블록 (start, end) 로 분할. 마지막 블록이 나머지 흡수."""
    size = T // S
    bounds = []
    for k in range(S):
        start = k * size
        end = start + size if k < S - 1 else T
        bounds.append((start, end))
    return bounds


def _rank_ascending(values: np.ndarray) -> np.ndarray:
    """0-based ordinal rank (ascending). 연속값 Sharpe 전제 — tie 는 입력 순서."""
    return np.argsort(np.argsort(values))


def cscv_pbo(
    returns_matrix: np.ndarray,
    n_partitions: int = 16,
    max_combinations: Optional[int] = None,
) -> Dict:
    """CSCV 기반 full PBO (Bailey-Borwein-López de Prado-Zhu 2014).

    Args:
        returns_matrix: (T, N) — T 관측 (일별 수익률) × N 전략 trial.
            N ≥ 2 의무 (rank 비교 대상 필요). 시도한 모든 config 포함 의무
            (생존 trial 만 넣으면 PBO 과소 — selection bias).
        n_partitions: S (짝수, default 16 → C(16,8) = 12,870 조합).
        max_combinations: 조합 수 상한. 초과 시 균등 stride 부표본
            (결정론 — RNG 미사용). None = 전체.

    Returns:
        {
          "pbo": float,                 # P(λ ≤ 0)
          "n_combinations": int,
          "n_partitions": int,
          "n_trials": int,
          "lambda_quantiles": {...},    # λ 분포 p5/p25/p50/p75/p95
          "degradation_slope": float,   # OOS_best ~ a + b·IS_best OLS 기울기
          "degradation_intercept": float,
          "p_oos_loss": float,          # IS 최적 전략의 OOS Sharpe < 0 비율
          "verdict": "robust"|"caution"|"overfit",
        }

    주의:
      - Sharpe 는 raw (일별, 비연환산) — rank 비교라 연환산 상수 무관.
      - 분산 0 (상수 수익률) 전략의 Sharpe = nan → rank 최하위 처리.
    """
    M = np.asarray(returns_matrix, dtype=float)
    if M.ndim != 2:
        raise ValueError("returns_matrix must be 2-D (T, N)")
    T, N = M.shape
    if N < 2:
        raise ValueError("need >= 2 strategy trials (N)")
    if n_partitions % 2 != 0 or n_partitions < 2:
        raise ValueError("n_partitions must be even >= 2")
    if T < n_partitions * 2:
        raise ValueError(f"T={T} too short for S={n_partitions} (need >= {n_partitions * 2})")

    S = n_partitions
    bounds = _block_bounds(T, S)

    # 블록별 통계 사전계산 — 조합마다 행 재슬라이스 회피 (12,870 조합 효율)
    counts = np.empty(S)
    sums = np.empty((S, N))
    sumsqs = np.empty((S, N))
    for k, (a, b) in enumerate(bounds):
        blk = M[a:b]
        counts[k] = blk.shape[0]
        sums[k] = blk.sum(axis=0)
        sumsqs[k] = (blk ** 2).sum(axis=0)

    combos = list(combinations(range(S), S // 2))
    if max_combinations is not None and len(combos) > max_combinations:
        stride = len(combos) / max_combinations
        combos = [combos[int(i * stride)] for i in range(max_combinations)]

    def _sharpe_from(idx: Sequence[int]) -> np.ndarray:
        n = counts[list(idx)].sum()
        s = sums[list(idx)].sum(axis=0)
        ss = sumsqs[list(idx)].sum(axis=0)
        mean = s / n
        var = (ss - n * mean ** 2) / max(n - 1, 1)
        with np.errstate(invalid="ignore", divide="ignore"):
            sd = np.sqrt(np.maximum(var, 0.0))
            sr = np.where(sd > 0, mean / sd, np.nan)
        return sr

    all_blocks = set(range(S))
    lambdas = []
    pairs = []           # (IS_best_sharpe, OOS_sharpe_of_that_strategy)
    for c in combos:
        oos_blocks = tuple(sorted(all_blocks - set(c)))
        sr_is = _sharpe_from(c)
        sr_oos = _sharpe_from(oos_blocks)

        # nan (분산 0) → rank 최하위로: -inf 대체
        sr_is_f = np.where(np.isfinite(sr_is), sr_is, -np.inf)
        sr_oos_f = np.where(np.isfinite(sr_oos), sr_oos, -np.inf)

        n_star = int(np.argmax(sr_is_f))
        oos_rank = int(_rank_ascending(sr_oos_f)[n_star])     # 0-based ascending
        omega = (oos_rank + 1) / (N + 1)                       # ∈ (0, 1)
        lam = math.log(omega / (1.0 - omega))
        lambdas.append(lam)
        pairs.append((sr_is_f[n_star], sr_oos_f[n_star]))

    lambdas_arr = np.array(lambdas)
    pbo = float((lambdas_arr <= 0).mean())

    # 성과 저하 회귀 — IS best vs 그 전략의 OOS (Bailey 2014 §5 degradation)
    is_b = np.array([p[0] for p in pairs])
    oos_b = np.array([p[1] for p in pairs])
    finite = np.isfinite(is_b) & np.isfinite(oos_b)
    if finite.sum() >= 2 and np.std(is_b[finite]) > 0:
        slope, intercept = np.polyfit(is_b[finite], oos_b[finite], 1)
    else:
        slope, intercept = float("nan"), float("nan")
    p_oos_loss = float((oos_b[finite] < 0).mean()) if finite.any() else float("nan")

    verdict = "robust" if pbo <= PBO_PASS else ("overfit" if pbo >= PBO_OVERFIT else "caution")
    q = lambda x: float(np.percentile(lambdas_arr, x))  # noqa: E731
    return {
        "pbo": round(pbo, 4),
        "n_combinations": len(combos),
        "n_partitions": S,
        "n_trials": N,
        "lambda_quantiles": {"p5": q(5), "p25": q(25), "p50": q(50), "p75": q(75), "p95": q(95)},
        "degradation_slope": round(float(slope), 4) if math.isfinite(slope) else None,
        "degradation_intercept": round(float(intercept), 4) if math.isfinite(intercept) else None,
        "p_oos_loss": round(p_oos_loss, 4) if math.isfinite(p_oos_loss) else None,
        "verdict": verdict,
    }
