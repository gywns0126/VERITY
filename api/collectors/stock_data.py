"""
KOSPI/KOSDAQ 지수: pykrx(KRX) 우선, 실패 시 yfinance.
해외 지수(NDX, S&P500): yfinance.
"""
from datetime import timedelta
from typing import Dict, Optional

import pandas as pd
import yfinance as yf

from api.config import now_kst

# pykrx KRX 지수 티커 (코스피·코스닥 종합)
_PYKRX_KOSPI = "1001"
_PYKRX_KOSDAQ = "2001"

KOSPI_MAJOR = {
    "005930.KS": "삼성전자",
    "000660.KS": "SK하이닉스",
    "373220.KS": "LG에너지솔루션",
    "207940.KS": "삼성바이오로직스",
    "005380.KS": "현대차",
    "000270.KS": "기아",
    "068270.KS": "셀트리온",
    "035420.KS": "NAVER",
    "035720.KS": "카카오",
    "051910.KS": "LG화학",
    "006400.KS": "삼성SDI",
    "055550.KS": "신한지주",
    "105560.KS": "KB금융",
    "003670.KS": "포스코퓨처엠",
    "012330.KS": "현대모비스",
    "066570.KS": "LG전자",
    "028260.KS": "삼성물산",
    "003550.KS": "LG",
    "096770.KS": "SK이노베이션",
    "034730.KS": "SK",
    "030200.KS": "KT",
    "032830.KS": "삼성생명",
    "086790.KS": "하나금융지주",
    "017670.KS": "SK텔레콤",
    "033780.KS": "KT&G",
    "009150.KS": "삼성전기",
    "034020.KS": "두산에너빌리티",
    "010130.KS": "고려아연",
    "003490.KS": "대한항공",
    "018260.KS": "삼성에스디에스",
}

KOSDAQ_MAJOR = {
    "247540.KQ": "에코프로비엠",
    "086520.KQ": "에코프로",
    "403870.KQ": "HPSP",
    "028300.KQ": "HLB",
    "067160.KQ": "아프리카TV",
    "277810.KQ": "레인보우로보틱스",
    "058470.KQ": "리노공업",
    "039030.KQ": "이오테크닉스",
    "035900.KQ": "JYP Ent.",
    "041510.KQ": "에스엠",
    "196170.KQ": "알테오젠",
    "348370.KQ": "엔켐",
    "257720.KQ": "실리콘투",
    "328130.KQ": "루닛",
    "145020.KQ": "휴젤",
}

ALL_STOCKS = {**KOSPI_MAJOR, **KOSDAQ_MAJOR}

_YF_INDEX_TICKERS = [
    ("^KS11", "kospi"),
    ("^KQ11", "kosdaq"),
    ("^NDX", "ndx"),
    ("^GSPC", "sp500"),
]


def _fi_scalar(fi, *keys):
    """yfinance fast_info에서 첫 유효 숫자 값."""
    if fi is None:
        return None
    for k in keys:
        try:
            v = fi[k]
        except Exception:
            continue
        if v is None:
            continue
        try:
            f = float(v)
            if pd.notna(f):
                return f
        except (TypeError, ValueError):
            continue
    return None


def _yf_index_snapshot(idx_ticker: str) -> dict:
    """
    단일 지수 스냅샷.
    가능하면 fast_info(시장 개장 중 지연 시세), 없으면 최근 일봉 종가.
    """
    bad = {"value": 0.0, "change_pct": 0.0}
    try:
        t = yf.Ticker(idx_ticker)
        last = None
        prev = None
        try:
            fi = t.fast_info
            last = _fi_scalar(fi, "last_price", "regular_market_price")
            prev = _fi_scalar(fi, "previous_close", "regular_market_previous_close")
        except Exception:
            pass
        if last is not None and prev is not None and prev > 0:
            return {
                "value": round(last, 2),
                "change_pct": round((last - prev) / prev * 100, 2),
            }

        hist = t.history(period="5d")
        hist = hist.dropna(subset=["Close"])
        if len(hist) >= 2:
            today_close = float(hist["Close"].iloc[-1])
            prev_close = float(hist["Close"].iloc[-2])
            if pd.notna(today_close) and pd.notna(prev_close) and prev_close > 0:
                change_pct = ((today_close - prev_close) / prev_close) * 100
                return {
                    "value": round(today_close, 2),
                    "change_pct": round(change_pct, 2),
                }
            return bad
        if len(hist) == 1:
            val = float(hist["Close"].iloc[-1])
            return {
                "value": round(val, 2) if pd.notna(val) else 0.0,
                "change_pct": 0.0,
            }
        return bad
    except Exception:
        return bad


