"""
사용자 액션 로깅 — 2-레이어 구조.

레이어:
  Layer 1 — KIS 자동 로깅: 실거래 체결 시점 (kis_broker)
  Layer 2 — Vercel API 수동 로깅: VAMS 승인/거절 + 수동 오버라이드 (order.py)
  CLI: 디버깅 전용. 메인 흐름 연결 금지

로깅하면 안 되는 것:
  - VAMS 시뮬레이션 실행
  - Brain 스캔
  - 단순 조회·클릭
  → 신호 오염 방지

저장:
  - data/history/trade_log.jsonl (append-only, git 저장)
  - Supabase trade_actions 테이블 (envvar 활성화 시 옵션)
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

from api.config import DATA_DIR, now_kst

_logger = logging.getLogger(__name__)
_PATH = os.path.join(DATA_DIR, "history", "trade_log.jsonl")

VALID_SOURCES = {"KIS_AUTO", "VERCEL_MANUAL", "VAMS_SIGNAL", "CLI_DEBUG"}
VALID_ACTIONS = {"BUY", "SELL", "HOLD", "OVERRIDE"}


def log_action(
    source: str,
    ticker: str,
    action: str,
    qty: Optional[float] = None,
    price: Optional[float] = None,
    filled_at: Optional[str] = None,
    reason: str = "",
    brain_grade: Optional[str] = None,
    brain_score: Optional[float] = None,
    regime: Optional[str] = None,
    vams_profile: Optional[str] = None,
    # 호환성: 옛 호출자(quantity/system_grade/user_note)가 있을 수 있음
    quantity: Optional[float] = None,
    system_grade: Optional[str] = None,
    user_note: Optional[str] = None,
) -> Dict[str, Any]:
    """
    액션 1건 로깅. append-only. KIS 체결 시점 또는 VAMS 승인/오버라이드 시만 호출.

    Args:
        source: "KIS_AUTO" | "VERCEL_MANUAL" | "VAMS_SIGNAL" | "CLI_DEBUG"
        ticker: 종목 코드
        action: "BUY" | "SELL" | "HOLD" | "OVERRIDE"
        qty: 수량 (또는 quantity 호환 인자)
        price: 단가
        filled_at: 체결 시각 (ISO KST). None 이면 now_kst() 사용
        reason: Brain 등급 / VAMS 시그널 / 수동 메모 등 컨텍스트
        brain_grade: 로깅 시점 Brain 등급 (system_grade 호환)
        brain_score: 로깅 시점 Brain score
        regime: 로깅 시점 매크로 국면 (NORMAL/WATCH/EARLY_BEAR/CONFIRMED_BEAR/PANIC)
        vams_profile: "aggressive" | "moderate" | "safe"
    """
    os.makedirs(os.path.dirname(_PATH), exist_ok=True)

    # 호환성 맵핑
    qty = qty if qty is not None else quantity
    brain_grade = brain_grade or system_grade
    if user_note and not reason:
        reason = user_note

    # 입력 검증
    src = (source or "").upper()
    if src not in VALID_SOURCES:
        _logger.warning("log_action invalid source=%s — UNKNOWN 으로 기록", source)
        src = "UNKNOWN"
    act = (action or "").upper()
    if act not in VALID_ACTIONS:
        _logger.warning("log_action invalid action=%s — UNKNOWN 으로 기록", action)
        act = "UNKNOWN"

    timestamp = now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00")
    entry = {
        "timestamp": timestamp,
        "filled_at": filled_at or timestamp,
        "source": src,
        "ticker": ticker,
        "action": act,
        "qty": qty,
        "price": price,
        "reason": reason,
        "brain_grade": brain_grade,
        "brain_score": brain_score,
        "regime": regime,
        "vams_profile": vams_profile,
        "agreement": _check_agreement(act, brain_grade),
    }

    # JSONL 기록 (메인 저장)
    with open(_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # Supabase 옵션 (envvar 활성화 시) — 실패해도 로깅은 성공으로 간주
    if os.environ.get("VERITY_SUPABASE_TRADE_LOG", "").lower() in ("1", "true", "yes"):
        _push_to_supabase(entry)

    return entry


def _push_to_supabase(entry: Dict[str, Any]) -> None:
    """Supabase trade_actions 테이블 push (옵션). 실패는 로깅만."""
    try:
        from api.utils.supabase_client import insert_row  # type: ignore
        insert_row("trade_actions", entry)
    except Exception as e:
        _logger.warning("supabase trade_log push failed: %s", e)


def _check_agreement(action: str, grade: Optional[str]) -> str:
    """본인 액션 vs 시스템 등급 일치 여부."""
    a = (action or "").upper()
    if a == "OVERRIDE":
        return "user_override"
    if not grade:
        return "no_signal"
    g = grade.upper()
    if a == "BUY" and g in ("BUY", "STRONG_BUY"):
        return "agree"
    if a in ("SELL", "HOLD") and g in ("AVOID", "STRONG_AVOID", "CAUTION"):
        return "agree"
    if a == "BUY" and g in ("AVOID", "STRONG_AVOID", "CAUTION"):
        return "disagree_user_buy_system_avoid"
    if a == "SELL" and g in ("BUY", "STRONG_BUY"):
        return "disagree_user_sell_system_buy"
    return "neutral"


def load_actions(days: int = 90, source_filter: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    최근 N일치 액션 로드.

    Args:
        source_filter: "KIS_AUTO" | "VERCEL_MANUAL" | None(전체)
    """
    if not os.path.exists(_PATH):
        return []
    out = []
    cutoff = now_kst().timestamp() - days * 86400
    src_f = source_filter.upper() if source_filter else None
    with open(_PATH, "r", encoding="utf-8") as f:
        for line in f:
            try:
                e = json.loads(line)
                if src_f and e.get("source", "") != src_f:
                    continue
                e_ts = _parse_ts(e.get("timestamp", ""))
                if e_ts >= cutoff:
                    out.append(e)
            except (json.JSONDecodeError, ValueError):
                continue
    return out


def _parse_ts(ts_str: str) -> float:
    from datetime import datetime
    try:
        return datetime.fromisoformat(ts_str).timestamp()
    except (ValueError, TypeError):
        return 0.0


def summarize(days: int = 90, source_filter: Optional[str] = None) -> Dict[str, Any]:
    """기간 + source 별 요약 — 본인 vs 시스템 일치율."""
    actions = load_actions(days, source_filter=source_filter)
    if not actions:
        return {
            "days": days,
            "source_filter": source_filter,
            "total_actions": 0,
            "agreement_rate": None,
        }

    total = len(actions)
    agree = sum(1 for a in actions if a.get("agreement") == "agree")
    user_buy_system_avoid = sum(1 for a in actions if a.get("agreement") == "disagree_user_buy_system_avoid")
    user_sell_system_buy = sum(1 for a in actions if a.get("agreement") == "disagree_user_sell_system_buy")
    overrides = sum(1 for a in actions if a.get("agreement") == "user_override")

    # source 별 분해
    by_source: Dict[str, int] = {}
    for a in actions:
        s = a.get("source", "UNKNOWN")
        by_source[s] = by_source.get(s, 0) + 1

    return {
        "days": days,
        "source_filter": source_filter,
        "total_actions": total,
        "agreement_count": agree,
        "agreement_rate": round(agree / total * 100, 1) if total else None,
        "user_buy_system_avoid": user_buy_system_avoid,
        "user_sell_system_buy": user_sell_system_buy,
        "overrides": overrides,
        "no_signal_count": sum(1 for a in actions if a.get("agreement") == "no_signal"),
        "by_source": by_source,
    }
