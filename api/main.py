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
    VERITY_MODE,
    VERITY_STAGING_REAL_KEYS,
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
from api.analyzers.stock_filter import run_filter_pipeline, run_filter_pipeline_with_ramp_up
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
    save_portfolio as _orig_save_portfolio,
    run_vams_cycle,
    recalculate_total,
    portfolio_lock,
)


# ────────────────────────────────────────────────────────────
# Graceful SIGTERM handler — watchdog 발동 시 partial portfolio 보호 (2026-05-10)
# ────────────────────────────────────────────────────────────
# 5/10 1500 stage SIGTERM (1h 23m, watchdog 82분 발동) 직후 portfolio.json
# 변화 0건 = 다음 cron 의 stale 데이터 risk. graceful save 추가해 partial 보호.
_latest_portfolio_ref = None


def save_portfolio(portfolio: dict):
    """save_portfolio wrapper — 매 호출 마다 module-level ref 갱신 + 원본 atomic save.

    2026-05-17 C3 audit: system_health 만 별도 snapshot 도 작성. SystemHealthBar 가 425KB
    portfolio.json 통째 fetch 대신 ~5KB lite snapshot 사용 → 매 5분 polling 비용 ~98% 감소.
    silent skip 차단 — 실패 시 stderr (portfolio 저장 자체는 영향 X).
    """
    global _latest_portfolio_ref
    _latest_portfolio_ref = portfolio
    # 계좌 라우팅 부착 (일반 vs ISA 자체 인지, 표시용 — 자동주문 X). 실패해도 저장 영향 X.
    try:
        from api.trading.account_profile import annotate_recommendations
        for _rk in ("recommendations", "safe_recommendations"):
            if isinstance(portfolio.get(_rk), list):
                portfolio[_rk] = annotate_recommendations(portfolio[_rk])
    except Exception as _e:
        import sys as _sys
        _sys.stderr.write(f"[account_route] annotate FAIL (무시): {_e}\n")
    rv = _orig_save_portfolio(portfolio)
    # system_health snapshot 별도 publish (SystemHealthBar lite source)
    try:
        sh = portfolio.get("system_health")
        if isinstance(sh, dict):
            import json as _json, os as _os, sys as _sys
            snap_path = _os.path.join(DATA_DIR, "system_health_snapshot.json")
            tmp = snap_path + ".tmp"
            snap_payload = {
                "system_health": sh,
                "updated_at": portfolio.get("updated_at"),
                "schema_version": "1.0",
                "source": "main.py save_portfolio (C3 split)",
            }
            with open(tmp, "w", encoding="utf-8") as _f:
                _json.dump(snap_payload, _f, ensure_ascii=False, indent=2, default=str)
            _os.replace(tmp, snap_path)
    except Exception as _e:
        import sys as _sys
        _sys.stderr.write(f"[system_health_snapshot] write FAIL (무시): {_e}\n")
    return rv


def _on_sigterm(signum, frame):  # noqa: ARG001
    """watchdog SIGTERM → partial portfolio 저장 + 텔레그램 alert + exit 1.

    silent skip 절대 금지 — stderr/stdout 명시.
    """
    import sys as _sys
    _sys.stderr.write("\n[graceful_sigterm] SIGTERM received — partial portfolio save 시도\n")
    saved = False
    if _latest_portfolio_ref is not None:
        try:
            _orig_save_portfolio(_latest_portfolio_ref)
            saved = True
            _sys.stderr.write("[graceful_sigterm] partial portfolio.json 저장 OK\n")
        except Exception as e:
            _sys.stderr.write(f"[graceful_sigterm] partial save FAIL: {e}\n")
    else:
        _sys.stderr.write("[graceful_sigterm] _latest_portfolio_ref None — save 스킵 (early SIGTERM)\n")

    # 🚨 미처리 신고 (2026-08-13) — 끊긴 자리에서 무엇이 얼마나 안 됐는지 남긴다.
    #   8/13 run 31745952833 은 Gemini 16/50 에서 죽어 34종목이 AI 종합 없이 남았는데, 발행은
    #   정상 완료해 data_health 가 green 이었다. 결손이 초록불 뒤에 숨는 게 진짜 문제라
    #   예산을 손대기 전에 먼저 보이게 만든다. 신고만 하고 판정·수정은 하지 않는다.
    shortfall_text = ""
    try:
        from api.observability import run_progress as _rp
        shortfall_text = _rp.format_shortfall()
        _sys.stderr.write(f"[graceful_sigterm] {shortfall_text}\n")
        _rp.append_cutoff_row(extra={"partial_portfolio_saved": saved})
    except Exception as e:
        _sys.stderr.write(f"[graceful_sigterm] shortfall 신고 FAIL: {e}\n")

    # 텔레그램 알람 (bypass_quiet — critical)
    try:
        from api.notifications.telegram import send_message
        send_message(
            f"⚠️ <b>VERITY 런타임 한계</b>\n"
            f"watchdog SIGTERM 발동 — partial portfolio {'저장' if saved else '미저장'}\n"
            + (f"{shortfall_text}\n" if shortfall_text else "")
            + f"즉시 root cause 진단 필요 (data/metadata/runtime_cutoff.jsonl · runtime_load_log.jsonl)",
            bypass_quiet=True,
            dedupe=False,
        )
    except Exception as e:
        _sys.stderr.write(f"[graceful_sigterm] telegram alert FAIL: {e}\n")

    _sys.exit(1)


import signal as _signal
_signal.signal(_signal.SIGTERM, _on_sigterm)
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
from api.intelligence.alert_engine import generate_briefing, build_geopolitical_hotspots
from api.intelligence.verity_brain import analyze_all as verity_brain_analyze
# scout_reports / run_report_summarizer 는 2026-08-14 에 scripts/analyst_reports_cron.py 로
# 옮겼다(STEP 5.87 분리). 여기서 다시 import 하지 말 것 — 인라인 재수집이 부활하면
# 51분이 파이프라인으로 되돌아와 워치독 110분 초과가 재발한다.
from api.analyzers.dart_report_analyzer import analyze_all_business_reports
from api.intelligence.periodic_report import generate_periodic_analysis, compute_sector_trend_summary
from api.workflows.archiver import archive_daily_snapshot, cleanup_old_snapshots
from api.workflows.brain_history import (
    save_brain_snapshot,
    cleanup_old_brain_snapshots,
    backfill_actual_returns,
)
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
    """관심종목 중 후보에 없는 것을 추가. 반환: 추가된 수.

    🚨 오염 수정 파이프 (2026-08-04 PM 승인) — 관심종목 유래 레코드 2결함 원천 수정:
    ① KR 전 종목 `.KS` 강제 → 코스닥(예: 094970 제이엠티)이 KOSPI 로 오조회.
       시장 오표기 + yfinance 응답 이상 → **펀더멘털 0-채움**(F-Score 1/9 왜곡 사고)의 뿌리.
       kr_listed.json(KP/KQ/KN) 으로 접미사·시장 라벨 결정.
    ② name 오염("094970.KS,0P0000EOZ4,42992") → kr_stock_names 정규화 + 콤마 최종 차단.
       오염 name 은 집행 게이트 E4 자동 제외·중용 오배제(JMT "고부채 극단" 사고)의 원인.
    """
    from api.collectors.stock_data import get_stock_data
    _sfx = {"KP": ".KS", "KQ": ".KQ", "KN": ".KQ"}
    _mkt_label = {"KP": "KOSPI", "KQ": "KOSDAQ", "KN": "KONEX"}
    try:
        with open(os.path.join(DATA_DIR, "kr_listed.json"), encoding="utf-8") as _f:
            _listed = json.load(_f)
    except Exception:
        _listed = {}
    try:
        with open(os.path.join(DATA_DIR, "kr_stock_names.json"), encoding="utf-8") as _f:
            _kr_names = json.load(_f)
    except Exception:
        _kr_names = {}

    existing = {s.get("ticker") for s in candidates}
    added = 0
    for wi in watch_items:
        ticker = (wi.get("ticker") or "").strip()
        if not ticker or ticker in existing:
            continue
        mkt = (wi.get("market") or "kr").lower()
        is_us = mkt == "us"
        _li = _listed.get(ticker) if isinstance(_listed, dict) else None
        _kr_mkt = (_li or {}).get("market")
        ticker_yf = ticker if is_us else f"{ticker}{_sfx.get(_kr_mkt, '.KS')}"
        data = get_stock_data(ticker_yf, period="1y")
        if data:
            if not is_us:
                _clean = (_kr_names.get(ticker) if isinstance(_kr_names, dict) else None) \
                    or (_li or {}).get("name")
                if _clean:
                    data["name"] = _clean
                if _kr_mkt in _mkt_label:
                    data["market"] = _mkt_label[_kr_mkt]
            if "," in str(data.get("name") or ""):
                # 정규화 실패 시에도 콤마 오염은 절대 통과 금지 — 티커로 대체
                data["name"] = ticker
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

    # 2026-06-10: 루프 전체 누적 예산 + fail-fast circuit breaker (realtime watchdog SIGTERM 재발 방어).
    #   6/9 per-ticker 8s cap 은 단일 ticker 무한 hang 만 막음 — 데이터 소스 전역 저하 시 N×(KIS 10s + yf 8s)
    #   누적이 10분 예산 초과 → 첫 save_portfolio 전 early SIGTERM(portfolio 미저장) 재발.
    #   사고: 6/10 00:30(US, yf) + 6/10 11:30(KR, 동일 early-SIGTERM/미저장) — US/KR 공통.
    #   KIS 경로(get_current_price)도 _get(requests timeout=10) 로 단건은 유한하나 N 누적은 무가드였음.
    #   대책: KIS+yf 통합 — (1) 루프 누적 wall-clock 이 _PRICE_BUDGET 초과 시 중단, (2) 가격 획득 실패(KIS·yf
    #         모두) 연속 ≥ _PRICE_BREAKER 면 소스 전역 다운 간주 → 잔여 ticker skip + 부분 price_map 반환
    #         (→ graceful save). silent skip 금지 — stderr 명시 (feedback_data_collection_verification_mandatory).
    _PRICE_BUDGET = 120.0   # build_price_map 누적 상한(초). 10분 예산 중 8분 이상을 잔여 파이프라인에 보존.
    _PRICE_BREAKER = 4      # 연속 가격획득 실패 임계. 소스 전역 다운 시 조기 차단 (vs 무가드 N×수십초).
    price_map = {}
    _loop_start = time.monotonic()
    _consecutive_fail = 0
    _circuit_open = False
    for t, yf_t, is_us in entries:
        if _circuit_open:
            continue  # circuit open — 잔여 ticker 가격 호출 skip (부분 반환)
        if time.monotonic() - _loop_start >= _PRICE_BUDGET:
            _circuit_open = True
            sys.stderr.write(
                f"[build_price_map] ⏱ 누적 예산 초과 ({time.monotonic() - _loop_start:.0f}s ≥ "
                f"{_PRICE_BUDGET:.0f}s) — 잔여 ticker skip, 부분 price_map({len(price_map)}) 반환 "
                f"(watchdog SIGTERM 방어)\n"
            )
            continue
        got = False
        if not is_us and kis_broker:
            try:
                snap = kis_broker.get_current_price(t)  # _get: requests timeout=10
                p = int(snap.get("stck_prpr", 0) or 0)
                if p > 0:
                    price_map[t] = float(p)
                    got = True
            except Exception:
                pass
        if not got:
            # 2026-06-09: per-ticker safe_collect 래핑 (8s thread cap). yfinance socket hang(fast_info/
            #   history)이 무로그 무한 대기로 예산 소진 → SIGTERM. safe_yf_call 은 예외(429)만 잡고 소켓
            #   hang 은 못 막음 → ThreadPoolExecutor timeout 으로 캡. default=0.0 (이후 >0 게이트).
            p = safe_collect(get_equity_last_price, yf_t, name=f"yf_price:{yf_t}", timeout=8, default=0.0)
            if p is not None and p > 0:
                price_map[t] = float(p)
                got = True
        if got:
            _consecutive_fail = 0
        else:
            _consecutive_fail += 1
            if _consecutive_fail >= _PRICE_BREAKER:
                _circuit_open = True
                sys.stderr.write(
                    f"[build_price_map] ⚡ circuit breaker open — 가격획득 연속 {_consecutive_fail}회 실패 "
                    f"(소스 전역 저하 추정). 잔여 ticker skip, 부분 price_map({len(price_map)}) 반환\n"
                )
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

        try:
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
            # 2026-05-19 C2 — US 종목 fallback path 에 equity_research_brief 전달.
            cblock = build_consensus_block(
                raw_c, price_c, flow, ex_map.get(str(ticker).zfill(6)),
                equity_research_brief=stock.get("equity_research_brief"),
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
                bond_regime=(portfolio.get("bonds") or {}).get("bond_regime"),
            )
            stock["multi_factor"] = mf
            cs_note = f"컨센서스 {cblock.get('consensus_score', 50)}점 ({cblock.get('score_source', '?')})"
            print(f"      종합: {mf['multi_score']}점 ({mf['grade']}) | {cs_note} | 시그널: {', '.join(mf['all_signals'][:3]) or '없음'}")
        except Exception as _loop_err:
            print(f"      ❌ 분석 실패(스킵): {_loop_err}")
            stock.setdefault("technical", {"rsi": None, "signals": [], "technical_score": 50})
            stock.setdefault("sentiment", {"score": 50, "positive": 0, "negative": 0, "neutral": 0, "headline_count": 0, "top_headlines": [], "detail": []})
            stock.setdefault("flow", {"flow_score": 50, "flow_signals": []})
            stock.setdefault("consensus", {})
            stock.setdefault("multi_factor", {"multi_score": 50, "grade": "N/A", "all_signals": []})
            continue

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
                "periodic_daily", "periodic_semi", "periodic_annual",
                "daily_admin_v2", "daily_public_v2",
                "weekly_admin_v2", "weekly_public_v2",
                "monthly_admin_v2", "monthly_public_v2",
                "quarterly_admin_v2", "quarterly_public_v2",
                "semi_admin_v2", "semi_public_v2",
                "annual_admin_v2", "annual_public_v2"):
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


def _compute_brain_quality(brain_acc: dict, period: str = "weekly") -> dict:
    """Brain 시스템의 품질을 0~100 종합 점수로 산출 (`portfolio["brain_quality"]`).

    구성 (총 100점):
      - 양성 등급 (STRONG_BUY/BUY) 가중 hit_rate           : 40점
      - AVOID 회피 효과 (avg_return 음수일수록 +)            : 30점
      - 등급 분리도 (STRONG_BUY avg − AVOID avg, %p)       : 30점

    표본 부족 시 status='insufficient_data' + score=None 반환 (오해 방지).
    """
    grades = (brain_acc or {}).get("grades") or {}
    if not grades:
        return {"score": None, "status": "no_data", "components": {}, "period": period}

    sb = grades.get("STRONG_BUY") or {}
    buy = grades.get("BUY") or {}
    avoid = grades.get("AVOID") or {}

    sb_n = int(sb.get("count", 0) or 0)
    buy_n = int(buy.get("count", 0) or 0)
    avoid_n = int(avoid.get("count", 0) or 0)
    total_pos = sb_n + buy_n
    total_n = total_pos + avoid_n

    # 표본 < 5: 점수 의미 없음
    if total_n < 5:
        return {
            "score": None,
            "status": "insufficient_data",
            "components": {},
            "period": period,
            "note": f"표본 {total_n}건 — 5건 이상 누적 필요",
        }

    # 1) 양성 가중 적중률 (40점)
    if total_pos:
        weighted_hit = (
            float(sb.get("hit_rate", 0)) * sb_n
            + float(buy.get("hit_rate", 0)) * buy_n
        ) / total_pos
        positive_score = round(weighted_hit / 100 * 40, 1)
    else:
        weighted_hit = 0.0
        positive_score = 20.0  # BUY/STRONG_BUY 표본 없음 → 중립 가산

    # 2) AVOID 회피 (30점, avg_return -10%면 만점)
    if avoid_n:
        avoid_avg = float(avoid.get("avg_return", 0))
        avoid_score = max(0.0, min(30.0, (5.0 - avoid_avg) / 15.0 * 30.0))
    else:
        avoid_avg = None
        avoid_score = 15.0  # 표본 없음 → 중립

    # 3) 등급 분리도 (30점, STRONG_BUY avg − AVOID avg 가 30%p+ 면 만점)
    if sb_n and avoid_n:
        spread = float(sb.get("avg_return", 0)) - avoid_avg
        sep_score = max(0.0, min(30.0, spread / 30.0 * 30.0))
    else:
        spread = None
        sep_score = 0.0

    total_score = round(positive_score + avoid_score + sep_score, 1)
    return {
        "score": total_score,
        "status": "ok",
        "period": period,
        "components": {
            "positive_hit_rate_score": positive_score,
            "avoid_avoidance_score": round(avoid_score, 1),
            "grade_separation_score": round(sep_score, 1),
        },
        "metrics": {
            "total_samples": total_n,
            "strong_buy_n": sb_n,
            "buy_n": buy_n,
            "avoid_n": avoid_n,
            "weighted_positive_hit_rate": round(weighted_hit, 1),
            "avoid_avg_return": avoid_avg,
            "grade_spread_pp": round(spread, 1) if spread is not None else None,
        },
    }


def _release_gate_check(portfolio, label: str) -> bool:
    """v2 PDF 생성 직전 Trust gate (Phase 4).

    verdict == 'hold'         → 차단 + Telegram 알림 → False
    verdict == 'manual_review' → 진행 + 검수 알림 → True
    그 외/실패              → 진행 → True (가드 정책: 게이트 실패가 차단 사유 X)
    """
    try:
        from api.observability import check_release_gate
        gate = check_release_gate(portfolio)
        verdict = gate.get("verdict", "unknown")
        sat, tot = gate.get("satisfied"), gate.get("total")
        print(f"  🛡 Release gate: {verdict} ({sat}/{tot})")

        if verdict == "manual_review":
            try:
                from api.notifications.telegram import send_message
                send_message(
                    f"⚠️ <b>{label}</b> 발행됨 (검수 필요)\n사유: {gate.get('reason', '')}",
                    dedupe=True,
                )
            except Exception:
                pass

        if not gate.get("allow", True):
            blocking = (gate.get("blocking") or [])[:5]
            try:
                from api.notifications.telegram import send_message
                msg = (f"🔴 <b>{label}</b> 발행 차단\n"
                       f"사유: {gate.get('reason', '')}\n"
                       f"미충족: {', '.join(blocking)[:300]}")
                send_message(msg, dedupe=True, bypass_quiet=True)
            except Exception:
                pass
            print(f"  ⛔ PDF 생성 차단: {gate.get('reason')}")
            return False
        return True
    except Exception as e:
        print(f"  ⚠️ release gate 검사 실패 (PDF 진행): {e}")
        return True


def _run_daily_admin_v2():
    """Daily 관리자 7장 PDF 생성. cron 또는 CLI 트리거."""
    from api.reports.daily_admin_pdf import generate_daily_admin_pdf_v2
    print(f"\n{'=' * 60}")
    print(f"  VERITY — Daily 관리자 리포트 v2 (7장)")
    print(f"  실행 시각: {now_kst().strftime('%Y-%m-%d %H:%M:%S KST')}")
    print(f"{'=' * 60}")
    portfolio = load_portfolio()
    if not _release_gate_check(portfolio, "Daily 관리자"):
        return
    try:
        path = generate_daily_admin_pdf_v2(portfolio)
        print(f"  ✓ PDF 생성: {path}")
    except Exception as e:
        print(f"  ⚠️ PDF 생성 실패: {e}")
        import traceback; traceback.print_exc()


def _run_daily_public_v2():
    """Daily 일반인 5섹션 PDF 생성. cron 또는 CLI 트리거."""
    from api.reports.daily_public import generate_daily_public_text
    from api.reports.daily_public_pdf import generate_daily_public_pdf
    print(f"\n{'=' * 60}")
    print(f"  VERITY — Daily 일반인 리포트 v2 (5섹션)")
    print(f"  실행 시각: {now_kst().strftime('%Y-%m-%d %H:%M:%S KST')}")
    print(f"{'=' * 60}")
    portfolio = load_portfolio()
    if not _release_gate_check(portfolio, "Daily 일반인"):
        return
    try:
        content = generate_daily_public_text(portfolio, channel="public")
        path = generate_daily_public_pdf(content)
        print(f"  ✓ PDF 생성: {path}")
        print(f"  cover: {content.get('cover')}")
        print(f"  grade: {content.get('metadata', {}).get('grade_raw')}")
        print(f"  watermark: {content.get('metadata', {}).get('watermark', '')}")
    except Exception as e:
        print(f"  ⚠️ PDF 생성 실패: {e}")
        import traceback; traceback.print_exc()


def _run_long_horizon_v2(period: str, kind: str):
    """Monthly/Quarterly/Semi/Annual 통합 트리거. kind = 'admin' | 'public'."""
    from api.intelligence.periodic_report import generate_periodic_analysis
    label = {"monthly": "월간", "quarterly": "분기", "semi": "반기", "annual": "연간"}.get(period, period)
    print(f"\n{'=' * 60}")
    print(f"  VERITY — {label} {kind} 리포트 v2")
    print(f"  실행 시각: {now_kst().strftime('%Y-%m-%d %H:%M:%S KST')}")
    print(f"{'=' * 60}")
    portfolio = load_portfolio()
    if not _release_gate_check(portfolio, f"{label} {kind}"):
        return
    try:
        analysis = generate_periodic_analysis(period)
        if analysis.get("status") == "no_data":
            print(f"  ⚠️ {analysis['message']}")
            return

        if kind == "admin":
            if period == "monthly":
                from api.reports.monthly_admin_pdf import generate_monthly_admin_pdf
                path = generate_monthly_admin_pdf(analysis, portfolio)
            else:
                from api.reports.long_horizon_admin import (
                    generate_quarterly_admin_pdf, generate_semi_admin_pdf,
                    generate_annual_admin_pdf,
                )
                gen = {"quarterly": generate_quarterly_admin_pdf,
                       "semi": generate_semi_admin_pdf,
                       "annual": generate_annual_admin_pdf}[period]
                path = gen(analysis, portfolio)
        else:  # public
            from api.reports.long_horizon_public import (
                generate_monthly_public_text, generate_monthly_public_pdf,
                generate_quarterly_public_text, generate_quarterly_public_pdf,
                generate_semi_public_text, generate_semi_public_pdf,
                generate_annual_public_text, generate_annual_public_pdf,
            )
            gen_text = {"monthly": generate_monthly_public_text,
                        "quarterly": generate_quarterly_public_text,
                        "semi": generate_semi_public_text,
                        "annual": generate_annual_public_text}[period]
            gen_pdf = {"monthly": generate_monthly_public_pdf,
                       "quarterly": generate_quarterly_public_pdf,
                       "semi": generate_semi_public_pdf,
                       "annual": generate_annual_public_pdf}[period]
            content = gen_text(analysis, portfolio, channel="public")
            path = gen_pdf(content)
            print(f"  cover: {content.get('cover')}")
            print(f"  watermark: {content.get('metadata', {}).get('watermark', '')}")

        print(f"  ✓ PDF 생성: {path}")
    except Exception as e:
        print(f"  ⚠️ PDF 생성 실패: {e}")
        import traceback; traceback.print_exc()


