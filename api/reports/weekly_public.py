"""
Weekly 일반인용 리포트 — 텍스트 생성 + PDF 렌더링.

4섹션:
  1. 이번 주 시장 돌아보기 (온도 변화 시각화 + 사건 2~3개)
  2. 잘된 분야 / 부진한 분야
  3. 다음 주 미리 보기 (이벤트 + 긍정/부정 시나리오)
  4. VERITY 다음 주 판단

dilution 헬퍼 + Daily public 패턴 재사용.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, Optional

from api.config import DATA_DIR, now_kst
from api.mocks import mockable
from api.reports.daily_public import (
    _build_macro_summary, _default_gemini_caller, _detect_section_cross_refs,
    _empty_public_result, _log_brain_learning_safe, _log_llm_cost_safe,
    _parse_llm_json,
)
from api.reports.pdf_generator import VerityPDF, _norm_text
from api.utils.dilution import (
    apply_grade_guard, apply_label_guard, brain_grade_from_score,
    build_dictionary_for_prompt, get_forbidden_phrases, get_principles,
    grade_label, is_validated, scenario_label, translate_ai_fallback,
    validation_status_summary,
)

_logger = logging.getLogger(__name__)


def _build_weekly_prompt(macro_summary: Dict[str, Any], analysis: Dict[str, Any],
                         grade_info: Dict[str, str]) -> str:
    """Weekly 일반인용 4섹션 LLM 프롬프트."""
    principles_text = "\n".join(f"- {p['rule']}" for p in get_principles())
    dictionary_block = build_dictionary_for_prompt()
    forbidden_text = ", ".join(f'"{p}"' for p in get_forbidden_phrases())

    macro = analysis.get("macro", {}) or {}
    sectors = analysis.get("sectors", {}) or {}
    recs = analysis.get("recommendations", {}) or {}

    macro_block = (
        f"주간 VIX 평균 {macro.get('vix_avg', '?')}\n"
        f"주간 환율 평균 {macro.get('usd_krw_avg', '?')}원\n"
        f"주간 시장 분위기 {macro.get('mood_avg', '?')}\n"
        f"S&P500 주간 변화 {macro.get('sp500_weekly_pct', 0):+.2f}%"
    )
    top_sectors = sectors.get("top3_sectors") or []
    bottom_sectors = sectors.get("bottom3_sectors") or []
    perf_block = (
        f"BUY 추천 {recs.get('total_buy_recs', 0)}건, "
        f"적중률 {recs.get('hit_rate_pct', 0)}%, "
        f"평균 수익률 {recs.get('avg_return_pct', 0):+.2f}%"
    )

    return f"""[배경] VERITY 주간 일반인용 리포트 작성자다. 평범한 직장인이 5분 안에 읽고 '이번 주 시장이 어땠나' + '다음 주 어떻게 봐야 하나'를 이해할 수 있게 써라.

[원칙]
{principles_text}

{dictionary_block}

[입력 데이터]
== 매크로 (주간) ==
{macro_block}

== 섹터 ==
잘 된 업종: {', '.join(s.get('name', '?') for s in top_sectors[:3])}
부진한 업종: {', '.join(s.get('name', '?') for s in bottom_sectors[:3])}

== 시스템 성과 ==
{perf_block}

== VERITY 등급 ==
{grade_info.get('label')} ({grade_info.get('raw_grade')})

[금지 사항]
- 종목명 절대 등장 금지
- Brain 점수, VCI, 모델명 노출 금지
- 위 변환 사전 라벨만 사용
- 수익 보장 표현 절대 금지: {forbidden_text}

[출력 형식 — JSON만]
{{
  "cover": "이번 주 시장 한 줄 요약 (15자 이내)",
  "section_review": {{
    "icon_change": "지난주 → 이번주 온도 변화 (예: '😐 → 😟')",
    "summary": "이번 주가 어땠는지 한 줄",
    "events": ["이번 주 핵심 사건 2~3개 (전문용어 없이)"]
  }},
  "section_sectors": {{
    "winners": [{{"label": "쉬운 업종 이름", "reason": "왜 올랐는지 한 줄"}}],
    "losers": [{{"label": "쉬운 업종 이름", "reason": "왜 내렸는지 한 줄"}}],
    "anomaly": "특이 신호 한 줄 (없으면 빈 문자열)"
  }},
  "section_next_week": {{
    "events": [{{"description": "한 문장 (날짜·수치 없이 방향만)"}}],
    "positive_scenario": "긍정 시나리오 한 줄",
    "negative_scenario": "부정 시나리오 한 줄"
  }},
  "section_judgment": {{
    "icon_label": "{grade_info.get('label')}",
    "reasoning": "2~3줄 (쉬운 말로)",
    "advice": "지금 투자 고민하는 분께 한 마디"
  }},
  "self_assessment": "지난주 우리 판단 vs 실제 결과 한 줄 (있으면)"
}}

