"""
conviction_selector — KR vs US 세후 동등 hurdle + AT Sharpe 최적 비중.

출처: Perplexity 2026-05-17 자문 (메모리 [[after-tax-sharpe-kr-us]] 갱신).
docs/COST_MODEL_SPEC.md §5 정밀 산식 적용. 단순 fallback "+5%p" 폐기.

핵심 산식:
    R_KR_AT = R_KR_gross × (1 - t_KR)            # t_KR=0 (비대주주 비과세)
    R_US_AT = R_US_gross × (1 - t_US) - δ_FX     # t_US=0.22, δ_FX=0.003
    σ_US_KRW = √(σ_US² + σ_FX² + 2·ρ·σ_US·σ_FX)  # FX 변동성 포함 실효 σ

    US hurdle (세후 Sharpe 동등) = ((R_KR - R_f)/σ_KR × σ_US + R_f + δ_FX) / (1 - t_US)
    최적 w_KR = Markowitz 2-asset tangency (AT Sharpe max)

학계 표준 정합:
- R_f 세전 사용 (분자/분모 동시 통일 원칙, 혼용 = Sharpe 과대 추정)
- KR 거주자 세제 특화 산식 = 학계 부재 → 실무 도출 (목적함수 내재화)

wiring: 현재 dead code (단위 테스트만). Tier 2 진입 / Brain v6 sprint 시 호출 연결.
"""

from __future__ import annotations
import math
from dataclasses import dataclass
from typing import Optional

from api.config import (
    VAMS_US_CAPITAL_GAINS_RATE,
    VAMS_US_FX_COST_RATE,
    VAMS_RISK_FREE_RATE_PRETAX,
)


# 기본 KRW/USD FX 변동성 (2026-05 기준 30일 σ 추정 ~8% 연환산).
# 환경변수 override 가능 — 위기 국면 σ 상승 시 동적 조정.
DEFAULT_SIGMA_FX = 0.08
# KOSPI/SP500 vs USD/KRW 상관 (~0.1, 거의 독립 가정).
DEFAULT_RHO_S_FX = 0.1


@dataclass
class ConvictionResult:
    """conviction_selector 산출 결과."""
    w_kr: float            # 최적 KR 비중 (0~1)
    w_us: float            # 최적 US 비중 (1 - w_kr)
    us_hurdle_gross: float # KR 와 세후 Sharpe 동등 위한 US gross 기대수익
    kr_at_return: float    # KR 세후 수익
    us_at_return: float    # US 세후 수익 (FX 비용 차감)
    at_sharpe: float       # 포트폴리오 AT Sharpe (최적 비중 기준)
    sigma_us_krw: float    # FX 환산 실효 σ_US
    note: str


def at_return_kr(R_kr_gross: float, t_kr: float = 0.0) -> float:
    """KR 세후 수익률. 비대주주 t_kr = 0 (소액주주 비과세).
    대주주 진입 시 t_kr = 0.20~0.30 (1년 미만 / 3억 초과 누진)."""
    return R_kr_gross * (1.0 - t_kr)


def at_return_us(R_us_gross: float,
                 t_us: float = VAMS_US_CAPITAL_GAINS_RATE,
                 fx_cost: float = VAMS_US_FX_COST_RATE) -> float:
    """US 세후 수익률.

    Note: 250만 양도소득 기본공제는 평균 수익률 산식에서 무시 (개별 매도 시점에 적용,
    포트폴리오 전체 평균 산정 시 미세 영향). conviction 산식 = 평균 기대수익 기준.
    """
    return R_us_gross * (1.0 - t_us) - fx_cost


def sigma_us_krw(sigma_us: float,
                 sigma_fx: float = DEFAULT_SIGMA_FX,
                 rho_s_fx: float = DEFAULT_RHO_S_FX) -> float:
    """US 주식의 KRW 환산 실효 변동성.

    σ_US_KRW = √(σ_US² + σ_FX² + 2·ρ·σ_US·σ_FX)

    한국 거주자 입장에서는 환율 변동이 실효 σ 에 가산됨. 위기 국면 σ_FX ↑ 시 US σ
    상대적 증가 → KR hurdle 상승. ρ ≈ 0.1 가정 (KR 자본통제 환경 + FX 헤지 부재)."""
    return math.sqrt(
        sigma_us ** 2 + sigma_fx ** 2 + 2 * rho_s_fx * sigma_us * sigma_fx
    )


def us_hurdle_gross(R_kr: float, sigma_kr: float, sigma_us: float,
                    R_f: float = VAMS_RISK_FREE_RATE_PRETAX,
                    t_us: float = VAMS_US_CAPITAL_GAINS_RATE,
                    fx_cost: float = VAMS_US_FX_COST_RATE,
                    fx_adjust_sigma: bool = True) -> float:
    """KR 와 세후 Sharpe 동등을 만족하는 US gross 기대수익 hurdle.

    산식:
        kr_excess = R_KR - R_f
        kr_sharpe = kr_excess / σ_KR
        target_us_at_excess = kr_sharpe × σ_US_KRW
        R_US_hurdle = (target_us_at_excess + R_f + fx_cost) / (1 - t_us)

    Args:
        R_kr: KR gross 기대수익률 (연율, 예: 0.15 = 15%)
        sigma_kr: KR σ (연율)
        sigma_us: US gross σ (KRW 환산 전, USD 기준)
        fx_adjust_sigma: True 면 σ_US_KRW 사용 (실효 σ), False 면 σ_US 그대로

    Returns:
        US gross 기대수익 hurdle. R_US > 이 값이면 US 우위.
    """
    sigma_us_eff = sigma_us_krw(sigma_us) if fx_adjust_sigma else sigma_us
    kr_excess = R_kr - R_f
    kr_sharpe = kr_excess / sigma_kr if sigma_kr > 0 else 0.0
    target_us_at_excess = kr_sharpe * sigma_us_eff
    return (target_us_at_excess + R_f + fx_cost) / (1.0 - t_us)