def _run_weekly_admin_v2():
    """Weekly 관리자 6장 PDF."""
    from api.intelligence.periodic_report import generate_periodic_analysis
    from api.reports.weekly_admin_pdf import generate_weekly_admin_pdf
    print(f"\n{'=' * 60}")
    print(f"  VERITY — Weekly 관리자 리포트 v2 (6장)")
    print(f"  실행 시각: {now_kst().strftime('%Y-%m-%d %H:%M:%S KST')}")
    print(f"{'=' * 60}")
    portfolio = load_portfolio()
    if not _release_gate_check(portfolio, "Weekly 관리자"):
        return
    try:
        analysis = generate_periodic_analysis("weekly")
        if analysis.get("status") == "no_data":
            print(f"  ⚠️ {analysis['message']}")
            return
        path = generate_weekly_admin_pdf(analysis, portfolio)
        print(f"  ✓ PDF 생성: {path}")
    except Exception as e:
        print(f"  ⚠️ PDF 생성 실패: {e}")
        import traceback; traceback.print_exc()


def _run_weekly_public_v2():
    """Weekly 일반인 4섹션 PDF."""
    from api.intelligence.periodic_report import generate_periodic_analysis
    from api.reports.weekly_public import (
        generate_weekly_public_text, generate_weekly_public_pdf,
    )
    print(f"\n{'=' * 60}")
    print(f"  VERITY — Weekly 일반인 리포트 v2 (4섹션)")
    print(f"  실행 시각: {now_kst().strftime('%Y-%m-%d %H:%M:%S KST')}")
    print(f"{'=' * 60}")
    portfolio = load_portfolio()
    if not _release_gate_check(portfolio, "Weekly 일반인"):
        return
    try:
        analysis = generate_periodic_analysis("weekly")
        if analysis.get("status") == "no_data":
            print(f"  ⚠️ {analysis['message']}")
            return
        content = generate_weekly_public_text(analysis, portfolio, channel="public")
        path = generate_weekly_public_pdf(content)
        print(f"  ✓ PDF 생성: {path}")
        print(f"  cover: {content.get('cover')}")
        print(f"  grade: {content.get('metadata', {}).get('grade_raw')}")
        print(f"  watermark: {content.get('metadata', {}).get('watermark', '')}")
    except Exception as e:
        print(f"  ⚠️ PDF 생성 실패: {e}")
        import traceback; traceback.print_exc()


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

    # Brain 시스템 품질 정량 데이터 — Gemini 호출 성공 여부와 무관하게 portfolio top-level 에 mirror
    # (이전엔 weekly_report 안에만 묻혀 있어 사용자가 한눈에 못 봄. fallback 시엔 아예 잃었음.)
    brain_acc = analysis.get("brain_accuracy") or {}
    if brain_acc:
        portfolio["brain_accuracy"] = brain_acc
        portfolio["brain_quality"] = _compute_brain_quality(brain_acc, p)

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

        # 2026-05-17 [2.6] Perplexity 분기 딥리서치 (quarterly_research) 폐기.
        # 사용처 audit 결과 = 5/17 까지 data/research_archive/ 폴더 부재 = 한 번도 실행 안 됨.
        # PM 결정: LLM 무료/유료 가입자 (ChatGPT Pro/Claude Pro/Perplexity Pro) 직접 묻는 게 더
        # 자유로움 + 차별점 0 + 비용 발생. [[feedback_no_new_llm_narrative_features]] + CLAUDE.md
        # RULE 6 정합. Brain v6 input 후보 = 자기 trail (verity_brain) 우위로 대체.

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

    # 2026-05-17 분기 Perplexity 딥리서치 (quarterly_research) 폐기 — periodic_quarterly path.
    # [2.6] 와 동일 사유 (CLAUDE.md RULE 6 정합).

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
        # 2026-06-04 AI_ANALYSIS_FAILED 불변식 — 정상 verdict 인데 실패 플래그 잔존 =
        # stale 모순 (GOOGL 6/4: 다중 pass merge 로 정상 Gemini verdict + fallback
        # risk_flags 공존). risk_flags→auto_avoid 점수 오염 + field_coverage 지표 오염
        # 차단. 좋은 분석이면 AI_ANALYSIS_FAILED 제거 (실패 verdict 면 유지).
        _v = stock.get("ai_verdict", "") or ""
        if _v and not any(m in _v for m in ("파싱 실패", "분석 오류", "분석 실패", "수동 확인")):
            _rf = stock.get("risk_flags") or []
            if "AI_ANALYSIS_FAILED" in _rf:
                stock["risk_flags"] = [x for x in _rf if x != "AI_ANALYSIS_FAILED"]
                _drk = stock.get("detected_risk_keywords") or []
                stock["detected_risk_keywords"] = [x for x in _drk if x != "AI_ANALYSIS_FAILED"]

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
    """VAMS 매매 이력으로부터 누적 시뮬레이션 통계 갱신 (**리셋 이후만**).

    🚨 2026-08-05 측정 정화 fix — 자본 리셋 경계 미적용 + 부분청산 누락.
      결함: 옛 구현은 history 의 SELL 을 **전부** 셌다. VAMS 는 2026-05-17 에 자본
        1천만으로 리셋(vams.reset_meta)했는데 그 **이전 13건**(4/2~5/15, 합 +164만)이
        섞여 들어와 성과를 과대표시했다. 실측 대비:
          옛: 91거래 · 승률 12.1% · 실현손익 −409,108원
          신: 78거래 · 승률  5.1% · 실현손익 −1,815,620원 (리셋 이후 실제)
      2차 피해: verification_trail 이 이 total_trades 를 "리셋 후 누적"으로 문서화하고
        검증 게이트 유의성 마일스톤(Bailey & López de Prado 2014)을 계산한다 — 13건 과대계상.
      3차: validation_report(게이트 판정)와 같은 원장을 다르게 읽어 4.8배 괴리.

    정합 기준 = api/vams/validation.py 와 **동일 정의**로 통일한다:
      · 창 = reset_meta.reset_at 이후 (없으면 전체 — legacy 폴백, window_start=None 표기)
      · 거래 1건 = 청산 episode. 부분청산(PARTIAL_SELL)은 부모 episode 에 합산해
        1건으로 센다 (부분익절을 별건 '승'으로 세면 승률이 부풀려진다).
    산식 아님 — 집계 창·거래 정의 교정이다 (RULE 7 임계 조정 비대상, 측정 정화).
    """
    from api.vams.engine import load_history, VAMS_INITIAL_CASH
    history = load_history()
    vams = portfolio.get("vams", {})

    reset_at = str(((vams.get("reset_meta") or {}).get("reset_at") or ""))[:10] or None

    # 🚨 2026-08-09 규칙 변경 표식 (docs/PREREG_STOPLOSS_CAP_2026_08_09.md).
    #   손절 캡 −5% → −20% 로 바꾸면 이전 거래와 이후 거래는 **다른 규칙의 산물**이다.
    #   5/17 리셋 선례(옛 룰/새 룰 혼재 방지) 정합.
    #   다만 자산 리셋은 하지 않으므로 창을 통째로 옮기지 않고 **양쪽을 다 노출**한다 —
    #   집계 창은 reset_at 유지(누적 N 보존), 규칙 변경 이후만의 집계를 별도 필드로 병기.
    #   어느 창을 게이트에 쓸지는 PM 결정 사항이며 여기서 임의로 바꾸지 않는다.
    # 🚨 2026-08-25 — 전용 jsonl 을 읽되 **매매 행동을 바꾼 것만** 센다. 되돌리지 말 것.
    #   종전엔 portfolio.json 의 legacy 리스트만 읽었고 그건 크론 재생성물이라 늘 비어 있어서
    #   `rule_change_at` 이 null 이었다. 그 결과 게이트가 손절 캡 −5% 시절 22거래를 현 성적에
    #   섞어 세고 있었다(전체 −0.336R = before −0.588R + after +1.386R).
    #   🚨 그런데 이 원장은 **공유 파일**이라 그냥 max(at) 을 잡으면 안 된다 — 실측 124행 중
    #   122행이 `fx_hedge_regime` 운영 이벤트이고, 그걸 세면 경계가 8/17 로 밀린다.
    #   또 8/16 `vams_stoploss_priority` 는 "기각 확정 · 코드·임계 변경 0" 이라 행동 경계가 아니다.
    rule_changes = list(vams.get("rule_change_log") or [])
    try:
        _rl = os.path.join(DATA_DIR, "metadata", "rule_change_log.jsonl")
        with open(_rl, encoding="utf-8") as _f:
            for _line in _f:
                _line = _line.strip()
                if _line:
                    rule_changes.append(json.loads(_line))
    except (OSError, json.JSONDecodeError):
        pass
    _boundaries = _vams_behavior_boundaries(rule_changes)
    last_rule_change = _boundaries[-1][:10] if _boundaries else None

    def _in_window(ev: dict) -> bool:
        if not reset_at:
            return True
        return str(ev.get("date", ""))[:10] >= reset_at

    # 🚨 2026-08-05 — 유령 매도 배제 + 정의 단일화. 원장 재생은 api/vams/trade_ledger 가
    # 단일 출처다(#290 의 4.8배 괴리 재발 방지 + 7/20 감사 phantom 잔존분 제거).
    from api.vams.trade_ledger import reconstruct
    led = reconstruct(history, since=reset_at)
    sells = led["episodes"]
    excluded_n = led["excluded_pre_window"]
    phantom_n = len(led["phantoms"])
    total_trades = len(sells)
    wins = sum(1 for s in sells if s.get("pnl", 0) > 0)
    win_rate = round(wins / total_trades * 100, 1) if total_trades else 0
    # realized_pnl = 실제 돈 = 창 내 청산 raw + 창 내 부분청산 전액 (유령 손익 제외)
    realized_pnl = round(sum(float(s.get("raw_pnl", 0)) for s in sells)
                         + led["partial_realized"], 2)

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
        # 감사 필드 (2026-08-05) — 어떤 창을 셌는지 산출물 자체가 말하게 한다.
        "window_start": reset_at,
        # 규칙 변경 이후만의 집계 — 게이트 창 전환 여부는 PM 결정(임의 전환 금지).
        "rule_change_at": last_rule_change,
        # 🚨 2026-08-25 — 경계 **양쪽**을 게이트와 같은 지표로 신고한다. 되돌리지 말 것.
        #   종전엔 post 쪽 거래수·실현손익만 실어서, 다음 세션이 전체 기대값 −0.336R 을
        #   "현재 시스템 성적" 으로 읽었다(내가 그랬다). 실제로는 27거래 중 22거래가
        #   손절 캡 −5% 시절이고, 캡 −20% 복원(4a2c3f4ee) 이후는 5거래뿐이다.
        #   🚨 판정(overall)은 **바꾸지 않는다** — 창 전환은 PM 결정이다. 신고만 한다.
        "segments": _rule_change_segments(sells, last_rule_change),
        "post_rule_change": (
            {
                "trades": sum(1 for e in sells if str(e.get("date", ""))[:10] >= last_rule_change),
                "realized_pnl": round(sum(
                    float(e.get("pnl") or 0) for e in sells
                    if str(e.get("date", ""))[:10] >= last_rule_change), 2),
            } if last_rule_change else None
        ),
        "excluded_pre_reset_trades": excluded_n,
        "excluded_phantom_sells": phantom_n,
        "phantom_pnl_excluded": led["phantom_pnl"],
        "partial_exits_folded": True,
        "definition": "청산 episode 기준 (부분청산 부모 합산 · 보유 0 유령매도 배제) · SoT=api/vams/trade_ledger",
        "updated_at": now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
    }
    portfolio["vams"] = vams




# 🚨 매매 행동을 실제로 바꾼 VAMS 규칙 변경만 경계로 센다 (2026-08-25).
#   제외 ① `fx_hedge_regime` — 환헷지 운영 이벤트(124행 중 122행). 체결 규칙이 아니다.
#          ② 기각·무변경 기록 — 결정은 남기되 행동은 안 바뀌었다(8/16 vams_stoploss_priority).
_NON_RULE_EVENTS = frozenset({"fx_hedge_regime"})
_NO_CHANGE_MARKS = ("변경 0", "기각", "❌")


def _vams_behavior_boundaries(rows):
    """행동 경계 날짜 목록(오름차순). 없으면 빈 리스트."""
    out = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        if str(r.get("rule") or "") in _NON_RULE_EVENTS:
            continue
        to = str(r.get("to") or "")
        if any(m in to for m in _NO_CHANGE_MARKS):
            continue
        at = str(r.get("at") or "")
        if at:
            out.append(at)
    return sorted(out)


def _rule_change_segments(sells, boundary):
    """규칙 변경 경계 양쪽을 **게이트와 같은 지표**로 집계한다 (2026-08-25 신설).

    🚨 RULE 13 ⑤ — 창 안에 변경 경계가 있으면 하나의 평균은 두 시스템을 섞는다.
       실측 2026-08-25: 전체 −0.336R 인데 before(캡 −5%) −0.588R / after(캡 −20%) +1.386R
       로 **부호가 뒤집힌다**. 섞은 값을 현재 성적으로 읽으면 이미 고친 결함을 계속 센다.
    🚨 판정에 쓰지 않는다. 게이트 창 전환은 PM 결정이며 여기서 바꾸지 않는다.
    """
    if not boundary:
        return {"boundary": None, "note": "규칙 변경 미기록 — data/metadata/rule_change_log.jsonl 확인"}

    def _agg(rows):
        p = [float(e.get("pnl") or 0) for e in rows]
        if not p:
            return {"trades": 0}
        wins = [x for x in p if x > 0]
        losses = [x for x in p if x <= 0]
        avg_w = sum(wins) / len(wins) if wins else 0.0
        avg_l = sum(losses) / len(losses) if losses else 0.0
        pl = abs(avg_w / avg_l) if (wins and losses and avg_l) else None
        wr = len(wins) / len(p)
        exp_r = (wr * pl - (1 - wr)) if pl is not None else None
        return {
            "trades": len(p),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(wr, 4),
            "pl_ratio": round(pl, 3) if pl is not None else None,
            "expectancy_r": round(exp_r, 3) if exp_r is not None else None,
            "realized_pnl": round(sum(p), 2),
        }

    before = [e for e in sells if str(e.get("date", ""))[:10] < boundary]
    after = [e for e in sells if str(e.get("date", ""))[:10] >= boundary]
    return {
        "boundary": boundary,
        "what_changed": "VAMS 손절 캡 −5% → −20% (ATR 개별 손절선 복원) · commit 4a2c3f4ee",
        "before": _agg(before),
        "after": _agg(after),
        "used_by_gate": True,
        "note": "2026-08-09 이후 구간이 현행 게이트 정본이다. before 구간은 legacy diagnostic only.",
    }


# #1 AI 리더보드 피드백 루프 — 상수 (evolver 와 철학 맞춤: 최소샘플 + delta cap)
AI_LEADERBOARD_MIN_SAMPLES = 30          # 소스별 추천 건수 하한 — 미만 시 base 유지 (단기 노이즈 방어)
AI_WEIGHT_DELTA_CAP = 0.10               # baseline 45% 대비 단일 사이클 변화폭 cap ±0.10
# cumulative drift 상한 — Claude weight 를 baseline(0.45) ±0.10 내로 고정 = [0.35, 0.55].
# Gemini 자동으로 [0.45, 0.65] 로 대칭 고정. 시간 누적 드리프트 원천 차단.
AI_WEIGHT_ABS_MIN = 0.35                 # 절대 floor  (= 0.45 - 0.10)
AI_WEIGHT_ABS_MAX = 0.55                 # 절대 ceiling (= 0.45 + 0.10)


def _resolve_dual_model_weights(portfolio: dict) -> dict:
    """직전 리더보드 성과를 바탕으로 Gemini/Claude 가중치 산출.

    안전장치:
      - 소스별 샘플 n < AI_LEADERBOARD_MIN_SAMPLES (30) 면 base 유지
        → 단기 우연 (예: 4건 100%) 로 쏠림 방지
      - 단일 사이클 변화폭 cap ±AI_WEIGHT_DELTA_CAP (0.10)
        → evolver 의 STRATEGY_MAX_WEIGHT_DELTA 와 동일 철학
      - 절대 범위 [0.35, 0.65] — 한 쪽에 2:1 초과 쏠림 금지

    Returns: {gemini, claude} + audit 메타 (_feedback, _gemini_n, _claude_n, _delta)
    """
    base = {"gemini": 0.55, "claude": 0.45}
    lb = portfolio.get("ai_leaderboard") or {}
    rows = lb.get("by_source") or []
    if not rows:
        return {**base, "_feedback": "no_leaderboard"}

    gemini_info = None
    claude_info = None
    for r in rows:
        src = str(r.get("source", "")).lower()
        try:
            n = int(r.get("n", 0))
            hit_rate = float(r.get("hit_rate", 0))
        except (TypeError, ValueError):
            continue
        if src == "gemini":
            gemini_info = {"n": n, "hit_rate": hit_rate}
        elif src == "claude":
            claude_info = {"n": n, "hit_rate": hit_rate}

    if gemini_info is None or claude_info is None:
        return {**base, "_feedback": "missing_source"}

    # 30건 하한: 둘 다 충족해야 피드백 루프 발화
    if gemini_info["n"] < AI_LEADERBOARD_MIN_SAMPLES or claude_info["n"] < AI_LEADERBOARD_MIN_SAMPLES:
        return {
            **base,
            "_feedback": "insufficient_samples",
            "_gemini_n": gemini_info["n"],
            "_claude_n": claude_info["n"],
            "_min_required": AI_LEADERBOARD_MIN_SAMPLES,
        }

    # hit_rate 차이 (claude - gemini) → claude 가중치 조정
    # 적중률 10%p 차이 → claude_w +0.20 (raw), 하지만 cap 에서 ±0.10 로 제한
    delta = claude_info["hit_rate"] - gemini_info["hit_rate"]
    raw_claude_w = 0.45 + (delta / 50.0)
    # 단일 사이클 cap: baseline 0.45 기준 ±AI_WEIGHT_DELTA_CAP
    capped_claude_w = max(0.45 - AI_WEIGHT_DELTA_CAP, min(0.45 + AI_WEIGHT_DELTA_CAP, raw_claude_w))
    # 절대 범위
    claude_w = max(AI_WEIGHT_ABS_MIN, min(AI_WEIGHT_ABS_MAX, capped_claude_w))
    gemini_w = 1.0 - claude_w

    return {
        "gemini": round(gemini_w, 3),
        "claude": round(claude_w, 3),
        "_feedback": "applied",
        "_gemini_n": gemini_info["n"],
        "_claude_n": claude_info["n"],
        "_gemini_hit": round(gemini_info["hit_rate"], 1),
        "_claude_hit": round(claude_info["hit_rate"], 1),
        "_delta_hit_rate": round(delta, 2),
        "_raw_claude_w": round(raw_claude_w, 3),
        "_cap_applied": abs(raw_claude_w - capped_claude_w) > 0.001,
    }


