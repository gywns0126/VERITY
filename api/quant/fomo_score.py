"""
FOMO Score 측정 인프라 v0.1 (2026-05-17, Perplexity Q6 학계 자문 적용).

2028 Vision Anti-FOMO 산식 코드. docs/GOLDEN_GOOSE_VISION_2028_v0.1.md SSOT.

핵심 산식:
    FOMO Score = Realized Turnover / Rule-based Turnover - 1

    > 0.3: 위험한 충동매매 → 코드 룰 강제 강화 필요
    0.1 ~ 0.3: 주의
    < 0.1: Anti-FOMO 달성 ✅

추가 지표 (Entry Timing Regret Rate):
    - 추적 자체가 FOMO 정신적 비용 폭증 → VERITY 는 추적 X (의도된 침묵)

데이터 source:
    - Realized Turnover: VAMS history 의 BUY/SELL events (manual + auto 분리)
    - Rule-based Turnover: trade_plan v0 의 transition_triggers 발화 카운트

NOTE: 운영 누적 데이터 부족 (2026-05 운영 시작, 진짜 측정 = 1년 누적 2027+).
본 모듈 = 산식 구현 인프라. cron_health_monitor 분기별 호출.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

KST = timezone(timedelta(hours=9))

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FOMO_LEDGER_PATH = REPO_ROOT / "data" / "metadata" / "fomo_score_ledger.jsonl"


def load_vams_history(path: Optional[str] = None) -> List[Dict[str, Any]]:
    """data/portfolio.json 의 vams.history 또는 별도 history file 로드."""
    target = Path(path) if path else REPO_ROOT / "data" / "portfolio.json"
    if not target.exists():
        return []
    try:
        d = json.loads(target.read_text())
        # portfolio.json 구조: vams.history 또는 trade_history
        vams = d.get("vams", {}) if "vams" in d else d
        return vams.get("history") or vams.get("trade_history") or []
    except Exception as e:
        print(f"[fomo_score] history load fail: {e}", file=sys.stderr)
        return []


def count_realized_turnover(
    history: List[Dict[str, Any]],
    days_window: int = 30,
    cutoff: Optional[datetime] = None,
) -> Dict[str, int]:
    """VAMS history 의 BUY/SELL events 카운트.

    Auto = trade_plan transition 자동 매매 (rule_id 기록됨).
    Manual = 사용자 override 매매 (rule_id 없음).

    Returns: {auto_buys, auto_sells, manual_buys, manual_sells, total}.
    """
    cutoff = cutoff or datetime.now(KST)
    since = cutoff - timedelta(days=days_window)

    counts = {"auto_buys": 0, "auto_sells": 0, "manual_buys": 0, "manual_sells": 0}
    for ev in history:
        ts_str = ev.get("timestamp") or ev.get("at") or ev.get("date") or ""
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=KST)
            if ts < since:
                continue
        except (ValueError, TypeError):
            continue

        ev_type = str(ev.get("type", "")).upper()
        is_manual = not bool(
            ev.get("rule_id") or ev.get("transition_trigger") or ev.get("auto")
        )

        if ev_type == "BUY":
            if is_manual:
                counts["manual_buys"] += 1
            else:
                counts["auto_buys"] += 1
        elif ev_type in ("SELL", "PARTIAL_SELL", "STOP_LOSS"):
            if is_manual:
                counts["manual_sells"] += 1
            else:
                counts["auto_sells"] += 1

    counts["total"] = sum(counts.values())
    counts["auto_total"] = counts["auto_buys"] + counts["auto_sells"]
    counts["manual_total"] = counts["manual_buys"] + counts["manual_sells"]
    return counts


def estimate_rule_based_turnover(
    history: List[Dict[str, Any]],
    days_window: int = 30,
    cutoff: Optional[datetime] = None,
) -> Dict[str, int]:
    """trade_plan v0 transition_triggers 발화 카운트.

    proxy: history 의 auto events + (verdict change events 추정).
    진짜 = trade_plan_followup.py 의 verdict history 와 비교 (별 sprint).
    """
    cutoff = cutoff or datetime.now(KST)
    since = cutoff - timedelta(days=days_window)

    rule_triggered = 0
    verdict_changes = 0
    for ev in history:
        ts_str = ev.get("timestamp") or ev.get("at") or ev.get("date") or ""
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=KST)
            if ts < since:
                continue
        except (ValueError, TypeError):
            continue

        # rule_id 또는 transition trigger 설정된 events
        if ev.get("rule_id") or ev.get("transition_trigger") or ev.get("auto"):
            rule_triggered += 1
        # verdict change events
        if ev.get("verdict_change") or ev.get("grade_transition"):
            verdict_changes += 1

    return {
        "rule_triggered": rule_triggered,
        "verdict_changes": verdict_changes,
        "estimated_total": rule_triggered + verdict_changes,
    }


def compute_fomo_score(
    history: List[Dict[str, Any]],
    days_window: int = 30,
) -> Dict[str, Any]:
    """FOMO Score 산출.

    FOMO Score = Realized Turnover / Rule-based Turnover - 1
    """
    realized = count_realized_turnover(history, days_window=days_window)
    rule_based = estimate_rule_based_turnover(history, days_window=days_window)

    realized_total = realized["total"]
    rule_total = rule_based["estimated_total"]

    if rule_total == 0:
        if realized_total == 0:
            fomo_score = 0.0
            interpretation = "no_activity"
        else:
            fomo_score = None  # 정의 불가 (분모 0)
            interpretation = "all_manual_no_rules"
    else:
        fomo_score = round(realized_total / rule_total - 1, 3)
        if fomo_score > 0.3:
            interpretation = "high_risk_impulsive_trading"
        elif fomo_score > 0.1:
            interpretation = "caution"
        else:
            interpretation = "anti_fomo_achieved"

    # Manual ratio = 사용자 override 비중
    manual_ratio = (
        realized["manual_total"] / realized_total if realized_total > 0 else None
    )

    return {
        "fomo_score": fomo_score,
        "interpretation": interpretation,
        "realized_turnover": realized,
        "rule_based_turnover": rule_based,
        "manual_override_ratio": round(manual_ratio, 3) if manual_ratio is not None else None,
        "days_window": days_window,
        "assessed_at": datetime.now(KST).isoformat(timespec="seconds"),
    }


def append_ledger(entry: Dict[str, Any]) -> bool:
    """data/metadata/fomo_score_ledger.jsonl 1줄 append. 분기 추세 추적."""
    try:
        FOMO_LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(FOMO_LEDGER_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return True
    except Exception as e:
        print(f"[fomo_score] ledger write fail: {e}", file=sys.stderr)
        return False


if __name__ == "__main__":
    # CLI: 실제 VAMS history 로 산출
    history = load_vams_history()
    if not history:
        # synthetic test
        from datetime import timezone as _tz
        now = datetime.now(KST)
        history = [
            {"type": "BUY", "timestamp": (now - timedelta(days=5)).isoformat(),
             "rule_id": "verdict_BUY", "ticker": "TICK1"},
            {"type": "SELL", "timestamp": (now - timedelta(days=3)).isoformat(),
             "rule_id": "verdict_to_AVOID", "ticker": "TICK2"},
            {"type": "BUY", "timestamp": (now - timedelta(days=2)).isoformat(),
             "ticker": "TICK3"},  # manual (no rule_id)
            {"type": "SELL", "timestamp": (now - timedelta(days=1)).isoformat(),
             "ticker": "TICK4"},  # manual
        ]
        print("[fomo_score] VAMS history 비어있음 — synthetic 4 events 로 test", file=sys.stderr)

    result = compute_fomo_score(history)
    print(json.dumps(result, indent=2, ensure_ascii=False))
