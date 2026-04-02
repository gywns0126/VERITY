"""
실적 캘린더 모듈
yfinance에서 종목별 실적발표 예정일을 수집
"""
import yfinance as yf
from datetime import datetime, timedelta
import pandas as pd


def get_earnings_dates(ticker_yf: str) -> dict:
    """종목의 다음 실적발표 예정일 조회"""
    try:
        t = yf.Ticker(ticker_yf)

        cal = t.calendar
        if cal is not None:
            if isinstance(cal, dict):
                ed = cal.get("Earnings Date", [])
                if ed:
                    next_date = str(ed[0])[:10] if isinstance(ed, list) else str(ed)[:10]
                    return {"next_earnings": next_date, "source": "calendar"}
            elif isinstance(cal, pd.DataFrame) and not cal.empty:
                if "Earnings Date" in cal.index:
                    val = cal.loc["Earnings Date"].iloc[0]
                    return {"next_earnings": str(val)[:10], "source": "calendar"}

        try:
            edates = t.get_earnings_dates(limit=4)
            if edates is not None and not edates.empty:
                now = datetime.now()
                future = edates[edates.index >= pd.Timestamp(now - timedelta(days=7))]
                if not future.empty:
                    next_date = str(future.index[0])[:10]
                    return {"next_earnings": next_date, "source": "earnings_dates"}
        except Exception:
            pass

    except Exception:
        pass

    return {"next_earnings": None, "source": "unavailable"}


def collect_earnings_for_stocks(stocks: list) -> list:
    """후보 종목들의 실적발표일 일괄 수집"""
    for stock in stocks:
        ticker_yf = stock.get("ticker_yf", f"{stock['ticker']}.KS")
        try:
            ed = get_earnings_dates(ticker_yf)
            stock["earnings"] = ed
        except Exception:
            stock["earnings"] = {"next_earnings": None, "source": "error"}
    return stocks
