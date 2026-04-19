"""
Timing Signal Watcher — 매수/매도 타이밍 변화 감지 + 텔레그램 수동 알림.

recommendations[].timing.action 이 이전 사이클과 달라졌을 때만 알림.
쿨다운으로 노이즈 컷, 보유중 종목은 매도 시그널 강조.

상태 파일: data/.timing_state.json
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from api.config import DATA_DIR

KST = timezone(timedelta(hours=9))

_STATE_PATH = os.path.join(DATA_DIR, ".timing_state.json")

_COOLDOWN_HOURS = 4

_BUY_ACTIONS = {"BUY", "STRONG_BUY"}
_SELL_ACTIONS = {"SELL", "STRONG_SELL"}
_NEUTRAL_ACTIONS = {"HOLD"}

_TRANSITION_SIGNIFICANCE = {
    ("HOLD", "BUY"): "enter_buy",
    ("HOLD", "STRONG_BUY"): "enter_strong_buy",
    ("BUY", "STRONG_BUY"): "escalate_buy",
    ("STRONG_BUY", "HOLD"): "cool_down",
    ("STRONG_BUY", "SELL"): "reverse_sell",
    ("STRONG_BUY", "STRONG_SELL"): "reverse_strong_sell",
    ("BUY", "HOLD"): "cool_down",
    ("BUY", "SELL"): "reverse_sell",
    ("BUY", "STRONG_SELL"): "reverse_strong_sell",
    ("HOLD", "SELL"): "enter_sell",
    ("HOLD", "STRONG_SELL"): "enter_strong_sell",
    ("SELL", "STRONG_SELL"): "escalate_sell",
    ("SELL", "HOLD"): "recover",
    ("SELL", "BUY"): "recover_strong",
    ("STRONG_SELL", "BUY"): "recover_strong",
    ("STRONG_SELL", "HOLD"): "recover",
}


def _now() -> datetime:
    return datetime.now(KST)


def _load_state() -> Dict[str, Any]:
    try:
        with open(_STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_state(state: Dict[str, Any]) -> None:
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(_STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _cooldown_ok(last_sent_at: Optional[str], now: datetime) -> bool:
    if not last_sent_at:
        return True
    try:
        last = datetime.fromisoformat(last_sent_at)
    except Exception:
        return True
    return (now - last) >= timedelta(hours=_COOLDOWN_HOURS)


def detect_transitions(
    recommendations: List[Dict[str, Any]],
    held_tickers: Optional[set] = None,
    state: Optional[Dict[str, Any]] = None,
    now: Optional[datetime] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """recommendations에서 action 전이를 감지한다.

    Args:
        recommendations: portfolio.json의 recommendations 리스트
        held_tickers: 현재 보유중인 티커 집합 (매도 시그널 강조용)
        state: 이전 상태 dict (None이면 파일에서 로드)
        now: 현재 시각 (테스트용 주입)

    Returns:
        (transitions, new_state): 알림할 전이 목록과 저장할 새 상태
    """
    if held_tickers is None:
        held_tickers = set()
    if state is None:
        state = _load_state()
    if now is None:
        now = _now()

    new_state = dict(state)
    transitions: List[Dict[str, Any]] = []

    for r in recommendations:
        ticker = str(r.get("ticker", "")).strip()
        if not ticker:
            continue
        timing = r.get("timing") or {}
        action = str(timing.get("action", "HOLD")).upper()
        score = int(timing.get("timing_score", 50) or 50)
        reasons = timing.get("reasons") or []

        prev = state.get(ticker) or {}
        prev_action = str(prev.get("last_action", "HOLD")).upper()
        last_sent_at = prev.get("last_sent_at")

        new_state[ticker] = {
            "last_action": action,
            "last_score": score,
            "last_sent_at": last_sent_at,
            "last_seen_at": now.isoformat(),
        }

        if action == prev_action:
            continue

        transition_key = (prev_action, action)
        significance = _TRANSITION_SIGNIFICANCE.get(transition_key)
        if not significance:
            continue

        is_buy_signal = action in _BUY_ACTIONS
        is_sell_signal = action in _SELL_ACTIONS
        is_held = ticker in held_tickers

        if is_buy_signal and is_held:
            continue
        if is_sell_signal and not is_held and significance not in (
            "enter_strong_sell", "reverse_strong_sell", "escalate_sell",
        ):
            continue

        if not _cooldown_ok(last_sent_at, now):
            continue

        transitions.append({
            "ticker": ticker,
            "name": r.get("name", ticker),
            "from_action": prev_action,
            "to_action": action,
            "significance": significance,
            "score": score,
            "prev_score": int(prev.get("last_score", 50) or 50),
            "reasons": list(reasons)[:3],
            "is_held": is_held,
            "recommendation": r.get("recommendation", ""),
            "safety_score": int(r.get("safety_score", 0) or 0),
            "price": r.get("price"),
            "currency": r.get("currency", "KRW"),
        })
        new_state[ticker]["last_sent_at"] = now.isoformat()

    return transitions, new_state


def run_timing_watcher(portfolio: Dict[str, Any]) -> List[Dict[str, Any]]:
    """portfolio.json에서 recommendations + 보유종목을 읽어 전이를 감지하고 상태 저장.

    Returns:
        감지된 전이 리스트 (텔레그램 알림 대상)
    """
    recs = portfolio.get("recommendations") or []
    holdings = portfolio.get("vams", {}).get("holdings") or []
    held = {str(h.get("ticker", "")).strip() for h in holdings if h.get("ticker")}

    transitions, new_state = detect_transitions(recs, held_tickers=held)

    _save_state(new_state)
    return transitions
