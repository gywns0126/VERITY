"""
yfinance 기반 KOSPI/KOSDAQ 주가 데이터 수집기
pykrx가 KRX 접속 불가 시 yfinance를 주 데이터소스로 사용
"""
import pandas as pd
import yfinance as yf

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


def get_market_index() -> dict:
    """KOSPI, KOSDAQ 지수 조회"""
    result = {}
    for idx_ticker, name in [("^KS11", "kospi"), ("^KQ11", "kosdaq")]:
        try:
            t = yf.Ticker(idx_ticker)
            hist = t.history(period="2d")
            if len(hist) >= 2:
                today_close = float(hist["Close"].iloc[-1])
                prev_close = float(hist["Close"].iloc[-2])
                change_pct = ((today_close - prev_close) / prev_close) * 100
                result[name] = {
                    "value": round(today_close, 2),
                    "change_pct": round(change_pct, 2),
                }
            elif len(hist) == 1:
                result[name] = {
                    "value": round(float(hist["Close"].iloc[-1]), 2),
                    "change_pct": 0,
                }
            else:
                result[name] = {"value": 0, "change_pct": 0}
        except Exception:
            result[name] = {"value": 0, "change_pct": 0}
    return result


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
