"""
백테스팅 엔진 (Sprint 4 + Brain V2)
- 과거 1년 데이터로 멀티팩터 전략 검증
- 매수/매도 시뮬레이션 후 승률/수익률/최대낙폭 계산
- 종목별 백테스트 결과를 portfolio.json에 포함
- Brain V2: 스냅샷 기반 가중치 재채점 백테스트
- Brain Audit §5: fact/sentiment 가중치 최적화 실험 (optimize_brain_weights)
"""
import json
import os
import statistics
from typing import Any, Dict, List, Optional, Tuple

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


# ── Brain Audit §5: fact / sentiment 가중치 최적화 ────────────
#
# 현재 verity_constitution.json 의 fact 0.70 / sentiment 0.30 이 실증적으로 최적인지
# 5가지 후보 조합으로 검증. 각 조합에 대해:
#   1) 등급별 평균 실현 수익률 (STRONG_BUY > BUY > ... 단조성 점검)
#   2) Precision@1 — 일자별 1위 종목의 hold_days 후 수익률
#   3) Grade 안정성 — 인접 일자 동일 종목의 등급 변동률
#
# 외부 호출 0회. data/history/YYYY-MM-DD.json 만 사용.

WEIGHT_COMBINATIONS: List[Dict[str, float]] = [
    {"fact": 0.60, "sentiment": 0.40},
    {"fact": 0.65, "sentiment": 0.35},
    {"fact": 0.70, "sentiment": 0.30},  # 현재값 (verity_constitution.json 기본)
    {"fact": 0.75, "sentiment": 0.25},
    {"fact": 0.80, "sentiment": 0.20},
]
CURRENT_WEIGHTS = {"fact": 0.70, "sentiment": 0.30}

# verity_brain.GRADE_ORDER 와 동일 (constitution decision_tree 기반)
_GRADE_THRESHOLDS = [("STRONG_BUY", 75), ("BUY", 60), ("WATCH", 45),
                     ("CAUTION", 30), ("AVOID", 0)]
_GRADE_ORDER = ["STRONG_BUY", "BUY", "WATCH", "CAUTION", "AVOID"]


def _score_to_grade(score: float) -> str:
    for g, thr in _GRADE_THRESHOLDS:
        if score >= thr:
            return g
    return "AVOID"


def _clip100(x: float) -> float:
    return max(0.0, min(100.0, x))


def _rescore_with_weights(stock: Dict[str, Any], w_fact: float, w_sent: float) -> Tuple[float, str]:
    """저장된 fact/sentiment 점수를 새 가중치로 결합 → (brain_score, grade).

    bonus / penalty 는 보존 (vci/candle/red_flag/inst_13f/gs_bonus 등).
    원래 brain_score 와 동일 공식이지만 fact/sent 항만 변동.
    """
    vb = stock.get("verity_brain") or {}
    fact = vb.get("fact_score") or {}
    sent = vb.get("sentiment_score") or {}
    try:
        fs = float(fact.get("score", 50))
        ss = float(sent.get("score", 50))
    except (TypeError, ValueError):
        fs, ss = 50.0, 50.0

    vci_b = float(vb.get("vci_bonus", 0) or 0)
    candle_b = float(vb.get("candle_bonus", 0) or 0)
    rf_pen = float(vb.get("red_flag_penalty", 0) or 0)
    # gs_bonus / inst_bonus 는 별도 필드로 분리되지 않음 — brain_score 잔차에서 역산
    base_bw = vb.get("brain_weights") or {}
    orig_wf = float(base_bw.get("fact", 0.7) or 0.7)
    orig_ws = float(base_bw.get("sentiment", 0.3) or 0.3)
    orig_brain = float(vb.get("brain_score", 0) or 0)
    # residual = brain_score - (fact*orig_wf + sent*orig_ws + vci_b + candle_b - rf_pen)
    # residual 은 gs_bonus + inst_bonus + clipping 손실 등 — 시나리오별 동일 적용 가정.
    residual = orig_brain - (fs * orig_wf + ss * orig_ws + vci_b + candle_b - rf_pen)

    new_score = _clip100(fs * w_fact + ss * w_sent + vci_b + candle_b - rf_pen + residual)
    return round(new_score, 2), _score_to_grade(new_score)


