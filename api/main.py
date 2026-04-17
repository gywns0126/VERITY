"""
VERITY — AI 주식 분석 엔진 v8.2 (Sprint 8: 24h×15min + Safety Layer)

24시간 15분 주기, 시각 기반 3단계 자동 모드:
  realtime (KST 9-15):     가격/환율/지수/수급/뉴스/X감성 (~1분)
  full (KST 15:30-16):     + Gemini AI/재무분석/백테스트/텔레그램 (~7분)
  quick (그 외 장외):      + 기술적분석/멀티팩터/XGBoost (~3분)

Safety Layer (v8.2):
  - Deadman's Switch: 데이터 소스 3개+ 실패 시 즉시 분석 중단 + 긴급 알림
  - Cross-Verification: Gemini↔Claude 의견 분열 시 텔레그램 즉시 알림
  - AI 포스트모텀: 매주 Sonnet이 오심 복기 → 실패 원인 분석 리포트
  - VAMS 시뮬레이션: 누적 매매 통계, 승률, MDD 자동 추적
"""
import json
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from api.config import (
    now_kst,
    DATA_DIR,
    CONSENSUS_DATA_PATH,
    COMMODITY_SCOUT_IN_QUICK,
    COMMODITY_NARRATIVE_IN_QUICK,
    ANTHROPIC_API_KEY,
    CLAUDE_TOP_N,
    CLAUDE_MIN_BRAIN_SCORE,
    CLAUDE_IN_QUICK,
    CLAUDE_IN_REALTIME,
    CLAUDE_QUICK_TOP_N,
    CLAUDE_EMERGENCY_THRESHOLD_PCT,
    CLAUDE_EMERGENCY_COOLDOWN_MIN,
    CLAUDE_MORNING_STRATEGY,
    POSTMORTEM_ENABLED,
    STRATEGY_EVOLUTION_ENABLED,
    REPORT_SEND_HOUR_KST,
    REPORT_SEND_MINUTE_KST,
    MORNING_BRIEF_HOUR_KST,
    MORNING_BRIEF_MINUTE_KST,
    VALUE_HUNT_ENABLED,
    CRYPTO_MACRO_ENABLED,
    PERPLEXITY_API_KEY,
    VAMS_PROFILES,
    VAMS_ACTIVE_PROFILE,
)
from api.collectors.stock_data import get_market_index, get_equity_last_price
from api.collectors.krx_openapi import (
    collect_krx_openapi_snapshot,
    collect_krx_tiers,
    krx_tier_plan_dict,
    merge_krx_openapi_snapshots,
)
from api.collectors.macro_data import get_macro_indicators
from api.collectors.news_sentiment import get_stock_sentiment
from api.collectors.market_flow import get_investor_flow
from api.collectors.program_trading_collector import get_program_trading_today
from api.collectors.expiry_calendar import get_expiry_status
from api.collectors.us_flow import compute_us_flow
from api.collectors.ConsensusScout import scout_consensus, save_consensus_batch
from api.analyzers.consensus_score import (
    build_consensus_block,
    load_trade_export_by_ticker,
    merge_fundamental_with_consensus,
)
from api.analyzers.value_chain_trade import attach_value_chain_trade_overlay
from api.analyzers.stock_filter import run_filter_pipeline
from api.analyzers.technical import analyze_technical
from api.analyzers.multi_factor import compute_multi_factor_score
from api.analyzers.gemini_analyst import analyze_batch, generate_daily_report, reanalyze_top_n_pro
from api.analyzers.sector_rotation import get_sector_rotation
from api.analyzers.safe_picks import generate_safe_recommendations
from api.analyzers.macro_adjustments import fundamental_penalty_from_macro
from api.predictors.xgb_predictor import predict_stock
from api.predictors.backtester import backtest_stock
from api.predictors.timing_signal import compute_timing_signal
from api.vams.engine import (
    load_portfolio,
    save_portfolio,
    run_vams_cycle,
    recalculate_total,
)
from api.collectors.news_headlines import collect_headlines, collect_bloomberg_google_news_rss, collect_us_headlines
from api.collectors.sector_analysis import get_sector_rankings
from api.collectors.earnings_calendar import collect_earnings_for_stocks
from api.collectors.global_events import collect_global_events
from api.collectors.geo_trigger import check_taiwan_quake_trigger, format_alert_message
from api.collectors.x_sentiment import collect_x_sentiment
from api.collectors.sentiment_engine import compute_social_sentiment
from api.collectors.CommodityScout import (
    attach_commodity_to_stocks,
    apply_commodity_adjustment_to_fundamental,
    run_commodity_scout,
)
from api.analyzers.commodity_narrator import enrich_commodity_impact_narratives
from api.analyzers.claude_analyst import (
    analyze_batch_deep,
    analyze_batch_light,
    analyze_stock_emergency,
    check_brain_drift,
    generate_morning_strategy,
    merge_dual_analysis,
)
from api.intelligence.alert_engine import generate_briefing
from api.intelligence.verity_brain import analyze_all as verity_brain_analyze
from api.intelligence.periodic_report import generate_periodic_analysis, compute_sector_trend_summary
from api.workflows.archiver import archive_daily_snapshot, cleanup_old_snapshots
from api.intelligence.backtest_archive import evaluate_past_recommendations
from api.analyzers.gemini_analyst import generate_periodic_report
from api.notifications.telegram import (
    send_alerts,
    send_daily_report,
    send_morning_briefing,
    send_deadman_alert,
    send_cross_verification_alert,
    send_postmortem_report,
    send_vams_simulation_report,
)
from api.notifications.telegram_dedupe import (
    filter_deduped_realtime_alerts,
    mark_realtime_alerts_sent,
)
from api.notifications.telegram_bot import run_poll_once
from api.intelligence.tail_risk_digest import maybe_send_tail_risk_digest
from api.intelligence.value_hunter import run_value_hunt
from api.collectors.group_structure import (
    collect_group_structures,
    save_group_structures,
    load_group_structures,
    attach_group_structure_to_candidates,
)
from api.health import run_health_check, validate_deadman_switch, VERSION
from api.tracing import get_tracer
from api.collectors.crypto_macro import collect_crypto_macro
from api.collectors.market_fear_greed import collect_market_fear_greed
from api.collectors.yieldcurve import get_full_yield_curve_data
from api.collectors.etfdata import get_top_etf_summary
from api.collectors.etfus import get_us_etf_summary, get_bond_etf_summary
from api.reports.pdf_generator import generate_all_reports
from api.config import KIS_ENABLED, KIS_IS_REAL, KIS_OPENAPI_BASE_URL
from api.quant.factors.momentum import compute_momentum_score, enrich_momentum_prices
from api.quant.factors.quality import compute_quality_score
from api.quant.factors.volatility import compute_volatility_score, compute_universe_vol_stats
from api.quant.factors.mean_reversion import compute_mean_reversion_score
from api.utils.safe_collect import safe_collect


