"""
VERITY — AI 주식 분석 엔진 v6.0 (Sprint 6)

3단계 실행 모드:
  realtime (15분): 가격/환율/지수/수급만 갱신 (~1분)
  quick (1시간):   + 기술적분석/멀티팩터/XGBoost (~3분)
  full (장마감):   + 뉴스감성/Gemini AI/백테스트/실적/리포트 (~7분)
"""
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from api.config import now_kst, DATA_DIR
from api.collectors.stock_data import get_market_index
from api.collectors.macro_data import get_macro_indicators
from api.collectors.news_sentiment import get_stock_sentiment
from api.collectors.market_flow import get_investor_flow
from api.analyzers.stock_filter import run_filter_pipeline
from api.analyzers.technical import analyze_technical
from api.analyzers.multi_factor import compute_multi_factor_score
from api.analyzers.gemini_analyst import analyze_batch, generate_daily_report
from api.analyzers.sector_rotation import get_sector_rotation
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
from api.notifications.telegram import send_alerts, send_daily_report


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
    """Sprint 2: 각 후보 종목에 기술적/감성/수급/멀티팩터 분석 추가"""
    macro_mood = macro.get("market_mood", {"score": 50, "label": "중립"})
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

        # 멀티팩터 통합 점수
        mf = compute_multi_factor_score(
            fundamental_score=stock.get("safety_score", 50),
            technical=tech,
            sentiment=sentiment,
            flow=flow,
            macro_mood=macro_mood,
        )
        stock["multi_factor"] = mf
        print(f"      종합: {mf['multi_score']}점 ({mf['grade']}) | 시그널: {', '.join(mf['all_signals'][:3]) or '없음'}")

    return candidates


def get_analysis_mode() -> str:
    """
    실행 시각 기반으로 3단계 분석 모드 결정
    - realtime: 매 15분 → 가격/환율/지수/수급만 (~1분)
    - quick: 매 정시 → + 기술적/멀티팩터/XGBoost (~3분)
    - full: 장마감 후 → + 뉴스감성/Gemini/백테스트/텔레그램 (~5분)
    """
    mode = os.environ.get("ANALYSIS_MODE", "").lower()
    if mode in ("full", "quick", "realtime"):
        return mode
    now = now_kst()
    hour, minute = now.hour, now.minute
    if hour > 15 or (hour == 15 and minute >= 30):
        return "full"
    if minute < 5:
        return "quick"
    return "realtime"


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
    MODE_LABELS = {
        "realtime": "실시간 갱신 (가격/환율/수급)",
        "quick": "빠른 분석 (기술적/멀티팩터/예측)",
        "full": "전체 분석 (Gemini/백테스트/텔레그램)",
    }

    print("=" * 60)
    print(f"  VERITY — AI 주식 분석 엔진 v5.0")
    print(f"  실행 시각: {now_kst().strftime('%Y-%m-%d %H:%M:%S KST')}")
    print(f"  분석 모드: {MODE_LABELS.get(mode, mode)}")
    print("=" * 60)

    # ── STEP 1: 항상 실행 — 시장 지수 + 매크로 + 보유종목 현재가 ──
    print("\n[1] 시장 지수 + 매크로 지표 수집")
    market_summary = get_market_index()
    print(f"  KOSPI: {market_summary.get('kospi', {}).get('value', 'N/A')}")
    print(f"  KOSDAQ: {market_summary.get('kosdaq', {}).get('value', 'N/A')}")

    macro = get_macro_indicators()
    mood = macro.get("market_mood", {})
    print(f"  매크로: {mood.get('label', '?')} ({mood.get('score', 0)}점) | USD/KRW: {macro.get('usd_krw', {}).get('value', '?')} | VIX: {macro.get('vix', {}).get('value', '?')}")

    portfolio = load_portfolio()
    portfolio["updated_at"] = now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00")
    portfolio["market_summary"] = market_summary
    portfolio["macro"] = macro

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

        save_portfolio(portfolio)
        print(f"\n✅ 실시간 갱신 완료 (보유 {len(portfolio['vams']['holdings'])}종목)")
        return

    # ── STEP 2: quick + full — 종목 필터링 ──
    print("\n[2] 3단계 깔때기 필터링")
    candidates = run_filter_pipeline()
    print(f"  최종 후보: {len(candidates)}개 종목")

    # ── STEP 3: quick + full — 기술적 + 수급 분석 ──
    print("\n[3] 기술적 분석 + 수급")
    macro_mood = macro.get("market_mood", {"score": 50, "label": "중립"})
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

        mf = compute_multi_factor_score(
            fundamental_score=stock.get("safety_score", 50),
            technical=tech, sentiment=sentiment, flow=flow, macro_mood=macro_mood,
        )
        stock["multi_factor"] = mf
        print(f" {mf['multi_score']}점({mf['grade']}) RSI:{tech['rsi']} 수급:{flow['flow_score']}")

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

    # ── STEP 6.5: full 전용 — AI 일일 리포트 ──
    if mode == "full":
        print("\n[6.5] AI 일일 시장 리포트")
        try:
            daily_report = generate_daily_report(
                macro=macro,
                candidates=analyzed,
                sectors=portfolio.get("sectors", []),
                headlines=portfolio.get("headlines", []),
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

    # ── STEP 8: 저장 + 알림 ──
    print(f"\n[8] 저장 + 알림")
    save_portfolio(portfolio)

    vams = portfolio["vams"]
    print(f"  총자산: {vams['total_asset']:,.0f}원 | 수익률: {vams['total_return_pct']:+.2f}% | 보유: {len(vams['holdings'])}종목")

    if alerts:
        for a in alerts:
            print(f"  알림: {a['message']}")
        send_alerts(alerts)

    if mode == "full":
        send_daily_report(portfolio)
        print(f"\n✅ 전체 분석 완료!")
    else:
        print(f"\n✅ 빠른 분석 완료!")


if __name__ == "__main__":
    main()
