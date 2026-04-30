"""
trade_plan v0_heuristic — verdict 옆에 entry/exit/position 표시값을 산출하는 보조 레이어.

설계 원칙 (2026-04-30 결정):
- 결정 룰은 단순 (BB/MA20/RSI 3개 AND), 자동 액션은 verdict 상태 전이만.
- 가격 목표·손절 라인은 **표시값**일 뿐 자동 액션 X.
- position_pct 자동 산출 X — 권고 범위만.
- expected_return: 백테스트 quintile 결과 연결 전 None.
- A 단계 학습 데이터 수집을 위해 진입 후보(verdict BUY 신규 + entry_active) 발생 시
  진입 시점의 풍부한 피처 스냅샷을 trade_plan_v0_log.jsonl 에 append.

vercel-api/api/stock.py 의 _build_trade_plan 과 동일 로직 — v1 단계에서 통합 예정.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Optional


def _current_action_from_rec(rec: str) -> str:
    if rec == "BUY":
        return "보유 유지 / 신규 진입 검토"
    if rec == "WATCH":
        return "관망 — BUY 강등 시 부분 축소"
    return "청산 권고"


def _skeleton(rec: str, note: str = "기술적 데이터 부족 — 산출 보류") -> dict:
    return {
        "rec": rec,
        "entry_zone": None,
        "position_pct": None,
        "position_pct_range": None,
        "exit_target": None,
        "stop_loss": None,
        "transition_triggers": None,
        "expected_return": None,
        "version": "v0_skeleton",
        "note": note,
    }


def build_trade_plan_v0(stock: dict, judgment: dict) -> dict:
    rec = judgment.get("recommendation", "WATCH")
    tech = stock.get("technical", {}) or {}
    price = float(stock.get("price", 0) or 0)
    if price <= 0:
        return _skeleton(rec)

    bb_lower = float(tech.get("bb_lower", 0) or 0)
    bb_upper = float(tech.get("bb_upper", 0) or 0)
    ma20 = float(tech.get("ma20", 0) or 0)
    rsi_v = tech.get("rsi")
    rsi = float(rsi_v) if rsi_v is not None else 50.0

    if bb_lower <= 0 or bb_upper <= 0 or ma20 <= 0:
        return _skeleton(rec)

    cond_verdict = (rec == "BUY")
    cond_position = bb_lower <= price <= ma20
    cond_rsi = rsi <= 50
    entry_active = cond_verdict and cond_position and cond_rsi

    if rec == "BUY":
        entry_low = round(bb_lower)
        entry_high = round(min(ma20, price))
        if entry_low >= entry_high:
            entry_low = round(price * 0.95)
            entry_high = round(price)

        unmet = []
        if not cond_position:
            if price > ma20:
                unmet.append(f"현재가 {round(price):,} > MA20 {round(ma20):,} (구간 위)")
            elif price < bb_lower:
                unmet.append(f"현재가 {round(price):,} < BB하단 {round(bb_lower):,} (구간 아래)")
        if not cond_rsi:
            unmet.append(f"RSI {rsi:.0f} > 50 (단기 과열)")

        if entry_active:
            trigger = f"BUY + BB하단~MA20 + RSI {rsi:.0f}≤50 — 진입 가능"
        else:
            trigger = "진입 대기 — " + " · ".join(unmet) if unmet else "진입 대기"

        entry_zone = {
            "low": entry_low,
            "high": entry_high,
            "trigger": trigger,
            "active": entry_active,
        }

        target_price = round(min(bb_upper, ma20 * 1.12))
        if target_price <= price:
            target_price = round(price * 1.10)
        exit_target = {
            "price": target_price,
            "condition": "BB 상단 또는 MA20 × 1.12 — 참고 표시 (자동 액션 X)",
        }

        stop_price = round(min(entry_low * 0.92, price * 0.92))
        stop_loss = {
            "price": stop_price,
            "condition": "진입가 -8% — 가격 도달 시 수동 손절 검토",
        }
        position_pct_range = {"min": 5, "max": 15, "note": "단일 종목 한도 — portfolio 보고 수동 결정"}
    elif rec == "WATCH":
        entry_zone = None
        exit_target = None
        stop_loss = None
        position_pct_range = {"min": 0, "max": 5, "note": "관망 우선 — 진입 시 시범 비중"}
    else:
        entry_zone = None
        exit_target = None
        stop_loss = None
        position_pct_range = {"min": 0, "max": 0, "note": "회피"}

    transition_triggers = {
        "current_verdict": rec,
        "current_action": _current_action_from_rec(rec),
        "rules": [
            "BUY → WATCH 강등 시: 50% 축소 권고",
            "→ AVOID 강등 시: 전량 청산 권고",
            "진입가 -8% 이탈 시: 수동 손절 검토",
        ],
    }

    return {
        "rec": rec,
        "entry_zone": entry_zone,
        "position_pct": None,
        "position_pct_range": position_pct_range,
        "exit_target": exit_target,
        "stop_loss": stop_loss,
        "transition_triggers": transition_triggers,
        "expected_return": None,
        "version": "v0_heuristic",
        "note": "결정 룰 단순(BB/MA/RSI). 자동 액션은 verdict 상태 전이만. 검증 전 — 본인 운영 참고",
    }


# ── 진입 후보 로깅 ────────────────────────────────────────
# 풍부한 피처 스냅샷을 row 1개로 jsonl 에 append. A 단계에서 사후 회귀 분석 데이터로 사용.
def _snapshot_features(stock: dict) -> dict:
    tech = stock.get("technical", {}) or {}
    flow = stock.get("flow", {}) or {}
    mf = stock.get("multi_factor", {}) or {}
    return {
        "price": stock.get("price"),
        "ma20": tech.get("ma20"),
        "ma60": tech.get("ma60"),
        "ma120": tech.get("ma120"),
        "bb_lower": tech.get("bb_lower"),
        "bb_upper": tech.get("bb_upper"),
        "bb_position": tech.get("bb_position"),
        "rsi": tech.get("rsi"),
        "macd_hist": tech.get("macd_hist"),
        "vol_ratio": tech.get("vol_ratio"),
        "vol_direction": tech.get("vol_direction"),
        "trend_strength": tech.get("trend_strength"),
        "technical_score": tech.get("technical_score"),
        "safety_score": stock.get("safety_score"),
        "flow_score": flow.get("flow_score"),
        "foreign_net": flow.get("foreign_net"),
        "institution_net": flow.get("institution_net"),
        "foreign_5d_sum": flow.get("foreign_5d_sum"),
        "institution_5d_sum": flow.get("institution_5d_sum"),
        "foreign_ratio": flow.get("foreign_ratio"),
        "multi_score": mf.get("multi_score"),
        "grade": mf.get("grade"),
        "sector": stock.get("sector") or stock.get("industry"),
        "market": stock.get("market"),
        "company_type": stock.get("company_type"),
        "gold_insight": stock.get("gold_insight"),
        "silver_insight": stock.get("silver_insight"),
    }


def _log_dir() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(here, "..", "data", "metadata"))


def _log_path() -> str:
    return os.path.join(_log_dir(), "trade_plan_v0_log.jsonl")


def _read_open_cases() -> dict[str, str]:
    """현재 'open' 상태인 (ticker → suggested_at) 매핑.
    같은 종목이 BUY 유지 중이면 중복 append 안 함. BUY 끊긴 후 재진입은 새 row.
    """
    path = _log_path()
    if not os.path.exists(path):
        return {}
    open_map: dict[str, str] = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                t = row.get("ticker")
                if not t:
                    continue
                if row.get("closed_at"):
                    open_map.pop(t, None)
                else:
                    open_map[t] = row.get("suggested_at", "")
    except Exception:
        return {}
    return open_map


def maybe_log_entry_candidate(
    stock: dict,
    judgment: dict,
    plan: dict,
    *,
    prev_recommendation: Optional[str] = None,
) -> Optional[str]:
    """진입 후보 발생 시 jsonl 에 append. row id (suggested_at) 또는 None 반환.

    조건:
    - plan["entry_zone"]["active"] == True (BUY + 가격구간 + RSI 충족)
    - 현재 동일 ticker 의 'open' row 가 없음 (중복 방지)
    """
    ez = plan.get("entry_zone") or {}
    if not ez.get("active"):
        return None
    ticker = stock.get("ticker")
    if not ticker:
        return None

    try:
        open_map = _read_open_cases()
        if ticker in open_map:
            return None  # 이미 열린 케이스
    except Exception:
        open_map = {}

    suggested_at = datetime.now(timezone.utc).isoformat()
    row = {
        "suggested_at": suggested_at,
        "ticker": ticker,
        "name": stock.get("name"),
        "verdict": judgment.get("recommendation"),
        "prev_verdict": prev_recommendation,
        "entry_zone": ez,
        "exit_target": plan.get("exit_target"),
        "stop_loss": plan.get("stop_loss"),
        "position_pct_range": plan.get("position_pct_range"),
        "snapshot": _snapshot_features(stock),
        "version": plan.get("version"),
        "horizons": [5, 14, 30],
        "followups": {},   # cron 이 5/14/30d 후 채워넣음
        "closed_at": None,
    }

    os.makedirs(_log_dir(), exist_ok=True)
    with open(_log_path(), "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return suggested_at


def mark_case_closed(ticker: str, *, reason: str) -> int:
    """ticker 의 open row 를 closed 로 마킹 (verdict 가 BUY 가 아니게 됐을 때).
    파일 전체 재기록. 닫은 row 수 반환.
    """
    path = _log_path()
    if not os.path.exists(path):
        return 0
    rows = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
    except Exception:
        return 0

    closed_at = datetime.now(timezone.utc).isoformat()
    n = 0
    for r in rows:
        if r.get("ticker") == ticker and not r.get("closed_at"):
            r["closed_at"] = closed_at
            r["close_reason"] = reason
            n += 1
    if n == 0:
        return 0
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return n