def _pykrx_index_snapshot(pykrx_ticker: str) -> Optional[Dict[str, float]]:
    """
    KRX 일봉 기준 최신 종가·전일 대비(%). 장중이면 당일 봉이 채워질 때까지 전일 대비로 근사.
    KRX/네트워크 실패 시 None.
    """
    try:
        from pykrx import stock
    except ImportError:
        return None
    bad = None
    try:
        end = now_kst().date()
        start = end - timedelta(days=14)
        from_s = start.strftime("%Y%m%d")
        to_s = end.strftime("%Y%m%d")
        df = stock.get_index_ohlcv_by_date(from_s, to_s, pykrx_ticker)
        if df is None or df.empty:
            return bad
        close_col = "종가"
        if close_col not in df.columns:
            return bad
        closes = df[close_col].dropna()
        if len(closes) < 1:
            return bad
        last = float(closes.iloc[-1])
        if len(closes) >= 2:
            prev = float(closes.iloc[-2])
            pct = round((last - prev) / prev * 100, 2) if prev > 0 else 0.0
        else:
            pct = 0.0
        return {"value": round(last, 2), "change_pct": pct}
    except Exception:
        return bad


def _pykrx_equity_last_close(ticker_6: str) -> Optional[float]:
    """KRX 상장 종 최근 거래일 종가(당일 봉 반영). 네트워크/모듈 실패 시 None."""
    try:
        from pykrx import stock as pykrx_stock
    except ImportError:
        return None
    try:
        code = str(ticker_6).zfill(6)
        end = now_kst().date()
        start = end - timedelta(days=14)
        df = pykrx_stock.get_market_ohlcv_by_date(
            start.strftime("%Y%m%d"),
            end.strftime("%Y%m%d"),
            code,
        )
        if df is None or df.empty or "종가" not in df.columns:
            return None
        closes = df["종가"].dropna()
        if len(closes) < 1:
            return None
        v = float(closes.iloc[-1])
        return v if v > 0 else None
    except Exception:
        return None


def get_equity_last_price(ticker_yf: str) -> Optional[float]:
    """
    개별 종목 최신가(원화).
    KOSPI/KOSDAQ: pykrx(거래소 일봉) 우선 → yfinance fast_info → 최근 일봉.
    """
    if not ticker_yf or "." not in str(ticker_yf):
        return None
    parts = str(ticker_yf).strip().split(".")
    code = parts[0].zfill(6)
    suf = parts[-1].upper() if len(parts) >= 2 else ""
    if suf in ("KS", "KQ"):
        pk = _pykrx_equity_last_close(code)
        if pk is not None:
            return pk
    try:
        t = yf.Ticker(ticker_yf)
        try:
            fi = t.fast_info
            last = _fi_scalar(fi, "last_price", "regular_market_price")
            if last is not None and last > 0:
                return float(last)
        except Exception:
            pass
        hist = t.history(period="5d")
        hist = hist.dropna(subset=["Close"])
        if len(hist) >= 1:
            v = float(hist["Close"].iloc[-1])
            if pd.notna(v) and v > 0:
                return v
    except Exception:
        pass
    return None


