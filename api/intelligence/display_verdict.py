# -*- coding: utf-8 -*-
"""display_verdict — 배지(recommendation) 단일 소유 = Brain + 강등 전용 게이트.

2026-08-03 PM 승인 ("사이트를 뜯어 고쳐야 하는거 아닌가") — 승인 순서
(① 측정 정화 → ② 재채점 → ③ 표시 게이트)의 ③.

배경 (실측):
  rec 배지 소유자가 LLM 합의(claude_analyst → pro override → light override 3중)라
  run 간 배지 멤버가 전원 교체 수준으로 흔들림 — 2026-08-03 하루에
  16:28 산출 BUY={기아, RRC} → 20:03 산출 BUY={네이버, NEM}. 브레인 상위 12에
  없는 종목이 배지 BUY 로 노출 (판정 소유 3중화).

설계:
  base = verity_brain.grade  (red flag·macro cap 이 이미 반영된 자체 산식 최종 등급)
  게이트 = **내리기만** (올리기 불가 — 보수 단방향이라 곡선맞추기 위험 구조적 차단):
    ① base 가 BUY 이상 && grade_confidence == "soft"(임계 경계 5점 이내)
       → 한 단계 강등. 62점 턱걸이 BUY 가 74점 firm BUY 와 같은 배지를 달던 문제.
    ② base 가 BUY 이상 && timing.action == "SELL"
       → WATCH 강등. "동시 confirm 시 강한 신호" 설계 의도의 역방향(정면 충돌) 처리.
  정렬: 최종 BUY 이상 && timing.action == "BUY" → aligned=True (설계 의도의 실현 표기).
  LLM 합의는 analyst_view 로 보존 — 참고 관측으로 강등, 배지 소유권 상실 (RULE 6:
  LLM 이 최종 판단 간판을 소유하면 자체 산식 trail 이 아니라 "ChatGPT 도 하는 판단"이 간판).

불변 조건:
  · 산식 점수·가중치·임계 = 무변경 (RULE 7 — 표시 집계 레이어만 신설)
  · 강등 전용이므로 배지 등급 ≤ position_guide 적용 등급 — 배지 BUY 인데 가이드가
    "WATCH 상한 3%" 인 모순(2026-08-02 GOOGL 실측)이 구조적으로 소멸
  · 브레인 미채점 종목(grade 부재) = 게이트 불가 → 기존 rec 유지 + 미채점 표기

공개 노출: display_verdict 키는 publish sanitize 의 STRIP_PAT(r"verdict") 에 자동
포착되어 공개 blob 에서 제거된다. analyst_view 는 STRIP_KEYS 명시 추가 (동 커밋).
recommendation 문자열만 종전대로 공개 — 값이 정직해질 뿐 스키마 불변.
"""
from __future__ import annotations

from typing import Any, Dict

GRADE_ORDER = ["STRONG_BUY", "BUY", "WATCH", "CAUTION", "AVOID"]
_VALIDATION_NOTE = "가설 — 자체 산식 N<252 IC 게이트(2027-05) 미검증"
_RATE_SHIELD_THRESHOLD = 4.5  # 미 10Y 금리 방패 임계 (B1+B2 2026-05-18 등록 상수 — 재정의 아님)


def _demote(grade: str, steps: int = 1) -> str:
    try:
        i = GRADE_ORDER.index(grade)
    except ValueError:
        return "WATCH"
    return GRADE_ORDER[min(i + steps, len(GRADE_ORDER) - 1)]


# F1 pullback_hold 임계 — 직전 5거래일 +15% 이상 급등 (PREREG_SIGNAL_FILTERS §F1, LOCKED)
_PULLBACK_SURGE_PCT = 15.0


def _trigger_condition(stock: Dict[str, Any], final: str, base: str,
                       timing_action: Any) -> Dict[str, Any] | None:
    """F1 조건부 신호 (PREREG_SIGNAL_FILTERS_2026_08_04 §F1 — 표시 전용, 산식 불변).

    사례 = 기아: 시스템 "BUY" vs 오퍼레이터 "MA20 회복 후 분할" — 시스템이 발동 조건을
    말하지 못하던 갭. 대상 = 최종 배지 WATCH ∧ brain_score ≥ 60.
    유형 판정 = 등록 문서 나열 순 first-match (결정론): ma20_reclaim → timing_align →
    pullback_hold. 전 조건 일봉 산술만 — LLM 재량 0 (RULE 6). v0 = 표시 전용,
    집행 연결(E1 확장) = 별도 재등록.
    """
    vb = stock.get("verity_brain") or {}
    brain_score = vb.get("brain_score")
    if final != "WATCH" or not isinstance(brain_score, (int, float)) or brain_score < 60:
        return None
    tech = stock.get("technical") or {}
    price = tech.get("price") or stock.get("current_price")
    ma20 = tech.get("ma20")
    if isinstance(price, (int, float)) and isinstance(ma20, (int, float)) \
            and ma20 > 0 and price < ma20:
        return {"type": "ma20_reclaim", "ma20": round(float(ma20)), "price": round(float(price)),
                "message": f"MA20({round(float(ma20)):,}) 회복 시 관심 승격"}
    if base in ("STRONG_BUY", "BUY") and timing_action != "BUY":
        return {"type": "timing_align", "message": "타이밍 정렬 시 aligned 후보"}
    r5 = tech.get("return_5d_pct")
    if isinstance(r5, (int, float)) and r5 >= _PULLBACK_SURGE_PCT \
            and isinstance(price, (int, float)):
        return {"type": "pullback_hold", "prev_close": round(float(price)), "surge_5d_pct": r5,
                "message": f"되돌림에서 {round(float(price)):,} 유지 확인"}
    return None


