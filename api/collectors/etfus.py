"""
미국 ETF 시세·AUM·수익률 수집 (Polygon + yfinance 폴백)
  - 주요 ETF 시세/거래량
  - AUM, 비용비율, 배당수익률
  - 기간별 수익률 (1M / 3M / 1Y)
  - 채권 ETF 전용 리스트 분리
"""
import logging
from typing import Any, Dict, List, Optional

import yfinance as yf
import pandas as pd

from api.config import POLYGON_API_KEY, POLYGON_TIER, now_kst

logger = logging.getLogger(__name__)

_US_TOP_ETFS = [
    ("SPY",  "SPDR S&P 500 ETF Trust",         "equity_us_large"),
    ("QQQ",  "Invesco QQQ Trust",               "equity_us_tech"),
    ("IWM",  "iShares Russell 2000 ETF",        "equity_us_small"),
    ("VTI",  "Vanguard Total Stock Market ETF",  "equity_us_total"),
    ("EFA",  "iShares MSCI EAFE ETF",           "equity_intl"),
    ("EEM",  "iShares MSCI Emerging Markets",    "equity_em"),
    ("VWO",  "Vanguard FTSE Emerging Markets",   "equity_em"),
    ("XLF",  "Financial Select Sector SPDR",     "sector_financial"),
    ("XLK",  "Technology Select Sector SPDR",    "sector_tech"),
    ("XLE",  "Energy Select Sector SPDR",        "sector_energy"),
    ("GLD",  "SPDR Gold Shares",                 "commodity_gold"),
    ("SLV",  "iShares Silver Trust",             "commodity_silver"),
    ("USO",  "United States Oil Fund",           "commodity_oil"),
    ("DIA",  "SPDR Dow Jones Industrial",        "equity_us_large"),
    ("ARKK", "ARK Innovation ETF",              "thematic_innovation"),
]

_BOND_ETFS = [
    ("TLT",  "iShares 20+ Year Treasury Bond", "bond_us_long"),
    ("IEF",  "iShares 7-10 Year Treasury Bond", "bond_us_mid"),
    ("SHY",  "iShares 1-3 Year Treasury Bond",  "bond_us_short"),
    ("AGG",  "iShares Core US Aggregate Bond",   "bond_us_agg"),
    ("BND",  "Vanguard Total Bond Market ETF",   "bond_us_total"),
    ("LQD",  "iShares iBoxx $ IG Corporate",    "bond_us_ig"),
    ("HYG",  "iShares iBoxx $ High Yield Corp", "bond_us_hy"),
    ("JNK",  "SPDR Bloomberg High Yield Bond",  "bond_us_hy"),
    ("TIP",  "iShares TIPS Bond ETF",           "bond_us_tips"),
    ("EMB",  "iShares J.P. Morgan USD EM Bond", "bond_em"),
]

_PERIOD_TRADING_DAYS = {"1M": 22, "3M": 66, "1Y": 252}


def _yf_etf_data(ticker: str) -> Optional[Dict[str, Any]]:
    """yfinance로 ETF 시세·AUM·비용비율·배당수익률·수익률 수집."""
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="1y")
        if hist is None or hist.empty:
            return None

        hist = hist.dropna(subset=["Close"])
        if hist.empty:
            return None

        last_close = float(hist["Close"].iloc[-1])
        volume = int(hist["Volume"].iloc[-1]) if "Volume" in hist.columns else 0

        info = t.info or {}
        aum = info.get("totalAssets")
        expense_ratio = info.get("annualReportExpenseRatio")
        dividend_yield = info.get("yield")

        returns: Dict[str, Optional[float]] = {}
        closes = hist["Close"].dropna()
        for label, days in _PERIOD_TRADING_DAYS.items():
            if len(closes) > days:
                ref = float(closes.iloc[-(days + 1)])
                if ref > 0:
                    returns[label] = round((last_close - ref) / ref * 100, 2)
                else:
                    returns[label] = None
            else:
                returns[label] = None

        result: Dict[str, Any] = {
            "close": round(last_close, 2),
            "volume": volume,
            "returns": returns,
        }

        if aum is not None:
            result["aum"] = int(aum)
        if expense_ratio is not None:
            result["expense_ratio"] = round(float(expense_ratio), 4)
        if dividend_yield is not None and dividend_yield > 0:
            result["dividend_yield"] = round(float(dividend_yield), 4)

        return result
    except Exception as e:
        logger.warning("yfinance ETF %s failed: %s", ticker, e)
        return None


def _polygon_etf_snapshot(ticker: str) -> Optional[Dict[str, Any]]:
    """Polygon에서 ETF 스냅샷 (보조)."""
    if not POLYGON_API_KEY:
        return None
    try:
        from api.collectors.polygon_client import _get
        data = _get(
            f"/v2/snapshot/locale/us/markets/stocks/tickers/{ticker}",
            {},
            POLYGON_API_KEY,
            tier=POLYGON_TIER,
        )
        if not data or not isinstance(data, dict):
            return None
        snap = data.get("ticker", {})
        day = snap.get("day", {})
        prev = snap.get("prevDay", {})
        close = day.get("c") or snap.get("lastTrade", {}).get("p")
        prev_close = prev.get("c")
        if close is None:
            return None
        result: Dict[str, Any] = {"close": round(float(close), 2)}
        if prev_close and prev_close > 0:
            result["change_pct"] = round((float(close) / float(prev_close) - 1) * 100, 2)
        result["volume"] = int(day.get("v", 0))
        return result
    except Exception:
        return None


def _collect_etf_list(
    etf_list: List[tuple],
) -> List[Dict[str, Any]]:
    """ETF 리스트를 순회하며 시세 수집."""
    ts = now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00")
    results: List[Dict[str, Any]] = []

    for ticker, name, category in etf_list:
        data = _yf_etf_data(ticker)
        if data is None:
            poly = _polygon_etf_snapshot(ticker)
            if poly is None:
                continue
            data = poly

        entry: Dict[str, Any] = {
            "ticker": ticker,
            "name": name,
            "category": category,
            **data,
            "updated_at": ts,
        }
        results.append(entry)

    return results


def get_us_etf_summary() -> List[Dict[str, Any]]:
    """미국 주요 ETF 시세·수익률 요약."""
    return _collect_etf_list(_US_TOP_ETFS)


def get_bond_etf_summary() -> List[Dict[str, Any]]:
    """미국 채권 ETF 시세·수익률 요약."""
    return _collect_etf_list(_BOND_ETFS)


if __name__ == "__main__":
    import json
    print("=== US Top ETFs ===")
    us = get_us_etf_summary()
    print(f"수집: {len(us)}개")
    if us:
        print(json.dumps(us[:2], ensure_ascii=False, indent=2))

    print("\n=== Bond ETFs ===")
    bonds = get_bond_etf_summary()
    print(f"수집: {len(bonds)}개")
    if bonds:
        print(json.dumps(bonds[:2], ensure_ascii=False, indent=2))
