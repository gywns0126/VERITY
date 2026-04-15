"""
VERITY 실시간 종목 분석 API
GET /api/stock?q=005930 또는 ?q=삼성전자

yfinance + 기술적분석 + 네이버 수급 + 안심점수를 한번에 반환.
Vercel Serverless 10초 제한 내 동작.
"""
from http.server import BaseHTTPRequestHandler
import json
import os
import re
import math
from urllib.parse import parse_qs, urlparse
from concurrent.futures import ThreadPoolExecutor

import requests
from bs4 import BeautifulSoup

from api.unlisted_exposure import get_unlisted_exposure

STOCKS_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "krx_stocks.json")
_stock_cache = None

US_STOCKS = [
    {"ticker": "AAPL", "name": "Apple", "name_kr": "애플", "market": "NASDAQ", "yf": "AAPL"},
    {"ticker": "MSFT", "name": "Microsoft", "name_kr": "마이크로소프트", "market": "NASDAQ", "yf": "MSFT"},
    {"ticker": "NVDA", "name": "NVIDIA", "name_kr": "엔비디아", "market": "NASDAQ", "yf": "NVDA"},
    {"ticker": "AMZN", "name": "Amazon", "name_kr": "아마존", "market": "NASDAQ", "yf": "AMZN"},
    {"ticker": "GOOGL", "name": "Alphabet Class A", "name_kr": "알파벳(구글)", "market": "NASDAQ", "yf": "GOOGL"},
    {"ticker": "GOOG", "name": "Alphabet Class C", "name_kr": "알파벳C", "market": "NASDAQ", "yf": "GOOG"},
    {"ticker": "META", "name": "Meta Platforms", "name_kr": "메타", "market": "NASDAQ", "yf": "META"},
    {"ticker": "TSLA", "name": "Tesla", "name_kr": "테슬라", "market": "NASDAQ", "yf": "TSLA"},
    {"ticker": "NFLX", "name": "Netflix", "name_kr": "넷플릭스", "market": "NASDAQ", "yf": "NFLX"},
    {"ticker": "AMD", "name": "Advanced Micro Devices", "name_kr": "AMD", "market": "NASDAQ", "yf": "AMD"},
    {"ticker": "AVGO", "name": "Broadcom", "name_kr": "브로드컴", "market": "NASDAQ", "yf": "AVGO"},
    {"ticker": "QCOM", "name": "Qualcomm", "name_kr": "퀄컴", "market": "NASDAQ", "yf": "QCOM"},
    {"ticker": "INTC", "name": "Intel", "name_kr": "인텔", "market": "NASDAQ", "yf": "INTC"},
    {"ticker": "CRM", "name": "Salesforce", "name_kr": "세일즈포스", "market": "NYSE", "yf": "CRM"},
    {"ticker": "ORCL", "name": "Oracle", "name_kr": "오라클", "market": "NYSE", "yf": "ORCL"},
    {"ticker": "ADBE", "name": "Adobe", "name_kr": "어도비", "market": "NASDAQ", "yf": "ADBE"},
    {"ticker": "PYPL", "name": "PayPal", "name_kr": "페이팔", "market": "NASDAQ", "yf": "PYPL"},
    {"ticker": "UBER", "name": "Uber Technologies", "name_kr": "우버", "market": "NYSE", "yf": "UBER"},
    {"ticker": "JPM", "name": "JPMorgan Chase", "name_kr": "JP모건", "market": "NYSE", "yf": "JPM"},
    {"ticker": "BAC", "name": "Bank of America", "name_kr": "뱅크오브아메리카", "market": "NYSE", "yf": "BAC"},
    {"ticker": "GS", "name": "Goldman Sachs", "name_kr": "골드만삭스", "market": "NYSE", "yf": "GS"},
    {"ticker": "V", "name": "Visa", "name_kr": "비자", "market": "NYSE", "yf": "V"},
    {"ticker": "MA", "name": "Mastercard", "name_kr": "마스터카드", "market": "NYSE", "yf": "MA"},
    {"ticker": "BRK-B", "name": "Berkshire Hathaway B", "name_kr": "버크셔해서웨이", "market": "NYSE", "yf": "BRK-B"},
    {"ticker": "UNH", "name": "UnitedHealth Group", "name_kr": "유나이티드헬스", "market": "NYSE", "yf": "UNH"},
    {"ticker": "JNJ", "name": "Johnson & Johnson", "name_kr": "존슨앤존슨", "market": "NYSE", "yf": "JNJ"},
    {"ticker": "PFE", "name": "Pfizer", "name_kr": "화이자", "market": "NYSE", "yf": "PFE"},
    {"ticker": "LLY", "name": "Eli Lilly", "name_kr": "일라이릴리", "market": "NYSE", "yf": "LLY"},
    {"ticker": "MRK", "name": "Merck", "name_kr": "머크", "market": "NYSE", "yf": "MRK"},
    {"ticker": "ABBV", "name": "AbbVie", "name_kr": "애브비", "market": "NYSE", "yf": "ABBV"},
    {"ticker": "XOM", "name": "Exxon Mobil", "name_kr": "엑슨모빌", "market": "NYSE", "yf": "XOM"},
    {"ticker": "CVX", "name": "Chevron", "name_kr": "셰브론", "market": "NYSE", "yf": "CVX"},
    {"ticker": "CAT", "name": "Caterpillar", "name_kr": "캐터필러", "market": "NYSE", "yf": "CAT"},
    {"ticker": "GE", "name": "GE Aerospace", "name_kr": "GE에어로스페이스", "market": "NYSE", "yf": "GE"},
    {"ticker": "BA", "name": "Boeing", "name_kr": "보잉", "market": "NYSE", "yf": "BA"},
    {"ticker": "DIS", "name": "Walt Disney", "name_kr": "디즈니", "market": "NYSE", "yf": "DIS"},
    {"ticker": "WMT", "name": "Walmart", "name_kr": "월마트", "market": "NYSE", "yf": "WMT"},
    {"ticker": "COST", "name": "Costco", "name_kr": "코스트코", "market": "NASDAQ", "yf": "COST"},
    {"ticker": "COIN", "name": "Coinbase", "name_kr": "코인베이스", "market": "NASDAQ", "yf": "COIN"},
    {"ticker": "SQ", "name": "Block (Square)", "name_kr": "블록(스퀘어)", "market": "NYSE", "yf": "SQ"},
    {"ticker": "SNOW", "name": "Snowflake", "name_kr": "스노우플레이크", "market": "NYSE", "yf": "SNOW"},
    {"ticker": "PLTR", "name": "Palantir", "name_kr": "팔란티어", "market": "NYSE", "yf": "PLTR"},
    {"ticker": "SOFI", "name": "SoFi Technologies", "name_kr": "소파이", "market": "NASDAQ", "yf": "SOFI"},
    {"ticker": "SHOP", "name": "Shopify", "name_kr": "쇼피파이", "market": "NYSE", "yf": "SHOP"},
    {"ticker": "ARM", "name": "ARM Holdings", "name_kr": "ARM", "market": "NASDAQ", "yf": "ARM"},
    {"ticker": "TSM", "name": "TSMC", "name_kr": "TSMC(대만반도체)", "market": "NYSE", "yf": "TSM"},
    {"ticker": "ASML", "name": "ASML Holding", "name_kr": "ASML", "market": "NASDAQ", "yf": "ASML"},
    {"ticker": "MU", "name": "Micron Technology", "name_kr": "마이크론", "market": "NASDAQ", "yf": "MU"},
    {"ticker": "MRVL", "name": "Marvell Technology", "name_kr": "마벨", "market": "NASDAQ", "yf": "MRVL"},
    {"ticker": "PANW", "name": "Palo Alto Networks", "name_kr": "팔로알토", "market": "NASDAQ", "yf": "PANW"},
    {"ticker": "CRWD", "name": "CrowdStrike", "name_kr": "크라우드스트라이크", "market": "NASDAQ", "yf": "CRWD"},
    {"ticker": "NOW", "name": "ServiceNow", "name_kr": "서비스나우", "market": "NYSE", "yf": "NOW"},
    {"ticker": "ABNB", "name": "Airbnb", "name_kr": "에어비앤비", "market": "NASDAQ", "yf": "ABNB"},
    {"ticker": "RIVN", "name": "Rivian", "name_kr": "리비안", "market": "NASDAQ", "yf": "RIVN"},
    {"ticker": "NIO", "name": "NIO", "name_kr": "니오", "market": "NYSE", "yf": "NIO"},
    {"ticker": "BABA", "name": "Alibaba", "name_kr": "알리바바", "market": "NYSE", "yf": "BABA"},
    {"ticker": "PDD", "name": "PDD Holdings", "name_kr": "핀둬둬", "market": "NASDAQ", "yf": "PDD"},
    {"ticker": "SPOT", "name": "Spotify", "name_kr": "스포티파이", "market": "NYSE", "yf": "SPOT"},
    {"ticker": "NET", "name": "Cloudflare", "name_kr": "클라우드플레어", "market": "NYSE", "yf": "NET"},
    {"ticker": "DDOG", "name": "Datadog", "name_kr": "데이터독", "market": "NASDAQ", "yf": "DDOG"},
    {"ticker": "ZS", "name": "Zscaler", "name_kr": "지스케일러", "market": "NASDAQ", "yf": "ZS"},
    {"ticker": "MSTR", "name": "MicroStrategy", "name_kr": "마이크로스트래티지", "market": "NASDAQ", "yf": "MSTR"},
    {"ticker": "HD", "name": "Home Depot", "name_kr": "홈디포", "market": "NYSE", "yf": "HD"},
    {"ticker": "NKE", "name": "Nike", "name_kr": "나이키", "market": "NYSE", "yf": "NKE"},
    {"ticker": "SBUX", "name": "Starbucks", "name_kr": "스타벅스", "market": "NASDAQ", "yf": "SBUX"},
    {"ticker": "MCD", "name": "McDonald's", "name_kr": "맥도날드", "market": "NYSE", "yf": "MCD"},
    {"ticker": "KO", "name": "Coca-Cola", "name_kr": "코카콜라", "market": "NYSE", "yf": "KO"},
    {"ticker": "PEP", "name": "PepsiCo", "name_kr": "펩시", "market": "NASDAQ", "yf": "PEP"},
    {"ticker": "PG", "name": "Procter & Gamble", "name_kr": "P&G", "market": "NYSE", "yf": "PG"},
    {"ticker": "T", "name": "AT&T", "name_kr": "AT&T", "market": "NYSE", "yf": "T"},
    {"ticker": "VZ", "name": "Verizon", "name_kr": "버라이즌", "market": "NYSE", "yf": "VZ"},
]


