"""2026-07-24 2차 산식 감사 Class B(돈 우선) — graham PEG 분모 revenue→EPS + PEGY 배당조정.

graham.py PEG 보정(-15/+8/+15)이 red_flags 와 동일 revenue_growth fallback 버그 → US 15종목 중 13 을
매출성장 기반 오산 PEG 로 잘못된 -15 penalty(가치주 오탈락). 실 EPS(eps_quarterly_growth) + PEGY
(Lynch 배당 팩터: 분모=성장+배당수익률)로 정정. red_flags PEG(#153)와 정합.
"""
from __future__ import annotations

from api.intelligence.factors.graham import _compute_graham_score
from api.intelligence.factors.red_flags import _detect_red_flags


def _g(stock):
    return _compute_graham_score(stock)


def test_graham_good_eps_growth_no_penalty():
    # EPS 35% 성장(PEGY 낮음) → -15 없어야 (옛 revenue 12%면 PEG 3.1→-15 였음)
    good = _g({"per": 37.0, "eps_quarterly_growth": 35.4, "div_yield": 2.5})
    expensive = _g({"per": 40.0, "eps_quarterly_growth": 5.0, "div_yield": 0})
    assert good > expensive  # 좋은 성장주는 -15 penalty 회피


def test_graham_ignores_revenue_growth():
    # revenue_growth 만 있고 eps 없음 → PEG 미평가(revenue 로 계산 안 함)
    only_rev = _g({"per": 70.0, "revenue_growth": 7.0})   # old: 70/7=10>2 → -15
    no_data = _g({"per": 70.0})
    assert only_rev == no_data  # revenue_growth 는 PEG 에 영향 없음


def test_graham_pegy_dividend_adjustment():
    # 고배당 가치주: 성장 낮아도 배당 가산 시 PEGY 개선 → -15 완화.
    # per 30, eps 3% → PEG 10(>2, -15). div 7% → PEGY 30/10=3 여전히>2. div 없이 vs 있이 비교로 배당효과 검증.
    no_div = _g({"per": 20.0, "eps_quarterly_growth": 8.0, "div_yield": 0})    # PEG 2.5>2 → -15
    with_div = _g({"per": 20.0, "eps_quarterly_growth": 8.0, "div_yield": 5.0})  # PEGY 20/13=1.54≤2 → 중립
    assert with_div > no_div  # 배당 가산이 PEGY 개선 → penalty 완화


def test_redflags_pegy_high_dividend_not_avoided():
    # red_flags PEGY: 고배당으로 PEGY≤3 → auto_avoid 없어야
    aa = _detect_red_flags({"currency": "KRW", "per": 15.0, "eps_quarterly_growth": 3.0, "div_yield": 5.0}, {"macro": {}})["auto_avoid"]
    assert not any("PEG" in x for x in aa)  # PEGY 15/8=1.9≤3
