"""KRX 전 종목 리스트 생성 → data/krx_stocks.json (검색 자동완성용)"""
import json
import os

try:
    from pykrx import stock as pykrx_stock
    tickers_kospi = pykrx_stock.get_market_ticker_list(market="KOSPI")
    tickers_kosdaq = pykrx_stock.get_market_ticker_list(market="KOSDAQ")

    stocks = []
    for t in tickers_kospi:
        name = pykrx_stock.get_market_ticker_name(t)
        if name:
            stocks.append({"ticker": t, "name": name, "market": "KOSPI", "yf": f"{t}.KS"})
    for t in tickers_kosdaq:
        name = pykrx_stock.get_market_ticker_name(t)
        if name:
            stocks.append({"ticker": t, "name": name, "market": "KOSDAQ", "yf": f"{t}.KQ"})

    print(f"수집 완료: KOSPI {len(tickers_kospi)}개, KOSDAQ {len(tickers_kosdaq)}개")

except Exception as e:
    print(f"pykrx 실패 ({e}), 하드코딩 목록 사용")
    stocks = []

if not stocks:
    from _fallback_stocks import FALLBACK_STOCKS
    stocks = FALLBACK_STOCKS

out_path = os.path.join(os.path.dirname(__file__), "..", "data", "krx_stocks.json")
os.makedirs(os.path.dirname(out_path), exist_ok=True)
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(stocks, f, ensure_ascii=False, indent=1)

print(f"저장 완료: {len(stocks)}개 → {out_path}")
