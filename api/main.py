"""
VERITY — AI 주식 분석 엔진 v8.0 (Sprint 8: 24h×15min)

24시간 15분 주기, 시각 기반 3단계 자동 모드:
  realtime (KST 9-15):     가격/환율/지수/수급/뉴스/X감성 (~1분)
  full (KST 15:30-16):     + Gemini AI/재무분석/백테스트/텔레그램 (~7분)
  quick (그 외 장외):      + 기술적분석/멀티팩터/XGBoost (~3분)
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
)
from api.collectors.stock_data import get_market_index
from api.collectors.macro_data import get_macro_indicators
from api.collectors.news_sentiment import get_stock_sentiment
from api.collectors.market_flow import get_investor_flow
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
from api.analyzers.gemini_analyst import analyze_batch, generate_daily_report
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
from api.collectors.news_headlines import collect_headlines
from api.collectors.sector_analysis import get_sector_rankings
from api.collectors.earnings_calendar import collect_earnings_for_stocks
from api.collectors.global_events import collect_global_events
from api.collectors.x_sentiment import collect_x_sentiment
from api.collectors.CommodityScout import (
    attach_commodity_to_stocks,
    apply_commodity_adjustment_to_fundamental,
    run_commodity_scout,
)
from api.analyzers.commodity_narrator import enrich_commodity_impact_narratives
from api.analyzers.claude_analyst import analyze_batch_deep, merge_dual_analysis
from api.intelligence.alert_engine import generate_alerts, generate_briefing
from api.intelligence.verity_brain import analyze_all as verity_brain_analyze
from api.intelligence.periodic_report import generate_periodic_analysis
from api.workflows.archiver import archive_daily_snapshot, cleanup_old_snapshots
from api.analyzers.gemini_analyst import generate_periodic_report
from api.notifications.telegram import send_alerts, send_daily_report
from api.notifications.telegram_bot import run_poll_once
from api.health import run_health_check, VERSION


def build_price_map(portfolio: dict) -> dict:
    """보유 종목의 현재가 맵 구성 (yfinance)"""
    import yfinance as yf
    price_map = {}
    for holding in portfolio["vams"]["holdings"]:
        ticker = holding["ticker"]
        ticker_yf = holding.get("ticker_yf", f"{ticker}.KS")
        try:
            t = yf.Ticker(ticker_yf)
            hist = t.history(period="1d")
            if not hist.empty:
                price_map[ticker] = float(hist["Close"].iloc[-1])
        except Exception:
            pass
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

        # 뉴스 감성
        sentiment = get_stock_sentiment(name)
        stock["sentiment"] = sentiment
        print(f"      뉴스: {sentiment['score']}점 | 긍정 {sentiment['positive']} / 부정 {sentiment['negative']} ({sentiment['headline_count']}건)")

        # 수급 (외국인/기관)
        flow = get_investor_flow(ticker)
        stock["flow"] = flow
        print(f"      수급: {flow['flow_score']}점 | {', '.join(flow['flow_signals'][:2]) or '중립'}")

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
        )
        stock["multi_factor"] = mf
        cs_note = f"컨센서스 {cblock.get('consensus_score', 50)}점 ({cblock.get('score_source', '?')})"
        print(f"      종합: {mf['multi_score']}점 ({mf['grade']}) | {cs_note} | 시그널: {', '.join(mf['all_signals'][:3]) or '없음'}")

    return candidates


def get_analysis_mode() -> str:
    """
    24시간 15분 주기 — 시각 기반 모드 자동 결정
    - realtime (KST 9:00~15:29):  가격/환율/지수/수급/뉴스 (~1분)
    - full (KST 15:30~16:14):     + Gemini/재무/백테스트/텔레그램 (~7분)
    - quick (그 외 전체):         + 기술적/멀티팩터/XGBoost (~3분)
    - periodic_weekly / periodic_monthly / periodic_quarterly: 정기 리포트 전용
    """
    mode = os.environ.get("ANALYSIS_MODE", "").lower()
    if mode in ("full", "quick", "realtime",
                "periodic_weekly", "periodic_monthly", "periodic_quarterly"):
        return mode
    now = now_kst()
    hour, minute = now.hour, now.minute
    if (hour == 15 and minute >= 30) or hour == 16:
        return "full"
    if 9 <= hour <= 15:
        return "realtime"
    return "quick"


def _run_periodic_report(period: str):
    """정기 리포트 생성 파이프라인 (주간/월간/분기)."""
    period_map = {
        "periodic_weekly": "weekly",
        "periodic_monthly": "monthly",
        "periodic_quarterly": "quarterly",
    }
    p = period_map.get(period, "weekly")
    label = {"weekly": "주간", "monthly": "월간", "quarterly": "분기"}.get(p, p)

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

    portfolio_path = os.path.join(DATA_DIR, "portfolio.json")
    if os.path.exists(portfolio_path):
        with open(portfolio_path, "r", encoding="utf-8") as f:
            txt = f.read().replace("NaN", "null")
            portfolio = json.loads(txt)
    else:
        portfolio = {}

    report_key = f"{p}_report"
    portfolio[report_key] = report
    portfolio[f"{report_key}_updated"] = now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00")

    with open(portfolio_path, "w", encoding="utf-8") as f:
        json.dump(portfolio, f, ensure_ascii=False, indent=2, default=str)

    print(f"\n✅ {label} 정기 리포트 생성 완료 → portfolio.json['{report_key}']")


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


def main():
    mode = get_analysis_mode()

    if mode.startswith("periodic_"):
        _run_periodic_report(mode)
        return

    MODE_LABELS = {
        "realtime": "실시간 갱신 (가격/환율/수급)",
        "quick": "빠른 분석 (기술적/멀티팩터/예측)",
        "full": "전체 분석 (Gemini/백테스트/텔레그램)",
    }

    print("=" * 60)
    print(f"  VERITY — AI 주식 분석 엔진 {VERSION}")
    print(f"  실행 시각: {now_kst().strftime('%Y-%m-%d %H:%M:%S KST')}")
    print(f"  분석 모드: {MODE_LABELS.get(mode, mode)}")
    print("=" * 60)

    # ── STEP 0: 시스템 자가진단 ──
    try:
        system_health = run_health_check()
    except Exception as e:
        print(f"  ⚠️ 자가진단 실패: {e}")
        system_health = {"status": "unknown", "errors": [str(e)]}

    # ── STEP 1: 항상 실행 — 시장 지수 + 매크로 + 보유종목 현재가 ──
    print("\n[1] 시장 지수 + 매크로 지표 수집")
    market_summary = get_market_index()
    print(f"  KOSPI: {market_summary.get('kospi', {}).get('value', 'N/A')}")
    print(f"  KOSDAQ: {market_summary.get('kosdaq', {}).get('value', 'N/A')}")

    macro = get_macro_indicators()
    mood = macro.get("market_mood", {})
    fred = macro.get("fred") or {}
    fred_note = ""
    if fred.get("dgs10"):
        fred_note = f" | FRED DGS10 {fred['dgs10'].get('value')}% ({fred['dgs10'].get('date', '')})"
    print(
        f"  매크로: {mood.get('label', '?')} ({mood.get('score', 0)}점) | "
        f"USD/KRW: {macro.get('usd_krw', {}).get('value', '?')} | VIX: {macro.get('vix', {}).get('value', '?')}"
        f"{fred_note}"
    )

    portfolio = load_portfolio()
    portfolio["updated_at"] = now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00")
    portfolio["market_summary"] = market_summary
    portfolio["macro"] = macro
    portfolio["system_health"] = system_health

    # 뉴스 + 섹터 수집 (모든 모드에서 실행)
    print("\n[2] 헤드라인 뉴스 + 섹터 수집")
    try:
        headlines = collect_headlines(max_items=20)
        portfolio["headlines"] = headlines
        print(f"  뉴스 {len(headlines)}건")
    except Exception as e:
        print(f"  뉴스 수집 실패: {e}")
        portfolio.setdefault("headlines", [])

    try:
        sectors = get_sector_rankings()
        portfolio["sectors"] = sectors
        hot = [s["name"] for s in sectors[:3]]
        print(f"  섹터 {len(sectors)}개 | HOT: {', '.join(hot)}")
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

    # X(트위터) 감성 수집 (모든 모드)
    print("\n[2.3] X(트위터) 시장 감성")
    try:
        x_sentiment = collect_x_sentiment(max_items=20)
        portfolio["x_sentiment"] = x_sentiment
        fig_names = [f["name"] for f in x_sentiment.get("key_figures", [])[:3]]
        print(f"  X 감성: {x_sentiment['score']}점 | {x_sentiment['tweet_count']}건 | 주요 인물: {', '.join(fig_names) or '없음'}")
    except Exception as e:
        print(f"  X 감성 수집 실패: {e}")
        portfolio.setdefault("x_sentiment", {})

    # 글로벌 이벤트 수집 (모든 모드)
    print("\n[2.5] 글로벌 이벤트 캘린더")
    try:
        global_events = collect_global_events()
        portfolio["global_events"] = global_events
        upcoming = [e for e in global_events if e.get("d_day", 99) <= 3]
        print(f"  이벤트 {len(global_events)}건 | D-3 이내 {len(upcoming)}건")
    except Exception as e:
        print(f"  이벤트 수집 실패: {e}")
        portfolio.setdefault("global_events", [])

    # realtime 모드: 보유종목 현재가만 갱신 후 저장
    if mode == "realtime":
        print("\n[3] 보유 종목 현재가 갱신")
        price_map = build_price_map(portfolio)
        for h in portfolio["vams"]["holdings"]:
            if h["ticker"] in price_map:
                h["current_price"] = price_map[h["ticker"]]
                h["return_pct"] = round((h["current_price"] - h["buy_price"]) / h["buy_price"] * 100, 2)
                h["highest_price"] = max(h.get("highest_price", 0), h["current_price"])
        recalculate_total(portfolio)
        print(f"  {len(price_map)}개 종목 갱신")

        prev_recs = portfolio.get("recommendations", [])
        for stock in prev_recs:
            try:
                flow = get_investor_flow(stock["ticker"])
                stock["flow"] = flow
            except Exception:
                pass
        portfolio["recommendations"] = prev_recs

        # 알림 엔진 실행 (realtime에서도)
        briefing = generate_briefing(portfolio)
        portfolio["briefing"] = briefing
        print(f"  비서: {briefing['headline']}")

        save_portfolio(portfolio)
        print(f"\n✅ 실시간 갱신 완료 (보유 {len(portfolio['vams']['holdings'])}종목)")
        return

    # ── STEP 2: quick + full — 종목 필터링 ──
    print("\n[2] 3단계 깔때기 필터링")
    candidates = run_filter_pipeline()
    print(f"  최종 후보: {len(candidates)}개 종목")

    # ── STEP 3: quick + full — 기술적 + 수급 + 컨센서스 ──
    print("\n[3] 기술적 분석 + 수급 + 컨센서스")
    macro_mood = macro.get("market_mood", {"score": 50, "label": "중립"})
    export_by_ticker = load_trade_export_by_ticker()
    consensus_rows: list = []
    for i, stock in enumerate(candidates, 1):
        name = stock["name"]
        ticker = stock["ticker"]
        ticker_yf = stock.get("ticker_yf", f"{ticker}.KS")
        print(f"  [{i}/{len(candidates)}] {name}...", end="")

        tech = analyze_technical(ticker_yf)
        stock["technical"] = tech

        flow = get_investor_flow(ticker)
        stock["flow"] = flow

        if mode == "full":
            sentiment = get_stock_sentiment(name)
        else:
            prev_recs = _load_previous_analysis()
            prev_match = next((r for r in prev_recs if r.get("ticker") == ticker), None)
            sentiment = prev_match.get("sentiment", {"score": 50, "positive": 0, "negative": 0, "neutral": 0, "headline_count": 0, "top_headlines": [], "detail": []}) if prev_match else {"score": 50, "positive": 0, "negative": 0, "neutral": 0, "headline_count": 0, "top_headlines": [], "detail": []}
        stock["sentiment"] = sentiment

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
    for stock in candidates:
        ticker_yf = stock.get("ticker_yf", f"{stock['ticker']}.KS")
        try:
            prediction = predict_stock(ticker_yf, current_features=stock)
            stock["prediction"] = prediction
            print(f"  {stock['name']}: {prediction['up_probability']}% ({prediction['method']})")
        except Exception:
            stock["prediction"] = {"up_probability": 50, "method": "error", "model_accuracy": 0, "confidence_level": "none", "top_features": {}, "train_samples": 0, "test_samples": 0}

    # 타이밍 시그널 계산 (예측 완료 후)
    for stock in candidates:
        stock["timing"] = compute_timing_signal(stock)

    # ── STEP 5: full 전용 — 백테스트 ──
    if mode == "full":
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
    if mode == "full":
        print("\n[5.5] 실적 캘린더 수집")
        try:
            collect_earnings_for_stocks(candidates)
            earns = [s for s in candidates if s.get("earnings", {}).get("next_earnings")]
            print(f"  {len(earns)}개 종목 실적일 확인")
        except Exception as e:
            print(f"  실적 캘린더 스킵: {e}")

    # ── STEP 5.7: full 전용 — DART 재무제표(현금흐름) ──
    if mode == "full":
        print("\n[5.7] DART 재무제표 + 현금흐름 수집")
        from api.collectors.DartScout import scout
        dart_ok = 0
        for stock in candidates:
            ticker_yf = stock.get("ticker_yf", f"{stock['ticker']}.KS")
            try:
                dart_data = scout(ticker_yf)
                if not dart_data.get("error") and not dart_data.get("critical_error"):
                    stock["dart_financials"] = {
                        "financials": dart_data.get("financials", {}),
                        "cashflow": dart_data.get("cashflow", {}),
                        "dividends": dart_data.get("dividends", []),
                        "audit_opinion": dart_data.get("audit_opinion", ""),
                    }
                    dart_ok += 1
            except Exception:
                pass
        print(f"  {dart_ok}/{len(candidates)} 종목 DART 데이터 수집 완료")

    # ── STEP 5.8: 원자재 상관·마진 (기본 full / quick는 COMMODITY_SCOUT_IN_QUICK=1)
    run_commodity = mode == "full" or COMMODITY_SCOUT_IN_QUICK
    run_commodity_narrative = mode == "full" or COMMODITY_NARRATIVE_IN_QUICK
    if run_commodity:
        tag = "full" if mode == "full" else "quick+COMMODITY_SCOUT_IN_QUICK"
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
                )
            n_hi = len(scout.get("high_correlation") or [])
            n_mom = len(scout.get("commodity_mom_alerts") or [])
            print(f"  고상관 종목 {n_hi}개 | 전월대비 급변 원자재 {n_mom}건 → commodity_impact.json")
        except Exception as e:
            print(f"  CommodityScout 스킵: {e}")
            portfolio.setdefault("commodity_impact", {})
    else:
        portfolio.setdefault("commodity_impact", {})

    # ── STEP 5.9: Verity Brain — 종합 판단 엔진 ──
    print("\n[5.9] Verity Brain 종합 판단")
    portfolio["recommendations"] = candidates
    try:
        brain_result = verity_brain_analyze(candidates, portfolio)
        portfolio["verity_brain"] = {
            "macro_override": brain_result.get("macro_override"),
            "market_brain": brain_result.get("market_brain"),
        }
        brain_stocks = {r["ticker"]: r for r in brain_result.get("stocks", [])}
        for stock in candidates:
            br = brain_stocks.get(stock.get("ticker"), {})
            stock["verity_brain"] = {
                "brain_score": br.get("brain_score", 0),
                "grade": br.get("grade", "WATCH"),
                "grade_label": br.get("grade_label", "관망"),
                "fact_score": br.get("fact_score", {}),
                "sentiment_score": br.get("sentiment_score", {}),
                "vci": br.get("vci", {}),
                "red_flags": br.get("red_flags", {}),
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
            flag_str = ", ".join(f["name"] for f in flagged[:3])
            print(f"  레드플래그: {flag_str}")
    except Exception as e:
        print(f"  ⚠️ Verity Brain 스킵: {e}")
        portfolio.setdefault("verity_brain", {})

    # ── STEP 6: full 전용 — Gemini AI ──
    if mode == "full":
        print("\n[6] Gemini AI 종합 분석")
        try:
            analyzed = analyze_batch(candidates, macro_context=macro)
            print(f"  분석 완료: {len(analyzed)}개 종목")
        except Exception as e:
            print(f"  ⚠️ Gemini 스킵: {e}")
            analyzed = candidates
    else:
        analyzed = candidates

    _apply_fallback_judgments(analyzed)

    # ── STEP 6.3: full 전용 — Claude 2차 심층 분석 (상위 N개만) ──
    if mode == "full" and ANTHROPIC_API_KEY:
        print(f"\n[6.3] Claude 2차 심층 분석 (Brain {CLAUDE_MIN_BRAIN_SCORE}점↑, 상위 {CLAUDE_TOP_N}개)")
        try:
            claude_targets = [
                s for s in analyzed
                if s.get("verity_brain", {}).get("brain_score", 0) >= CLAUDE_MIN_BRAIN_SCORE
            ]
            claude_targets.sort(
                key=lambda s: s.get("verity_brain", {}).get("brain_score", 0),
                reverse=True,
            )
            claude_targets = claude_targets[:CLAUDE_TOP_N]

            if claude_targets:
                gemini_map = {s["ticker"]: s for s in analyzed}
                claude_results = analyze_batch_deep(claude_targets, gemini_map, macro)

                merged = 0
                overridden = 0
                for stock in analyzed:
                    cr = claude_results.get(stock["ticker"])
                    if cr and cr.get("_model"):
                        merge_dual_analysis(stock, cr)
                        merged += 1
                        if cr.get("override_recommendation"):
                            overridden += 1

                total_tokens = sum(
                    (r.get("_input_tokens", 0) + r.get("_output_tokens", 0))
                    for r in claude_results.values()
                )
                print(f"  병합: {merged}종목 | 판정 변경: {overridden}건 | 총 {total_tokens:,}토큰")
            else:
                print(f"  Brain {CLAUDE_MIN_BRAIN_SCORE}점 이상 종목 없음 → 스킵")
        except Exception as e:
            print(f"  ⚠️ Claude 분석 스킵: {e}")

    # ── STEP 6.5: full 전용 — AI 일일 리포트 ──
    if mode == "full":
        print("\n[6.5] AI 일일 시장 리포트")
        try:
            daily_report = generate_daily_report(
                macro=macro,
                candidates=analyzed,
                sectors=portfolio.get("sectors", []),
                headlines=portfolio.get("headlines", []),
                verity_brain=portfolio.get("verity_brain"),
            )
            portfolio["daily_report"] = daily_report
            print(f"  요약: {daily_report.get('market_summary', '?')[:60]}")
        except Exception as e:
            print(f"  리포트 스킵: {e}")
            portfolio.setdefault("daily_report", {})
    else:
        portfolio.setdefault("daily_report", {})

    # ── STEP 7: VAMS ──
    print(f"\n[7] VAMS 가상 투자")
    portfolio["recommendations"] = analyzed

    price_map = build_price_map(portfolio)
    for stock in analyzed:
        price_map.setdefault(stock["ticker"], stock.get("price", 0))

    portfolio, alerts = run_vams_cycle(portfolio, analyzed, price_map)

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
    print(f"  비서: {briefing['headline']}")
    print(f"  알림: CRITICAL {briefing['alert_counts']['critical']} | WARNING {briefing['alert_counts']['warning']} | INFO {briefing['alert_counts']['info']}")
    for item in briefing.get("action_items", []):
        print(f"  → {item}")

    # ── STEP 9: 저장 + 알림 ──
    print(f"\n[9] 저장 + 알림")
    save_portfolio(portfolio)

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

    # 텔레그램 봇 — 대기 중인 질문 응답
    print(f"\n[10] 텔레그램 봇 폴링")
    try:
        run_poll_once()
    except Exception as e:
        print(f"  봇 폴링 스킵: {e}")

    if mode == "full":
        send_daily_report(portfolio)
        print(f"\n✅ 전체 분석 완료!")
    else:
        print(f"\n✅ 빠른 분석 완료!")


if __name__ == "__main__":
    main()
