"""
Brain 학습 데이터 트랙 — Weekly~Annual 리포트의 자기진화 input.

리포트 텍스트와는 분리된 정형화 시그널:
  - 등급 분포 (STRONG_BUY/BUY/WATCH/CAUTION/AVOID 비율)
  - 적중률 (BUY 추천 → +N% 도달 / AVOID 추천 → -N% 도달)
  - misleading_factor 분포 (postmortem 결과)
  - VCI 평균/극단값
  - 매크로 필터 차단 효과

저장: data/metadata/brain_learning.jsonl (일자별 누적)
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from api.config import DATA_DIR, now_kst

_PATH = os.path.join(DATA_DIR, "metadata", "brain_learning.jsonl")


def log_daily_signals(
    portfolio: Dict[str, Any],
    backtest_summary: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """일일 학습 시그널 1건 추출 + 저장."""
    os.makedirs(os.path.dirname(_PATH), exist_ok=True)

    recs = portfolio.get("recommendations") or []
    grade_dist = _grade_distribution(recs)
    vci_stats = _vci_stats(recs)
    macro_filter = portfolio.get("macro_filter_log") or {}

    entry = {
        "date": now_kst().strftime("%Y-%m-%d"),
        "timestamp": now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "grade_distribution": grade_dist,
        "vci": vci_stats,
        "macro_filter_blocked": macro_filter.get("blocked_count", 0),
        "macro_filter_passed": macro_filter.get("passed_count", 0),
        "backtest_hit_rate_14d": _safe_get(backtest_summary, "periods", "14d", "hit_rate"),
        "backtest_hit_rate_30d": _safe_get(backtest_summary, "periods", "30d", "hit_rate"),
        "postmortem_misleading_factors": _safe_get(portfolio, "postmortem", "misleading_factors") or {},
    }

    with open(_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def _grade_distribution(recs: List[Dict[str, Any]]) -> Dict[str, int]:
    """등급별 카운트."""
    out: Dict[str, int] = {}
    for r in recs:
        g = (r.get("verity_brain") or {}).get("grade") or r.get("recommendation") or "UNKNOWN"
        out[g] = out.get(g, 0) + 1
    return out


def _vci_stats(recs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """VCI 분포 통계."""
    vcis = []
    for r in recs:
        vci = (r.get("verity_brain") or {}).get("vci") or {}
        v = vci.get("vci")
        if v is not None:
            try:
                vcis.append(float(v))
            except (TypeError, ValueError):
                continue
    if not vcis:
        return {"count": 0}
    return {
        "count": len(vcis),
        "avg": round(sum(vcis) / len(vcis), 2),
        "min": min(vcis),
        "max": max(vcis),
        "extreme_count": sum(1 for v in vcis if abs(v) >= 30),
    }


def _safe_get(obj: Optional[Dict[str, Any]], *keys) -> Any:
    """중첩 dict 안전 접근."""
    cur = obj
    for k in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


def load_signals(days: int = 30) -> List[Dict[str, Any]]:
    """최근 N일 학습 시그널 로드."""
    if not os.path.exists(_PATH):
        return []
    out = []
    cutoff_date = (now_kst().date() - __import__("datetime").timedelta(days=days)).strftime("%Y-%m-%d")
    with open(_PATH, "r", encoding="utf-8") as f:
        for line in f:
            try:
                e = json.loads(line)
                if e.get("date", "") >= cutoff_date:
                    out.append(e)
            except json.JSONDecodeError:
                continue
    return out


def trend_summary(days: int = 28) -> Dict[str, Any]:
    """추세 요약 — Brain 진화 추적."""
    sigs = load_signals(days)
    if len(sigs) < 2:
        return {"days": days, "samples": len(sigs), "trend": "insufficient_data"}

    # 등급 분포 시작 vs 끝 비교
    first = sigs[0].get("grade_distribution") or {}
    last = sigs[-1].get("grade_distribution") or {}
    buy_first = first.get("BUY", 0) + first.get("STRONG_BUY", 0)
    buy_last = last.get("BUY", 0) + last.get("STRONG_BUY", 0)

    # 적중률 추세
    hit_14d = [s.get("backtest_hit_rate_14d") for s in sigs if s.get("backtest_hit_rate_14d") is not None]

    return {
        "days": days,
        "samples": len(sigs),
        "buy_count_change": buy_last - buy_first,
        "hit_rate_14d_avg": round(sum(hit_14d) / len(hit_14d), 1) if hit_14d else None,
        "hit_rate_14d_trend": "up" if len(hit_14d) >= 2 and hit_14d[-1] > hit_14d[0] else "down" if len(hit_14d) >= 2 else "n/a",
    }