def apply_display_verdict(stock: Dict[str, Any]) -> Dict[str, Any]:
    """analyzed 레코드 1건의 배지를 Brain 소유로 교정 (in-place, 반환 동일 객체).

    파이프라인 최종 지점(모든 LLM override 이후, portfolio 저장 직전)에서 호출한다 —
    이보다 앞이면 pro/light override 가 다시 덮어써 게이트가 무효화된다.
    """
    vb = stock.get("verity_brain") or {}
    base = vb.get("grade")
    analyst_view = stock.get("recommendation")

    if base not in GRADE_ORDER:
        # 브레인 미채점 — 소유권 이전 불가. LLM rec 유지하되 출처를 정직하게 표기.
        stock["display_verdict"] = {
            "final": analyst_view, "base_grade": None, "gates": ["brain_ungraded"],
            "analyst_view": analyst_view, "aligned": False,
            "owner": "analyst_fallback", "validation": _VALIDATION_NOTE,
        }
        return stock

    final = base
    gates = []

    if final in ("STRONG_BUY", "BUY") and vb.get("grade_confidence") == "soft":
        final = _demote(final)
        gates.append("soft_boundary")  # 임계 경계권 — 승격 차단

    timing_action = (stock.get("timing") or {}).get("action")
    if final in ("STRONG_BUY", "BUY") and timing_action == "SELL":
        final = "WATCH"
        gates.append("timing_conflict")  # 펀더멘털 우위 · 기술 역배열 충돌

    aligned = final in ("STRONG_BUY", "BUY") and timing_action == "BUY"

    stock["analyst_view"] = analyst_view
    stock["recommendation"] = final
    stock["display_verdict"] = {
        "final": final, "base_grade": base, "gates": gates,
        "analyst_view": analyst_view, "aligned": aligned,
        "owner": "brain", "validation": _VALIDATION_NOTE,
    }
    trig = _trigger_condition(stock, final, base, timing_action)
    if trig:
        stock["display_verdict"]["trigger_condition"] = trig
    return stock


def build_system_action(portfolio: Dict[str, Any], analyzed) -> Dict[str, Any]:
    """시스템 작용 요약 — 매크로·게이트가 지금 파이프라인에 미치는 실작용의 집계 (표시 전용).

    2026-08-03 PM ("/macro 1번 패널"): 매크로 페이지가 지표 나열에 그침 — "그래서 시스템이
    지금 뭘 하고 있나"를 한 패널로. 산식 불변 — 이미 산출된 값의 집계만.
    소비처 = 오퍼레이터 사이트(알파파운더) SystemActionPanel. 공개 blob 에서는
    sanitize STRIP_KEYS("system_action") 로 제거 (오퍼레이터 전용).
    """
    from datetime import datetime, timedelta, timezone
    _kst = timezone(timedelta(hours=9))

    macro = portfolio.get("macro") or {}
    us10 = (macro.get("us_10y") or {}).get("value")
    vb_top = portfolio.get("verity_brain") or {}
    mo = vb_top.get("macro_override") or []
    if isinstance(mo, dict):
        mo = [mo]
    shield = next((o for o in mo if isinstance(o, dict)
                   and o.get("mode") in ("yield_defense", "kr_rate_defense")), None)
    shield_on = shield is not None or (isinstance(us10, (int, float)) and us10 >= _RATE_SHIELD_THRESHOLD)

    quadrant: Dict[str, Any] = {}
    try:
        from api.intelligence.verity_brain import detect_economic_quadrant
        q = detect_economic_quadrant(portfolio) or {}
        quadrant = {k: q.get(k) for k in ("quadrant", "label", "favored", "unfavored")
                    if q.get(k) is not None}
    except Exception:  # 표시 데이터가 파이프라인을 못 죽인다
        pass

    mults = sorted(m for m in ((s.get("macro_multiplier") or {}).get("multiplier")
                               for s in analyzed) if isinstance(m, (int, float)))
    buys = [s for s in analyzed if s.get("recommendation") in ("STRONG_BUY", "BUY")]

    return {
        "as_of": datetime.now(_kst).isoformat(timespec="seconds"),
        "rate_shield": {
            "on": bool(shield_on),
            "us_10y": us10,
            "threshold": _RATE_SHIELD_THRESHOLD,
            "grade_cap": (shield or {}).get("max_grade"),
            "label": (shield or {}).get("label") or ("금리 방패" if shield_on else None),
            "effect": "발동 중 — 등급 상한 WATCH · 현금 비중 확대 권고" if shield_on else "미발동",
        },
        "quadrant": quadrant,
        "macro_multiplier_median": (mults[len(mults) // 2] if mults else None),
        "verdict_gate": {
            "buy_count": len(buys),
            "aligned": [s.get("ticker") for s in buys
                        if (s.get("display_verdict") or {}).get("aligned")],
            "gated_count": sum(1 for s in analyzed
                               if (s.get("display_verdict") or {}).get("gates")),
            "owner": "brain",
        },
        "validation": _VALIDATION_NOTE,
        "_note": "표시 전용 · 산식 불변 — 이미 산출된 작용값의 집계 (오퍼레이터)",
    }
