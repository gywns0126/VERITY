"""
brain_weights cross-validation OOS — Sprint 11 결함 4 후속 (2026-05-01).

베테랑 due diligence 결함 2: 현재 brain_weights default (0.7/0.3) 가 inferred —
out-of-sample 검증 없이 사용. 후보 가중치 (0.70~0.85) 로 과거 추천을 재계산해서
hit_rate / avg_return 비교. constitution 갱신 결정 근거 마련.

핵심 idea (verity_brain 의 가산점 분해 저장된 점 이용):
  raw_brain = fact_score * w_fact + sentiment_score * w_sent
              + vci_bonus + candle_bonus - red_flag_penalty
  → 후보 (w_fact, w_sent) 만 변경해서 다시 산출 가능 (다른 가산점은 동일)

T+1 시가 보정 (결함 1 후속 패턴) 통일 — alpha 부풀림 차단.

산출 결과:
  data/metadata/brain_weights_cv.json
  portfolio["brain_weights_cv"] (Brain 진화 prompt 입력)

자동 적용 X — 사용자 검토 후 수동 (4가드 정책).
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# 후보 가중치 — fact 비중 점진 증가 (Tetlock sentiment decay 반영)
CANDIDATES: List[Tuple[float, float]] = [
    (0.70, 0.30),  # current default
    (0.75, 0.25),
    (0.80, 0.20),
    (0.85, 0.15),  # 베테랑 권고
]

LOOKBACK_DAYS = 30   # 단일 윈도우 — 다음 단계에서 14/30/60 multi-window
TX_COST_PCT = 0.4    # round-trip 비용 (backtest_archive 와 동일 임계)

# 등급 임계 (현재 constitution 보수적 기본값)
def _grade_from_score(score: float) -> str:
    if score >= 80:
        return "STRONG_BUY"
    if score >= 65:
        return "BUY"
    if score >= 50:
        return "WATCH"
    if score >= 35:
        return "CAUTION"
    return "AVOID"


def _recompute_brain_score(rec: Dict[str, Any], w_fact: float, w_sent: float) -> Optional[float]:
    """후보 가중치로 brain_score 재산출. fact/sentiment 외 가산점은 원본 유지."""
    vb = rec.get("verity_brain") or {}
    fs_block = vb.get("fact_score")
    ss_block = vb.get("sentiment_score")
    if not isinstance(fs_block, dict) or not isinstance(ss_block, dict):
        return None
    fs = fs_block.get("score")
    ss = ss_block.get("score")
    if not isinstance(fs, (int, float)) or not isinstance(ss, (int, float)):
        return None
    vci_bonus = vb.get("vci_bonus") or 0
    candle_bonus = vb.get("candle_bonus") or 0
    red_flag_penalty = vb.get("red_flag_penalty") or 0
    raw = fs * w_fact + ss * w_sent + vci_bonus + candle_bonus - red_flag_penalty
    return max(0, min(100, raw))


def _backtest_one_candidate(
    past_recs: List[Dict[str, Any]],
    t_plus_1_prices: Dict[str, float],
    current_prices: Dict[str, float],
    w_fact: float,
    w_sent: float,
) -> Dict[str, Any]:
    """단일 가중치 후보로 BUY/STRONG_BUY 재선정 → hit_rate / avg_return."""
    hits = 0
    total = 0
    returns: List[float] = []
    skipped_no_t1 = 0

    for rec in past_recs:
        ticker = rec.get("ticker")
        if not ticker:
            continue
        new_score = _recompute_brain_score(rec, w_fact, w_sent)
        if new_score is None:
            continue
        new_grade = _grade_from_score(new_score)
        if new_grade not in ("BUY", "STRONG_BUY"):
            continue

        t1_price = t_plus_1_prices.get(ticker)
        if t1_price is None or t1_price <= 0:
            skipped_no_t1 += 1
            continue
        cur_price = current_prices.get(ticker)
        if cur_price is None or cur_price <= 0:
            continue

        ret = (float(cur_price) - float(t1_price)) / float(t1_price) * 100.0
        net_ret = ret - TX_COST_PCT
        returns.append(round(net_ret, 2))
        total += 1
        if net_ret > 0:
            hits += 1

    return {
        "w_fact": w_fact,
        "w_sent": w_sent,
        "n_buy_picks": total,
        "skipped_no_t_plus_1": skipped_no_t1,
        "hit_rate_pct": round(hits / total * 100, 1) if total > 0 else None,
        "avg_return_net_pct": round(sum(returns) / total, 2) if total > 0 else None,
        "median_return_pct": round(sorted(returns)[total // 2], 2) if total > 0 else None,
        "max_return_pct": round(max(returns), 2) if returns else None,
        "min_return_pct": round(min(returns), 2) if returns else None,
    }


def cross_validate(lookback_days: int = LOOKBACK_DAYS) -> Dict[str, Any]:
    """전체 cross-validation 수행. 결과 dict 반환.

    snapshot 시계열에서:
      - past_snap = 오늘 - lookback_days (가장 가까운 영업일)
      - T+1 = past_snap 다음 영업일
      - today = 가장 최신 snapshot
    각 후보 (w_fact, w_sent) 별로 backtest.
    """
    from api.workflows.archiver import list_available_dates, load_snapshot
    from api.intelligence.backtest_archive import (
        _t_plus_1_price_map,
        _get_price_map_from_snapshot,
        _find_nearest_snapshot,
    )

    dates = list_available_dates()
    if len(dates) < 5:
        return {
            "status": "insufficient_snapshots",
            "available": len(dates),
            "need": 5,
            "lookback_days": lookback_days,
        }

    today_str = dates[-1]
    today_snap = load_snapshot(today_str)
    if not today_snap:
        return {"status": "today_snapshot_missing"}
    current_prices = _get_price_map_from_snapshot(today_snap)

    from datetime import datetime as _dt, timedelta as _td
    try:
        today_d = _dt.strptime(today_str, "%Y-%m-%d").date()
    except ValueError:
        return {"status": "date_parse_error"}
    target_date = (today_d - _td(days=lookback_days)).strftime("%Y-%m-%d")
    past_snap_date = _find_nearest_snapshot(target_date, dates)
    if not past_snap_date:
        return {"status": "no_past_snapshot", "target_date": target_date}

    past_snap = load_snapshot(past_snap_date)
    if not past_snap:
        return {"status": "past_snapshot_load_failed", "date": past_snap_date}
    past_recs = past_snap.get("recommendations") or []
    if not past_recs:
        return {"status": "past_snap_no_recs", "date": past_snap_date}

    t_plus_1_prices = _t_plus_1_price_map(past_snap_date, dates)
    if not t_plus_1_prices:
        return {"status": "no_t_plus_1_prices", "past_snap": past_snap_date}

    results: List[Dict[str, Any]] = []
    for w_fact, w_sent in CANDIDATES:
        result = _backtest_one_candidate(past_recs, t_plus_1_prices, current_prices, w_fact, w_sent)
        results.append(result)

    # 비교 + 추천
    valid = [r for r in results if r["hit_rate_pct"] is not None]
    if not valid:
        return {
            "status": "no_valid_candidates",
            "lookback_days": lookback_days,
            "past_snap": past_snap_date,
        }

    best_by_return = max(valid, key=lambda r: r["avg_return_net_pct"] or -999)
    best_by_hitrate = max(valid, key=lambda r: r["hit_rate_pct"] or 0)
    current_default = next((r for r in results if r["w_fact"] == 0.70), None)

    return {
        "status": "active",
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "lookback_days": lookback_days,
        "past_snap": past_snap_date,
        "t_plus_1_count": len(t_plus_1_prices),
        "current_snap": today_str,
        "candidates": results,
        "best_by_return": {"w_fact": best_by_return["w_fact"], "avg_return": best_by_return["avg_return_net_pct"]},
        "best_by_hit_rate": {"w_fact": best_by_hitrate["w_fact"], "hit_rate": best_by_hitrate["hit_rate_pct"]},
        "current_default": current_default,
        "tx_cost_pct_round_trip": TX_COST_PCT,
        "policy_note": (
            "자동 적용 X. 단일 윈도우 — 다음 단계에서 14/30/60 multi-window 평균. "
            "constitution 변경 시 4가드 정책 (commit/시간대/모니터링/롤백) 적용 필요."
        ),
    }


def persist(cv: Dict[str, Any], path: Optional[str] = None) -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.normpath(os.path.join(here, "..", ".."))
    if path is None:
        path = os.path.join(repo_root, "data", "metadata", "brain_weights_cv.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cv, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    return path


def attach_to_portfolio(portfolio: Dict[str, Any]) -> Dict[str, Any]:
    cv = cross_validate()
    portfolio["brain_weights_cv"] = cv
    try:
        persist(cv)
    except Exception as e:  # noqa: BLE001
        logger.warning("brain_weights_cv persist failed: %s", e)
    return cv
