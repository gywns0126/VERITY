"""
Probabilistic Sharpe Ratio (PSR) — Lopez de Prado & Bailey 정의 (2014).

OOS Sharpe gate 의 통계적 유의성 검정. strategy_evolver.py 의
"proposal.sharpe > current.sharpe + margin" 단순 비교를 PSR p-value 로 교체 가능.

Perplexity Q4 (2026-05-17) 학계 자문 정합. strategy_evolver.py 에서 호출.

산식:
    PSR(SR*) = Φ((SR_observed - SR_benchmark) / SE(SR))

    SE(SR) = sqrt((1 - skew × SR + (kurt - 3) / 4 × SR²) / (T - 1))

    Φ = 표준정규 cdf
    skew = Pearson skewness of returns
    kurt = Pearson kurtosis of returns
    T = OOS 거래일 수

PSR > 0.95: 95% 신뢰 — proposal SR > current SR
PSR > 0.90: 90% 신뢰 — 단측 검정 표준
PSR > 0.50: 50% 이상 확률 — 단순 평균 비교

Deflated Sharpe Ratio (DSR) — 다중 검정 보정 (K trials):
    DSR = Z((1 - γ_E) × Φ⁻¹(1 - 1/K) + γ_E × Φ⁻¹(1 - 1/(K × e)))
    γ_E = Euler-Mascheroni constant ≈ 0.5772
"""
from __future__ import annotations

import math
import statistics
from typing import Dict, List, Optional


_GAMMA_E = 0.5772156649  # Euler-Mascheroni


