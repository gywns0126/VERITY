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
    FILTER_TOP_N, FILTER_KR_TOP_N, FILTER_US_TOP_N, UNIVERSE_RAMP_UP_STAGE,
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


# ───────────────────────────────────────────────────────────────────
# Stage 1.5 — 금융업(industry) 제외 (2026-06-07, funnel Phase A.2)
# ───────────────────────────────────────────────────────────────────
# 표준 펀더멘털 팩터(P/B·ROE·레버리지)가 은행/보험/여신에 구조적 왜곡 → 분석 풀 제외.
# sector(섹터) 통째가 아니라 industry(세부업종) 기준 (PM 결정 2026-06-07) — 자산경량
# 금융(데이터/거래소 'Financial Data & Stock Exchanges' = 에프앤가이드 류)은 왜곡 없어 유지.
# 제외 ≠ 영구 무시: 금융 전용 분석 sleeve(은행 NIM/CET1, 보험 combined ratio/float)는
# 별 모듈 큐잉 ([[project_funnel_5stage_sprint]] Phase A.2 trail). 증권(Capital Markets)/
# 자산운용(Asset Management)은 본 경계 밖 — 미래 확장.
_EXCLUDED_FINANCIAL_INDUSTRY_KW = ("Banks", "Insurance", "Credit Services")


def exclude_financial_sector(stocks: List[dict]) -> List[dict]:
    """금융업(은행/보험/여신) industry 제외. 코어 포함 (팩터 왜곡은 코어도 동일).

    industry 빈값(yfinance 미제공) = 통과 (보수 — 결손 데이터로 과제외 회피).
    제외 건수 로깅 (silent cap 금지).
    """
    kept: List[dict] = []
    excluded: List[str] = []
    for s in stocks:
        industry = str(s.get("industry") or "")
        if industry and any(kw in industry for kw in _EXCLUDED_FINANCIAL_INDUSTRY_KW):
            excluded.append(s.get("name") or s.get("ticker") or "?")
        else:
            kept.append(s)
    if excluded:
        print(f"[Stage 1.5 금융업 제외] {len(excluded)}종목: {excluded[:10]}")
    return kept


def run_filter_pipeline(market_scope: str = "all", _metrics: Optional[dict] = None) -> List[dict]:
    """필터링 파이프라인 실행. market_scope: 'kr' | 'us' | 'all'.

    _metrics: ramp_up_monitor 가 yf_failure_rate 받아갈 dict (silent skip 차단).
    """
    print(f"[Filter] 전 종목 데이터 수집 중... (scope={market_scope})")
    all_stocks = get_all_stock_data(market_scope=market_scope, _metrics=_metrics)
    print(f"[Filter] 수집 완료: {len(all_stocks)}개 종목")

    # Stage 1.5 — 금융업 제외 (sector 보유 후)
    all_stocks = exclude_financial_sector(all_stocks)

    # ── Phase 2-B wide_scan shadow (legacy core path 도 동일 hook) ──
    # WIDE_SCAN_MODE=DISABLED 면 즉시 skip. decision 영향 0.
    try:
        from api.analyzers.wide_scan import run_wide_scan_shadow
        ws_result = run_wide_scan_shadow(all_stocks)
        if not ws_result.get("skipped"):
            print(
                f"[Phase 2-B wide_scan {ws_result['mode']}] "
                f"input={ws_result['input_n']} target={ws_result['target_n']} "
                f"passed={ws_result['passed_n']} logged={ws_result['logged']}"
            )
    except Exception as _ws_err:
        print(f"[Phase 2-B wide_scan] 실패(무시): {_ws_err}")

    # ── Phase 2-B 분기 시계열 jsonl 누적 (legacy core path 도 동일 hook) ──
    try:
        from api.utils.quarterly_history import append_universe_snapshot
        qh_result = append_universe_snapshot(all_stocks)
        if qh_result.get("logged"):
            print(f"[quarterly_history] appended {qh_result['appended_n']}")
    except Exception as _qh_err:
        print(f"[quarterly_history] 실패(무시): {_qh_err}")

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
        # 2026-05-11: 시장별 분리. KR 10 + US 15 = 25 (사용자 결정).
        top_kr = kr_pool[:FILTER_KR_TOP_N]
        top_us = us_pool[:FILTER_US_TOP_N]
        top = top_kr + top_us
        print(f"[Filter] 최종 후보: KR {len(top_kr)}개 + US {len(top_us)}개 = {len(top)}개")
    else:
        step2.sort(key=lambda x: x["safety_score"], reverse=True)
        # 단일 시장 = legacy FILTER_TOP_N 사용 (정합 fallback)
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


