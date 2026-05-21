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
# KI-9 (2026-05-21) — cross-link baseline 90일 historical mean source.
# brain_distribution_evaluator.compute_baseline() 가 lookback 90d 로 읽음
# (updated_at + hit_rate_14d 계약). lean timeseries (hit-rate only, brain_learning 스키마 churn 과 decouple).
_HISTORY_PATH = os.path.join(DATA_DIR, "metadata", "backtest_stats_history.jsonl")


def _append_backtest_history(entry: Dict[str, Any]) -> None:
    """backtest_stats_history.jsonl 1행 append — cross-link baseline source.

    - hit_rate_14d 가 None (no_data) 이면 skip (lean timeseries, null 노이즈 회피).
      compute_baseline 도 None 은 어차피 skip → 일관.
    - 일자 dedupe: 하루 여러 cron run 시 중복 행이 90일 mean 을 왜곡 → 1일 1행.
    - silent-fail (학습 적재 무중단). logged=True stderr (feedback_data_collection_verification_mandatory).
    """
    import sys
    try:
        hit_14d = entry.get("backtest_hit_rate_14d")
        if hit_14d is None:
            return  # no_data — 누적 보류 (값 흐르면 그때부터 timeseries 시작)
        today = entry.get("date")
        # 일자 dedupe — 오늘 행 이미 있으면 skip (first-write-of-day wins)
        if os.path.exists(_HISTORY_PATH):
            with open(_HISTORY_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        if json.loads(line).get("date") == today:
                            return
                    except json.JSONDecodeError:
                        continue
        row = {
            "date": today,
            "updated_at": entry.get("timestamp"),
            "hit_rate_14d": hit_14d,
            "hit_rate_30d": entry.get("backtest_hit_rate_30d"),
            "data_status": entry.get("backtest_hit_rate_data_status"),
            "source": "brain_learning.log_daily_signals",
        }
        with open(_HISTORY_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"[backtest_history] OK: date={today} hit_rate_14d={hit_14d} logged=True",
              file=sys.stderr, flush=True)
    except Exception as e:
        print(f"[backtest_history] WARNING: append 실패 — {type(e).__name__}: {e}",
              file=sys.stderr, flush=True)



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

    # cover 필드 (2026-05-11) — "어제 결심 vs 오늘 결심" 직접 비교용.
    # 사용자 피드백 "어제 결심과 오늘 결심의 차이를 분석하는건 당연한 복기".
    brain = portfolio.get("verity_brain") or {}
    mb = brain.get("market_brain") or {}
    macro = portfolio.get("macro") or {}
    mood = macro.get("market_mood") or {}
    briefing = portfolio.get("briefing") or {}
    daily_report = portfolio.get("daily_report") or {}
    horizon = portfolio.get("market_horizon") or {}

    # 오늘의 판단 = Brain 평균 점수 → grade label
    try:
        from api.utils.dilution import brain_grade_from_score, grade_label
        avg_brain = mb.get("avg_brain_score")
        raw_grade = brain_grade_from_score(avg_brain) if avg_brain is not None else None
        verdict_label = grade_label(raw_grade) if raw_grade else None
    except Exception:
        avg_brain = mb.get("avg_brain_score")
        raw_grade = None
        verdict_label = None

    # BUY / AVOID 후보 list (ticker + name + score)
    def _ticker_list(grades: tuple, limit: int = 10) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for r in recs[:200]:
            g = (r.get("verity_brain") or {}).get("grade") or r.get("recommendation")
            if g in grades:
                out.append({
                    "ticker": str(r.get("ticker") or ""),
                    "name": str(r.get("name") or ""),
                    "score": (r.get("verity_brain") or {}).get("brain_score"),
                })
                if len(out) >= limit:
                    break
        return out

    entry = {
        "date": now_kst().strftime("%Y-%m-%d"),
        "timestamp": now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        # 옛 필드 (호환)
        "grade_distribution": grade_dist,
        "vci": vci_stats,
        "macro_filter_blocked": macro_filter.get("blocked_count", 0),
        "macro_filter_passed": macro_filter.get("passed_count", 0),
        # 2026-05-16 audit P0-1: hit_rate 가 null 인 경우 fallback (net/gross/7d 순)
        "backtest_hit_rate_14d": _resolve_hit_rate(backtest_summary, "14d"),
        "backtest_hit_rate_30d": _resolve_hit_rate(backtest_summary, "30d"),
        "backtest_hit_rate_data_status": _hit_rate_status(backtest_summary, "14d"),
        "postmortem_misleading_factors": _safe_get(portfolio, "postmortem", "misleading_factors") or {},
        # 신규 cover 필드 (어제 vs 오늘 직접 비교)
        "verdict_label": verdict_label,
        "verdict_grade": raw_grade,
        "avg_brain_score": avg_brain,
        "avg_fact_score": mb.get("avg_fact_score"),
        "avg_sentiment_score": mb.get("avg_sentiment_score"),
        "avg_vci": mb.get("avg_vci"),
        "macro_mood_score": mood.get("score"),
        "macro_mood_label": mood.get("label"),
        "horizon_verdict": horizon.get("verdict"),
        "horizon_stage": horizon.get("cycle_stage"),
        "buy_candidates": _ticker_list(("STRONG_BUY", "BUY")),
        "avoid_candidates": _ticker_list(("AVOID",)),
        "key_brief_lines": {
            "macro": briefing.get("macro_line"),
            "brain": briefing.get("brain_line"),
            "max_risk": briefing.get("max_risk_line"),
        },
        "market_summary": daily_report.get("market_summary"),
    }

    with open(_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    # KI-9 — cross-link baseline source 누적 (hit_rate_14d non-null 시 1일 1행).
    _append_backtest_history(entry)
    return entry


def compare_yesterday_vs_today() -> Optional[Dict[str, Any]]:
    """brain_learning.jsonl 의 어제 row vs 오늘 row 직접 비교.

    사용자 피드백 "어제 결심과 오늘 결심의 차이를 분석하는건 당연한 복기" (2026-05-11).

    Returns:
        {
            "yesterday_date", "today_date",
            "yesterday": {verdict_label, avg_brain_score, macro_mood, buy_candidates, ...},
            "today": {...},
            "deltas": {brain_score_delta, mood_score_delta, vci_delta, ...},
            "verdict_changed": bool,
            "buy_candidates_added": [ticker], "buy_candidates_removed": [ticker],
        }
        None — row n<2 (당일 첫 산출)
    """
    rows = load_signals(days=3)
    # 같은 date 중복 가능 — 마지막 row 만 keep per date
    by_date: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        d = r.get("date")
        if d:
            by_date[d] = r
    dates = sorted(by_date.keys())
    if len(dates) < 2:
        return None
    y_date, t_date = dates[-2], dates[-1]
    y, t = by_date[y_date], by_date[t_date]

    def _delta(a, b):
        try:
            return round(float(b) - float(a), 2)
        except (TypeError, ValueError):
            return None

    y_buys = {c["ticker"]: c for c in (y.get("buy_candidates") or [])}
    t_buys = {c["ticker"]: c for c in (t.get("buy_candidates") or [])}
    y_avoids = {c["ticker"]: c for c in (y.get("avoid_candidates") or [])}
    t_avoids = {c["ticker"]: c for c in (t.get("avoid_candidates") or [])}

    return {
        "yesterday_date": y_date,
        "today_date": t_date,
        "yesterday": y,
        "today": t,
        "deltas": {
            "brain_score": _delta(y.get("avg_brain_score"), t.get("avg_brain_score")),
            "fact_score": _delta(y.get("avg_fact_score"), t.get("avg_fact_score")),
            "sentiment_score": _delta(y.get("avg_sentiment_score"), t.get("avg_sentiment_score")),
            "vci": _delta(y.get("avg_vci"), t.get("avg_vci")),
            "mood_score": _delta(y.get("macro_mood_score"), t.get("macro_mood_score")),
        },
        "verdict_changed": y.get("verdict_grade") != t.get("verdict_grade"),
        "yesterday_verdict": y.get("verdict_label"),
        "today_verdict": t.get("verdict_label"),
        "buy_candidates_added": [t_buys[k] for k in t_buys if k not in y_buys],
        "buy_candidates_removed": [y_buys[k] for k in y_buys if k not in t_buys],
        "avoid_candidates_added": [t_avoids[k] for k in t_avoids if k not in y_avoids],
        "avoid_candidates_removed": [y_avoids[k] for k in y_avoids if k not in t_avoids],
    }


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


def _resolve_hit_rate(backtest_summary: Optional[Dict[str, Any]],
                      period: str = "14d") -> Optional[float]:
    """hit_rate fallback chain — null 회피 (P0-1 audit, 2026-05-16).

    우선순위:
      1. periods[period].hit_rate (기존 path)
      2. periods[period].hit_rate_net (수수료·세금 차감)
      3. periods[period].hit_rate_gross (총수익)
      4. periods["7d"].hit_rate (짧은 윈도우 fallback)

    모두 null 이면 None 반환. silent skip 아닌 명시적 data 부재.
    27/28 entries null 사고 (audit P0-1) 학습.
    """
    if not isinstance(backtest_summary, dict):
        return None
    p = _safe_get(backtest_summary, "periods", period) or {}
    if not isinstance(p, dict):
        return None
    # 1-3차 fallback
    for key in ("hit_rate", "hit_rate_net", "hit_rate_gross"):
        v = p.get(key)
        if v is not None:
            return v
    # 4차 fallback — period 14d/30d 모두 비면 7d 시도
    if period != "7d":
        p7 = _safe_get(backtest_summary, "periods", "7d") or {}
        if isinstance(p7, dict):
            for key in ("hit_rate", "hit_rate_net", "hit_rate_gross"):
                v = p7.get(key)
                if v is not None:
                    return v
    return None


def _hit_rate_status(backtest_summary: Optional[Dict[str, Any]],
                     period: str = "14d") -> str:
    """data status 명시 — silent skip 회피 (feedback_data_collection_verification_mandatory).

    Returns: "ok" / "fallback_net" / "fallback_gross" / "fallback_7d" / "no_data"
    """
    if not isinstance(backtest_summary, dict):
        return "no_summary"
    p = _safe_get(backtest_summary, "periods", period) or {}
    if p.get("hit_rate") is not None:
        return "ok"
    if p.get("hit_rate_net") is not None:
        return "fallback_net"
    if p.get("hit_rate_gross") is not None:
        return "fallback_gross"
    if period != "7d":
        p7 = _safe_get(backtest_summary, "periods", "7d") or {}
        if p7 and any(p7.get(k) is not None for k in ("hit_rate", "hit_rate_net", "hit_rate_gross")):
            return "fallback_7d"
    return "no_data"


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


def compute_hit_rate_weight_multiplier(
    hit_rate_avg: Optional[float],
    samples: int,
) -> Dict[str, Any]:
    """hit_rate 기반 brain weights multiplier 자동 산출 (P1-2, Perplexity NQ2).

    공식 (NQ2 verdict):
      - hit_rate ≥ 60: ×1.20 (상한 cap)
      - hit_rate 55-60: ×1.10-1.15
      - hit_rate 50-55: ×1.0 (유지)
      - hit_rate 45-50: ×0.80
      - hit_rate < 45: ×0.50 (floor — 30-50% 사이, 신호 재활성화 능력 보존)

    Floor 30-50% 의무 (AQR 계열 암묵적 관행): 0 수렴 시 신호 재활성화 탐지 능력 손실.

    Sample size confidence (Half-Kelly 변형):
      - samples < 10: 영향력 0.5× (shrinkage)
      - samples 10-30: 0.75× (보수 진입)
      - samples ≥ 30: 1.0× (full)

    Returns:
        {
            "raw_multiplier": float,        # 공식 적용 raw
            "applied_multiplier": float,    # confidence 적용 후
            "floor_applied": bool,          # 30% floor 도달 여부
            "tier": str,                    # poor/below_avg/neutral/good/strong
            "reason": str,
        }
    """
    if hit_rate_avg is None or samples < 2:
        return {
            "raw_multiplier": 1.0,
            "applied_multiplier": 1.0,
            "floor_applied": False,
            "tier": "no_data",
            "reason": f"hit_rate={hit_rate_avg} samples={samples} — 평가 불가",
        }

    # 1) Raw multiplier (NQ2 verdict 정합)
    if hit_rate_avg >= 60:
        raw, tier = 1.20, "strong"
    elif hit_rate_avg >= 55:
        raw, tier = 1.15, "good"
    elif hit_rate_avg >= 50:
        raw, tier = 1.0, "neutral"
    elif hit_rate_avg >= 45:
        raw, tier = 0.80, "below_avg"
    else:
        raw, tier = 0.50, "poor"

    # 2) Floor 30% 강제 (신호 재활성화 능력 보존)
    floor_applied = False
    if raw < 0.30:
        raw = 0.30
        floor_applied = True

    # 3) Sample size confidence (Half-Kelly 변형)
    if samples >= 30:
        conf = 1.0
    elif samples >= 10:
        conf = 0.75
    else:
        conf = 0.5

    # multiplier = 1.0 + (raw - 1.0) × confidence
    applied = round(1.0 + (raw - 1.0) * conf, 3)

    return {
        "raw_multiplier": round(raw, 3),
        "applied_multiplier": applied,
        "floor_applied": floor_applied,
        "tier": tier,
        "confidence": conf,
        "reason": (f"hit_rate={hit_rate_avg:.1f}% samples={samples} → "
                  f"tier={tier} raw=×{raw:.2f} conf={conf:.2f} → applied=×{applied:.2f}"
                  + (" (floor 30% 적용)" if floor_applied else "")),
    }
