"""
백테스팅 엔진 (Sprint 4 + Brain V2)
- 과거 1년 데이터로 멀티팩터 전략 검증
- 매수/매도 시뮬레이션 후 승률/수익률/최대낙폭 계산
- 종목별 백테스트 결과를 portfolio.json에 포함
- Brain V2: 스냅샷 기반 가중치 재채점 백테스트
"""
import json
import os
import statistics
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import yfinance as yf


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


# ── Brain V2: 스냅샷 기반 가중치 재채점 백테스트 ──────────

def _rescore_stock(stock: Dict[str, Any], override: Optional[Dict[str, Any]]) -> float:
    """주어진 가중치(override)로 단일 종목의 Brain Score를 재계산."""
    from api.config import DATA_DIR

    const_path = os.path.join(DATA_DIR, "verity_constitution.json")
    try:
        with open(const_path, "r", encoding="utf-8") as f:
            const = json.load(f)
    except Exception:
        const = {}

    fact_w = dict(const.get("fact_score", {}).get("weights", {}))
    sent_w = dict(const.get("sentiment_score", {}).get("weights", {}))
    grade_map = {}
    for g, v in const.get("decision_tree", {}).get("grades", {}).items():
        grade_map[g] = v.get("min_brain_score", 0)

    if override:
        if override.get("fact_score_weights"):
            fact_w.update(override["fact_score_weights"])
        if override.get("sentiment_score_weights"):
            sent_w.update(override["sentiment_score_weights"])
        if override.get("grade_thresholds"):
            grade_map.update(override["grade_thresholds"])

    def _clip(x: float) -> float:
        return max(0.0, min(100.0, x))

    mf = stock.get("multi_factor", {}).get("multi_score", 50)
    cons = stock.get("consensus", {}).get("consensus_score", 50)
    if isinstance(cons, str):
        try:
            cons = float(cons)
        except (ValueError, TypeError):
            cons = 50
    pred_up = stock.get("prediction", {}).get("up_probability", 50)
    bt = stock.get("backtest", {})
    bt_score = 50.0
    if bt.get("total_trades", 0) > 0:
        bt_score = _clip(bt.get("win_rate", 50) * 0.6 + min(bt.get("sharpe_ratio", 0) * 10, 40))
    timing = stock.get("timing", {}).get("timing_score", 50)
    cm = stock.get("commodity_margin", {})
    cm_score = 50.0
    if isinstance(cm, dict):
        pr = cm.get("primary", {}) or {}
        cm_score = _clip(pr.get("margin_safety_score", 50))
    export_score = 50.0

    fact = _clip(
        mf * fact_w.get("multi_factor", 0.30)
        + cons * fact_w.get("consensus", 0.20)
        + pred_up * fact_w.get("prediction", 0.15)
        + bt_score * fact_w.get("backtest", 0.10)
        + timing * fact_w.get("timing", 0.10)
        + cm_score * fact_w.get("commodity_margin", 0.05)
        + export_score * fact_w.get("export_trade", 0.10)
    )

    news = stock.get("sentiment", {}).get("score", 50)
    x_sent = 50.0
    mood = 50.0
    cons_op = 50.0

    sent = _clip(
        news * sent_w.get("news_sentiment", 0.35)
        + x_sent * sent_w.get("x_sentiment", 0.25)
        + mood * sent_w.get("market_mood", 0.25)
        + cons_op * sent_w.get("consensus_opinion", 0.15)
    )

    vci = fact - sent
    vci_bonus = 0
    if vci > 25 and fact >= 60:
        vci_bonus = 5
    elif vci < -25 and fact < 50:
        vci_bonus = -10

    brain_score = _clip(fact * 0.7 + sent * 0.3 + vci_bonus)
    return brain_score


def backtest_brain_strategy(
    override: Optional[Dict[str, Any]] = None,
    lookback_days: int = 30,
    hold_days: int = 7,
) -> Dict[str, Any]:
    """
    과거 스냅샷의 recommendations를 주어진 가중치로 재채점하여
    BUY 판정 종목의 실제 수익률을 추적. 기대값 E, Sharpe, 적중률 산출.
    """
    from api.workflows.archiver import load_snapshots_range

    snapshots = load_snapshots_range(lookback_days)
    if len(snapshots) < 2:
        return {"sharpe": 0, "hit_rate": 0, "expected_value": 0, "total_trades": 0, "note": "데이터 부족"}

    trades: List[Dict[str, Any]] = []
    buy_threshold = 60

    if override and override.get("grade_thresholds"):
        buy_threshold = override["grade_thresholds"].get("BUY", 60)

    for i in range(len(snapshots) - 1):
        snap = snapshots[i]
        snap_date = snap.get("_date", "?")
        recs = snap.get("recommendations", [])

        future_snap = None
        for j in range(i + 1, min(i + hold_days + 1, len(snapshots))):
            future_snap = snapshots[j]
        if not future_snap:
            continue

        future_prices: Dict[str, float] = {}
        for r in future_snap.get("recommendations", []):
            t = r.get("ticker", "")
            p = r.get("price")
            if t and p:
                try:
                    future_prices[t] = float(p)
                except (TypeError, ValueError):
                    pass

        for stock in recs:
            ticker = stock.get("ticker", "")
            price = stock.get("price")
            if not ticker or not price:
                continue
            try:
                price = float(price)
            except (TypeError, ValueError):
                continue

            brain_score = _rescore_stock(stock, override)

            if brain_score >= buy_threshold:
                future_price = future_prices.get(ticker)
                if future_price is None or future_price <= 0:
                    continue

                ret = round((future_price - price) / price * 100, 2)
                trades.append({
                    "ticker": ticker,
                    "name": stock.get("name", "?"),
                    "date": snap_date,
                    "brain_score": round(brain_score, 1),
                    "entry_price": price,
                    "exit_price": future_price,
                    "return_pct": ret,
                    "win": ret > 0,
                })

    if not trades:
        return {"sharpe": 0, "hit_rate": 0, "expected_value": 0, "total_trades": 0, "note": "매매 시그널 없음"}

    returns = [t["return_pct"] for t in trades]
    wins = sum(1 for t in trades if t["win"])
    losses = len(trades) - wins
    win_rate = round(wins / len(trades) * 100, 1)

    avg_win = statistics.mean([r for r in returns if r > 0]) if wins > 0 else 0
    avg_loss = abs(statistics.mean([r for r in returns if r <= 0])) if losses > 0 else 0
    pw = wins / len(trades) if trades else 0
    pl = losses / len(trades) if trades else 0
    expected_value = round(pw * avg_win - pl * avg_loss, 2)

    avg_ret = statistics.mean(returns)
    std_ret = statistics.stdev(returns) if len(returns) >= 2 else 1
    sharpe = round((avg_ret / std_ret) * (252 / hold_days) ** 0.5, 2) if std_ret > 0 else 0

    cum = 0
    peak = 0
    max_dd = 0
    for r in returns:
        cum += r
        peak = max(peak, cum)
        max_dd = max(max_dd, peak - cum)

    return {
        "sharpe": sharpe,
        "hit_rate": win_rate,
        "expected_value": expected_value,
        "total_trades": len(trades),
        "avg_return": round(avg_ret, 2),
        "max_drawdown": round(max_dd, 2),
        "win_count": wins,
        "loss_count": losses,
    }