def optimal_kr_weight(R_kr: float, R_us: float,
                       sigma_kr: float, sigma_us: float,
                       rho: float,
                       R_f: float = VAMS_RISK_FREE_RATE_PRETAX,
                       t_kr: float = 0.0,
                       t_us: float = VAMS_US_CAPITAL_GAINS_RATE,
                       fx_cost: float = VAMS_US_FX_COST_RATE,
                       fx_adjust_sigma: bool = True) -> float:
    """Markowitz 2-asset tangency: AT Sharpe 최대화 KR 비중.

    분석적 해 (long-only):
        w_KR_unconstrained = (μ_KR · σ_US² - μ_US · ρ·σ_KR·σ_US) / D
        D = μ_KR·σ_US² + μ_US·σ_KR² - (μ_KR+μ_US)·ρ·σ_KR·σ_US
        where μ_X = R_X_AT - R_f

    [0, 1] clamp 적용 (short 금지).
    """
    R_kr_at = at_return_kr(R_kr, t_kr)
    R_us_at = at_return_us(R_us, t_us, fx_cost)
    sigma_us_eff = sigma_us_krw(sigma_us) if fx_adjust_sigma else sigma_us

    mu_kr = R_kr_at - R_f
    mu_us = R_us_at - R_f

    # 양쪽 모두 R_f 이하면 risk-free 우위 → 50/50 fallback
    if mu_kr <= 0 and mu_us <= 0:
        return 0.5

    cov = rho * sigma_kr * sigma_us_eff
    var_kr = sigma_kr ** 2
    var_us = sigma_us_eff ** 2

    numerator = mu_kr * var_us - mu_us * cov
    denominator = mu_kr * var_us + mu_us * var_kr - (mu_kr + mu_us) * cov

    if abs(denominator) < 1e-12:
        return 0.5

    w_kr = numerator / denominator
    return max(0.0, min(1.0, w_kr))


def at_sharpe(R_p_at: float, sigma_p: float,
              R_f: float = VAMS_RISK_FREE_RATE_PRETAX) -> float:
    """세후 Sharpe ratio. R_f 세전 사용 — 분자/분모 통일 원칙
    (혼용 시 systematically Sharpe 과대 추정, Perplexity 2026-05-17 학계 정합)."""
    if sigma_p <= 0:
        return 0.0
    return (R_p_at - R_f) / sigma_p


def select_conviction(R_kr: float, R_us: float,
                       sigma_kr: float = 0.25,
                       sigma_us: float = 0.28,
                       rho: float = 0.4,
                       R_f: float = VAMS_RISK_FREE_RATE_PRETAX,
                       t_kr: float = 0.0,
                       t_us: float = VAMS_US_CAPITAL_GAINS_RATE,
                       fx_cost: float = VAMS_US_FX_COST_RATE,
                       fx_adjust_sigma: bool = True) -> ConvictionResult:
    """통합 dispatcher: KR/US 비중 + US hurdle + AT Sharpe 산출.

    Args:
        R_kr / R_us: gross 기대수익 (brain_score → R 변환은 호출자 책임)
        sigma_kr / sigma_us: 자산 σ (기본 KOSPI 25% / SP500 28%, 2026-05 추정)
        rho: KR/US 상관 (기본 0.4 — 글로벌 동조 중간)

    Returns:
        ConvictionResult dataclass — frontend / commit log 노출용.
    """
    R_kr_at = at_return_kr(R_kr, t_kr)
    R_us_at = at_return_us(R_us, t_us, fx_cost)
    sigma_us_eff = sigma_us_krw(sigma_us) if fx_adjust_sigma else sigma_us

    w_kr = optimal_kr_weight(
        R_kr, R_us, sigma_kr, sigma_us, rho,
        R_f=R_f, t_kr=t_kr, t_us=t_us, fx_cost=fx_cost,
        fx_adjust_sigma=fx_adjust_sigma,
    )
    w_us = 1.0 - w_kr

    # 포트폴리오 AT 수익 + σ
    R_p_at = w_kr * R_kr_at + w_us * R_us_at
    var_p = (
        w_kr ** 2 * sigma_kr ** 2
        + w_us ** 2 * sigma_us_eff ** 2
        + 2 * w_kr * w_us * rho * sigma_kr * sigma_us_eff
    )
    sigma_p = math.sqrt(max(0.0, var_p))
    sharpe_at = at_sharpe(R_p_at, sigma_p, R_f)

    hurdle = us_hurdle_gross(R_kr, sigma_kr, sigma_us, R_f, t_us, fx_cost, fx_adjust_sigma)
    us_advantage = R_us > hurdle

    note = (
        f"KR {w_kr*100:.1f}% / US {w_us*100:.1f}% | AT Sharpe {sharpe_at:.3f} | "
        f"US hurdle gross {hurdle*100:.2f}% ({'US 우위' if us_advantage else 'KR 우위'})"
    )

    return ConvictionResult(
        w_kr=round(w_kr, 4),
        w_us=round(w_us, 4),
        us_hurdle_gross=round(hurdle, 6),
        kr_at_return=round(R_kr_at, 6),
        us_at_return=round(R_us_at, 6),
        at_sharpe=round(sharpe_at, 4),
        sigma_us_krw=round(sigma_us_eff, 6),
        note=note,
    )
