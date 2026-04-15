"""
국내 ETF 시세·수익률 수집 (pykrx)
  - 주요 ETF 시세 (종가, 등락률, 거래량)
  - 기간별 수익률 (1M / 3M / 1Y)
  - 카테고리 분류 (국내주식 / 해외주식 / 채권 / 원자재 / 레버리지·인버스)
"""
from datetime import timedelta
from typing import Any, Dict, List, Optional

from api.config import now_kst

_KR_TOP_ETFS = [
    ("069500", "KODEX 200", "equity_domestic"),
    ("229200", "KODEX 코스닥150", "equity_domestic"),
    ("102110", "TIGER 200", "equity_domestic"),
    ("371460", "TIGER 차이나전기차SOLACTIVE", "equity_foreign"),
    ("305720", "KODEX 2차전지산업", "thematic"),
    ("091160", "KODEX 반도체", "thematic"),
    ("381180", "TIGER 미국S&P500", "equity_foreign"),
    ("379800", "KODEX 미국S&P500TR", "equity_foreign"),
    ("379810", "KODEX 미국나스닥100TR", "equity_foreign"),
    ("133690", "TIGER 미국나스닥100", "equity_foreign"),
    ("148070", "KOSEF 국고채10년", "bond_kr"),
    ("152380", "KODEX 국고채3년", "bond_kr"),
    ("304660", "KODEX 미국채울트라30년선물(H)", "bond_us"),
    ("261240", "KODEX 미국채10년선물", "bond_us"),
    ("132030", "KODEX 골드선물(H)", "commodity"),
    ("130680", "TIGER 원유선물Enhanced(H)", "commodity"),
    ("122630", "KODEX 레버리지", "leverage"),
    ("252670", "KODEX 200선물인버스2X", "inverse"),
    ("114800", "KODEX 인버스", "inverse"),
    ("364690", "KODEX 은행", "sector"),
    ("091170", "KODEX 은행", "sector"),
    ("139260", "TIGER 200 IT", "sector"),
    ("117700", "KODEX 건설", "sector"),
    ("143860", "TIGER 헬스케어", "sector"),
    ("266370", "KODEX 배당성장", "dividend"),
]


def _pykrx_etf_ohlcv(ticker: str, days: int = 400) -> Optional[Dict[str, Any]]:
    """pykrx에서 ETF 일봉(OHLCV) 조회."""
    try:
        from pykrx import stock
    except ImportError:
        return None

    today = now_kst().date()
    start = today - timedelta(days=days)
    from_s = start.strftime("%Y%m%d")
    to_s = today.strftime("%Y%m%d")

    try:
        df = stock.get_etf_ohlcv_by_date(from_s, to_s, ticker)
        if df is None or df.empty:
            return None

        close_col = "종가" if "종가" in df.columns else "NAV"
        vol_col = "거래량" if "거래량" in df.columns else None

        if close_col not in df.columns:
            return None

        closes = df[close_col].dropna()
        if closes.empty:
            return None

        last_close = float(closes.iloc[-1])
        prev_close = float(closes.iloc[-2]) if len(closes) >= 2 else last_close
        change_pct = round((last_close - prev_close) / prev_close * 100, 2) if prev_close > 0 else 0.0

        volume = 0
        if vol_col and vol_col in df.columns:
            vol_series = df[vol_col].dropna()
            if not vol_series.empty:
                volume = int(vol_series.iloc[-1])

        returns: Dict[str, Optional[float]] = {}
        for label, trading_days in [("1M", 22), ("3M", 66), ("1Y", 252)]:
            if len(closes) > trading_days:
                ref = float(closes.iloc[-(trading_days + 1)])
                if ref > 0:
                    returns[label] = round((last_close - ref) / ref * 100, 2)
                else:
                    returns[label] = None
            else:
                returns[label] = None

        return {
            "close": last_close,
            "change_pct": change_pct,
            "volume": volume,
            "returns": returns,
        }
    except Exception:
        return None


def get_top_etf_summary() -> List[Dict[str, Any]]:
    """
    국내 주요 ETF 시세·수익률 요약.
    반환: [{ticker, name, category, close, change_pct, volume, returns: {1M, 3M, 1Y}, updated_at}, ...]
    """
    ts = now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00")
    results: List[Dict[str, Any]] = []
    seen_tickers: set = set()

    for ticker, name, category in _KR_TOP_ETFS:
        if ticker in seen_tickers:
            continue
        seen_tickers.add(ticker)

        data = _pykrx_etf_ohlcv(ticker)
        if data is None:
            continue

        results.append({
            "ticker": ticker,
            "name": name,
            "category": category,
            "close": data["close"],
            "change_pct": data["change_pct"],
            "volume": data["volume"],
            "returns": data["returns"],
            "updated_at": ts,
        })

    return results


if __name__ == "__main__":
    import json
    data = get_top_etf_summary()
    print(f"수집 ETF: {len(data)}개")
    print(json.dumps(data[:3], ensure_ascii=False, indent=2))