def _load_stocks():
    global _stock_cache
    if _stock_cache is None:
        try:
            with open(STOCKS_PATH, "r", encoding="utf-8") as f:
                _stock_cache = json.load(f)
        except Exception:
            _stock_cache = []
    return _stock_cache


def _is_us_symbol(q: str) -> bool:
    s = (q or "").strip().upper()
    return bool(re.fullmatch(r"[A-Z][A-Z0-9.-]{0,6}", s))


def _resolve_query(q: str, market_hint: str = "all"):
    """종목코드 또는 이름 → (ticker, ticker_yf, name, market) 반환"""
    q = q.strip()
    stocks = _load_stocks()
    us = US_STOCKS

    if q.isdigit() and len(q) == 6:
        for s in stocks:
            if s["ticker"] == q:
                return s["ticker"], s["yf"], s["name"], s["market"]
        suffix = ".KS"
        return q, f"{q}{suffix}", q, "KOSPI"

    q_lower = q.lower()
    q_upper = q.upper()

    if market_hint != "kr":
        for s in us:
            if s["ticker"] == q_upper:
                return s["ticker"], s["yf"], s["name"], s["market"]
        for s in us:
            kr = (s.get("name_kr") or "").lower()
            if s["name"].lower() == q_lower or q_lower in s["name"].lower():
                return s["ticker"], s["yf"], s["name"], s["market"]
            if kr and (kr == q_lower or q_lower in kr):
                return s["ticker"], s["yf"], s["name"], s["market"]
        if _is_us_symbol(q):
            return q_upper, q_upper, q_upper, "NASDAQ"
        if market_hint == "us":
            return None, None, None, None

    for s in stocks:
        if s["name"] == q or s["name"].lower() == q_lower:
            return s["ticker"], s["yf"], s["name"], s["market"]

    for s in stocks:
        if q_lower in s["name"].lower():
            return s["ticker"], s["yf"], s["name"], s["market"]

    return None, None, None, None


