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


def _demote(grade: str, steps: int = 1) -> str:
    try:
        i = GRADE_ORDER.index(grade)
    except ValueError:
        return "WATCH"
    return GRADE_ORDER[min(i + steps, len(GRADE_ORDER) - 1)]


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
    return stock
