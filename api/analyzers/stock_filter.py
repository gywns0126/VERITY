"""
3단계 깔때기 필터링 엔진 v2 (Sprint 3)
Step 1: 거래대금 필터
Step 2: 펀더멘털 필터 (PER/PBR + 부채비율 + 영업이익률)
Step 3: 안심 점수 계산 (8개 팩터 기반)
"""
from typing import List
from api.config import FILTER_MIN_TRADING_VALUE, FILTER_MIN_TRADING_VALUE_US, FILTER_MAX_DEBT_RATIO, FILTER_TOP_N
from api.collectors.stock_data import get_all_stock_data


def step1_trading_filter(stocks: list) -> list:
    """Step 1: 거래대금 기준 필터 (KRW/USD 자동 분기)"""
    filtered = []
    for s in stocks:
        is_us = s.get("currency") == "USD"
        threshold = FILTER_MIN_TRADING_VALUE_US if is_us else FILTER_MIN_TRADING_VALUE
        if s["trading_value"] >= threshold:
            filtered.append(s)
    filtered.sort(key=lambda x: x["trading_value"], reverse=True)
    return filtered


def step2_fundamental_filter(stocks: list) -> list:
    """Step 2: 펀더멘털 필터 (PER/PBR + 부채비율 + 수익성)"""
    results = []
    for s in stocks:
        per = s.get("per", 0)
        pbr = s.get("pbr", 0)
        debt = s.get("debt_ratio", 0)
        op_margin = s.get("operating_margin", 0)

        if per < 0:
            if op_margin > 0:
                s["_turnaround"] = True
            else:
                continue
        if per > 100:
            continue
        if pbr > 10:
            continue
        if debt > FILTER_MAX_DEBT_RATIO and debt > 0:
            continue

        results.append(s)
    return results


def calculate_safety_score(stock: dict) -> int:
    """안심 점수 계산 v2 (0~100, 8개 팩터)"""
    score = 0

    per = stock.get("per", 0)
    if 5 <= per <= 15:
        score += 20
    elif 15 < per <= 25:
        score += 12
    elif 0 < per <= 50:
        score += 5

    pbr = stock.get("pbr", 0)
    if 0 < pbr <= 1.0:
        score += 15
    elif 1.0 < pbr <= 1.5:
        score += 10
    elif 1.5 < pbr <= 3.0:
        score += 5
    elif pbr == 0:
        score += 3

    div_yield = stock.get("div_yield", 0)
    if div_yield >= 3:
        score += 12
    elif div_yield >= 1:
        score += 7

    drop = stock.get("drop_from_high_pct", 0)
    if drop <= -30:
        score += 15
    elif drop <= -20:
        score += 10
    elif drop <= -10:
        score += 5

    trading_val = stock.get("trading_value", 0)
    is_us = stock.get("currency") == "USD"
    if is_us:
        if trading_val >= 500_000_000:
            score += 12
        elif trading_val >= 100_000_000:
            score += 8
        elif trading_val >= 50_000_000:
            score += 4
    else:
        if trading_val >= 50_000_000_000:
            score += 12
        elif trading_val >= 10_000_000_000:
            score += 8
        elif trading_val >= 1_000_000_000:
            score += 4

    debt = stock.get("debt_ratio", 0)
    if 0 < debt <= 30:
        score += 10
    elif 30 < debt <= 60:
        score += 6
    elif debt == 0:
        score += 3

    op_margin = stock.get("operating_margin", 0)
    if op_margin >= 15:
        score += 10
    elif op_margin >= 8:
        score += 6
    elif op_margin >= 3:
        score += 3

    roe = stock.get("roe", 0)
    if roe >= 15:
        score += 6
    elif roe >= 8:
        score += 4
    elif roe >= 3:
        score += 2

    if stock.get("_turnaround"):
        score = max(score - 10, 0)

    return min(score, 100)


def run_filter_pipeline(market_scope: str = "all") -> List[dict]:
    """필터링 파이프라인 실행. market_scope: 'kr' | 'us' | 'all'"""
    print(f"[Filter] 전 종목 데이터 수집 중... (scope={market_scope})")
    all_stocks = get_all_stock_data(market_scope=market_scope)
    print(f"[Filter] 수집 완료: {len(all_stocks)}개 종목")

    print("[Filter] Step 1: 거래대금 필터")
    step1 = step1_trading_filter(all_stocks)
    print(f"[Filter] Step 1 결과: {len(step1)}개 종목")

    print("[Filter] Step 2: 펀더멘털 필터 (PER/PBR/부채비율)")
    step2 = step2_fundamental_filter(step1)
    print(f"[Filter] Step 2 결과: {len(step2)}개 종목")

    for s in step2:
        s["safety_score"] = calculate_safety_score(s)

    if market_scope == "all":
        kr_pool = [s for s in step2 if s.get("currency") != "USD"]
        us_pool = [s for s in step2 if s.get("currency") == "USD"]
        kr_pool.sort(key=lambda x: x["safety_score"], reverse=True)
        us_pool.sort(key=lambda x: x["safety_score"], reverse=True)
        top_kr = kr_pool[:FILTER_TOP_N]
        top_us = us_pool[:FILTER_TOP_N]
        top = top_kr + top_us
        print(f"[Filter] 최종 후보: KR {len(top_kr)}개 + US {len(top_us)}개 = {len(top)}개")
    else:
        step2.sort(key=lambda x: x["safety_score"], reverse=True)
        top = step2[:FILTER_TOP_N]
        print(f"[Filter] 최종 후보 (상위 {len(top)}개):")

    for s in top:
        tag = " [턴어라운드]" if s.get("_turnaround") else ""
        mkt = "US" if s.get("currency") == "USD" else "KR"
        print(f"  [{mkt}] {s['name']} | 안심 {s['safety_score']}점 | PER {s['per']} | 부채 {s['debt_ratio']}% | 영업 {s['operating_margin']}%{tag}")

    return top
