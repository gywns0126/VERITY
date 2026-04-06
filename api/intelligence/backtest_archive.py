"""
백테스트 아카이브 — 추천 스냅샷 저장 + 7/14/30일 후 성과 추적.
history/ 스냅샷의 recommendations[]를 비교하여 적중률·수익률을 산출.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import timedelta
from typing import Any, Dict, List, Optional

from api.config import DATA_DIR, now_kst
from api.workflows.archiver import load_snapshot, list_available_dates

logger = logging.getLogger(__name__)

BACKTEST_PATH = os.path.join(DATA_DIR, "backtest_stats.json")


def _load_existing_stats() -> Dict[str, Any]:
    if os.path.exists(BACKTEST_PATH):
        try:
            with open(BACKTEST_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_stats(stats: Dict[str, Any]):
    with open(BACKTEST_PATH, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2, default=str)


def _get_price_map_from_snapshot(snap: dict) -> Dict[str, float]:
    """스냅샷에서 ticker → price 맵 추출."""
    prices: Dict[str, float] = {}
    for r in snap.get("recommendations", []):
        ticker = r.get("ticker", "")
        price = r.get("price") or r.get("current_price")
        if ticker and price:
            try:
                prices[ticker] = float(price)
            except (TypeError, ValueError):
                pass
    for h in snap.get("vams", {}).get("holdings", []):
        ticker = h.get("ticker", "")
        price = h.get("current_price") or h.get("price")
        if ticker and price:
            try:
                prices[ticker] = float(price)
            except (TypeError, ValueError):
                pass
    return prices


def evaluate_past_recommendations(
    lookback_days: List[int] = None,
) -> Dict[str, Any]:
    """
    과거 추천 종목의 성과를 추적.

    lookback_days: 비교 기간 (기본 [7, 14, 30])
    Returns: {
        "periods": {
            "7d": {hit_rate, avg_return, total_recs, ...},
            "14d": {...},
            "30d": {...},
        },
        "recommendations": [{ticker, name, rec_date, rec_price, ...}],
        "updated_at": "...",
    }
    """
    if lookback_days is None:
        lookback_days = [7, 14, 30]

    dates = list_available_dates()
    if len(dates) < 2:
        return {"periods": {}, "recommendations": [], "updated_at": str(now_kst())}

    today = now_kst().date()
    today_str = today.strftime("%Y-%m-%d")
    today_snap = load_snapshot(today_str)
    if not today_snap:
        if dates:
            today_snap = load_snapshot(dates[-1])
            today_str = dates[-1]
    if not today_snap:
        return {"periods": {}, "recommendations": [], "updated_at": str(now_kst())}

    current_prices = _get_price_map_from_snapshot(today_snap)

    period_stats: Dict[str, Dict[str, Any]] = {}
    all_recs: List[Dict[str, Any]] = []

    for days in lookback_days:
        target_date = (today - timedelta(days=days)).strftime("%Y-%m-%d")
        past_snap = _find_nearest_snapshot(target_date, dates)
        if not past_snap:
            period_stats[f"{days}d"] = {"hit_rate": None, "avg_return": None, "total_recs": 0}
            continue

        past_data = load_snapshot(past_snap)
        if not past_data:
            period_stats[f"{days}d"] = {"hit_rate": None, "avg_return": None, "total_recs": 0}
            continue

        past_recs = past_data.get("recommendations", [])
        buy_recs = [r for r in past_recs if r.get("recommendation") in ("BUY", "STRONG_BUY", "매수", "강력 매수")]

        hits = 0
        returns: List[float] = []
        details: List[Dict[str, Any]] = []

        for rec in buy_recs:
            ticker = rec.get("ticker", "")
            name = rec.get("name", "?")
            rec_price = rec.get("price") or rec.get("current_price")
            if not rec_price or not ticker:
                continue
            try:
                rec_price = float(rec_price)
            except (TypeError, ValueError):
                continue

            cur_price = current_prices.get(ticker)
            if cur_price is None or cur_price <= 0:
                continue

            ret = round((cur_price - rec_price) / rec_price * 100, 2)
            returns.append(ret)
            if ret > 0:
                hits += 1

            detail = {
                "ticker": ticker,
                "name": name,
                "rec_date": past_snap,
                "rec_price": rec_price,
                "current_price": cur_price,
                "return_pct": ret,
                "hit": ret > 0,
                "period": f"{days}d",
                "recommendation": rec.get("recommendation"),
                "brain_score": rec.get("brain_score"),
            }
            details.append(detail)
            all_recs.append(detail)

        total = len(returns)
        hit_rate = round(hits / total * 100, 1) if total > 0 else None
        avg_ret = round(sum(returns) / total, 2) if total > 0 else None
        max_ret = round(max(returns), 2) if returns else None
        min_ret = round(min(returns), 2) if returns else None

        sharpe = None
        if total >= 3:
            import statistics
            mean_r = sum(returns) / total
            std_r = statistics.stdev(returns)
            if std_r > 0:
                sharpe = round(mean_r / std_r, 2)

        period_stats[f"{days}d"] = {
            "hit_rate": hit_rate,
            "avg_return": avg_ret,
            "max_return": max_ret,
            "min_return": min_ret,
            "sharpe": sharpe,
            "total_recs": total,
            "hits": hits,
            "snapshot_date": past_snap,
        }

    all_recs.sort(key=lambda x: x.get("return_pct", 0), reverse=True)

    result = {
        "periods": period_stats,
        "recommendations": all_recs[:50],
        "updated_at": str(now_kst()),
    }

    _save_stats(result)
    return result


def _find_nearest_snapshot(target_date: str, available: List[str]) -> Optional[str]:
    """target_date에 가장 가까운 스냅샷 날짜 반환 (±2일 범위)."""
    if target_date in available:
        return target_date

    from datetime import datetime
    try:
        td = datetime.strptime(target_date, "%Y-%m-%d").date()
    except ValueError:
        return None

    best = None
    best_diff = 999
    for d_str in available:
        try:
            d = datetime.strptime(d_str, "%Y-%m-%d").date()
            diff = abs((d - td).days)
            if diff <= 2 and diff < best_diff:
                best = d_str
                best_diff = diff
        except ValueError:
            continue
    return best
