"""
Phase 2 Module 4 — Portfolio Optimizer (11월 wire 전제 stub)

목적: Risk Parity / HRP / Black-Litterman 기반 최적 비중 계산.
      현재 균등 + safety_score top N 절단 방식 (구 path) 의 후속.

참고 (≥2 학술, feedback_formula_coefficient_fact_check 정합):
  - Markowitz (1952) "Portfolio Selection" JoF
  - Black & Litterman (1992) "Global Portfolio Optimization" FAJ
  - Lopez de Prado (2016) "Building Diversified Portfolios that Outperform Out-of-Sample" JPM (HRP)
  - Ledoit & Wolf (2004) "Honey, I Shrunk the Sample Covariance Matrix" JPM
  - Riskfolio-Lib (memory project_riskfolio_lib_portfolio_2026_05_27)

입출력 schema (사전 정의, RULE 7 — 임계 미정 stub):

  Input:
    - data/factor_log.jsonl (Module 1)
    - data/stress_log.jsonl (Module 2)
    - data/regime_log.jsonl (Module 3)
    - data/portfolio.json 현 25 종목 candidate

  Output (data/portfolio_weights.json):
    - as_of: ISO timestamp (KST)
    - method: "risk_parity" | "hrp" | "black_litterman" | "ledoit_wolf"
    - weights: {ticker: weight, ...} (합 1.0)
    - n_holdings: int
    - sector_balance: dict
    - dep: Module 1+2+3 모두 input (sequential)

운영 계획 (project_institutional_5module_roadmap):
  - 2026-11 시작 — Factor + Stress + Regime 3 모듈 결과 후
  - dep sequential: Factor (8) → Stress (9) → Regime (10) → Portfolio (11)
  - parallel 불가 (3 모듈 input 모두 의존)

RULE 7 정합:
  - 임계 (방법 선택 / shrinkage strength / BL prior weight) = PM 사전등록 후 활성
  - 본 stub = NotImplementedError. 11월 wire 시 verity_constitution.json 매핑.

fallback (조건 3-C minimum viable subset, 2026-05-28 PM 옵션2 박힘):
  Portfolio = 필수 ABSOLUTE. slip = vision 도달 X.
  현 path (균등 또는 safety_score top N) 유지 = 임시 fallback (vision 정합도 ↓).
"""
from __future__ import annotations

from typing import Any, Dict


def compute_weights_risk_parity(
    covariance_matrix: Dict[str, Dict[str, float]],
) -> Dict[str, float]:
    """Risk Parity 비중 (각 자산 risk contribution 동일).

    Phase 2 Module 4 11월 wire. 본 stub = NotImplementedError.

    Args:
        covariance_matrix: {ticker: {ticker: cov, ...}, ...}

    Returns:
        weights: {ticker: weight, ...} (합 1.0)
    """
    raise NotImplementedError("Phase 2 Module 4 — 2026-11 wire 전제 stub")


def compute_weights_hrp(
    correlation_matrix: Dict[str, Dict[str, float]],
) -> Dict[str, float]:
    """Hierarchical Risk Parity (Lopez de Prado 2016).

    Phase 2 Module 4 11월 wire. 본 stub = NotImplementedError.
    """
    raise NotImplementedError("Phase 2 Module 4 — HRP 11월 wire")


def compute_weights_black_litterman(
    market_weights: Dict[str, float],
    views: Dict[str, float],
    confidence: Dict[str, float],
) -> Dict[str, float]:
    """Black-Litterman (prior + views).

    Phase 2 Module 4 11월 wire. views = Brain v5+ fact/sent + Module 1 factor 결과.
    본 stub = NotImplementedError.
    """
    raise NotImplementedError("Phase 2 Module 4 — Black-Litterman 11월 wire")