def run_extended_filter_pipeline(
    market_scope: str = "all",
    target_size: int = 0,
    _metrics: Optional[dict] = None,
) -> List[dict]:
    """Phase 2-A 확장 유니버스 → 기존 step1/step2/score/topN 그대로 적용.

    target_size <= 85 → 기존 run_filter_pipeline 으로 위임 (backward compatible).
    target_size > 85 → universe_builder + hard_floor → custom_universe → 기존 파이프라인.
    종목 0 edge case → 코어 fallback (run_filter_pipeline 호출).

    _metrics: ramp_up_monitor 가 yf_failure_rate 받아갈 dict (silent skip 차단).
    """
    if target_size <= _PHASE_2A_TRIGGER_THRESHOLD:
        return run_filter_pipeline(market_scope=market_scope, _metrics=_metrics)

    print(f"[Phase 2-A] 확장 유니버스 모드 (target={target_size}, scope={market_scope})")

    custom = _build_custom_universe_for_phase_2a(market_scope, target_size)
    if not custom:
        print(f"[Phase 2-A] custom universe 비어 있음 → 코어 fallback")
        return run_filter_pipeline(market_scope=market_scope, _metrics=_metrics)

    print(f"[Phase 2-A] Hard Floor 통과 {len(custom)}개 종목 데이터 수집 시작")
    all_stocks = get_all_stock_data(market_scope=market_scope, custom_universe=custom, _metrics=_metrics)
    print(f"[Phase 2-A] 수집 완료: {len(all_stocks)}개 종목")

    if not all_stocks:
        print(f"[Phase 2-A] 데이터 수집 0건 → 코어 fallback")
        return run_filter_pipeline(market_scope=market_scope, _metrics=_metrics)

    # Stage 1.5 — 금융업 제외 (sector 보유 후, DART/shadow/snapshot 전)
    all_stocks = exclude_financial_sector(all_stocks)

    # ── DART pre-attach (KR universe 주 1회 batch snapshot 주입) ──
    # dart_batch cron (일요일 KST 22:00) 가 dart_fundamentals_kr.json 적재.
    # cache hit 시 stock dict per/pbr/roe/debt_ratio/op_margin 보강 (DART 1순위, 메모리 결정 2).
    try:
        from api.utils.dart_pre_attach import attach_dart_to_stocks
        dart_result = attach_dart_to_stocks(all_stocks, max_stale_days=8)
        if dart_result.get("cache_hit"):
            print(f"  [DART pre-attach] {dart_result['attached_n']}/{dart_result['kr_total_n']} KR 종목 보강")
    except Exception as _dart_err:
        print(f"  [DART pre-attach] 실패(무시): {_dart_err}")

    # ── Phase 2-B wide_scan shadow (5,000 raw 입력) ──
    # 메모리 원칙 9 funnel 정합: Coarse Filter 위치 = step1/step2 *전*, 5,000 raw.
    # WIDE_SCAN_MODE=DISABLED 면 즉시 skip (config.py default). decision 영향 0 보장.
    try:
        from api.analyzers.wide_scan import run_wide_scan_shadow
        ws_result = run_wide_scan_shadow(all_stocks)
        if not ws_result.get("skipped"):
            print(
                f"[Phase 2-B wide_scan {ws_result['mode']}] "
                f"input={ws_result['input_n']} target={ws_result['target_n']} "
                f"passed={ws_result['passed_n']} logged={ws_result['logged']}"
            )
    except Exception as _ws_err:
        print(f"[Phase 2-B wide_scan] 실패(무시): {_ws_err}")

    # ── Phase 2-B 분기 시계열 jsonl 누적 (5,000 raw snapshot) ──
    # WIDE_SCAN_MODE 무관 — 시계열 누적 자체가 텐버거 leading 정량 input (CANSLIM C / GP/A 가속 / FCF trend)
    # 13주 누적 후 F-Score Δ 항목 + Magic Formula 한국개선 정량 가능. decision 영향 0.
    try:
        from api.utils.quarterly_history import append_universe_snapshot
        qh_result = append_universe_snapshot(all_stocks)
        if qh_result.get("logged"):
            print(f"[quarterly_history] appended {qh_result['appended_n']}")
    except Exception as _qh_err:
        print(f"[quarterly_history] 실패(무시): {_qh_err}")

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
        # 2026-05-11: 시장별 분리. KR 10 + US 15 = 25 (사용자 결정).
        top_kr = kr_pool[:FILTER_KR_TOP_N]
        top_us = us_pool[:FILTER_US_TOP_N]
        top = top_kr + top_us
        print(f"[Phase 2-A] 최종: KR {len(top_kr)} + US {len(top_us)} = {len(top)}개")
    else:
        step2.sort(key=lambda x: x["safety_score"], reverse=True)
        top = step2[:FILTER_TOP_N]
        print(f"[Phase 2-A] 최종 후보: {len(top)}개")

    if not top:
        print(f"[Phase 2-A] step1/step2 통과 0건 → 코어 fallback")
        return run_filter_pipeline(market_scope=market_scope, _metrics=_metrics)

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
    from time import perf_counter
    _t0 = perf_counter()
    stage = UNIVERSE_RAMP_UP_STAGE or 0
    # 2026-05-10 fix (silent skip 차단): get_all_stock_data → run_filter_pipeline →
    # 여기까지 yf_failure_rate 흘러오게 _metrics dict 전달.
    # ramp_up_monitor 가 항상 0 으로 보고 → trigger dead 였던 결함 (5000 stage 첫 run 노출).
    metrics: dict = {}
    # 2026-05-05: try/finally 보장. 5/1~5/4 mode=full 3건 schedule success 인데
    # jsonl entry 1건만 누적 — extended path 의 예외가 main.py tracer.step 에서
    # silently catch 되면 hook 도달 못 함. finally 로 어떤 경로에서도 측정 보장.
    try:
        if stage <= _PHASE_2A_TRIGGER_THRESHOLD:
            return run_filter_pipeline(market_scope=market_scope, _metrics=metrics)
        if not _is_within_phase2a_window():
            print(f"[Phase 2-A] KST window 06~22 밖 → 코어 fallback (가드 1)")
            return run_filter_pipeline(market_scope=market_scope, _metrics=metrics)
        return run_extended_filter_pipeline(market_scope=market_scope, target_size=stage, _metrics=metrics)
    finally:
        _log_w1_runtime(stage=stage, elapsed=perf_counter() - _t0, market_scope=market_scope, metrics=metrics)


