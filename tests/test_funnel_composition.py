"""Funnel Phase A 합성 회귀 테스트 (2026-06-07).

hard_floor(Stage 1 구조적/품질, universe build + core keep-clause) → exclude_financial_sector
(Stage 1.5, fetch 후) 체인이 올바로 합성되는지 검증. 정밀검수(2026-06-07)의 ad-hoc 합성
체크를 영구 가드로 도구화 ([[project_site_audit_tool]] 규율 = 재현 도구화).
"""
from __future__ import annotations

from api.analyzers.hard_floor import apply_hard_floor
from api.analyzers.stock_filter import exclude_financial_sector

_GOOD = dict(market_cap=100_000_000_000, avg_trading_value_30d=5_000_000_000)
_USGOOD = dict(market_cap=600_000_000, avg_trading_value_30d=12_000_000)


def _pipeline_survivors(universe):
    """실 파이프라인 순서 재현: hard_floor(+ universe_builder 'passes OR is_core' keep) → 금융제외."""
    after_hf = []
    for s in universe:
        apply_hard_floor(s)
        if s["hard_floor_metadata"]["passes"] or s.get("is_core"):
            after_hf.append(s)
    return {s["name"] for s in exclude_financial_sector(after_hf)}


def test_full_universe_composition():
    universe = [
        dict(ticker="005930", name="삼성전자", currency="KRW", industry="Semiconductors", **_GOOD),         # 생존
        dict(ticker="005935", name="삼성전자우", currency="KRW", industry="Semiconductors", **_GOOD),       # 우선주(Rule4)
        dict(ticker="900110", name="이스트아시아", currency="KRW", industry="Specialty", **_GOOD),           # 외국주권(Rule5)
        dict(ticker="123450", name="엔에이치스팩30호", currency="KRW", industry="Shell", **_GOOD),           # SPAC(Rule6)
        dict(ticker="175330", name="JB금융지주", currency="KRW", industry="Banks - Regional", **_GOOD),     # 금융(1.5)
        dict(ticker="064850", name="에프앤가이드", currency="KRW",
             industry="Financial Data & Stock Exchanges", **_GOOD),                                          # 생존(자산경량)
        dict(ticker="999999", name="페니", currency="KRW", industry="Misc",
             market_cap=1_000_000_000, avg_trading_value_30d=50_000_000),                                    # penny(Rule1)
        dict(ticker="888880", name="관리주", currency="KRW", industry="Misc", is_managed=True, **_GOOD),     # 관리(Rule2)
        dict(ticker="BRK-B", name="BRK-B", currency="USD", industry="Insurance - Diversified", **_USGOOD),  # 금융(1.5)
        dict(ticker="AAPL", name="AAPL", currency="USD", industry="Consumer Electronics", **_USGOOD),       # 생존
        dict(ticker="SMOL", name="US소형", currency="USD", industry="Misc",
             market_cap=300_000_000, avg_trading_value_30d=50_000_000),                                      # US 신임계(Rule1)
        dict(ticker="005930", name="코어은행", currency="KRW", industry="Banks - Regional",
             is_core=True, **_GOOD),                                                                         # 코어 금융도 1.5서 cut
    ]
    assert _pipeline_survivors(universe) == {"삼성전자", "에프앤가이드", "AAPL"}


def test_core_financial_excluded_at_stage_1_5():
    # 코어는 hard_floor 품질 floor 면제(keep-clause)지만, Stage 1.5 금융제외는 코어도 적용
    universe = [dict(ticker="005930", name="코어은행", currency="KRW",
                     industry="Banks - Regional", is_core=True, **_GOOD)]
    assert _pipeline_survivors(universe) == set()


def test_clean_common_stock_survives_full_chain():
    universe = [dict(ticker="005930", name="삼성전자", currency="KRW",
                     industry="Semiconductors", **_GOOD)]
    assert _pipeline_survivors(universe) == {"삼성전자"}