# ── yfinance 데이터 수집 ────────────────────────────────

_YF_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

def _fetch_chart_direct(ticker_yf: str):
    """Yahoo Finance chart API 직접 호출 (yfinance 우회, 단일 HTTP 요청)."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker_yf}?range=3mo&interval=1d&includePrePost=false"
    r = requests.get(url, headers=_YF_HEADERS, timeout=6)
    r.raise_for_status()
    data = r.json()
    result = data.get("chart", {}).get("result", [])
    if not result:
        return None, None
    chart = result[0]
    meta = chart.get("meta", {})
    indicators = chart.get("indicators", {}).get("quote", [{}])[0]
    timestamps = chart.get("timestamp", [])
    closes = indicators.get("close", [])
    volumes = indicators.get("volume", [])
    highs = indicators.get("high", [])
    return meta, list(zip(timestamps, closes, volumes, highs))


def _fetch_stock_data(ticker_yf: str, name: str, market: str):
    meta, ohlcv = _fetch_chart_direct(ticker_yf)
    if not meta or not ohlcv:
        return None

    valid = [(t, c, v, h) for t, c, v, h in ohlcv if c is not None]
    if not valid:
        return None

    closes = [c for _, c, _, _ in valid]
    volumes = [v or 0 for _, _, v, _ in valid]
    highs = [h or c for _, c, _, h in valid]

    price = closes[-1]
    volume = int(volumes[-1])
    trading_value = int(price * volume)
    high_period = max(highs)
    drop_from_high = ((price - high_period) / high_period * 100) if high_period > 0 else 0

    is_us = "." not in ticker_yf

    spark = [round(float(v), 2 if is_us else 0) for v in closes[-20:]]

    tech = _analyze_technical(closes, volumes, price)

    per = round(meta.get("trailingPE", 0) or 0, 2)

    return {
        "ticker": ticker_yf.split(".")[0],
        "ticker_yf": ticker_yf,
        "name": name,
        "market": market,
        "currency": "USD" if is_us else "KRW",
        "price": round(price, 2 if is_us else 0),
        "volume": volume,
        "trading_value": trading_value,
        "market_cap": meta.get("marketCap", 0) or 0,
        "high_52w": round(high_period, 0),
        "drop_from_high_pct": round(drop_from_high, 2),
        "per": per,
        "pbr": 0,
        "eps": 0,
        "div_yield": 0,
        "debt_ratio": 0,
        "operating_margin": 0,
        "profit_margin": 0,
        "revenue_growth": 0,
        "roe": 0,
        "current_ratio": 0,
        "sparkline": spark,
        "technical": tech,
    }


# ── 기술적 분석 (순수 Python, pandas/numpy 불필요) ────────

def _ma_list(closes: list, n: int) -> float:
    if len(closes) < n:
        return closes[-1] if closes else 0
    return sum(closes[-n:]) / n

def _ema_list(closes: list, span: int) -> list:
    k = 2 / (span + 1)
    ema = [closes[0]]
    for c in closes[1:]:
        ema.append(c * k + ema[-1] * (1 - k))
    return ema

def _calc_rsi(closes: list, period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0))
        losses.append(max(-d, 0))
    ag = sum(gains[:period]) / period
    al = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        ag = (ag * (period - 1) + gains[i]) / period
        al = (al * (period - 1) + losses[i]) / period
    if al == 0:
        return 100.0
    return round(100 - 100 / (1 + ag / al), 2)

def _analyze_technical(closes: list, volumes: list, price: float) -> dict:
    default = {"rsi": 50, "macd": 0, "macd_signal": 0, "macd_hist": 0,
               "bb_upper": 0, "bb_lower": 0, "bb_position": 50,
               "vol_ratio": 1.0, "vol_direction": "flat",
               "ma5": 0, "ma20": 0, "ma60": 0, "ma120": 0,
               "price": round(price, 2), "price_change_pct": 0,
               "trend_strength": 0, "signals": [], "technical_score": 50}
    if len(closes) < 5:
        return default

    ma5 = _ma_list(closes, 5)
    ma20 = _ma_list(closes, 20)
    ma60 = _ma_list(closes, 60)
    ma120 = _ma_list(closes, 120)
    rsi = _calc_rsi(closes) if len(closes) >= 15 else 50

    ema12 = _ema_list(closes, 12)
    ema26 = _ema_list(closes, 26)
    macd_line = [e12 - e26 for e12, e26 in zip(ema12, ema26)]
    signal_line = _ema_list(macd_line, 9)
    macd_val = round(macd_line[-1], 4)
    macd_sig = round(signal_line[-1], 4)
    macd_hist = round(macd_val - macd_sig, 4)

    if len(closes) >= 20:
        w = closes[-20:]
        mean20 = sum(w) / 20
        std20 = math.sqrt(sum((x - mean20) ** 2 for x in w) / 20)
        bb_upper = mean20 + 2 * std20
        bb_lower = mean20 - 2 * std20
    else:
        bb_upper, bb_lower = price * 1.05, price * 0.95
    bb_range = bb_upper - bb_lower
    bb_position = round((price - bb_lower) / bb_range * 100, 1) if bb_range > 0 else 50.0

    vol_today = float(volumes[-1]) if volumes else 0
    vol_avg = sum(volumes[-20:]) / min(len(volumes), 20) if volumes else 1
    vol_ratio = round(vol_today / vol_avg, 2) if vol_avg > 0 else 1.0

    price_change = round((closes[-1] - closes[-2]) / closes[-2] * 100, 2) if len(closes) >= 2 else 0
    vol_direction = "up" if price_change > 0.3 else "down" if price_change < -0.3 else "flat"

    trend_strength = 0
    if len(closes) >= 25:
        ma20_prev = _ma_list(closes[:-5], 20)
        slope = (ma20 - ma20_prev) / ma20 * 100 if ma20 > 0 else 0
        if slope > 1: trend_strength = 2
        elif slope > 0.3: trend_strength = 1
        elif slope < -1: trend_strength = -2
        elif slope < -0.3: trend_strength = -1

    signals, score = [], 50
    if price > ma20 > ma60: signals.append("정배열"); score += 10
    elif price < ma20 < ma60: signals.append("역배열"); score -= 10
    if rsi <= 30: signals.append(f"RSI 과매도({rsi})"); score += 15
    elif rsi <= 40: signals.append(f"RSI 저점접근({rsi})"); score += 8
    elif rsi >= 70: signals.append(f"RSI 과매수({rsi})"); score -= 10
    elif rsi >= 60: score += 3
    if macd_hist > 0 and macd_val > macd_sig: signals.append("MACD 매수시그널"); score += 10
    elif macd_hist < 0 and macd_val < macd_sig: signals.append("MACD 매도시그널"); score -= 8
    if bb_position <= 10: signals.append("볼린저 하단터치"); score += 12
    elif bb_position >= 90: signals.append("볼린저 상단터치"); score -= 5
    if vol_ratio >= 3.0:
        if vol_direction == "up": signals.append("거래폭증+상승"); score += 10
        elif vol_direction == "down": signals.append("거래폭증+하락"); score -= 8
    elif vol_ratio >= 1.5 and vol_direction == "up": signals.append("거래증가+상승"); score += 5
    if trend_strength >= 2: signals.append("강한 상승추세"); score += 5
    elif trend_strength <= -2: signals.append("강한 하락추세"); score -= 5

    return {
        "rsi": rsi, "macd": macd_val, "macd_signal": macd_sig, "macd_hist": macd_hist,
        "bb_upper": round(bb_upper, 0), "bb_lower": round(bb_lower, 0), "bb_position": bb_position,
        "vol_ratio": vol_ratio, "vol_direction": vol_direction,
        "ma5": round(ma5, 0), "ma20": round(ma20, 0), "ma60": round(ma60, 0), "ma120": round(ma120, 0),
        "price": round(price, 2), "price_change_pct": price_change,
        "trend_strength": trend_strength, "signals": signals, "technical_score": max(0, min(100, score)),
    }


# ── 수급 분석 (네이버 금융) ─────────────────────────────

def _fetch_flow_us(ticker_yf: str):
    """미장용 경량 수급 추정(가격·거래량 기반) — yfinance 미사용."""
    default = {"foreign_net": 0, "institution_net": 0, "foreign_5d_sum": 0,
               "institution_5d_sum": 0, "foreign_ratio": 0, "flow_signals": [], "flow_score": 50}
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker_yf}?range=1mo&interval=1d"
        r = requests.get(url, headers=_YF_HEADERS, timeout=4)
        r.raise_for_status()
        result = r.json().get("chart", {}).get("result", [])
        if not result:
            return default
        quotes = result[0].get("indicators", {}).get("quote", [{}])[0]
        closes = [c for c in (quotes.get("close") or []) if c is not None]
        vols = [v for v in (quotes.get("volume") or []) if v is not None]
        if len(closes) < 6:
            return default
        chg_5d = (closes[-1] - closes[-6]) / closes[-6] * 100
        vol_ratio = (sum(vols[-5:]) / 5) / (sum(vols[-20:]) / max(len(vols[-20:]), 1)) if len(vols) >= 20 else 1.0
        score = 50
        signals = []
        if chg_5d >= 3:
            score += 10; signals.append(f"5일 모멘텀 강세({chg_5d:+.1f}%)")
        elif chg_5d <= -3:
            score -= 10; signals.append(f"5일 모멘텀 약세({chg_5d:+.1f}%)")
        if vol_ratio >= 1.4:
            score += 6 if chg_5d >= 0 else -4; signals.append(f"거래량 확대({vol_ratio:.2f}x)")
        return {**default, "flow_signals": signals, "flow_score": max(0, min(100, int(round(score))))}
    except Exception:
        return default


def _fetch_flow(ticker: str, ticker_yf: str = "", is_us: bool = False):
    if is_us:
        return _fetch_flow_us(ticker_yf or ticker)
    try:
        url = "https://finance.naver.com/item/frgn.naver"
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, params={"code": ticker}, headers=headers, timeout=5)
        html = r.text

        vals = []
        for raw in re.findall(r'<td[^>]*class="num"[^>]*>([^<]*)</td>', html):
            c = raw.strip().replace(",", "").replace("+", "")
            if c and c.lstrip("-").isdigit():
                vals.append(int(c))

        fr_match = re.search(r'외국인한도소진율.*?<td[^>]*>([0-9.]+)%', html, re.DOTALL)
        foreign_ratio = float(fr_match.group(1)) if fr_match else 0

        fn = vals[4] if len(vals) > 4 else 0
        inst = vals[5] if len(vals) > 5 else 0
        f5 = [vals[i] for i in range(4, min(len(vals), 54), 10)][:5]
        i5 = [vals[i] for i in range(5, min(len(vals), 55), 10)][:5]

        score = 50
        signals = []
        if fn > 0: score += 8; signals.append(f"외국인 순매수({fn:+,}주)")
        elif fn < 0: score -= 8; signals.append(f"외국인 순매도({fn:+,}주)")
        if inst > 0: score += 8; signals.append(f"기관 순매수({inst:+,}주)")
        elif inst < 0: score -= 6; signals.append(f"기관 순매도({inst:+,}주)")
        if fn > 0 and inst > 0: score += 8; signals.append("외국인+기관 동반매수")

        return {
            "foreign_net": fn, "institution_net": inst,
            "foreign_5d_sum": sum(f5), "institution_5d_sum": sum(i5),
            "foreign_ratio": foreign_ratio, "flow_signals": signals,
            "flow_score": max(0, min(100, score)),
        }
    except Exception:
        return {"foreign_net": 0, "institution_net": 0, "foreign_5d_sum": 0,
                "institution_5d_sum": 0, "foreign_ratio": 0, "flow_signals": [],
                "flow_score": 50}


# ── 안심 점수 ───────────────────────────────────────────

def _safety_score(s: dict) -> int:
    score = 0
    per = s.get("per", 0)
    if 5 <= per <= 15: score += 20
    elif 15 < per <= 25: score += 12
    elif 0 < per <= 50: score += 5

    pbr = s.get("pbr", 0)
    if 0 < pbr <= 1.0: score += 15
    elif 1.0 < pbr <= 1.5: score += 10
    elif 1.5 < pbr <= 3.0: score += 5

    dy = s.get("div_yield", 0)
    if dy >= 3: score += 12
    elif dy >= 1: score += 7

    drop = s.get("drop_from_high_pct", 0)
    if drop <= -30: score += 15
    elif drop <= -20: score += 10
    elif drop <= -10: score += 5

    tv = s.get("trading_value", 0)
    is_us = s.get("currency") == "USD"
    if is_us:
        if tv >= 500_000_000: score += 12
        elif tv >= 100_000_000: score += 8
        elif tv >= 50_000_000: score += 4
    else:
        if tv >= 50e9: score += 12
        elif tv >= 10e9: score += 8
        elif tv >= 1e9: score += 4

    dr = s.get("debt_ratio", 0)
    if 0 < dr <= 30: score += 10
    elif 30 < dr <= 60: score += 6

    om = s.get("operating_margin", 0)
    if om >= 15: score += 10
    elif om >= 8: score += 6
    elif om >= 3: score += 3

    roe = s.get("roe", 0)
    if roe >= 15: score += 6
    elif roe >= 8: score += 4
    elif roe >= 3: score += 2

    return min(score, 100)


# ── 종합 판정 ───────────────────────────────────────────

def _judge(stock: dict) -> dict:
    ss = stock.get("safety_score", 0)
    ts = stock.get("technical", {}).get("technical_score", 50)
    fs = stock.get("flow", {}).get("flow_score", 50)
    multi = round(ss * 0.35 + ts * 0.35 + fs * 0.30)

    if multi >= 65:
        rec = "BUY"
    elif multi >= 45:
        rec = "WATCH"
    else:
        rec = "AVOID"

    grade = "S+" if multi >= 80 else "A" if multi >= 65 else "B" if multi >= 50 else "C" if multi >= 35 else "D"

    return {"multi_score": multi, "grade": grade, "recommendation": rec}


# ── 숫자 sanitize ──────────────────────────────────────

def _sanitize(obj):
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, int):
        return obj
    return obj


# ── HTTP Handler ────────────────────────────────────────

def _build_response(q: str, market_hint: str) -> tuple:
    """응답 body를 먼저 완성한 뒤 (body_str, is_success) 튜플로 반환."""
    if not q:
        return json.dumps({"error": "q 파라미터 필요 (종목코드 또는 이름)"}, ensure_ascii=False), False

    ticker, ticker_yf, name, market = _resolve_query(q, market_hint=market_hint)
    if not ticker:
        return json.dumps({"error": f"'{q}' 종목을 찾을 수 없습니다"}, ensure_ascii=False), False

    is_us = "." not in ticker_yf or market in ("NASDAQ", "NYSE", "AMEX")
    with ThreadPoolExecutor(max_workers=2) as pool:
        future_stock = pool.submit(_fetch_stock_data, ticker_yf, name, market)
        future_flow = pool.submit(_fetch_flow, ticker, ticker_yf, is_us)

        stock_data = future_stock.result(timeout=8)
        try:
            flow_data = future_flow.result(timeout=3)
        except Exception:
            flow_data = {"foreign_net": 0, "institution_net": 0, "foreign_5d_sum": 0,
                         "institution_5d_sum": 0, "foreign_ratio": 0, "flow_signals": [], "flow_score": 50}

    if not stock_data:
        return json.dumps({"error": f"'{name}' 데이터 수집 실패 (Yahoo Finance 응답 없음)"}, ensure_ascii=False), False

    stock_data["flow"] = flow_data
    stock_data["safety_score"] = _safety_score(stock_data)
    judgment = _judge(stock_data)
    stock_data["multi_factor"] = {"multi_score": judgment["multi_score"], "grade": judgment["grade"]}
    stock_data["recommendation"] = judgment["recommendation"]

    try:
        stock_data["unlisted_exposure"] = get_unlisted_exposure(ticker)
    except Exception:
        stock_data["unlisted_exposure"] = {"has_data": False, "total_count": 0, "total_stake_value_억": 0, "items": []}

    result = _sanitize(stock_data)
    return json.dumps(result, ensure_ascii=False), True


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        q = params.get("q", [""])[0]
        market_hint = params.get("market", ["all"])[0].strip().lower()

        body = json.dumps({"error": "처리 중 알 수 없는 오류"}, ensure_ascii=False)
        cache = "no-store"
        try:
            body, success = _build_response(q, market_hint)
            cache = "s-maxage=60, stale-while-revalidate=300" if success else "no-store"
        except Exception as e:
            body = json.dumps({"error": f"서버 오류: {str(e)[:200]}"}, ensure_ascii=False)
        finally:
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", cache)
            self.end_headers()
            self.wfile.write(body.encode("utf-8"))