def _load_history_snapshots(lookback_days: int) -> List[Dict[str, Any]]:
    from api.workflows.archiver import load_snapshots_range
    return load_snapshots_range(lookback_days)


def _build_price_index(snapshots: List[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
    """{ticker: {date: price}} 인덱스. 후속 hold_days 가격 lookup 용."""
    idx: Dict[str, Dict[str, float]] = {}
    for snap in snapshots:
        d = snap.get("_date")
        if not d:
            continue
        for r in snap.get("recommendations") or []:
            t = r.get("ticker")
            p = r.get("price")
            if not t or p in (None, 0):
                continue
            try:
                idx.setdefault(t, {})[d] = float(p)
            except (TypeError, ValueError):
                continue
    return idx


def _future_price(price_idx: Dict[str, Dict[str, float]], ticker: str,
                  base_date: str, hold_days: int,
                  available_dates: List[str]) -> Optional[float]:
    """base_date 로부터 hold_days 영업일 이후 가격. 캘린더 기준 ±2일 허용."""
    try:
        base_idx = available_dates.index(base_date)
    except ValueError:
        return None
    for offset in range(hold_days, hold_days + 3):  # 주말 허용
        if base_idx + offset >= len(available_dates):
            break
        target = available_dates[base_idx + offset]
        p = price_idx.get(ticker, {}).get(target)
        if p:
            return p
    return None


def _evaluate_combo(
    snapshots: List[Dict[str, Any]],
    price_idx: Dict[str, Dict[str, float]],
    available_dates: List[str],
    w_fact: float,
    w_sent: float,
    hold_days: int,
) -> Dict[str, Any]:
    """단일 가중치 조합에 대한 3개 지표 산출."""
    grade_returns: Dict[str, List[float]] = {g: [] for g in _GRADE_ORDER}
    p1_returns: List[float] = []
    grade_changes = 0
    grade_pairs = 0
    prev_grades: Dict[str, str] = {}

    for snap in snapshots:
        d = snap.get("_date")
        if not d:
            continue
        # (1) 종목별 rescore + 등급별 future return 누적
        scored: List[Tuple[float, str, Dict[str, Any], Optional[float]]] = []
        cur_grades: Dict[str, str] = {}
        for stock in snap.get("recommendations") or []:
            tkr = stock.get("ticker")
            base_p = stock.get("price")
            if not tkr or not base_p:
                continue
            try:
                base_pf = float(base_p)
            except (TypeError, ValueError):
                continue
            score, grade = _rescore_with_weights(stock, w_fact, w_sent)
            cur_grades[tkr] = grade
            fut_p = _future_price(price_idx, tkr, d, hold_days, available_dates)
            ret_pct = ((fut_p - base_pf) / base_pf * 100) if (fut_p and base_pf) else None
            scored.append((score, grade, stock, ret_pct))
            if ret_pct is not None:
                grade_returns[grade].append(ret_pct)

        # (2) Precision@1 — 1위 종목 (현재 weight 기준 brain_score 최대) 의 future return
        if scored:
            top1 = max(scored, key=lambda x: x[0])
            if top1[3] is not None:
                p1_returns.append(top1[3])

        # (3) Grade 안정성 — 직전 일자 vs 오늘 동일 종목 비교
        for tkr, g in cur_grades.items():
            if tkr in prev_grades:
                grade_pairs += 1
                if prev_grades[tkr] != g:
                    grade_changes += 1
        prev_grades = cur_grades

    # 등급별 평균 + 단조성 검사
    grade_summary: Dict[str, Dict[str, float]] = {}
    grade_avg_list: List[Tuple[str, float]] = []  # (grade, avg) — STRONG_BUY 부터
    for g in _GRADE_ORDER:
        rets = grade_returns[g]
        if rets:
            avg = sum(rets) / len(rets)
            wr = sum(1 for r in rets if r > 0) / len(rets) * 100
            grade_summary[g] = {
                "n": len(rets),
                "avg_return_pct": round(avg, 3),
                "win_rate_pct": round(wr, 1),
            }
            grade_avg_list.append((g, avg))
        else:
            grade_summary[g] = {"n": 0, "avg_return_pct": None, "win_rate_pct": None}

    # 단조성: 인접 등급 쌍 중 (상위 등급 평균 ≥ 하위 등급 평균) 비율
    pairs = 0
    correct = 0
    for i in range(len(grade_avg_list) - 1):
        g_hi, avg_hi = grade_avg_list[i]
        g_lo, avg_lo = grade_avg_list[i + 1]
        pairs += 1
        if avg_hi >= avg_lo:
            correct += 1
    monotonicity = round(correct / pairs, 3) if pairs else None

    # Precision@1
    p1_avg = round(sum(p1_returns) / len(p1_returns), 3) if p1_returns else None
    p1_wr = round(sum(1 for r in p1_returns if r > 0) / len(p1_returns) * 100, 1) if p1_returns else None

    # Grade 안정성
    change_rate = round(grade_changes / grade_pairs, 3) if grade_pairs else None

    return {
        "weights": {"fact": w_fact, "sentiment": w_sent},
        "grade_returns": grade_summary,
        "monotonicity_score": monotonicity,
        "monotonicity_pairs": pairs,
        "precision_at_1": {
            "n_days": len(p1_returns),
            "avg_return_pct": p1_avg,
            "win_rate_pct": p1_wr,
        },
        "grade_stability": {
            "n_pairs": grade_pairs,
            "changes": grade_changes,
            "change_rate": change_rate,
        },
    }


def _select_best(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Precision@1 avg_return 기준 최적 — None 인 결과는 제외, 동률은 fact 가중치 큰 쪽."""
    candidates = [r for r in results if r["precision_at_1"]["avg_return_pct"] is not None]
    if not candidates:
        return results[0]
    return max(
        candidates,
        key=lambda r: (r["precision_at_1"]["avg_return_pct"], r["weights"]["fact"]),
    )


def _format_table(results: List[Dict[str, Any]]) -> str:
    """ASCII 표 출력."""
    lines = []
    hdr = "%-10s %-8s %-8s %-12s %-12s %-12s %s" % (
        "weights", "mono", "p@1_n", "p@1_avg%", "p@1_win%", "stab_chg%", "grade_avg(SB/B/W/C/A)")
    lines.append(hdr)
    lines.append("-" * len(hdr))
    for r in results:
        w = r["weights"]
        wstr = "%.2f/%.2f" % (w["fact"], w["sentiment"])
        mono = r["monotonicity_score"]
        mono_s = "%.2f" % mono if mono is not None else "  -"
        p1 = r["precision_at_1"]
        p1_n = p1["n_days"]
        p1_avg = ("%+6.3f" % p1["avg_return_pct"]) if p1["avg_return_pct"] is not None else "    -"
        p1_wr = ("%5.1f" % p1["win_rate_pct"]) if p1["win_rate_pct"] is not None else "   - "
        stab = r["grade_stability"]
        stab_chg = ("%5.1f" % (stab["change_rate"] * 100)) if stab["change_rate"] is not None else "   - "
        grade_avgs = []
        for g in _GRADE_ORDER:
            v = r["grade_returns"][g]["avg_return_pct"]
            grade_avgs.append("%+5.2f" % v if v is not None else "  -  ")
        lines.append("%-10s %-8s %-8d %-12s %-12s %-12s %s" % (
            wstr, mono_s, p1_n, p1_avg, p1_wr, stab_chg, "/".join(grade_avgs)))
    return "\n".join(lines)


def _is_same_weights(a: Dict[str, float], b: Dict[str, float]) -> bool:
    return abs(a["fact"] - b["fact"]) < 1e-6 and abs(a["sentiment"] - b["sentiment"]) < 1e-6


def _maybe_apply_to_constitution(best: Dict[str, float], confirm: bool) -> Dict[str, Any]:
    """constitution.json 의 brain_weights 업데이트. confirm=False 면 dry-run."""
    from api.config import DATA_DIR
    const_path = os.path.join(DATA_DIR, "verity_constitution.json")
    try:
        with open(const_path, "r", encoding="utf-8") as f:
            const = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        return {"applied": False, "error": f"constitution load failed: {e}"}

    bw = const.get("brain_weights") or {}
    cur = {"fact": float(bw.get("fact", 0.7)), "sentiment": float(bw.get("sentiment", 0.3))}

    if _is_same_weights(cur, best):
        return {"applied": False, "reason": "best == current", "current": cur}

    if not confirm:
        return {
            "applied": False, "reason": "confirm=False (dry-run)",
            "current": cur, "proposed": best,
            "diff_fact": round(best["fact"] - cur["fact"], 3),
            "diff_sentiment": round(best["sentiment"] - cur["sentiment"], 3),
        }

    # 실제 적용 (confirm=True 시에만)
    bw["fact"] = best["fact"]
    bw["sentiment"] = best["sentiment"]
    const["brain_weights"] = bw
    tmp = const_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(const, f, ensure_ascii=False, indent=2)
    os.replace(tmp, const_path)
    return {"applied": True, "previous": cur, "new": best}


def optimize_brain_weights(
    weight_combinations: Optional[List[Dict[str, float]]] = None,
    lookback_days: int = 30,
    hold_days: int = 3,
    output_path: Optional[str] = None,
    confirm_apply: bool = False,
) -> Dict[str, Any]:
    """fact/sentiment 가중치 최적화 실험.

    Args:
        weight_combinations: 후보 조합 (None = WEIGHT_COMBINATIONS 기본 5개).
        lookback_days: history snapshot 윈도우 (기본 30).
        hold_days: 미래 수익률 평가 holding 기간 (기본 3).
        output_path: 결과 JSON 저장 경로 (None = data/weight_optimization_result.json).
        confirm_apply: True 일 때만 constitution.json 자동 업데이트 허용.
                       False (기본) 면 dry-run — 변경 제안만 반환.

    Returns: 결과 dict (results, best_combo, should_update, apply_result).
    """
    from api.config import DATA_DIR, now_kst

    combos = weight_combinations or WEIGHT_COMBINATIONS
    snapshots = _load_history_snapshots(lookback_days)
    if len(snapshots) < hold_days + 2:
        return {
            "status": "insufficient_data",
            "snapshots_available": len(snapshots),
            "snapshots_required": hold_days + 2,
        }

    price_idx = _build_price_index(snapshots)
    available_dates = sorted({s.get("_date") for s in snapshots if s.get("_date")})

    results = []
    for c in combos:
        wf = float(c["fact"])
        ws = float(c["sentiment"])
        if abs(wf + ws - 1.0) > 1e-6:
            results.append({"weights": c, "error": "sum != 1.0"})
            continue
        r = _evaluate_combo(snapshots, price_idx, available_dates, wf, ws, hold_days)
        r["is_current"] = _is_same_weights(c, CURRENT_WEIGHTS)
        results.append(r)

    valid = [r for r in results if "error" not in r]
    best = _select_best(valid) if valid else None
    best_weights = best["weights"] if best else CURRENT_WEIGHTS

    apply_result = _maybe_apply_to_constitution(best_weights, confirm_apply) if best else None

    table = _format_table(valid)

    out = {
        "status": "ok",
        "generated_at": now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "config": {
            "weight_combinations": combos,
            "lookback_days": lookback_days,
            "hold_days": hold_days,
        },
        "data_window": {
            "snapshots_used": len(snapshots),
            "first_date": available_dates[0] if available_dates else None,
            "last_date": available_dates[-1] if available_dates else None,
        },
        "results": results,
        "best_combo": best_weights,
        "current_combo": CURRENT_WEIGHTS,
        "best_is_current": _is_same_weights(best_weights, CURRENT_WEIGHTS),
        "selection_metric": "precision_at_1.avg_return_pct",
        "apply_result": apply_result,
        "table_text": table,
    }

    out_path = output_path or os.path.join(DATA_DIR, "weight_optimization_result.json")
    tmp = out_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2, default=str)
    os.replace(tmp, out_path)

    return out
