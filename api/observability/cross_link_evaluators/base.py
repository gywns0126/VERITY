"""CrossLinkEvaluator base — v1.5 §4 plugin 패턴.

v1.6+ 확장 시 (12주 운영 누적 후) 나머지 7 sub-factor evaluator 가 동일
인터페이스로 추가됨. 현재 1차 scope = brain_distribution_normal 1개.
"""
from __future__ import annotations
from typing import Any, Dict


class CrossLinkEvaluator:
    sub_factor_name: str = ""

    def fetch_ground_truth(self, evaluation_date: str) -> Dict[str, Any]:
        raise NotImplementedError

    def compute_baseline(self, lookback_days: int = 90) -> Dict[str, Any]:
        raise NotImplementedError

    def evaluate(
        self,
        verdict_at_t_minus_14: str,
        ground_truth: Dict[str, Any],
        baseline: Dict[str, Any],
        enabled_tiers: list,
    ) -> Dict[str, Any]:
        raise NotImplementedError
