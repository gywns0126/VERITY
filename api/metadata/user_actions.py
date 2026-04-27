"""
사용자 액션 로깅 — Quarterly~Annual 리포트의 "본인 vs 시스템 적중률" 비교용.

기록 대상:
  - 본인이 실제 매수/매도/관망 결정한 시점과 종목
  - 그 시점 시스템 추천 등급 (BUY/WATCH/AVOID)
  - 본인 결정과 시스템 일치/불일치 여부

집계:
  - 분기/반기/연간 단위로 "본인 따라 vs 시스템 따라" 가상 수익률 비교
  - 본인 결정이 시스템과 다를 때 어느 쪽이 더 자주 옳았는지

저장 위치: data/metadata/user_actions.jsonl (append-only)
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from api.config import DATA_DIR, now_kst

_PATH = os.path.join(DATA_DIR, "metadata", "user_actions.jsonl")


def log_action(
    ticker: str,
    action: str,  # "buy" | "sell" | "hold" | "watch"
    system_grade: Optional[str] = None,
    user_note: str = "",
    price: Optional[float] = None,
    quantity: Optional[float] = None,
) -> Dict[str, Any]:
    """본인 액션 1건 로깅. append-only."""
    os.makedirs(os.path.dirname(_PATH), exist_ok=True)
    entry = {
        "timestamp": now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "ticker": ticker,
        "action": action,
        "system_grade": system_grade,  # 본인 결정 시점 시스템 추천 등급
        "user_note": user_note,
        "price": price,
        "quantity": quantity,
        "agreement": _check_agreement(action, system_grade),
    }
    with open(_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def _check_agreement(action: str, grade: Optional[str]) -> str:
    """본인 액션 vs 시스템 등급 일치 여부."""
    if not grade:
        return "no_signal"
    a = action.lower()
    g = grade.upper()
    if a == "buy" and g in ("BUY", "STRONG_BUY"):
        return "agree"
    if a in ("sell", "watch", "hold") and g in ("AVOID", "STRONG_AVOID", "CAUTION"):
        return "agree"
    if a == "buy" and g in ("AVOID", "STRONG_AVOID", "CAUTION"):
        return "disagree_user_buy_system_avoid"
    if a == "sell" and g in ("BUY", "STRONG_BUY"):
        return "disagree_user_sell_system_buy"
    return "neutral"


def load_actions(days: int = 90) -> List[Dict[str, Any]]:
    """최근 N일치 액션 로드."""
    if not os.path.exists(_PATH):
        return []
    out = []
    cutoff = now_kst().timestamp() - days * 86400
    with open(_PATH, "r", encoding="utf-8") as f:
        for line in f:
            try:
                e = json.loads(line)
                ts_str = e.get("timestamp", "")
                # 단순 문자열 비교 (ISO 형식이라 정확)
                e_ts = _parse_ts(ts_str)
                if e_ts >= cutoff:
                    out.append(e)
            except (json.JSONDecodeError, ValueError):
                continue
    return out


def _parse_ts(ts_str: str) -> float:
    """ISO timestamp → epoch."""
    from datetime import datetime
    try:
        return datetime.fromisoformat(ts_str).timestamp()
    except (ValueError, TypeError):
        return 0.0


def summarize(days: int = 90) -> Dict[str, Any]:
    """기간별 요약 — 본인 vs 시스템 일치율."""
    actions = load_actions(days)
    if not actions:
        return {"days": days, "total_actions": 0, "agreement_rate": None}

    total = len(actions)
    agree = sum(1 for a in actions if a.get("agreement") == "agree")
    user_buy_system_avoid = sum(1 for a in actions if a.get("agreement") == "disagree_user_buy_system_avoid")
    user_sell_system_buy = sum(1 for a in actions if a.get("agreement") == "disagree_user_sell_system_buy")

    return {
        "days": days,
        "total_actions": total,
        "agreement_count": agree,
        "agreement_rate": round(agree / total * 100, 1) if total else None,
        "user_buy_system_avoid": user_buy_system_avoid,
        "user_sell_system_buy": user_sell_system_buy,
        "no_signal_count": sum(1 for a in actions if a.get("agreement") == "no_signal"),
    }
