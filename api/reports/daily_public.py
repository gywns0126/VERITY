"""
Daily 일반인용 리포트 — 텍스트 생성 모듈.

사용자가 정의한 5섹션 구조:
  1. COVER — "오늘 시장은 ___ 입니다"
  2. 제1섹션 — 지금 시장 온도
  3. 제2섹션 — 글로벌 경제 신호등 (미국/한국/환율)
  4. 제3섹션 — 잘 된 업종 / 부진한 업종
  5. 제4섹션 — 오늘 놓치면 안 될 뉴스
  6. 제5섹션 — VERITY 오늘 판단

dilution 헬퍼의 4개 가드 통합:
  - 검증 워터마크 (project_validation_plan): STRONG_BUY/🔥 자동 강등
  - 시점 표현 (feedback_macro_timestamp_policy): 매크로 지표 기준일 표기
  - AI fallback 정화 (feedback_ai_fallback_sanitization): raw 에러 노출 금지
  - cross-ref 일관성: 같은 개념 다중 라벨 충돌 방지

PDF 렌더링은 별도 모듈(daily_public_pdf.py)에서 이 텍스트를 받아 처리.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from api.mocks import mockable
from api.utils.dilution import (
    apply_grade_guard,
    apply_label_guard,
    brain_grade_from_score,
    build_dictionary_for_prompt,
    detect_cross_ref_conflicts,
    get_forbidden_phrases,
    get_principles,
    grade_label,
    is_validated,
    normalize_cross_ref,
    timestamp_label,
    translate_ai_fallback,
    validation_status_summary,
)

_logger = logging.getLogger(__name__)


# ─── 입력 데이터 압축 ─────────────────────────────────────────

def _build_macro_summary(macro: Dict[str, Any]) -> Dict[str, Any]:
    """매크로 dict → 일반인용 압축. 시점 라벨 포함."""
    if not isinstance(macro, dict):
        return {}

    vix = macro.get("vix") or {}
    usd_krw = macro.get("usd_krw") or {}
    us_10y = macro.get("us_10y") or {}
    sp500 = macro.get("sp500") or {}
    mood = macro.get("market_mood") or {}

    return {
        "vix": {
            "value": vix.get("value"),
            "change_pct": vix.get("change_pct"),
            "as_of_label": timestamp_label(vix.get("source"), vix.get("as_of")),
        },
        "usd_krw": {
            "value": usd_krw.get("value"),
            "change_pct": usd_krw.get("change_pct"),
            "as_of_label": timestamp_label(usd_krw.get("source"), usd_krw.get("as_of")),
        },
        "us_10y": {
            "value": us_10y.get("value"),
            "change_pct": us_10y.get("change_pct"),
            "as_of_label": timestamp_label(us_10y.get("source"), us_10y.get("as_of")),
        },
        "sp500": {
            "change_pct": sp500.get("change_pct"),
            "as_of_label": timestamp_label(sp500.get("source"), sp500.get("as_of")),
        },
        "mood_score": mood.get("score"),
        "mood_label": mood.get("label"),
        "collected_at": macro.get("collected_at"),
    }


def _build_sector_summary(sectors: list) -> Dict[str, list]:
    """섹터 리스트 → 잘 된 3개 / 부진한 3개."""
    if not isinstance(sectors, list) or not sectors:
        return {"winners": [], "losers": []}

    sorted_secs = sorted(
        sectors,
        key=lambda s: (s.get("change_pct") or 0),
        reverse=True,
    )
    winners = [
        {"name": s.get("name") or s.get("sector"), "change_pct": s.get("change_pct")}
        for s in sorted_secs[:3]
    ]
    losers = [
        {"name": s.get("name") or s.get("sector"), "change_pct": s.get("change_pct")}
        for s in sorted_secs[-3:][::-1]  # 가장 부진한 것부터
    ]
    return {"winners": winners, "losers": losers}


def _build_grade_distribution(verity_brain: Dict[str, Any], validated: bool, channel: str) -> Dict[str, str]:
    """
    Brain 시장 평균 점수 → 룰북 등급 매핑 + 가드 적용.
    v2.0 임계: STRONG_BUY 75+ / BUY 60-74 / WATCH 45-59 / CAUTION 30-44 / AVOID 30↓
    """
    mb = (verity_brain or {}).get("market_brain") or {}
    avg_score = mb.get("avg_brain_score")

    # 룰북에서 점수 → 등급 매핑 (단일 소스 오브 트루스)
    raw_grade = brain_grade_from_score(avg_score)

    # 검증 워터마크 가드 — 미검증 + public 이면 STRONG_BUY → BUY 자동 강등
    safe_grade = apply_grade_guard(raw_grade, validated=validated, channel=channel)

    # 룰북 라벨 (icon + label) 사용
    label = grade_label(safe_grade)
    # 라벨 가드 (🔥 자동 강등 — 룰북엔 🔥 없지만 향후 호환용)
    label = apply_label_guard(label, validated=validated, channel=channel)

    return {"label": label, "raw_grade": safe_grade, "score": avg_score}


def _build_events_summary(events: list, max_n: int = 3) -> list:
    """이벤트 캘린더 → D-7 이내 상위 N개 (날짜·수치 제거, 방향만)."""
    if not isinstance(events, list):
        return []
    out = []
    for ev in events[:max_n]:
        out.append({
            "name": ev.get("name") or ev.get("event"),
            "impact_summary": ev.get("impact_summary") or ev.get("description") or "",
            "kr_impact": ev.get("kr_impact"),
            "us_impact": ev.get("us_impact"),
        })
    return out


# ─── LLM 프롬프트 ────────────────────────────────────────────

def _build_prompt(
    macro_summary: Dict[str, Any],
    sector_summary: Dict[str, list],
    events_summary: list,
    grade_info: Dict[str, str],
    fallback_msg: Optional[str],
) -> str:
    """일반인용 5섹션 생성 LLM 프롬프트. 룰북 변환 사전 + 6대 원칙 + 금지 표현 모두 주입."""
    principles_text = "\n".join(f"- {p['rule']}" for p in get_principles())
    dictionary_block = build_dictionary_for_prompt()
    forbidden_text = ", ".join(f'"{p}"' for p in get_forbidden_phrases())

    macro_block = (
        f"VIX {macro_summary.get('vix', {}).get('value', '?')} "
        f"{macro_summary.get('vix', {}).get('as_of_label', '')}\n"
        f"USD/KRW {macro_summary.get('usd_krw', {}).get('value', '?')}원 "
        f"{macro_summary.get('usd_krw', {}).get('as_of_label', '')}\n"
        f"미10Y {macro_summary.get('us_10y', {}).get('value', '?')}% "
        f"{macro_summary.get('us_10y', {}).get('as_of_label', '')}\n"
        f"S&P500 변화 {macro_summary.get('sp500', {}).get('change_pct', '?')}%\n"
        f"시장무드 점수 {macro_summary.get('mood_score', '?')} ({macro_summary.get('mood_label', '?')})"
    )
    winners = ", ".join(f"{w.get('name')} ({w.get('change_pct'):+.1f}%)"
                        for w in sector_summary.get("winners", []) if w.get("name"))
    losers = ", ".join(f"{l.get('name')} ({l.get('change_pct'):+.1f}%)"
                       for l in sector_summary.get("losers", []) if l.get("name"))
    events_text = "\n".join(
        f"- {e.get('name')}: {e.get('impact_summary', '')[:200]}"
        for e in events_summary
    ) or "주요 이벤트 없음"

    fallback_note = f"\n[참고] AI 분석 시스템 메모: {fallback_msg}\n" if fallback_msg else ""

    return f"""[배경] 너는 VERITY 일반인용 리포트 작성자다. 평범한 직장인이 5분 안에 읽고 '오늘 시장 분위기'를 이해할 수 있게 써라.

