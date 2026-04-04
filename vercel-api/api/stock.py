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
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd
import yfinance as yf
import requests
from bs4 import BeautifulSoup

STOCKS_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "krx_stocks.json")
_stock_cache = None


def _load_stocks():
    global _stock_cache
    if _stock_cache is None:
        with open(STOCKS_PATH, "r", encoding="utf-8") as f:
            _stock_cache = json.load(f)
    return _stock_cache


def _resolve_query(q: str):
    """종목코드 또는 이름 → (ticker, ticker_yf, name, market) 반환"""
    q = q.strip()
    stocks = _load_stocks()

    if q.isdigit() and len(q) == 6:
        for s in stocks:
            if s["ticker"] == q:
                return s["ticker"], s["yf"], s["name"], s["market"]
        suffix = ".KS"
        return q, f"{q}{suffix}", q, "KOSPI"

    q_lower = q.lower()
    for s in stocks:
        if s["name"] == q or s["name"].lower() == q_lower:
            return s["ticker"], s["yf"], s["name"], s["market"]

    for s in stocks:
        if q_lower in s["name"].lower():
            return s["ticker"], s["yf"], s["name"], s["market"]

    return None, None, None, None


# ── yfinance 데이터 수집 ────────────────────────────────

def _fetch_stock_data(ticker_yf: str, name: str, market: str):
    t = yf.Ticker(ticker_yf)
    hist = t.history(period="1y")
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
    op_margin = (info.get("operatingMargins", 0) or 0) * 100
    profit_margin = (info.get("profitMargins", 0) or 0) * 100
    revenue_growth = (info.get("revenueGrowth", 0) or 0) * 100
    roe = (info.get("returnOnEquity", 0) or 0) * 100
    current_ratio = info.get("currentRatio", 0) or 0

    spark = [round(float(v), 0) for v in hist.tail(20)["Close"].dropna().tolist()]

    close = hist["Close"].dropna()
    tech = _analyze_technical(close, hist["Volume"].dropna(), price)

    return {
        "ticker": ticker_yf.split(".")[0],
        "ticker_yf": ticker_yf,
        "name": name,
        "market": market,
        "price": round(price, 0),
        "volume": volume,
        "trading_value": trading_value,
        "market_cap": market_cap,
        "high_52w": round(high_52w, 0),
        "drop_from_high_pct": round(drop_from_high, 2),
        "per": round(per, 2) if per else 0,
        "pbr": round(pbr, 2) if pbr else 0,
        "eps": round(eps, 2) if eps else 0,
        "div_yield": round(div_yield, 2) if div_yield else 0,
        "debt_ratio": round(debt_ratio, 1),
        "operating_margin": round(op_margin, 1),
        "profit_margin": round(profit_margin, 1),
        "revenue_growth": round(revenue_growth, 1),
        "roe": round(roe, 1),
        "current_ratio": round(current_ratio, 2),
        "sparkline": spark,
        "technical": tech,
    }


# ── 기술적 분석 (yfinance 데이터에서 직접 계산) ────────

def _calc_rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    first_avg_gain = gain.iloc[1:period + 1].mean()
    first_avg_loss = loss.iloc[1:period + 1].mean()
    avg_gains = [first_avg_gain]
    avg_losses = [first_avg_loss]
    for i in range(period + 1, len(series)):
        ag = (avg_gains[-1] * (period - 1) + gain.iloc[i]) / period
        al = (avg_losses[-1] * (period - 1) + loss.iloc[i]) / period
        avg_gains.append(ag)
        avg_losses.append(al)
    if not avg_gains or avg_losses[-1] == 0:
        return 50.0
    rs = avg_gains[-1] / avg_losses[-1] if avg_losses[-1] != 0 else 100
    rsi = 100 - (100 / (1 + rs))
    return round(float(rsi), 2) if pd.notna(rsi) else 50.0


