"""
3단계 깔때기 필터링 엔진 (yfinance 기반)
Step 1: 거래대금 상위 종목
Step 2: 밸류에이션 필터 (PER, PBR)
Step 3: 안심 점수 계산
"""
from typing import List
from api.config import FILTER_MIN_TRADING_VALUE
from api.collectors.stock_data import get_all_stock_data


def step1_trading_filter(stocks: list) -> list:
    """Step 1: 거래대금 기준 필터"""
    filtered = [s for s in stocks if s["trading_value"] >= FILTER_MIN_TRADING_VALUE]
    filtered.sort(key=lambda x: x["trading_value"], reverse=True)
    return filtered


def step2_fundamental_filter(stocks: list) -> list:
    """Step 2: 밸류에이션 필터 (yfinance 한국주식은 PBR 누락이 많아서 유연하게 처리)"""
    results = []
    for s in stocks:
        per = s.get("per", 0)
        pbr = s.get("pbr", 0)

        # PER이 음수(적자)면 제외
        if per < 0:
            continue
        # PER 100 초과는 고평가
        if per > 100:
            continue
        # PBR이 10 초과는 고평가 (0은 데이터 없음이므로 허용)
        if pbr > 10:
            continue

        results.append(s)
    return results


def calculate_safety_score(stock: dict) -> int:
    """
    안심 점수 계산 (0~100)
    """
    score = 0

    per = stock.get("per", 0)
    if 5 <= per <= 15:
        score += 25
    elif 15 < per <= 25:
        score += 15
    elif 0 < per <= 50:
        score += 5

    pbr = stock.get("pbr", 0)
    if 0 < pbr <= 1.0:
        score += 20
    elif 1.0 < pbr <= 1.5:
        score += 15
    elif 1.5 < pbr <= 3.0:
        score += 5
    elif pbr == 0:
        score += 5  # 데이터 없으면 기본 점수

    div_yield = stock.get("div_yield", 0)
    if div_yield >= 3:
        score += 15
    elif div_yield >= 1:
        score += 10

    drop = stock.get("drop_from_high_pct", 0)
    if drop <= -30:
        score += 20
    elif drop <= -20:
        score += 15
    elif drop <= -10:
        score += 10

    trading_val = stock.get("trading_value", 0)
    if trading_val >= 50_000_000_000:
        score += 20
    elif trading_val >= 10_000_000_000:
        score += 15
    elif trading_val >= 1_000_000_000:
        score += 10

    return min(score, 100)


def run_filter_pipeline() -> List[dict]:
    """필터링 파이프라인 실행"""
    print("[Filter] 전 종목 데이터 수집 중...")
    all_stocks = get_all_stock_data()
    print(f"[Filter] 수집 완료: {len(all_stocks)}개 종목")

    print("[Filter] Step 1: 거래대금 필터")
    step1 = step1_trading_filter(all_stocks)
    print(f"[Filter] Step 1 결과: {len(step1)}개 종목")

    print("[Filter] Step 2: 밸류에이션 필터")
    step2 = step2_fundamental_filter(step1)
    print(f"[Filter] Step 2 결과: {len(step2)}개 종목")

    for s in step2:
        s["safety_score"] = calculate_safety_score(s)

    step2.sort(key=lambda x: x["safety_score"], reverse=True)
    top = step2[:10]

    print("[Filter] 최종 후보:")
    for s in top:
        print(f"  {s['name']} | 안심 {s['safety_score']}점 | {s['price']:,.0f}원 | PER {s['per']} | PBR {s['pbr']}")

    return top
