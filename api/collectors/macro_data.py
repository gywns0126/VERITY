"""
매크로 경제 지표 수집 모듈
Alpha Vantage + yfinance로 금리, 환율, 유가, 공포지수 등 수집
"""
import requests
import yfinance as yf
from api.config import ALPHA_VANTAGE_KEY


def get_macro_indicators() -> dict:
    """주요 매크로 지표 수집"""
    result = {
        "usd_krw": _get_usd_krw(),
        "wti_oil": _get_commodity("CL=F", "WTI 원유"),
        "gold": _get_commodity("GC=F", "금"),
        "vix": _get_commodity("^VIX", "VIX 공포지수"),
        "us_10y": _get_commodity("^TNX", "미국 10년물"),
        "sp500": _get_index_change("^GSPC", "S&P500"),
        "nasdaq": _get_index_change("^IXIC", "나스닥"),
    }

    result["market_mood"] = _assess_market_mood(result)
    return result


def _get_usd_krw() -> dict:
    """USD/KRW 환율"""
    try:
        t = yf.Ticker("KRW=X")
        hist = t.history(period="5d")
        if len(hist) >= 2:
            current = float(hist["Close"].iloc[-1])
            prev = float(hist["Close"].iloc[-2])
            change = round(current - prev, 2)
            return {"value": round(current, 2), "change": change}
        elif len(hist) == 1:
            return {"value": round(float(hist["Close"].iloc[-1]), 2), "change": 0}
    except Exception:
        pass
    return {"value": 0, "change": 0}


def _get_commodity(ticker: str, name: str) -> dict:
    """원자재/지표 가격"""
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="5d")
        if len(hist) >= 2:
            current = float(hist["Close"].iloc[-1])
            prev = float(hist["Close"].iloc[-2])
            change_pct = round(((current - prev) / prev) * 100, 2)
            return {"value": round(current, 2), "change_pct": change_pct}
        elif len(hist) == 1:
            return {"value": round(float(hist["Close"].iloc[-1]), 2), "change_pct": 0}
    except Exception:
        pass
    return {"value": 0, "change_pct": 0}


def _get_index_change(ticker: str, name: str) -> dict:
    """해외 주요 지수 변동"""
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="5d")
        if len(hist) >= 2:
            current = float(hist["Close"].iloc[-1])
            prev = float(hist["Close"].iloc[-2])
            change_pct = round(((current - prev) / prev) * 100, 2)
            return {"value": round(current, 2), "change_pct": change_pct}
    except Exception:
        pass
    return {"value": 0, "change_pct": 0}


def _assess_market_mood(data: dict) -> dict:
    """매크로 지표 기반 시장 분위기 판단"""
    mood_score = 50

    vix = data.get("vix", {}).get("value", 0)
    if vix > 30:
        mood_score -= 20
    elif vix > 25:
        mood_score -= 10
    elif vix < 15:
        mood_score += 10
    elif vix < 20:
        mood_score += 5

    usd_change = data.get("usd_krw", {}).get("change", 0)
    if usd_change > 10:
        mood_score -= 10
    elif usd_change < -10:
        mood_score += 10

    sp500_chg = data.get("sp500", {}).get("change_pct", 0)
    if sp500_chg > 1:
        mood_score += 10
    elif sp500_chg < -1:
        mood_score -= 10

    us10y = data.get("us_10y", {}).get("change_pct", 0)
    if us10y > 3:
        mood_score -= 5
    elif us10y < -3:
        mood_score += 5

    mood_score = max(0, min(100, mood_score))

    if mood_score >= 65:
        label = "낙관"
    elif mood_score >= 45:
        label = "중립"
    else:
        label = "비관"

    return {"score": mood_score, "label": label}
