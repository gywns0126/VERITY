"""
Phase 2 Module 1 — Factor Engine (8월 wire 전제 stub)

목적: Cross-sectional factor IC/ICIR 측정 → 가중치 조정 + factor pool 관리.

참고 (≥2 학술, feedback_formula_coefficient_fact_check 정합):
  - Fama-MacBeth (1973) "Risk, Return, and Equilibrium: Empirical Tests" JPE
  - Bailey & Lopez de Prado (2014) "The Deflated Sharpe Ratio" JPM
  - Microsoft qlib Alpha158 / Alpha360 factor set
    (memory project_qlib_ai_factor_reference_2026_05_27)
  - Perplexity Q2 (5/17) "Factor IC/IR 1인 운용 적정 복잡도"
    → ICIR < 0.2 weight floor 30% / ≥ 0.3 정상 / ≥ 0.5 가중 증가

입출력 schema (사전 정의, RULE 7 — 임계/가중치 산식 미정 stub):

  Input:
    - api.intelligence.verity_brain 의 factor sub-scores (fact/sent axes)
    - data/wide_scan_log.jsonl 의 7차원 composite components
    - daily snapshot N ≥ 252 (IC 통계 게이트, memory project_minimum_n_milestones_2026_05_18)

  Output (data/factor_log.jsonl):
    - as_of: ISO timestamp (KST)
    - factor_name: str (e.g. "value", "profitability", "momentum")
    - ic_spearman: float  (cross-sectional rank correlation, -1 ~ 1)
    - ic_pearson: float
    - icir: float  (IC mean / IC std, "information coefficient ratio")
    - n_obs: int
    - window_days: int  (252 default)
    - weight_adj: float | None  (ICIR 게이트 통과 시만, RULE 7 사전등록 후 활성)

운영 계획 (project_institutional_5module_roadmap):
  - 2026-08 시작 — N ≥ 90 거래일 SHADOW→PRODUCTION 게이트 통과 후
  - sequential dep: Factor → Stress (9월) → Portfolio (11월) → Attribution (12~1월)
  - parallel 가능 (조건 3-B): Regime (10월) 과 Factor (8~9월) 병렬 input dep 무관

RULE 7 정합:
  - 임계 (ICIR cutoff / weight floor / 게이트 N) = PM 사전등록 후 활성
  - 본 stub = 산식 미정, NotImplementedError. 8월 wire 시 verity_constitution.json 매핑.
"""
from __future__ import annotations

from typing import Any, Dict, List


def compute_factor_ic(
    factor_name: str,
    daily_scores: List[Dict[str, float]],
    forward_returns: List[Dict[str, float]],
    window_days: int = 252,
) -> Dict[str, Any]:
    """Cross-sectional IC 계산 (Spearman rank correlation).

    Phase 2 Module 1 8월 wire. 본 stub = NotImplementedError.

    Args:
        factor_name: "value" / "profitability" / "momentum" / ... (verity_constitution.json 매핑)
        daily_scores: [{"date": "YYYY-MM-DD", "ticker": "AAPL", "score": 0.72}, ...]
        forward_returns: [{"date": "YYYY-MM-DD", "ticker": "AAPL", "ret_1d": 0.012}, ...]
        window_days: 252 default (1년 거래일, IC 통계 의미 게이트)

    Returns:
        {
          "factor_name": str,
          "ic_spearman": float,
          "ic_pearson": float,
          "icir": float,
          "n_obs": int,
          "window_days": int,
          "as_of": ISO timestamp,
        }
    """
    raise NotImplementedError("Phase 2 Module 1 — 2026-08 wire 전제 stub")


def adjust_weight_by_icir(
    factor_name: str,
    icir: float,
) -> float | None:
    """ICIR 기반 factor 가중치 조정 (Perplexity Q2 5/17 사전등록).

    Phase 2 Module 1 8월 wire. RULE 7 — 임계 (0.2 / 0.3 / 0.5) 사전등록 commit 후 활성.

    Args:
        factor_name: factor 이름
        icir: information coefficient ratio (IC mean / IC std)

    Returns:
        weight_adj: float (0.3 ~ 1.5) | None (ICIR < 0.2 또는 게이트 미통과)
    """
    raise NotImplementedError("Phase 2 Module 1 — RULE 7 임계 사전등록 후 활성")
