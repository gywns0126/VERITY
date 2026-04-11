"""
AI Leaderboard — LLM 소스별 추천 성과 집계

history/ 스냅샷에서 _recommendation_source 필드를 기준으로
Gemini·Claude 오버라이드·기타 소스의 적중률·평균 수익률을 30일 윈도로 산출.
"""
from __future__ import annotations

import statistics
from datetime import timedelta
from typing import Any, Dict, List, Optional

from api.config import now_kst
from api.workflows.archiver import load_snapshot, list_available_dates


def _classify_source(raw: Optional[str]) -> str:
    if not raw:
        return "gemini"
    r = raw.lower()
    if "claude" in r:
        return "claude"
    if "disputed" in r:
        return "gemini_disputed"
    return "gemini"


def compute_ai_leaderboard(window_days: int = 30) -> Dict[str, Any]:
    """
    최근 window_days 동안의 BUY 추천을 소스별로 분류하여 성과 집계.

    Returns:
        {
            "as_of": str,
            "window_days": int,
            "by_source": [
                {"source": "gemini", "n": 20, "hits": 12, "hit_rate": 60.0, "avg_return": 2.3},
                {"source": "claude", "n": 5, "hits": 4, "hit_rate": 80.0, "avg_return": 4.1},
                ...
            ],
            "suggested_note": str,
        }
    """
    dates = list_available_dates()
    if len(dates) < 2:
        return {"as_of": str(now_kst()), "window_days": window_days, "by_source": []}

    today = now_kst().date()
    today_str = today.strftime("%Y-%m-%d")
    today_snap = load_snapshot(today_str)
    if not today_snap and dates:
        today_snap = load_snapshot(dates[-1])
    if not today_snap:
        return {"as_of": str(now_kst()), "window_days": window_days, "by_source": []}

    current_prices: Dict[str, float] = {}
    for r in today_snap.get("recommendations", []):
        t = r.get("ticker", "")
        p = r.get("price") or r.get("current_price")
        if t and p:
            try:
                current_prices[t] = float(p)
            except (TypeError, ValueError):
                pass

    cutoff = (today - timedelta(days=window_days)).strftime("%Y-%m-%d")
    past_dates = [d for d in dates if d >= cutoff and d != today_str]

    buckets: Dict[str, List[float]] = {}

    for d_str in past_dates:
        snap = load_snapshot(d_str)
        if not snap:
            continue
        for rec in snap.get("recommendations", []):
            if rec.get("recommendation") not in ("BUY", "STRONG_BUY", "매수", "강력 매수"):
                continue
            ticker = rec.get("ticker", "")
            rec_price = rec.get("price") or rec.get("current_price")
            if not ticker or not rec_price:
                continue
            try:
                rec_price = float(rec_price)
            except (TypeError, ValueError):
                continue
            cur_price = current_prices.get(ticker)
            if cur_price is None or cur_price <= 0 or rec_price <= 0:
                continue

            ret = round((cur_price - rec_price) / rec_price * 100, 2)
            source = _classify_source(rec.get("_recommendation_source"))
            buckets.setdefault(source, []).append(ret)

    by_source = []
    for src, returns in sorted(buckets.items()):
        n = len(returns)
        hits = sum(1 for r in returns if r > 0)
        hit_rate = round(hits / n * 100, 1) if n else 0
        avg_ret = round(sum(returns) / n, 2) if n else 0
        entry: Dict[str, Any] = {
            "source": src,
            "n": n,
            "hits": hits,
            "hit_rate": hit_rate,
            "avg_return": avg_ret,
        }
        if n >= 3:
            std = statistics.stdev(returns)
            entry["sharpe"] = round(avg_ret / std, 2) if std > 0 else None
        by_source.append(entry)

    by_source.sort(key=lambda x: x.get("hit_rate", 0), reverse=True)

    note = ""
    if len(by_source) >= 2:
        best = by_source[0]
        if best["n"] >= 3:
            note = f"최근 {window_days}일 기준 '{best['source']}' 소스 적중률 {best['hit_rate']}% 우세"

    return {
        "as_of": now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "window_days": window_days,
        "by_source": by_source,
        "suggested_note": note,
    }
