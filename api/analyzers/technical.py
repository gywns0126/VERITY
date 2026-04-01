"""
기술적 지표 분석 엔진
yfinance 히스토리 데이터로 MA, RSI, MACD, 볼린저밴드, 거래량 추세 계산
"""
import numpy as np
import pandas as pd
import yfinance as yf


def _calc_rsi(series: pd.Series, period: int = 14) -> float:
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    val = rsi.iloc[-1]
    return round(float(val), 2) if pd.notna(val) else 50.0


def _calc_macd(series: pd.Series):
    ema12 = series.ewm(span=12, adjust=False).mean()
    ema26 = series.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    histogram = macd_line - signal_line
    return (
        round(float(macd_line.iloc[-1]), 2),
        round(float(signal_line.iloc[-1]), 2),
        round(float(histogram.iloc[-1]), 2),
    )


def analyze_technical(ticker_yf: str) -> dict:
    """
    종목의 기술적 지표 분석
    반환:
      ma5, ma20, ma60, ma120, rsi, macd, macd_signal, macd_hist,
      bb_upper, bb_lower, bb_position,
      vol_ratio, signals[], technical_score (0~100)
    """
    try:
        t = yf.Ticker(ticker_yf)
        hist = t.history(period="1y")
        if hist.empty or len(hist) < 20:
            return _empty_result()
    except Exception:
        return _empty_result()

    close = hist["Close"].dropna()
    volume = hist["Volume"].dropna()

    if len(close) < 5:
        return _empty_result()

    price = float(close.iloc[-1])

    def _safe_ma(n):
        if len(close) < n:
            return price
        val = close.rolling(n).mean().iloc[-1]
        return float(val) if pd.notna(val) else price

    ma5 = _safe_ma(5)
    ma20 = _safe_ma(20)
    ma60 = _safe_ma(60)
    ma120 = _safe_ma(120)

    rsi = _calc_rsi(close)
    macd_val, macd_sig, macd_hist = _calc_macd(close)

    bb_mid = close.rolling(20).mean()
    bb_std = close.rolling(20).std()
    bb_u_val = (bb_mid + 2 * bb_std).iloc[-1]
    bb_l_val = (bb_mid - 2 * bb_std).iloc[-1]
    bb_upper = float(bb_u_val) if pd.notna(bb_u_val) else price * 1.05
    bb_lower = float(bb_l_val) if pd.notna(bb_l_val) else price * 0.95
    bb_range = bb_upper - bb_lower
    bb_position = round((price - bb_lower) / bb_range * 100, 1) if bb_range > 0 else 50.0

    vol_avg20 = float(volume.rolling(20).mean().iloc[-1])
    vol_today = float(volume.iloc[-1])
    vol_ratio = round(vol_today / vol_avg20, 2) if vol_avg20 > 0 else 1.0

    signals = []
    score = 50

    # MA 배열 분석
    if price > ma20 > ma60:
        signals.append("정배열")
        score += 10
    elif price < ma20 < ma60:
        signals.append("역배열")
        score -= 10

    if len(close) >= 20:
        prev_ma5 = close.rolling(5).mean().iloc[-2]
        prev_ma20 = close.rolling(20).mean().iloc[-2]
        if pd.notna(prev_ma5) and pd.notna(prev_ma20):
            if ma5 > ma20 and float(prev_ma5) <= float(prev_ma20):
                signals.append("골든크로스(5/20)")
                score += 15

    # RSI
    if rsi <= 30:
        signals.append("RSI 과매도")
        score += 15
    elif rsi <= 40:
        signals.append("RSI 저점 접근")
        score += 8
    elif rsi >= 70:
        signals.append("RSI 과매수")
        score -= 10
    elif rsi >= 60:
        score += 3

    # MACD
    if macd_hist > 0 and macd_val > macd_sig:
        signals.append("MACD 매수 시그널")
        score += 10
    elif macd_hist < 0 and macd_val < macd_sig:
        signals.append("MACD 매도 시그널")
        score -= 8

    # 볼린저밴드
    if bb_position <= 10:
        signals.append("볼린저 하단 터치")
        score += 12
    elif bb_position >= 90:
        signals.append("볼린저 상단 터치")
        score -= 5

    # 거래량 폭증
    if vol_ratio >= 3.0:
        signals.append("거래량 폭증")
        score += 5
    elif vol_ratio >= 1.5:
        signals.append("거래량 증가")
        score += 3

    score = max(0, min(100, score))

    return {
        "price": round(price, 0),
        "ma5": round(ma5, 0),
        "ma20": round(ma20, 0),
        "ma60": round(ma60, 0),
        "ma120": round(ma120, 0),
        "rsi": rsi,
        "macd": macd_val,
        "macd_signal": macd_sig,
        "macd_hist": macd_hist,
        "bb_upper": round(bb_upper, 0),
        "bb_lower": round(bb_lower, 0),
        "bb_position": bb_position,
        "vol_ratio": vol_ratio,
        "signals": signals,
        "technical_score": score,
    }


def _empty_result() -> dict:
    return {
        "price": 0, "ma5": 0, "ma20": 0, "ma60": 0, "ma120": 0,
        "rsi": 50, "macd": 0, "macd_signal": 0, "macd_hist": 0,
        "bb_upper": 0, "bb_lower": 0, "bb_position": 50,
        "vol_ratio": 1.0, "signals": [], "technical_score": 50,
    }
