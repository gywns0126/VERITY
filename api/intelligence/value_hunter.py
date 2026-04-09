"""
Value Hunter — 저평가 발굴 엔진

퀀트 시스템(백테스트 아카이브)의 승률·수익률이 일정 임계를 넘으면
게이트가 열리고, 저평가(밸류) 후보를 별도 발굴해 portfolio["value_hunt"]에 저장.

게이트 기준(설정값으로 조정 가능):
  - 14d 또는 30d 승률 >= VALUE_HUNT_WIN_RATE_MIN (기본 55%)
  - 표본 수 >= VALUE_HUNT_MIN_TRADES (기본 10)
  - avg_return > 0 (양수 수익)

밸류 스코어 (0~100):
  PER 30점 + PBR 25점 + ROE 20점 + 배당 10점 + 품질(FCF/영업이익률) 10점 + 부채 5점
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from api.config import (
    VALUE_HUNT_WIN_RATE_MIN,
    VALUE_HUNT_MIN_TRADES,
    VALUE_HUNT_TOP_N,
    VALUE_HUNT_LOOKBACK,
    now_kst,
)


# ─────────────────────────────────────────────
# 1. 게이트: 백테스트 성과 임계 체크
# ─────────────────────────────────────────────

def check_value_hunt_gate(backtest_stats: Dict[str, Any]) -> Tuple[bool, str]:
    """
    백테스트 아카이브 통계로 저평가 발굴 게이트 개폐 판단.

    Returns:
        (gate_open: bool, reason: str)
    """
    if not backtest_stats:
        return False, "백테스트 데이터 없음"

    periods: Dict[str, Any] = backtest_stats.get("periods", {})
    if not periods:
        return False, "백테스트 기간 데이터 없음"

    # VALUE_HUNT_LOOKBACK (예: "14d,30d") 에서 우선순위대로 체크
    lookback_keys = [k.strip() for k in VALUE_HUNT_LOOKBACK.split(",") if k.strip()]
    if not lookback_keys:
        lookback_keys = ["14d", "30d"]

    for period_key in lookback_keys:
        info = periods.get(period_key)
        if not info:
            continue

        hit_rate = info.get("hit_rate")
        avg_return = info.get("avg_return")
        total_recs = info.get("total_recs", 0)

        if hit_rate is None or avg_return is None:
            continue
        if total_recs < VALUE_HUNT_MIN_TRADES:
            continue
        if hit_rate < VALUE_HUNT_WIN_RATE_MIN:
            continue
        if avg_return <= 0:
            continue

        sharpe = info.get("sharpe")
        sharpe_note = f" / Sharpe {sharpe:.2f}" if sharpe is not None else ""
        reason = (
            f"{period_key} 승률 {hit_rate}% / 평균수익 {avg_return:+.2f}%{sharpe_note}"
            f" (표본 {total_recs}개)"
        )
        return True, reason

    # 임계 미달 시 가장 가까운 수치를 reason에 담아 반환
    best_hit = None
    best_key = None
    for k, info in periods.items():
        if info.get("hit_rate") is not None:
            if best_hit is None or info["hit_rate"] > best_hit:
                best_hit = info["hit_rate"]
                best_key = k

    if best_hit is not None:
        reason = (
            f"임계 미달 — 최고 승률 {best_hit}% ({best_key}),"
            f" 기준 {VALUE_HUNT_WIN_RATE_MIN}% / 최소 표본 {VALUE_HUNT_MIN_TRADES}개"
        )
    else:
        reason = f"임계 미달 — 기준 승률 {VALUE_HUNT_WIN_RATE_MIN}%, 표본 {VALUE_HUNT_MIN_TRADES}개"

    return False, reason


# ─────────────────────────────────────────────
# 2. 밸류 스코어 계산
# ─────────────────────────────────────────────

def compute_value_score(stock: Dict[str, Any]) -> Tuple[int, List[str]]:
    """
    저평가 종합 스코어 (0~100) + 근거 시그널 목록 반환.

    배점:
      PER  30점 — 낮을수록 좋음 (단, 적자 제외)
      PBR  25점 — 낮을수록 좋음 (자산 대비 가격)
      ROE  20점 — 높을수록 좋음 (수익성 보장)
      배당 10점 — 배당수익률
      품질 10점 — FCF 양수 + 영업이익률
      부채  5점 — 부채비율 낮을수록
    """
    score = 0
    signals: List[str] = []

    per: float = stock.get("per") or 0
    pbr: float = stock.get("pbr") or 0
    roe: float = stock.get("roe") or 0
    div_yield: float = stock.get("div_yield") or 0
    op_margin: float = stock.get("operating_margin") or 0
    debt: float = stock.get("debt_ratio") or 0

    # FCF: DART cashflow 우선, 없으면 stock 직접 값
    dart_cf = (stock.get("dart_financials") or {}).get("cashflow") or {}
    fcf: float = dart_cf.get("free_cashflow") or stock.get("free_cashflow") or 0

    # ── PER (30점) ──
    if per > 0:
        if per <= 8:
            score += 30
            signals.append(f"PER {per:.1f}배 극저평가")
        elif per <= 12:
            score += 24
            signals.append(f"PER {per:.1f}배 저평가")
        elif per <= 18:
            score += 16
            signals.append(f"PER {per:.1f}배 적정")
        elif per <= 28:
            score += 6
        # per > 28: 0점

    # ── PBR (25점) ──
    if pbr > 0:
        if pbr <= 0.7:
            score += 25
            signals.append(f"PBR {pbr:.2f} 자산가치 대비 초저평가")
        elif pbr <= 1.0:
            score += 20
            signals.append(f"PBR {pbr:.2f} 자산가치 이하")
        elif pbr <= 1.5:
            score += 12
            signals.append(f"PBR {pbr:.2f} 적정")
        elif pbr <= 2.5:
            score += 4
        # pbr > 2.5: 0점

    # ── ROE (20점) — 수익성 필터 겸용 ──
    if roe >= 20:
        score += 20
        signals.append(f"ROE {roe:.1f}% 고수익")
    elif roe >= 15:
        score += 15
        signals.append(f"ROE {roe:.1f}% 우량")
    elif roe >= 10:
        score += 10
        signals.append(f"ROE {roe:.1f}% 양호")
    elif roe >= 5:
        score += 5
    # roe < 5 또는 음수: 0점

    # ── 배당수익률 (10점) ──
    if div_yield >= 5:
        score += 10
        signals.append(f"배당수익률 {div_yield:.1f}% 고배당")
    elif div_yield >= 3:
        score += 8
        signals.append(f"배당수익률 {div_yield:.1f}%")
    elif div_yield >= 1.5:
        score += 4
    elif div_yield > 0:
        score += 1

    # ── 품질: FCF + 영업이익률 (10점) ──
    fcf_positive = fcf > 0
    if fcf_positive and op_margin >= 12:
        score += 10
        signals.append(f"FCF 양수 + 영업이익률 {op_margin:.1f}%")
    elif fcf_positive and op_margin >= 6:
        score += 7
        signals.append(f"FCF 양수 / 영업이익률 {op_margin:.1f}%")
    elif fcf_positive:
        score += 4
        signals.append("FCF 양수")
    elif op_margin >= 10:
        score += 4
        signals.append(f"영업이익률 {op_margin:.1f}%")
    elif op_margin >= 5:
        score += 2

    # ── 부채비율 (5점) ──
    if 0 < debt <= 25:
        score += 5
        signals.append(f"부채비율 {debt:.0f}% 건전")
    elif debt <= 50:
        score += 3
    elif debt <= 80:
        score += 1

    return min(score, 100), signals


def _passes_quality_filter(stock: Dict[str, Any]) -> Tuple[bool, str]:
    """
    가치 덫(Value Trap) 방지 최소 품질 조건.
    하나라도 걸리면 (False, 이유) 반환.
    """
    per: float = stock.get("per") or 0
    roe: float = stock.get("roe") or 0
    op_margin: float = stock.get("operating_margin") or 0
    debt: float = stock.get("debt_ratio") or 0

    if per < 0:
        return False, "적자(PER 음수)"
    if roe <= 0:
        return False, "ROE 0 이하(수익성 없음)"
    if op_margin <= 0:
        return False, "영업손실"
    if debt > 200:
        return False, f"부채비율 {debt:.0f}% 과다"

    return True, ""


# ─────────────────────────────────────────────
# 3. 메인 함수
# ─────────────────────────────────────────────

def run_value_hunt(
    candidates: List[Dict[str, Any]],
    backtest_stats: Optional[Dict[str, Any]],
    macro: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    저평가 발굴 파이프라인.

    Args:
        candidates: 이미 필터링된 종목 리스트 (stock_filter 출력)
        backtest_stats: evaluate_past_recommendations() 결과
        macro: 매크로 지표 (risk-off 국면에서 기준 강화에 사용)

    Returns:
        {
            "gate_open": bool,
            "gate_reason": str,
            "value_candidates": [...],
            "total_scored": int,
            "updated_at": str,
        }
    """
    gate_open, gate_reason = check_value_hunt_gate(backtest_stats or {})

    result: Dict[str, Any] = {
        "gate_open": gate_open,
        "gate_reason": gate_reason,
        "value_candidates": [],
        "total_scored": 0,
        "updated_at": now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
    }

    if not gate_open:
        print(f"  [ValueHunt] 게이트 닫힘 — {gate_reason}")
        return result

    # risk-off 국면이면 기준 강화: 최소 value_score 임계를 높임
    macro_score: int = (macro or {}).get("market_mood", {}).get("score", 50)
    min_value_score = 45 if macro_score >= 50 else 60  # risk-off = 보수적

    scored: List[Dict[str, Any]] = []
    for stock in candidates:
        ok, skip_reason = _passes_quality_filter(stock)
        if not ok:
            continue

        v_score, v_signals = compute_value_score(stock)
        if v_score < min_value_score:
            continue

        entry: Dict[str, Any] = {
            "ticker": stock.get("ticker"),
            "name": stock.get("name"),
            "value_score": v_score,
            "value_signals": v_signals,
            "per": stock.get("per"),
            "pbr": stock.get("pbr"),
            "roe": stock.get("roe"),
            "div_yield": stock.get("div_yield"),
            "operating_margin": stock.get("operating_margin"),
            "debt_ratio": stock.get("debt_ratio"),
            "price": stock.get("price"),
            "drop_from_high_pct": stock.get("drop_from_high_pct"),
            "safety_score": stock.get("safety_score"),
            "brain_score": stock.get("verity_brain", {}).get("brain_score"),
            "sector": stock.get("sector"),
        }
        # FCF 추가
        dart_cf = (stock.get("dart_financials") or {}).get("cashflow") or {}
        fcf = dart_cf.get("free_cashflow") or stock.get("free_cashflow")
        if fcf is not None:
            entry["free_cashflow"] = fcf

        scored.append(entry)

    # 밸류 스코어 내림차순 정렬 후 상위 N개
    scored.sort(key=lambda x: x["value_score"], reverse=True)
    top = scored[:VALUE_HUNT_TOP_N]

    result["value_candidates"] = top
    result["total_scored"] = len(scored)

    print(f"  [ValueHunt] 게이트 열림 ({gate_reason})")
    print(f"  [ValueHunt] 품질 통과 {len(scored)}개 → 상위 {len(top)}개 선정")
    for c in top:
        sigs = " | ".join(c["value_signals"][:3]) or "—"
        print(f"    {c['name']} 밸류 {c['value_score']}점 — {sigs}")

    return result