def main():
    # ── VERITY_MODE 배너 ──
    _staging_info = f"  real_keys={sorted(VERITY_STAGING_REAL_KEYS)}" if VERITY_MODE == "staging" else ""
    print(f"[VERITY_MODE] {VERITY_MODE}{_staging_info}")
    if VERITY_MODE != "prod":
        print(f"  ⚠ 비-prod 모드: portfolio → portfolio.dev.json으로 저장됩니다")

    mode = get_analysis_mode()

    if mode.startswith("periodic_"):
        _run_periodic_report(mode)
        return

    # ── Daily 리포트 v2 (관리자 7장 + 일반인 5섹션) ──
    if mode == "daily_admin_v2":
        _run_daily_admin_v2()
        return
    if mode == "daily_public_v2":
        _run_daily_public_v2()
        return

    # ── Weekly 리포트 v2 (관리자 6장 + 일반인 4섹션) ──
    if mode == "weekly_admin_v2":
        _run_weekly_admin_v2()
        return
    if mode == "weekly_public_v2":
        _run_weekly_public_v2()
        return

    # ── Monthly / Quarterly / Semi / Annual v2 ──
    long_horizon_modes = {
        "monthly_admin_v2": ("monthly", "admin"),
        "monthly_public_v2": ("monthly", "public"),
        "quarterly_admin_v2": ("quarterly", "admin"),
        "quarterly_public_v2": ("quarterly", "public"),
        "semi_admin_v2": ("semi", "admin"),
        "semi_public_v2": ("semi", "public"),
        "annual_admin_v2": ("annual", "admin"),
        "annual_public_v2": ("annual", "public"),
    }
    if mode in long_horizon_modes:
        period, kind = long_horizon_modes[mode]
        _run_long_horizon_v2(period, kind)
        return

    # ── portfolio.json advisory lock ──
    # 크론 겹침(realtime / realtime_us / quick / full)이 동일 시점에 load→modify→write 할 때
    # lost-update / 중복 매수를 방지. main() 종료(정상/예외) 시 atexit로 해제.
    import atexit as _atexit
    _portfolio_lock_cm = portfolio_lock(timeout_sec=600)
    _portfolio_lock_cm.__enter__()

    def _release_portfolio_lock():
        try:
            _portfolio_lock_cm.__exit__(None, None, None)
        except Exception:
            pass
    _atexit.register(_release_portfolio_lock)

    is_us_mode = mode in ("realtime_us", "full_us")
    effective_mode = mode.replace("_us", "") if is_us_mode else mode
    market_scope = "us" if is_us_mode else "all"
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
    # full / full_us = 110분.
    #
    # 🚨 2026-08-15 계측 — 이 값의 근거가 한동안 사라져 있었다. 원래 산정식은
    #   "workflow timeout-minutes 120 − 안전 마진 10" 이었는데, yml 의 timeout-minutes 는
    #   그 뒤 150 → 240 으로 올라갔고 이 상수와 아래 print 문구만 120 에 남았다.
    #   즉 run 을 죽이던 것은 워크플로 타임아웃이 아니라 이 가드였고,
    #   240분 예산 중 약 125분이 쓰이지 않고 남았다 (실측 job 115.3분 종료).
    #
    # 🚨 110 → 130 (PM 승인 2026-08-15). yml 주석의 기존 결정("또 닿으면 올리지 말고
    #   분해를 논의")에 대한 명시적 예외다. 근거 = 분해가 이미 실행됐고 효과도 실측됐다는 것 —
    #   증권사 리포트 51분 분리(6c4a78a2c) 전후로 미처리가 45종목(10%) → 1종목(98%) 으로 줄었다.
    #   남은 것은 분해로 풀 2% 가 아니라 근거가 사라진 가드가 막고 있던 2% 다.
    #   130 이어도 워크플로 예산 240분 대비 110분이 남는다. 여기서 또 닿으면 그때는
    #   상향 금지 — STEP 3(33.5분) 분리로 간다. 단 리포트 빌드 step 이 같은 run 의
    #   recommendations.json 에 의존해 단순 분리가 불가함을 확인했다(2026-08-13).
    # 5/10 13:11 KST 1500 stage run 이 82분 한계 도달 SIGTERM 후 상향 (Phase 2-A ramp-up).
    # universe stage 별 동적 산식은 실측 데이터 누적 후 (5/16 ATR verdict 후 sprint).
    _MODE_MAX_SECONDS = {
        "realtime": 10 * 60,
        "realtime_us": 10 * 60,
        "quick": 35 * 60,
        "full": 130 * 60,
        "full_us": 130 * 60,
    }
    _run_limit = _MODE_MAX_SECONDS.get(effective_mode, 110 * 60)
    # .github/workflows/daily_analysis_full.yml 의 timeout-minutes 와 동일해야 한다.
    # 어긋나면 위 print 가 다시 거짓 여유를 보고한다 (그게 이번 drift 의 형태였다).
    _WORKFLOW_TIMEOUT_MIN = 240
    import threading as _threading, time as _time
    _run_start = _time.monotonic()

    # 운영 가시화 — silent skip 절대 금지 (feedback_data_collection_verification_mandatory)
    print(
        f"\n⏱ runtime watchdog: mode={effective_mode} stage={os.environ.get('UNIVERSE_RAMP_UP_STAGE', '0')} "
        f"limit={_run_limit//60}분 (workflow timeout {_WORKFLOW_TIMEOUT_MIN}분 · 미사용 여유 "
        f"{_WORKFLOW_TIMEOUT_MIN - _run_limit//60}분)"
    )

    def _runtime_watchdog():
        _threading.Event().wait(_run_limit)
        elapsed = int(_time.monotonic() - _run_start)
        print(f"\n⏱ 런타임 한계 도달 ({elapsed//60}분 {elapsed%60}초) — 프로세스 종료")
        # 🚨 SIGTERM 을 보내기 **전에** 사유를 못박는다. 핸들러에서 사유가 비어 있으면 외부 취소
        #   (GH Actions concurrency cancel 등)로 구분된다. 둘을 섞으면 예산 문제 빈도를 잘못 센다.
        try:
            from api.observability import run_progress as _rp
            _rp.mark_cutoff("runtime_budget")
        except Exception:
            pass
        import os as _os
        _os.kill(_os.getpid(), 15)  # SIGTERM → 정상 종료 흐름

    _wd = _threading.Thread(target=_runtime_watchdog, daemon=True)
    _wd.start()

    # ── STEP 0: 시스템 자가진단 ──
    # realtime/realtime_us: 5분 cron 따라잡기 위해 캐시 재사용 (이전 측정 9m45s 중 220s = 자가진단)
    # 캐시 미존재 또는 12h 초과 시에만 실제 진단. quick(hourly)/full 에서 정기 갱신됨.
    system_health = None
    if mode in ("realtime", "realtime_us"):
        try:
            _ppath = os.path.join(DATA_DIR, "portfolio.json")
            if os.path.exists(_ppath):
                with open(_ppath, "r", encoding="utf-8") as _pf:
                    _cached_sh = json.load(_pf).get("system_health")
                if isinstance(_cached_sh, dict) and _cached_sh.get("checked_at"):
                    _checked_at = _cached_sh.get("checked_at", "")
                    try:
                        from datetime import datetime as _dt
                        _age_h = (now_kst() - _dt.fromisoformat(_checked_at)).total_seconds() / 3600
                    except (ValueError, TypeError, ImportError):
                        _age_h = 999
                    if _age_h <= 12:
                        system_health = _cached_sh
                        print(f"\n[HEALTH] realtime — 캐시 재사용 (age {_age_h:.1f}h, checked_at={_checked_at})")
        except Exception as _e:
            print(f"  ⚠️ 자가진단 캐시 읽기 실패: {_e}")
    if system_health is None:
        # 🚨 2026-07-27 — realtime 은 런타임 상한 10분인데 자가진단이 125~345s 를 먹어
        #   SIGTERM 종료(2026-07-27 08~11시 KST run 2/8 실패, partial save 조차 못 함).
        #   상류 지연(ECOS max-retries·KRX 18-sweep)이 예산을 통째 삼키는 구조라 개별
        #   timeout 만으로는 못 막음 → 모드별 진단 예산 상한. 초과분 프로브 = skipped(=error 아님),
        #   다음 quick(1h)/full 진단이 정상 갱신하므로 감시 공백 없음.
        #   🚨 2026-07-27 후속 — 전체 예산만으로는 불충분했음이 N=1 실측으로 드러남.
        #   deadline 은 프로브 사이에서만 평가돼서 단일 프로브 폭주를 못 끊음:
        #   run 30246412723 = dart 단독 197,727ms → 90s 예산 무력 + 나머지 13 프로브 skip(감시 공백),
        #   run 30239950220 = 진단 428,589ms 로 10분 SIGTERM 재발.
        #   → 프로브 1건 하드 상한 + 동시 실행. realtime 은 25s 로 눌러 진단 전체를 ~25s 로 bound.
        _is_rt = mode in ("realtime", "realtime_us")
        _health_budget = 90 if _is_rt else None
        _probe_timeout = 25 if _is_rt else None
        try:
            system_health = run_health_check(
                budget_seconds=_health_budget, probe_timeout=_probe_timeout
            )
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

    # 매크로 / 채권 / 글로벌이벤트 = macro_collect 별도 cron snapshot fast path (2026-05-10).
    # stale 30분+ 또는 file 없음 시 inline fetch fallback.
    from api.utils.macro_snapshot import load_macro_snapshot, load_macro_snapshot_stale_ok
    # 30분 cron + 15분 마진 = 45분 stale 허용 (cron 지연/queue 흡수).
    _macro_snap = load_macro_snapshot(max_stale_minutes=45)
    # strict miss 시 inline fetch — 타임아웃/실패 시 빈 {} 대신 stale snapshot 으로 degrade.
    # 빈값 = 실데이터 공백(deadman switch 가 macro 검사), N 시간 stale 실데이터가 항상 우위.
    _macro_stale = None if (_macro_snap and _macro_snap.get("macro")) else load_macro_snapshot_stale_ok()

    if _macro_snap and _macro_snap.get("macro"):
        macro = _macro_snap["macro"]
        if isinstance(macro, dict):
            macro.setdefault("collected_at", _macro_snap.get("collected_at"))
        print(f"  매크로: snapshot cache hit ({_macro_snap.get('collected_at')})")
    else:
        # inline fetch — 실패/타임아웃 시 None 반환받아 stale snapshot 으로 degrade.
        macro = safe_collect(
            get_macro_indicators, name="매크로지표", timeout=45, default=None, notify=_tg_notify,
        )
        if not macro and _macro_stale and _macro_stale.get("macro"):
            # 빈 {} 대신 stale 실데이터 (forward-fill). staleness 표기 의무
            # (feedback_macro_timestamp_policy: collected_at + _stale 메타 — fresh 처럼 노출 금지).
            macro = _macro_stale["macro"]
            if isinstance(macro, dict):
                macro["_stale"] = True
                macro["collected_at"] = _macro_stale.get("collected_at")
            print(f"  ⚠️ 매크로: inline fetch 실패 → stale snapshot degrade ({_macro_stale.get('collected_at')})")
        elif not macro:
            macro = {}
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

    # ── 모드 전환 시 이전 모드 전용 결과의 스테일 방지 ──
    # realtime/realtime_us에서는 verity_brain_analyze를 돌리지 않으므로
    # macro_override·market_brain 등 full 전용 블록은 6시간 초과 시 파기
    _STALE_TTL_KEYS = {
        # 2026-05-17: "quarterly_research" 제거 (모듈 폐기, CLAUDE.md RULE 6)
        "realtime": ("postmortem", "strategy_evolution",
                     "claude_morning", "verity_brain"),
        "realtime_us": ("postmortem", "strategy_evolution",
                        "claude_morning", "verity_brain"),
    }
    for _sk in _STALE_TTL_KEYS.get(mode, ()):
        _v = portfolio.get(_sk)
        if not isinstance(_v, dict):
            continue
        _ts = _v.get("generated_at") or _v.get("updated_at")
        if not _ts:
            continue
        try:
            from datetime import datetime as _dt
            _t = _dt.fromisoformat(str(_ts))
            if (now_kst() - _t).total_seconds() > 6 * 3600:
                portfolio.pop(_sk, None)
        except Exception:
            pass

    # ── STEP 1.5: KRX OpenAPI — tier별 주기 (US 모드에서는 스킵)
    # full: 전부 갱신 | quick: Macro+Active 병합(Static 유지) | realtime: Active만 병합
    def _slim_krx(snap: dict) -> dict:
        """portfolio.json 저장용: summary + 메타만 유지, 상세 endpoint rows 제거.

        🚨 이 축약은 **L3(발행) 층의 일이지 L1(수집) 층의 일이 아니다.** 2026-08-09 까지는
           여기서 버린 것이 어디에도 남지 않아 매일 채권 308 · 파생지수 320 행이 소멸했다.
           지금은 collect_krx_openapi_snapshot(persist_raw=True) 가 전체 행을
           data/krx_raw/{bas_dd}.json 에 먼저 착지시킨다 — 이 함수는 축약만 담당한다.
           persist_raw 를 끄면 그 폐기가 되살아난다.
        """
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
            # 🚨 persist_raw — 아래 _slim_krx 가 상세 행을 제거하기 때문에, 이걸 켜지 않으면
            #   매 full run 이 채권 308 · 파생지수 320 등을 받아서 그대로 버린다(추가 호출 0).
            #   L1 폐기 금지 — docs/DATA_LAYER_RESEARCH_20260809.md §1-1 · §4-1.
            krx_snapshot = collect_krx_openapi_snapshot(persist_raw=True)
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
            # 🚨 2026-07-27 — 소스 불가(KRX bld LOGOUT, KDM 개편으로 MDCSTAT06401 사망)인데
            #   로그가 "프로그램: NEUTRAL | 순매수 +0억" 으로 떠서 실측 중립과 구분 불가였음.
            #   collector 는 이미 unavailable=True 로 정직 반환 중 → 로그도 그대로 노출.
            if prog.get("unavailable"):
                print(f"  프로그램: 불가 — {prog.get('status_note') or prog.get('error') or '소스 점검 중'} (신호 미산출)")
            else:
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
        if _macro_snap and _macro_snap.get("bonds"):
            bonds_data = _macro_snap["bonds"]
            if isinstance(bonds_data, dict):
                bonds_data.setdefault("collected_at", _macro_snap.get("collected_at"))
            print(f"  채권수익률곡선: snapshot cache hit ({_macro_snap.get('collected_at')})")
        else:
            # 타임아웃/실패 시 빈 {} 대신 stale snapshot bonds 로 degrade (실데이터 우위).
            bonds_data = safe_collect(
                get_full_yield_curve_data,
                name="채권수익률곡선", timeout=45, default=None, notify=_tg_notify,
            )
            if not bonds_data and _macro_stale and _macro_stale.get("bonds"):
                # staleness 표기 의무 (feedback_macro_timestamp_policy).
                bonds_data = _macro_stale["bonds"]
                if isinstance(bonds_data, dict):
                    bonds_data["_stale"] = True
                    bonds_data["collected_at"] = _macro_stale.get("collected_at")
                print(f"  ⚠️ 채권: inline fetch 실패 → stale snapshot degrade ({_macro_stale.get('collected_at')})")
            elif not bonds_data:
                bonds_data = {}
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

            try:
                from api.collectors.niche_intel import build_macro_niche_credit
                niche_credit_macro = build_macro_niche_credit(bonds_data)
                if niche_credit_macro:
                    portfolio.setdefault("macro", {})["niche_credit"] = niche_credit_macro
                    print(f"  macro.niche_credit: AA- 스프레드 {niche_credit_macro.get('corporate_spread_vs_gov_pp')}%p"
                          f"{' · 경고' if niche_credit_macro.get('alert') else ''}")
            except Exception as e:
                print(f"  macro.niche_credit 계산 실패(무시): {e}")

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
                # 2026-06-10: build_market_overview = KIS 배치 ~7 호출(각 _get timeout=10).
                #   KIS 저하 시 누적이 realtime 10분 예산 잠식 → watchdog SIGTERM. safe_collect 로 캡.
                mkt_overview = safe_collect(
                    kis.build_market_overview, name="kis_market_overview", timeout=60, default={}
                )
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
                # 2026-06-10: build_overseas_market_overview = 6 거래소 × 5 + 뉴스 2 = 32 KIS 호출
                #   (각 _get timeout=10). KIS 해외 엔드포인트 저하(미국장 마감 시간대 등) 시 최악 ~320s 누적
                #   → realtime 10분 예산 절반 잠식 → watchdog SIGTERM(6/10 11:30 KR 사고 hang step=[1.7]).
                #   safe_collect 로 전체 배치 캡 (timeout 시 부분/빈 dict → 분석 계속).
                os_overview = safe_collect(
                    kis.build_overseas_market_overview, overseas_exchanges,
                    name="kis_overseas_overview", timeout=90, default={},
                )
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
                    # 2026-06-10: 30 ticker × build_overseas_brain_snapshot(다중 KIS 호출)도 누적 무가드였음.
                    #   build_price_map 과 동일 — 누적 예산(_US_SNAP_BUDGET) + 연속 실패 breaker 로 캡.
                    _US_SNAP_BUDGET = 60.0
                    _us_snap_start = time.monotonic()
                    _us_snap_fail = 0
                    for tk, excd in us_tickers:
                        if time.monotonic() - _us_snap_start >= _US_SNAP_BUDGET or _us_snap_fail >= 4:
                            sys.stderr.write(
                                f"[kis_us_snapshots] 중단 — 예산 초과 또는 연속 실패 {_us_snap_fail}회 "
                                f"(부분 {us_ok}/{len(us_tickers)}, watchdog SIGTERM 방어)\n"
                            )
                            break
                        try:
                            snap = safe_collect(
                                kis.build_overseas_brain_snapshot, excd, tk,
                                name=f"kis_us_snap:{tk}", timeout=8, default=None,
                            )
                            if snap:
                                kis_us_snapshots[tk] = snap
                                us_ok += 1
                                _us_snap_fail = 0
                            else:
                                _us_snap_fail += 1
                        except Exception:
                            _us_snap_fail += 1
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
        collect_headlines, max_items=40,   # 20→40 (뉴스 페이지 볼륨↑, PM 2026-06-27 "뉴스량 적어보임")
        name="헤드라인", timeout=30, default=[], notify=_tg_notify,
    )
    portfolio["headlines"] = headlines
    if headlines:
        print(f"  뉴스 {len(headlines)}건")

    bb_rss = safe_collect(
        collect_bloomberg_google_news_rss, max_items=25,   # 15→25 (글로벌 헤드라인 볼륨↑, 시장 탭 합본)
        name="Bloomberg RSS", timeout=30, default=[], notify=_tg_notify,
    )
    portfolio["bloomberg_google_headlines"] = bb_rss
    if bb_rss:
        print(f"  Bloomberg(Google News RSS) {len(bb_rss)}건")

    us_hl = safe_collect(
        collect_us_headlines,
        kr_headlines=portfolio.get("headlines", []),
        bloomberg_rss=portfolio.get("bloomberg_google_headlines", []),
        max_items=30,   # 20→30 (미국 탭 볼륨↑)
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
    if _macro_snap and _macro_snap.get("global_events"):
        global_events = _macro_snap["global_events"]
        print(f"  글로벌이벤트: snapshot cache hit ({_macro_snap.get('collected_at')})")
    else:
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
                    send_message(format_alert_message(qe), bypass_quiet=True)
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
            name="CFTC_COT", timeout=90, default={"ok": False, "instruments": {}}, notify=_tg_notify,
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
        portfolio.setdefault("cboe_pcr", {
            "signal": "NEUTRAL", "panic_trigger": False, "vci_adjustment": 0.0,
            "panic_reason": None, "total_pcr_latest": None,
            "total_pcr_avg_20d": None, "spx_realtime_pcr": None,
            "pcr_z_score": None, "equity_pcr_latest": None, "history_20d": [],
        })

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
                # 🚨 2026-08-20 — current_price 동반 갱신. 12줄 위 holdings 분기(2435)는
                #   갱신하는데 추천만 price 에서 멈춰 있었다. 섹션 헤더가 "보유·추천 종목
                #   시세 갱신"(2426) 이고 publish 쪽 action.yml 주석도 "recommendations
                #   current_price 1분 fresh" 라 **의도는 갱신**이었다. 실측 9일 지속 —
                #   8/12 40/40 · 8/19 44/56 · 8/20 59/66 이 cp≠p, 최대 괴리 15%.
                #   점수 입력 아님(consensus 는 호출부 2곳 전수가 price 를 넘긴다) →
                #   산식 무변경. 소비처 = 긴급알림(2481)·trade_plan_followup·수익률 표시.
                stock["current_price"] = p
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
                                f"대응: {action}",
                                bypass_quiet=True,
                            )
                        emergency_sent += 1
                except Exception as e:
                    print(f"    Claude 긴급 심사 실패: {e}")
            portfolio["_claude_emergency_dedupe"] = dedupe
            if emergency_sent:
                print(f"  Claude 긴급 심사: {emergency_sent}건 처리")

        # 지정학 노출 집계 (DART 사업보고서 파싱 결과 기반)
        try:
            portfolio["geopolitical_hotspots"] = build_geopolitical_hotspots(
                portfolio.get("recommendations", []),
                portfolio.get("vams", {}).get("holdings", []),
            )
        except Exception as e:
            print(f"  지정학 집계 스킵: {e}")

        # 알림 엔진 실행 (realtime에서도)
        try:
            briefing = generate_briefing(portfolio)
        except Exception as _bf_err:
            print(f"  비서 생성 실패(폴백): {_bf_err}")
            briefing = {
                "headline": "브리핑 생성 실패",
                "alerts": [],
                "alert_counts": {"critical": 0, "warning": 0, "info": 0},
                "action_items": [],
            }
        portfolio["briefing"] = briefing
        portfolio["alerts"] = briefing.get("alerts", [])
        print(f"  비서: {briefing.get('headline', '?')}")

        # 2026-05-12: realtime 텔레그램 통수 절감 — 기본 CRITICAL only.
        # WARNING 은 사이트 카드/Bell 로 표시되므로 텔레그램에서 빼는 게 정합.
        # 환경변수 TELEGRAM_REALTIME_MIN_LEVEL=WARNING 으로 되돌릴 수 있음.
        try:
            from api.config import TELEGRAM_REALTIME_MIN_LEVEL
        except Exception:
            TELEGRAM_REALTIME_MIN_LEVEL = "CRITICAL"  # type: ignore
        _level_rank = {"CRITICAL": 0, "WARNING": 1, "INFO": 2}
        _min_rank = _level_rank.get(str(TELEGRAM_REALTIME_MIN_LEVEL).upper(), 0)
        tg_alerts = [
            a
            for a in briefing.get("alerts", [])
            if _level_rank.get(str(a.get("level", "INFO")).upper(), 99) <= _min_rank
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

        # ── realtime 모드도 첫 화면(TodayActionsCard) 보조 필드 갱신 ──
        # daily_actions 는 직전 quick/full 결과 stale 유지(보유 변동만 갱신).
        # dashboard_summary 는 매번 재계산 — vams.total_return_pct + alerts 가 realtime 에서 갱신되므로.
        try:
            from api.intelligence.dashboard_summary import attach_to_portfolio as _attach_summary_rt
            _attach_summary_rt(portfolio)
            _ps = portfolio.get("portfolio_summary") or {}
            _dq = portfolio.get("decision_queue") or []
            _vd = portfolio.get("validation") or {}
            print(f"  📊 dashboard summary (realtime): cum={_ps.get('cumulative_pct')}%, "
                  f"queue={len(_dq) if isinstance(_dq, list) else '-'}, "
                  f"validation={_vd.get('cumulative_days')}d")
        except Exception as _ds_err:
            print(f"  ⚠️ dashboard_summary (realtime) 스킵: {_ds_err}")

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

    # ── STEP 2: quick + full — 종목 필터링 (Phase 2-A: ramp-up 기반 dispatch) ──
    # 2026-05-10: universe_scan_builder 별도 cron snapshot fast path.
    # 2026-05-11: inline 5000 scan fallback 제거. universe_scan cron 단독으로만.
    # 2026-05-17 weekday 정합 fix ([[feedback_weekday_check_mandatory]]):
    #   universe_scan cron = 평일 KST 15:30 만. 주말 = 도래 0 = 자연 stale (금 → 월 = 72h).
    #   주말 max_stale = 96h (금→월 + 마진). 평일 = 26h 유지.
    #   주말 + stale = abort 아니라 옛 candidates 사용 (사이트 데이터 정상, 알림 폭주 차단).
    print(f"\n[2] 3단계 깔때기 필터링 (scope={market_scope})")
    candidates = None
    _now_kst_dt = now_kst()
    _wd = _now_kst_dt.weekday()  # Mon=0 … Sat=5, Sun=6
    is_weekend = _wd >= 5  # 토/일
    # 2026-06-01 fix: 월요일 첫 universe_scan(15:30 KST) 전 구간도 확장 tolerance.
    #   universe_scan cron = 평일 15:30 KST only → 금요일 scan 이후 월요일 새벽 = 60~72h stale.
    #   is_weekend(토/일)만 96h 적용 시 월요일 새벽(평일 취급)은 26h 게이트에 걸려 abort + 시간당
    #   텔레그램 알림 폭주 (5/30~6/1 사고: daily_analysis 월요일 장전 5연속 실패). markets closed →
    #   주말~월요일 scan 전까지 universe 불변이므로 금요일 candidates 재사용이 정합 (RULE 8 / [[feedback_weekday_check_mandatory]]).
    # 2026-07-13: 경계 16 → 17. universe_scan 은 KST 15:30 시작이지만 소요가 35→43분으로 늘어
    #   실착지가 16:05~16:15 KST. daily_analysis_full 은 KST 16:07 트리거라 hour==16 구간에 들어오는데
    #   옛 경계(hour < 16)는 그 구간을 못 덮어 월요일에 26h 게이트로 abort 했다(7/13 실사고).
    #   주 수리는 checkout ref=main(경합 소멸). 이 관용창은 scan 이 아예 실패했을 때의 안전망 —
    #   중단(하위 빌더 24개 skip) 대신 금요일 candidates 로 degrade. markets closed 구간이라 정합.
    is_pre_scan_monday = _wd == 0 and _now_kst_dt.hour < 17
    max_stale_hours = 96 if (is_weekend or is_pre_scan_monday) else 26
    try:
        from api.utils.universe_candidates import load_universe_candidates
        _u_snap = load_universe_candidates(max_stale_hours=max_stale_hours)
        if _u_snap and _u_snap.get("candidates"):
            candidates = _u_snap["candidates"]
            print(
                f"  candidates: snapshot cache hit ({_u_snap.get('collected_at')}) — "
                f"{len(candidates)}개 (weekday max_stale={max_stale_hours}h)"
            )
    except Exception as e:
        print(f"  universe_candidates 로드 실패: {e}")

    if not candidates:
        # universe_scan cron 결함 또는 첫 운영. daily_analysis 가 5000 inline scan 절대 X.
        # 🚨 직접 텔레그램 발송 금지: daily_analysis(매시 :07)가 지연된 universe_scan보다
        # 먼저 도착하는 정상 경계에서도 같은 문구가 반복됐다. 여기서는 exit 1로 다음 cron
        # 재시도와 실행 이력만 남기고, 실제 연속 결함 알림은 cron_health_monitor 단일 경로가 맡는다.
        abort_msg = (
            f"⚠️ <b>VERITY daily_analysis 중단</b>\n"
            f"universe_candidates.json 없음 또는 {max_stale_hours}h stale.\n"
            f"universe_scan cron 결함 의심 → 진단 + 다음 cron 재시도.\n"
            f"(daily_analysis 는 5000 inline scan 안 함 — 분리 sprint 의도 정합)"
        )
        print(f"  {abort_msg}")
        print("  텔레그램 silent · 연속 결함은 cron_health_monitor에서 단일 알림")
        import sys as _sys
        _sys.exit(1)

    print(f"  최종 후보: {len(candidates)}개 종목")
    tracer.log_filter("pipeline", 0, len(candidates))

    # ── STEP 2.01 equity_research_brief attach (Brain v6 prep, 2026-05-17) ──
    # US 종목에 data/equity_research/<TICKER>.json 부착. _compute_fact_score 가
    # equity_brief_verdict component (weight 0.03) 산출. 데이터 부재 시 50 neutral.
    try:
        from api.utils.equity_brief_attach import attach_briefs_to_stocks
        attached = attach_briefs_to_stocks(candidates)
        print(f"  equity_brief attached: {attached} (US 종목)")
    except Exception as e:
        print(f"  equity_brief attach 실패 (skip, fact_score 영향 없음): {e}")

    # ── STEP 2.05 폐기 (2026-05-10) ──
    # wide_scan 호출이 candidates(60개) 위에 있어 "5,000 raw → 22% cut" Coarse Filter 의도 위반.
    # 정정: wide_scan 호출을 stock_filter 의 get_all_stock_data 직후로 이동.
    # universe_scan_builder 가 stock_filter 호출하면 자동으로 5,000 raw 가 wide_scan 으로 흘러감.
    # 메모리 원칙 9 funnel 정합 (Coarse Filter 위치 = step1/step2 전).

    # ── STEP 2.1: 관심종목(Supabase) 병합 ──
    try:
        watch_items = _fetch_watch_tickers()
        if watch_items:
            watch_added = _merge_watch_items_into_candidates(candidates, watch_items)
            if watch_added:
                print(f"  + 관심종목 {watch_added}개 추가 (총 {len(candidates)}개)")
    except Exception as e:
        print(f"  관심종목 병합 스킵: {e}")

    # ── STEP 2.15: R1 보유 강제 편입 (PREREG_POOL_ROTATION_2026_08_04 — 관측 사각 0) ──
    # VAMS·페이퍼 트랙 보유 = 풀 의무 편입, 보유 해소 전 퇴출 금지. 8/3 실측: 보유 4종
    # (티쓰리·NAVER·파마리서치·삼성E&A)이 풀 밖 → 배지·청산(X1~X4) 판정 불가 사각.
    # 매 run 집행 (R6 주간 판정과 별개 — R1 은 LOCKED 절대 조건). #271 오염 수정 파이프 재사용.
    # 보유 소스 = 전 run 산출 portfolio.json (이 시점 신규 portfolio 미구성 — 전일 보유가 정답).
    try:
        _r1_items = []
        _prev_pf = {}
        try:
            with open(os.path.join(DATA_DIR, "portfolio.json"), encoding="utf-8") as _pf:
                _prev_pf = json.load(_pf)
        except (OSError, json.JSONDecodeError):
            pass
        for _h in ((_prev_pf.get("vams") or {}).get("holdings") or []):
            _tk = str(_h.get("ticker") or "").strip()
            if _tk:
                _r1_items.append({"ticker": _tk, "market": "kr" if _tk.isdigit() and len(_tk) == 6 else "us"})
        try:
            with open(os.path.join(DATA_DIR, "exec_paper_state.json"), encoding="utf-8") as _ef:
                for _tk in ((json.load(_ef).get("positions") or {})):
                    _tk = str(_tk).strip()
                    _r1_items.append({"ticker": _tk, "market": "kr" if _tk.isdigit() and len(_tk) == 6 else "us"})
        except (OSError, json.JSONDecodeError):
            pass
        if _r1_items:
            _r1_added = _merge_watch_items_into_candidates(candidates, _r1_items)
            if _r1_added:
                print(f"  + [pool R1] 보유 강제 편입 {_r1_added}개 — 관측 사각 해소 (총 {len(candidates)}개)")
    except Exception as _r1_e:  # noqa: BLE001
        print(f"  [pool R1] 스킵: {type(_r1_e).__name__}: {_r1_e}")

    # ── STEP 2.16: 거장 순매수 TOP 10 강제 편입 (PM 지시 2026-08-25) ──
    # 공개 거장 페이지의 순매수 TOP 10 = 리포트 유입 표면 — 사용자가 그 목록을 보고
    # 종목 리포트로 들어오므로, 그 종목들은 분석·리포트 파이프라인에 무조건 존재해야 한다.
    # 발견 경위 = 로테이션 상태 미영속로 지명이 알파벳 앞줄 동결 → V(순번 1,387/1,505)가
    # 콘솔에 영영 미도달 (kickoff 상류 발견 ③). 이 스텝은 로테이션과 무관하게 보장한다.
    # 🚨 랭킹 = PublicInvestorPortfolios TOP 10 과 동일 산식 (펀드 수 신규+증액−감액 —
    #    value_change 랭킹 금지: 주가 등락 혼재). 두 산식이 갈리면 화면과 편입이 어긋난다.
    try:
        with open(os.path.join(DATA_DIR, "us_smart_money_13f.json"), encoding="utf-8") as _sf:
            _sm_stocks = (json.load(_sf).get("stocks") or [])
        _sm_scored = []
        for _s in _sm_stocks:
            # ETF 는 데이터엔 있으나(PM 8/25 "ETF 는 필수지" — 보유 사실) 강제편입 제외:
            # 분석 파이프는 개별주 전용이고 ETF 매수는 개별 종목 확신 신호가 아니다.
            if _s.get("is_etf"):
                continue
            _hs = _s.get("holders") or []
            _nw = sum(1 for _h in _hs if _h.get("change_type") == "NEW")
            _inc = sum(1 for _h in _hs if _h.get("change_type") == "INCREASED")
            _dec = sum(1 for _h in _hs if _h.get("change_type") == "DECREASED")
            _net = _nw + _inc - _dec
            if _net > 0 and _s.get("ticker"):
                _sm_scored.append((_net, _nw + _inc, _s.get("total_value_usd") or 0, str(_s["ticker"])))
        _sm_scored.sort(key=lambda x: (-x[0], -x[1], -x[2]))
        _sm_items = [{"ticker": _tk, "market": "us"} for _n, _b, _v, _tk in _sm_scored[:10]]
        if _sm_items:
            _sm_added = _merge_watch_items_into_candidates(candidates, _sm_items)
            if _sm_added:
                print(f"  + [pool 13F] 거장 순매수 TOP{len(_sm_items)} 강제 편입 {_sm_added}개 (총 {len(candidates)}개)")
    except Exception as _sm_e:  # noqa: BLE001
        print(f"  [pool 13F] 스킵: {type(_sm_e).__name__}: {_sm_e}")

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

        try:
            tech = analyze_technical(ticker_yf)
            stock["technical"] = tech
        except Exception as _tech_err:
            print(f" ❌ 기술 분석 실패(스킵): {_tech_err}")
            stock["technical"] = {"rsi": None, "signals": [], "technical_score": 50}
            stock["flow"] = {"flow_score": 50, "flow_signals": []}
            stock["sentiment"] = {"score": 50, "positive": 0, "negative": 0, "neutral": 0, "headline_count": 0, "top_headlines": [], "detail": []}
            stock["consensus"] = {}
            stock["multi_factor"] = {"multi_score": 50, "grade": "N/A", "all_signals": []}
            continue

        # US 종목: quick 모드에서 경량 Finnhub 수집 (Brain 입력 확보)
        if stock.get("currency") == "USD" and effective_mode != "full":
            prev_match_us = next((r for r in prev_recs_cache if r.get("ticker") == ticker), None)
            # 2026-05-18 — A7 attach drop fix: full mode 산출 field 도 prev_match merge 보존.
            # 옛: realtime cron 도래 시마다 external_risk / dart_business_analysis / commodity / vol 손실.
            # 신: full mode 산출 field 도 보존 (다음 full mode 도래 전까지 brain re-analyze 정합).
            _us_fields = ["analyst_consensus", "earnings_surprises", "insider_sentiment",
                          "institutional_ownership", "short_interest",
                          "sec_financials", "sec_filings", "company_news",
                          "finnhub_metrics", "peer_companies",
                          "insider_transactions",
                          # full mode 산출 (A7/A1/A6/A5) — drop 방지
                          "external_risk", "dart_business_analysis",
                          "commodity_margin", "analyst_report_summary",
                          "volatility_20d", "volatility_60d",
                          # 2026-05-20 — backtest drop fix (A7 누락분).
                          # full STEP 5 산출 backtest 가 quick merge 보존 X →
                          # _backtest_to_score 전 종목 50 fallback (측정 25/25 @50, 보편 최악).
                          "backtest"]
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
                        stock.setdefault("institutional_ownership", _fh.get_institutional_ownership(ticker, _fhk))
                except Exception:
                    pass
            if not stock.get("sec_filings") or not stock.get("sec_financials"):
                try:
                    from api.collectors import sec_edgar as _sec
                    from api.config import SEC_EDGAR_USER_AGENT as _ua
                    if not _ua:
                        # 2026-05-18 A4 fix — silent skip 명시 (feedback_data_collection_verification_mandatory).
                        # 옛 silent except: pass → 5 US 종목 sec_financials 누락 root cause 진단 불가.
                        import sys as _sys
                        _sys.stderr.write(
                            f"[sec_edgar] {ticker} skip — SEC_EDGAR_USER_AGENT env missing\n")
                    else:
                        if not stock.get("sec_filings"):
                            stock["sec_filings"] = _sec.get_recent_filings(ticker, _ua)
                        if not stock.get("sec_financials"):
                            stock["sec_financials"] = _sec.get_financial_facts(ticker, _ua)
                except Exception as _e:
                    # A4 silent skip 해소 — fail reason stderr 명시 (logged=True 정합).
                    import sys as _sys
                    _sys.stderr.write(
                        f"[sec_edgar] {ticker} fetch fail: {type(_e).__name__}: {str(_e)[:200]}\n")

        try:
            if stock.get("currency") == "USD":
                flow = compute_us_flow(stock)
            else:
                flow = get_investor_flow(ticker)
        except Exception as _flow_err:
            print(f"      수급 수집 실패(폴백): {_flow_err}")
            flow = {"flow_score": 50, "flow_signals": []}
        stock["flow"] = flow

        try:
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
                    # 2026-05-18 — A7 attach drop fix (KR 정합, US line 2429-2444 와 대칭).
                    # full mode 산출 (external_risk / dart_business / commodity / vol / analyst) 보존.
                    for _kr_field in ("external_risk", "dart_business_analysis",
                                      "commodity_margin", "analyst_report_summary",
                                      "volatility_20d", "volatility_60d",
                                      "backtest"):  # 2026-05-20 backtest drop fix (US 대칭)
                        if not stock.get(_kr_field) and prev_match.get(_kr_field):
                            stock[_kr_field] = prev_match[_kr_field]
        except Exception as _sent_err:
            print(f"      감성 수집 실패(폴백): {_sent_err}")
            sentiment = {"score": 50, "positive": 0, "negative": 0, "neutral": 0, "headline_count": 0, "top_headlines": [], "detail": []}
        stock["sentiment"] = sentiment

        if effective_mode == "full":
            try:
                # 2026-07-20 감사 P1: 기존 `not ticker_yf.startswith(ticker)` = KR('005930.KS'.startswith('005930')=True)
                # 도 US 도 항상 None → KR naver_community 영구 skip(30% 감성가중 KR 변별력 0). currency 로 정정.
                code_6 = None if stock.get("currency") == "USD" else str(ticker).zfill(6)
                social = compute_social_sentiment(
                    name=name, ticker_yf=ticker_yf,
                    stock_code=code_6, existing_news=sentiment,
                )
                stock["social_sentiment"] = social
                print(f"      소셜: {social['score']}점 ({social['trend']}) | 소스: {', '.join(social['sources_used'])}")
            except Exception as e:
                print(f"      소셜 감성 수집 실패: {e}")
                stock["social_sentiment"] = {"score": 50, "trend": "neutral", "sources_used": []}

        try:
            raw_c = scout_consensus(ticker)
            time.sleep(0.1)
            price_c = float(stock.get("price") or 0)
            # 2026-05-19 C2 — US 종목 fallback path 에 equity_research_brief 전달.
            cblock = build_consensus_block(
                raw_c, price_c, flow, export_by_ticker.get(str(ticker).zfill(6)),
                equity_research_brief=stock.get("equity_research_brief"),
            )
        except Exception as _cons_err:
            print(f"      컨센서스 수집 실패(폴백): {_cons_err}")
            raw_c = {"ok": False, "error": str(_cons_err)}
            cblock = {}
        stock["consensus"] = cblock
        fund_c = merge_fundamental_with_consensus(stock.get("safety_score", 50), cblock)
        mp = fundamental_penalty_from_macro(macro)
        if mp:
            fund_c = max(0, fund_c - mp)

        try:
            mf = compute_multi_factor_score(
                fundamental_score=fund_c,
                technical=tech, sentiment=sentiment, flow=flow, macro_mood=macro_mood,
                social_sentiment=stock.get("social_sentiment"),
                bond_regime=(portfolio.get("bonds") or {}).get("bond_regime"),
            )
        except Exception as _mf_err:
            print(f"      멀티팩터 계산 실패(폴백): {_mf_err}")
            mf = {"multi_score": 50, "grade": "N/A", "all_signals": []}
        stock["multi_factor"] = mf
        try:
            attach_value_chain_trade_overlay(stock)
        except Exception as _vc_err:
            print(f"      value chain overlay 실패(무시): {_vc_err}")
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
                # 2026-07-28 — 네이버 기업실적분석 표의 분기 컬럼(과거 actual + (E) 추정).
                # 같은 페이지에 이미 있던 것을 파서가 tds[:4] 로 잘라 버리던 것 복원.
                # 🔒 consensus_data.json = 발행 제외 확정(2026-07-21 전수감사 PM 승인) + 공개
                #   리포트 빌더도 "consensus": None 봉인(2026-07-10 쟁점4) → 공개 노출 0.
                #   비공개 브레인 own-use 전용.
                "quarters": raw_c.get("quarters") or [],
                "quarter_estimate_labels": raw_c.get("quarter_estimate_labels") or [],
            }
        )
        print(
            f" {mf['multi_score']}점({mf['grade']}) RSI:{tech['rsi']} "
            f"수급:{flow['flow_score']} 컨센:{cblock.get('consensus_score', '?')}({cblock.get('score_source', '')})"
        )

    # 내 종목 탭 뉴스 영어 헤드라인 → 한글 사전번역(build-time) 부착 — 미국 탭(news_headlines.py)과 동일 배치.
    # top_headline_links 토글용. 캐시(news_translation_cache.json) miss 만 호출. 실패/키부재 시 미부착(컴포넌트 영문 fallback).
    try:
        from api.collectors.news_translation import translate_headlines_ko
        _link_titles = [
            (h.get("title") or "")
            for s in candidates
            for h in ((s.get("sentiment") or {}).get("top_headline_links") or [])
            if h.get("title")
        ]
        if _link_titles:
            _ko_map = translate_headlines_ko(_link_titles)
            for s in candidates:
                for h in ((s.get("sentiment") or {}).get("top_headline_links") or []):
                    _ko = _ko_map.get((h.get("title") or "").strip())
                    if _ko:
                        h["title_ko"] = _ko
            print(f"  종목 헤드라인 한글번역 부착: {sum(1 for t in _ko_map.values() if t)}건")
    except Exception as _tr_err:  # noqa: BLE001
        print(f"  종목 헤드라인 한글번역 스킵: {_tr_err}")

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
        try:
            stock["timing"] = compute_timing_signal(stock)
        except Exception as _ts_err:
            print(f"  타이밍 계산 실패(폴백) {stock.get('ticker','?')}: {_ts_err}")
            stock["timing"] = {"timing_score": 50}

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
                # 2026-05-20 wire — fscore_deltas attach (사이클 섹터 8Q AND 게이트 포함)
                # quality.compute_piotroski_f_score F3/F5/F6/F8/F9 시계열 Δ 활성.
                # data/dart_quarterly_snapshots.jsonl 부재 시 fscore_deltas={data_source: no_snapshots}.
                try:
                    from api.utils.fscore_delta import attach_fscore_deltas
                    attach_fscore_deltas(stock)
                except Exception:
                    pass
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
                bond_regime=(portfolio.get("bonds") or {}).get("bond_regime"),
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
                # 2026-05-18 A5 fix — backtester 가 fetch한 close 시계열로 vol 산출, propagate.
                # docs/COMPONENT_FALLBACK_AUDIT_20260518.md §D (quant_volatility 0/25 fallback) 해소.
                if bt.get("volatility_20d") is not None:
                    stock["volatility_20d"] = bt["volatility_20d"]
                if bt.get("volatility_60d") is not None:
                    stock["volatility_60d"] = bt["volatility_60d"]
            except Exception:
                stock["backtest"] = {"total_trades": 0, "win_rate": 0, "avg_return": 0, "max_drawdown": 0, "sharpe_ratio": 0, "recent_trades": []}
    else:
        for stock in candidates:
            stock.setdefault("backtest", {})

    # ── STEP 5.05: A5.1 fix — quant_volatility 재계산 (post-backtest) ──
    # 2026-05-19 추가. 5/18 A5 fix unfinished 부분 정정.
    # 진단 (docs/BRAIN_SCORE_AUDIT_20260518.md §3, quant_volatility 100% fallback):
    #   STEP 4.5 quant_factors 계산 → STEP 5 backtester vol propagation 순서 결함.
    #   compute_volatility_score 가 vol_20d/60d 없는 stock 입력받아 모두 score=50 반환.
    #   5/18 A5 fix 가 backtester→stock vol propagation 만 추가, 재계산은 누락.
    # 신: backtest 후 stock["volatility_20d"] 있는 종목에 한해 재계산 + universe_stats 갱신.
    # multi_factor.quant_factors.volatility 는 STEP 5.8 commodity_margin 단계가
    #   compute_multi_factor_score 재호출 시 자동 cascade (full mode 항상 실행).
    # RULE 7 정합 — single-variable, 임계/가중치 변경 X.
    if effective_mode == "full":
        try:
            vol_stats_refresh = compute_universe_vol_stats(candidates)
            refreshed = 0
            for stock in candidates:
                if stock.get("volatility_20d") is None:
                    continue
                try:
                    new_vol = compute_volatility_score(stock, universe_stats=vol_stats_refresh)
                    stock.setdefault("quant_factors", {})["volatility"] = new_vol
                    refreshed += 1
                except Exception:
                    pass
            if refreshed:
                print(f"\n[5.05] quant_volatility 재계산 → {refreshed}/{len(candidates)} 종목 (STEP 5.8 multi_factor cascade)")
        except Exception as e:
            print(f"\n[5.05] quant_volatility 재계산 스킵: {e}")

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
        print("\n[5.7] DART 재무제표 + 현금흐름 + 사업장 현황 수집")
        from api.collectors.DartScout import scout, fetch_business_facilities_raw
        from api.collectors.dart_corp_code import get_corp_code

        # 사업보고서 rcept_no 캐싱 (연 1회 공시) — Gemini 중복 호출 방지
        _fac_cache: dict = {}
        try:
            import json as _json
            from pathlib import Path as _Path
            _prev_path = _Path("data/portfolio.json")
            if _prev_path.exists():
                _prev = _json.loads(_prev_path.read_text(encoding="utf-8"))
                for _r in _prev.get("recommendations", []):
                    _fac = _r.get("facilities_dart")
                    if _fac and _fac.get("rcept_no"):
                        _fac_cache[_r.get("ticker")] = _fac
        except Exception:
            pass

        dart_ok = 0
        dart_timeout = 0
        fac_ok = 0
        for stock in candidates:
            if stock.get("currency") == "USD":
                continue
            ticker_yf = stock.get("ticker_yf", f"{stock['ticker']}.KS")
            dart_data = safe_collect(
                scout, ticker_yf,
                name=f"DART({stock.get('name', ticker_yf)})", timeout=90, default={},
            )
            if dart_data and not dart_data.get("error") and not dart_data.get("critical_error"):
                has_timeout = any(
                    isinstance(v, dict) and v.get("status") == "timeout"
                    for v in dart_data.values()
                )
                if has_timeout:
                    dart_timeout += 1
                stock["dart_financials"] = {
                    "financials": dart_data.get("financials", {}),
                    "cashflow": dart_data.get("cashflow", {}),
                    "dividends": dart_data.get("dividends", []),
                    "audit_opinion": dart_data.get("audit_opinion", ""),
                    "property_assets": dart_data.get("property_assets", {}),
                }
                # ── Phase 1.B / §15 거버넌스 시그널 — top-level attach ──
                # verity_brain._compute_fact_score 가 stock.get("treasury_stock") 등
                # top-level 키로 직접 접근하므로 dart_financials 서브딕셔너리에 넣지 않음.
                if dart_data.get("treasury_stock"):
                    stock["treasury_stock"] = dart_data["treasury_stock"]
                if dart_data.get("exec_compensation"):
                    stock["exec_compensation"] = dart_data["exec_compensation"]
                if dart_data.get("major_shareholder_changes"):
                    stock["major_shareholder_changes"] = dart_data["major_shareholder_changes"]
                dart_ok += 1

            # 사업장/해외 거점 — 사업보고서 "II. 사업의 내용" 파싱
            try:
                corp_code = get_corp_code(ticker_yf)
                if not corp_code:
                    continue
                prev_fac = _fac_cache.get(stock.get("ticker")) or {}
                raw = safe_collect(
                    fetch_business_facilities_raw, corp_code,
                    name=f"DART-Facil({stock.get('name')})", timeout=60, default={},
                )
                if raw and not raw.get("error") and raw.get("char_count", 0) > 300:
                    # tangible_assets 키 있는 신 스키마 파싱만 재사용 — 구 캐시(토지 필드 부재)는 1회 재파싱(자가치유).
                    if prev_fac.get("rcept_no") == raw.get("rcept_no") and prev_fac.get("data") and "tangible_assets" in prev_fac["data"]:
                        stock["facilities_dart"] = prev_fac
                        fac_ok += 1
                    else:
                        from api.analyzers.facilities_parser import parse_business_facilities
                        # 유형자산 주석(토지·건물 장부금액) additive 피드 — 본문 재무제표엔 유형자산 총계만.
                        _fac_rt = raw.get("raw_text") or ""
                        _fac_ppe = raw.get("ppe_note_text") or ""
                        if _fac_ppe:
                            _fac_rt = _fac_rt + "\n\n=== 유형자산 주석 ===\n" + _fac_ppe
                        parsed = safe_collect(
                            parse_business_facilities,
                            stock.get("name", ticker_yf), stock.get("ticker"), _fac_rt,
                            name=f"DART-FacilParse({stock.get('name')})",
                            timeout=90, default={},
                        )
                        if parsed and not parsed.get("error"):
                            stock["facilities_dart"] = {
                                "rcept_no": raw.get("rcept_no"),
                                "rcept_dt": raw.get("rcept_dt"),
                                "report_nm": raw.get("report_nm"),
                                "bsns_year": raw.get("bsns_year"),
                                "data": parsed,
                            }
                            fac_ok += 1
                elif prev_fac.get("data"):
                    stock["facilities_dart"] = prev_fac
                    fac_ok += 1
            except Exception as e:
                print(f"    사업장 파싱 실패({stock.get('name')}): {e}")

        timeout_note = f" (timeout: {dart_timeout})" if dart_timeout else ""
        print(f"  {dart_ok}/{len(candidates)} 종목 DART 재무, {fac_ok} 종목 사업장 파싱 완료{timeout_note}")

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
        us_data_requests_est = len(us_targets) * 11  # Finnhub 7 + SEC 3 + yfinance 1
        scope_label = "전체" if is_us_mode else f"상위 {us_limit}개"
        print(f"\n[5.71] 미장 데이터 수집 — {scope_label} ({len(us_targets)}종목, Finnhub/SEC/yfinance)")
        from api.collectors import finnhub_client as finnhub
        from api.collectors import sec_edgar as sec
        from api.config import FINNHUB_API_KEY, SEC_EDGAR_USER_AGENT

        # 10-K Item 2 파싱은 accession 기반 캐싱(연 1회 공시)
        # full 모드라도 이전 portfolio에서 매핑 로드해 Gemini 중복 호출 방지
        _props_cache: dict = {}
        try:
            import json as _json
            from pathlib import Path as _Path
            _prev_path = _Path("data/portfolio.json")
            if _prev_path.exists():
                _prev = _json.loads(_prev_path.read_text(encoding="utf-8"))
                for _r in _prev.get("recommendations", []):
                    _pr = _r.get("properties_10k")
                    if _pr and _pr.get("accession"):
                        _props_cache[_r.get("ticker")] = _pr
        except Exception:
            pass

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

            # 공매도는 yfinance로 전환 (Polygon Options Starter $29/월 절감)
            # 옵션 플로우·Pre/After는 중장기 투자에서 효용 낮아 제거
            from api.collectors.stock_data import get_short_interest_yf
            ticker_yf = stock.get("ticker_yf") or ticker
            si = safe_collect(
                get_short_interest_yf, ticker_yf,
                name=f"ShortInt({ticker})", timeout=30, default={},
            )
            if si:
                stock["short_interest"] = si

            # 10-K Item 2 Properties — 연 1회 공시라 accession 캐싱으로 중복 파싱 방지
            try:
                prev_props = _props_cache.get(ticker) or {}
                raw = safe_collect(
                    sec.fetch_10k_properties_section, ticker, SEC_EDGAR_USER_AGENT,
                    name=f"10K-Item2({ticker})", timeout=60, default={},
                )
                if raw and not raw.get("error") and raw.get("char_count", 0) > 200:
                    if prev_props.get("accession") == raw.get("accession") and prev_props.get("data"):
                        stock["properties_10k"] = prev_props
                    else:
                        from api.analyzers.properties_parser import parse_10k_properties
                        parsed = safe_collect(
                            parse_10k_properties, name, ticker, raw["raw_text"],
                            name=f"10K-Parse({ticker})", timeout=90, default={},
                        )
                        if parsed and not parsed.get("error"):
                            stock["properties_10k"] = {
                                "accession": raw.get("accession"),
                                "filed_date": raw.get("filed_date"),
                                "source_url": raw.get("url"),
                                "data": parsed,
                            }
                            print(f"      10-K Properties 파싱 완료 ({raw.get('filed_date')})")
                elif prev_props.get("data"):
                    stock["properties_10k"] = prev_props
            except Exception as e:
                print(f"      10-K Properties 수집 실패: {e}")

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

    # [5.76] fair_value_gap 관측 (RIM V/P + implied-g) — 점수 wire 0, 사전등록(~2028-29 검증 대기)
    if not is_us_mode:
        try:
            from api.observability.fair_value_gap import run_fair_value_gap_observation
            _fvg = run_fair_value_gap_observation(candidates)
            print(f"  [5.76] fair_value_gap 관측: {_fvg.get('tickers')}종목 "
                  f"(저평가 {_fvg.get('undervalued')} / trap후보 {_fvg.get('value_trap_candidate')}) "
                  f"logged={_fvg.get('logged')}")
        except Exception as _e:
            print(f"  [5.76] fair_value_gap 관측 스킵: {_e}")

    # [5.77] 분산매도 정황 관측 (외국인/기관 순매도 + DART 5%룰 축소) — 점수 wire 0.
    # AlphaNest 유리박스 역(방어) 렌즈. 사전등록 docs/PREREG_DISTRIBUTION_FOOTPRINT_2026_06_25.md
    # (점수화=forward-IC N≥50 게이트 후). flow(KIS)는 종목별 이미 부착(STEP 데이터 보강).
    if not is_us_mode:
        try:
            from api.intelligence.distribution_footprint import log_distribution_observations
            _dist = log_distribution_observations(candidates)
            print(f"  [5.77] 분산매도 정황 관측: {_dist}종목 발화 logged")
        except Exception as _e:
            print(f"  [5.77] 분산매도 정황 관측 스킵: {_e}")

    # [5.78] earnings surprise 관측 (PEAD, US Phase 1a) — 점수 wire 0, brain_input=False, 사전등록.
    #   스펙 docs/earnings_surprise_pead_spec_v0_2026_06_19.md §4(2단계 채점 ①). forward eval=Phase 1b 별도 cron.
    #   us_candidates_571 = earnings_surprises 부착된 리스트(L3087). 부재 시 run_shadow no-op(안전).
    #   🚨 KR 경로 = ConsensusScout 연간추정 vs DART 분기actual mismatch → PM 결정 대기(본 step US-only).
    if effective_mode == "full" and us_candidates_571:
        try:
            from api.intelligence.earnings_surprise import run_shadow as _es_run_shadow
            _es = _es_run_shadow(us_candidates_571)
            print(f"  [5.78] earnings surprise 관측(US): 신규 {_es.get('new_events')}건 "
                  f"(중복스킵 {_es.get('skipped_seen')} / universe {_es.get('universe')})")
        except Exception as _e:
            print(f"  [5.78] earnings surprise 관측 스킵: {_e}")

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

    # ── STEP 5.78: full 전용 — DART catalyst alert (2026-05-19 추가) ──
    # 운영 풀 KR 종목 직전 7일 catalyst (주요사항 B / 발행 C / 지분 D + 정정) 자동 감지.
    # 산식 동결 가드 정합 (B 옵션 6월 중순) — brain 산식 영향 X, 별 reporting 만.
    # data/dart_catalyst_alerts.jsonl append (dedupe by rcept_no).
    # Perplexity narrative 자동화는 별 모듈 (큐잉).
    if effective_mode == "full":
        try:
            from api.collectors.dart_catalyst import (
                fetch_catalysts_for_pool, persist_catalyst_alerts,
            )
            from api.collectors.dart_corp_code import get_corp_code as _get_cc_cat
            cat_stocks: Dict[str, Dict[str, Any]] = {}
            for s in candidates:
                t = s.get("ticker")
                if not t or s.get("currency") == "USD":
                    continue
                t6 = str(t).split(".")[0].zfill(6)
                cc = s.get("corp_code")
                if not cc:
                    try:
                        cc = _get_cc_cat(s.get("ticker_yf") or t)
                    except Exception:
                        cc = None
                if cc:
                    cat_stocks[t6] = {"name": s.get("name", t), "corp_code": cc}

            if cat_stocks:
                print(f"\n[5.78] DART catalyst 감지 (KR {len(cat_stocks)}종목, 직전 7d)")
                cat_result = fetch_catalysts_for_pool(cat_stocks, lookback_days=7)
                cs = cat_result.get("stats", {})
                events = cat_result.get("events", [])
                new_count = persist_catalyst_alerts(events)
                print(
                    f"  catalyst {cs.get('total', 0)}건 "
                    f"(주요사항 {cs.get('by_type', {}).get('B', 0)} / "
                    f"발행 {cs.get('by_type', {}).get('C', 0)} / "
                    f"지분 {cs.get('by_type', {}).get('D', 0)} / "
                    f"정정 {cs.get('corrections', 0)}) "
                    f"→ {new_count} 신규 alert append"
                )
                portfolio["dart_catalyst_alerts"] = cat_result
        except Exception as e:
            print(f"  ⚠️ DART catalyst 감지 스킵: {e}")

        # 5.78b: 시장 전체 catalyst (KOSPI+KOSDAQ 전 종목 — 공개 터미널 커버리지 확장 2026-06-18)
        # 운영풀 수집(위)에 추가. 동일 jsonl 에 dedup(rcept_no) append. brain 산식 영향 0.
        try:
            from api.collectors.dart_catalyst import (
                fetch_catalysts_market_wide, persist_catalyst_alerts as _persist_cat_mw,
            )
            print("\n[5.78b] DART 시장 전체 catalyst (KOSPI+KOSDAQ, 직전 7d)")
            _mw = fetch_catalysts_market_wide(lookback_days=7)
            _mws = _mw.get("stats", {})
            _mw_new = _persist_cat_mw(_mw.get("events", []))
            print(
                f"  시장전체 {_mws.get('total', 0)}건 / {_mws.get('tickers', 0)}종목 "
                f"→ {_mw_new} 신규 append"
            )
        except Exception as e:
            print(f"  ⚠️ DART 시장 전체 catalyst 스킵: {e}")

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
                    bond_regime=(portfolio.get("bonds") or {}).get("bond_regime"),
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
        # 2026-05-30 — injection mismatch 진단 (4 종목 silent miss audit, [[project_data_audit_2026_05_27]])
        kr_cand_tickers = {str(s.get("ticker", "")).zfill(6) for s in candidates if s.get("currency") != "USD"}
        kis_only = sorted(set(kis_brain_map.keys()) - kr_cand_tickers)
        cand_only = sorted(kr_cand_tickers - set(kis_brain_map.keys()))
        overlap = len(kr_cand_tickers & set(kis_brain_map.keys()))
        if kis_only or cand_only:
            print(f"  [KIS_injection_mismatch] overlap={overlap}/{len(kr_cand_tickers)} candidates ∩ {len(kis_brain_map)} KIS", file=sys.stderr)
            print(f"  [KIS_injection_mismatch] KIS only (수집 후 추천 풀 X) N={len(kis_only)}: {kis_only[:10]}", file=sys.stderr)
            print(f"  [KIS_injection_mismatch] candidates only (추천 풀 안 KIS 수집 X) N={len(cand_only)}: {cand_only[:10]}", file=sys.stderr)
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

    # ── STEP 5.87: full 전용 — 증권사 애널리스트 리포트 수집 + Gemini AI 요약 ──
    # ReportScout: 네이버 기업/산업 리포트 PDF URL 메타 (1일 1회)
    # report_summarizer: PDF → Gemini Flash 요약 → 종목별 집계 (analyst_sentiment_score 등)
    # verity_brain 이 analyst_report_summary 를 fact_score 컴포넌트로 사용하므로 Brain 직전 실행.
    # 🚨 2026-08-14 분리 — 수집·요약(51.4분)을 scripts/analyst_reports_cron.py 로 옮겼다.
    #   실측: daily_analysis_full 4회 연속 실패(fail 2/cancel 2). 원인은 run 117분 vs 워치독
    #   110분 초과이고, 그 117분의 구간 프로파일이 5.87 리포트 51.4분 / STEP 3 기술적분석
    #   33.5분 / 5.75 NAV 14.2분이었다. 5.87 한 구간이 44% 였다.
    #   Brain 이 쓰는 것은 attach 산물(analyst_report_summary)뿐이고 집계는 이미
    #   data/report_summaries.json 에 원자적으로 저장된다 → 여기서는 읽어서 붙이기만 한다.
    #   산식·선정 로직 무변경, 수집 시점만 앞선 cron(평일 KST 13:20)으로 이동.
    #   🚨 인라인 재수집 fallback 을 두지 않는다 — 그걸 두면 파일이 없는 날 다시 51분이
    #     들어와 같은 초과가 재발한다. 부재는 결손으로 신고하고 파이프라인은 계속 간다.
    if effective_mode == "full":
        print("\n[5.87] 증권사 리포트 요약 부착 (수집=analyst_reports cron 분리)")
        try:
            from api.analyzers.report_summarizer import SUMMARIES_PATH as _RS_PATH
            summary_result: Dict[str, Any] = {}
            if os.path.exists(_RS_PATH):
                with open(_RS_PATH, encoding="utf-8") as _f:
                    summary_result = json.load(_f) or {}
            _upd = summary_result.get("updated_at") or "?"
            _age_h = None
            try:
                # 🚨 main.py 에는 datetime 모듈 상단 import 가 없다 — 파일 전역이 블록마다
                #   지역 import 하는 관례다. 바로 `datetime.fromisoformat` 를 쓰면 NameError 가
                #   나는데 이 try 가 삼켜서 _age_h=None 이 되고, stale 경고가 영구히 안 뜬다
                #   (2026-08-14 작성 직후 발견 — 조용히 꺼진 가드).
                from datetime import datetime as _dt
                _age_h = (now_kst() - _dt.fromisoformat(_upd)).total_seconds() / 3600
            except Exception:  # noqa: BLE001
                pass
            _st = summary_result.get("stats", {}) or {}
            print(f"  집계 파일 {os.path.basename(_RS_PATH)} · updated_at {_upd}"
                  + (f" ({_age_h:.1f}h 전)" if _age_h is not None else "")
                  + f" · 종목 {_st.get('tickers_aggregated', 0)}")
            if _age_h is not None and _age_h > 48:
                # 신선도 이탈은 조용히 넘기지 않는다. 파이프라인은 계속 가되 사실을 남긴다.
                print(f"  ⚠️ report_summaries 48h 초과 stale ({_age_h:.1f}h) — "
                      f"analyst_reports cron 점검 필요")
            if not summary_result:
                print("  ⚠️ report_summaries.json 부재 — analyst_report_summary 부착 0 "
                      "(Brain 은 해당 컴포넌트 없이 진행)")

            # 우선순위 티커 선정(운영 후보 KR + 운영 풀 KR, dedupe)은 분리된 러너가
            # 같은 규칙으로 디스크에서 수행한다 — scripts/analyst_reports_cron.py::_priority_tickers.
            # 2026-05-18 A2 / 2026-05-19 A2.1 fix 의 의도(운영 풀 우선, 모드 무관 KR pool)는
            # 그쪽에 그대로 옮겨져 있다.
            summaries = summary_result.get("summaries", {})
            analyst_attached = 0
            for stock in candidates:
                t = stock.get("ticker")
                if not t:
                    continue
                t6 = str(t).split(".")[0].zfill(6)
                agg = summaries.get(t6)
                if agg:
                    stock["analyst_report_summary"] = agg
                    analyst_attached += 1
            if analyst_attached:
                print(f"  ✓ {analyst_attached}개 종목에 analyst_report_summary 부착")
        except Exception as e:
            print(f"  ⚠️ 리포트 수집/요약 스킵: {e}")

    # ── STEP 5.88: full 모드 — DART 사업보고서 AI 분석 ──
    # 사업보고서는 연 1회 발행 + 캐시 — full 모드 매 run 시도 (cache hit dominant 예상).
    # 2026-05-18 A1 fix (PM 승인) — docs/BRAIN_SCORE_AUDIT_20260518.md §6 root cause #1
    # ("data fallback dominance"): dart_business_analysis 0/25 영구 fallback.
    # 옛: weekend 제한 (주 1회) → 신: full 매 run. KR 10 종목 × 1회/일 = +10 DART 호출,
    # 한도 20K/day 의 0.05% 수준. cache 활용 dominant (사업보고서 연 1회 발행).
    # 16:07 KST 평일 daily_full 첫 호출 시 cache miss → 신규 분석 (Gemini 호출 0.05 USD 종목당).
    if effective_mode == "full":
        print("\n[5.88] DART 사업보고서 AI 분석 (full)")
        try:
            from api.collectors.dart_corp_code import get_corp_code as _get_cc
            # 2026-05-18 fix v2 — A1 fix 가 옛 weekend 분기 제거 시 `from datetime import datetime as _dt`
            # import 같이 제거 → trigger run 26011919102 "cannot access local variable '_dt'" fail.
            from datetime import datetime as _dt

            # candidates 에서 KR 종목만 → ticker6 dict 재구성
            stocks_dict = {}
            _last_fy = str(_dt.now().year - 1)
            for stock in candidates:
                t = stock.get("ticker")
                if not t or stock.get("currency") == "USD":
                    continue
                t6 = str(t).split(".")[0].zfill(6)
                cc = stock.get("corp_code")
                if not cc:
                    try:
                        cc = _get_cc(stock.get("ticker_yf") or t)
                    except Exception:
                        cc = None
                if cc:
                    stocks_dict[t6] = {
                        "name": stock.get("name", t),
                        "corp_code": cc,
                        "bsns_year": _last_fy,
                    }

            if stocks_dict:
                dart_result = analyze_all_business_reports(stocks_dict, auto_fetch_missing=True)
                ds = dart_result.get("stats", {})
                print(f"  분석 총 {ds.get('total', 0)} · 신규 {ds.get('new_analyzed', 0)} "
                      f"· 캐시 hit {ds.get('cache_hit', 0)} · skip {ds.get('skipped', 0)}")
                # 2026-05-19 A4 fix — _skip_reason 분포 노출. 진단 enabler:
                # fetch_failed/ai_fail (transient) vs no_raw_or_too_short (structural).
                _sr = ds.get("skip_reasons") or {}
                if _sr:
                    _sr_str = ", ".join(f"{k}={v}" for k, v in sorted(_sr.items(), key=lambda x: -x[1]))
                    print(f"  skip 분포: {_sr_str}")
                    _st = ds.get("skip_tickers") or {}
                    for _reason, _tks in _st.items():
                        print(f"    {_reason}: {', '.join(_tks[:10])}")
                results = dart_result.get("results", {})
                dart_attached = 0
                for stock in candidates:
                    t = stock.get("ticker")
                    if not t:
                        continue
                    t6 = str(t).split(".")[0].zfill(6)
                    analysis = results.get(t6)
                    if analysis and "_skip_reason" not in analysis:
                        stock["dart_business_analysis"] = analysis
                        dart_attached += 1
                if dart_attached:
                    print(f"  ✓ {dart_attached}개 종목에 dart_business_analysis 부착")

                # ── DART 2차 원문 심화: 특수관계자/대주주 거래 터널링 분석 ──
                # 2026-06-03. 🚨 관측 only — dart_related_party 데이터 필드로만 부착.
                # scored risk_flags 미주입(detected_risk_keywords→auto_avoid 경로로 Brain
                # 점수 영향 = RULE 7). 점수 반영은 N 누적 후 사전등록 + PM 승인.
                try:
                    from api.analyzers.dart_related_party import analyze_all_related_party
                    rp_result = analyze_all_related_party(stocks_dict, auto_fetch_missing=True)
                    rp_attached = rp_high = 0
                    for stock in candidates:
                        t = stock.get("ticker")
                        if not t:
                            continue
                        t6 = str(t).split(".")[0].zfill(6)
                        rp = rp_result.get(t6)
                        if rp and "_skip_reason" not in rp:
                            stock["dart_related_party"] = rp
                            rp_attached += 1
                            if rp.get("severity") == "high":
                                rp_high += 1
                    if rp_attached:
                        print(f"  ✓ {rp_attached}개 종목에 dart_related_party 부착 "
                              f"(터널링 고위험 {rp_high}, 관측 only)")
                except Exception as e:
                    print(f"  ⚠️ 특수관계자 분석 스킵: {e}")

                # ── DART 2차 원문 심화: 소송/우발부채/제재 분석 ──
                # 2026-06-06. 🚨 관측 only — dart_litigation 데이터 필드로만 부착.
                # distress(회생·파산, dart_disclosure_events)와 별개 = 진행 중 소송 *규모*·
                # 우발채무. scored risk_flags 미주입(RULE 7, 점수 반영은 N 누적 후 사전등록 + PM 승인).
                try:
                    from api.analyzers.dart_litigation import analyze_all_litigation
                    lit_result = analyze_all_litigation(stocks_dict, auto_fetch_missing=True)
                    lit_attached = lit_high = 0
                    for stock in candidates:
                        t = stock.get("ticker")
                        if not t:
                            continue
                        t6 = str(t).split(".")[0].zfill(6)
                        lit = lit_result.get(t6)
                        if lit and "_skip_reason" not in lit:
                            stock["dart_litigation"] = lit
                            lit_attached += 1
                            if lit.get("severity") == "high":
                                lit_high += 1
                    if lit_attached:
                        print(f"  ✓ {lit_attached}개 종목에 dart_litigation 부착 "
                              f"(소송·우발부채 고위험 {lit_high}, 관측 only)")
                except Exception as e:
                    print(f"  ⚠️ 소송·우발부채 분석 스킵: {e}")

                # ── 🚨 감사보고서 핵심감사사항(KAM) 판독 (2026-08-16 신설, PM 승인) ──
                # 감사인이 "가장 위험하다고 본 것" 을 직접 적어둔 산문. 2018년부터 의무 기재인데
                # 우리는 한 번도 읽은 적이 없었다(전수 grep 0건). 정형 필드가 없어 LLM 판독만 가능.
                # 🚨 관측 only — 산출은 점수가 아니라 **사실**(감사인이 X 를 지목했다)이라
                #    추출 정확도로 검증 가능. 점수 반영은 표본 검증 + 사전등록 후.
                try:
                    from api.analyzers.dart_kam import analyze_all_kam
                    kam_result = analyze_all_kam(stocks_dict)
                    kam_attached = kam_total = 0
                    for stock in candidates:
                        t = stock.get("ticker")
                        if not t:
                            continue
                        t6 = str(t).split(".")[0].zfill(6)
                        km = kam_result.get(t6)
                        if km and "_skip_reason" not in km:
                            stock["dart_kam"] = km
                            kam_attached += 1
                            kam_total += int(km.get("kam_count") or 0)
                    if kam_attached:
                        print(f"  ✓ {kam_attached}개 종목에 dart_kam 부착 "
                              f"(핵심감사사항 {kam_total}건, 관측 only)")
                except Exception as e:
                    print(f"  ⚠️ 핵심감사사항 판독 스킵: {e}")

                # ── DART 주요사항: CB/BW 전환·행사 오버행(잠재 희석) ──
                # 2026-07-10. 🚨 관측 only · 사실만 — 발행규모·전환가·발행가능주식수·희석률.
                # 구조화 파싱(LLM 0) · 자체 점수 0(RULE 7). dart_cb_bw 필드로만 부착.
                try:
                    from api.analyzers.dart_cb_bw import analyze_all_cb_bw
                    cbw_result = analyze_all_cb_bw(stocks_dict)
                    cbw_attached = 0
                    for stock in candidates:
                        t = stock.get("ticker")
                        if not t:
                            continue
                        t6 = str(t).split(".")[0].zfill(6)
                        cbw = cbw_result.get(t6)
                        if cbw and cbw.get("n_instruments"):
                            stock["dart_cb_bw"] = cbw
                            cbw_attached += 1
                    if cbw_attached:
                        print(f"  ✓ {cbw_attached}개 종목에 dart_cb_bw 부착 (CB/BW 오버행, 관측 only)")
                except Exception as e:
                    print(f"  ⚠️ CB/BW 오버행 분석 스킵: {e}")

                # ── DART 공시 이벤트 스캔: 유상증자/정정/불성실/distress ──
                # 2026-06-04. 키워드 분류(LLM 0). 🚨 distress/불성실 = 2026-06-05 점수 사전등록
                # (factors/red_flags.py, RULE 7 PM 승인). 유상증자/정정/올빼미 = 관측 only(임계 fit 대기).
                try:
                    from api.analyzers.dart_disclosure_events import scan_disclosure_events
                    ev_result = scan_disclosure_events(stocks_dict, window_days=90)
                    ev_attached = ev_flagged = 0
                    for stock in candidates:
                        t = stock.get("ticker")
                        if not t:
                            continue
                        t6 = str(t).split(".")[0].zfill(6)
                        ev = ev_result.get(t6)
                        if ev:
                            stock["dart_disclosure_events"] = ev
                            ev_attached += 1
                            if ev.get("severity") in ("high", "medium"):
                                ev_flagged += 1
                    if ev_attached:
                        print(f"  ✓ {ev_attached}개 종목에 dart_disclosure_events 부착 "
                              f"(이벤트 {ev_flagged}, 관측 only)")
                except Exception as e:
                    print(f"  ⚠️ 공시 이벤트 스캔 스킵: {e}")

                # ── DART 감사 신호: going-concern/강조사항 ──
                # 2026-06-04. doubt 전용 구문(boilerplate 회피). 🚨 going_concern_doubt =
                # 2026-06-05 점수 사전등록(factors/red_flags.py, RULE 7 PM 승인). 강조사항 = 관측 only.
                try:
                    from api.analyzers.dart_audit_signals import scan_audit_signals
                    au_result = scan_audit_signals(stocks_dict)
                    au_attached = au_flagged = 0
                    for stock in candidates:
                        t = stock.get("ticker")
                        if not t:
                            continue
                        t6 = str(t).split(".")[0].zfill(6)
                        au = au_result.get(t6)
                        if au:
                            stock["dart_audit_signals"] = au
                            au_attached += 1
                            if au.get("going_concern_doubt"):
                                au_flagged += 1
                    if au_attached:
                        print(f"  ✓ {au_attached}개 종목에 dart_audit_signals 부착 "
                              f"(going-concern {au_flagged}, 관측 only)")
                except Exception as e:
                    print(f"  ⚠️ 감사 신호 스캔 스킵: {e}")

                # ── 배당 정책 변화 이벤트: 개시/삭감/중단 ──
                # 2026-06-13. 기존 dividends_kr.json history 의 year-over-year 비교(추가 DART 콜 0).
                # 🚨 관측 only — dividend_policy_change 데이터 필드만. scored risk_flags 미주입
                # (RULE 7, 신규 신호). cut/omission 약신호도 점수/verdict 피드백 0. 점수 반영은
                # N 누적 후 사전등록 + PM 승인. spec docs/dividend_policy_change_spec_v0_2026_06_13.md.
                try:
                    from api.analyzers.dividend_policy_change import scan_dividend_policy_changes
                    dpc_result = scan_dividend_policy_changes(stocks_dict)
                    dpc_attached = dpc_flagged = 0
                    for stock in candidates:
                        t = stock.get("ticker")
                        if not t:
                            continue
                        t6 = str(t).split(".")[0].zfill(6)
                        dpc = dpc_result.get(t6)
                        if dpc:
                            stock["dividend_policy_change"] = dpc
                            dpc_attached += 1
                            if dpc.get("severity") in ("high", "medium"):
                                dpc_flagged += 1
                    if dpc_attached:
                        print(f"  ✓ {dpc_attached}개 종목에 dividend_policy_change 부착 "
                              f"(삭감·중단 {dpc_flagged}, 관측 only)")
                except Exception as e:
                    print(f"  ⚠️ 배당 정책 변화 스캔 스킵: {e}")

                # ── DART 기관 대량보유(5%+) — 2026-06-07 (action_queue d7158b4f) ──
                # 🚨 관측 only — dart_major_holders 데이터 필드만. 결정/점수 미반영 (RULE 7,
                # 신규 신호). 기관 순매집/처분 = smart-money flow(약 prior). 점수 편입 = 검증 후.
                try:
                    from api.collectors.dart_major_holders import analyze_all as _mh_all
                    mh_result = _mh_all(stocks_dict)
                    mh_attached = mh_accum = 0
                    for stock in candidates:
                        t = stock.get("ticker")
                        if not t:
                            continue
                        t6 = str(t).split(".")[0].zfill(6)
                        mh = mh_result.get(t6)
                        if mh:
                            stock["dart_major_holders"] = mh
                            mh_attached += 1
                            if mh.get("net_flow_direction") == "accumulate":
                                mh_accum += 1
                    if mh_attached:
                        print(f"  ✓ {mh_attached}개 종목에 dart_major_holders 부착 "
                              f"(기관 순매집 {mh_accum}, 관측 only)")
                except Exception as e:
                    print(f"  ⚠️ 기관 대량보유 수집 스킵: {e}")
            else:
                print(f"  KR 종목 없음 — skip")
        except Exception as e:
            print(f"  ⚠️ DART 분석 스킵: {e}")

    # ── STEP 5.89 (2026-05-19 추가): Perplexity 외부 리스크 — BEFORE brain ──
    # 옛 STEP 5.95 (post-brain) 순서 결함 fix.
    # 진단 (docs/BRAIN_SCORE_AUDIT_20260518.md §9 B audit):
    #   external_risk raw 10/25 종목 부착 → brain 안에서 perplexity_risk 100% fallback.
    #   STEP 5.95 가 brain 직후 실행돼 perplexity_risk_score 가 매번 50 (default).
    # Fix: brain 직전 attach → brain fact_score component perplexity_risk_score 정상 작동.
    #   _RISK_SCORE_MAP {LOW:60, MODERATE:40, HIGH:15, CRITICAL:5} 그대로 활용.
    # 선정: brain_score 없으므로 multi_factor.multi_score desc top-N.
    # RULE 7 단일 변수 통제 — 선정 logic + 실행 순서만 변경, 임계/가중치 X.
    PERPLEXITY_RISK_SCAN_TOP_N = 10  # 운영 cron 호출 cap (Perplexity rate + 비용 budget)
    if effective_mode == "full" and PERPLEXITY_API_KEY:
        ranked = sorted(
            [s for s in candidates if not s.get("detected_risk_keywords")],
            key=lambda s: s.get("multi_factor", {}).get("multi_score", 0),
            reverse=True,
        )
        top_candidates = ranked[:PERPLEXITY_RISK_SCAN_TOP_N]
        if top_candidates:
            top_ms = top_candidates[0].get("multi_factor", {}).get("multi_score", 0)
            bot_ms = top_candidates[-1].get("multi_factor", {}).get("multi_score", 0)
            print(
                f"\n[5.89] Perplexity 외부 리스크 스캔 (상위 {len(top_candidates)}종목, "
                f"multi_score {bot_ms}~{top_ms}) — pre-brain"
            )
            try:
                from api.intelligence.perplexity_realtime import research_stock_risk
                hi_cnt = 0
                for stock in top_candidates:
                    sname = stock.get("name", stock.get("ticker", "?"))
                    msc = stock.get("multi_factor", {}).get("multi_score", 0)
                    risk = research_stock_risk(stock)
                    stock["external_risk"] = risk
                    lvl = risk.get("risk_level")
                    if lvl == "HIGH":
                        hi_cnt += 1
                        print(f"  [Perplexity] HIGH: {sname} (multi={msc})")
                    elif "error" not in risk:
                        print(f"  [Perplexity] {lvl or '?'}: {sname}")
                print(f"  → 부착 {len(top_candidates)}건 (HIGH {hi_cnt}), brain perplexity_risk 활성")
            except Exception as e:
                print(f"  ⚠️ 외부 리스크 스캔 스킵: {e}")

    # ── STEP 5.9: Verity Brain — 종합 판단 엔진 ──
    print("\n[5.9] Verity Brain 종합 판단")

    # US/KR 모드별로 recommendations를 MERGE (상대 시장 종목 보존)
    prev_recs_all = portfolio.get("recommendations", [])
    if is_us_mode:
        kept = [r for r in prev_recs_all if r.get("currency") != "USD"]
        # 🚨 2026-08-21 — `kept + candidates` 였다. 아래 dedup 이 **먼저 온 것을 채택**하므로
        #   중복 티커에서 **이월(stale) 레코드가 신규를 이겼다**. 바로 아래 주석이
        #   "신규 우선" 이라 선언하는데 코드가 반대였다 = 코드를 주석에 맞춘다.
        #   scope=all 런에서는 이 분기를 안 타 잠복이었고(실측 최근 full run 3/3 이 scope=all),
        #   `a0d6105f0` 로 full_us 가 부활하면서 발현 가능해졌다.
        merged = candidates + kept
        print(f"  [MERGE] 기존 KR {len(kept)}개 보존 + 신규 US {len(candidates)}개")
    else:
        kept = [r for r in prev_recs_all if r.get("currency") == "USD"]
        merged = candidates + kept
        print(f"  [MERGE] 신규 KR+US {len(candidates)}개 + 기존 US-only {len(kept)}개 보존")
    # 🚨 2026-08-21 — 이월 레코드 자기신고. 이월 자체는 **유지**한다(재분석은 런타임 비용이
    #   크고 이미 60분 타임아웃 이력이 있다). 문제는 이월분이 `verity_brain.grade` ·
    #   `overrides_applied`(거시 캡) 를 **다른 시장 국면에서 계산된 채** 달고 온다는 것이다.
    #   실측 8/20 — `kr_decoupling_weak` 캡이 KOSPI −5.8% 국면에서 정당하게 붙었는데,
    #   KOSPI 가 +6% 로 뒤집힌 뒤에도 이월로 계속 살아 BUY 7건을 전부 WATCH 로 덮었다.
    #   소비자가 "지금 계산된 값" 과 "이월된 값" 을 구분할 수 있어야 한다 (RULE 12).
    _fresh_tickers = {r.get("ticker") for r in candidates}
    _carried_n = 0
    for r in kept:
        if r.get("ticker") in _fresh_tickers:
            continue  # dedup 에서 신규가 이기므로 이월 아님
        r["_carried"] = {
            "as_of": r.get("collected_at") or portfolio.get("updated_at"),
            "reason": "opposite_market_scope",
            "frozen_fields": ["verity_brain", "overrides_applied",
                              "multi_factor", "technical"],
            "note": "이 레코드는 이번 런에서 재분석되지 않았다 — 등급·거시캡은 이월 시점 기준",
        }
        _carried_n += 1
    # 신규로 재분석된 레코드는 과거 이월 스탬프를 지운다 (stale 스탬프 잔존 방지)
    for r in candidates:
        r.pop("_carried", None)

    # 중복 제거 (ticker 기준, 신규 우선)
    seen_tickers = set()
    deduped = []
    for r in merged:
        tk = r.get("ticker")
        if tk not in seen_tickers:
            seen_tickers.add(tk)
            deduped.append(r)
    print(f"  [MERGE] 이월 자기신고 {_carried_n}건 (_carried 스탬프)")
    portfolio["recommendations"] = deduped
    candidates = deduped

    try:
        from api.collectors.niche_intel import build_niche_data
        _bonds_for_niche = portfolio.get("bonds") or {}
        _global_headlines = portfolio.get("headlines") or []
        _kr_targets = sum(1 for s in candidates if s.get("currency") != "USD")
        for _stock in candidates:
            try:
                _stock["niche_data"] = build_niche_data(
                    _stock,
                    global_headlines=_global_headlines,
                    bonds_data=_bonds_for_niche,
                )
            except Exception:
                _stock.setdefault("niche_data", {})
        _legal_hits_total = sum(len((s.get("niche_data") or {}).get("legal", {}).get("hits", [])) for s in candidates)
        _legal_flagged = sum(1 for s in candidates if (s.get("niche_data") or {}).get("legal", {}).get("risk_flag"))
        print(f"  niche_data 주입: {len(candidates)}종목 (KR {_kr_targets}) · legal hits {_legal_hits_total}건 · flagged {_legal_flagged}종목")
    except Exception as e:
        print(f"  niche_data 생성 실패(무시): {e}")

    # US Financials calibration attach — F-Score → brain fact_score us_fscore 컴포넌트 (RULE 7 PM 승인).
    # data/us_financials/_summary.json (월 1회 cron 커밋) read-only. US 종목만. project_us_financials_sec_edgar v0.4.
    try:
        _usf_path = os.path.join(DATA_DIR, "us_financials", "_summary.json")
        if os.path.exists(_usf_path):
            with open(_usf_path, encoding="utf-8") as _uf:
                _usf_rows = (json.load(_uf) or {}).get("rows", [])
            _usf_map = {str(r.get("ticker", "")).upper(): r for r in _usf_rows}
            _usf_n = 0
            for stock in candidates:
                if stock.get("currency") != "USD":
                    continue
                row = _usf_map.get(str(stock.get("ticker", "")).upper())
                if row and row.get("fscore") is not None:
                    stock["us_fscore"] = row["fscore"]
                    _usf_n += 1
            print(f"  us_fscore 주입: {_usf_n}종목 (US Financials F-Score → brain)")
    except Exception as _usf_e:
        print(f"  us_fscore 주입 실패(무시): {_usf_e}")

    # ── US 애널리스트 컨센서스 주입 (2026-08-20, PM 지시) ─────────────────────────
    # 🚨 **오퍼레이터(알파콘솔) 전용.** 공개 발행에는 나가지 않는다 — 2중 차단:
    #   ① `data/us_analyst_consensus.json` = manifest `banned` (yfinance 재배포 권리 없음,
    #      PM 2026-07-10 · blob 404 실측 8/16)
    #   ② 발행 sanitizer STRIP_KEYS 에 `analyst_consensus` 포함 (2026-08-18)
    #   즉 "백엔드에는 연동, 알파콘솔에서만 사용" 이라는 지시가 기존 가드로 이미 성립한다.
    #
    # WHY: 원본은 5,274종목을 매일 받고 있는데(운영 풀 US 49 중 **49/49** 보유) 이 값이
    #   `recommendations` 에 안 붙어, 대신 Finnhub 값이 그 자리를 차지하고 있었다.
    #   Finnhub 는 무료 플랜에서 `stock/price-target` 403 이라 **목표가가 전부 0** 이고
    #   커버도 29/49 다. 좋은 소스가 있는데 나쁜 소스가 자리를 잡고 있던 형태
    #   (2026-08-20 실측 · `us_fin_annual_compact` 미부착과 같은 형태).
    #
    # 🚨 점수 영향 0 — 헌법 `fact_score.weights` 는 문헌 4축뿐이고 `analyst_consensus` 는
    #   가중이 없다. 관측·판단 보조 자료로만 실린다 (RULE 7 쿼터 미소모).
    # 🚨 Finnhub 값을 덮지 않는다 — `analyst_consensus_yf` 로 따로 싣는다. 같은 키에 두 소스를
    #   섞으면 어느 쪽인지 산출물에서 갈리지 않는다([[feedback_source_attribution_discipline]]).
    try:
        _ac_path = os.path.join(DATA_DIR, "us_analyst_consensus.json")
        if os.path.exists(_ac_path):
            with open(_ac_path, encoding="utf-8") as _acf:
                _ac_doc = json.load(_acf) or {}
            _ac_rows = _ac_doc.get("stocks") or []
            _ac_map = {str(r.get("ticker", "")).upper(): r for r in _ac_rows}
            _ac_asof = (_ac_doc.get("_meta") or {}).get("generated_at")
            _ac_n = 0
            for stock in candidates:
                if stock.get("currency") != "USD":
                    continue
                row = _ac_map.get(str(stock.get("ticker", "")).upper())
                if not row:
                    continue
                stock["analyst_consensus_yf"] = {
                    "rec_key": row.get("rec_key"),
                    "rec_mean": row.get("rec_mean"),
                    "num_analysts": row.get("num_analysts"),
                    "target_mean": row.get("target_mean"),
                    "target_high": row.get("target_high"),
                    "target_low": row.get("target_low"),
                    "upside_pct": row.get("upside_pct"),
                    "counts": row.get("counts"),
                    # 🚨 as_of 필수 — 어제 값을 오늘 값으로 읽는 사고 차단
                    #   ([[feedback_cluster_silent_defect]] 상한 도달 rows[-1] 둔갑)
                    "as_of": row.get("collected_at") or _ac_asof,
                    "source": "yfinance (Yahoo Finance 애널리스트 집계)",
                    "publish": False,
                }
                _ac_n += 1
            print(f"  analyst_consensus_yf 주입: {_ac_n}종목 "
                  f"(오퍼레이터 전용 · 발행 제외 · as_of {str(_ac_asof)[:16]})")
    except Exception as _ac_e:
        print(f"  analyst_consensus_yf 주입 실패(무시): {_ac_e}")

    # new_listings 주입 — 막스 5번째 사이클 신호 "신규 딜 품질" source.
    # data/new_listings.json (월 1회 KRX IPO collector cron 커밋) read-only.
    # market_horizon.classify_new_listing_quality 가 portfolio["new_listings"] 6키 소비.
    # 파일 부재/형식 어긋남 시 신호 None (graceful). [[project_new_listings_collector_2026_06_07]].
    try:
        _nl_path = os.path.join(DATA_DIR, "new_listings.json")
        if os.path.exists(_nl_path):
            with open(_nl_path, encoding="utf-8") as _nlf:
                _nl_data = json.load(_nlf) or {}
            if isinstance(_nl_data, dict) and _nl_data.get("recent_3m_count") is not None:
                portfolio["new_listings"] = _nl_data
                print(f"  new_listings 주입: recent={_nl_data.get('recent_3m_count')} "
                      f"baseline={_nl_data.get('baseline_5y_count')} (막스 신규 딜 품질 source)")
    except Exception as _nl_e:  # noqa: BLE001
        print(f"  new_listings 주입 실패(무시): {_nl_e}")

    # 미장 sentiment/positioning 관측 주입 — market_horizon modest informational prior.
    # ⚠️ cycle_stage/verdict 가중 0 (사전등록 N≥50 전 → brain 불간섭). [[project_us_market_observations_2026_06_07]].
    try:
        from api.collectors.us_market_observations import latest_per_source
        _us = latest_per_source()
        if _us:
            portfolio["us_sentiment"] = _us
            print(f"  us_sentiment 주입: {list(_us.keys())} (market_horizon informational prior, 가중 0)")
    except Exception as _us_e:  # noqa: BLE001
        print(f"  us_sentiment 주입 실패(무시): {_us_e}")

    # ── 신호 필터 F2·F3 가드 평가 (PREREG_SIGNAL_FILTERS_2026_08_04) — 채점 전 부착 ──
    # graham_value 채점(verity_brain_analyze 내부)이 stock["value_guards"] 를 읽으므로 반드시
    # 이 앞. 결측·API 실패 = 비활성 (가드 미발동 — 채점 파이프 무영향). 공개 blob 은
    # sanitize STRIP_KEYS("value_guards") 로 제거 (동 커밋, 오퍼레이터 전용 진단).
    try:
        from api.intelligence.value_guards import evaluate_value_guards
        _vg_hits = []
        for stock in candidates:
            _g = evaluate_value_guards(stock)
            if _g is not None:
                stock["value_guards"] = _g
                if _g.get("cycle_peak_guard") or _g.get("earnings_quality"):
                    _vg_hits.append(f"{stock.get('ticker')}"
                                    f"({'F2' if _g.get('cycle_peak_guard') else 'F3'})")
        print(f"  [value_guards] 발동 {len(_vg_hits)}건" + (f" — {', '.join(_vg_hits[:8])}" if _vg_hits else ""))
    except Exception as _vg_e:  # noqa: BLE001
        print(f"  [value_guards] 스킵(채점 무영향): {type(_vg_e).__name__}: {_vg_e}")

    try:
        from api.intelligence.verity_brain import reset_ic_cache
        reset_ic_cache()
        brain_result = verity_brain_analyze(candidates, portfolio)
        portfolio["verity_brain"] = {
            "macro_override": brain_result.get("macro_override"),
            "market_brain": brain_result.get("market_brain"),
        }

        # MarketHorizon V0 — 시장 사이클/horizon 분포 산출
        try:
            from api.intelligence.market_horizon import compute_market_horizon
            portfolio["market_horizon"] = compute_market_horizon(portfolio)
        except Exception as _mh_err:  # noqa: BLE001
            print(f"  [WARN] market_horizon 산출 실패(무시): {_mh_err}")
            portfolio["market_horizon"] = {"_error": str(_mh_err)[:200]}

        # ATR Migration Summary — Phase 0 (5/16 verdict 까지) 운영 가시성
        try:
            from api.observability.atr_migration_summary import compute_atr_migration_summary
            portfolio["atr_migration"] = compute_atr_migration_summary()
        except Exception as _am_err:  # noqa: BLE001
            print(f"  [WARN] atr_migration summary 실패(무시): {_am_err}")
            portfolio["atr_migration"] = {"_error": str(_am_err)[:200]}
        brain_stocks = {r["ticker"]: r for r in (brain_result.get("stocks") or [])}
        for stock in candidates:
            br = brain_stocks.get(stock.get("ticker"), {})
            stock["verity_brain"] = {
                "brain_score": br.get("brain_score", 0),
                "validation": br.get("validation", {}),  # RULE7 가설/N 단일출처 라벨
                "grade": br.get("grade", "WATCH"),
                "grade_label": br.get("grade_label", "관망"),
                "grade_confidence": br.get("grade_confidence", "firm"),
                "data_coverage": br.get("data_coverage", 1.0),
                "fact_score": br.get("fact_score", {}),
                "sentiment_score": br.get("sentiment_score", {}),
                "vci": br.get("vci", {}),
                "vci_bonus": br.get("vci_bonus", 0),
                "candle_bonus": br.get("candle_bonus", 0),
                # 2026-06-17: brain_weights_cv 재계산 SoT 정합 — production raw 의 두 항 persist
                "gs_bonus": (stock.get("score_breakdown") or {}).get("gs_bonus", 0),
                "inst_13f_bonus": br.get("inst_13f_bonus", 0),
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

    # 옛 STEP 5.95 (post-brain Perplexity 스캔) = STEP 5.89 으로 이동 (2026-05-19).
    # 순서 결함 fix — brain 직전 attach 로 perplexity_risk_score 정상 작동.
    # docs/BRAIN_SCORE_AUDIT_20260518.md §9 B audit 참조.

    # 🚨 체크포인트 저장 (2026-08-15) — LLM 단계 진입 직전.
    #
    #   왜 여기인가: `full` 모드는 여기까지 `save_portfolio()` 가 **한 번도** 불리지 않았다.
    #   main() 안의 호출 지점 3곳이 전부 비켜 있다 — 1726 은 `if should_abort:` 조기중단 경로,
    #   2590 은 `if mode in ("realtime","realtime_us")` 전용, 4915 는 이 STEP 6 보다 뒤다.
    #   그래서 워치독이 Gemini 도중 SIGTERM 을 보내면 `_latest_portfolio_ref` 가 None 이라
    #   핸들러의 "partial portfolio 저장" 이 **항상 스킵**됐다(8/14·8/15 실패 run 2건 로그 실측:
    #   `_latest_portfolio_ref None — save 스킵 (early SIGTERM)`).
    #   결과 = 예산을 다 태우고 죽으면 유니버스 스캔(약 33분) + 병합(약 51분) + 채점까지
    #   **그때까지의 분석분이 통째로 사라졌다.** 꼬리만 잃는 게 아니었다.
    #
    #   여기서 한 번 저장하면 둘이 동시에 해결된다.
    #     ① 디스크에 채점 완료분이 남는다 — LLM 단계가 잘려도 앞의 결과는 보존
    #     ② `_latest_portfolio_ref` 가 세팅돼 SIGTERM 핸들러의 partial 저장이 실제로 작동
    #   되돌리지 말 것 — 이 저장을 빼면 위 두 안전장치가 같이 죽는다.
    #
    #   비용은 저장 1회(원자적 write)뿐이고 외부 호출·LLM 0 이다.
    try:
        save_portfolio(portfolio)
        print("  [checkpoint] LLM 단계 진입 전 저장 — 여기서 잘려도 채점분은 보존")
    except Exception as _cp_err:
        import sys as _cp_sys
        _cp_sys.stderr.write(f"[checkpoint] 저장 실패(무시하고 계속): {_cp_err}\n")

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
            # 🚨 2026-08-16 — 종목별 LLM 판정 기본 OFF (config.GEMINI_VERDICT_ENABLE).
            #   LLM 은 채점자가 아니라 판독자다. 판정은 Brain(문헌 4군)이 하고, LLM 예산은
            #   공시 원문 판독(dart_litigation·audit_signals·related_party)으로 간다.
            from api.config import GEMINI_VERDICT_ENABLE
            if not GEMINI_VERDICT_ENABLE:
                analyzed_subset = []
                print("  Gemini 종목판정 OFF — 공시 판독 경로로 이관 (GEMINI_VERDICT_ENABLE=1 로 복구)")
            else:
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
        from api.config import GEMINI_PRO_ENABLE, GEMINI_CRITICAL_TOP_N, GEMINI_VERDICT_ENABLE
        # Pro 재판단도 recommendation·ai_verdict 를 덮어쓰는 **판정**이라 같은 스위치를 받는다
        # (2026-08-16 — 판정은 Brain, LLM 은 판독). 종전엔 Flash 만 끄고 Pro 가 살아 판정을 계속 썼다.
        if GEMINI_PRO_ENABLE and GEMINI_VERDICT_ENABLE:
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
            # #1 피드백 메타 portfolio 에 기록 (UI/audit) + 콘솔 로그
            _fb_status = model_weights.get("_feedback", "unknown")
            portfolio["dual_model_weights"] = {
                "gemini": model_weights.get("gemini"),
                "claude": model_weights.get("claude"),
                "feedback_status": _fb_status,
                "gemini_n": model_weights.get("_gemini_n"),
                "claude_n": model_weights.get("_claude_n"),
                "gemini_hit": model_weights.get("_gemini_hit"),
                "claude_hit": model_weights.get("_claude_hit"),
                "delta_hit_rate": model_weights.get("_delta_hit_rate"),
                "cap_applied": model_weights.get("_cap_applied"),
                "min_samples_required": AI_LEADERBOARD_MIN_SAMPLES,
                "delta_cap": AI_WEIGHT_DELTA_CAP,
            }
            if _fb_status == "applied":
                print(f"  [#1 피드백] gemini={model_weights['gemini']} / claude={model_weights['claude']} "
                      f"(Δhit={model_weights.get('_delta_hit_rate'):+.1f}%p, cap={model_weights.get('_cap_applied')})")
            elif _fb_status == "insufficient_samples":
                print(f"  [#1 피드백] 샘플 부족 → base 유지 (gemini n={model_weights.get('_gemini_n')}, "
                      f"claude n={model_weights.get('_claude_n')}, min={AI_LEADERBOARD_MIN_SAMPLES})")
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
    # flag ON + 키 없음 조합을 조용히 지나치지 않도록 경고 (2026-04-25 preflight MAJ-4).
    if mode == "quick" and CLAUDE_IN_QUICK and not ANTHROPIC_API_KEY:
        print("  ⚠️ CLAUDE_IN_QUICK=1 인데 ANTHROPIC_API_KEY 미설정 — Claude 라이트 검증 스킵")
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
    # 🚨 2026-08-16 (PM 결정) — 오퍼레이터 리포트를 **보유 종목으로만** 좁힌다.
    #   근거: 시장 전체 서사는 PM 이 이 챗(verity-stock 29소스 조인)에서 훨씬 깊게 본다.
    #         리포트가 남을 이유는 "내가 들고 있는 것을 확인" 하는 용도뿐이다.
    #   범위: vams.holdings(보유) 에 있는 종목만 candidates 로 넘긴다. 보유 0이면 종전대로.
    #   🚨 알파네스트(공개)는 무변경 — daily_report 는 발행 시 STRIP_KEYS 로 제거된다
    #      (sanitize_portfolio_public.py:47). 공개 리포트는 daily_public_report 별도 경로.
    _held_tickers = {
        str(h.get("ticker") or "").split(".")[0]
        for h in ((portfolio.get("vams") or {}).get("holdings") or [])
        if isinstance(h, dict) and h.get("ticker")
    }
    if _held_tickers:
        _report_scope = [s for s in analyzed
                         if str(s.get("ticker") or "").split(".")[0] in _held_tickers]
        print(f"  리포트 범위 = 보유 {len(_report_scope)}/{len(_held_tickers)}종목 "
              f"(전체 후보 {len(analyzed)} 중)")
    else:
        _report_scope = analyzed
        print("  리포트 범위 = 보유 원장 부재 → 전체 후보 (종전 동작)")

    if effective_mode == "full":
        print("\n[6.5] AI 일일 시장 리포트 (KR)")
        try:
            daily_report = generate_daily_report(
                macro=macro,
                candidates=_report_scope,
                sectors=portfolio.get("sectors", []),
                headlines=portfolio.get("headlines", []),
                verity_brain=portfolio.get("verity_brain"),
                market="kr",
                market_summary=portfolio.get("market_summary"),
                event_insights=portfolio.get("event_insights"),
            )
            portfolio["daily_report"] = daily_report
            print(f"  KR 요약: {daily_report.get('market_summary', '?')[:60]}")
        except Exception as e:
            # 2026-05-18 — silent fail 보강 (trace 확보). "unhashable type: 'dict'" root cause 진단.
            import traceback as _tb
            print(f"  KR 리포트 스킵: {type(e).__name__}: {e}\n{_tb.format_exc()[:800]}")
            portfolio.setdefault("daily_report", {})

        print("\n[6.5b] AI 일일 시장 리포트 (US)")
        try:
            daily_report_us = generate_daily_report(
                macro=macro,
                candidates=_report_scope,
                sectors=portfolio.get("sectors", []),
                headlines=portfolio.get("headlines", []),
                verity_brain=portfolio.get("verity_brain"),
                market="us",
                market_summary=portfolio.get("market_summary"),
                event_insights=portfolio.get("event_insights"),
            )
            portfolio["daily_report_us"] = daily_report_us
            print(f"  US 요약: {daily_report_us.get('market_summary', '?')[:60]}")
        except Exception as e:
            # 2026-05-18 silent fail 보강
            import traceback as _tb
            print(f"  US 리포트 스킵: {type(e).__name__}: {e}\n{_tb.format_exc()[:800]}")
            portfolio.setdefault("daily_report_us", {})
    else:
        portfolio.setdefault("daily_report", {})
        portfolio.setdefault("daily_report_us", {})

    # ── 배지 단일 소유 게이트 (2026-08-03 PM 승인 — 표시 레이어, 산식 불변) ──
    # 반드시 모든 LLM override(claude_analyst→pro→light) 이후·저장 직전에 실행.
    # rec 배지 = verity_brain.grade 소유 + 강등 전용 게이트, LLM 합의는 analyst_view 보존.
    try:
        from api.intelligence.display_verdict import apply_display_verdict
        _gated = sum(1 for _s in analyzed if apply_display_verdict(_s).get("display_verdict", {}).get("gates"))
        print(f"  [display_verdict] {len(analyzed)}종목 배지 교정 · 게이트 발동 {_gated}건")
    except Exception as _dv_e:  # 표시 게이트 실패가 파이프라인을 중단시키면 안 됨
        print(f"  [display_verdict] 스킵: {type(_dv_e).__name__}: {_dv_e}")

    # ── 시스템 작용 패널 데이터 (2026-08-03 PM "/macro 1번 패널") ──
    # 매크로·게이트가 지금 시스템에 미치는 실작용 집계 — 표시 전용, 산식 불변.
    # 공개 blob 은 sanitize STRIP_KEYS("system_action") 로 제거 (오퍼레이터 전용).
    try:
        from api.intelligence.display_verdict import build_system_action
        portfolio["system_action"] = build_system_action(portfolio, analyzed)
        _sa = portfolio["system_action"]
        print(f"  [system_action] 방패={'ON' if _sa['rate_shield']['on'] else 'OFF'}"
              f" · BUY {_sa['verdict_gate']['buy_count']}"
              f" · aligned {len(_sa['verdict_gate']['aligned'])}"
              f" · 게이트 {_sa['verdict_gate']['gated_count']}건")
    except Exception as _sa_e:
        print(f"  [system_action] 스킵: {type(_sa_e).__name__}: {_sa_e}")

    # ── 사전등록 페이퍼 트랙 (PM 2026-08-04 "페이퍼 트랙 ㄱㄱ") ──
    # PREREG_AUTO_EXECUTION_GATE_2026_08_03 의 E·S·X 규칙을 가상 1,000만원으로 문자 그대로
    # 집행 — 실전 전략(aligned BUY 체계) 자체의 예비 trail 축적. VAMS 불간섭(별도 상태·장부).
    # 장부 = data/exec_paper_trail.jsonl (다음 step git add data/ broad = RULE 4 자동 포함).
    try:
        from api.execution.paper_track import run_paper_track
        portfolio["exec_paper"] = run_paper_track(analyzed, DATA_DIR)
        _ep = portfolio["exec_paper"]
        print(f"  [exec_paper] equity {_ep['equity']:,} · 진입 {_ep['entered_today']}"
              f" · pending {_ep['pending']} · flags {_ep['flags']}")
    except Exception as _ep_e:
        print(f"  [exec_paper] 스킵: {type(_ep_e).__name__}: {_ep_e}")

    # ── STEP 7: VAMS ──
    print(f"\n[7] VAMS 가상 투자")
    portfolio["recommendations"] = analyzed

    # ── 필드 커버리지 측정 (데이터 품질 = breadth × 정확성 × 신선도 × 커버리지) ──
    # 2026-06-03: silent 누수(6/3 80% AI_ANALYSIS_FAILED 등)를 측정값으로 전환.
    # trust_score(시스템 GO/NO-GO)와 직교 — 종목·필드 레벨. 모든 mode 에서 실행.
    try:
        from api.observability.field_coverage import (
            compute_field_coverage, log_field_coverage, summary_line)
        _fc = compute_field_coverage(analyzed)
        portfolio["field_coverage"] = _fc
        log_field_coverage(_fc)
        print(f"  [field_coverage] {summary_line(_fc)}")
    except Exception as _fc_err:
        print(f"  [field_coverage] 스킵: {_fc_err}")

    # rec_price 스냅샷 + current_price alias 주입 (preflight MIN-5 후속).
    # BacktestDashboard 가 'rec_price → current_price' 로 수익률을 시각화하려면
    # 추천 시점 가격이 고정 저장돼야 함. 기존 recommendations 에서 동일 ticker 의
    # rec_price 가 있으면 유지, 없으면 현재 price 로 초기화 (신규 추천).
    try:
        _prev_rec_price_map: dict = {}
        _prev_rec_file = os.path.join(DATA_DIR, "recommendations.json")
        if os.path.exists(_prev_rec_file):
            with open(_prev_rec_file, "r", encoding="utf-8") as _f:
                _prev_list = json.load(_f)
            if isinstance(_prev_list, list):
                for _prev in _prev_list:
                    _t = _prev.get("ticker")
                    _rp = _prev.get("rec_price")
                    if _t and _rp is not None:
                        _prev_rec_price_map[_t] = _rp
    except Exception:
        _prev_rec_price_map = {}

    for _rec in analyzed:
        _price = _rec.get("price")
        if _price is None:
            continue
        # 🚨 2026-08-20 — setdefault → 명시 대입. current_price 는 **live 가 의도**인데
        #   (tests/test_rec_price_snapshot.py:26,34 이 price 와 동일함을 assert)
        #   setdefault 는 값이 이미 있으면 no-op 이라 한번 굳으면 영영 안 풀렸다.
        #   scope=all 런은 반대 시장 레코드를 통째 이월하므로(4087~4097 `kept`)
        #   이월분의 current_price 가 그대로 따라와 no-op 이 영구화된다.
        #   이 줄이 있어야 다음 full run 에서 기존 오염분까지 자가 복구된다.
        _rec["current_price"] = _price
        # rec_price 는 setdefault 유지 — 추천 시점 진입가 고정이 **설계**다
        # (같은 테스트 35행 "유지됨 — 추천 시점 고정"). 절대 명시 대입으로 바꾸지 말 것.
        _rec.setdefault("rec_price", _prev_rec_price_map.get(_rec.get("ticker"), _price))

    # ── trade_plan v0_heuristic 산출 + 진입 후보 로깅 ──
    # 결정 룰은 단순(BB/MA/RSI), 자동 액션은 verdict 상태 전이만. 본인 운영 참고용.
    # 진입 후보(BUY 신규 + entry_active)는 trade_plan_v0_log.jsonl 에 풍부한 피처 스냅샷으로 append.
    try:
        from api.trade_planner import (
            build_trade_plan_v0,
            mark_case_closed,
            maybe_log_entry_candidate,
        )
        _prev_verdict_map = {
            r.get("ticker"): r.get("recommendation")
            for r in (_prev_list if isinstance(_prev_list, list) else [])
            if r.get("ticker")
        } if "_prev_list" in dir() else {}

        _tp_logged = 0
        _tp_closed = 0
        for _stock in analyzed:
            _judgment = {
                "recommendation": _stock.get("recommendation"),
                "multi_score": (_stock.get("multi_factor") or {}).get("multi_score", 50),
            }
            _plan = build_trade_plan_v0(_stock, _judgment)
            _stock["trade_plan"] = _plan

            _ticker = _stock.get("ticker")
            _prev_rec = _prev_verdict_map.get(_ticker)
            _curr_rec = _stock.get("recommendation")

            # BUY 가 아니게 되면 open 케이스 닫기
            if _prev_rec == "BUY" and _curr_rec != "BUY" and _ticker:
                _tp_closed += mark_case_closed(_ticker, reason=f"verdict_transition:{_prev_rec}->{_curr_rec}")

            # 진입 후보 발생 (entry_active=True + open 케이스 없음) 이면 append
            if maybe_log_entry_candidate(_stock, _judgment, _plan, prev_recommendation=_prev_rec):
                _tp_logged += 1

        if _tp_logged or _tp_closed:
            print(f"  [trade_plan] 진입 후보 로깅 {_tp_logged}건 · 케이스 종료 {_tp_closed}건")

        # 메타-검증: 누적 row 분해 통계 → portfolio["trade_plan_meta"] + jsonl persist
        try:
            from api.observability.trade_plan_meta_validation import summarize_and_attach
            _tp_meta = summarize_and_attach(portfolio)
            print(f"  [trade_plan_meta] status={_tp_meta.get('status')} · "
                  f"total={_tp_meta.get('sample_size', {}).get('total', 0)}")
        except Exception as _tp_meta_err:
            print(f"  [trade_plan_meta] 산출 스킵: {_tp_meta_err}")

        # Brain 자체 진화 신호: hit rate / IC / drift / 피처 단조성 점검 → 룰 재검토 후보
        try:
            from api.intelligence.trade_plan_evolution import attach_to_portfolio as _tp_evo_attach
            _tp_evo = _tp_evo_attach(portfolio)
            _summary = _tp_evo.get("summary") or {}
            print(f"  [trade_plan_evolution] status={_tp_evo.get('status')} · "
                  f"crit={_summary.get('critical', 0)} warn={_summary.get('warning', 0)}")
        except Exception as _tp_evo_err:
            print(f"  [trade_plan_evolution] 산출 스킵: {_tp_evo_err}")

        # brain_weights cross-validation (full mode 만 — 무거운 snapshot 다중 로드)
        if effective_mode == "full":
            try:
                from api.intelligence.brain_weights_cv import attach_to_portfolio as _bw_cv_attach
                _bw_cv = _bw_cv_attach(portfolio)
                _bw_status = _bw_cv.get("status")
                if _bw_status == "active":
                    _best_r = _bw_cv.get("best_by_return", {})
                    _best_h = _bw_cv.get("best_by_hit_rate", {})
                    print(f"  [brain_weights_cv] best_return: w_fact={_best_r.get('w_fact')} "
                          f"({_best_r.get('avg_return')}%) · best_hit: w_fact={_best_h.get('w_fact')} "
                          f"({_best_h.get('hit_rate')}%)")
                else:
                    print(f"  [brain_weights_cv] status={_bw_status}")
            except Exception as _bw_err:
                print(f"  [brain_weights_cv] 산출 스킵: {_bw_err}")
    except Exception as _tp_err:
        print(f"  [trade_plan] 산출/로깅 스킵: {_tp_err}")

    def _gate_pass(s):
        """게이트 컷오버 (2026-08-12, PR #357 채택 B): 정본 = safety_pct ≥ GATE_BOTTOM_PCT.
        🚨 전환 폴백 — safety_pct 미부착(구 아티팩트/보유 주입)이면 구 게이트(≥55)로.
        조용한 빈 픽 방지. 폴백 사용은 measurement_audit 가 감시한다."""
        from api.config import GATE_BOTTOM_PCT
        pct = s.get("safety_pct")
        if pct is not None:
            return pct >= GATE_BOTTOM_PCT
        return s.get("safety_score", 0) >= 55          # 폴백 (min_safety 55 섀도)

    def _profile_picks(stocks, profile):
        return [
            {"ticker": s["ticker"], "name": s["name"], "price": s.get("price"),
             "safety_score": s.get("safety_score", 0),
             "safety_pct": s.get("safety_pct"),
             "recommendation": s.get("recommendation"),
             "ai_verdict": s.get("ai_verdict", ""),
             "detected_risk_keywords": s.get("detected_risk_keywords", [])}
            for s in stocks
            if s.get("recommendation") in profile["recommendations"]
            and _gate_pass(s)
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

    # ── 배당 DB 최신화 (KR) — VAMS 사이클 내부의 ex_date 당일 누적 훅이 참조할 소스 ──
    # · 부트스트랩: DB에 실제 배당 레코드 없는 보유 종목은 즉시 Tier 1 sweep
    # · 1/15, 7/15:  보유 종목 연간 계획 전수 sweep (사업보고서 갱신 주기)
    # · 매 월요일:   Tier 2 poll(최근 공시) + Tier 3 reconcile(announced→confirmed 승격)
    try:
        from api.collectors.dividend_kr import (
            sweep_annual_plans,
            poll_recent_decisions,
            reconcile_confirmed,
            load_dividends_db,
        )
        hold_tickers_kr = [
            h["ticker"] for h in portfolio.get("vams", {}).get("holdings", [])
            if h.get("currency", "KRW") == "KRW" and h.get("ticker")
        ]
        if hold_tickers_kr:
            today_kst = now_kst()
            div_db = load_dividends_db()
            missing = [
                t for t in hold_tickers_kr
                if not any(not r.get("_meta") for r in div_db.get(t, []))
            ]
            if missing:
                with tracer.step("dividend_bootstrap"):
                    r = sweep_annual_plans(missing)
                    ok = sum(1 for v in r.values() if v in ("insert", "update"))
                    print(f"  [배당/bootstrap] {len(missing)}종목 → {ok} OK / {len(r) - ok} miss")
            if today_kst.day == 15 and today_kst.month in (1, 7):
                with tracer.step("dividend_sweep_annual"):
                    r = sweep_annual_plans(hold_tickers_kr)
                    ok = sum(1 for v in r.values() if v in ("insert", "update"))
                    print(f"  [배당/sweep] 정기 {today_kst.month}/15 · {len(hold_tickers_kr)}종목 → {ok} 갱신")
            if today_kst.weekday() == 0:
                with tracer.step("dividend_poll_weekly"):
                    hits = poll_recent_decisions(hold_tickers_kr, days_back=14)
                    if hits:
                        print(f"  [배당/poll] 최근 배당결정 공시 감지: {len(hits)}종목")
                with tracer.step("dividend_reconcile_weekly"):
                    rc = reconcile_confirmed(hold_tickers_kr)
                    if rc:
                        print(f"  [배당/reconcile] {len(rc)}종목 재검증")
    except Exception as e:
        print(f"  [배당] 스킵 (무시): {e}")

    # ── 배당 DB 최신화 (US) — yfinance Ticker.dividends 기반 ──
    # · 부트스트랩: DB에 실제 배당 레코드 없는 US 보유 종목은 즉시 fetch
    # · 매 월요일: 보유 US 종목 전수 sweep (yfinance free, rate limit 없음)
    # · KR 패턴 정합 (api/main.py:3829~). 현재 US 매수 0건 = no-op.
    try:
        from api.collectors.dividend_us import (
            update_dividends_for_tickers as _update_us_div,
            load_dividends_db as _load_us_div_db,
        )
        hold_tickers_us = [
            h["ticker"] for h in portfolio.get("vams", {}).get("holdings", [])
            if (h.get("asset_class") in ("US_STOCK", "US_ETF") or h.get("currency", "").upper() == "USD")
            and h.get("ticker")
        ]
        if hold_tickers_us:
            today_kst = now_kst()
            us_div_db = _load_us_div_db()
            missing_us = [
                t for t in hold_tickers_us
                if not any(not r.get("_meta") for r in us_div_db.get(t, []))
            ]
            if missing_us:
                with tracer.step("dividend_us_bootstrap"):
                    r = _update_us_div(missing_us, lookback_years=2)
                    ok = sum(1 for v in r.values() if "insert" in v or "update" in v)
                    print(f"  [배당US/bootstrap] {len(missing_us)}종목 → {ok} OK / {len(r) - ok} miss")
            if today_kst.weekday() == 0:
                with tracer.step("dividend_us_sweep_weekly"):
                    r = _update_us_div(hold_tickers_us, lookback_years=2)
                    ok = sum(1 for v in r.values() if "insert" in v or "update" in v)
                    print(f"  [배당US/sweep] 정기 월요일 · {len(hold_tickers_us)}종목 → {ok} 갱신")
    except Exception as e:
        print(f"  [배당US] 스킵 (무시): {e}")

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
    try:
        portfolio["geopolitical_hotspots"] = build_geopolitical_hotspots(
            portfolio.get("recommendations", []),
            portfolio.get("vams", {}).get("holdings", []),
        )
        gh = portfolio["geopolitical_hotspots"]
        if gh.get("covered_companies"):
            print(
                f"  지정학 집계: {gh['covered_companies']}종목 "
                f"(중국 고노출 {len(gh['china_high_exposure'])}, "
                f"제재지역 노출 {len(gh['sanctioned_exposure'])})"
            )
    except Exception as e:
        print(f"  지정학 집계 스킵: {e}")

    try:
        briefing = generate_briefing(portfolio)
    except Exception as _bf_err:
        print(f"  비서 생성 실패(폴백): {_bf_err}")
        briefing = {
            "headline": "브리핑 생성 실패",
            "alerts": [],
            "alert_counts": {"critical": 0, "warning": 0, "info": 0},
            "action_items": [],
        }
    portfolio["briefing"] = briefing
    portfolio["alerts"] = briefing.get("alerts", [])
    print(f"  비서: {briefing.get('headline', '?')}")
    _ac = briefing.get("alert_counts", {})
    print(f"  알림: CRITICAL {_ac.get('critical', 0)} | WARNING {_ac.get('warning', 0)} | INFO {_ac.get('info', 0)}")
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
    # 2026-05-11 fix: 실 Gemini stock 호출 수 = min(candidates, GEMINI_BATCH_MAX_STOCKS).
    # 이전엔 len(candidates) 그대로 적재 = 3x over-estimate (60 vs 실 20).
    from api.config import GEMINI_BATCH_MAX_STOCKS as _GEMINI_MAX
    _gemini_actual_calls = min(len(candidates), _GEMINI_MAX) if effective_mode == "full" else 0
    run_stats = {
        "gemini_stock_calls": _gemini_actual_calls,
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
            path = archive_daily_snapshot(portfolio, mode=mode)
            cleanup_old_snapshots()
            print(f"  저장: {path} (+ runs/ 감사 로그)")
        except Exception as e:
            print(f"  아카이빙 스킵: {e}")

        # ── STEP 9.51: Brain 슬림 스냅샷 90일 보존 + 3일 후 수익률 백필 ──
        # red_flag_penalty / overrides precision 누적 검증용
        print(f"\n[9.51] Brain 90일 스냅샷 + 3일 후 수익률 백필")
        try:
            brain_path = save_brain_snapshot(portfolio)
            filled, total = backfill_actual_returns(portfolio)
            removed = cleanup_old_brain_snapshots()
            if brain_path:
                print(f"  저장: {brain_path}")
            if total:
                print(f"  3일전 백필: {filled}/{total} 종목")
            if removed:
                print(f"  90일 초과 {removed}개 폴더 정리")
        except Exception as e:
            print(f"  Brain 스냅샷 스킵: {e}")

        # ── STEP 9.52: 결정-trail 무결성 감사 (손실/gap/품질 단일 검증) ──
        # 2026-06-13 신설: 검증 게이트 입력이 되는 결정시점 기록이 손실 없이·끊김 없이
        # 축적되는지 매 실행 검증. 산식 무관 read-only. 결과 = portfolio 노출 + jsonl 적재.
        print(f"\n[9.52] 결정-trail 무결성 감사")
        try:
            from api.observability.trail_integrity import run_and_log
            _ti = run_and_log()
            portfolio["trail_integrity"] = _ti
            _h = _ti.get("history", {})
            print(f"  {_ti.get('severity')} | history {_h.get('snapshot_count')}일 "
                  f"gap {len(_h.get('business_day_gaps') or [])} | "
                  f"필드 {_h.get('latest_rec_field_count')}")
            for _fnd in (_ti.get("findings") or [])[:3]:
                print(f"    - {_fnd}")
        except Exception as e:
            print(f"  trail 무결성 감사 스킵: {e}")

        # ── STEP 9.53: 200MA 추세 게이트 (A1 SHADOW 꼬리리스크 오버레이) ──
        # 2026-06-15 신설: 지수 200일선 게이트. SHADOW(실 포트 무영향, brain-input 0).
        # full 모드만(지수 1회 fetch). target 지수 KOSPI/S&P 둘 다 로깅 = PM N후 선택.
        if effective_mode == "full":
            print(f"\n[9.53] 200MA 추세 게이트 (A1 SHADOW)")
            try:
                from api.intelligence.trend_overlay import run_shadow as _trend_shadow
                _to = _trend_shadow()
                portfolio["trend_overlay"] = _to
                for _k, _v in (_to.get("indices") or {}).items():
                    if _v.get("status") == "ok":
                        print(f"  {_k}: {_v['gate']} (close {_v['close']} vs sma200 {_v['sma200']}, "
                              f"gap {_v['gap_pct']:+.1f}%)")
            except Exception as e:
                print(f"  추세 게이트 스킵(무영향): {e}")

        # ── STEP 9.54: DART 공시 중요도 게이팅 관측 (C1 SHADOW) ──
        # 2026-06-15 신설: 기존 catalyst severity(중요도) 재사용 + 가격/forward 조인 관측.
        # SHADOW(brain-input 0, 임계 미설정). 부호 확인이 1차 목적(검증상 역알파 가능).
        if effective_mode == "full":
            print(f"\n[9.54] DART 공시 중요도 게이팅 관측 (C1 SHADOW)")
            try:
                from api.intelligence.dart_importance_observer import run_shadow as _dart_obs
                _do = _dart_obs()
                portfolio["dart_importance_obs"] = _do
                print(f"  신규 관측 {_do.get('new_observations')} / severity 분포 {_do.get('severity_dist')}")
            except Exception as e:
                print(f"  공시 중요도 관측 스킵(무영향): {e}")

    # ── STEP 9.55: 추천 성과 백테스트 (PDF 보다 먼저 — 학습 트랙용) ──
    # 2026-05-03 정정: 기존엔 PDF→백테스트 순서였는데, daily_public.py 의
    # _log_brain_learning_safe 가 portfolio.backtest_stats 를 읽어 학습 트랙에
    # 적재함. PDF→백테스트 순서면 모든 entry 의 hit_rate 가 null 이 되어 학습
    # 루프 단절. 백테스트→PDF 로 swap (PDF 본문은 backtest_stats 미참조라 안전).
    if effective_mode == "full":
        print(f"\n[9.55] 추천 성과 백테스트")
        try:
            bt_stats = evaluate_past_recommendations()
            portfolio["backtest_stats"] = bt_stats
            for period, info in bt_stats.get("periods", {}).items():
                if info.get("hit_rate") is not None:
                    print(f"  {period}: 적중률 {info['hit_rate']}% | 평균수익 {info['avg_return']}% | {info['total_recs']}종목")
        except Exception as e:
            print(f"  백테스트 스킵: {e}")

    # ── STEP 9.57: report findings 추출 → Brain 학습 트랙 ──
    # 리포트의 #1 목적 = Brain 의 지속 학습 input. PDF 만 만들고 끝나면 정체.
    # backtest_stats 가 채워진 직후 (위 9.55) 에 호출해야 hit_rate 까지 포함.
    if effective_mode == "full":
        print(f"\n[9.57] 리포트 findings 추출 (Brain 학습 input)")
        try:
            from api.metadata import report_findings
            entry = report_findings.log(portfolio, report_type="daily")
            if entry:
                f = entry.get("findings") or {}
                buys = len(f.get("top_buy_picks") or [])
                hr14 = f.get("backtest_hit_rate_14d")
                print(f"  daily: top_buy={buys}건 hit14d={hr14} → report_findings.jsonl")
        except Exception as e:
            print(f"  findings 추출 스킵: {e}")

    # ── STEP 9.6: PDF 리포트 생성 (full) ──
    if effective_mode == "full":
        print(f"\n[9.6] PDF 리포트 생성")
        try:
            pdf_paths = generate_all_reports(portfolio)
            print(f"  PDF {len(pdf_paths)}건 생성 완료")
        except Exception as e:
            print(f"  PDF 생성 스킵: {e}")

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

            # 2026-05-24 wire / 2026-06-03 정정: ledger 적재·관측 only.
            # postmortem.misleading_factors → EWMA factor weight learning + ledger 적재.
            # ⚠ quarantine 결과는 brain 점수에 자동 반영 안 함 (N 부족 — factor_decay 5/23 동결과
            # 일관, RULE 7 곡선맞추기 방지). 적용 활성화 = 사전 검정력 관문 승인 + PM 재승인.
            try:
                from api.intelligence.postmortem_auto_evolve import evaluate_and_persist
                _ae = evaluate_and_persist(portfolio)
                portfolio["postmortem_auto_evolve"] = _ae
                _q = _ae.get("quarantined_factors") or []
                print(f"  auto_evolve: ewma {len(_ae.get('ewma_state_new') or {})} factors, "
                      f"quarantine {len(_q)}")
            except Exception as _ae_err:
                print(f"  auto_evolve 스킵: {_ae_err}")
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
            # 63/126 = fundamental(밸류/퀄리티/안전/컨센서스) 분기 horizon forward IC 로깅.
            # 7일 일간 IC 는 분기 reporting-lag 자기상관 노이즈 (Perplexity NQ1, 3a6c4f92).
            # 장기윈도는 exact_horizon — history 부족 단계엔 자동 미저장(라벨오염 0).
            mw_result = scan_all_factors_multi_window([7, 14, 30, 63, 126])
            ic_scan = (mw_result.get("windows", {}).get("7")
                       or mw_result.get("windows", {}).get("14")
                       or {})
            if ic_scan.get("status") == "ok":
                monthly = compute_monthly_rollup(30)
                portfolio["factor_ic"] = {
                    "ranking": ic_scan.get("ranking", [])[:10],
                    "significant_factors": ic_scan.get("significant_factors", []),
                    "decaying_factors": ic_scan.get("decaying_factors", []),
                    # 🚨 2026-08-15 PM 승인 — "유의" 표현 철회 + 겹침 보정 병기.
                    #    is_significant 는 표본 수 항이 없는 고정 임계다. 소비처가 그 사실과
                    #    독립 관측 수를 같은 자리에서 보이게 한다 (admin PDF 9-2 / 3-3).
                    "significant_label": ic_scan.get("significant_label"),
                    "significant_criterion": ic_scan.get("significant_criterion"),
                    "nonoverlap_pass_factors": ic_scan.get("nonoverlap_pass_factors", []),
                    "unestimable_factors": ic_scan.get("unestimable_factors", []),
                    "overlap_note": ic_scan.get("overlap_note"),
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
                # 2026-05-11: token counter 적재 (morning_strategy 도 cost monitor 반영)
                _morning_in = int(morning.get("_input_tokens") or 0)
                _morning_out = int(morning.get("_output_tokens") or 0)
                if _morning_in or _morning_out:
                    claude_tokens_used += _morning_in + _morning_out
                    claude_light_calls += 1  # morning 도 light 카운트로 합산 (별도 카운터 신설 X)
                    print(f"  [cost] morning tokens: in={_morning_in} out={_morning_out}")
            else:
                # 재생성 실패 — load_portfolio() carry-forward 로 들어온 옛 blob 을 반드시 제거.
                # 안 그러면 stale 환각 blob 이 portfolio.json/history 에 재저장되고 매 아침
                # 재전송됨 (2026-06-05 삼성 65,000원 환각 3차 surface 의 근본 원인).
                portfolio.pop("claude_morning_strategy", None)
                print(f"  Claude 모닝 전략 생성 실패 (API 오류) — stale carry-forward blob 제거")
        except Exception as e:
            portfolio.pop("claude_morning_strategy", None)
            print(f"  모닝 전략 스킵: {e} — stale carry-forward blob 제거")
    elif portfolio.get("claude_morning_strategy"):
        # 기능 비활성(CLAUDE_MORNING_STRATEGY=0 default — production) 인데 load_portfolio()
        # carry-forward 로 옛 blob 이 남아 있으면 제거. 안 그러면 fossil 환각 blob 이
        # portfolio.json/history 에 영구 carry-forward (2026-06-05: production 플래그 off
        # 상태에서 6/3 이전 fossil 이 매 아침 송출되던 사고의 잔존 경로 차단).
        portfolio.pop("claude_morning_strategy", None)
        print(f"\n[10.7] Claude 모닝 전략 비활성 — carry-forward fossil blob 제거")

    # ── STEP 10.75: Claude 종합 검수 신선도 가드 (2026-06-07) ──
    # claude_final_review 는 full 모드(10.8)에서만 생성되나 recommendations 는 light cycle 에서도
    # 갱신됨 → load_portfolio carry-forward 로 낡은 검수가 잔존해 REVIEW_REQUIRED stale 표시 사고(6/7,
    # market_horizon 미산출/CSCO 등 현재와 불일치 concern). claude_morning_strategy fossil 가드(10.7)
    # 와 동형 — recs 시그니처 불일치/미표기 시 제거(다음 full 실행에서 재생성).
    def _cfr_recs_sig(pf):
        recs = pf.get("recommendations") or []
        return "|".join(sorted(
            f"{r.get('ticker')}:{r.get('grade') or r.get('recommendation') or ''}" for r in recs
        ))
    _cur_sig = _cfr_recs_sig(portfolio)
    _cfr_existing = portfolio.get("claude_final_review")
    if isinstance(_cfr_existing, dict):
        _old_sig = _cfr_existing.get("_recs_sig")
        if (not _old_sig) or (_old_sig != _cur_sig):
            portfolio.pop("claude_final_review", None)
            print("\n[10.75] Claude 검수 신선도 가드 — recs 스냅샷 불일치/미표기 → 낡은 검수 제거")

    # ── STEP 10.8: Claude 종합 검수 (full 모드, 1회/일) ──
    # 2026-05-11 추가. project_claude_budget_guard 정합 (~$2.81/월).
    # portfolio 핵심 (brain top 10 / macro / horizon / VAMS / tail_risk) 종합 → Claude
    # 가 합리성·일관성 검수. claude_final_verdict 산출 (PROCEED/CAUTION/REVIEW_REQUIRED).
    if effective_mode == "full" and ANTHROPIC_API_KEY:
        print(f"\n[10.8] Claude 종합 검수")
        try:
            from api.analyzers.claude_analyst import final_portfolio_review
            review = final_portfolio_review(portfolio)
            if review:
                portfolio["claude_final_review"] = review
                review["_recs_sig"] = _cur_sig  # 신선도 가드 (10.75) — 다음 빌드 stale 판별
                verdict = review.get("claude_final_verdict", "?")
                score = review.get("review_score", "?")
                concerns = review.get("concerns", [])
                print(f"  검수 verdict: {verdict} (score {score})")
                if concerns:
                    print(f"  우려사항: {concerns[0][:80]}")
                # cost counter 적재
                _r_in = int(review.get("_input_tokens") or 0)
                _r_out = int(review.get("_output_tokens") or 0)
                if _r_in or _r_out:
                    claude_tokens_used += _r_in + _r_out
                    claude_light_calls += 1
                    print(f"  [cost] final_review tokens: in={_r_in} out={_r_out}")
            else:
                # 2026-05-18 — silent fail 보강. review = None / 빈 dict = API fail root cause 진단 불가.
                # final_portfolio_review 가 None 반환 path stderr 명시.
                import sys as _sys
                _sys.stderr.write(
                    "[claude_final_review] None or empty review — API 호출 결과 빈. "
                    "ANTHROPIC_API_KEY env / model availability / rate limit 의심.\n"
                )
                print(f"  Claude 종합 검수 실패 (API 오류, stderr 참조)")
        except Exception as e:
            # 2026-05-18 silent fail 보강 (traceback)
            import traceback as _tb
            print(f"  종합 검수 스킵: {type(e).__name__}: {e}\n{_tb.format_exc()[:600]}")

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
            # ── 매월 1일: 월간 검증 리포트 (VAMS validation_report + adjusted_performance) ──
            if now.day == 1 and now.weekday() < 5:
                try:
                    from api.notifications.monthly_validation_report import send_monthly_report
                    send_monthly_report(portfolio)
                    print(f"  [12.1] 월간 검증 리포트 전송됨")
                except Exception as e:
                    print(f"  [12.1] 월간 검증 리포트 스킵: {e}")
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

    # ── Brain 진화 이력 attach (전 모드 — git log 분석, 가벼움) ──
    try:
        from api.intelligence.brain_evolution import attach_to_portfolio as _attach_evo
        _attach_evo(portfolio, max_count=30)
        _evo_n = len(portfolio.get("brain_evolution_log") or [])
        print(f"  🧬 Brain 진화 이력: {_evo_n}건")
    except Exception as _evo_err:
        print(f"  ⚠️ brain_evolution attach 스킵: {_evo_err}")

    # ── Lynch 6분류 (한국 기준) attach (전 모드, 가벼움) ──
    try:
        from api.intelligence.lynch_classifier import attach_classifications as _attach_lynch
        _attach_lynch(portfolio)
        _dist = portfolio.get("lynch_kr_distribution", {}).get("counts") or {}
        if _dist:
            _summary = " / ".join(f"{k.split('_')[0][:5]}={v}" for k, v in _dist.items() if v > 0)
            print(f"  📚 Lynch 분류: {_summary}")
    except Exception as _lyn_err:
        print(f"  ⚠️ lynch_classifier 스킵: {_lyn_err}")

    # ── Sprint 11 결함 7 — 오늘의 액션 3개 (BUY/SELL/WATCH) attach (전 모드) ──
    try:
        from api.intelligence.daily_actions import attach_to_portfolio as _attach_actions
        _attach_actions(portfolio)
        _da = portfolio.get("daily_actions") or {}
        _b, _s, _w = _da.get("buy"), _da.get("sell"), _da.get("watch")
        print(f"  🎯 오늘의 액션: "
              f"BUY={_b['ticker'] if _b else '-'} / "
              f"SELL={_s['ticker'] if _s else '-'} / "
              f"WATCH={_w['ticker'] if _w else '-'}")
    except Exception as _da_err:
        print(f"  ⚠️ daily_actions 스킵: {_da_err}")

    # ── 첫 화면(TodayActionsCard) 보조 필드 attach: portfolio_summary/decision_queue/validation/evolution ──
    try:
        from api.intelligence.dashboard_summary import attach_to_portfolio as _attach_summary
        _attach_summary(portfolio)
        _ps = portfolio.get("portfolio_summary") or {}
        _dq = portfolio.get("decision_queue") or []
        _vd = portfolio.get("validation") or {}
        _ev = portfolio.get("evolution") or {}
        print(f"  📊 dashboard summary: cum={_ps.get('cumulative_pct')}%, "
              f"queue={len(_dq) if isinstance(_dq, list) else '-'}, "
              f"validation={_vd.get('cumulative_days')}d, "
              f"evolution={_ev.get('label')}")
    except Exception as _ds_err:
        print(f"  ⚠️ dashboard_summary 스킵: {_ds_err}")

    # ── 어태치 결과 즉시 저장 (모든 모드) ──
    # 주의: full/full_us 는 아래 Observatory 에서 다시 save_portfolio 호출.
    # quick/realtime 은 여기서만 attach 결과가 디스크 반영됨.
    if mode not in ("full", "full_us"):
        save_portfolio(portfolio)

    # ── Brain Observatory: 4개 측정 모듈 + jsonl 누적 (Phase 1~2) ──
    # full/full_us 모드에서만 누적. quick/realtime 은 잡음 (분단위 호출).
    if mode in ("full", "full_us"):
        try:
            from api.observability import run_full_observability
            obs = run_full_observability(portfolio, save_jsonl=True,
                                        attach_to_portfolio=True)
            trust = obs.get("trust") or {}
            health_meta = (obs.get("data_health") or {}).get("_meta") or {}
            drift = obs.get("drift") or {}
            print(f"  🧠 Observatory: trust={trust.get('verdict')} "
                  f"({trust.get('satisfied')}/{trust.get('total')}), "
                  f"health={health_meta.get('overall_status')}, "
                  f"drift={drift.get('level')} ({drift.get('overall_drift_score', 0)})")
            # Vercel API 가 portfolio.observability 를 읽도록 재저장
            save_portfolio(portfolio)
        except Exception as e:
            print(f"  ⚠️ Observatory 측정 스킵: {e}")

    # ── 실행 추적 아카이브 저장 ──
    tracer.log("cost_monitor", portfolio.get("cost_monitor", {}))
    trace_path = tracer.end()
    if trace_path:
        print(f"  📦 실행 추적: {trace_path}")

    # ── KB 인용 통계 flush (2026-04-25, 책 충돌 분석용) ──
    try:
        from api.analyzers.gemini_analyst import flush_kb_usage_to_file
        flushed = flush_kb_usage_to_file()
        if flushed:
            print(f"  📚 KB 인용 통계: {flushed}건 → data/brain_kb_usage.json")
    except Exception as e:
        print(f"  ⚠️ KB usage flush 스킵: {e}")

    # DART drain (post-pipeline) — STEP 5.7/5.78/5.88 누적 (project_dart_drain_gap_2026_05_25, 옵션 i)
    try:
        import os as _os
        from api.analyzers.stock_filter import _log_w1_runtime
        _stage = int(_os.environ.get("UNIVERSE_RAMP_UP_STAGE", "0") or "0")
        _log_w1_runtime(
            stage=_stage,
            elapsed=0.0,
            market_scope="post_main_dart_drain",
            metrics={},
        )
    except Exception as e:
        print(f"  ⚠️ DART post-drain 스킵: {e}")


if __name__ == "__main__":
    main()
