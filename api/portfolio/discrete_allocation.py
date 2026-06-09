"""
discrete_allocation — PyPortfolioOpt DiscreteAllocation wrapper (spike, 2026-05-17).

audit 결과 (메모리 [[after-tax-sharpe-kr-us]] / Perplexity Q1~Q8 정합):
- 3단 분할 도입의 1단계 = DiscreteAllocation
- Tier 1 운영 중에도 즉시 활용 가능 (KIS 매수 lot 단위 분배)
- cvxpy 의존성 1회 추가 = 후속 BL/EF/HRP 분할 상환

핵심 산식:
- Greedy: 가장 단순 (반올림 + 남은 자본 재분배). 빠름, 결과 sub-optimal
- LP: cvxpy linear programming (최적 정수해). 느림, 정확

VERITY 통합:
- input = brain_score 기반 비중 (conviction_selector 산출) 또는 manual 비중
- input = 가용 자본 (KRW) + 종목별 현재가
- output = {ticker: integer_lots} + 잔여 현금

wiring: 현재 dead code (KIS 주문 wire 시 호출 trigger). Tier 1 운영 중 매수 lot 분배 즉시 활용 가능.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Optional, Literal


@dataclass
class AllocationResult:
    """DiscreteAllocation 결과."""
    lots: Dict[str, int]           # {ticker: 정수 매수 수량}
    leftover_krw: float            # 잔여 현금 (분배 후 남은 KRW)
    invested_krw: float            # 실제 매수 금액
    target_weights: Dict[str, float]   # 입력 비중 (참고)
    actual_weights: Dict[str, float]   # 실제 분배 후 비중 (KRW 환산)
    method: str                    # "greedy" or "lp"
    note: str


def allocate_lots(
    weights: Dict[str, float],
    prices_krw: Dict[str, float],
    total_capital_krw: float,
    method: Literal["greedy", "lp"] = "greedy",
    min_lot: int = 1,
) -> AllocationResult:
    """비중 → 정수 lot 분배.

    Args:
        weights: {ticker: 비중 (0~1, 합 = 1)}
        prices_krw: {ticker: 현재가 (KRW)}. US 종목이면 호출자가 KRW 환산 후 전달.
        total_capital_krw: 가용 자본 (KRW)
        method: "greedy" (빠름) or "lp" (cvxpy 정수 최적해, 느림)
        min_lot: 최소 lot (KIS 일반 = 1주). KOSPI200 ETF 등은 다를 수 있음.

    Returns:
        AllocationResult dataclass

    Raises:
        ValueError: 빈 weights / 잘못된 합 / 자본 부족 등
    """
    if not weights:
        raise ValueError("weights 비어있음")
    if total_capital_krw <= 0:
        raise ValueError(f"total_capital_krw must > 0, got {total_capital_krw}")

    # 비중 normalize (합 1 보장)
    w_sum = sum(weights.values())
    if w_sum <= 0:
        raise ValueError(f"weights 합 = {w_sum} (> 0 필요)")
    w_norm = {t: v / w_sum for t, v in weights.items()}

    # price 검증
    for t in w_norm:
        if t not in prices_krw or prices_krw[t] <= 0:
            raise ValueError(f"prices_krw[{t}] missing or <= 0")

    try:
        from pypfopt import DiscreteAllocation
        import pandas as pd
    except ImportError as e:
        raise ImportError(
            "PyPortfolioOpt + cvxpy 설치 필요: pip install PyPortfolioOpt==1.6.0 cvxpy"
        ) from e

    # PyPortfolioOpt API — dtype=float 강제 (greedy_portfolio numpy 2.0 int64 casting 버그 회피)
    prices_series = pd.Series(prices_krw, dtype="float64")
    da = DiscreteAllocation(
        w_norm,
        prices_series,
        total_portfolio_value=total_capital_krw,
    )

    if method == "lp":
        try:
            lots, leftover = da.lp_portfolio()
        except Exception as e:
            # LP 실패 시 greedy fallback
            lots, leftover = da.greedy_portfolio()
            method = "greedy_fallback"
    else:
        lots, leftover = da.greedy_portfolio()

    # min_lot 보정 (1 미만 = 0)
    lots = {t: max(0, n) for t, n in lots.items() if n >= min_lot}

    # 실제 비중 산출
    invested = sum(lots[t] * prices_krw[t] for t in lots)
    if invested > 0:
        actual = {t: lots[t] * prices_krw[t] / invested for t in lots}
    else:
        actual = {}

    return AllocationResult(
        lots=lots,
        leftover_krw=round(float(leftover), 2),
        invested_krw=round(invested, 2),
        target_weights=w_norm,
        actual_weights={t: round(v, 4) for t, v in actual.items()},
        method=method,
        note=(
            f"{method} | {len(lots)}종목 매수 | "
            f"투입 {invested:,.0f}원 / 잔여 {leftover:,.0f}원"
        ),
    )
