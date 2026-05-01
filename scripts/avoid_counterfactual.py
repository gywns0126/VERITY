#!/usr/bin/env python3
"""
avoid_counterfactual — AVOID/CAUTION 등급 종목의 사후 30d 수익률 → regime 별 분리 집계.

배경:
  Brain 의 BUY/WATCH 만 VAMS 에 들어가서 후속 측정됨. AVOID 의 후속은 측정되지 않아
  "AVOID 가 진짜 시그널이었는가 vs 보수 편향이었는가" 를 알 수 없음.
  → self-evolving 시스템이 regime 별로 overfit 되고 있는지 검출하기 위한 입력.

regime 분류 (regime_diagnostics.trailing_score 기반, 5/1 이후 history snapshot 만 가용):
  trailing_score >  0.3 → uptrend   (상승장 — AVOID hit 은 운, FN 위주)
  trailing_score < -0.3 → downtrend (하락장 — AVOID hit 은 진짜 시그널, TN 위주)
  나머지              → sideways   (횡보장 — baseline)

산출:
  data/metadata/avoid_counterfactual.json (placeholder schema 준수, 자동 갱신)

사용:
  python3 scripts/avoid_counterfactual.py
  python3 scripts/avoid_counterfactual.py --window-start 2026-05-03 --window-end 2026-05-16
  python3 scripts/avoid_counterfactual.py --hold-days 30
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List, Optional, Tuple

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, ".."))


_HISTORY_DIR = Path("data/history")
_OUTPUT_PATH = Path("data/metadata/avoid_counterfactual.json")

# regime 분류 임계
_UPTREND_THRESHOLD = 0.3
_DOWNTREND_THRESHOLD = -0.3

# AVOID/CAUTION 으로 간주할 recommendation 값
_AVOID_LIKE = ("AVOID", "CAUTION", "STRONG_AVOID")


def _load_snapshot(path: Path) -> Optional[Dict[str, Any]]:
    try:
        text = path.read_text(encoding="utf-8")
        text = text.replace("NaN", "null").replace("Infinity", "null").replace("-Infinity", "null")
        return json.loads(text)
    except Exception:
        return None


def _classify_regime(diag: Dict[str, Any]) -> Optional[str]:
    score = diag.get("trailing_score")
    if score is None:
        return None
    try:
        s = float(score)
    except Exception:
        return None
    if s > _UPTREND_THRESHOLD:
        return "uptrend"
    if s < _DOWNTREND_THRESHOLD:
        return "downtrend"
    return "sideways"


def _ticker_price(snapshot: Dict[str, Any], ticker: str) -> Optional[float]:
    """snapshot 의 recommendations 또는 holdings 에서 ticker 가격 조회."""
    for rec in snapshot.get("recommendations") or []:
        if rec.get("ticker") == ticker:
            p = rec.get("price")
            if isinstance(p, (int, float)) and p > 0:
                return float(p)
    vams = snapshot.get("vams") or {}
    for h in vams.get("holdings") or []:
        if h.get("ticker") == ticker:
            p = h.get("current_price") or h.get("close")
            if isinstance(p, (int, float)) and p > 0:
                return float(p)
    return None


def _find_snapshot_around(target_date: str, max_offset_days: int = 3) -> Optional[Tuple[str, Dict[str, Any]]]:
    """target_date 정확히 또는 ±max_offset_days 내 가장 가까운 snapshot 반환.
    토/일/공휴일 보정용.
    """
    try:
        d0 = datetime.strptime(target_date, "%Y-%m-%d")
    except Exception:
        return None
    for offset in range(0, max_offset_days + 1):
        for sign in (1, -1) if offset > 0 else (0,):
            cand = (d0 + timedelta(days=sign * offset)).strftime("%Y-%m-%d")
            cand_path = _HISTORY_DIR / f"{cand}.json"
            if cand_path.exists():
                snap = _load_snapshot(cand_path)
                if snap:
                    return cand, snap
    return None


def aggregate(
    window_start: Optional[str] = None,
    window_end: Optional[str] = None,
    hold_days: int = 30,
) -> Dict[str, Any]:
    if not _HISTORY_DIR.exists():
        return {"_error": "data/history 없음"}

    today_str = datetime.now().strftime("%Y-%m-%d")
    snapshot_files = sorted(_HISTORY_DIR.glob("*.json"))

    samples_by_regime: Dict[str, List[Dict[str, Any]]] = {
        "uptrend": [], "downtrend": [], "sideways": []
    }
    pending_count = 0
    no_regime_count = 0

    for snap_file in snapshot_files:
        date_str = snap_file.stem
        if window_start and date_str < window_start:
            continue
        if window_end and date_str > window_end:
            continue

        snap = _load_snapshot(snap_file)
        if not snap:
            continue

        diag = snap.get("regime_diagnostics") or {}
        regime = _classify_regime(diag)
        if regime is None:
            no_regime_count += 1
            continue

        avoid_recs = [
            r for r in (snap.get("recommendations") or [])
            if (r.get("recommendation") or "").upper() in _AVOID_LIKE
        ]
        if not avoid_recs:
            continue

        # D+hold_days snapshot
        future_date = (datetime.strptime(date_str, "%Y-%m-%d") + timedelta(days=hold_days)).strftime("%Y-%m-%d")
        if future_date > today_str:
            pending_count += len(avoid_recs)
            continue

        future = _find_snapshot_around(future_date, max_offset_days=3)
        if not future:
            pending_count += len(avoid_recs)
            continue
        future_date_actual, future_snap = future

        for rec in avoid_recs:
            ticker = rec.get("ticker")
            if not ticker:
                continue
            p0 = rec.get("price")
            if not isinstance(p0, (int, float)) or p0 <= 0:
                continue
            p1 = _ticker_price(future_snap, ticker)
            if p1 is None:
                continue
            ret_pct = (p1 - p0) / p0 * 100.0
            samples_by_regime[regime].append({
                "date": date_str,
                "future_date": future_date_actual,
                "ticker": ticker,
                "name": rec.get("name"),
                "recommendation": rec.get("recommendation"),
                "p0": p0,
                "p1": p1,
                "return_pct": round(ret_pct, 2),
            })

    # 집계
    def _summarize(samples: List[Dict[str, Any]], regime: str) -> Dict[str, Any]:
        n = len(samples)
        if n == 0:
            return {"avoid_count": 0, "30d_return_avg_pct": None, "fn_rate": None, "tn_rate": None}
        rets = [s["return_pct"] for s in samples]
        avg = round(mean(rets), 2)
        # FN: AVOID 했는데 + 수익 (놓친 기회)
        fn = sum(1 for r in rets if r > 0)
        # TN: AVOID 했는데 - 수익 (회피 성공)
        tn = sum(1 for r in rets if r <= 0)
        return {
            "avoid_count": n,
            "30d_return_avg_pct": avg,
            "fn_rate": round(fn / n, 3) if n else None,
            "tn_rate": round(tn / n, 3) if n else None,
        }

    regime_split = {
        "uptrend": {
            **_summarize(samples_by_regime["uptrend"], "uptrend"),
            "_note": "FN = AVOID 했는데 30d 후 + 수익. 상승장 FN 은 운이 아니라 진짜 false negative.",
        },
        "downtrend": {
            **_summarize(samples_by_regime["downtrend"], "downtrend"),
            "_note": "TN = AVOID 후 - 수익 (손실 회피). 하락장 TN 이 진짜 시그널.",
        },
        "sideways": {
            **_summarize(samples_by_regime["sideways"], "sideways"),
            "_note": "횡보장은 시그널 약함. baseline 비교용.",
        },
    }

    return {
        "_schema_version": "v1",
        "_purpose": "AVOID/CAUTION 등급 종목의 사후 30d 수익률 — regime별 분리. self-evolving 시스템의 regime overfitting 검출.",
        "_writer": "scripts/avoid_counterfactual.py",
        "_status": "AUTO_WRITTEN",
        "_last_computed_at": datetime.now().isoformat(),
        "aggregation_period": {"start": window_start, "end": window_end},
        "hold_days": hold_days,
        "regime_source": "regime_diagnostics (commit c5ec057, leading/trailing score)",
        "regime_split": regime_split,
        "diagnostic": {
            "pending_count": pending_count,
            "no_regime_count": no_regime_count,
            "_pending_note": "D+30 snapshot 미도래. 시간 지나면 채워짐.",
            "_no_regime_note": "regime_diagnostics 없는 snapshot (5/1 이전).",
        },
        "interpretation": {
            "_note": "regime별 FN rate 가 baseline 보다 높으면 그 regime 에 AVOID 임계 overfit 의심.",
            "action_thresholds": {
                "uptrend_fn_rate_warning": 0.4,
                "downtrend_tn_rate_minimum": 0.6,
            },
        },
    }


def main() -> int:
    p = argparse.ArgumentParser(description="AVOID counterfactual aggregator")
    p.add_argument("--window-start", default="2026-05-03", help="ISO date")
    p.add_argument("--window-end", default=None, help="ISO date (default: today)")
    p.add_argument("--hold-days", type=int, default=30)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args()

    if args.window_end is None:
        args.window_end = datetime.now().strftime("%Y-%m-%d")

    report = aggregate(
        window_start=args.window_start,
        window_end=args.window_end,
        hold_days=args.hold_days,
    )

    if args.verbose or args.dry_run:
        print(json.dumps(report, ensure_ascii=False, indent=2))

    if args.dry_run:
        return 0

    _OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    _OUTPUT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(f"✓ {_OUTPUT_PATH} 갱신")
    return 0


if __name__ == "__main__":
    sys.exit(main())