def _analyze_technical(close, volume, price):
    if len(close) < 5:
        return {"rsi": 50, "macd_hist": 0, "bb_position": 50, "vol_ratio": 1.0,
                "signals": [], "technical_score": 50, "trend_strength": 0,
                "ma20": 0, "ma60": 0, "price_change_pct": 0}

    def _ma(n):
        if len(close) < n:
            return price
        v = close.rolling(n).mean().iloc[-1]
        return float(v) if pd.notna(v) else price

    ma5, ma20, ma60, ma120 = _ma(5), _ma(20), _ma(60), _ma(120)
    rsi = _calc_rsi(close) if len(close) >= 15 else 50

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    macd_hist = round(float((macd_line - signal_line).iloc[-1]), 2)
    macd_val = round(float(macd_line.iloc[-1]), 2)
    macd_sig = round(float(signal_line.iloc[-1]), 2)

    bb_mid = close.rolling(20).mean()
    bb_std = close.rolling(20).std()
    bb_upper = float((bb_mid + 2 * bb_std).iloc[-1]) if len(close) >= 20 else price * 1.05
    bb_lower = float((bb_mid - 2 * bb_std).iloc[-1]) if len(close) >= 20 else price * 0.95
    bb_range = bb_upper - bb_lower
    bb_position = round((price - bb_lower) / bb_range * 100, 1) if bb_range > 0 else 50.0

    vol_avg20 = float(volume.rolling(20).mean().iloc[-1]) if len(volume) >= 20 else float(volume.mean())
    vol_today = float(volume.iloc[-1])
    vol_ratio = round(vol_today / vol_avg20, 2) if vol_avg20 > 0 else 1.0

    price_change = round(float((close.iloc[-1] - close.iloc[-2]) / close.iloc[-2] * 100), 2) if len(close) >= 2 else 0
    vol_direction = "up" if price_change > 0.3 else "down" if price_change < -0.3 else "flat"

    trend_strength = 0
    if len(close) >= 20:
        ma20_slope = (ma20 - float(close.rolling(20).mean().iloc[-5])) / ma20 * 100 if ma20 > 0 else 0
        if ma20_slope > 1: trend_strength = 2
        elif ma20_slope > 0.3: trend_strength = 1
        elif ma20_slope < -1: trend_strength = -2
        elif ma20_slope < -0.3: trend_strength = -1

    signals = []
    score = 50

    if price > ma20 > ma60:
        signals.append("정배열"); score += 10
    elif price < ma20 < ma60:
        signals.append("역배열"); score -= 10

    if rsi <= 30: signals.append(f"RSI 과매도({rsi})"); score += 15
    elif rsi <= 40: signals.append(f"RSI 저점접근({rsi})"); score += 8
    elif rsi >= 70: signals.append(f"RSI 과매수({rsi})"); score -= 10
    elif rsi >= 60: score += 3

    if macd_hist > 0 and macd_val > macd_sig:
        signals.append("MACD 매수시그널"); score += 10
    elif macd_hist < 0 and macd_val < macd_sig:
        signals.append("MACD 매도시그널"); score -= 8

    if bb_position <= 10: signals.append("볼린저 하단터치"); score += 12
    elif bb_position >= 90: signals.append("볼린저 상단터치"); score -= 5

    if vol_ratio >= 3.0:
        if vol_direction == "up": signals.append("거래폭증+상승"); score += 10
        elif vol_direction == "down": signals.append("거래폭증+하락"); score -= 8
    elif vol_ratio >= 1.5 and vol_direction == "up":
        signals.append("거래증가+상승"); score += 5

    if trend_strength >= 2: signals.append("강한 상승추세"); score += 5
    elif trend_strength <= -2: signals.append("강한 하락추세"); score -= 5

    score = max(0, min(100, score))

    return {
        "rsi": rsi, "macd": macd_val, "macd_signal": macd_sig, "macd_hist": macd_hist,
        "bb_upper": round(bb_upper, 0), "bb_lower": round(bb_lower, 0), "bb_position": bb_position,
        "vol_ratio": vol_ratio, "vol_direction": vol_direction,
        "ma5": round(ma5, 0), "ma20": round(ma20, 0), "ma60": round(ma60, 0), "ma120": round(ma120, 0),
        "price": round(price, 0), "price_change_pct": price_change,
        "trend_strength": trend_strength, "signals": signals, "technical_score": score,
    }


# ── 수급 분석 (네이버 금융) ─────────────────────────────

def _fetch_flow(ticker: str):
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
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        v = float(obj)
        return None if math.isnan(v) or math.isinf(v) else v
    return obj


# ── HTTP Handler ────────────────────────────────────────

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

        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "s-maxage=60, stale-while-revalidate=300")
        self.end_headers()

        if not q:
            self.wfile.write(json.dumps({"error": "q 파라미터 필요 (종목코드 또는 이름)"}, ensure_ascii=False).encode())
            return

        ticker, ticker_yf, name, market = _resolve_query(q)
        if not ticker:
            self.wfile.write(json.dumps({"error": f"'{q}' 종목을 찾을 수 없습니다"}, ensure_ascii=False).encode())
            return

        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                future_stock = pool.submit(_fetch_stock_data, ticker_yf, name, market)
                future_flow = pool.submit(_fetch_flow, ticker)

                stock_data = future_stock.result(timeout=8)
                flow_data = future_flow.result(timeout=8)

            if not stock_data:
                self.wfile.write(json.dumps({"error": f"'{name}' 데이터 수집 실패"}, ensure_ascii=False).encode())
                return

            stock_data["flow"] = flow_data
            stock_data["safety_score"] = _safety_score(stock_data)
            judgment = _judge(stock_data)
            stock_data["multi_factor"] = {"multi_score": judgment["multi_score"], "grade": judgment["grade"]}
            stock_data["recommendation"] = judgment["recommendation"]

            result = _sanitize(stock_data)
            self.wfile.write(json.dumps(result, ensure_ascii=False).encode())

        except Exception as e:
            self.wfile.write(json.dumps({"error": str(e)[:100]}, ensure_ascii=False).encode())