def get_market_index() -> dict:
    """KOSPI, KOSDAQ, 나스닥100(^NDX), S&P500(^GSPC) 지수 조회"""
    out: Dict[str, Dict[str, float]] = {}
    kospi_pk = _pykrx_index_snapshot(_PYKRX_KOSPI)
    kosdaq_pk = _pykrx_index_snapshot(_PYKRX_KOSDAQ)
    out["kospi"] = kospi_pk if kospi_pk else _yf_index_snapshot("^KS11")
    out["kosdaq"] = kosdaq_pk if kosdaq_pk else _yf_index_snapshot("^KQ11")
    for tick, name in _YF_INDEX_TICKERS:
        if name in ("kospi", "kosdaq"):
            continue
        out[name] = _yf_index_snapshot(tick)
    return out


def get_stock_data(ticker_yf: str, period: str = "1y") -> dict:
    """
    yfinance로 종목 데이터 수집
    반환: {name, ticker, market, price, volume, trading_value, high_52w, ...}
    """
    name = ALL_STOCKS.get(ticker_yf, ticker_yf)
    market = "KOSPI" if ticker_yf.endswith(".KS") else "KOSDAQ"
    krx_code = ticker_yf.split(".")[0]

    try:
        t = yf.Ticker(ticker_yf)
        hist = t.history(period=period)
        if hist.empty:
            return None

        hist = hist.dropna(subset=["Close"])
        if hist.empty:
            return None
        latest = hist.iloc[-1]
        price = float(latest["Close"])
        if pd.isna(price):
            return None
        volume = int(latest["Volume"]) if pd.notna(latest["Volume"]) else 0
        trading_value = int(price * volume)

        high_52w = float(hist["High"].max())
        drop_from_high = ((price - high_52w) / high_52w * 100) if high_52w > 0 else 0

        info = t.info or {}
        per = info.get("trailingPE", info.get("forwardPE", 0)) or 0
        pbr = info.get("priceToBook", 0) or 0
        div_yield = info.get("dividendYield", 0) or 0
        div_yield = div_yield * 100 if div_yield < 1 else div_yield
        market_cap = info.get("marketCap", 0) or 0
        eps = info.get("trailingEps", 0) or 0

        debt_ratio = info.get("debtToEquity", 0) or 0
        operating_margin = (info.get("operatingMargins", 0) or 0) * 100
        profit_margin = (info.get("profitMargins", 0) or 0) * 100
        revenue_growth = (info.get("revenueGrowth", 0) or 0) * 100
        roe = (info.get("returnOnEquity", 0) or 0) * 100
        current_ratio = info.get("currentRatio", 0) or 0

        spark = []
        recent = hist.tail(20)
        for _, row in recent.iterrows():
            c = float(row["Close"])
            if pd.notna(c):
                spark.append(round(c, 0))

        return {
            "ticker": krx_code,
            "ticker_yf": ticker_yf,
            "name": name,
            "market": market,
            "price": price,
            "volume": volume,
            "trading_value": trading_value,
            "market_cap": market_cap,
            "high_52w": high_52w,
            "drop_from_high_pct": round(drop_from_high, 2),
            "per": round(per, 2) if per else 0,
            "pbr": round(pbr, 2) if pbr else 0,
            "eps": round(eps, 2) if eps else 0,
            "div_yield": round(div_yield, 2) if div_yield else 0,
            "debt_ratio": round(debt_ratio, 1),
            "operating_margin": round(operating_margin, 1),
            "profit_margin": round(profit_margin, 1),
            "revenue_growth": round(revenue_growth, 1),
            "roe": round(roe, 1),
            "current_ratio": round(current_ratio, 2),
            "sparkline": spark,
        }
    except Exception as e:
        print(f"  [수집 실패] {name}: {e}")
        return None


def get_all_stock_data() -> list:
    """전체 종목 데이터 수집"""
    results = []
    total = len(ALL_STOCKS)
    for i, (ticker_yf, name) in enumerate(ALL_STOCKS.items(), 1):
        print(f"  [{i}/{total}] {name} 수집 중...", end="")
        data = get_stock_data(ticker_yf, period="1y")
        if data:
            results.append(data)
            print(f" ✓ {data['price']:,.0f}원")
        else:
            print(" ✗ 실패")
    return results
