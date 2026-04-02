"""
백테스팅 엔진 (Sprint 4)
- 과거 1년 데이터로 멀티팩터 전략 검증
- 매수/매도 시뮬레이션 후 승률/수익률/최대낙폭 계산
- 종목별 백테스트 결과를 portfolio.json에 포함
"""
import numpy as np
import pandas as pd
import yfinance as yf
from typing import Dict


def backtest_stock(ticker_yf: str, hold_days: int = 5, lookback: str = "1y") -> Dict:
    """
    단일 종목 백테스트
    전략: RSI ≤ 40 매수 → hold_days일 후 매도

    반환: win_rate, avg_return, max_drawdown, total_trades, sharpe_ratio
    """
    try:
        t = yf.Ticker(ticker_yf)
        df = t.history(period=lookback)
        if df.empty or len(df) < 60:
            return _empty_result()
    except Exception:
        return _empty_result()

    df = df.dropna(subset=["Close"])
    close = df["Close"]

    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    macd_hist = macd - signal

    ma20 = close.rolling(20).mean()
    ma60 = close.rolling(60).mean()

    trades = []
    last_exit = 0

    for i in range(60, len(close) - hold_days):
        if i < last_exit:
            continue

        r = rsi.iloc[i]
        mh = macd_hist.iloc[i]
        alignment = close.iloc[i] > ma20.iloc[i] if pd.notna(ma20.iloc[i]) else False

        buy_signal = False
        if pd.notna(r) and r <= 40:
            buy_signal = True
        if pd.notna(mh) and mh > 0 and alignment:
            buy_signal = True

        if buy_signal:
            entry_price = close.iloc[i]
            exit_price = close.iloc[i + hold_days]
            ret = (exit_price - entry_price) / entry_price * 100

            trades.append({
                "entry_date": str(df.index[i].date()),
                "exit_date": str(df.index[i + hold_days].date()),
                "entry_price": round(float(entry_price), 0),
                "exit_price": round(float(exit_price), 0),
                "return_pct": round(float(ret), 2),
                "win": ret > 0,
            })
            last_exit = i + hold_days

    if not trades:
        return _empty_result()

    returns = [t["return_pct"] for t in trades]
    wins = sum(1 for t in trades if t["win"])

    cumulative = []
    cum = 0
    peak = 0
    max_dd = 0
    for r in returns:
        cum += r
        cumulative.append(cum)
        peak = max(peak, cum)
        dd = peak - cum
        max_dd = max(max_dd, dd)

    avg_ret = np.mean(returns)
    std_ret = np.std(returns) if len(returns) > 1 else 1
    sharpe = (avg_ret / std_ret) * np.sqrt(252 / hold_days) if std_ret > 0 else 0

    return {
        "total_trades": len(trades),
        "win_count": wins,
        "loss_count": len(trades) - wins,
        "win_rate": round(wins / len(trades) * 100, 1),
        "avg_return": round(float(avg_ret), 2),
        "best_trade": round(float(max(returns)), 2),
        "worst_trade": round(float(min(returns)), 2),
        "total_return": round(float(sum(returns)), 2),
        "max_drawdown": round(float(max_dd), 2),
        "sharpe_ratio": round(float(sharpe), 2),
        "recent_trades": trades[-3:],
    }


def _empty_result() -> Dict:
    return {
        "total_trades": 0,
        "win_count": 0,
        "loss_count": 0,
        "win_rate": 0,
        "avg_return": 0,
        "best_trade": 0,
        "worst_trade": 0,
        "total_return": 0,
        "max_drawdown": 0,
        "sharpe_ratio": 0,
        "recent_trades": [],
    }