def _log_w1_runtime(*, stage: int, elapsed: float, market_scope: str, metrics: Optional[dict] = None) -> None:
    """W1 production hook — runtime_load_log.jsonl 1줄 누적. silent 실패.

    2026-05-03 — 5건 cron 중 2건만 row 누적 (silent gap) 디버깅 위해
    실패 시 stderr 1줄 노출 (logger 환경 의존 없이). main 흐름 무중단.

    2026-05-10 — silent skip 차단 (memory feedback_data_collection_verification_mandatory):
      get_all_stock_data 가 _metrics dict 에 채운 yf_failure_rate 를 monitor 에 의무 전달.
      이전엔 default 0.0 으로 박혀 yf rate-limit 65% 도 trigger=[] 로 보고된 결함 노출.
    """
    try:
        import os as _os
        import sys
        from api.observability.ramp_up_monitor import log_run_with_estimate
        from api.observability.dart_metrics import (
            compute_dart_failure_rate,
            get_dart_snapshot,
        )
        mode = _os.environ.get("ANALYSIS_MODE", "unknown")
        m = metrics or {}
        yf_fail = float(m.get("yf_failure_rate", 0.0))
        yf_attempted = int(m.get("yf_attempted", 0))
        yf_failed = int(m.get("yf_failed", 0))
        # W3 wiring (2026-05-21) — get_all_stock_data 가 _metrics 에 채운 라이브 인자 통합.
        #   rate_limit_violations ← yf_rate_limited (yfinance_safe wrapper 누적)
        #   kr_first_call_ms       ← 첫 KR fetch latency (get_all_stock_data 측정)
        # W3 4/4 (2026-05-23) — dart_metrics drain. DartScout._call + dart_fundamentals
        #   _fetch_fnltt_all_cached 가 process-level state 에 누적 → 여기서 snapshot.
        rate_limit_violations = int(m.get("yf_rate_limited", 0))
        kr_first_call_ms = int(m.get("kr_first_call_ms", 0))
        dart_fail = compute_dart_failure_rate()
        dart_snap = get_dart_snapshot()
        result = log_run_with_estimate(
            mode=mode,
            ramp_up_stage=stage,
            execution_time_seconds=elapsed,
            yfinance_failure_rate=yf_fail,
            dart_failure_rate=dart_fail,
            kr_max_workers_used=30,
            kr_first_call_ms=kr_first_call_ms,
            rate_limit_violations=rate_limit_violations,
            us_max_workers_used=50,
            extra={
                "market_scope": market_scope,
                "yf_attempted": yf_attempted,
                "yf_failed": yf_failed,
                "dart_attempted": dart_snap["dart_attempted"],
                "dart_failed": dart_snap["dart_failed"],
                "dart_rate_limited": dart_snap["dart_rate_limited"],
            },
        )
        # 2026-05-05: 5/1~5/4 mode=full 3건 success 인데 jsonl entry 1건만 누적.
        # logged=True 도 명시적 stderr 1줄 — 다음 run 부터 발동 여부 추적용.
        if result.get("logged"):
            triggers = result.get("fail_triggers") or []
            print(
                f"[runtime_load] OK: mode={mode} stage={stage} elapsed={elapsed:.2f}s "
                f"scope={market_scope} yf_fail={yf_fail:.2%} ({yf_failed}/{yf_attempted}) "
                f"dart_fail={dart_fail:.2%} ({dart_snap['dart_failed']}/{dart_snap['dart_attempted']}) "
                f"rate_limit={rate_limit_violations} kr_first_call_ms={kr_first_call_ms} triggers={triggers}",
                file=sys.stderr, flush=True,
            )
        else:
            print(
                f"[runtime_load] WARNING: stage={stage} elapsed={elapsed:.2f}s "
                f"scope={market_scope} → logged=False err={result.get('error')}",
                file=sys.stderr, flush=True,
            )
    except Exception as e:
        import sys, traceback
        print(
            f"[runtime_load] WARNING outer except: stage={stage} elapsed={elapsed:.2f}s "
            f"scope={market_scope} err={e}",
            file=sys.stderr, flush=True,
        )
        traceback.print_exc(file=sys.stderr)
