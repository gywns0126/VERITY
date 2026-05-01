"""
Hard Floor 룰 — Phase 2-A (2026-05-01)

자동 제외 룰 (코어 종목은 면제):
  Rule 1 — 페니스톡:
    KR market_cap < 50억원
    US market_cap < $100M
  Rule 2 — 관리종목/투자경고/거래정지
  Rule 3 — 일평균 거래대금 부족:
    KR < 1억원
    US < $1M

is_core=True 종목은 모든 Rule 면제 (코어 화이트리스트 보호).
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

# 임계값 (원/USD) — 변경 시 결정 6 메모리 갱신 필수
HARD_FLOOR_MIN_MARKET_CAP_KR = 5_000_000_000  # 50억원
HARD_FLOOR_MIN_MARKET_CAP_US = 100_000_000  # $100M
HARD_FLOOR_MIN_TRADING_VALUE_KR = 100_000_000  # 1억원
HARD_FLOOR_MIN_TRADING_VALUE_US = 1_000_000  # $1M


def apply_hard_floor(stock: dict) -> dict:
    """자동 제외 룰 적용. 코어 종목은 면제.

    입력 dict 에 hard_floor_metadata 추가하여 반환 (in-place 변형 + return).

    Returns:
        stock dict + {
          "hard_floor_metadata": {
            "passes": bool,
            "reasons": list[str],
            "applied_rules": list[str],
            "computed_at": ISO,
          }
        }
    """
    is_core = bool(stock.get("is_core"))
    is_us = stock.get("currency") == "USD"

    reasons: list[str] = []
    applied: list[str] = []

    # Rule 1 — 페니스톡 (시총)
    market_cap = stock.get("market_cap", 0) or 0
    threshold_cap = HARD_FLOOR_MIN_MARKET_CAP_US if is_us else HARD_FLOOR_MIN_MARKET_CAP_KR
    applied.append("rule_1_penny_stock")
    if market_cap < threshold_cap:
        reasons.append(
            f"penny_stock: market_cap={market_cap:,} < {threshold_cap:,}"
        )

    # Rule 2 — 관리종목/투자경고/거래정지
    applied.append("rule_2_alert_status")
    if stock.get("is_managed"):
        reasons.append(f"managed_stock: sect_tp={stock.get('sect_tp', '')!r}")
    if stock.get("is_suspended"):
        reasons.append("trading_suspended")

    # Rule 3 — 거래대금 부족
    trading_val = stock.get("avg_trading_value_30d", 0) or 0
    threshold_tv = (
        HARD_FLOOR_MIN_TRADING_VALUE_US if is_us else HARD_FLOOR_MIN_TRADING_VALUE_KR
    )
    applied.append("rule_3_low_trading_value")
    if trading_val < threshold_tv:
        reasons.append(
            f"low_trading_value: avg_30d={trading_val:,} < {threshold_tv:,}"
        )

    # 코어 면제 — 거래정지만 예외 적용 (정지 종목은 코어라도 cut)
    if is_core:
        if stock.get("is_suspended"):
            passes = False
            reasons.append("core_immune_except_suspended")
        else:
            passes = True
            reasons = ["core_immune"]
    else:
        passes = len(reasons) == 0

    stock["hard_floor_metadata"] = {
        "passes": passes,
        "reasons": reasons,
        "applied_rules": applied,
        "computed_at": datetime.now(ZoneInfo("Asia/Seoul")).isoformat(),
    }
    return stock


def filter_hard_floor(stocks: list[dict]) -> list[dict]:
    """list 입력 helper — 룰 적용 후 통과 종목만 반환."""
    out = []
    for s in stocks:
        apply_hard_floor(s)
        if s.get("hard_floor_metadata", {}).get("passes", True):
            out.append(s)
    return out