JSON만 출력."""


@mockable("weekly_public_text")
def generate_weekly_public_text(
    analysis: Dict[str, Any],
    portfolio: Dict[str, Any],
    channel: str = "public",
    llm_caller: Optional[callable] = None,
) -> Dict[str, Any]:
    """Weekly 일반인용 텍스트 생성. analysis = generate_periodic_analysis('weekly')."""
    macro = analysis.get("macro", {}) or {}
    verity_brain = portfolio.get("verity_brain") or {}
    vams = portfolio.get("vams") or {}

    val_summary = validation_status_summary(vams)
    validated = val_summary["validated"]

    macro_summary = _build_macro_summary(macro)

    # Brain 등급 (Daily 와 동일 패턴)
    mb = verity_brain.get("market_brain") or {}
    avg_score = mb.get("avg_brain_score")
    raw_grade = brain_grade_from_score(avg_score)
    safe_grade = apply_grade_guard(raw_grade, validated=validated, channel=channel)
    label = apply_label_guard(grade_label(safe_grade), validated=validated, channel=channel)
    grade_info = {"label": label, "raw_grade": safe_grade, "score": avg_score}

    prompt = _build_weekly_prompt(macro_summary, analysis, grade_info)

    _log_brain_learning_safe(portfolio)

    if llm_caller is None:
        llm_caller = _default_gemini_caller
    try:
        raw_text = llm_caller(prompt)
        parsed = _parse_llm_json(raw_text)
        _log_llm_cost_safe("weekly_public_report", len(prompt) // 4,
                           len(raw_text) // 4 if raw_text else 0)
    except Exception as e:
        _logger.error("weekly_public LLM call failed: %s", e, exc_info=True)
        _log_llm_cost_safe("weekly_public_report", len(prompt) // 4, 0, success=False)
        return _weekly_empty_result(grade_info, val_summary, error=type(e).__name__)

    sections = {
        "review": parsed.get("section_review") or {},
        "sectors": parsed.get("section_sectors") or {},
        "next_week": parsed.get("section_next_week") or {},
        "judgment": parsed.get("section_judgment") or {},
        "self_assessment": parsed.get("self_assessment") or "",
    }
    cross_ref_warnings = _detect_section_cross_refs(sections)

    return {
        "cover": parsed.get("cover", "이번 주 시장 요약"),
        "sections": sections,
        "metadata": {
            "generated_at": now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
            "period": "weekly",
            "date_range": analysis.get("date_range", {}),
            "grade_raw": grade_info.get("raw_grade"),
            "validated": validated,
            "channel": channel,
            "watermark": val_summary["watermark_label"],
            "cross_ref_warnings": cross_ref_warnings,
        },
    }


def _weekly_empty_result(grade_info: Dict[str, str], val_summary: Dict[str, Any],
                         error: str = "") -> Dict[str, Any]:
    return {
        "cover": "이번 주 분석을 다시 검토 중입니다",
        "sections": {
            "review": {"summary": "분석 일시 불가", "events": []},
            "sectors": {"winners": [], "losers": []},
            "next_week": {"events": []},
            "judgment": {"icon_label": grade_info.get("label", "🟡 지켜볼게요"),
                         "reasoning": "이번 주 분석을 다시 검토 중입니다."},
            "self_assessment": "",
        },
        "metadata": {
            "period": "weekly",
            "grade_raw": grade_info.get("raw_grade"),
            "validated": val_summary.get("validated", False),
            "watermark": val_summary.get("watermark_label", ""),
            "_error": error,
        },
    }


# ─── PDF 렌더링 ────────────────────────────────────────────

def _render_weekly_cover(pdf: VerityPDF, content: Dict[str, Any]):
    metadata = content.get("metadata", {}) or {}
    sections = content.get("sections", {}) or {}
    review = sections.get("review", {}) or {}
    date_range = metadata.get("date_range", {}) or {}

    pdf._set_font("B", 22)
    pdf.set_text_color(*pdf.WHITE)
    pdf.set_x(15)
    pdf.cell(0, 14, "VERITY WEEKLY")
    pdf.ln(15)

    pdf._set_font("", 9)
    pdf.set_text_color(*pdf.GRAY)
    pdf.set_x(15)
    pdf.cell(0, 5, f"{date_range.get('start', '?')} ~ {date_range.get('end', '?')}")
    pdf.ln(8)

    if not metadata.get("validated"):
        wm = metadata.get("watermark", "")
        if wm:
            y = pdf.get_y()
            pdf.set_fill_color(60, 30, 0)
            pdf.rect(10, y, 190, 7, "F")
            pdf._set_font("", 7)
            pdf.set_text_color(*pdf.YELLOW)
            pdf.set_xy(14, y + 1.5)
            pdf.multi_cell(180, 4, wm, align="L")
            pdf.set_y(y + 11)

    pdf._set_font("B", 16)
    pdf.set_text_color(*pdf.ACCENT)
    pdf.set_x(15)
    pdf.multi_cell(180, 9, _norm_text(content.get("cover", "")), align="L")
    pdf.ln(8)

    # 시장 돌아보기
    pdf._set_font("B", 11)
    pdf.set_text_color(*pdf.WHITE)
    pdf.set_x(15)
    pdf.cell(0, 7, "이번 주 돌아보기")
    pdf.ln(8)

    pdf._set_font("", 14)
    pdf.set_text_color(*pdf.YELLOW)
    pdf.set_x(18)
    pdf.cell(0, 8, _norm_text(review.get("icon_change", "")))
    pdf.ln(10)

    pdf._set_font("", 10)
    pdf.set_text_color(204, 204, 204)
    pdf.set_x(18)
    pdf.multi_cell(177, pdf.LH_BODY, _norm_text(review.get("summary", "")), align="L")
    pdf.ln(4)

    events = review.get("events", []) or []
    if events:
        pdf._set_font("B", 9)
        pdf.set_text_color(*pdf.WHITE)
        pdf.set_x(18)
        pdf.cell(0, 6, "이번 주 핵심 사건")
        pdf.ln(6)
        pdf._set_font("", 9)
        pdf.set_text_color(204, 204, 204)
        for ev in events[:3]:
            pdf.set_x(20)
            pdf.multi_cell(175, pdf.LH_BODY, f"· {_norm_text(ev)}", align="L")
            pdf.ln(1)


def _render_weekly_sectors(pdf: VerityPDF, sections: Dict[str, Any]):
    pdf.add_page()
    pdf._set_font("B", 14)
    pdf.set_text_color(*pdf.WHITE)
    pdf.set_x(15)
    pdf.cell(0, 9, "잘된 분야 / 부진한 분야")
    pdf.ln(11)

    sec = sections.get("sectors", {}) or {}
    winners = sec.get("winners", []) or []
    losers = sec.get("losers", []) or []
    anomaly = _norm_text(sec.get("anomaly", ""))

    pdf._set_font("B", 11)
    pdf.set_text_color(*pdf.GREEN)
    pdf.set_x(15)
    pdf.cell(0, 7, "▲ 잘된 분야")
    pdf.ln(8)
    for w in winners[:3]:
        pdf._set_font("B", 10)
        pdf.set_text_color(*pdf.WHITE)
        pdf.set_x(18)
        pdf.cell(50, 6, _norm_text(w.get("label", "")))
        pdf._set_font("", 9)
        pdf.set_text_color(204, 204, 204)
        pdf.multi_cell(125, pdf.LH_COMPACT, _norm_text(w.get("reason", "")), align="L")
        pdf.ln(1)
    pdf.ln(4)

    pdf._set_font("B", 11)
    pdf.set_text_color(*pdf.RED)
    pdf.set_x(15)
    pdf.cell(0, 7, "▼ 부진한 분야")
    pdf.ln(8)
    for l in losers[:3]:
        pdf._set_font("B", 10)
        pdf.set_text_color(*pdf.WHITE)
        pdf.set_x(18)
        pdf.cell(50, 6, _norm_text(l.get("label", "")))
        pdf._set_font("", 9)
        pdf.set_text_color(204, 204, 204)
        pdf.multi_cell(125, pdf.LH_COMPACT, _norm_text(l.get("reason", "")), align="L")
        pdf.ln(1)

    if anomaly:
        pdf.ln(5)
        pdf._set_font("B", 10)
        pdf.set_text_color(*pdf.YELLOW)
        pdf.set_x(15)
        pdf.cell(0, 6, "특이 신호")
        pdf.ln(7)
        pdf._set_font("", 9)
        pdf.set_text_color(204, 204, 204)
        pdf.set_x(18)
        pdf.multi_cell(177, pdf.LH_BODY, anomaly, align="L")


def _render_weekly_next(pdf: VerityPDF, sections: Dict[str, Any]):
    pdf.add_page()
    pdf._set_font("B", 14)
    pdf.set_text_color(*pdf.WHITE)
    pdf.set_x(15)
    pdf.cell(0, 9, "다음 주 미리 보기")
    pdf.ln(11)

    nw = sections.get("next_week", {}) or {}
    events = nw.get("events", []) or []
    pos = _norm_text(nw.get("positive_scenario", ""))
    neg = _norm_text(nw.get("negative_scenario", ""))

    if events:
        pdf._set_font("B", 11)
        pdf.set_text_color(*pdf.WHITE)
        pdf.set_x(15)
        pdf.cell(0, 7, "주요 이벤트")
        pdf.ln(8)
        pdf._set_font("", 10)
        pdf.set_text_color(204, 204, 204)
        for i, ev in enumerate(events[:3], 1):
            pdf.set_x(18)
            pdf._set_font("B", 10)
            pdf.set_text_color(*pdf.YELLOW)
            pdf.cell(8, 6, f"{i}.")
            pdf._set_font("", 10)
            pdf.set_text_color(204, 204, 204)
            pdf.multi_cell(170, pdf.LH_BODY, _norm_text(ev.get("description", "")), align="L")
            pdf.ln(2)
        pdf.ln(3)

    if pos:
        pdf._set_font("B", 10)
        pdf.set_text_color(*pdf.GREEN)
        pdf.set_x(15)
        pdf.cell(0, 6, "긍정 시나리오")
        pdf.ln(7)
        pdf._set_font("", 10)
        pdf.set_text_color(204, 204, 204)
        pdf.set_x(18)
        pdf.multi_cell(177, pdf.LH_BODY, pos, align="L")
        pdf.ln(3)

    if neg:
        pdf._set_font("B", 10)
        pdf.set_text_color(*pdf.RED)
        pdf.set_x(15)
        pdf.cell(0, 6, "부정 시나리오")
        pdf.ln(7)
        pdf._set_font("", 10)
        pdf.set_text_color(204, 204, 204)
        pdf.set_x(18)
        pdf.multi_cell(177, pdf.LH_BODY, neg, align="L")


def _render_weekly_judgment(pdf: VerityPDF, sections: Dict[str, Any]):
    pdf.add_page()
    pdf._set_font("B", 14)
    pdf.set_text_color(*pdf.WHITE)
    pdf.set_x(15)
    pdf.cell(0, 9, "VERITY 다음 주 판단")
    pdf.ln(11)

    j = sections.get("judgment", {}) or {}
    pdf._set_font("B", 18)
    pdf.set_text_color(*pdf.ACCENT)
    pdf.set_x(15)
    pdf.multi_cell(180, 11, _norm_text(j.get("icon_label", "")), align="L")
    pdf.ln(4)
    pdf._set_font("", 10)
    pdf.set_text_color(204, 204, 204)
    pdf.set_x(15)
    pdf.multi_cell(180, pdf.LH_BODY, _norm_text(j.get("reasoning", "")), align="L")
    pdf.ln(6)

    advice = _norm_text(j.get("advice", ""))
    if advice:
        pdf._set_font("B", 10)
        pdf.set_text_color(*pdf.WHITE)
        pdf.set_x(15)
        pdf.cell(0, 6, "지금 투자를 고민하는 분께")
        pdf.ln(7)
        pdf._set_font("", 10)
        pdf.set_text_color(204, 204, 204)
        pdf.set_x(18)
        pdf.multi_cell(177, pdf.LH_BODY, advice, align="L")
        pdf.ln(4)

    self_assess = _norm_text(sections.get("self_assessment", ""))
    if self_assess:
        pdf._set_font("B", 11)
        pdf.set_text_color(*pdf.WHITE)
        pdf.set_x(15)
        pdf.cell(0, 7, "VERITY 자기평가")
        pdf.ln(8)
        pdf._set_font("", 9)
        pdf.set_text_color(*pdf.GRAY)
        pdf.set_x(18)
        pdf.multi_cell(177, pdf.LH_BODY, self_assess, align="L")


def _render_weekly_disclaimer(pdf: VerityPDF):
    pdf.ln(10)
    pdf._set_font("", 8)
    pdf.set_text_color(*pdf.DARK_GRAY)
    pdf.set_x(15)
    pdf.multi_cell(180, pdf.LH_COMPACT,
                   "이 리포트는 투자 권유가 아닙니다. 모든 투자 결정은 본인 책임입니다.",
                   align="L")


def generate_weekly_public_pdf(content: Dict[str, Any]) -> str:
    """Weekly 일반인용 PDF 생성."""
    pdf = VerityPDF()
    pdf.add_page()

    sections = content.get("sections", {}) or {}
    _render_weekly_cover(pdf, content)
    _render_weekly_sectors(pdf, sections)
    _render_weekly_next(pdf, sections)
    _render_weekly_judgment(pdf, sections)
    _render_weekly_disclaimer(pdf)

    out_dir = os.path.join(DATA_DIR, "reports")
    os.makedirs(out_dir, exist_ok=True)
    fname = f"verity_weekly_public_{now_kst().strftime('%Y%m%d_%H%M')}.pdf"
    path = os.path.join(out_dir, fname)
    pdf.output(path)
    return path
