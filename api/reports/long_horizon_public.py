"""
Monthly / Quarterly / Semi-Annual / Annual 일반인용 리포트 — 통합 모듈.

각 단위는 4~5섹션으로 같은 패턴:
  - 시장 돌아보기 (해당 기간)
  - 승자/패자
  - 다음 기간 미리 보기
  - VERITY 판단

dilution 헬퍼 + Daily/Weekly public 패턴 재사용.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, Optional

from api.config import DATA_DIR, now_kst
from api.mocks import mockable
from api.reports.daily_public import (
    _default_gemini_caller, _detect_section_cross_refs, _empty_public_result,
    _log_brain_learning_safe, _log_llm_cost_safe, _parse_llm_json,
)
from api.reports.pdf_generator import VerityPDF, _norm_text
from api.utils.dilution import (
    apply_grade_guard, apply_label_guard, brain_grade_from_score,
    build_dictionary_for_prompt, get_forbidden_phrases, get_principles,
    grade_label, validation_status_summary,
)

_logger = logging.getLogger(__name__)


# ─── 공통 프롬프트 빌더 ───────────────────────────────────────

_PERIOD_LABEL = {
    "monthly": ("이달", "다음 달", "한 달"),
    "quarterly": ("이번 분기", "다음 분기", "분기"),
    "semi": ("이번 반기", "다음 반기", "반기"),
    "annual": ("올해", "내년", "1년"),
}


def _build_prompt(period: str, analysis: Dict[str, Any], grade_info: Dict[str, str]) -> str:
    cur, nxt, span = _PERIOD_LABEL.get(period, ("이번 기간", "다음 기간", "기간"))
    principles_text = "\n".join(f"- {p['rule']}" for p in get_principles())
    dictionary_block = build_dictionary_for_prompt()
    forbidden_text = ", ".join(f'"{p}"' for p in get_forbidden_phrases())

    macro = analysis.get("macro", {}) or {}
    sectors = analysis.get("sectors", {}) or {}
    recs = analysis.get("recommendations", {}) or {}
    top = sectors.get("top3_sectors") or []
    bottom = sectors.get("bottom3_sectors") or []

    return f"""[배경] VERITY {span} 일반인용 리포트 작성자다. 평범한 직장인이 5분 안에 읽고 '{cur} 시장이 어땠나' + '{nxt} 어떻게 봐야 하나'를 이해할 수 있게 써라.

[원칙]
{principles_text}

{dictionary_block}

[입력 데이터]
== 매크로 ==
{span} 시장 분위기 평균 {macro.get('mood_avg', '?')}점
{span} VIX 평균 {macro.get('vix_avg', '?')}
{span} 환율 평균 {macro.get('usd_krw_avg', '?')}원
{span} S&P500 변화 {macro.get(f'sp500_{period}_pct', 0):+.2f}%

== 섹터 ==
잘 된 업종: {', '.join(s.get('name', '?') for s in top[:3])}
부진한 업종: {', '.join(s.get('name', '?') for s in bottom[:3])}

== 시스템 성과 ==
BUY {recs.get('total_buy_recs', 0)}건, 적중률 {recs.get('hit_rate_pct', 0)}%, 평균 {recs.get('avg_return_pct', 0):+.2f}%

== VERITY 등급 ==
{grade_info.get('label')} ({grade_info.get('raw_grade')})

[금지 사항]
- 종목명 절대 등장 금지
- Brain 점수, VCI, 모델명 노출 금지
- 위 변환 사전 라벨만 사용
- 수익 보장 표현 절대 금지: {forbidden_text}

[출력 형식 — JSON만]
{{
  "cover": "{cur} 시장 한 줄 요약 (15자 이내)",
  "section_review": {{
    "summary": "{cur}이 어땠는지 2~3줄 (계절 비유 OK)",
    "key_events": ["{cur} 핵심 사건 2~3개 (전문용어 없이)"]
  }},
  "section_sectors": {{
    "winners": [{{"label": "쉬운 업종 이름", "reason": "왜 올랐는지 두 줄"}}],
    "losers": [{{"label": "쉬운 업종 이름", "reason": "왜 내렸는지 두 줄"}}]
  }},
  "section_next": {{
    "events": [{{"description": "한 문장"}}],
    "positive_scenario": "긍정 시나리오 한 줄",
    "negative_scenario": "부정 시나리오 한 줄",
    "biggest_factor": "{nxt} 가장 큰 변수 한 줄"
  }},
  "section_judgment": {{
    "icon_label": "{grade_info.get('label')}",
    "reasoning": "2~3줄 쉬운 말로",
    "big_picture": "{nxt}을 바라보는 큰 그림 한 줄"
  }},
  "self_assessment": "지난 {span} 우리 판단 vs 실제 결과 한 줄 (있으면)"
}}