[원칙]
{principles_text}

{dictionary_block}

[입력 데이터]
== 매크로 ==
{macro_block}

== 섹터 ==
잘 된 업종: {winners or '(데이터 없음)'}
부진한 업종: {losers or '(데이터 없음)'}

== 다가올 이벤트 (D-7) ==
{events_text}

== VERITY 시스템 등급 ==
{grade_info.get('label')} ({grade_info.get('raw_grade')})
{fallback_note}

[금지 사항]
- 종목명 절대 등장 금지
- Brain 점수, VCI, 팩트/심리 서브스코어, 모델명 노출 금지
- 영어 약자 그대로 사용 금지 — 위 변환 사전 라벨만 사용
- 수익 보장 표현 절대 금지: {forbidden_text}
- 날짜·수치 절대값 최소화. 방향만 (오름/내림/보합)

[출력 형식 — 반드시 JSON]
{{
  "cover": "오늘 시장은 [한 줄] 입니다 (15자 이내)",
  "section_temperature": {{
    "icon": "😰|😟|😐|🙂|😊",
    "summary": "한 줄 (지금 투자자들이 얼마나 긴장하고 있는지)",
    "detail": "2~3줄 (전문용어 없이)"
  }},
  "section_signals": {{
    "us": {{"icon": "🟢|🟡|🔴", "reason": "한 줄"}},
    "kr": {{"icon": "🟢|🟡|🔴", "reason": "한 줄"}},
    "fx": {{"icon": "🔼|➡️|🔽", "reason": "한 줄"}}
  }},
  "section_sectors": {{
    "winners": [{{"label": "쉬운 업종 이름", "reason": "왜 올랐는지 한 줄"}}],
    "losers": [{{"label": "쉬운 업종 이름", "reason": "왜 내렸는지 한 줄"}}]
  }},
  "section_events": [
    {{"description": "한 문장 (날짜·수치 없이 방향만)"}}
  ],
  "section_verity_judgment": {{
    "icon_label": "{grade_info.get('label')}",
    "reasoning": "2~3줄 (쉬운 말로)"
  }},
  "self_assessment": "지난 리포트 판단과 실제 결과 한 줄 (있으면)"
}}

