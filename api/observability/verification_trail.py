"""verification_trail — N counter helper (Phase 1 P1-d).

PM=approved 2026-05-23 (plan §Phase 1-d).
WHY: VAMS reset_meta 시점 = N=0 origin. 매매 이벤트 count → N_today.
     Q11 milestone (50/100/252/365) 까지 잔여 계산. Bailey-Lopez de Prado 2014
     N≥252 후 통계 유의 (메모리 [[project_minimum_n_milestones_2026_05_18]]).
DATA: portfolio.vams.simulation_stats.total_trades (5/17 reset 후 누적 trade count) +
      portfolio.validation.cumulative_days (운영 일수).
EXPECTED: cockpit_aggregate.py 가 compute_n_today() + compute_milestones() 호출 추가.

자기 산식 0 (단순 count + 차이). RULE 7 비대상.

별 ledger (verification_trail.jsonl) 기록하지 않음 — Phase 2 후속 (시계열 분석 필요 시).
"""
from __future__ import annotations

from typing import Any, Dict, Optional


# 통계 유의성 milestone (메모리 [[project_minimum_n_milestones_2026_05_18]] 정합)
_MILESTONES = {
    "to_50": 50,    # IC 측정 가능 임계 (5% 신뢰)
    "to_100": 100,  # PSR 적용 가능 (Bailey-Lopez 2014)
    "to_252": 252,  # IC IR 신뢰 임계 (1년 영업일)
    "to_365": 365,  # 운영 trail 1년 (목표 2027-05)
}


def compute_n_today(portfolio: Dict[str, Any]) -> Dict[str, int]:
    """portfolio.json → N counter dict 반환.

    Returns:
        {
            "n_trades": int,            # vams.simulation_stats.total_trades
            "n_validation_days": int,   # validation.cumulative_days (운영 일수)
            "n_validation_samples": int # validation.sample_total
        }

    결손 source 부분 = 0 반환 (silent skip 차단 — 0 값이 의도된 미충족).
    """
    vams = portfolio.get("vams") or {}
    sim = vams.get("simulation_stats") or {}
    val = portfolio.get("validation") or {}

    try:
        n_trades = int(sim.get("total_trades") or 0)
    except (TypeError, ValueError):
        n_trades = 0
    try:
        n_days = int(val.get("cumulative_days") or 0)
    except (TypeError, ValueError):
        n_days = 0
    try:
        n_samples = int(val.get("sample_total") or 0)
    except (TypeError, ValueError):
        n_samples = 0

    return {
        "n_trades": n_trades,
        "n_validation_days": n_days,
        "n_validation_samples": n_samples,
    }


def compute_milestones(n_current: int) -> Dict[str, int]:
    """N_current 기준 milestone 잔여 계산.

    Args:
        n_current: 현 N (trades / days / samples 중 하나).

    Returns:
        {"to_50": 잔여, "to_100": 잔여, "to_252": 잔여, "to_365": 잔여}
        도달 시 = 0 (음수 반환하지 않음).
    """
    return {
        key: max(0, target - n_current)
        for key, target in _MILESTONES.items()
    }


def compute_trail(portfolio: Dict[str, Any]) -> Dict[str, Any]:
    """전체 N trail 산출.

    Returns:
        {
            "n_today": {n_trades, n_validation_days, n_validation_samples},
            "trade_milestones": {to_50, to_100, to_252, to_365},
            "day_milestones": {to_50, to_100, to_252, to_365},
            "sample_milestones": {to_50, to_100, to_252, to_365}
        }
    """
    n_today = compute_n_today(portfolio)
    return {
        "n_today": n_today,
        "trade_milestones": compute_milestones(n_today["n_trades"]),
        "day_milestones": compute_milestones(n_today["n_validation_days"]),
        "sample_milestones": compute_milestones(n_today["n_validation_samples"]),
    }
