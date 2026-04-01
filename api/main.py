"""
안심(安心) AI 주식 보안 비서 - 메인 파이프라인
매일 장 마감 후 실행:
  1. 시장 데이터 수집 (pykrx)
  2. 3단계 깔때기 필터링
  3. Gemini AI 종합 분석
  4. VAMS 가상 투자 실행
  5. JSON 저장 + 텔레그램 알림
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from api.config import now_kst
from api.collectors.stock_data import get_market_index
from api.analyzers.stock_filter import run_filter_pipeline
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


def main():
    print("=" * 60)
    print(f"  안심 AI 주식 보안 비서 - 일일 분석 시작")
    print(f"  실행 시각: {now_kst().strftime('%Y-%m-%d %H:%M:%S KST')}")
    print("=" * 60)

    # 1. 시장 지수 수집
    print("\n[1/5] 시장 지수 수집")
    market_summary = get_market_index()
    print(f"  KOSPI: {market_summary.get('kospi', {}).get('value', 'N/A')}")
    print(f"  KOSDAQ: {market_summary.get('kosdaq', {}).get('value', 'N/A')}")

    # 2. 종목 필터링
    print("\n[2/5] 3단계 깔때기 필터링")
    candidates = run_filter_pipeline()
    print(f"  최종 후보: {len(candidates)}개 종목")
    for c in candidates:
        print(f"    - {c['name']} (안심 {c['safety_score']}점)")

    # 3. Gemini AI 분석
    print("\n[3/5] Gemini AI 종합 분석")
    try:
        analyzed = analyze_batch(candidates)
        print(f"  분석 완료: {len(analyzed)}개 종목")
    except Exception as e:
        print(f"  ⚠️ Gemini 분석 스킵 (API 키 미설정 또는 오류): {e}")
        analyzed = candidates

    # Gemini 실패/미연동 종목은 안심점수 기반으로 자동 판단
    for stock in analyzed:
        if "recommendation" not in stock or "오류" in stock.get("ai_verdict", ""):
            score = stock.get("safety_score", 0)
            if score >= 75:
                stock["recommendation"] = "BUY"
                stock["ai_verdict"] = f"안심점수 {score}점 — 펀더멘털 양호, 자동 매수 후보"
            elif score >= 60:
                stock["recommendation"] = "WATCH"
                stock["ai_verdict"] = f"안심점수 {score}점 — 관찰 필요"
            else:
                stock["recommendation"] = "AVOID"
                stock["ai_verdict"] = f"안심점수 {score}점 — 리스크 높음"
            stock.setdefault("confidence", score)
            stock.setdefault("risk_flags", [])
            stock.setdefault("gold_insight", "재무 데이터 기반 자동 판단")
            stock.setdefault("silver_insight", "시장 데이터 기반")
            stock.setdefault("detected_risk_keywords", [])

    # 4. VAMS 가상 투자 실행
    print("\n[4/5] VAMS 가상 투자 엔진 가동")
    portfolio = load_portfolio()
    portfolio["updated_at"] = now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00")
    portfolio["market_summary"] = market_summary
    portfolio["recommendations"] = analyzed

    price_map = build_price_map(portfolio)
    for stock in analyzed:
        price_map.setdefault(stock["ticker"], stock.get("price", 0))

    portfolio, alerts = run_vams_cycle(portfolio, analyzed, price_map)

    # 5. 저장 및 알림
    print("\n[5/5] 결과 저장 및 알림")
    save_portfolio(portfolio)
    print(f"  portfolio.json 저장 완료")

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

    send_daily_report(portfolio)
    print("\n✅ 일일 분석 완료!")


if __name__ == "__main__":
    main()