def _norm_cdf(x: float) -> float:
    """표준정규 cdf — scipy.stats.norm.cdf 대체 (math.erf 사용)."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_ppf(p: float) -> float:
    """표준정규 percent point function (quantile) — 정규 inverse cdf 근사.
    Beasley-Springer-Moro 알고리즘.
    """
    if not 0 < p < 1:
        raise ValueError(f"p must be in (0, 1), got {p}")
    # Beasley-Springer-Moro approximation
    a = [-3.969683028665376e+01, 2.209460984245205e+02,
         -2.759285104469687e+02, 1.383577518672690e+02,
         -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02,
         -1.556989798598866e+02, 6.680131188771972e+01,
         -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01,
         -2.400758277161838e+00, -2.549732539343734e+00,
         4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01,
         2.445134137142996e+00, 3.754408661907416e+00]
    plow = 0.02425
    phigh = 1 - plow
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
               ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p <= phigh:
        q = p - 0.5
        r = q * q
        return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / \
               (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)
    q = math.sqrt(-2 * math.log(1 - p))
    return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
            ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)


def _skewness(returns: List[float]) -> float:
    n = len(returns)
    if n < 3:
        return 0.0
    m = statistics.mean(returns)
    s = statistics.stdev(returns)
    if s == 0:
        return 0.0
    return sum((r - m) ** 3 for r in returns) / (n * s ** 3)


def _kurtosis(returns: List[float]) -> float:
    n = len(returns)
    if n < 4:
        return 3.0  # 정규분포 default
    m = statistics.mean(returns)
    s = statistics.stdev(returns)
    if s == 0:
        return 3.0
    return sum((r - m) ** 4 for r in returns) / (n * s ** 4)


def compute_sr_standard_error(
    sr: float,
    T: int,
    skew: float = 0.0,
    kurt: float = 3.0,
) -> float:
    """Sharpe Ratio 의 표준 오차 (Lo 2002 / Mertens 2002 / Bailey-Lopez de Prado).

    SE(SR) = sqrt((1 + ½·SR² − skew·SR + (kurt−3)/4·SR²) / (T − 1))
            = sqrt((1 − skew·SR + (kurt−1)/4·SR²) / (T − 1))   # 동치 (kurt=Pearson, 정규=3)

    2026-06-11 정정: 옛 식이 Lo(2002) 정규 baseline `+½·SR²` 누락 → SE 과소추정 →
      PSR 과대(과신). 검증 2 원전 = quantstats verbatim(1+0.5·SR²+(kurt-3)/4·SR²) +
      Bailey-Lopez de Prado((kurt-1)/4) 일치. 정규(skew=0,kurt=3): (1+½SR²)/(T-1) (Lo 2002).
    """
    if T < 2:
        return float("inf")
    variance = (1 + 0.5 * sr ** 2 - skew * sr + (kurt - 3) / 4 * sr ** 2) / (T - 1)
    if variance <= 0:
        # 음수 점근분산 = Lo(2002) 점근 SE 식 붕괴(저N·고표본 skew×SR). SE=0(완벽추정) 아님.
        # nan sentinel 로 '추정불가' 전달 → compute_psr 가 psr=None 처리(거짓확실성 차단, RULE 7).
        return float("nan")
    return math.sqrt(variance)


def compute_psr(
    sr_observed: float,
    sr_benchmark: float,
    T: int,
    returns: Optional[List[float]] = None,
    skew: Optional[float] = None,
    kurt: Optional[float] = None,
) -> Dict[str, float]:
    """Probabilistic Sharpe Ratio.

    PSR = Φ((sr_observed - sr_benchmark) / SE(sr_observed))

    Returns:
        {
          "psr": float,           # 0.0 ~ 1.0
          "se_sr": float,
          "skewness": float,
          "kurtosis": float,
          "z_score": float,
          "T": int,
        }
    """
    if returns is not None and len(returns) >= 4:
        if skew is None:
            skew = _skewness(returns)
        if kurt is None:
            kurt = _kurtosis(returns)
    else:
        skew = skew if skew is not None else 0.0
        kurt = kurt if kurt is not None else 3.0

    se = compute_sr_standard_error(sr_observed, T, skew, kurt)
    if not math.isfinite(se) or se <= 0:
        # SE 추정 붕괴(음수 점근분산/비유효) → psr=1.0/z=inf 거짓확실성 대신 '추정불가' None.
        # 저N·고표본 skew×SR 에서 발생. verdict/게이트 미반영(관측 only) — significant_95 None-safe.
        return {
            "psr": None,
            "se_sr": None,
            "skewness": round(skew, 4),
            "kurtosis": round(kurt, 4),
            "z_score": None,
            "T": T,
            "_note": "분산 추정 음수/비유효 — 저N·고표본SR×skew 에서 Lo(2002) 점근 SE 식 붕괴. 유의성 측정 불가(거짓확실성 차단).",
        }
    z = (sr_observed - sr_benchmark) / se
    psr = _norm_cdf(z)
    return {
        "psr": round(psr, 4),
        "se_sr": round(se, 4),
        "skewness": round(skew, 4),
        "kurtosis": round(kurt, 4),
        "z_score": round(z, 4),
        "T": T,
    }


def compute_deflated_sharpe_ratio(
    sr_observed: float,
    T: int,
    n_trials: int,
    returns: Optional[List[float]] = None,
    skew: Optional[float] = None,
    kurt: Optional[float] = None,
) -> Dict[str, float]:
    """Deflated Sharpe Ratio — 다중 검정 보정 (Lopez de Prado).

    K trials 중 SR_max 가 우연히 발생할 확률 보정.
    DSR > 0.95 = 95% 신뢰 (단측 검정).
    """
    if n_trials < 1:
        return {"dsr": None, "_error": "n_trials < 1"}
    if returns is not None and len(returns) >= 4:
        if skew is None:
            skew = _skewness(returns)
        if kurt is None:
            kurt = _kurtosis(returns)
    else:
        skew = skew if skew is not None else 0.0
        kurt = kurt if kurt is not None else 3.0

    # SR_benchmark = expected max SR over K trials (random) — Bailey 2014
    # SR* = sqrt(V[SR]) × ((1-γ_E) × Φ⁻¹(1-1/K) + γ_E × Φ⁻¹(1-1/(K×e)))
    var_sr_estimated = (1 - skew * 0 + (kurt - 3) / 4 * 0) / max(T - 1, 1)
    sd_sr = math.sqrt(max(var_sr_estimated, 1e-9))

    if n_trials == 1:
        sr_benchmark = 0.0
    else:
        K = n_trials
        e = math.e
        try:
            sr_benchmark = sd_sr * (
                (1 - _GAMMA_E) * _norm_ppf(1 - 1.0 / K)
                + _GAMMA_E * _norm_ppf(1 - 1.0 / (K * e))
            )
        except (ValueError, ZeroDivisionError):
            sr_benchmark = 0.0

    return compute_psr(
        sr_observed=sr_observed,
        sr_benchmark=sr_benchmark,
        T=T,
        returns=returns,
        skew=skew,
        kurt=kurt,
    )


if __name__ == "__main__":
    # Sanity test
    import json
    import random
    random.seed(42)

    # SR 0.8 strategy, T=90, 정규분포
    returns_a = [random.gauss(0.001, 0.012) for _ in range(90)]
    sr_a = (statistics.mean(returns_a) / statistics.stdev(returns_a)) * math.sqrt(252)

    # SR 0.5 benchmark
    sr_b = 0.5

    psr_result = compute_psr(sr_a, sr_b, T=90, returns=returns_a)
    print("PSR test (T=90, SR_a vs 0.5):")
    print(json.dumps(psr_result, indent=2))

    # DSR — 27 trials (27 cycle reject 케이스)
    dsr_result = compute_deflated_sharpe_ratio(sr_a, T=90, n_trials=27, returns=returns_a)
    print("\nDSR test (T=90, K=27):")
    print(json.dumps(dsr_result, indent=2))
