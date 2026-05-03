"""
Report findings → Brain 학습 트랙 (2026-05-03).

리포트의 존재 목적 #1 = Brain 의 지속 학습 input. PDF 만 만들고 끝나면 Brain 은
정체. 이 모듈은 매 cron 마다 portfolio 에서 structured findings 를 추출해
data/metadata/report_findings.jsonl 에 누적한다. strategy_evolver 가 이걸 다시
prompt context 로 흡수해 가중치/임계 진화 제안을 생성.

기존 brain_learning.jsonl (등급 분포 + VCI + hit_rate) 와 직교:
  brain_learning.jsonl  = 정량 시그널 (수치)
  report_findings.jsonl = 정성 findings (텍스트)
둘을 합쳐 Brain 진화의 양 측면 (성과 + 해석) 모두 담는다.

스키마 (1 line = 1 daily findings):
  {
    "date": "2026-05-03",
    "timestamp": "2026-05-03T22:05:00+09:00",
    "report_type": "daily",
    "findings": {
      "market_summary": "<text>",
      "strategy": "<text>",
      "risk_watch": "<text>",
      "tomorrow_outlook": "<text>",
      "briefing_headline": "<text>",
      "briefing_tone": "neutral|bullish|bearish",
      "action_items": ["...", "..."],
      "alerts_count": N,
      "top_buy_picks": [{"ticker", "name", "grade", "score", "vci"}, ...],
      "grade_distribution": {"BUY": N, "WATCH": N, ...},
      "macro_mood": "<label>",
      "backtest_hit_rate_14d": 50.0,
      "backtest_avg_return_14d": 3.69,
      "postmortem_status": "clean|...",
      "postmortem_misleading_factors": {"factor": count, ...}
    }
  }
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

from api.config import DATA_DIR, now_kst

_logger = logging.getLogger(__name__)
_PATH = os.path.join(DATA_DIR, "metadata", "report_findings.jsonl")

_BUY_LABELS = ("BUY", "STRONG_BUY", "매수", "강력 매수")


def _safe_text(v: Any, max_len: int = 600) -> str:
    """문자열 정규화 + 길이 제한 (LLM context 절약)."""
    if v is None:
        return ""
    if isinstance(v, dict):
        # market_summary 등이 dict 인 케이스 — 주요 텍스트만 결합
        parts = [str(x) for x in v.values() if isinstance(x, str)]
        s = " / ".join(parts)
    elif isinstance(v, list):
        s = " / ".join(str(x) for x in v if x)
    else:
        s = str(v)
    s = s.strip()
    if len(s) > max_len:
        return s[:max_len] + "..."
    return s


def _safe_get(obj: Optional[Dict[str, Any]], *keys: str) -> Any:
    cur = obj
    for k in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


def extract_daily(portfolio: Dict[str, Any]) -> Dict[str, Any]:
    """portfolio 에서 daily findings 추출."""
    daily = portfolio.get("daily_report") or {}
    briefing = portfolio.get("briefing") or {}
    macro = portfolio.get("macro") or {}
    mood = (macro.get("market_mood") or {}) if isinstance(macro, dict) else {}
    recs = portfolio.get("recommendations") or []
    bt = portfolio.get("backtest_stats") or {}
    bt14 = (bt.get("periods") or {}).get("14d") or {}
    bt30 = (bt.get("periods") or {}).get("30d") or {}
    pm = portfolio.get("postmortem") or {}

    # 등급 분포
    grade_dist: Dict[str, int] = {}
    for r in recs:
        g = _safe_get(r, "verity_brain", "grade") or r.get("recommendation") or "UNKNOWN"
        grade_dist[g] = grade_dist.get(g, 0) + 1

    # Top BUY picks (간결 포맷, 상위 5건)
    buy_picks: List[Dict[str, Any]] = []
    for r in recs:
        g = _safe_get(r, "verity_brain", "grade") or r.get("recommendation")
        if g not in _BUY_LABELS:
            continue
        score = _safe_get(r, "verity_brain", "score")
        vci = _safe_get(r, "verity_brain", "vci", "vci")
        buy_picks.append({
            "ticker": r.get("ticker", ""),
            "name": r.get("name", ""),
            "grade": g,
            "score": score,
            "vci": vci,
        })
    buy_picks.sort(
        key=lambda x: (x.get("score") if isinstance(x.get("score"), (int, float)) else -1),
        reverse=True,
    )
    buy_picks = buy_picks[:5]

    return {
        "market_summary": _safe_text(daily.get("market_summary")),
        "strategy": _safe_text(daily.get("strategy")),
        "risk_watch": _safe_text(daily.get("risk_watch")),
        "tomorrow_outlook": _safe_text(daily.get("tomorrow_outlook")),
        "briefing_headline": _safe_text(briefing.get("headline"), max_len=200),
        "briefing_tone": _safe_text(briefing.get("tone"), max_len=40),
        "action_items": [_safe_text(x, max_len=200) for x in (briefing.get("action_items") or [])][:5],
        "alerts_count": len(briefing.get("alerts") or []),
        "top_buy_picks": buy_picks,
        "grade_distribution": grade_dist,
        "macro_mood": _safe_text(mood.get("label"), max_len=40),
        "backtest_hit_rate_14d": bt14.get("hit_rate"),
        "backtest_avg_return_14d": bt14.get("avg_return"),
        "backtest_total_recs_14d": bt14.get("total_recs"),
        "backtest_hit_rate_30d": bt30.get("hit_rate"),
        "backtest_avg_return_30d": bt30.get("avg_return"),
        "postmortem_status": pm.get("status"),
        "postmortem_analyzed_count": pm.get("analyzed_count"),
        "postmortem_misleading_factors": pm.get("misleading_factors") or {},
    }


def log(portfolio: Dict[str, Any], report_type: str = "daily") -> Optional[Dict[str, Any]]:
    """findings 추출 + JSONL append. 실패해도 호출자 흐름 막지 않음."""
    try:
        if report_type != "daily":
            # MVP: daily 만. weekly/monthly+ 는 후속.
            return None
        findings = extract_daily(portfolio)
        os.makedirs(os.path.dirname(_PATH), exist_ok=True)
        entry = {
            "date": now_kst().strftime("%Y-%m-%d"),
            "timestamp": now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
            "report_type": report_type,
            "findings": findings,
        }
        with open(_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry
    except Exception as e:  # noqa: BLE001
        _logger.warning("report_findings.log 실패 (호출자 진행): %s", e)
        return None


def load_recent(days: int = 30, report_type: Optional[str] = None) -> List[Dict[str, Any]]:
    """최근 N일 findings 반환. strategy_evolver 가 prompt context 로 사용."""
    if not os.path.exists(_PATH):
        return []
    import datetime as _dt
    cutoff = (now_kst().date() - _dt.timedelta(days=days)).strftime("%Y-%m-%d")
    out: List[Dict[str, Any]] = []
    with open(_PATH, "r", encoding="utf-8") as f:
        for line in f:
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            if e.get("date", "") < cutoff:
                continue
            if report_type and e.get("report_type") != report_type:
                continue
            out.append(e)
    return out