def _to_float(value, default=0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _fetch_watch_tickers() -> list:
    """Supabase watch_group_items에서 모든 사용자의 관심종목 ticker/market를 반환."""
    import requests as _req
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_ANON_KEY", "")
    if not url or not key:
        return []
    try:
        r = _req.get(
            f"{url}/rest/v1/watch_group_items",
            headers={
                "apikey": key,
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            params={"select": "ticker,name,market", "limit": "200"},
            timeout=8,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"  관심종목 로드 실패: {e}")
        return []


def _merge_watch_items_into_candidates(
    candidates: list,
    watch_items: list,
) -> int:
    """관심종목 중 후보에 없는 것을 추가. 반환: 추가된 수."""
    from api.collectors.stock_data import get_stock_data
    existing = {s.get("ticker") for s in candidates}
    added = 0
    for wi in watch_items:
        ticker = (wi.get("ticker") or "").strip()
        if not ticker or ticker in existing:
            continue
        mkt = (wi.get("market") or "kr").lower()
        is_us = mkt == "us"
        ticker_yf = ticker if is_us else f"{ticker}.KS"
        data = get_stock_data(ticker_yf, period="1y")
        if data:
            data["_from_watchlist"] = True
            candidates.append(data)
            existing.add(ticker)
            added += 1
    return added


def _build_cost_monitor(
    portfolio: dict,
    mode: str,
    effective_mode: str,
    macro: dict,
    run_stats: dict,
) -> dict:
    """
    월 비용 모니터(추정치) 생성/누적.
    - 실제 청구액이 아닌 실행량 기반 추정치
    - month별 usage를 누적해 Framer에서 월 예산 진행률 표시
    """
    now = now_kst()
    month_key = now.strftime("%Y-%m")
    fx_rate = _to_float((macro or {}).get("usd_krw", {}).get("value"), 1350.0)
    if fx_rate <= 0:
        fx_rate = 1350.0

    # 운영자가 환경변수로 조정 가능한 예산/단가(기본값은 보수적 추정)
    target_monthly_krw = int(_to_float(os.environ.get("COST_TARGET_MONTHLY_KRW"), 150000))
    gemini_pro_krw = int(_to_float(os.environ.get("COST_GEMINI_PRO_KRW"), 29000))
    ops_plan_usd = _to_float(os.environ.get("COST_OPS_PLAN_USD"), 16.0)
    gemini_api_budget_usd = _to_float(os.environ.get("COST_GEMINI_API_BUDGET_USD"), 15.0)
    claude_credit_budget_usd = _to_float(os.environ.get("COST_CLAUDE_CREDIT_BUDGET_USD"), 20.0)
    us_data_budget_usd = _to_float(os.environ.get("COST_US_DATA_BUDGET_USD"), 10.0)
    perplexity_budget_usd = _to_float(os.environ.get("COST_PERPLEXITY_BUDGET_USD"), 50.0)
    perplexity_per_call_usd = _to_float(os.environ.get("COST_PERPLEXITY_PER_CALL_USD"), 0.50)

    gemini_stock_unit_usd = _to_float(os.environ.get("COST_GEMINI_STOCK_USD"), 0.015)
    gemini_report_unit_usd = _to_float(os.environ.get("COST_GEMINI_REPORT_USD"), 0.02)
    gemini_pro_per_call_usd = _to_float(os.environ.get("COST_GEMINI_PRO_PER_CALL_USD"), 0.07)
    claude_per_1k_tokens_usd = _to_float(os.environ.get("COST_CLAUDE_PER_1K_TOKENS_USD"), 0.012)
    us_data_per_symbol_usd = _to_float(os.environ.get("COST_US_DATA_PER_SYMBOL_USD"), 0.002)

    prev_cm = portfolio.get("cost_monitor") or {}
    usage_history = prev_cm.get("monthly_usage_history") or {}
    month_usage = usage_history.get(month_key) or {
        "runs": 0,
        "full_runs": 0,
        "full_us_runs": 0,
        "quick_runs": 0,
        "realtime_runs": 0,
        "realtime_us_runs": 0,
        "gemini_stock_calls": 0,
        "gemini_report_calls": 0,
        "gemini_pro_calls": 0,
        "claude_deep_calls": 0,
        "claude_light_calls": 0,
        "claude_tokens": 0,
        "us_data_symbols": 0,
        "us_data_requests_est": 0,
        "perplexity_calls": 0,
    }

    month_usage["runs"] += 1
    mode_key = f"{mode}_runs"
    if mode_key in month_usage:
        month_usage[mode_key] += 1

    month_usage["gemini_stock_calls"] += int(run_stats.get("gemini_stock_calls", 0))
    month_usage["gemini_report_calls"] += int(run_stats.get("gemini_report_calls", 0))
    month_usage["gemini_pro_calls"] = month_usage.get("gemini_pro_calls", 0) + int(run_stats.get("gemini_pro_calls", 0))
    month_usage["claude_deep_calls"] += int(run_stats.get("claude_deep_calls", 0))
    month_usage["claude_light_calls"] += int(run_stats.get("claude_light_calls", 0))
    month_usage["claude_tokens"] += int(run_stats.get("claude_tokens", 0))
    month_usage["us_data_symbols"] += int(run_stats.get("us_data_symbols", 0))
    month_usage["us_data_requests_est"] += int(run_stats.get("us_data_requests_est", 0))
    month_usage["perplexity_calls"] = month_usage.get("perplexity_calls", 0) + int(run_stats.get("perplexity_calls", 0))

    gemini_flash_usd = (
        month_usage["gemini_stock_calls"] * gemini_stock_unit_usd
        + month_usage["gemini_report_calls"] * gemini_report_unit_usd
    )
    gemini_pro_usd = month_usage.get("gemini_pro_calls", 0) * gemini_pro_per_call_usd
    gemini_est_usd = gemini_flash_usd + gemini_pro_usd
    gemini_est_usd = min(gemini_est_usd, gemini_api_budget_usd)

    claude_est_usd = (month_usage["claude_tokens"] / 1000.0) * claude_per_1k_tokens_usd
    claude_est_usd = min(claude_est_usd, claude_credit_budget_usd)

    us_data_est_usd = month_usage["us_data_symbols"] * us_data_per_symbol_usd
    us_data_est_usd = min(us_data_est_usd, us_data_budget_usd)

    perplexity_est_usd = month_usage.get("perplexity_calls", 0) * perplexity_per_call_usd
    perplexity_est_usd = min(perplexity_est_usd, perplexity_budget_usd)

    variable_usd = round(gemini_est_usd + claude_est_usd + us_data_est_usd + perplexity_est_usd, 2)
    fixed_krw = int(round(gemini_pro_krw + (ops_plan_usd * fx_rate)))
    variable_krw = int(round(variable_usd * fx_rate))
    total_krw = fixed_krw + variable_krw
    progress_pct = round((total_krw / max(target_monthly_krw, 1)) * 100, 1)
    status = "ok" if progress_pct < 70 else "warning" if progress_pct < 90 else "critical"

    usage_history[month_key] = month_usage
    # 최근 6개월만 유지
    recent_keys = sorted(usage_history.keys(), reverse=True)[:6]
    usage_history = {k: usage_history[k] for k in recent_keys}

    return {
        "updated_at": now.strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "month_key": month_key,
        "analysis_mode_last": mode,
        "effective_mode_last": effective_mode,
        "exchange_rate": round(fx_rate, 2),
        "budget": {
            "target_monthly_krw": target_monthly_krw,
            "fixed_subscriptions": {
                "gemini_pro_krw": gemini_pro_krw,
                "ops_plan_usd": ops_plan_usd,
                "ops_plan_krw": int(round(ops_plan_usd * fx_rate)),
            },
            "variable_caps_usd": {
                "gemini_api": gemini_api_budget_usd,
                "claude_console": claude_credit_budget_usd,
                "us_data_api": us_data_budget_usd,
                "perplexity_api": perplexity_budget_usd,
            },
        },
        "monthly_usage": month_usage,
        "monthly_usage_history": usage_history,
        "estimated_cost": {
            "variable_usd": variable_usd,
            "variable_krw": variable_krw,
            "fixed_krw": fixed_krw,
            "total_krw": total_krw,
            "progress_pct": progress_pct,
            "status": status,
            "breakdown_usd": {
                "gemini_api": round(gemini_est_usd, 2),
                "gemini_flash": round(gemini_flash_usd, 2),
                "gemini_pro": round(gemini_pro_usd, 2),
                "claude_console": round(claude_est_usd, 2),
                "us_data_api": round(us_data_est_usd, 2),
                "perplexity_api": round(perplexity_est_usd, 2),
            },
        },
        "last_run_estimate": {
            "mode": mode,
            "gemini_stock_calls": int(run_stats.get("gemini_stock_calls", 0)),
            "gemini_report_calls": int(run_stats.get("gemini_report_calls", 0)),
            "gemini_pro_calls": int(run_stats.get("gemini_pro_calls", 0)),
            "claude_deep_calls": int(run_stats.get("claude_deep_calls", 0)),
            "claude_light_calls": int(run_stats.get("claude_light_calls", 0)),
            "claude_tokens": int(run_stats.get("claude_tokens", 0)),
            "us_data_symbols": int(run_stats.get("us_data_symbols", 0)),
            "us_data_requests_est": int(run_stats.get("us_data_requests_est", 0)),
            "perplexity_calls": int(run_stats.get("perplexity_calls", 0)),
        },
    }


_KIS_BROKER_SINGLETON = None

def _get_kis_broker():
    """KIS 브로커 프로세스-레벨 싱글턴. 토큰 발급은 캐시 미스 시 1회만."""
    global _KIS_BROKER_SINGLETON
    if _KIS_BROKER_SINGLETON is not None:
        return _KIS_BROKER_SINGLETON
    if not KIS_ENABLED:
        return None
    if not KIS_IS_REAL:
        print(f"  ⚠ KIS 모의투자 서버 연결 중: {KIS_OPENAPI_BASE_URL}")
        print("  ⚠ 실제 거래 시 KIS_OPENAPI_BASE_URL=https://openapi.koreainvestment.com:9443 설정 필요")
    try:
        from api.trading.kis_broker import KISBroker
        broker = KISBroker()
        if broker.is_configured:
            broker.authenticate()  # 캐시 히트 시 내부에서 API 호출 생략
            _KIS_BROKER_SINGLETON = broker
            return broker
    except Exception as e:
        print(f"  KIS 인증 실패: {e}")
    return None


def build_price_map(portfolio: dict, kis_broker=None) -> dict:
    """
    보유 + recommendations에 등장하는 티커의 현재가 맵.
    KR: KIS API 우선 → pykrx → yfinance 폴백.
    US: 티커 그대로 키 (yfinance).
    """
    seen = set()
    entries = []

    def add_entry(raw_ticker, ticker_yf=None, currency=None):
        if raw_ticker is None:
            return
        is_us = currency == "USD"
        t = str(raw_ticker) if is_us else str(raw_ticker).zfill(6)
        if t in seen:
            return
        seen.add(t)
        yf_t = ticker_yf or (t if is_us else f"{t}.KS")
        entries.append((t, yf_t, is_us))

    for holding in portfolio.get("vams", {}).get("holdings", []) or []:
        add_entry(holding.get("ticker"), holding.get("ticker_yf"), holding.get("currency"))
    for stock in portfolio.get("recommendations", []) or []:
        add_entry(stock.get("ticker"), stock.get("ticker_yf"), stock.get("currency"))

    price_map = {}
    for t, yf_t, is_us in entries:
        if not is_us and kis_broker:
            try:
                snap = kis_broker.get_current_price(t)
                p = int(snap.get("stck_prpr", 0) or 0)
                if p > 0:
                    price_map[t] = float(p)
                    continue
            except Exception:
                pass
        p = get_equity_last_price(yf_t)
        if p is not None and p > 0:
            price_map[t] = float(p)
    return price_map


def enrich_with_analysis(candidates: list, macro: dict) -> list:
    """Sprint 2: 각 후보 종목에 기술적/감성/수급/컨센서스/멀티팩터 분석 추가"""
    macro_mood = macro.get("market_mood", {"score": 50, "label": "중립"})
    ex_map = load_trade_export_by_ticker()
    total = len(candidates)

    for i, stock in enumerate(candidates, 1):
        name = stock["name"]
        ticker = stock["ticker"]
        ticker_yf = stock.get("ticker_yf", f"{ticker}.KS")
        print(f"    [{i}/{total}] {name} 분석 중...")

        # 기술적 지표
        tech = analyze_technical(ticker_yf)
        stock["technical"] = tech
        print(f"      기술: {tech['technical_score']}점 | RSI {tech['rsi']} | {', '.join(tech['signals'][:3]) or '시그널 없음'}")

        # 뉴스 감성 (US 종목은 Google News RSS + NewsAPI + 영문 사전)
        stock_market = stock.get("market", "KR")
        sentiment = get_stock_sentiment(name, market=stock_market, ticker=ticker)
        stock["sentiment"] = sentiment
        print(f"      뉴스: {sentiment['score']}점 | 긍정 {sentiment['positive']} / 부정 {sentiment['negative']} ({sentiment['headline_count']}건)")

        # 수급 (외국인/기관) — US 종목은 Finnhub+Polygon 기반 수급 합성
        is_us = stock.get("currency") == "USD"
        if is_us:
            flow = compute_us_flow(stock)
        else:
            flow = get_investor_flow(ticker)
        stock["flow"] = flow
        print(f"      수급: {flow['flow_score']}점 | {', '.join(flow.get('flow_signals', [])[:2]) or '중립'}")

        raw_c = scout_consensus(ticker)
        time.sleep(0.1)
        price_c = float(stock.get("price") or 0)
        cblock = build_consensus_block(
            raw_c, price_c, flow, ex_map.get(str(ticker).zfill(6))
        )
        stock["consensus"] = cblock
        fund_c = merge_fundamental_with_consensus(stock.get("safety_score", 50), cblock)

        # 멀티팩터 통합 점수
        mf = compute_multi_factor_score(
            fundamental_score=fund_c,
            technical=tech,
            sentiment=sentiment,
            flow=flow,
            macro_mood=macro_mood,
            quant_factors=stock.get("quant_factors"),
            social_sentiment=stock.get("social_sentiment"),
        )
        stock["multi_factor"] = mf
        cs_note = f"컨센서스 {cblock.get('consensus_score', 50)}점 ({cblock.get('score_source', '?')})"
        print(f"      종합: {mf['multi_score']}점 ({mf['grade']}) | {cs_note} | 시그널: {', '.join(mf['all_signals'][:3]) or '없음'}")

    return candidates


def _is_us_market_hours(kst_hour: int, kst_minute: int) -> bool:
    """US 정규장 시간 (EST 9:30-16:00 → KST 23:30-06:00, 서머타임 시 22:30-05:00).
    보수적으로 KST 22:30~06:00 범위를 커버."""
    if kst_hour >= 23 or kst_hour < 6:
        return True
    if kst_hour == 22 and kst_minute >= 30:
        return True
    return False


def _is_us_market_close(kst_hour: int, kst_minute: int) -> bool:
    """US 장 마감 직후 (KST 06:00~07:00)"""
    return kst_hour == 6 or (kst_hour == 7 and kst_minute == 0)


def get_analysis_mode() -> str:
    """
    GitHub Actions 크론 + 시각 기반 모드 자동 결정
    - realtime (KST 9:00~15:29):  KR 장중 가격/환율/지수/수급/뉴스 (~1분)
    - full (KST 15:30~16:14):     KR 장 마감 + Gemini/재무/백테스트 (~7분)
    - realtime_us (KST 22:30~06:00): US 장중 가격/지수/뉴스 (~1분)
    - full_us (KST 06:00~07:00):  US 장 마감 + Gemini/재무/백테스트 (~7분)
    - quick (그 외 전체):         + 기술적/멀티팩터/XGBoost (~3분)
    - periodic_daily / periodic_weekly / periodic_monthly / periodic_quarterly
      / periodic_semi / periodic_annual: 정기 리포트 전용
    """
    mode = os.environ.get("ANALYSIS_MODE", "").lower()
    if mode in ("full", "quick", "realtime", "realtime_us", "full_us",
                "periodic_weekly", "periodic_monthly", "periodic_quarterly",
                "periodic_daily", "periodic_semi", "periodic_annual"):
        return mode
    now = now_kst()
    hour, minute = now.hour, now.minute
    # KR 장 마감 full
    if (hour == 15 and minute >= 30) or hour == 16:
        return "full"
    # KR 장중
    if 9 <= hour <= 15:
        return "realtime"
    # US 장 마감 full
    if _is_us_market_close(hour, minute):
        return "full_us"
    # US 장중
    if _is_us_market_hours(hour, minute):
        return "realtime_us"
    return "quick"


def _run_periodic_report(period: str):
    """정기 리포트 생성 + 성장 트리거 파이프라인."""
    from api.config import (
        GROWTH_TRIGGER_PERIODS,
        GROWTH_MIN_SNAPSHOTS,
        STRATEGY_EVOLUTION_ENABLED,
        compute_period_end,
    )

    period_map = {
        "periodic_daily": "daily",
        "periodic_weekly": "weekly",
        "periodic_monthly": "monthly",
        "periodic_quarterly": "quarterly",
        "periodic_semi": "semi",
        "periodic_annual": "annual",
    }
    p = period_map.get(period, "weekly")
    label = {
        "daily": "일일", "weekly": "주간", "monthly": "월간",
        "quarterly": "분기", "semi": "반기", "annual": "연간",
    }.get(p, p)

    print(f"\n{'=' * 60}")
    print(f"  VERITY — {label} 정기 리포트 생성")
    print(f"  실행 시각: {now_kst().strftime('%Y-%m-%d %H:%M:%S KST')}")
    print(f"{'=' * 60}")

    print(f"\n[1] {label} 데이터 수집 및 분석")
    analysis = generate_periodic_analysis(p)
    if analysis.get("status") == "no_data":
        print(f"  ⚠️ {analysis['message']}")
        return

    print(f"  기간: {analysis['date_range']['start']} ~ {analysis['date_range']['end']} ({analysis['days_available']}일)")
    recs = analysis.get("recommendations", {})
    print(f"  추천 성과: {recs.get('total_buy_recs', 0)}건 BUY → 적중률 {recs.get('hit_rate_pct', 0)}% / 평균 {recs.get('avg_return_pct', 0)}%")
    sectors = analysis.get("sectors", {})
    top3 = [s["name"] for s in sectors.get("top3_sectors", [])]
    print(f"  TOP 섹터: {', '.join(top3) or '없음'}")
    meta = analysis.get("meta_analysis", {})
    print(f"  메타 분석: {meta.get('best_predictor', '데이터 부족')}")

    print(f"\n[2] Gemini AI {label} 리포트 작성")
    report = generate_periodic_report(analysis)
    print(f"  제목: {report.get('title', '?')}")
    print(f"  요약: {report.get('executive_summary', '?')[:80]}")

    portfolio = load_portfolio()

    report_key = f"{p}_report"
    portfolio[report_key] = report
    portfolio[f"{report_key}_updated"] = now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00")

    # ── 분기 전용: 13F 기관 수집 + Perplexity 딥리서치 ──
    if p == "quarterly":
        try:
            from api.collectors.sec_13f_collector import collect_all_13f, compute_institutional_signal
            print(f"\n[2.5] 13F 기관 투자자 포지션 수집")
            f13_data = collect_all_13f()
            inst_signal = compute_institutional_signal()
            portfolio["institutional_13f"] = {
                "institutions_collected": len(f13_data),
                "updated_at": now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
                "signal": inst_signal if inst_signal.get("ok") else {},
            }
            consensus = inst_signal.get("smart_money_consensus", [])[:5]
            print(f"  13F 수집 완료: {len(f13_data)}개 기관 | 시그널 TOP: {[c.get('issuer', '?') for c in consensus]}")
        except Exception as e:
            print(f"  13F 수집 스킵: {e}")

        try:
            from api.intelligence.quarterly_research import run_quarterly_research, apply_patch, mark_patch_applied
            print(f"\n[2.6] Perplexity 분기 딥리서치")
            macro_data = portfolio.get("macro", {})
            market_ctx = {
                "economic_quadrant": macro_data.get("economic_quadrant"),
                "fear_greed_score":  macro_data.get("fear_greed_score"),
                "vix":               macro_data.get("vix"),
                "fed_rate":          macro_data.get("fed_funds_rate"),
                "us_10y_yield":      macro_data.get("us_10y_yield"),
            }
            research = run_quarterly_research(market_context=market_ctx)
            if research.get("status") == "success":
                portfolio["quarterly_research"] = research
                portfolio["_quarterly_research_done"] = True
                print(f"  분기 리서치 완료: {research.get('quarter')} | 비용 ${research.get('token_cost_usd', 0)}")

                patch = research.get("constitution_patch_proposal")
                if patch:
                    from api.predictors.backtester import backtest_brain_strategy
                    bt_before = backtest_brain_strategy(override=None, lookback_days=30)
                    bt_after = backtest_brain_strategy(override=patch, lookback_days=30)

                    sharpe_ok = bt_after.get("sharpe", 0) > bt_before.get("sharpe", 0)
                    mdd_ok = bt_after.get("max_drawdown", 999) <= bt_before.get("max_drawdown", 0) * 1.2 or bt_before.get("max_drawdown", 0) == 0

                    from api.intelligence.strategy_evolver import _load_registry
                    registry = _load_registry()
                    auto_approve = registry.get("auto_approve", False)

                    if sharpe_ok and mdd_ok and auto_approve:
                        apply_patch(patch)
                        if research.get("archive_path"):
                            mark_patch_applied(research["archive_path"])
                        print(f"  Constitution 패치 자동 적용 (Sharpe {bt_before.get('sharpe',0):.2f}→{bt_after.get('sharpe',0):.2f})")
                    else:
                        print(f"  Constitution 패치 제안 있음 → /approve_strategy quarterly")
                        patch_summary = ", ".join(list(patch.keys())[:5])
                        try:
                            from api.notifications.telegram import send_message
                            send_message(
                                f"📋 분기 리서치 패치 제안 ({research.get('quarter', '?')})\n"
                                f"변경 키: {patch_summary}\n"
                                f"Sharpe: {bt_before.get('sharpe',0):.2f} → {bt_after.get('sharpe',0):.2f}\n"
                                f"MDD: {bt_before.get('max_drawdown',0):.2f} → {bt_after.get('max_drawdown',0):.2f}\n"
                                f"{'✅ 백테스트 통과' if sharpe_ok and mdd_ok else '⚠️ 백테스트 미통과'}\n\n"
                                f"/approve_strategy quarterly 로 승인"
                            )
                        except Exception:
                            pass
                else:
                    print(f"  Constitution 패치 제안 없음")
            else:
                print(f"  분기 리서치 스킵: {research.get('status')}")
        except Exception as e:
            print(f"  분기 리서치 스킵: {e}")

    save_portfolio(portfolio)

    print(f"\n✅ {label} 정기 리포트 생성 완료 → portfolio.json['{report_key}']")

    # ── 성장 트리거: 리포트 기반 진화 사이클 ──
    if p in GROWTH_TRIGGER_PERIODS and STRATEGY_EVOLUTION_ENABLED and ANTHROPIC_API_KEY:
        period_end_key = compute_period_end(p)
        print(f"\n[3] Brain 성장 트리거 ({label}, period_end={period_end_key})")
        _run_growth_trigger(portfolio, p, period_end_key, analysis)

        save_portfolio(portfolio)


def _run_growth_trigger(
    portfolio: dict,
    period: str,
    period_end_key: str,
    analysis: dict,
):
    """정기 리포트 완료 후 Brain 성장 트리거를 실행한다.

    1) registry에서 동일 기간 중복 여부 확인 (idempotent)
    2) 최소 스냅샷 수 가드레일
    3) run_evolution_cycle 호출
    4) 실행 이력을 registry에 기록
    """
    from api.config import GROWTH_MIN_SNAPSHOTS
    from api.intelligence.strategy_evolver import (
        run_evolution_cycle,
        _load_registry,
        _save_registry,
    )

    label = {
        "daily": "일일", "weekly": "주간", "monthly": "월간",
        "quarterly": "분기", "semi": "반기", "annual": "연간",
    }.get(period, period)

    registry = _load_registry()

    # 중복 실행 방지
    growth_runs = registry.setdefault("growth_runs", {})
    period_runs = growth_runs.setdefault(period, {})
    if period_runs.get(period_end_key):
        print(f"  ⏭️ 이미 실행됨: {period}/{period_end_key} — 건너뜀")
        return

    # 최소 스냅샷 가드레일
    min_snaps = GROWTH_MIN_SNAPSHOTS.get(period, 1)
    available = analysis.get("days_available", 0)
    if available < min_snaps:
        print(f"  ⚠️ 스냅샷 부족: {available}일 < 최소 {min_snaps}일 — 건너뜀")
        return

    # 분기 이상 주기에서 Perplexity 딥리서치 선행 실행 (periodic_quarterly에서 이미 실행했으면 스킵)
    if period in ("quarterly", "semi", "annual") and not portfolio.get("_quarterly_research_done"):
        try:
            from api.intelligence.quarterly_research import run_quarterly_research
            from api.config import PERPLEXITY_API_KEY as _pplx_key
            if _pplx_key:
                print(f"  [Research] Perplexity 분기 딥리서치 실행...")
                macro_data = portfolio.get("macro", {})
                market_ctx = {
                    "economic_quadrant": macro_data.get("economic_quadrant"),
                    "fear_greed_score":  macro_data.get("fear_greed_score"),
                    "vix":               macro_data.get("vix"),
                    "fed_rate":          macro_data.get("fed_funds_rate"),
                    "us_10y_yield":      macro_data.get("us_10y_yield"),
                }
                research = run_quarterly_research(market_context=market_ctx)
                if research.get("status") == "success":
                    portfolio["quarterly_research"] = research
        except Exception as e:
            print(f"  [Research] 리서치 스킵: {e}")
    elif portfolio.get("_quarterly_research_done"):
        print(f"  [Research] 이미 실행됨 — 이중 호출 스킵")

    print(f"  성장 트리거 실행 (컨텍스트: {label})")
    try:
        result = run_evolution_cycle(
            portfolio,
            trigger_context={
                "period": period,
                "period_end": period_end_key,
                "days_available": available,
                "hit_rate_pct": analysis.get("recommendations", {}).get("hit_rate_pct", 0),
                "brain_accuracy": analysis.get("brain_accuracy", {}),
            },
        )
        portfolio["strategy_evolution"] = result
        status = result.get("status", "?")
        print(f"  결과: {status}")
        if status == "pending_approval":
            print(f"  → 텔레그램 승인 대기 중")
        elif status == "auto_applied":
            print(f"  → 자동 적용 완료 (v{result.get('new_version', '?')})")
        elif status == "no_change":
            print(f"  → Claude: 현행 유지 ({result.get('reason', '')[:60]})")

        # 실행 이력 기록
        period_runs[period_end_key] = {
            "status": status,
            "executed_at": now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        }
        _save_registry(registry)

    except Exception as e:
        print(f"  성장 트리거 실패: {e}")
        period_runs[period_end_key] = {
            "status": "error",
            "error": str(e)[:200],
            "executed_at": now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        }
        _save_registry(registry)


def _load_previous_analysis() -> list:
    """이전 실행의 recommendations를 캐시로 로드"""
    portfolio_path = os.path.join(DATA_DIR, "portfolio.json")
    if os.path.exists(portfolio_path):
        try:
            with open(portfolio_path, "r", encoding="utf-8") as f:
                txt = f.read().replace("NaN", "null")
                data = json.loads(txt)
            return data.get("recommendations", [])
        except Exception:
            pass
    return []


def _apply_fallback_judgments(analyzed: list):
    """Gemini 미실행/실패 시 멀티팩터 기반 자동 판단"""
    for stock in analyzed:
        mf = stock.get("multi_factor", {})
        ms = mf.get("multi_score", 0)
        if "recommendation" not in stock or "오류" in stock.get("ai_verdict", ""):
            if ms >= 65:
                stock["recommendation"] = "BUY"
                stock["ai_verdict"] = f"멀티팩터 {ms}점 ({mf.get('grade', '')}) — 기술적·펀더멘털·수급 양호"
            elif ms >= 45:
                stock["recommendation"] = "WATCH"
                stock["ai_verdict"] = f"멀티팩터 {ms}점 ({mf.get('grade', '')}) — 관찰 필요"
            else:
                stock["recommendation"] = "AVOID"
                stock["ai_verdict"] = f"멀티팩터 {ms}점 ({mf.get('grade', '')}) — 리스크 주의"
            stock.setdefault("confidence", ms)
            stock.setdefault("risk_flags", [])
            stock.setdefault("company_tagline", "")

            tech = stock.get("technical", {})
            sent = stock.get("sentiment", {})
            flow = stock.get("flow", {})

            gold_parts = []
            if tech.get("rsi", 50) <= 35:
                gold_parts.append(f"RSI {tech['rsi']}로 과매도 구간")
            if stock.get("per", 0) and 3 < stock["per"] < 15:
                gold_parts.append(f"PER {stock['per']}배 저평가")
            if stock.get("drop_from_high_pct", 0) <= -25:
                gold_parts.append(f"고점 대비 {stock['drop_from_high_pct']}% 하락")
            stock.setdefault("gold_insight", " | ".join(gold_parts) if gold_parts else "펀더멘털 양호")

            silver_parts = []
            if sent.get("score", 50) >= 60:
                silver_parts.append(f"뉴스 긍정 {sent['score']}점")
            elif sent.get("score", 50) <= 40:
                silver_parts.append(f"뉴스 부정 {sent['score']}점")
            if flow.get("flow_signals"):
                silver_parts.extend(flow["flow_signals"][:2])
            stock.setdefault("silver_insight", " | ".join(silver_parts) if silver_parts else "수급 중립")
            stock.setdefault("detected_risk_keywords", [])


def _update_simulation_stats(portfolio: dict):
    """VAMS 매매 이력으로부터 누적 시뮬레이션 통계 갱신."""
    from api.vams.engine import load_history, VAMS_INITIAL_CASH
    history = load_history()
    vams = portfolio.get("vams", {})

    sells = [h for h in history if h.get("type") == "SELL"]
    total_trades = len(sells)
    wins = sum(1 for s in sells if s.get("pnl", 0) > 0)
    win_rate = round(wins / total_trades * 100, 1) if total_trades else 0
    realized_pnl = sum(s.get("pnl", 0) for s in sells)

    best_trade = max(sells, key=lambda s: s.get("pnl", 0)) if sells else None
    worst_trade = min(sells, key=lambda s: s.get("pnl", 0)) if sells else None

    prev_stats = vams.get("simulation_stats", {})
    peak_asset = max(
        vams.get("total_asset", VAMS_INITIAL_CASH),
        prev_stats.get("peak_asset", VAMS_INITIAL_CASH),
    )
    current_asset = vams.get("total_asset", VAMS_INITIAL_CASH)
    max_dd = round((current_asset - peak_asset) / peak_asset * 100, 2) if peak_asset > 0 else 0
    prev_dd = prev_stats.get("max_drawdown_pct", 0)
    max_dd = min(max_dd, prev_dd) if prev_dd < 0 else max_dd

    vams["simulation_stats"] = {
        "total_trades": total_trades,
        "win_count": wins,
        "loss_count": total_trades - wins,
        "win_rate": win_rate,
        "realized_pnl": realized_pnl,
        "peak_asset": peak_asset,
        "max_drawdown_pct": max_dd,
        "best_trade": {
            "name": best_trade.get("name", "?"),
            "pnl": best_trade.get("pnl", 0),
            "date": best_trade.get("date", ""),
        } if best_trade else None,
        "worst_trade": {
            "name": worst_trade.get("name", "?"),
            "pnl": worst_trade.get("pnl", 0),
            "date": worst_trade.get("date", ""),
        } if worst_trade else None,
        "updated_at": now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
    }
    portfolio["vams"] = vams


def _resolve_dual_model_weights(portfolio: dict) -> dict:
    """직전 리더보드 성과를 바탕으로 Gemini/Claude 가중치 산출."""
    base = {"gemini": 0.55, "claude": 0.45}
    lb = portfolio.get("ai_leaderboard") or {}
    rows = lb.get("by_source") or []
    if not rows:
        return base

    gemini_rate = None
    claude_rate = None
    for r in rows:
        src = str(r.get("source", "")).lower()
        try:
            hit_rate = float(r.get("hit_rate", 0))
        except (TypeError, ValueError):
            continue
        if src == "gemini":
            gemini_rate = hit_rate
        elif src == "claude":
            claude_rate = hit_rate

    if gemini_rate is None or claude_rate is None:
        return base

    # 최소 0.35, 최대 0.65 범위에서 완만하게 조정
    delta = max(-10.0, min(10.0, claude_rate - gemini_rate))
    claude_w = 0.45 + (delta / 50.0)
    claude_w = max(0.35, min(0.65, claude_w))
    gemini_w = 1.0 - claude_w
    return {"gemini": round(gemini_w, 3), "claude": round(claude_w, 3)}


def main():
    mode = get_analysis_mode()

    if mode.startswith("periodic_"):
        _run_periodic_report(mode)
        return

    is_us_mode = mode in ("realtime_us", "full_us")
    effective_mode = mode.replace("_us", "") if is_us_mode else mode
    market_scope = "us" if is_us_mode else "all"
    # 실행량 기반 비용 추정용 카운터
    us_data_symbols_count = 0
    us_data_requests_est = 0
    claude_deep_calls = 0
    claude_light_calls = 0
    claude_tokens_used = 0

    MODE_LABELS = {
        "realtime": "실시간 갱신 (가격/환율/수급)",
        "realtime_us": "미장 실시간 갱신 (US 가격/지수/뉴스)",
        "quick": "빠른 분석 (기술적/멀티팩터/예측)",
        "full": "전체 분석 (Gemini/백테스트/텔레그램)",
        "full_us": "미장 전체 분석 (US Gemini/백테스트)",
    }

    print("=" * 60)
    print(f"  VERITY — AI 주식 분석 엔진 {VERSION}")
    print(f"  실행 시각: {now_kst().strftime('%Y-%m-%d %H:%M:%S KST')}")
    print(f"  분석 모드: {MODE_LABELS.get(mode, mode)}")
    print("=" * 60)

    tracer = get_tracer()
    tracer.start(mode)
    tracer.log("verity_version", VERSION)
    tracer.log("effective_mode", effective_mode)
    tracer.log("market_scope", market_scope)

    # ── 런타임 가드: 모드별 최대 실행 시간 초과 시 강제 종료 ──
    _MODE_MAX_SECONDS = {
        "realtime": 10 * 60,
        "realtime_us": 10 * 60,
        "quick": 35 * 60,
        "full": 82 * 60,
        "full_us": 82 * 60,
    }
    _run_limit = _MODE_MAX_SECONDS.get(effective_mode, 82 * 60)
    import threading as _threading, time as _time
    _run_start = _time.monotonic()

    def _runtime_watchdog():
        _threading.Event().wait(_run_limit)
        elapsed = int(_time.monotonic() - _run_start)
        print(f"\n⏱ 런타임 한계 도달 ({elapsed//60}분 {elapsed%60}초) — 프로세스 종료")
        import os as _os
        _os.kill(_os.getpid(), 15)  # SIGTERM → 정상 종료 흐름

    _wd = _threading.Thread(target=_runtime_watchdog, daemon=True)
    _wd.start()

    # ── STEP 0: 시스템 자가진단 ──
    try:
        system_health = run_health_check()
    except Exception as e:
        print(f"  ⚠️ 자가진단 실패: {e}")
        system_health = {"status": "unknown", "errors": [str(e)]}

    # Telegram 타임아웃/실패 알림 콜백
    def _tg_notify(msg: str) -> None:
        try:
            from api.notifications.telegram import send_message
            send_message(f"🔧 파이프라인 경고\n{msg}")
        except Exception:
            pass

    # ── STEP 1: 항상 실행 — 시장 지수 + 매크로 + 보유종목 현재가 ──
    print("\n[1] 시장 지수 + 매크로 지표 수집")
    market_summary = safe_collect(
        get_market_index, name="시장지수", timeout=45, default={}, notify=_tg_notify,
    )
    print(f"  KOSPI: {market_summary.get('kospi', {}).get('value', 'N/A')}")
    print(f"  KOSDAQ: {market_summary.get('kosdaq', {}).get('value', 'N/A')}")
    print(f"  NDX: {market_summary.get('ndx', {}).get('value', 'N/A')} | S&P500: {market_summary.get('sp500', {}).get('value', 'N/A')}")

    macro = safe_collect(
        get_macro_indicators, name="매크로지표", timeout=45, default={}, notify=_tg_notify,
    )
    mood = macro.get("market_mood", {})
    fred = macro.get("fred") or {}
    fred_note = ""
    if fred.get("dgs10"):
        fred_note = f" | FRED DGS10 {fred['dgs10'].get('value')}% ({fred['dgs10'].get('date', '')})"
    print(
        f"  매크로: {mood.get('label', '?')} ({mood.get('score', 0)}점) | "
        f"USD/KRW: {(macro.get('usd_krw') or {}).get('value', '?')} | VIX: {(macro.get('vix') or {}).get('value', '?')}"
        f"{fred_note}"
    )

    tracer.log_collector("market_summary", market_summary)
    tracer.log_collector("macro", macro)
    tracer.log_collector("system_health", system_health)

    # ── Deadman's Switch: 데이터 소스 장애 감지 시 즉시 중단 ──
    should_abort, abort_reasons = validate_deadman_switch(
        system_health, market_summary, macro
    )
    if should_abort:
        print("\n🚨 DEADMAN'S SWITCH 발동 — 분석 중단")
        for r in abort_reasons:
            print(f"  ⛔ {r}")
        send_deadman_alert(abort_reasons)
        # 중단 시에도 비용 모니터/헬스 상태를 저장해 프론트에서 즉시 확인 가능하게 유지
        try:
            portfolio = load_portfolio()
            portfolio["updated_at"] = now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00")
            portfolio["market_summary"] = market_summary
            portfolio["macro"] = macro
            portfolio["system_health"] = system_health
            portfolio["cost_monitor"] = _build_cost_monitor(
                portfolio=portfolio,
                mode=mode,
                effective_mode=effective_mode,
                macro=macro,
                run_stats={
                    "gemini_stock_calls": 0,
                    "gemini_report_calls": 0,
                    "claude_deep_calls": 0,
                    "claude_light_calls": 0,
                    "claude_tokens": 0,
                    "us_data_symbols": 0,
                    "us_data_requests_est": 0,
                },
            )
            save_portfolio(portfolio)
            print("  비용모니터 초기 데이터 저장 완료")
        except Exception as e:
            print(f"  비용모니터 저장 스킵: {e}")
        return

    portfolio = load_portfolio()
    portfolio["updated_at"] = now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00")
    portfolio["market_summary"] = market_summary
    portfolio["macro"] = macro
    portfolio["system_health"] = system_health

    # ── STEP 1.5: KRX OpenAPI — tier별 주기 (US 모드에서는 스킵)
    # full: 전부 갱신 | quick: Macro+Active 병합(Static 유지) | realtime: Active만 병합
    def _slim_krx(snap: dict) -> dict:
        """portfolio.json 저장용: summary + 메타만 유지, 상세 endpoint rows 제거."""
        return {
            "bas_dd": snap.get("bas_dd"),
            "updated_at": snap.get("updated_at"),
            "summary": snap.get("summary", {}),
            "tier_plan": snap.get("tier_plan"),
            "tier_updated_at": snap.get("tier_updated_at"),
        }

    try:
        if is_us_mode:
            print("\n[1.5] KRX OpenAPI 스킵 (US 모드)")
        elif effective_mode == "full":
            print("\n[1.5] KRX OpenAPI 전체 갱신 (Static+Macro+Active, 18개)")
            krx_snapshot = collect_krx_openapi_snapshot()
            krx_snapshot["tier_plan"] = krx_tier_plan_dict()
            ts = krx_snapshot.get("updated_at") or now_kst().strftime(
                "%Y-%m-%dT%H:%M:%S+09:00"
            )
            krx_snapshot["tier_updated_at"] = {
                "static": ts,
                "macro": ts,
                "active": ts,
            }
            portfolio["krx_openapi"] = _slim_krx(krx_snapshot)
            s = krx_snapshot.get("summary", {})
            print(
                "  KRX 요약: "
                f"정상 {s.get('ok', 0)} | 빈데이터 {s.get('empty', 0)} | "
                f"권한없음 {s.get('forbidden', 0)} | 오류 {s.get('error', 0)}"
            )
        elif mode == "quick":
            print("\n[1.5] KRX OpenAPI — Macro+Active 갱신 (Static 유지, 병합)")
            patch = collect_krx_tiers(("macro", "active"))
            merged_full = merge_krx_openapi_snapshots(
                portfolio.get("krx_openapi"),
                patch,
                ("macro", "active"),
            )
            portfolio["krx_openapi"] = _slim_krx(merged_full)
            merged = merged_full.get("summary", {})
            ps = patch.get("summary", {})
            print(
                "  KRX 이번(Macro+Active): "
                f"정상 {ps.get('ok', 0)} | 빈데이터 {ps.get('empty', 0)} | "
                f"권한없음 {ps.get('forbidden', 0)} | 오류 {ps.get('error', 0)}"
            )
            print(
                "  KRX 병합 누적: "
                f"{merged.get('total', 0)}개 엔드포인트 | "
                f"정상 {merged.get('ok', 0)} | 빈데이터 {merged.get('empty', 0)} | "
                f"권한없음 {merged.get('forbidden', 0)} | 오류 {merged.get('error', 0)}"
            )
        elif mode == "realtime":
            print("\n[1.5] KRX OpenAPI — Active만 갱신 (병합)")
            patch = collect_krx_tiers(("active",))
            merged_full = merge_krx_openapi_snapshots(
                portfolio.get("krx_openapi"),
                patch,
                ("active",),
            )
            portfolio["krx_openapi"] = _slim_krx(merged_full)
            merged = merged_full.get("summary", {})
            ps = patch.get("summary", {})
            print(
                "  KRX 이번(Active): "
                f"정상 {ps.get('ok', 0)} | 빈데이터 {ps.get('empty', 0)} | "
                f"권한없음 {ps.get('forbidden', 0)} | 오류 {ps.get('error', 0)}"
            )
            print(
                "  KRX 병합 누적: "
                f"{merged.get('total', 0)}개 엔드포인트 | "
                f"정상 {merged.get('ok', 0)} | 빈데이터 {merged.get('empty', 0)} | "
                f"권한없음 {merged.get('forbidden', 0)} | 오류 {merged.get('error', 0)}"
            )
        else:
            portfolio.setdefault("krx_openapi", {})
    except Exception as e:
        print(f"  KRX 스냅샷 실패: {e}")
        portfolio.setdefault("krx_openapi", {})

    # ── STEP 1.52: 프로그램 매매 + 만기일 캘린더 ────────────────────
    if not is_us_mode:
        print("\n[1.52] 프로그램 매매동향 + 만기일 상태")
        try:
            prog = get_program_trading_today()
            portfolio["program_trading"] = prog
            sig = prog.get("signal", "?")
            total = prog.get("total_net_bn", 0)
            print(f"  프로그램: {sig} | 순매수 {total:+,.0f}억 (차익 {prog.get('arb_net_bn', 0):+,.0f} / 비차익 {prog.get('non_arb_net_bn', 0):+,.0f})")
            if prog.get("sell_bomb"):
                print(f"  🚨 매도 폭탄 감지: {prog.get('sell_bomb_reason', '')}")
        except Exception as e:
            print(f"  프로그램 매매 수집 실패: {e}")
            portfolio.setdefault("program_trading", {})

        try:
            expiry = get_expiry_status()
            portfolio["expiry_status"] = expiry
            wl = expiry.get("watch_level", "?")
            print(f"  만기일: {wl} | KR옵션 D-{expiry.get('days_to_kr_option', '?')} / KR선물 D-{expiry.get('days_to_kr_futures', '?')} / US쿼드 D-{expiry.get('days_to_us_quad', '?')}")
            if wl != "NORMAL":
                print(f"  ⚠️ 관망 사유: {expiry.get('reason', '')}")
        except Exception as e:
            print(f"  만기일 캘린더 실패: {e}")
            portfolio.setdefault("expiry_status", {})

    # ── STEP 1.55: 채권·ETF 수집 (quick/full만) ──────────────────────
    if effective_mode in ("quick", "full"):
        print(f"\n[1.55] 채권·ETF 데이터 수집 (모드: {effective_mode})")
        bonds_data = safe_collect(
            get_full_yield_curve_data,
            name="채권수익률곡선", timeout=45, default={}, notify=_tg_notify,
        )
        if bonds_data:
            portfolio["bonds"] = bonds_data
            try:
                from api.analyzers.bondanalyzer import run_bond_analysis
                bond_analysis = run_bond_analysis(bonds_data)
                portfolio["bond_analysis"] = bond_analysis
                regime = bond_analysis.get("bond_regime", {})
                if regime:
                    portfolio["bonds"]["bond_regime"] = regime
                    print(f"  bond_regime 동기화: curve={regime.get('curve_shape', '?')} recession={regime.get('recession_signal', False)}")
            except Exception as e:
                print(f"  bond_regime 분석 실패(무시): {e}")
        else:
            portfolio.setdefault("bonds", {})
        if bonds_data:
            yc = bonds_data.get("yield_curves", {})
            n_alerts = len(bonds_data.get("inversion_alerts", []))
            kr_shape = yc.get("kr", {}).get("curve_shape", "-")
            us_shape = yc.get("us", {}).get("curve_shape", "-")
            print(f"  수익률 곡선: KR={kr_shape} / US={us_shape} | 역전 경보: {n_alerts}건")

        kr_etfs = safe_collect(get_top_etf_summary, name="KR ETF", timeout=30, default=[], notify=_tg_notify)
        us_etfs = safe_collect(get_us_etf_summary, name="US ETF", timeout=30, default=[], notify=_tg_notify)
        bond_etfs = safe_collect(get_bond_etf_summary, name="채권ETF", timeout=30, default=[], notify=_tg_notify)
        if kr_etfs or us_etfs or bond_etfs:
            all_etfs = sorted(
                [*kr_etfs, *us_etfs, *bond_etfs],
                key=lambda e: abs(e.get("return_1m", 0) or 0),
                reverse=True,
            )
            portfolio["etfs"] = {
                "kr_top": kr_etfs,
                "us_top": us_etfs,
                "us_bond": bond_etfs,
                "overall_top20": all_etfs[:20],
                "updated_at": now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
            }
            print(f"  ETF 수집: KR {len(kr_etfs)}개 / US {len(us_etfs)}개 / 채권ETF {len(bond_etfs)}개 | TOP20 생성")
        else:
            portfolio.setdefault("etfs", {})
    else:
        portfolio.setdefault("bonds", {})
        portfolio.setdefault("etfs", {})

    # ── STEP 1.6: KIS Open API — 실시간 시세·호가·차트 (US 모드 스킵) ──
    kis = None
    if KIS_ENABLED and not is_us_mode:
        print("\n[1.6] 한국투자증권 Open API 연동")
        try:
            kis = _get_kis_broker()
            if kis:
                print(f"  KIS 인증 완료 ({'모의투자' if kis.is_paper else '실전'})")
                kr_tickers = []
                for s in (portfolio.get("recommendations") or []):
                    if s.get("currency") != "USD":
                        kr_tickers.append(str(s.get("ticker", "")).zfill(6))
                for h in (portfolio.get("vams", {}).get("holdings") or []):
                    if h.get("currency") != "USD":
                        kr_tickers.append(str(h.get("ticker", "")).zfill(6))
                kr_tickers = list(dict.fromkeys(kr_tickers))[:30]

                kis_snapshots = {}
                ok_count = 0
                brain_ok = 0
                kis_sleep = 0.1 if kis.is_paper else 0.35
                for tk in kr_tickers:
                    snap = {}
                    price_snap = kis.build_price_snapshot(tk)
                    if price_snap:
                        snap["price"] = price_snap
                    time.sleep(kis_sleep)
                    ob_snap = kis.build_orderbook_snapshot(tk)
                    if ob_snap:
                        snap["orderbook"] = ob_snap
                    time.sleep(kis_sleep)
                    ccl_snap = kis.build_conclusion_snapshot(tk, top_n=20)
                    if ccl_snap:
                        snap["conclusion"] = ccl_snap
                    time.sleep(kis_sleep)
                    if effective_mode in ("full", "quick"):
                        chart_snap = kis.build_chart_data(tk, days=90)
                        if chart_snap:
                            snap["chart"] = chart_snap
                        time.sleep(kis_sleep)
                        try:
                            brain_snap = kis.build_brain_snapshot(tk)
                            if brain_snap:
                                snap["brain"] = brain_snap
                                brain_ok += 1
                        except Exception as e_br:
                            print(f"    KIS Brain({tk}) 수집 실패: {e_br}")
                        time.sleep(kis_sleep)
                    if snap:
                        kis_snapshots[tk] = snap
                        ok_count += 1

                portfolio["kis_snapshots"] = kis_snapshots
                print(f"  KIS 시세·호가·체결 {ok_count}/{len(kr_tickers)}개 수집 완료")
                if brain_ok:
                    print(f"  KIS Brain 데이터 {brain_ok}개 (투자자/공매도/신용/투자의견 등)")
                system_health.setdefault("apis", {})["kis_openapi"] = {
                    "status": "ok", "count": ok_count, "total": len(kr_tickers)
                }
            else:
                print("  KIS 미설정 또는 인증 실패 — 기존 소스 유지")
                portfolio.setdefault("kis_snapshots", {})
        except Exception as e:
            print(f"  KIS 수집 실패: {e}")
            portfolio.setdefault("kis_snapshots", {})
    else:
        portfolio.setdefault("kis_snapshots", {})

    # ── STEP 1.65: KIS 시장전반 데이터 (순위/업종/VI/뉴스) ──
    if KIS_ENABLED and not is_us_mode:
        print("\n[1.65] KIS 시장전반 데이터 수집")
        try:
            if kis is None:
                kis = _get_kis_broker()
            if kis:
                kis_sleep = 0.1 if kis.is_paper else 0.35
                mkt_overview = kis.build_market_overview()
                portfolio["kis_market"] = mkt_overview
                parts = [k for k in ("kospi", "kosdaq", "volume_rank", "foreign_institution",
                                     "short_sale_rank", "vi_status", "news") if mkt_overview.get(k)]
                print(f"  시장전반: {', '.join(parts)}")
                time.sleep(kis_sleep * 3)
        except Exception as e:
            print(f"  KIS 시장전반 스킵: {e}")
            portfolio.setdefault("kis_market", {})
    else:
        portfolio.setdefault("kis_market", {})

    # ── STEP 1.7: KIS 해외주식 데이터 (US 모드 or 상시) ──
    if KIS_ENABLED:
        print("\n[1.7] KIS 해외주식 시장 데이터 수집")
        try:
            if kis is None:
                kis = _get_kis_broker()
            if kis:
                kis_sleep = 0.1 if kis.is_paper else 0.35
                # KIS 해외 시세 API는 거래소 권한 없이도 조회 가능 (NAS·NYS·HKS·SHS·SZS·TSE)
                overseas_exchanges = ["NAS", "NYS", "HKS", "TSE", "SHS", "SZS"]
                os_overview = kis.build_overseas_market_overview(overseas_exchanges)
                portfolio["kis_overseas_market"] = os_overview
                excd_names = {
                    "NAS": "나스닥", "NYS": "뉴욕", "AMS": "아멕스",
                    "HKS": "홍콩", "TSE": "도쿄", "SHS": "상해", "SZS": "심천",
                }
                for excd in overseas_exchanges:
                    mkt_data = os_overview.get(excd, {})
                    cnt = sum(1 for k in mkt_data if mkt_data.get(k))
                    if cnt:
                        print(f"  {excd_names.get(excd, excd)}: {cnt}개 카테고리")
                time.sleep(kis_sleep * 3)

                if is_us_mode:
                    us_tickers = []
                    for s in (portfolio.get("recommendations") or []):
                        if s.get("currency") == "USD":
                            us_tickers.append((s.get("ticker", ""), "NAS"))
                    for h in (portfolio.get("vams", {}).get("holdings") or []):
                        if h.get("currency") == "USD":
                            us_tickers.append((h.get("ticker", ""), "NAS"))
                    us_tickers = list(dict.fromkeys(us_tickers))[:30]
                    kis_us_snapshots = {}
                    us_ok = 0
                    for tk, excd in us_tickers:
                        try:
                            snap = kis.build_overseas_brain_snapshot(excd, tk)
                            if snap:
                                kis_us_snapshots[tk] = snap
                                us_ok += 1
                        except Exception:
                            pass
                        time.sleep(kis_sleep)
                    portfolio["kis_us_snapshots"] = kis_us_snapshots
                    if us_ok:
                        print(f"  US 종목 KIS 시세: {us_ok}/{len(us_tickers)}개")
                else:
                    portfolio.setdefault("kis_us_snapshots", {})
        except Exception as e:
            print(f"  KIS 해외 스킵: {e}")
            portfolio.setdefault("kis_overseas_market", {})
            portfolio.setdefault("kis_us_snapshots", {})
    else:
        portfolio.setdefault("kis_overseas_market", {})
        portfolio.setdefault("kis_us_snapshots", {})

    # 뉴스 + 섹터 수집 (모든 모드에서 실행)
    print("\n[2] 헤드라인 뉴스 + 섹터 수집")
    headlines = safe_collect(
        collect_headlines, max_items=20,
        name="헤드라인", timeout=30, default=[], notify=_tg_notify,
    )
    portfolio["headlines"] = headlines
    if headlines:
        print(f"  뉴스 {len(headlines)}건")

    bb_rss = safe_collect(
        collect_bloomberg_google_news_rss, max_items=15,
        name="Bloomberg RSS", timeout=30, default=[], notify=_tg_notify,
    )
    portfolio["bloomberg_google_headlines"] = bb_rss
    if bb_rss:
        print(f"  Bloomberg(Google News RSS) {len(bb_rss)}건")

    us_hl = safe_collect(
        collect_us_headlines,
        kr_headlines=portfolio.get("headlines", []),
        bloomberg_rss=portfolio.get("bloomberg_google_headlines", []),
        max_items=20,
        name="US헤드라인", timeout=30, default=[], notify=_tg_notify,
    )
    portfolio["us_headlines"] = us_hl
    if us_hl:
        print(f"  US 헤드라인 {len(us_hl)}건 (혼합)")

    try:
        prev_sectors = portfolio.get("sectors", [])
        if is_us_mode:
            from api.collectors.us_sector import get_us_sector_rankings
            new_sectors = get_us_sector_rankings()
            kept_sectors = [s for s in prev_sectors if (s.get("market", "") or "").upper() != "US"]
            sectors = kept_sectors + new_sectors
        else:
            new_sectors = get_sector_rankings()
            kept_sectors = [s for s in prev_sectors if (s.get("market", "") or "").upper() == "US"]
            sectors = new_sectors + kept_sectors
        portfolio["sectors"] = sectors
        kr_cnt = len([s for s in sectors if (s.get("market", "") or "").upper() != "US"])
        us_cnt = len([s for s in sectors if (s.get("market", "") or "").upper() == "US"])
        hot = [s["name"] for s in new_sectors[:3]]
        print(f"  섹터 {len(sectors)}개 (KR {kr_cnt} + US {us_cnt}) | HOT: {', '.join(hot)}")
    except Exception as e:
        print(f"  섹터 수집 실패: {e}")
        portfolio.setdefault("sectors", [])

    try:
        rotation = get_sector_rotation(macro, portfolio.get("sectors", []))
        portfolio["sector_rotation"] = rotation
        print(f"  경기 국면: {rotation['cycle_label']} | 추천 {len(rotation['recommended_sectors'])}개 | 회피 {len(rotation['avoid_sectors'])}개")
    except Exception as e:
        print(f"  섹터 로테이션 실패: {e}")
        portfolio.setdefault("sector_rotation", {})

    try:
        sector_trends = compute_sector_trend_summary()
        portfolio["sector_trends"] = sector_trends
        avail = [k for k, v in sector_trends.items() if v is not None]
        print(f"  섹터 추이: {', '.join(avail) if avail else '스냅샷 부족'}")
    except Exception as e:
        print(f"  섹터 추이 스킵: {e}")
        portfolio.setdefault("sector_trends", {})

    # X(트위터) 감성 수집 (모든 모드)
    print("\n[2.3] X(트위터) 시장 감성")
    x_sentiment = safe_collect(
        collect_x_sentiment, max_items=20,
        name="X감성", timeout=45, default={}, notify=_tg_notify,
    )
    portfolio["x_sentiment"] = x_sentiment
    if x_sentiment:
        fig_names = [f["name"] for f in x_sentiment.get("key_figures", [])[:3]]
        print(f"  X 감성: {x_sentiment.get('score', '?')}점 | {x_sentiment.get('tweet_count', 0)}건 | 주요 인물: {', '.join(fig_names) or '없음'}")

    # 글로벌 이벤트 수집 (모든 모드)
    print("\n[2.5] 글로벌 이벤트 캘린더")
    global_events = safe_collect(
        collect_global_events,
        name="글로벌이벤트", timeout=30, default=[], notify=_tg_notify,
    )
    if global_events:
        portfolio["global_events"] = global_events
    else:
        portfolio.setdefault("global_events", [])
    if global_events:
        upcoming = [e for e in global_events if e.get("d_day", 99) <= 3]
        print(f"  이벤트 {len(global_events)}건 | D-3 이내 {len(upcoming)}건")

    # ── STEP 2.5b: 대만 지진 트리거 (모든 모드, 15분 주기 감시) ──
    # 평상시 무음. M6.0+ 발생시에만 global_events에 critical 추가 + 텔레그램 긴급 알림.
    # TSMC 단일 의존성 기반 반도체 공급망 충격 → 2330.TW/005930.KS/000660.KS/NVDA/AAPL 동시 영향
    print("\n[2.5b] 대만 지진 트리거 감시")
    try:
        quake_events = check_taiwan_quake_trigger()
        if quake_events:
            portfolio.setdefault("global_events", []).extend(quake_events)
            for qe in quake_events:
                mag = qe.get("meta", {}).get("magnitude", 0)
                print(f"  🚨 M{mag:.1f} 감지 → global_events 추가 + 긴급 알림 발송")
                try:
                    from api.notifications.telegram import send_message
                    send_message(format_alert_message(qe))
                except Exception as _e:
                    print(f"  ⚠️ 텔레그램 알림 실패: {_e}")
        else:
            print("  정상 (대만 인근 M6.0+ 지진 없음)")
    except Exception as e:
        print(f"  ⚠️ 대만 지진 트리거 체크 실패: {e}")

    # ── STEP 2.6: 임박 고영향 이벤트 Perplexity 해석 (full만) ──
    perplexity_call_count = 0
    if effective_mode == "full" and PERPLEXITY_API_KEY and global_events:
        imminent = [
            e for e in global_events
            if e.get("severity") in ("high", "critical") and e.get("d_day", 99) <= 1
        ]
        if imminent:
            print(f"\n[2.6] Perplexity 매크로 이벤트 리서치 ({len(imminent)}건)")
            try:
                from api.intelligence.perplexity_realtime import research_macro_events
                event_insights = research_macro_events(imminent)
                portfolio["event_insights"] = event_insights
                ok = sum(1 for ei in event_insights if "error" not in ei)
                print(f"  완료: {ok}/{len(event_insights)} 성공")
            except Exception as e:
                print(f"  ⚠️ 매크로 이벤트 리서치 스킵: {e}")

    # ── STEP 2.7: 크립토 매크로 센서 (모든 모드) ──
    if CRYPTO_MACRO_ENABLED:
        print("\n[2.7] 크립토 매크로 센서")
        crypto_macro = safe_collect(
            collect_crypto_macro,
            name="크립토매크로", timeout=45, default={"available": False}, notify=_tg_notify,
        )
        portfolio["crypto_macro"] = crypto_macro
        if crypto_macro.get("composite"):
            comp = crypto_macro["composite"]
            fng = crypto_macro.get("fear_and_greed", {})
            funding = crypto_macro.get("funding_rate", {})
            kimchi = crypto_macro.get("kimchi_premium", {})
            corr = crypto_macro.get("btc_nasdaq_corr", {})
            stable = crypto_macro.get("stablecoin_mcap", {})
            parts = []
            if fng.get("ok"):
                parts.append(f"F&G {fng['value']}({fng['label']})")
            if funding.get("ok"):
                parts.append(f"펀딩비 {funding['rate_pct']:+.4f}%")
            if kimchi.get("ok"):
                parts.append(f"김프 {kimchi['premium_pct']:+.1f}%")
            if corr.get("ok"):
                parts.append(f"BTC-NQ상관 {corr['correlation']:.2f}")
            if stable.get("ok"):
                parts.append(f"스테이블 ${stable['total_mcap_b']:.0f}B")
            print(f"  {' | '.join(parts) or '수집 실패'}")
            print(f"  종합: {comp.get('score', '?')}점 ({comp.get('label', '?')}) | {crypto_macro.get('ok_count', 0)}/{crypto_macro.get('total', 0)}개 성공")
            if comp.get("signals"):
                for sig in comp["signals"]:
                    print(f"    → {sig}")
    else:
        portfolio.setdefault("crypto_macro", {"available": False})

    # ── STEP 2.8: CNN Fear & Greed Index (모든 모드) ──
    from api.config import MARKET_FNG_ENABLED
    if MARKET_FNG_ENABLED:
        print("\n[2.8] CNN Fear & Greed Index (주식시장)")
        market_fng = safe_collect(
            collect_market_fear_greed,
            name="시장F&G", timeout=20, default={"ok": False}, notify=_tg_notify,
        )
        portfolio["market_fear_greed"] = market_fng
        if market_fng.get("ok"):
            v = market_fng["value"]
            desc = market_fng.get("description_kr", "")
            sig = market_fng.get("signal", "")
            chg = market_fng.get("change_1d")
            chg_str = f" ({chg:+.0f})" if chg is not None else ""
            print(f"  F&G {v}{chg_str} — {desc} | 시그널: {sig}")
            sub = market_fng.get("sub_indicators", {})
            if sub:
                parts = [f"{k.replace('_', ' ').title()}: {v_s.get('score', '?')}"
                         for k, v_s in sub.items() if isinstance(v_s, dict)]
                if parts:
                    print(f"  하위지표: {' | '.join(parts[:4])}")
        else:
            print(f"  ⚠️ 수집 실패: {market_fng.get('error', 'unknown')}")
    else:
        portfolio.setdefault("market_fear_greed", {"ok": False})

    # ── STEP 2.9: CFTC COT 리포트 (full/quick만) ──
    from api.config import CFTC_COT_ENABLED
    if CFTC_COT_ENABLED and mode not in ("realtime", "realtime_us"):
        print("\n[2.9] CFTC COT 리포트 (기관 포지셔닝)")
        from api.collectors.cftc_cot import collect_cot_report
        cot_data = safe_collect(
            collect_cot_report,
            name="CFTC_COT", timeout=60, default={"ok": False, "instruments": {}}, notify=_tg_notify,
        )
        portfolio["cftc_cot"] = cot_data
        if cot_data.get("ok"):
            summary = cot_data.get("summary", {})
            sig = summary.get("overall_signal", "?")
            conv = summary.get("conviction_level", 0)
            rd = cot_data.get("report_date", "?")
            print(f"  기관 포지셔닝: {sig} (확신도 {conv}%) | 기준일 {rd}")
            inst = cot_data.get("instruments", {})
            parts = []
            for k, v in inst.items():
                if v.get("ok"):
                    net = v.get("net_managed_money", 0)
                    chg = v.get("change_1w")
                    chg_str = f" ({chg:+,})" if chg is not None else ""
                    parts.append(f"{k}: {net:+,}{chg_str}")
            if parts:
                print(f"  {' | '.join(parts[:4])}")
        else:
            print(f"  ⚠️ 수집 실패: {cot_data.get('error', 'unknown')}")
    else:
        portfolio.setdefault("cftc_cot", {"ok": False, "instruments": {}})

    # ── STEP 2.10: 펀드 플로우 — ETF 기반 자금 유출입 (full/quick만) ──
    from api.config import FUND_FLOW_ENABLED, FUND_FLOW_ETF_TICKERS
    if FUND_FLOW_ENABLED and mode not in ("realtime", "realtime_us"):
        print("\n[2.10] 펀드 플로우 (ETF 자금 유출입)")
        from api.collectors.fund_flow import collect_fund_flows
        ff_kwargs = {}
        if FUND_FLOW_ETF_TICKERS:
            ff_kwargs["etf_tickers"] = FUND_FLOW_ETF_TICKERS
        fund_flow_data = safe_collect(
            collect_fund_flows,
            name="펀드플로우", timeout=90, default={"ok": False}, notify=_tg_notify,
            **ff_kwargs,
        )
        portfolio["fund_flows"] = fund_flow_data
        if fund_flow_data.get("ok"):
            rot = fund_flow_data.get("rotation_signal", "?")
            detail = fund_flow_data.get("rotation_detail", {}).get("detail", "")
            eq = fund_flow_data.get("equity_flow_score", 0)
            bd = fund_flow_data.get("bond_flow_score", 0)
            sf = fund_flow_data.get("safe_haven_flow_score", 0)
            print(f"  로테이션: {rot} — {detail}")
            print(f"  주식 {eq:+.0f} | 채권 {bd:+.0f} | 안전자산 {sf:+.0f} (머니플로우 스코어)")
        else:
            print(f"  ⚠️ 수집 실패: {fund_flow_data.get('error', 'unknown')}")
    else:
        portfolio.setdefault("fund_flows", {"ok": False})

    # ── STEP 2.11: CBOE 풋/콜 비율 (quick/full만) ────────────────────
    from api.config import CBOE_PCR_ENABLED
    if CBOE_PCR_ENABLED and mode not in ("realtime", "realtime_us"):
        print("\n[2.11] CBOE 풋/콜 비율 (시장 패닉/탐욕 신호)")
        from api.collectors.cboe_options_collector import get_pcr_composite_signal
        cboe_data = safe_collect(
            get_pcr_composite_signal,
            name="CBOE_PCR", timeout=20,
            default={"signal": "NEUTRAL", "panic_trigger": False, "vci_adjustment": 0.0},
            notify=_tg_notify,
        )
        portfolio["cboe_pcr"] = cboe_data
        pcr_latest = cboe_data.get("total_pcr_latest")
        signal = cboe_data.get("signal", "NEUTRAL")
        panic = cboe_data.get("panic_trigger", False)
        vci_adj = cboe_data.get("vci_adjustment", 0.0)
        if pcr_latest is not None:
            panic_str = " ⚠ PANIC" if panic else ""
            print(f"  PCR {pcr_latest:.3f} | 신호: {signal} | VCI조정: {vci_adj:+.1f}{panic_str}")
            avg = cboe_data.get("total_pcr_avg_20d")
            z = cboe_data.get("pcr_z_score")
            if avg is not None and z is not None:
                print(f"  20일평균 {avg:.3f} | Z-score {z:+.2f}")
        else:
            print("  ⚠️ 수집 실패 (CBOE 접근 불가)")
    else:
        portfolio.setdefault("cboe_pcr", {"signal": "NEUTRAL", "panic_trigger": False, "vci_adjustment": 0.0})

    # realtime / realtime_us 모드: 보유종목 현재가만 갱신 후 저장
    if mode in ("realtime", "realtime_us"):
        print(f"\n[3] 보유·추천 종목 시세 갱신 ({'US' if is_us_mode else 'KIS/KRX/yfinance'})")
        price_map = build_price_map(portfolio, kis_broker=kis)
        from api.vams.engine import _get_fx_rate
        fx_rate = _get_fx_rate(portfolio)
        for h in portfolio["vams"]["holdings"]:
            h_is_us = h.get("currency") == "USD"
            tk = str(h["ticker"]) if h_is_us else str(h["ticker"]).zfill(6)
            if tk in price_map:
                raw = price_map[tk]
                h["current_price"] = raw * fx_rate if h_is_us else raw
                h["return_pct"] = round((h["current_price"] - h["buy_price"]) / h["buy_price"] * 100, 2)
                h["highest_price"] = max(h.get("highest_price", 0), h["current_price"])
        prev_recs = portfolio.get("recommendations", [])
        for stock in prev_recs:
            s_is_us = stock.get("currency") == "USD"
            tk = str(stock.get("ticker", "")) if s_is_us else str(stock.get("ticker", "")).zfill(6)
            if tk in price_map:
                p = price_map[tk]
                stock["price"] = p
                sl = stock.get("sparkline")
                if isinstance(sl, list) and len(sl) > 0:
                    stock["sparkline"] = sl[:-1] + [round(p, 2 if s_is_us else 0)]
                hw = stock.get("high_52w") or 0
                try:
                    hwf = float(hw)
                    if hwf > 0:
                        stock["drop_from_high_pct"] = round((p - hwf) / hwf * 100, 2)
                except (TypeError, ValueError):
                    pass
            if not s_is_us:
                try:
                    flow = get_investor_flow(stock["ticker"])
                    stock["flow"] = flow
                except Exception:
                    pass
            elif s_is_us:
                try:
                    flow = compute_us_flow(stock)
                    stock["flow"] = flow
                except Exception:
                    pass
        portfolio["recommendations"] = prev_recs
        recalculate_total(portfolio)
        print(f"  {len(price_map)}개 티커 시세 반영 (보유+추천)")

        # ── Claude 긴급 심사: 보유/추천 종목 중 급변 감지 ──
        if CLAUDE_IN_REALTIME and ANTHROPIC_API_KEY:
            from datetime import datetime as _dt, timedelta as _td
            dedupe = portfolio.get("_claude_emergency_dedupe", {})
            if not isinstance(dedupe, dict):
                dedupe = {}
            emergency_sent = 0
            all_targets = list(portfolio["vams"]["holdings"]) + prev_recs
            for item in all_targets:
                ticker = str(item.get("ticker", "")).zfill(6)
                cur_price = item.get("current_price") or item.get("price") or 0
                buy_price = item.get("buy_price") or item.get("_prev_price") or 0
                if not cur_price or not buy_price:
                    continue
                change_pct = (cur_price - buy_price) / buy_price * 100
                if abs(change_pct) < CLAUDE_EMERGENCY_THRESHOLD_PCT:
                    continue
                # 쿨다운 체크
                last_ts = dedupe.get(ticker)
                if last_ts:
                    try:
                        ts = _dt.fromisoformat(str(last_ts))
                        if (now_kst() - ts) < _td(minutes=CLAUDE_EMERGENCY_COOLDOWN_MIN):
                            continue
                    except (ValueError, TypeError):
                        pass
                print(f"\n  ⚡ 급변 감지: {item.get('name', ticker)} ({change_pct:+.1f}%) → Claude 긴급 심사")
                try:
                    result = analyze_stock_emergency(item, change_pct, macro)
                    if result:
                        dedupe[ticker] = now_kst().isoformat()
                        urgency = result.get("urgency_1_5", 0)
                        action = result.get("action", "")
                        hold_exit = result.get("hold_or_exit", "HOLD")
                        print(f"    긴급도 {urgency}/5 | {hold_exit} | {action}")
                        item["claude_emergency"] = result
                        if urgency >= 4:
                            from api.notifications.telegram import send_message as _tg_send
                            _tg_send(
                                f"<b>⚡ 긴급 종목 심사</b>\n"
                                f"{item.get('name', '?')} {change_pct:+.1f}%\n"
                                f"판단: <b>{hold_exit}</b> (긴급도 {urgency}/5)\n"
                                f"원인: {result.get('cause_guess', '?')}\n"
                                f"대응: {action}"
                            )
                        emergency_sent += 1
                except Exception as e:
                    print(f"    Claude 긴급 심사 실패: {e}")
            portfolio["_claude_emergency_dedupe"] = dedupe
            if emergency_sent:
                print(f"  Claude 긴급 심사: {emergency_sent}건 처리")

        # 알림 엔진 실행 (realtime에서도)
        briefing = generate_briefing(portfolio)
        portfolio["briefing"] = briefing
        portfolio["alerts"] = briefing.get("alerts", [])
        print(f"  비서: {briefing['headline']}")

        tg_alerts = [
            a
            for a in briefing.get("alerts", [])
            if a.get("level") in ("CRITICAL", "WARNING")
        ]
        tg_alerts = filter_deduped_realtime_alerts(tg_alerts, portfolio)
        if tg_alerts:
            try:
                if send_alerts(tg_alerts):
                    mark_realtime_alerts_sent(portfolio, tg_alerts)
            except Exception as e:
                print(f"  장중 알림 전송 스킵: {e}")

        try:
            maybe_send_tail_risk_digest(portfolio, is_realtime=True)
        except Exception as e:
            print(f"  꼬리위험(realtime) 스킵: {e}")

        save_portfolio(portfolio)

        # 실시간 모드도 GitHub Actions에서 가장 자주 돌기 때문에, 여기서 봇 폴링·모닝 브리핑을 처리해야 함
        # (이전에는 quick/full 끝에서만 run_poll_once()가 호출되어 장중엔 거의 응답 없음)
        print(f"\n[3.1] 텔레그램 봇 폴링")
        try:
            run_poll_once()
        except Exception as e:
            print(f"  봇 폴링 스킵: {e}")

        now_rt = now_kst()
        morning_ok = (
            (now_rt.hour == MORNING_BRIEF_HOUR_KST and now_rt.minute >= MORNING_BRIEF_MINUTE_KST)
            and (now_rt.hour == MORNING_BRIEF_HOUR_KST and now_rt.minute < MORNING_BRIEF_MINUTE_KST + 15)
        )
        if morning_ok and now_rt.weekday() < 5:
            print(f"\n[3.2] 모닝 브리핑 전송 (KST {now_rt.strftime('%H:%M')})")
            try:
                send_morning_briefing(portfolio)
            except Exception as e:
                print(f"  모닝 브리핑 스킵: {e}")

        print(f"\n✅ 실시간 갱신 완료 (보유 {len(portfolio['vams']['holdings'])}종목)")
        return

    # ── STEP 2: quick + full — 종목 필터링 ──
    print(f"\n[2] 3단계 깔때기 필터링 (scope={market_scope})")
    with tracer.step("stock_filter"):
        candidates = run_filter_pipeline(market_scope=market_scope)
    print(f"  최종 후보: {len(candidates)}개 종목")
    tracer.log_filter("pipeline", 0, len(candidates))

    # ── STEP 2.1: 관심종목(Supabase) 병합 ──
    try:
        watch_items = _fetch_watch_tickers()
        if watch_items:
            watch_added = _merge_watch_items_into_candidates(candidates, watch_items)
            if watch_added:
                print(f"  + 관심종목 {watch_added}개 추가 (총 {len(candidates)}개)")
    except Exception as e:
        print(f"  관심종목 병합 스킵: {e}")

    # ── STEP 3: quick + full — 기술적 + 수급 + 컨센서스 ──
    print("\n[3] 기술적 분석 + 수급 + 컨센서스")
    macro_mood = macro.get("market_mood", {"score": 50, "label": "중립"})
    export_by_ticker = load_trade_export_by_ticker()
    consensus_rows: list = []
    prev_recs_cache: list = _load_previous_analysis() if mode != "full" else []
    for i, stock in enumerate(candidates, 1):
        name = stock["name"]
        ticker = stock["ticker"]
        ticker_yf = stock.get("ticker_yf", f"{ticker}.KS")
        print(f"  [{i}/{len(candidates)}] {name}...", end="")

        tech = analyze_technical(ticker_yf)
        stock["technical"] = tech

        # US 종목: quick 모드에서 경량 Finnhub 수집 (Brain 입력 확보)
        if stock.get("currency") == "USD" and effective_mode != "full":
            prev_match_us = next((r for r in prev_recs_cache if r.get("ticker") == ticker), None)
            _us_fields = ["analyst_consensus", "earnings_surprises", "insider_sentiment",
                          "institutional_ownership", "options_flow", "short_interest",
                          "sec_financials", "sec_filings", "company_news",
                          "pre_after_market", "finnhub_metrics", "peer_companies",
                          "insider_transactions"]
            if prev_match_us:
                for _uf in _us_fields:
                    if prev_match_us.get(_uf):
                        stock.setdefault(_uf, prev_match_us[_uf])
            if not stock.get("analyst_consensus"):
                try:
                    from api.collectors import finnhub_client as _fh
                    from api.config import FINNHUB_API_KEY as _fhk
                    if _fhk:
                        stock["analyst_consensus"] = _fh.get_analyst_consensus(ticker, _fhk)
                        stock["earnings_surprises"] = _fh.get_earnings_surprises(ticker, _fhk)
                        stock["insider_sentiment"] = _fh.get_insider_sentiment(ticker, _fhk)
                except Exception:
                    pass

        if stock.get("currency") == "USD":
            flow = compute_us_flow(stock)
        else:
            flow = get_investor_flow(ticker)
        stock["flow"] = flow

        if effective_mode == "full":
            sentiment = get_stock_sentiment(name, market=stock.get("market", "KR"), ticker=ticker)
        else:
            prev_match = next((r for r in prev_recs_cache if r.get("ticker") == ticker), None)
            sentiment = prev_match.get("sentiment", {"score": 50, "positive": 0, "negative": 0, "neutral": 0, "headline_count": 0, "top_headlines": [], "detail": []}) if prev_match else {"score": 50, "positive": 0, "negative": 0, "neutral": 0, "headline_count": 0, "top_headlines": [], "detail": []}
            if prev_match:
                dart_prev = prev_match.get("dart_financials")
                if dart_prev:
                    stock["dart_financials"] = dart_prev
                elif prev_match.get("dart_data"):
                    stock["dart_data"] = prev_match["dart_data"]
                elif prev_match.get("property_assets"):
                    stock["property_assets"] = prev_match["property_assets"]
                prev_social = prev_match.get("social_sentiment")
                if prev_social and prev_social.get("score") is not None:
                    stock["social_sentiment"] = prev_social
        stock["sentiment"] = sentiment

        if effective_mode == "full":
            try:
                code_6 = str(ticker).zfill(6) if not str(ticker_yf).startswith(str(ticker)) else None
                social = compute_social_sentiment(
                    name=name, ticker_yf=ticker_yf,
                    stock_code=code_6, existing_news=sentiment,
                )
                stock["social_sentiment"] = social
                print(f"      소셜: {social['score']}점 ({social['trend']}) | 소스: {', '.join(social['sources_used'])}")
            except Exception as e:
                print(f"      소셜 감성 수집 실패: {e}")
                stock["social_sentiment"] = {"score": 50, "trend": "neutral", "sources_used": []}

        raw_c = scout_consensus(ticker)
        time.sleep(0.1)
        price_c = float(stock.get("price") or 0)
        cblock = build_consensus_block(
            raw_c, price_c, flow, export_by_ticker.get(str(ticker).zfill(6))
        )
        stock["consensus"] = cblock
        fund_c = merge_fundamental_with_consensus(stock.get("safety_score", 50), cblock)
        mp = fundamental_penalty_from_macro(macro)
        if mp:
            fund_c = max(0, fund_c - mp)

        mf = compute_multi_factor_score(
            fundamental_score=fund_c,
            technical=tech, sentiment=sentiment, flow=flow, macro_mood=macro_mood,
            social_sentiment=stock.get("social_sentiment"),
        )
        stock["multi_factor"] = mf
        attach_value_chain_trade_overlay(stock)
        consensus_rows.append(
            {
                "ticker": ticker,
                "name": name,
                "scout_ok": raw_c.get("ok"),
                "scout_error": raw_c.get("error"),
                "investment_opinion": raw_c.get("investment_opinion"),
                "target_price": raw_c.get("target_price"),
                "sales_estimate_bn": raw_c.get("sales_estimate_bn"),
                "operating_profit_estimate_bn": raw_c.get("operating_profit_estimate_bn"),
                "operating_profit_prior_year_bn": raw_c.get("operating_profit_prior_year_bn"),
                "consensus_score": cblock.get("consensus_score"),
                "score_source": cblock.get("score_source"),
                "upside_pct": cblock.get("upside_pct"),
                "operating_profit_yoy_est_pct": cblock.get("operating_profit_yoy_est_pct"),
                "warnings": cblock.get("warnings", []),
            }
        )
        print(
            f" {mf['multi_score']}점({mf['grade']}) RSI:{tech['rsi']} "
            f"수급:{flow['flow_score']} 컨센:{cblock.get('consensus_score', '?')}({cblock.get('score_source', '')})"
        )

    try:
        save_consensus_batch(consensus_rows, CONSENSUS_DATA_PATH)
        print(f"  컨센서스 스냅샷 저장: {CONSENSUS_DATA_PATH} ({len(consensus_rows)}종목)")
    except Exception as e:
        print(f"  consensus_data.json 저장 실패: {e}")

    # ── STEP 4: quick + full — XGBoost 예측 ──
    print("\n[4] XGBoost 예측")
    with tracer.step("xgb_prediction"):
        for stock in candidates:
            ticker_yf = stock.get("ticker_yf", f"{stock['ticker']}.KS")
            try:
                prediction = predict_stock(ticker_yf, current_features=stock)
                stock["prediction"] = prediction
                tracer.log_prediction(stock["ticker"], {
                    "technical": stock.get("technical", {}),
                    "multi_factor": stock.get("multi_factor", {}),
                    "consensus": stock.get("consensus", {}),
                }, prediction)
                print(f"  {stock['name']}: {prediction['up_probability']}% ({prediction['method']})")
            except Exception:
                stock["prediction"] = {"up_probability": 50, "method": "error", "model_accuracy": 0, "confidence_level": "none", "top_features": {}, "train_samples": 0, "test_samples": 0}

    # 타이밍 시그널 계산 (예측 완료 후)
    for stock in candidates:
        stock["timing"] = compute_timing_signal(stock)

    # ── STEP 4.5: 학술 퀀트 팩터 계산 (모멘텀/퀄리티/변동성/평균회귀) ──
    print("\n[4.5] 퀀트 팩터 계산")
    try:
        for stock in candidates:
            ticker_yf = stock.get("ticker_yf", f"{stock['ticker']}.KS")
            enrich_momentum_prices(stock, ticker_yf)

        vol_stats = compute_universe_vol_stats(candidates)

        for stock in candidates:
            qf = {}
            try:
                qf["momentum"] = compute_momentum_score(stock, universe=candidates)
            except Exception:
                qf["momentum"] = {"momentum_score": 50, "signals": []}
            try:
                qf["quality"] = compute_quality_score(stock)
            except Exception:
                qf["quality"] = {"quality_score": 50, "signals": []}
            try:
                qf["volatility"] = compute_volatility_score(stock, universe_stats=vol_stats)
            except Exception:
                qf["volatility"] = {"volatility_score": 50, "signals": []}
            try:
                qf["mean_reversion"] = compute_mean_reversion_score(stock)
            except Exception:
                qf["mean_reversion"] = {"mean_reversion_score": 50, "signals": []}

            stock["quant_factors"] = qf

            # 퀀트 팩터로 멀티팩터 재계산
            fund_c = merge_fundamental_with_consensus(
                stock.get("safety_score", 50), stock.get("consensus", {})
            )
            mp = fundamental_penalty_from_macro(macro)
            if mp:
                fund_c = max(0, fund_c - mp)
            stock["multi_factor"] = compute_multi_factor_score(
                fundamental_score=fund_c,
                technical=stock.get("technical", {}),
                sentiment=stock.get("sentiment", {}),
                flow=stock.get("flow", {}),
                macro_mood=macro_mood,
                quant_factors=qf,
                social_sentiment=stock.get("social_sentiment"),
            )

        avg_mom = round(sum(s.get("quant_factors", {}).get("momentum", {}).get("momentum_score", 50) for s in candidates) / max(len(candidates), 1))
        avg_qual = round(sum(s.get("quant_factors", {}).get("quality", {}).get("quality_score", 50) for s in candidates) / max(len(candidates), 1))
        avg_vol = round(sum(s.get("quant_factors", {}).get("volatility", {}).get("volatility_score", 50) for s in candidates) / max(len(candidates), 1))
        avg_mr = round(sum(s.get("quant_factors", {}).get("mean_reversion", {}).get("mean_reversion_score", 50) for s in candidates) / max(len(candidates), 1))
        print(f"  유니버스 평균 — 모멘텀:{avg_mom} | 퀄리티:{avg_qual} | 저변동:{avg_vol} | 평균회귀:{avg_mr}")
    except Exception as e:
        print(f"  퀀트 팩터 스킵: {e}")
        _DEFAULT_QF = {
            "momentum": {"momentum_score": 50, "signals": [], "components": {}},
            "quality": {"quality_score": 50, "signals": [], "components": {}},
            "volatility": {"volatility_score": 50, "signals": [], "components": {}},
            "mean_reversion": {"mean_reversion_score": 50, "signals": [], "components": {}},
        }
        for stock in candidates:
            stock.setdefault("quant_factors", _DEFAULT_QF)

    # ── STEP 5: full 전용 — 백테스트 ──
    if effective_mode == "full":
        print("\n[5] 백테스팅")
        for stock in candidates:
            ticker_yf = stock.get("ticker_yf", f"{stock['ticker']}.KS")
            try:
                bt = backtest_stock(ticker_yf)
                stock["backtest"] = bt
                if bt["total_trades"] > 0:
                    print(f"  {stock['name']}: 승률 {bt['win_rate']}% | {bt['total_trades']}회")
            except Exception:
                stock["backtest"] = {"total_trades": 0, "win_rate": 0, "avg_return": 0, "max_drawdown": 0, "sharpe_ratio": 0, "recent_trades": []}
    else:
        for stock in candidates:
            stock.setdefault("backtest", {})

    # ── STEP 5.5: full 전용 — 실적 캘린더 ──
    if effective_mode == "full":
        print("\n[5.5] 실적 캘린더 수집")
        try:
            collect_earnings_for_stocks(candidates)
            earns = [s for s in candidates if s.get("earnings", {}).get("next_earnings")]
            print(f"  {len(earns)}개 종목 실적일 확인")
        except Exception as e:
            print(f"  실적 캘린더 스킵: {e}")

    # ── STEP 5.55: full 전용 — 실적 발표 직후 Perplexity 리서치 ──
    if effective_mode == "full" and PERPLEXITY_API_KEY:
        try:
            from api.intelligence.perplexity_realtime import (
                is_earnings_imminent,
                research_earnings,
            )
            earnings_today = [s for s in candidates if is_earnings_imminent(s)]
            if earnings_today:
                print(f"\n[5.55] Perplexity 실적 리서치 ({len(earnings_today)}종목)")
                for stock in earnings_today[:5]:
                    sname = stock.get("name", stock.get("ticker", "?"))
                    print(f"  [Perplexity] 실적 리서치: {sname}")
                    insight = research_earnings(stock)
                    stock["earnings_insight"] = insight
                    if "error" not in insight:
                        print(f"    결과: {insight.get('beat_miss', '?')}")
                    else:
                        print(f"    실패: {insight.get('error', '?')}")
        except Exception as e:
            print(f"  ⚠️ 실적 리서치 스킵: {e}")

    # ── STEP 5.7: full 전용 — DART 재무제표(현금흐름) — US 종목 스킵 ──
    if effective_mode == "full":
        print("\n[5.7] DART 재무제표 + 현금흐름 수집")
        from api.collectors.DartScout import scout
        dart_ok = 0
        for stock in candidates:
            if stock.get("currency") == "USD":
                continue
            ticker_yf = stock.get("ticker_yf", f"{stock['ticker']}.KS")
            dart_data = safe_collect(
                scout, ticker_yf,
                name=f"DART({stock.get('name', ticker_yf)})", timeout=60, default={},
            )
            if dart_data and not dart_data.get("error") and not dart_data.get("critical_error"):
                stock["dart_financials"] = {
                    "financials": dart_data.get("financials", {}),
                    "cashflow": dart_data.get("cashflow", {}),
                    "dividends": dart_data.get("dividends", []),
                    "audit_opinion": dart_data.get("audit_opinion", ""),
                    "property_assets": dart_data.get("property_assets", {}),
                }
                dart_ok += 1
        print(f"  {dart_ok}/{len(candidates)} 종목 DART 데이터 수집 완료")

    # ── STEP 5.705: full 전용 — yfinance 확장 재무 (분기 실적/배당/ESG) ──
    if effective_mode == "full":
        print("\n[5.705] yfinance 확장 재무 (분기 실적, 배당, ESG)")
        from api.collectors.stock_data import get_extended_financials
        yf_ext_ok = 0
        for stock in candidates[:20]:
            ticker_yf = stock.get("ticker_yf", f"{stock['ticker']}.KS")
            ext = safe_collect(
                get_extended_financials, ticker_yf,
                name=f"yf확장({stock.get('name', ticker_yf)})", timeout=30, default={},
            )
            has_data = (
                ext.get("quarterly_earnings")
                or ext.get("dividend_history")
                or ext.get("sustainability", {}).get("total") is not None
            )
            if has_data:
                stock["yf_extended"] = ext
                yf_ext_ok += 1
        print(f"  {yf_ext_ok}/{min(len(candidates), 20)} 종목 확장 재무 수집 완료")

    # ── STEP 5.71: full — Finnhub / SEC / Polygon 미장 데이터 수집 ──
    # full_us: 전체 USD 종목, full(KR): 상위 10개 USD 종목만 (호출량 방어)
    us_candidates_571 = [s for s in candidates if s.get("currency") == "USD"]
    if effective_mode == "full" and us_candidates_571:
        us_limit = len(us_candidates_571) if is_us_mode else 10
        us_targets = us_candidates_571[:us_limit]
        us_data_symbols_count = len(us_targets)
        us_data_requests_est = len(us_targets) * 13  # Finnhub 7 + SEC 3 + Polygon 3
        scope_label = "전체" if is_us_mode else f"상위 {us_limit}개"
        print(f"\n[5.71] 미장 데이터 수집 — {scope_label} ({len(us_targets)}종목, Finnhub/SEC/Polygon)")
        from api.collectors import finnhub_client as finnhub
        from api.collectors import sec_edgar as sec
        from api.collectors import polygon_client as polygon
        from api.config import FINNHUB_API_KEY, SEC_EDGAR_USER_AGENT, POLYGON_API_KEY, POLYGON_TIER

        us_ok = 0
        for idx, stock in enumerate(us_targets):
            ticker = stock["ticker"]
            name = stock["name"]
            print(f"    [{idx+1}/{len(us_targets)}] {name} ({ticker})")

            def _fetch_finnhub(t=ticker):
                return {
                    "analyst_consensus": finnhub.get_analyst_consensus(t, FINNHUB_API_KEY),
                    "earnings_surprises": finnhub.get_earnings_surprises(t, FINNHUB_API_KEY),
                    "insider_sentiment": finnhub.get_insider_sentiment(t, FINNHUB_API_KEY),
                    "institutional_ownership": finnhub.get_institutional_ownership(t, FINNHUB_API_KEY),
                    "company_news": finnhub.get_company_news(t, FINNHUB_API_KEY),
                    "peer_companies": finnhub.get_peer_companies(t, FINNHUB_API_KEY),
                    "finnhub_metrics": finnhub.get_basic_financials(t, FINNHUB_API_KEY),
                }
            fh = safe_collect(_fetch_finnhub, name=f"Finnhub({ticker})", timeout=60, default={})
            stock.update(fh)

            def _fetch_sec(t=ticker):
                return {
                    "sec_filings": sec.get_recent_filings(t, SEC_EDGAR_USER_AGENT),
                    "sec_financials": sec.get_financial_facts(t, SEC_EDGAR_USER_AGENT),
                    "insider_transactions": sec.get_insider_transactions(t, SEC_EDGAR_USER_AGENT),
                }
            sc = safe_collect(_fetch_sec, name=f"SEC({ticker})", timeout=60, default={})
            stock.update(sc)

            def _fetch_polygon(t=ticker):
                return {
                    "options_flow": polygon.get_options_flow(t, POLYGON_API_KEY, POLYGON_TIER),
                    "short_interest": polygon.get_short_interest(t, POLYGON_API_KEY, POLYGON_TIER),
                    "pre_after_market": polygon.get_pre_after_market(t, POLYGON_API_KEY, POLYGON_TIER),
                }
            pg = safe_collect(_fetch_polygon, name=f"Polygon({ticker})", timeout=45, default={})
            stock.update(pg)

            us_ok += 1
        print(f"  {us_ok}/{len(us_targets)} US 종목 미장 전용 데이터 수집 완료")

    # ── STEP 5.72: full — SEC 8-K 리스크 키워드 스캔 ──
    from api.config import SEC_RISK_SCAN_ENABLED, SEC_RISK_KEYWORDS, SEC_RISK_SCAN_DAYS, SEC_EDGAR_USER_AGENT as _sec_ua
    if effective_mode == "full" and SEC_RISK_SCAN_ENABLED and _sec_ua:
        print(f"\n[5.72] SEC 8-K 리스크 키워드 스캔 ({len(SEC_RISK_KEYWORDS)}개 키워드, {SEC_RISK_SCAN_DAYS}일)")
        from api.collectors.sec_edgar import scan_risk_filings
        risk_scan = safe_collect(
            scan_risk_filings,
            SEC_RISK_KEYWORDS, _sec_ua,
            days_back=SEC_RISK_SCAN_DAYS,
            name="SEC리스크스캔", timeout=60, default={"ok": False, "filings": []},
            notify=_tg_notify,
        )
        portfolio["sec_risk_scan"] = risk_scan
        if risk_scan.get("ok"):
            print(f"  {risk_scan['count']}건 리스크 공시 탐지 ({risk_scan.get('date_range', '')})")
            # 보유/추천 종목에 리스크 매칭
            port_tickers = set()
            for r in candidates:
                t = r.get("ticker", "")
                if t:
                    port_tickers.add(t.upper())
            matched = []
            for f in risk_scan.get("filings", []):
                ft = (f.get("ticker") or "").upper()
                if ft and ft in port_tickers:
                    matched.append(f)
                    for s in candidates:
                        if s.get("ticker", "").upper() == ft:
                            existing = s.get("sec_risk_flags") or []
                            existing.append(f["keyword_matched"])
                            s["sec_risk_flags"] = existing
            if matched:
                print(f"  ⚠️ 보유/추천 종목 매칭: {', '.join(m['ticker'] for m in matched)}")
        else:
            print(f"  리스크 공시 없음 (최근 {SEC_RISK_SCAN_DAYS}일)")

    # ── STEP 5.75: full 전용 — 관계회사 지배구조 + 지분가치 분석 (KR only) ──
    if effective_mode == "full" and not is_us_mode:
        print("\n[5.75] 관계회사 지배구조 + NAV 분석")
        try:
            gs_data = collect_group_structures(candidates)
            if gs_data:
                save_group_structures(gs_data)
                matched = attach_group_structure_to_candidates(candidates, gs_data)
                print(f"  {matched}/{len(candidates)} 종목 관계회사 구조 매칭 완료")
            else:
                print("  관계회사 구조 데이터 없음 — 스킵")
        except Exception as e:
            print(f"  관계회사 구조 수집 스킵: {e}")
    else:
        try:
            prev_gs = load_group_structures()
            if prev_gs:
                matched = attach_group_structure_to_candidates(candidates, prev_gs)
                if matched:
                    print(f"  [캐시] 관계회사 구조 {matched}건 재사용")
        except Exception:
            pass

    # ── STEP 5.76: full 전용 — ChainScout 주요 매출처/고객사 (KR only) ──
    if effective_mode == "full" and not is_us_mode:
        print("\n[5.76] ChainScout — 주요 매출처/고객사 분석")
        try:
            from api.collectors.ChainScout import scout_major_customer_snippets, save_snippets_payload
            chain_ok = 0
            kr_for_chain = [s for s in candidates if s.get("currency") != "USD"][:5]
            for stock in kr_for_chain:
                ticker_yf = stock.get("ticker_yf", f"{stock['ticker']}.KS")
                try:
                    cs_result = scout_major_customer_snippets(ticker_yf)
                    if cs_result.get("snippets"):
                        stock["chain_scout"] = {
                            "snippets": cs_result["snippets"][:5],
                            "report_nm": cs_result.get("report_nm", ""),
                            "rcept_dt": cs_result.get("rcept_dt", ""),
                        }
                        save_snippets_payload(cs_result)
                        chain_ok += 1
                        print(f"    {stock.get('name', '?')}: 스니펫 {len(cs_result['snippets'])}건")
                except Exception as e:
                    print(f"    {stock.get('name', '?')}: {e}")
            print(f"  {chain_ok}/{len(kr_for_chain)} 종목 매출처 스니펫 수집 완료")
        except Exception as e:
            print(f"  ChainScout 스킵: {e}")

    # ── STEP 5.77: full 전용 — SpecialScout RRA 인증 + KIPRIS 특허 (KR only) ──
    if effective_mode == "full" and not is_us_mode:
        print("\n[5.77] SpecialScout — RRA 인증 + 특허 출원")
        try:
            from api.collectors.SpecialScout import (
                company_name_variants as ss_variants,
                fetch_rra_for_company,
                fetch_patents_for_company,
            )
            import requests as _req
            kipris_key = (os.environ.get("KIPRIS_API_KEY") or os.environ.get("KIPRIS_ACCESS_KEY") or "").strip()
            ss_session = _req.Session()
            ss_session.headers.update({
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Accept-Language": "ko-KR,ko;q=0.9",
            })
            scout_ok = 0
            kr_for_scout = [s for s in candidates if s.get("currency") != "USD"][:10]
            for stock in kr_for_scout:
                name = stock.get("name", "")
                if not name:
                    continue
                variants = ss_variants(name)
                rra = []
                patents = []
                try:
                    rra = fetch_rra_for_company(ss_session, variants)
                except Exception:
                    pass
                if kipris_key:
                    try:
                        patents = fetch_patents_for_company(variants, kipris_key)
                    except Exception:
                        pass
                if rra or patents:
                    stock["special_scout"] = {
                        "rra_data": rra[:5],
                        "patent_data": patents[:10],
                        "rra_count": len(rra),
                        "patent_count": len(patents),
                    }
                    scout_ok += 1
            note = "KIPRIS 활성" if kipris_key else "KIPRIS 키 미설정"
            print(f"  {scout_ok}/{len(kr_for_scout)} 종목 인증/특허 수집 ({note})")
        except Exception as e:
            print(f"  SpecialScout 스킵: {e}")

    # ── STEP 5.8: 원자재 상관·마진 (기본 full / quick는 COMMODITY_SCOUT_IN_QUICK=1)
    run_commodity = effective_mode == "full" or COMMODITY_SCOUT_IN_QUICK
    run_commodity_narrative = effective_mode == "full" or COMMODITY_NARRATIVE_IN_QUICK
    if run_commodity:
        tag = "full" if effective_mode == "full" else "quick+COMMODITY_SCOUT_IN_QUICK"
        print(f"\n[5.8] 원자재 상관·스프레드 (CommodityScout) [{tag}]")
        try:
            holdings = portfolio.get("vams", {}).get("holdings", [])
            scout = run_commodity_scout(candidates, holdings)
            attach_commodity_to_stocks(candidates, scout)
            if run_commodity_narrative:
                try:
                    scout = enrich_commodity_impact_narratives(scout, candidates, holdings)
                except Exception as ne:
                    print(f"  원자재 서술 보강 스킵: {ne}")
            portfolio["commodity_impact"] = scout
            macro_mood = macro.get("market_mood", {"score": 50, "label": "중립"})
            for stock in candidates:
                cm = stock.get("commodity_margin") or {}
                fund_base = merge_fundamental_with_consensus(
                    stock.get("safety_score", 50),
                    stock.get("consensus", {}),
                )
                fund_adj = apply_commodity_adjustment_to_fundamental(fund_base, cm)
                mp = fundamental_penalty_from_macro(macro)
                if mp:
                    fund_adj = max(0, fund_adj - mp)
                stock["multi_factor"] = compute_multi_factor_score(
                    fundamental_score=fund_adj,
                    technical=stock.get("technical", {}),
                    sentiment=stock.get("sentiment", {}),
                    flow=stock.get("flow", {}),
                    macro_mood=macro_mood,
                    quant_factors=stock.get("quant_factors"),
                    social_sentiment=stock.get("social_sentiment"),
                )
            n_hi = len(scout.get("high_correlation") or [])
            n_mom = len(scout.get("commodity_mom_alerts") or [])
            print(f"  고상관 종목 {n_hi}개 | 전월대비 급변 원자재 {n_mom}건 → commodity_impact.json")
        except Exception as e:
            print(f"  CommodityScout 스킵: {e}")
            portfolio.setdefault("commodity_impact", {})
    else:
        portfolio.setdefault("commodity_impact", {})

    # ── STEP 5.85: KIS Brain 데이터 → 후보 종목 주입 ──
    kis_brain_map = {}
    for tk, snap in portfolio.get("kis_snapshots", {}).items():
        if "brain" in snap:
            kis_brain_map[tk] = snap["brain"]
    if kis_brain_map:
        print(f"\n[5.85] KIS 분석 데이터 → 후보 종목 주입 ({len(kis_brain_map)}종목)")
        for stock in candidates:
            if stock.get("currency") == "USD":
                continue
            tk = str(stock.get("ticker", "")).zfill(6)
            kb = kis_brain_map.get(tk)
            if not kb:
                continue

            if kb.get("investor"):
                flow = stock.get("flow", {})
                flow["kis_foreign_net"] = kb["investor"]["foreign_net"]
                flow["kis_institution_net"] = kb["investor"]["institution_net"]
                stock["flow"] = flow

            if kb.get("invest_opinion"):
                cons = stock.get("consensus", {})
                cons["kis_opinion"] = kb["invest_opinion"]["opinion"]
                cons["kis_target_price"] = kb["invest_opinion"]["target_price"]
                cons["kis_analyst_firm"] = kb["invest_opinion"]["analyst_firm"]
                stock["consensus"] = cons

            if kb.get("estimate"):
                stock["kis_estimate"] = kb["estimate"]

            if kb.get("financial_ratio"):
                stock["kis_financial_ratio"] = kb["financial_ratio"]

            if kb.get("short_sale"):
                stock["kis_short_sale"] = kb["short_sale"]

            if kb.get("credit_balance"):
                stock["kis_credit_balance"] = kb["credit_balance"]

            if kb.get("program_trade"):
                stock["kis_program_trade"] = kb["program_trade"]

    # ── STEP 5.86: KIS 해외주식 데이터 → US 후보 종목 주입 ──
    kis_us_map = portfolio.get("kis_us_snapshots", {})
    if kis_us_map:
        us_injected = 0
        for stock in candidates:
            if stock.get("currency") != "USD":
                continue
            tk = stock.get("ticker", "")
            kb = kis_us_map.get(tk)
            if not kb:
                continue
            if kb.get("price"):
                stock["kis_overseas_price"] = kb["price"]
                if kb["price"].get("per"):
                    stock.setdefault("per", kb["price"]["per"])
                if kb["price"].get("pbr"):
                    stock.setdefault("pbr", kb["price"]["pbr"])
            us_injected += 1
        if us_injected:
            print(f"\n[5.86] KIS 해외주식 → US 종목 {us_injected}건 주입")

    # ── STEP 5.9: Verity Brain — 종합 판단 엔진 ──
    print("\n[5.9] Verity Brain 종합 판단")

    # US/KR 모드별로 recommendations를 MERGE (상대 시장 종목 보존)
    prev_recs_all = portfolio.get("recommendations", [])
    if is_us_mode:
        kept = [r for r in prev_recs_all if r.get("currency") != "USD"]
        merged = kept + candidates
        print(f"  [MERGE] 기존 KR {len(kept)}개 보존 + 신규 US {len(candidates)}개")
    else:
        kept = [r for r in prev_recs_all if r.get("currency") == "USD"]
        merged = candidates + kept
        print(f"  [MERGE] 신규 KR+US {len(candidates)}개 + 기존 US-only {len(kept)}개 보존")
    # 중복 제거 (ticker 기준, 신규 우선)
    seen_tickers = set()
    deduped = []
    for r in merged:
        tk = r.get("ticker")
        if tk not in seen_tickers:
            seen_tickers.add(tk)
            deduped.append(r)
    portfolio["recommendations"] = deduped
    candidates = deduped
    try:
        from api.intelligence.verity_brain import reset_ic_cache
        reset_ic_cache()
        brain_result = verity_brain_analyze(candidates, portfolio)
        portfolio["verity_brain"] = {
            "macro_override": brain_result.get("macro_override"),
            "market_brain": brain_result.get("market_brain"),
        }
        brain_stocks = {r["ticker"]: r for r in (brain_result.get("stocks") or [])}
        for stock in candidates:
            br = brain_stocks.get(stock.get("ticker"), {})
            stock["verity_brain"] = {
                "brain_score": br.get("brain_score", 0),
                "grade": br.get("grade", "WATCH"),
                "grade_label": br.get("grade_label", "관망"),
                "grade_confidence": br.get("grade_confidence", "firm"),
                "data_coverage": br.get("data_coverage", 1.0),
                "fact_score": br.get("fact_score", {}),
                "sentiment_score": br.get("sentiment_score", {}),
                "vci": br.get("vci", {}),
                "vci_bonus": br.get("vci_bonus", 0),
                "candle_bonus": br.get("candle_bonus", 0),
                "brain_weights": br.get("brain_weights", {}),
                "red_flags": br.get("red_flags", {}),
                "red_flag_penalty": br.get("red_flag_penalty", 0),
                "position_guide": br.get("position_guide", {}),
                "reasoning": br.get("reasoning", ""),
            }

        mb = brain_result.get("market_brain", {})
        ov = brain_result.get("macro_override")
        dist = mb.get("grade_distribution", {})
        print(f"  시장 평균: 브레인 {mb.get('avg_brain_score', 0)}점 | "
              f"팩트 {mb.get('avg_fact_score', 0)} / 심리 {mb.get('avg_sentiment_score', 0)} / "
              f"VCI {mb.get('avg_vci', 0):+d}")
        print(f"  등급 분포: 강매수 {dist.get('STRONG_BUY', 0)} | 매수 {dist.get('BUY', 0)} | "
              f"관망 {dist.get('WATCH', 0)} | 주의 {dist.get('CAUTION', 0)} | 회피 {dist.get('AVOID', 0)}")
        if ov:
            print(f"  ⚠️ 매크로 오버라이드: {ov.get('label', '?')} — {ov.get('message', '')}")
        top = mb.get("top_picks", [])
        if top:
            top_str = ", ".join(f"{t['name']}({t['score']})" for t in top[:3])
            print(f"  TOP: {top_str}")
        flagged = mb.get("red_flag_stocks", [])
        if flagged:
            flag_str = ", ".join(f.get("name", "?") for f in flagged[:3])
            print(f"  레드플래그: {flag_str}")
        for stock in candidates:
            tracer.log_brain_detail(stock.get("ticker", ""), stock.get("verity_brain", {}))
    except Exception as e:
        print(f"  ⚠️ Verity Brain 스킵: {e}")
        tracer.log_error("verity_brain", e)
        portfolio.setdefault("verity_brain", {})

    # ── STEP 5.95: full 전용 — BUY 후보 외부 리스크 Perplexity 스캔 ──
    if effective_mode == "full" and PERPLEXITY_API_KEY:
        buy_candidates = [
            s for s in candidates
            if s.get("verity_brain", {}).get("grade") in ("BUY", "STRONG_BUY")
        ]
        if buy_candidates:
            print(f"\n[5.95] Perplexity 외부 리스크 스캔 ({len(buy_candidates)}종목)")
            try:
                from api.intelligence.perplexity_realtime import research_stock_risk
                for stock in buy_candidates[:10]:
                    sname = stock.get("name", stock.get("ticker", "?"))
                    print(f"  [Perplexity] 리스크 스캔: {sname}")
                    risk = research_stock_risk(stock)
                    stock["external_risk"] = risk
                    if risk.get("risk_level") == "HIGH":
                        rf = stock.get("verity_brain", {}).get("red_flags", {})
                        rf.setdefault("downgrade", []).append(
                            f"외부 리스크: {risk.get('external_risks', '')[:80]}")
                        print(f"    ⚠️ HIGH 리스크 감지 → downgrade 추가")
                    elif "error" not in risk:
                        print(f"    리스크: {risk.get('risk_level', '?')}")
            except Exception as e:
                print(f"  ⚠️ 외부 리스크 스캔 스킵: {e}")

    # ── STEP 6: full 전용 — Gemini AI (V6: 후보 상한 적용) ──
    if effective_mode == "full":
        from api.config import GEMINI_BATCH_MAX_STOCKS
        gemini_candidates = candidates
        if len(candidates) > GEMINI_BATCH_MAX_STOCKS:
            gemini_candidates = sorted(
                candidates,
                key=lambda s: s.get("verity_brain", {}).get("brain_score", 0),
                reverse=True,
            )[:GEMINI_BATCH_MAX_STOCKS]
            skipped = len(candidates) - GEMINI_BATCH_MAX_STOCKS
            print(f"\n[6] Gemini AI 종합 분석 (상위 {GEMINI_BATCH_MAX_STOCKS}개, {skipped}개 스킵)")
        else:
            print("\n[6] Gemini AI 종합 분석")
        try:
            # 지정학 트리거 (대만 지진 등) 추출 — 점수 반영 없이 AI 프롬프트에만 참고 주입
            active_geo_triggers = [
                ev for ev in portfolio.get("global_events", [])
                if ev.get("trigger_source") and ev.get("affected_tickers")
            ]
            with tracer.step("gemini_analysis"):
                analyzed_subset = analyze_batch(
                    gemini_candidates,
                    macro_context=macro,
                    geo_triggers=active_geo_triggers or None,
                )
            analyzed_tickers = {s["ticker"] for s in analyzed_subset}
            passthrough = [s for s in candidates if s.get("ticker") not in analyzed_tickers]
            analyzed = analyzed_subset + passthrough
            tracer.log("gemini_analyzed_count", len(analyzed_subset))
            print(f"  Gemini 분석: {len(analyzed_subset)}개 | 패스스루: {len(passthrough)}개")
        except Exception as e:
            print(f"  ⚠️ Gemini 스킵: {e}")
            tracer.log_error("gemini_analysis", e)
            analyzed = candidates
    else:
        analyzed = candidates

    _apply_fallback_judgments(analyzed)

    # ── STEP 6.2: full 전용 — Gemini Pro 상위 N개 재판단 (하이브리드 라우팅) ──
    gemini_pro_calls = 0
    if effective_mode == "full":
        from api.config import GEMINI_PRO_ENABLE, GEMINI_CRITICAL_TOP_N
        if GEMINI_PRO_ENABLE:
            print(f"\n[6.2] Gemini Pro 상위 {GEMINI_CRITICAL_TOP_N}개 재판단")
            try:
                pro_results = reanalyze_top_n_pro(
                    analyzed,
                    macro_context=macro,
                    geo_triggers=[
                        ev for ev in portfolio.get("global_events", [])
                        if ev.get("trigger_source") and ev.get("affected_tickers")
                    ] or None,
                )
                gemini_pro_calls = len(pro_results)
                merged_pro = 0
                for stock in analyzed:
                    pr = pro_results.get(stock.get("ticker"))
                    if pr and pr.get("recommendation"):
                        flash_rec = stock.get("recommendation", "WATCH")
                        flash_conf = stock.get("confidence", 0)
                        stock["recommendation"] = pr["recommendation"]
                        stock["confidence"] = pr.get("confidence", flash_conf)
                        stock["ai_verdict"] = pr.get("ai_verdict", stock.get("ai_verdict", ""))
                        stock["gold_insight"] = pr.get("gold_insight", stock.get("gold_insight", ""))
                        stock["silver_insight"] = pr.get("silver_insight", stock.get("silver_insight", ""))
                        stock["_gemini_model"] = pr.get("_gemini_model", "")
                        stock["_flash_recommendation"] = flash_rec
                        stock["_flash_confidence"] = flash_conf
                        merged_pro += 1
                        if flash_rec != pr["recommendation"]:
                            print(f"    ↕ {stock.get('name')}: {flash_rec} → {pr['recommendation']}")
                print(f"  Pro 병합: {merged_pro}종목 | Flash→Pro 판정변경 {sum(1 for s in analyzed if s.get('_flash_recommendation') and s['_flash_recommendation'] != s.get('recommendation', 'WATCH'))}건")
            except Exception as e:
                print(f"  ⚠️ Gemini Pro 재판단 스킵: {e}")

    # ── STEP 6.3: full 전용 — Claude 2차 심층 분석 (V6: STRONG_BUY 게이트 + 상한 강화) ──
    if effective_mode == "full" and ANTHROPIC_API_KEY:
        from api.config import CLAUDE_STRONG_BUY_ONLY
        grade_filter = "STRONG_BUY only" if CLAUDE_STRONG_BUY_ONLY else f"Brain {CLAUDE_MIN_BRAIN_SCORE}+"
        print(f"\n[6.3] Claude 2차 심층 분석 ({grade_filter}, 상위 {CLAUDE_TOP_N}개)")
        try:
            model_weights = _resolve_dual_model_weights(portfolio)
            print(f"  하이브리드 가중치: Gemini {model_weights['gemini']:.2f} / Claude {model_weights['claude']:.2f}")
            if CLAUDE_STRONG_BUY_ONLY:
                claude_targets = [
                    s for s in analyzed
                    if s.get("verity_brain", {}).get("grade") == "STRONG_BUY"
                    and s.get("verity_brain", {}).get("brain_score", 0) >= CLAUDE_MIN_BRAIN_SCORE
                ]
            else:
                claude_targets = [
                    s for s in analyzed
                    if s.get("verity_brain", {}).get("brain_score", 0) >= CLAUDE_MIN_BRAIN_SCORE
                ]
            claude_targets.sort(
                key=lambda s: s.get("verity_brain", {}).get("brain_score", 0),
                reverse=True,
            )
            claude_targets = claude_targets[:CLAUDE_TOP_N]
            claude_deep_calls = len(claude_targets)

            if claude_targets:
                gemini_map = {s["ticker"]: s for s in analyzed}
                with tracer.step("claude_deep_analysis"):
                    claude_results = analyze_batch_deep(claude_targets, gemini_map, macro)

                merged = 0
                overridden = 0
                disagreements = []
                for stock in analyzed:
                    cr = claude_results.get(stock["ticker"])
                    if cr and cr.get("_model"):
                        orig_rec = stock.get("recommendation", "WATCH")
                        merge_dual_analysis(stock, cr, model_weights=model_weights)
                        merged += 1
                        dc = stock.get("dual_consensus") or {}
                        has_disagreement = False
                        if dc.get("manual_review_required"):
                            disagreements.append({
                                "name": stock.get("name", "?"),
                                "ticker": stock.get("ticker", "?"),
                                "gemini_rec": dc.get("gemini_recommendation", orig_rec),
                                "claude_rec": dc.get("claude_recommendation", stock.get("recommendation", "?")),
                                "reason": f"수동검토 필요 ({dc.get('conflict_level', 'unknown')})",
                                "conflict_level": dc.get("conflict_level", "medium"),
                            })
                            has_disagreement = True
                        if cr.get("override_recommendation"):
                            overridden += 1
                            if not has_disagreement:
                                disagreements.append({
                                    "name": stock.get("name", "?"),
                                    "ticker": stock.get("ticker", "?"),
                                    "gemini_rec": orig_rec,
                                    "claude_rec": cr["override_recommendation"],
                                    "reason": cr.get("claude_verdict", ""),
                                    "conflict_level": dc.get("conflict_level", "medium"),
                                })
                        elif not cr.get("agrees_with_gemini"):
                            if not has_disagreement:
                                disagreements.append({
                                    "name": stock.get("name", "?"),
                                    "ticker": stock.get("ticker", "?"),
                                    "gemini_rec": orig_rec,
                                    "claude_rec": f"{orig_rec} (유지하되 반대)",
                                    "reason": cr.get("claude_verdict", ""),
                                    "conflict_level": dc.get("conflict_level", "medium"),
                                })

                total_tokens = sum(
                    (r.get("_input_tokens", 0) + r.get("_output_tokens", 0))
                    for r in claude_results.values()
                )
                claude_tokens_used += total_tokens
                print(f"  병합: {merged}종목 | 판정 변경: {overridden}건 | 총 {total_tokens:,}토큰")

                # Cross-Verification: AI 의견 분열 시 사장님께 즉시 알림
                if disagreements:
                    print(f"  ⚠️ AI 의견 분열 {len(disagreements)}건 → 텔레그램 알림")
                    send_cross_verification_alert(disagreements, model_weights)
                    portfolio["cross_verification"] = {
                        "disagreements": disagreements,
                        "total_analyzed": merged,
                        "override_count": overridden,
                        "weights_used": model_weights,
                        "checked_at": now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
                    }
            else:
                print(f"  Brain {CLAUDE_MIN_BRAIN_SCORE}점 이상 종목 없음 → 스킵")
        except Exception as e:
            print(f"  ⚠️ Claude 분석 스킵: {e}")

    # ── STEP 6.4: quick 전용 — Claude 라이트 검증 + Brain drift 체크 ──
    if mode == "quick" and CLAUDE_IN_QUICK and ANTHROPIC_API_KEY:
        print(f"\n[6.4] Claude 라이트 검증 (상위 {CLAUDE_QUICK_TOP_N}개) + Brain drift 체크")
        try:
            # 이전 full의 추천 결과에서 판정 맵 구성
            prev_rec_map = {
                r.get("ticker"): r.get("recommendation", "WATCH")
                for r in prev_recs_cache
            }
            prev_brain_map = {
                r.get("ticker"): r.get("verity_brain", {}).get("brain_score", 0)
                for r in prev_recs_cache
            }

            # 라이트 검증: Brain 상위 N개
            light_targets = sorted(
                analyzed,
                key=lambda s: s.get("verity_brain", {}).get("brain_score", 0),
                reverse=True,
            )[:CLAUDE_QUICK_TOP_N]
            claude_light_calls = len(light_targets)

            if light_targets:
                light_results = analyze_batch_light(light_targets, prev_rec_map)
                light_tokens = sum(
                    (r.get("_input_tokens", 0) + r.get("_output_tokens", 0))
                    for r in light_results.values()
                )
                claude_tokens_used += light_tokens
                changes = 0
                for stock in analyzed:
                    lr = light_results.get(stock.get("ticker"))
                    if lr and lr.get("alert_change") and lr.get("new_recommendation"):
                        stock["recommendation"] = lr["new_recommendation"]
                        stock["_recommendation_source"] = "claude_light_override"
                        changes += 1
                    if lr:
                        stock.setdefault("claude_analysis", {})["light"] = {
                            "verdict": lr.get("quick_verdict", ""),
                            "alert_change": lr.get("alert_change", False),
                            "watch_note": lr.get("watch_note", ""),
                        }
                print(f"  라이트 검증 완료: {len(light_results)}종목 | 판정 변경: {changes}건")

            # Brain drift 체크: 점수 10점 이상 변동 종목
            drift_count = 0
            for stock in analyzed:
                ticker = stock.get("ticker")
                prev_bs = prev_brain_map.get(ticker, 0)
                cur_bs = stock.get("verity_brain", {}).get("brain_score", 0)
                if abs(cur_bs - prev_bs) >= 10 and prev_bs > 0:
                    drift = check_brain_drift(stock, prev_bs, cur_bs)
                    if drift:
                        drift_count += 1
                        stock.setdefault("claude_analysis", {})["brain_drift"] = drift
                        if drift.get("alert_worthy"):
                            print(f"    ⚡ {stock.get('name')}: {prev_bs:.0f}→{cur_bs:.0f} | {drift.get('drift_cause', '')}")
            if drift_count:
                print(f"  Brain drift 분석: {drift_count}종목")
        except Exception as e:
            print(f"  ⚠️ Claude 라이트/drift 스킵: {e}")

    # ── STEP 6.5: full 전용 — AI 일일 리포트 (KR + US) ──
    if effective_mode == "full":
        print("\n[6.5] AI 일일 시장 리포트 (KR)")
        try:
            daily_report = generate_daily_report(
                macro=macro,
                candidates=analyzed,
                sectors=portfolio.get("sectors", []),
                headlines=portfolio.get("headlines", []),
                verity_brain=portfolio.get("verity_brain"),
                market="kr",
                event_insights=portfolio.get("event_insights"),
            )
            portfolio["daily_report"] = daily_report
            print(f"  KR 요약: {daily_report.get('market_summary', '?')[:60]}")
        except Exception as e:
            print(f"  KR 리포트 스킵: {e}")
            portfolio.setdefault("daily_report", {})

        print("\n[6.5b] AI 일일 시장 리포트 (US)")
        try:
            daily_report_us = generate_daily_report(
                macro=macro,
                candidates=analyzed,
                sectors=portfolio.get("sectors", []),
                headlines=portfolio.get("headlines", []),
                verity_brain=portfolio.get("verity_brain"),
                market="us",
                event_insights=portfolio.get("event_insights"),
            )
            portfolio["daily_report_us"] = daily_report_us
            print(f"  US 요약: {daily_report_us.get('market_summary', '?')[:60]}")
        except Exception as e:
            print(f"  US 리포트 스킵: {e}")
            portfolio.setdefault("daily_report_us", {})
    else:
        portfolio.setdefault("daily_report", {})
        portfolio.setdefault("daily_report_us", {})

    # ── STEP 7: VAMS ──
    print(f"\n[7] VAMS 가상 투자")
    portfolio["recommendations"] = analyzed

    def _profile_picks(stocks, profile):
        return [
            {"ticker": s["ticker"], "name": s["name"], "price": s.get("price"),
             "safety_score": s.get("safety_score", 0),
             "recommendation": s.get("recommendation"),
             "ai_verdict": s.get("ai_verdict", ""),
             "detected_risk_keywords": s.get("detected_risk_keywords", [])}
            for s in stocks
            if s.get("recommendation") in profile["recommendations"]
            and s.get("safety_score", 0) >= profile["min_safety"]
            and len(s.get("detected_risk_keywords") or []) <= profile["max_risk_keywords"]
        ][:profile["max_picks"]]

    portfolio["vams_profiles"] = {
        key: {**cfg, "picks": _profile_picks(analyzed, cfg)}
        for key, cfg in VAMS_PROFILES.items()
    }
    for k, v in portfolio["vams_profiles"].items():
        print(f"  [{k}] {v['label']} → {len(v['picks'])}종목")

    price_map = build_price_map(portfolio)
    for stock in analyzed:
        tnorm = str(stock["ticker"]).zfill(6)
        price_map.setdefault(tnorm, float(stock.get("price") or 0))

    active_profile = VAMS_PROFILES.get(VAMS_ACTIVE_PROFILE, VAMS_PROFILES["moderate"])
    print(f"  [VAMS] 활성 프로필: {VAMS_ACTIVE_PROFILE} ({active_profile['label']})")
    with tracer.step("vams_cycle"):
        portfolio, alerts = run_vams_cycle(portfolio, analyzed, price_map, profile=active_profile)
    tracer.log_vams_decision(alerts)

    # ── STEP 7.5: 안정 추천 (배당주 + 국채 파킹) ──
    print(f"\n[7.5] 안정 추천 생성")
    try:
        safe_recs = generate_safe_recommendations(analyzed, macro)
        portfolio["safe_recommendations"] = safe_recs
        div_count = safe_recs["total_safe_picks"]
        parking_msg = safe_recs["parking_options"]["message"]
        print(f"  배당주 {div_count}개 | {parking_msg}")
        if div_count > 0:
            top3 = [s["name"] for s in safe_recs["dividend_stocks"][:3]]
            print(f"  TOP3: {', '.join(top3)}")
    except Exception as e:
        print(f"  안정 추천 스킵: {e}")
        portfolio.setdefault("safe_recommendations", {})

    # ── STEP 8: 비서 브리핑 생성 ──
    print(f"\n[8] 비서 브리핑 생성")
    briefing = generate_briefing(portfolio)
    portfolio["briefing"] = briefing
    portfolio["alerts"] = briefing.get("alerts", [])
    print(f"  비서: {briefing['headline']}")
    print(f"  알림: CRITICAL {briefing['alert_counts']['critical']} | WARNING {briefing['alert_counts']['warning']} | INFO {briefing['alert_counts']['info']}")
    for item in briefing.get("action_items", []):
        print(f"  → {item}")

    print(f"\n[8.5] 꼬리위험 요약 (Gemini)")
    try:
        maybe_send_tail_risk_digest(portfolio)
    except Exception as e:
        print(f"  꼬리위험 스킵: {e}")

    # ── STEP 9: 저장 + 알림 ──
    print(f"\n[9] 저장 + 알림")
    try:
        from api.clients.perplexity_client import get_session_stats as _pplx_stats
        perplexity_call_count = _pplx_stats()["calls"]
    except Exception:
        pass
    run_stats = {
        "gemini_stock_calls": len(candidates) if effective_mode == "full" else 0,
        "gemini_report_calls": 2 if effective_mode == "full" else 0,
        "gemini_pro_calls": gemini_pro_calls,
        "claude_deep_calls": claude_deep_calls,
        "claude_light_calls": claude_light_calls,
        "claude_tokens": claude_tokens_used,
        "us_data_symbols": us_data_symbols_count,
        "us_data_requests_est": us_data_requests_est,
        "perplexity_calls": perplexity_call_count,
    }
    portfolio["cost_monitor"] = _build_cost_monitor(
        portfolio=portfolio,
        mode=mode,
        effective_mode=effective_mode,
        macro=macro,
        run_stats=run_stats,
    )
    cm = portfolio.get("cost_monitor", {})
    est = cm.get("estimated_cost", {})
    print(
        "  비용모니터: "
        f"{cm.get('month_key', '?')} "
        f"{est.get('total_krw', 0):,}원 "
        f"({est.get('progress_pct', 0)}%)"
    )
    save_portfolio(portfolio)

    tracer.log("final_recommendations_count", len(portfolio.get("recommendations", [])))
    tracer.log("final_candidates", [
        {"ticker": s.get("ticker"), "name": s.get("name"),
         "recommendation": s.get("recommendation"), "brain_score": s.get("verity_brain", {}).get("brain_score"),
         "grade": s.get("verity_brain", {}).get("grade"), "confidence": s.get("confidence"),
         "multi_score": s.get("multi_factor", {}).get("multi_score")}
        for s in analyzed
    ])

    vams = portfolio["vams"]
    print(f"  총자산: {vams['total_asset']:,.0f}원 | 수익률: {vams['total_return_pct']:+.2f}% | 보유: {len(vams['holdings'])}종목")

    if alerts:
        for a in alerts:
            print(f"  알림: {a['message']}")
        send_alerts(alerts)

    # ── STEP 9.5: 일일 아카이빙 (full + quick) ──
    if mode in ("full", "quick"):
        print(f"\n[9.5] 일일 스냅샷 아카이빙")
        try:
            path = archive_daily_snapshot(portfolio)
            cleanup_old_snapshots()
            print(f"  저장: {path}")
        except Exception as e:
            print(f"  아카이빙 스킵: {e}")

    # ── STEP 9.55: PDF 리포트 생성 (full) ──
    if effective_mode == "full":
        print(f"\n[9.55] PDF 리포트 생성")
        try:
            pdf_paths = generate_all_reports(portfolio)
            print(f"  PDF {len(pdf_paths)}건 생성 완료")
        except Exception as e:
            print(f"  PDF 생성 스킵: {e}")

    if effective_mode == "full":
        print(f"\n[9.6] 추천 성과 백테스트")
        try:
            bt_stats = evaluate_past_recommendations()
            portfolio["backtest_stats"] = bt_stats
            for period, info in bt_stats.get("periods", {}).items():
                if info.get("hit_rate") is not None:
                    print(f"  {period}: 적중률 {info['hit_rate']}% | 평균수익 {info['avg_return']}% | {info['total_recs']}종목")
        except Exception as e:
            print(f"  백테스트 스킵: {e}")

    # ── STEP 9.65: full 전용 — 저평가 발굴 (Value Hunter) ──
    if effective_mode == "full" and VALUE_HUNT_ENABLED:
        print(f"\n[9.65] 저평가 발굴 (Value Hunter)")
        try:
            vh_result = run_value_hunt(
                candidates=analyzed,
                backtest_stats=portfolio.get("backtest_stats"),
                macro=macro,
            )
            portfolio["value_hunt"] = vh_result
            if vh_result["gate_open"]:
                vc = vh_result["value_candidates"]
                print(f"  게이트 열림: {vh_result['gate_reason']}")
                print(f"  저평가 후보 {len(vc)}개 / 전체 검토 {vh_result['total_scored']}개")
            else:
                print(f"  게이트 닫힘: {vh_result['gate_reason']}")
        except Exception as e:
            print(f"  Value Hunter 스킵: {e}")
            portfolio.setdefault("value_hunt", {"gate_open": False, "gate_reason": str(e), "value_candidates": []})

    # ── STEP 9.7: VAMS 시뮬레이션 누적 통계 갱신 ──
    print(f"\n[9.7] VAMS 시뮬레이션 누적 통계")
    try:
        _update_simulation_stats(portfolio)
        sim = portfolio["vams"].get("simulation_stats", {})
        print(f"  총 매매: {sim.get('total_trades', 0)}회 | 승률: {sim.get('win_rate', 0):.1f}%")
        print(f"  최고 자산: {sim.get('peak_asset', 0):,.0f}원 | MDD: {sim.get('max_drawdown_pct', 0):.1f}%")
    except Exception as e:
        print(f"  시뮬레이션 통계 스킵: {e}")

    # ── STEP 9.8: AI 소스별 성과 리더보드 (full 모드) ──
    if effective_mode == "full":
        print(f"\n[9.8] AI 소스별 리더보드")
        try:
            from api.intelligence.ai_leaderboard import compute_ai_leaderboard
            lb = compute_ai_leaderboard(window_days=30)
            portfolio["ai_leaderboard"] = lb
            for src in lb.get("by_source", []):
                print(f"  {src['source']}: {src['n']}건 | 적중 {src['hit_rate']}% | 평균 {src['avg_return']}%")
            if lb.get("suggested_note"):
                print(f"  → {lb['suggested_note']}")
        except Exception as e:
            print(f"  AI 리더보드 스킵: {e}")

    # ── STEP 10: AI 오심 포스트모텀 (full 모드, 주 1회 수준) ──
    if effective_mode == "full" and POSTMORTEM_ENABLED:
        print(f"\n[10] AI 오심 포스트모텀")
        try:
            from api.intelligence.postmortem import generate_postmortem
            postmortem = generate_postmortem(days=7)
            portfolio["postmortem"] = postmortem
            if postmortem.get("failures"):
                print(f"  오심 {postmortem['analyzed_count']}건 분석 완료")
                print(f"  교훈: {postmortem.get('lesson', '없음')[:80]}")
                send_postmortem_report(postmortem)
            else:
                print(f"  최근 7일 유의미한 오심 없음")
        except Exception as e:
            print(f"  포스트모텀 스킵: {e}")

    # ── STEP 10.5: Brain V2 전략 진화 (full 모드) ──
    if effective_mode == "full" and STRATEGY_EVOLUTION_ENABLED and ANTHROPIC_API_KEY:
        print(f"\n[10.5] Brain V2 전략 진화")
        try:
            from api.intelligence.strategy_evolver import run_evolution_cycle
            evolution_result = run_evolution_cycle(portfolio)
            portfolio["strategy_evolution"] = evolution_result
            status = evolution_result.get("status", "?")
            print(f"  결과: {status}")
            if status == "pending_approval":
                print(f"  → 텔레그램 승인 대기 중")
            elif status == "auto_applied":
                print(f"  → 자동 적용 완료 (v{evolution_result.get('new_version', '?')})")
            elif status == "no_change":
                print(f"  → Claude: 현행 유지 ({evolution_result.get('reason', '')[:60]})")
        except Exception as e:
            print(f"  전략 진화 스킵: {e}")

    # ── STEP 10.55: 대안 데이터 수집 (full 모드) ──
    # NOTE: alt_data는 UI·아카이브 전용. 현재 추천/브레인 점수에 직접 반영되지 않음.
    if effective_mode == "full":
        print(f"\n[10.55] 대안 데이터 수집 (QuiverQuant/French/EIA/SOV) [UI·아카이브용]")
        try:
            from api.collectors.alt_data_collectors import collect_all_alt_data
            us_tickers = [
                s.get("ticker") for s in candidates
                if s.get("currency") == "USD" and s.get("ticker")
            ][:10]
            alt = collect_all_alt_data(us_tickers=us_tickers)
            portfolio["alt_data"] = alt
            active = alt.get("active_sources", 0)
            total = alt.get("total_sources", 0)
            print(f"  대안 데이터: {active}/{total} 소스 활성")
            congress = alt.get("sources", {}).get("congress_trades", {})
            if congress.get("ok"):
                top3 = ", ".join(b["ticker"] for b in congress.get("top_buys", [])[:3])
                print(f"  의회 매매 TOP: {top3} ({congress.get('buy_count', 0)}건 매수)")
            ff = alt.get("sources", {}).get("fama_french", {})
            if ff.get("ok"):
                avg = ff.get("recent_60d_avg", {})
                smb = avg.get("SMB", "?")
                hml = avg.get("HML", "?")
                print(f"  Fama-French 60d: SMB={smb} HML={hml}")
        except Exception as e:
            print(f"  대안 데이터 스킵: {e}")
            portfolio.setdefault("alt_data", {})

    # ── STEP 10.6: 퀀트 — 페어 트레이딩 스캔 + 팩터 IC 분석 (full 모드) ──
    if effective_mode == "full":
        print(f"\n[10.6] 퀀트 엔진 — 페어 스캔 + 팩터 IC")
        try:
            from api.quant.pairs.pair_scanner import scan_all_sectors
            pair_result = scan_all_sectors()
            portfolio["stat_arb"] = {
                "total_pairs": pair_result.get("total_pairs", 0),
                "actionable_pairs": pair_result.get("actionable_pairs", []),
                "by_sector": pair_result.get("by_sector", {}),
                "updated_at": now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
            }
            n_pairs = pair_result.get("total_pairs", 0)
            n_action = len(pair_result.get("actionable_pairs", []))
            print(f"  공적분 페어: {n_pairs}쌍 | 매매 시그널: {n_action}건")
            for ap in pair_result.get("actionable_pairs", [])[:3]:
                print(f"    {ap['name_a']}↔{ap['name_b']} Z={ap['spread_zscore']:.2f} ({ap['spread_signal']})")
        except Exception as e:
            print(f"  페어 스캔 스킵: {e}")
            portfolio.setdefault("stat_arb", {})

        try:
            from api.quant.alpha.alpha_scanner import (
                scan_all_factors_multi_window, compute_monthly_rollup,
            )
            mw_result = scan_all_factors_multi_window([7, 14, 30])
            ic_scan = (mw_result.get("windows", {}).get("7")
                       or mw_result.get("windows", {}).get("14")
                       or {})
            if ic_scan.get("status") == "ok":
                monthly = compute_monthly_rollup(30)
                portfolio["factor_ic"] = {
                    "ranking": ic_scan.get("ranking", [])[:10],
                    "significant_factors": ic_scan.get("significant_factors", []),
                    "decaying_factors": ic_scan.get("decaying_factors", []),
                    "updated_at": ic_scan.get("scanned_at"),
                    "monthly_rollup": monthly,
                    "windows_available": list(mw_result.get("windows", {}).keys()),
                }
                sig = ic_scan.get("significant_factors", [])
                dec = ic_scan.get("decaying_factors", [])
                windows_ok = [w for w, r in mw_result.get("windows", {}).items()
                              if isinstance(r, dict) and r.get("status") == "ok"]
                print(f"  팩터 IC: 유의미 {len(sig)}개 ({', '.join(sig[:5]) or '없음'}) | 붕괴 {len(dec)}개 | 윈도우: {','.join(windows_ok)}d")
                if monthly.get("by_factor"):
                    top3 = ", ".join(f["factor"] for f in monthly["by_factor"][:3])
                    print(f"  월간 롤업: {monthly.get('obs_entries', 0)}일 기준 | 상위: {top3}")
            else:
                print(f"  IC 스캔: {ic_scan.get('status', '?')}")
        except Exception as e:
            print(f"  IC 스캔 스킵: {e}")
            portfolio.setdefault("factor_ic", {})

        # NOTE: verification_report는 사후 검증용 아카이브. 실시간 판단에 역류하지 않음.
        try:
            from api.intelligence.backtest_archive import generate_verification_report
            vr = generate_verification_report()
            portfolio["verification_report"] = vr
            loop = vr.get("feedback_loop_status", "open")
            adj_cnt = len(vr.get("ic_adjustments_active", []))
            perf = vr.get("performance", {})
            print(f"  검증 리포트: 루프={loop} | IC 조정 {adj_cnt}건 | "
                  f"적중률 7d={perf.get('hit_rate_7d', '?')}% 14d={perf.get('hit_rate_14d', '?')}%")
        except Exception as e:
            print(f"  검증 리포트 스킵: {e}")

    # ── STEP 10.7: Claude 모닝 전략 코멘트 (full 모드) ──
    if effective_mode == "full" and CLAUDE_MORNING_STRATEGY and ANTHROPIC_API_KEY:
        print(f"\n[10.7] Claude 모닝 전략 코멘트 생성")
        try:
            morning = generate_morning_strategy(portfolio)
            if morning:
                portfolio["claude_morning_strategy"] = morning
                scenario = morning.get("scenario", "")
                print(f"  시나리오: {scenario[:80]}")
                top_comment = morning.get("top_pick_comment", "")
                if top_comment:
                    print(f"  주목 종목: {top_comment[:80]}")
            else:
                print(f"  Claude 모닝 전략 생성 실패 (API 오류)")
        except Exception as e:
            print(f"  모닝 전략 스킵: {e}")

    # ── STEP 11: 텔레그램 봇 — 대기 중인 질문 응답 ──
    print(f"\n[11] 텔레그램 봇 폴링")
    try:
        run_poll_once()
    except Exception as e:
        print(f"  봇 폴링 스킵: {e}")

    # ── STEP 12: 리포트 전송 (시간 체크 + full 모드) ──
    if effective_mode == "full":
        now = now_kst()
        scheduled_ok = (
            now.hour > REPORT_SEND_HOUR_KST
            or (now.hour == REPORT_SEND_HOUR_KST and now.minute >= REPORT_SEND_MINUTE_KST)
        )
        if scheduled_ok:
            print(f"\n[12] 일일 리포트 전송 (KST {REPORT_SEND_HOUR_KST}:{REPORT_SEND_MINUTE_KST:02d} 이후)")
            send_daily_report(portfolio)
            send_vams_simulation_report(portfolio)
        else:
            print(f"\n[12] 리포트 전송 대기 (현재 {now.strftime('%H:%M')} < 설정 {REPORT_SEND_HOUR_KST}:{REPORT_SEND_MINUTE_KST:02d})")

        save_portfolio(portfolio)
        print(f"\n✅ 전체 분석 완료!")
    else:
        # ── 모닝 브리핑: quick 모드에서 KST 08:00~08:14 사이에 전송 ──
        now = now_kst()
        is_morning_window = (
            (now.hour == MORNING_BRIEF_HOUR_KST and now.minute >= MORNING_BRIEF_MINUTE_KST)
            and (now.hour == MORNING_BRIEF_HOUR_KST and now.minute < MORNING_BRIEF_MINUTE_KST + 15)
        )
        if is_morning_window and now.weekday() < 5:
            print(f"\n[12] 모닝 브리핑 전송 (KST {now.strftime('%H:%M')})")
            try:
                send_morning_briefing(portfolio)
            except Exception as e:
                print(f"  모닝 브리핑 스킵: {e}")

        print(f"\n✅ 빠른 분석 완료!")

    # ── 실행 추적 아카이브 저장 ──
    tracer.log("cost_monitor", portfolio.get("cost_monitor", {}))
    trace_path = tracer.end()
    if trace_path:
        print(f"  📦 실행 추적: {trace_path}")


if __name__ == "__main__":
    main()