JSON만 출력."""


def _generate_text(period: str, analysis: Dict[str, Any], portfolio: Dict[str, Any],
                   channel: str = "public",
                   llm_caller: Optional[callable] = None) -> Dict[str, Any]:
    vams = portfolio.get("vams") or {}
    val_summary = validation_status_summary(vams)
    validated = val_summary["validated"]

    mb = (portfolio.get("verity_brain") or {}).get("market_brain") or {}
    avg_score = mb.get("avg_brain_score")
    raw_grade = brain_grade_from_score(avg_score)
    safe_grade = apply_grade_guard(raw_grade, validated=validated, channel=channel)
    label = apply_label_guard(grade_label(safe_grade), validated=validated, channel=channel)
    grade_info = {"label": label, "raw_grade": safe_grade, "score": avg_score}

    prompt = _build_prompt(period, analysis, grade_info)
    _log_brain_learning_safe(portfolio)

    if llm_caller is None:
        llm_caller = _default_gemini_caller
    try:
        raw_text = llm_caller(prompt)
        parsed = _parse_llm_json(raw_text)
        _log_llm_cost_safe(f"{period}_public_report", len(prompt) // 4,
                           len(raw_text) // 4 if raw_text else 0)
    except Exception as e:
        _logger.error("%s_public LLM call failed: %s", period, e, exc_info=True)
        _log_llm_cost_safe(f"{period}_public_report", len(prompt) // 4, 0, success=False)
        return _long_empty_result(period, grade_info, val_summary, error=type(e).__name__)

    sections = {
        "review": parsed.get("section_review") or {},
        "sectors": parsed.get("section_sectors") or {},
        "next": parsed.get("section_next") or {},
        "judgment": parsed.get("section_judgment") or {},
        "self_assessment": parsed.get("self_assessment") or "",
    }
    cross_ref_warnings = _detect_section_cross_refs(sections)

    return {
        "cover": parsed.get("cover", f"{_PERIOD_LABEL.get(period, ('?',))[0]} 시장 요약"),
        "sections": sections,
        "metadata": {
            "generated_at": now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
            "period": period,
            "date_range": analysis.get("date_range", {}),
            "grade_raw": grade_info.get("raw_grade"),
            "validated": validated,
            "channel": channel,
            "watermark": val_summary["watermark_label"],
            "cross_ref_warnings": cross_ref_warnings,
        },
    }


def _long_empty_result(period, grade_info, val_summary, error=""):
    cur = _PERIOD_LABEL.get(period, ("이번 기간",))[0]
    return {
        "cover": f"{cur} 분석을 다시 검토 중입니다",
        "sections": {
            "review": {"summary": "분석 일시 불가", "key_events": []},
            "sectors": {"winners": [], "losers": []},
            "next": {"events": []},
            "judgment": {"icon_label": grade_info.get("label", ""),
                         "reasoning": f"{cur} 분석을 다시 검토 중입니다."},
            "self_assessment": "",
        },
        "metadata": {
            "period": period, "grade_raw": grade_info.get("raw_grade"),
            "validated": val_summary.get("validated", False),
            "watermark": val_summary.get("watermark_label", ""),
            "_error": error,
        },
    }


# ─── 공개 함수 (네 개 단위 각각) ──────────────────────────────

@mockable("monthly_public_text")
def generate_monthly_public_text(analysis, portfolio, channel="public", llm_caller=None):
    return _generate_text("monthly", analysis, portfolio, channel, llm_caller)


@mockable("quarterly_public_text")
def generate_quarterly_public_text(analysis, portfolio, channel="public", llm_caller=None):
    return _generate_text("quarterly", analysis, portfolio, channel, llm_caller)


@mockable("semi_public_text")
def generate_semi_public_text(analysis, portfolio, channel="public", llm_caller=None):
    return _generate_text("semi", analysis, portfolio, channel, llm_caller)


@mockable("annual_public_text")
def generate_annual_public_text(analysis, portfolio, channel="public", llm_caller=None):
    return _generate_text("annual", analysis, portfolio, channel, llm_caller)


# ─── PDF 렌더링 (공통) ────────────────────────────────────────

def _render_pdf(content: Dict[str, Any], title_label: str) -> str:
    metadata = content.get("metadata", {}) or {}
    sections = content.get("sections", {}) or {}
    period = metadata.get("period", "monthly")
    date_range = metadata.get("date_range", {}) or {}

    pdf = VerityPDF(); pdf.add_page()

    # COVER
    pdf._set_font("B", 22); pdf.set_text_color(*pdf.WHITE); pdf.set_x(15)
    pdf.cell(0, 14, f"VERITY {title_label.upper()}"); pdf.ln(15)
    pdf._set_font("", 9); pdf.set_text_color(*pdf.GRAY); pdf.set_x(15)
    pdf.cell(0, 5, f"{date_range.get('start', '?')} ~ {date_range.get('end', '?')}"); pdf.ln(8)

    if not metadata.get("validated"):
        wm = metadata.get("watermark", "")
        if wm:
            y = pdf.get_y(); pdf.set_fill_color(60, 30, 0); pdf.rect(10, y, 190, 7, "F")
            pdf._set_font("", 7); pdf.set_text_color(*pdf.YELLOW); pdf.set_xy(14, y + 1.5)
            pdf.multi_cell(180, 4, wm, align="L"); pdf.set_y(y + 11)

    pdf._set_font("B", 16); pdf.set_text_color(*pdf.ACCENT); pdf.set_x(15)
    pdf.multi_cell(180, 9, _norm_text(content.get("cover", "")), align="L"); pdf.ln(8)

    # 시장 돌아보기
    review = sections.get("review", {}) or {}
    pdf._set_font("B", 14); pdf.set_text_color(*pdf.WHITE); pdf.set_x(15)
    cur = _PERIOD_LABEL.get(period, ("이번 기간",))[0]
    pdf.cell(0, 9, f"{cur} 돌아보기"); pdf.ln(11)
    pdf._set_font("", 10); pdf.set_text_color(204, 204, 204); pdf.set_x(15)
    pdf.multi_cell(180, pdf.LH_BODY, _norm_text(review.get("summary", "")), align="L"); pdf.ln(4)

    events = review.get("key_events", []) or []
    if events:
        pdf._set_font("B", 9); pdf.set_text_color(*pdf.WHITE); pdf.set_x(15)
        pdf.cell(0, 6, f"{cur} 핵심 사건"); pdf.ln(6)
        pdf._set_font("", 9); pdf.set_text_color(204, 204, 204)
        for ev in events[:3]:
            pdf.set_x(18)
            pdf.multi_cell(177, pdf.LH_BODY, f"· {_norm_text(ev)}", align="L"); pdf.ln(1)

    # 승자/패자
    pdf.add_page()
    pdf._set_font("B", 14); pdf.set_text_color(*pdf.WHITE); pdf.set_x(15)
    pdf.cell(0, 9, "승자 / 패자"); pdf.ln(11)
    sec = sections.get("sectors", {}) or {}
    for label, items, c in [("▲ 승자", sec.get("winners", [])[:3], pdf.GREEN),
                            ("▼ 패자", sec.get("losers", [])[:3], pdf.RED)]:
        pdf._set_font("B", 11); pdf.set_text_color(*c); pdf.set_x(15)
        pdf.cell(0, 7, label); pdf.ln(8)
        for it in items:
            pdf._set_font("B", 10); pdf.set_text_color(*pdf.WHITE); pdf.set_x(18)
            pdf.cell(50, 6, _norm_text(it.get("label", "")))
            pdf._set_font("", 9); pdf.set_text_color(204, 204, 204)
            pdf.multi_cell(125, pdf.LH_COMPACT, _norm_text(it.get("reason", "")), align="L"); pdf.ln(1)
        pdf.ln(4)

    # 다음 기간
    pdf.add_page()
    pdf._set_font("B", 14); pdf.set_text_color(*pdf.WHITE); pdf.set_x(15)
    nxt = _PERIOD_LABEL.get(period, ("?", "다음 기간"))[1]
    pdf.cell(0, 9, f"{nxt} 미리 보기"); pdf.ln(11)
    nx = sections.get("next", {}) or {}
    for ev in (nx.get("events", []) or [])[:3]:
        pdf.set_x(18); pdf._set_font("", 10); pdf.set_text_color(204, 204, 204)
        pdf.multi_cell(177, pdf.LH_BODY, f"· {_norm_text(ev.get('description', ''))}", align="L")
        pdf.ln(2)
    if nx.get("positive_scenario"):
        pdf._set_font("B", 10); pdf.set_text_color(*pdf.GREEN); pdf.set_x(15)
        pdf.cell(0, 6, "긍정 시나리오"); pdf.ln(7)
        pdf._set_font("", 10); pdf.set_text_color(204, 204, 204); pdf.set_x(18)
        pdf.multi_cell(177, pdf.LH_BODY, _norm_text(nx["positive_scenario"]), align="L"); pdf.ln(3)
    if nx.get("negative_scenario"):
        pdf._set_font("B", 10); pdf.set_text_color(*pdf.RED); pdf.set_x(15)
        pdf.cell(0, 6, "부정 시나리오"); pdf.ln(7)
        pdf._set_font("", 10); pdf.set_text_color(204, 204, 204); pdf.set_x(18)
        pdf.multi_cell(177, pdf.LH_BODY, _norm_text(nx["negative_scenario"]), align="L"); pdf.ln(3)
    if nx.get("biggest_factor"):
        pdf._set_font("B", 10); pdf.set_text_color(*pdf.YELLOW); pdf.set_x(15)
        pdf.cell(0, 6, f"{nxt} 가장 큰 변수"); pdf.ln(7)
        pdf._set_font("", 10); pdf.set_text_color(204, 204, 204); pdf.set_x(18)
        pdf.multi_cell(177, pdf.LH_BODY, _norm_text(nx["biggest_factor"]), align="L")

    # VERITY 판단
    pdf.add_page()
    pdf._set_font("B", 14); pdf.set_text_color(*pdf.WHITE); pdf.set_x(15)
    pdf.cell(0, 9, f"VERITY {nxt} 판단"); pdf.ln(11)
    j = sections.get("judgment", {}) or {}
    pdf._set_font("B", 18); pdf.set_text_color(*pdf.ACCENT); pdf.set_x(15)
    pdf.multi_cell(180, 11, _norm_text(j.get("icon_label", "")), align="L"); pdf.ln(4)
    pdf._set_font("", 10); pdf.set_text_color(204, 204, 204); pdf.set_x(15)
    pdf.multi_cell(180, pdf.LH_BODY, _norm_text(j.get("reasoning", "")), align="L"); pdf.ln(4)
    if j.get("big_picture"):
        pdf._set_font("B", 10); pdf.set_text_color(*pdf.WHITE); pdf.set_x(15)
        pdf.cell(0, 6, "큰 그림"); pdf.ln(7)
        pdf._set_font("", 10); pdf.set_text_color(204, 204, 204); pdf.set_x(18)
        pdf.multi_cell(177, pdf.LH_BODY, _norm_text(j["big_picture"]), align="L"); pdf.ln(4)

    self_assess = _norm_text(sections.get("self_assessment", ""))
    if self_assess:
        pdf._set_font("B", 11); pdf.set_text_color(*pdf.WHITE); pdf.set_x(15)
        pdf.cell(0, 7, "VERITY 자기평가"); pdf.ln(8)
        pdf._set_font("", 9); pdf.set_text_color(*pdf.GRAY); pdf.set_x(18)
        pdf.multi_cell(177, pdf.LH_BODY, self_assess, align="L")

    pdf.ln(10)
    pdf._set_font("", 8); pdf.set_text_color(*pdf.DARK_GRAY); pdf.set_x(15)
    pdf.multi_cell(180, pdf.LH_COMPACT,
                   "이 리포트는 투자 권유가 아닙니다. 모든 투자 결정은 본인 책임입니다.", align="L")

    out_dir = os.path.join(DATA_DIR, "reports")
    os.makedirs(out_dir, exist_ok=True)
    fname = f"verity_{period}_public_{now_kst().strftime('%Y%m%d_%H%M')}.pdf"
    path = os.path.join(out_dir, fname)
    pdf.output(path)
    return path


def generate_monthly_public_pdf(content): return _render_pdf(content, "Monthly")
def generate_quarterly_public_pdf(content): return _render_pdf(content, "Quarterly")
def generate_semi_public_pdf(content): return _render_pdf(content, "Semi-Annual")
def generate_annual_public_pdf(content): return _render_pdf(content, "Annual")
