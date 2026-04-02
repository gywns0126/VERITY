"""
안심(安心) AI 주식 보안 비서 - 메인 파이프라인 (Sprint 2)
매일 장 마감 후 실행:
  1. 시장 데이터 + 매크로 지표 수집
  2. 3단계 깔때기 필터링
  3. 기술적 분석 + 뉴스 감성 + 수급 분석
  4. 멀티팩터 통합 점수
  5. Gemini AI 종합 분석 (강화 프롬프트)
  6. VAMS 가상 투자 실행
  7. JSON 저장 + 텔레그램 알림
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from api.config import now_kst
from api.collectors.stock_data import get_market_index
from api.collectors.macro_data import get_macro_indicators
from api.collectors.news_sentiment import get_stock_sentiment
from api.collectors.market_flow import get_investor_flow
from api.analyzers.stock_filter import run_filter_pipeline
from api.analyzers.technical import analyze_technical
from api.analyzers.multi_factor import compute_multi_factor_score
from api.analyzers.gemini_analyst import analyze_batch
from api.vams.engine import (
    load_portfolio,
    save_portfolio,
    run_vams_cycle,
    recalculate_total,
)
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
    실행 시각 기반으로 분석 모드 결정
    - full: KST 15:30 이후 → Gemini AI 포함 전체 분석
    - quick: 장중 → Gemini 스킵, 멀티팩터 기반 분석
    """
    mode = os.environ.get("ANALYSIS_MODE", "").lower()
    if mode in ("full", "quick"):
        return mode
    hour = now_kst().hour
    minute = now_kst().minute
    if hour > 15 or (hour == 15 and minute >= 30):
        return "full"
    return "quick"


def main():
    mode = get_analysis_mode()
    mode_label = "전체 분석 (Gemini 포함)" if mode == "full" else "빠른 갱신 (멀티팩터)"

    print("=" * 60)
    print(f"  VERITY — AI 주식 분석 엔진 v2.0")
    print(f"  실행 시각: {now_kst().strftime('%Y-%m-%d %H:%M:%S KST')}")
    print(f"  분석 모드: {mode_label}")
    print("=" * 60)

    # 1. 시장 지수 + 매크로
    print("\n[1/7] 시장 지수 + 매크로 지표 수집")
    market_summary = get_market_index()
    print(f"  KOSPI: {market_summary.get('kospi', {}).get('value', 'N/A')}")
    print(f"  KOSDAQ: {market_summary.get('kosdaq', {}).get('value', 'N/A')}")

    macro = get_macro_indicators()
    mood = macro.get("market_mood", {})
    print(f"  매크로 분위기: {mood.get('label', '?')} ({mood.get('score', 0)}점)")
    print(f"  USD/KRW: {macro.get('usd_krw', {}).get('value', '?')}")
    print(f"  VIX: {macro.get('vix', {}).get('value', '?')}")

    # 2. 종목 필터링
    print("\n[2/7] 3단계 깔때기 필터링")
    candidates = run_filter_pipeline()
    print(f"  최종 후보: {len(candidates)}개 종목")

    # 3. 기술적 + 감성 + 수급 분석
    print("\n[3/7] 멀티팩터 분석 (기술적/뉴스/수급)")
    candidates = enrich_with_analysis(candidates, macro)

    # 4. Gemini AI 분석 (full 모드에서만 실행)
    print(f"\n[4/7] Gemini AI 종합 분석 [{mode} 모드]")
    if mode == "full":
        try:
            analyzed = analyze_batch(candidates, macro_context=macro)
            print(f"  분석 완료: {len(analyzed)}개 종목")
        except Exception as e:
            print(f"  ⚠️ Gemini 분석 스킵: {e}")
            analyzed = candidates
    else:
        print("  → quick 모드: Gemini 스킵, 멀티팩터 기반 판단 사용")
        analyzed = candidates

    # Gemini 미실행 또는 실패 시 멀티팩터 기반 자동 판단
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

            # Gold/Silver 자동 생성 (Gemini 실패 시)
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

    # 5. VAMS
    print("\n[5/7] VAMS 가상 투자 엔진 가동")
    portfolio = load_portfolio()
    portfolio["updated_at"] = now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00")
    portfolio["market_summary"] = market_summary
    portfolio["macro"] = macro
    portfolio["recommendations"] = analyzed

    price_map = build_price_map(portfolio)
    for stock in analyzed:
        price_map.setdefault(stock["ticker"], stock.get("price", 0))

    portfolio, alerts = run_vams_cycle(portfolio, analyzed, price_map)

    # 6. 저장
    print("\n[6/7] 결과 저장")
    save_portfolio(portfolio)
    print(f"  portfolio.json 저장 완료")

    # 7. 알림
    print("\n[7/7] 알림 전송")
    vams = portfolio["vams"]
    print(f"\n{'=' * 60}")
    print(f"  📊 VAMS 현황")
    print(f"  총 자산: {vams['total_asset']:,.0f}원")
    print(f"  현금: {vams['cash']:,.0f}원")
    print(f"  수익률: {vams['total_return_pct']:+.2f}%")
    print(f"  보유: {len(vams['holdings'])}종목")
    print(f"  알림: {len(alerts)}건")
    print(f"{'=' * 60}")

    if alerts:
        print("\n  알림 내역:")
        for a in alerts:
            print(f"    {a['message']}")
        send_alerts(alerts)

    if mode == "full":
        send_daily_report(portfolio)
        print("\n✅ 일일 전체 분석 완료!")
    else:
        print("\n✅ 장중 빠른 갱신 완료!")


if __name__ == "__main__":
    main()
