"""
3단계 깔때기 필터링 엔진 v2 (Sprint 3) + Phase 2-A 확장 유니버스 (2026-05-01)
Step 1: 거래대금 필터
Step 2: 펀더멘털 필터 (PER/PBR + 부채비율 + 영업이익률)
Step 3: 안심 점수 계산 (8개 팩터 기반)

Phase 2-A: run_extended_filter_pipeline — 정적 화이트리스트 85종목 → 동적 5,000.
  UNIVERSE_RAMP_UP_STAGE 환경변수로 Stage 1 (500) ~ Stage 4 (5000) 제어.
  Hard Floor → 코어 fallback → step1/step2 호환성 유지.
"""
from typing import List, Optional
from api.config import (
    FILTER_MIN_TRADING_VALUE, FILTER_MIN_TRADING_VALUE_US, FILTER_MAX_DEBT_RATIO,
    FILTER_TOP_N, UNIVERSE_RAMP_UP_STAGE,
)
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


# ───────────────────────────────────────────────────────────────────
# Phase 2-A — 확장 유니버스 파이프라인 (UNIVERSE_RAMP_UP_STAGE 제어)
# ───────────────────────────────────────────────────────────────────

# 코어 화이트리스트 = 85종목. Stage > 85 일 때 확장 모드 진입.
_PHASE_2A_TRIGGER_THRESHOLD = 85


def _build_custom_universe_for_phase_2a(market_scope: str, target_size: int) -> Optional[dict]:
    """확장 유니버스 dict ({ticker_yf: name}) 생성. Hard Floor 통과 종목만.

    KR=KRX OpenAPI K1 + US=정적 캐시. 종목 0인 edge case 는 None 반환 → 호출자가 fallback.
    """
    from api.collectors.universe_builder import build_extended_universe

    # KR/US 비율 — 결정 1: KR 2,000 + US 3,000 = 5,000 (40:60)
    kr_target = max(int(target_size * 0.4), 1)
    us_target = max(int(target_size * 0.6), 1)

    custom: dict = {}
    if market_scope in ("kr", "all"):
        try:
            kr_entries = build_extended_universe("KR", target_size=kr_target, apply_hard_floor=True)
            for e in kr_entries:
                # ticker (6자리) → ticker_yf (.KS or .KQ)
                suffix = ".KS" if e.get("market", "").upper() == "KOSPI" else ".KQ"
                custom[f"{e['ticker']}{suffix}"] = e.get("name") or e["ticker"]
        except Exception as exc:
            print(f"[Phase 2-A] KR universe build 실패 → 코어 fallback: {exc}")
    if market_scope in ("us", "all"):
        try:
            us_entries = build_extended_universe("US", target_size=us_target, apply_hard_floor=True)
            for e in us_entries:
                custom[e["ticker"]] = e.get("name") or e["ticker"]
        except Exception as exc:
            print(f"[Phase 2-A] US universe build 실패 → 코어 fallback: {exc}")

    if not custom:
        return None
    return custom


def run_extended_filter_pipeline(market_scope: str = "all", target_size: int = 0) -> List[dict]:
    """Phase 2-A 확장 유니버스 → 기존 step1/step2/score/topN 그대로 적용.

    target_size <= 85 → 기존 run_filter_pipeline 으로 위임 (backward compatible).
    target_size > 85 → universe_builder + hard_floor → custom_universe → 기존 파이프라인.
    종목 0 edge case → 코어 fallback (run_filter_pipeline 호출).
    """
    if target_size <= _PHASE_2A_TRIGGER_THRESHOLD:
        return run_filter_pipeline(market_scope=market_scope)

    print(f"[Phase 2-A] 확장 유니버스 모드 (target={target_size}, scope={market_scope})")

    custom = _build_custom_universe_for_phase_2a(market_scope, target_size)
    if not custom:
        print(f"[Phase 2-A] custom universe 비어 있음 → 코어 fallback")
        return run_filter_pipeline(market_scope=market_scope)

    print(f"[Phase 2-A] Hard Floor 통과 {len(custom)}개 종목 데이터 수집 시작")
    all_stocks = get_all_stock_data(market_scope=market_scope, custom_universe=custom)
    print(f"[Phase 2-A] 수집 완료: {len(all_stocks)}개 종목")

    if not all_stocks:
        print(f"[Phase 2-A] 데이터 수집 0건 → 코어 fallback")
        return run_filter_pipeline(market_scope=market_scope)

    print("[Phase 2-A] Step 1: 거래대금 필터")
    step1 = step1_trading_filter(all_stocks)
    print(f"[Phase 2-A] Step 1 결과: {len(step1)}개")

    print("[Phase 2-A] Step 2: 펀더멘털 필터")
    step2 = step2_fundamental_filter(step1)
    print(f"[Phase 2-A] Step 2 결과: {len(step2)}개")

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
        print(f"[Phase 2-A] 최종: KR {len(top_kr)} + US {len(top_us)} = {len(top)}개")
    else:
        step2.sort(key=lambda x: x["safety_score"], reverse=True)
        top = step2[:FILTER_TOP_N]
        print(f"[Phase 2-A] 최종 후보: {len(top)}개")

    if not top:
        print(f"[Phase 2-A] step1/step2 통과 0건 → 코어 fallback")
        return run_filter_pipeline(market_scope=market_scope)

    return top


def _is_within_phase2a_window() -> bool:
    """결정 5 가드 1 — KST 06:00~22:00 만 wide_scan 허용.

    범위 밖이면 backward compatible: 기존 85종목 run_filter_pipeline 으로 fallback.
    (workflow cron 자체는 손대지 않음 — US realtime 지원 backward compat 보호.)
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo
    hour = datetime.now(ZoneInfo("Asia/Seoul")).hour
    return 6 <= hour < 22


def run_filter_pipeline_with_ramp_up(market_scope: str = "all") -> List[dict]:
    """Phase 2-A dispatch — UNIVERSE_RAMP_UP_STAGE + KST 시간대 기반 자동 분기.

    main.py 가 호출하는 진입점. backward compatible:
      - UNIVERSE_RAMP_UP_STAGE <= 85 → 기존 run_filter_pipeline
      - KST 시간 범위 밖 (가드 1) → 기존 run_filter_pipeline
      - 그 외 → run_extended_filter_pipeline
    """
    stage = UNIVERSE_RAMP_UP_STAGE or 0
    if stage <= _PHASE_2A_TRIGGER_THRESHOLD:
        return run_filter_pipeline(market_scope=market_scope)
    if not _is_within_phase2a_window():
        print(f"[Phase 2-A] KST window 06~22 밖 → 코어 fallback (가드 1)")
        return run_filter_pipeline(market_scope=market_scope)
    return run_extended_filter_pipeline(market_scope=market_scope, target_size=stage)