JSON만 출력. 다른 텍스트 금지."""


# ─── 공개 함수 ────────────────────────────────────────────────

@mockable("daily_public_text")
def generate_daily_public_text(
    portfolio: Dict[str, Any],
    channel: str = "public",
    llm_caller: Optional[callable] = None,
) -> Dict[str, Any]:
    """
    Daily 일반인용 리포트 텍스트 생성.

    Args:
        portfolio: portfolio.json 데이터
        channel: "public" | "instagram" | "admin" (가드 동작 결정)
        llm_caller: 테스트 주입용. None 이면 Gemini 기본 사용.

    Returns:
        {
          "cover": str, "sections": {...}, "metadata": {...}, "_error": Optional[str]
        }
    """
    macro = portfolio.get("macro") or {}
    sectors = portfolio.get("sectors") or []
    events = portfolio.get("global_events") or portfolio.get("events") or []
    verity_brain = portfolio.get("verity_brain") or {}
    daily_report = portfolio.get("daily_report") or {}

    # Phase 1.5 — 검증 상태 자동 판정 (VAMS 데이터 또는 환경변수)
    vams = portfolio.get("vams") or {}
    val_summary = validation_status_summary(vams)
    validated = val_summary["validated"]

    macro_summary = _build_macro_summary(macro)
    sector_summary = _build_sector_summary(sectors)
    events_summary = _build_events_summary(events, max_n=3)
    grade_info = _build_grade_distribution(verity_brain, validated=validated, channel=channel)

    # 백엔드 fallback 메시지 → 일반인용 톤 변환 (또는 숨김)
    backend_fb = daily_report.get("ai_verdict") or daily_report.get("summary")
    public_fb = translate_ai_fallback(backend_fb)

    prompt = _build_prompt(macro_summary, sector_summary, events_summary, grade_info, public_fb)

    # Phase 1.5 — Brain 학습 시그널 누적 (Weekly+ 리포트 input)
    _log_brain_learning_safe(portfolio)

    # LLM 호출
    if llm_caller is None:
        llm_caller = _default_gemini_caller
    try:
        raw_text = llm_caller(prompt)
        parsed = _parse_llm_json(raw_text)
        _log_llm_cost_safe("daily_public_report", len(prompt) // 4,
                           len(raw_text) // 4 if raw_text else 0)
    except Exception as e:
        _logger.error("daily_public LLM call failed: %s", e, exc_info=True)
        _log_llm_cost_safe("daily_public_report", len(prompt) // 4, 0, success=False)
        return _empty_public_result(grade_info, val_summary, error=type(e).__name__)

    sections = {
        "temperature": parsed.get("section_temperature") or {},
        "signals": parsed.get("section_signals") or {},
        "sectors": parsed.get("section_sectors") or {},
        "events": parsed.get("section_events") or [],
        "verity_judgment": parsed.get("section_verity_judgment") or {},
        "self_assessment": parsed.get("self_assessment") or "",
    }
    # Phase 1.5 — cross-ref 후처리 (다중 라벨 충돌 검출)
    cross_ref_warnings = _detect_section_cross_refs(sections)

    return {
        "cover": parsed.get("cover", "오늘 시장 요약"),
        "sections": sections,
        "metadata": {
            "generated_at": macro_summary.get("collected_at"),
            "grade_raw": grade_info.get("raw_grade"),
            "validated": validated,
            "channel": channel,
            "watermark": val_summary["watermark_label"],
            "validation_samples": val_summary["samples"],
            "cross_ref_warnings": cross_ref_warnings,
        },
    }


def _log_brain_learning_safe(portfolio: Dict[str, Any]) -> None:
    """Brain 학습 시그널 누적. 실패해도 리포트 흐름은 진행."""
    try:
        from api.metadata import brain_learning
        brain_learning.log_daily_signals(portfolio,
                                         backtest_summary=portfolio.get("backtest_summary"))
    except Exception as e:
        _logger.warning("brain_learning 누적 실패 (리포트는 진행): %s", e)


def _log_llm_cost_safe(call_type: str, input_tokens: int, output_tokens: int,
                       success: bool = True) -> None:
    """LLM 호출 비용 기록. 실패는 무시."""
    try:
        from api.metadata import llm_cost
        from api.config import GEMINI_MODEL_DEFAULT
        llm_cost.log_call(
            provider="google",
            model=GEMINI_MODEL_DEFAULT or "gemini-2.5-flash",
            call_type=call_type,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            success=success,
        )
    except Exception as e:
        _logger.debug("llm_cost 기록 실패: %s", e)


def _detect_section_cross_refs(sections: Dict[str, Any]) -> list:
    """모든 섹션 텍스트 결합 → cross-ref 충돌 검출."""
    blob = json.dumps(sections, ensure_ascii=False)
    return detect_cross_ref_conflicts(blob)


# ─── 내부 유틸 ────────────────────────────────────────────────

def _default_gemini_caller(prompt: str) -> str:
    """기본 Gemini 호출. 일반인용은 가벼운 모델 사용."""
    from api.analyzers.gemini_analyst import init_gemini, _pick_model

    client = init_gemini()
    model = _pick_model(critical=False)
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config={"system_instruction": "JSON 만 출력하라. 마크다운 코드 펜스 금지."},
    )
    return (response.text or "").strip()


def _parse_llm_json(raw: str) -> Dict[str, Any]:
    """LLM 출력 JSON 파싱 — 코드 펜스/주변 텍스트 제거."""
    if not raw:
        return {}
    txt = raw.strip()
    # 코드 펜스 제거
    if txt.startswith("```"):
        lines = txt.split("\n")
        # 첫 줄과 마지막 줄 제거 (보통 ```json ... ```)
        if len(lines) >= 3:
            txt = "\n".join(lines[1:-1])
    # 첫 { 부터 마지막 } 까지만
    start = txt.find("{")
    end = txt.rfind("}")
    if start >= 0 and end > start:
        txt = txt[start:end + 1]
    return json.loads(txt)


def _empty_public_result(
    grade_info: Dict[str, str],
    val_summary: Optional[Dict[str, Any]] = None,
    error: str = "",
) -> Dict[str, Any]:
    """LLM 실패 시 안전한 기본 결과. raw 에러는 _error 필드로 분리."""
    val_summary = val_summary or {}
    return {
        "cover": "오늘 분석을 다시 검토 중입니다",
        "sections": {
            "temperature": {"icon": "😐", "summary": "분석 일시 불가", "detail": ""},
            "signals": {},
            "sectors": {"winners": [], "losers": []},
            "events": [],
            "verity_judgment": {
                "icon_label": grade_info.get("label", "🟡 아직은 지켜보세요"),
                "reasoning": "오늘 분석을 다시 검토 중입니다.",
            },
            "self_assessment": "",
        },
        "metadata": {
            "grade_raw": grade_info.get("raw_grade"),
            "validated": val_summary.get("validated", False),
            "watermark": val_summary.get("watermark_label", ""),
            "_error": error,
        },
    }
