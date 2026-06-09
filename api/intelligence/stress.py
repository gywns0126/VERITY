"""
Phase 2 Module 2 — Stress Test Engine (9월 wire 전제 stub)

목적: 포트폴리오 tail risk + scenario VaR/CVaR + historical 시나리오 재현.

참고 (≥2 학술, feedback_formula_coefficient_fact_check 정합):
  - Acerbi & Tasche (2002) "On the coherence of expected shortfall" JBF
  - Lopez de Prado (2018) "Advances in Financial Machine Learning" Ch 16 (Backtesting)
  - mlfinlab PBO Bailey-Lopez 2014 정밀 impl (memory project_mlfinlab_pbo_precision_2026_05_27)
  - 2008 GFC / 2020 COVID / 2022 IR shock 시나리오 재현 (historical replay)

입출력 schema (사전 정의, RULE 7 — 임계 미정 stub):

  Input:
    - data/portfolio.json (현재 25 종목 + 비중)
    - data/factor_log.jsonl (Phase 2 Module 1 결과)
    - historical scenario library (2008/2020/2022, 별 데이터 source)

  Output (data/stress_log.jsonl):
    - as_of: ISO timestamp (KST)
    - scenario_id: str (e.g. "gfc_2008", "covid_2020", "ir_shock_2022")
    - var_95: float (95% VaR, 양수 magnitude — feedback_mdd_magnitude_display 정합)
    - var_99: float (99% VaR)
    - cvar_95: float (Conditional VaR / Expected Shortfall)
    - mdd_simulated: float (시나리오 재현 MDD 양수)
    - n_holdings: int
    - dep: Phase 2 Module 1 (factor.py) ICIR 게이트 통과 후 input

운영 계획 (project_institutional_5module_roadmap):
  - 2026-09 시작 — Factor 모듈 (Module 1) 완료 후 sequential
  - dep: Factor 결과 input → Stress
  - parallel 불가 (Factor 결과 의존)

RULE 7 정합:
  - 임계 (VaR confidence level / scenario weight / MDD 경고 임계) = PM 사전등록 후 활성
  - 본 stub = NotImplementedError. 9월 wire 시 verity_constitution.json 매핑.

조건 3-C (minimum viable subset, 2026-05-28 PM 옵션2 확정):
  Stress = 필수 ABSOLUTE — tail risk monitoring 필수. slip = vision 직접 위협.
"""
from __future__ import annotations

from typing import Any, Dict, List


def compute_var_cvar(
    portfolio_weights: Dict[str, float],
    returns_history: List[Dict[str, float]],
    confidence: float = 0.95,
) -> Dict[str, Any]:
    """historical VaR + CVaR 계산.

    Phase 2 Module 2 9월 wire. 본 stub = NotImplementedError.

    Args:
        portfolio_weights: {"AAPL": 0.04, "NVDA": 0.06, ...} (합 1.0)
        returns_history: [{"date": "YYYY-MM-DD", "ticker": "AAPL", "ret_1d": 0.012}, ...]
        confidence: 0.95 default (RULE 7 사전등록 — 0.99 추가 시 PM 승인)

    Returns:
        {
          "var": float (magnitude 양수),
          "cvar": float (magnitude 양수),
          "confidence": float,
          "n_obs": int,
          "as_of": ISO timestamp,
        }
    """
    raise NotImplementedError("Phase 2 Module 2 — 2026-09 wire 전제 stub")


def run_scenario_replay(
    scenario_id: str,
    portfolio_weights: Dict[str, float],
) -> Dict[str, Any]:
    """historical 시나리오 재현 (2008 GFC / 2020 COVID / 2022 IR shock).

    Phase 2 Module 2 9월 wire. 시나리오 library = 별 sprint.

    Args:
        scenario_id: "gfc_2008" / "covid_2020" / "ir_shock_2022" / ...
        portfolio_weights: 현 portfolio.json 비중

    Returns:
        {
          "scenario_id": str,
          "mdd_simulated": float (양수 magnitude),
          "duration_days": int,
          "n_holdings_affected": int,
          "as_of": ISO timestamp,
        }
    """
    raise NotImplementedError("Phase 2 Module 2 — scenario library 별 sprint")
