"""
Daily 일반인용 PDF 렌더링 — 5섹션 인스타 카드뉴스 톤.

입력: daily_public.generate_daily_public_text() 결과 dict
출력: PDF 파일 경로 (data/reports/verity_daily_public_*.pdf)

5섹션:
  1. COVER + 시장 온도
  2. 글로벌 경제 신호등 (미/한/환율)
  3. 잘 된 업종 / 부진한 업종
  4. 다음 며칠 놓치면 안 될 뉴스
  5. VERITY 오늘 판단 + 자기평가
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

from api.config import DATA_DIR, now_kst
from api.reports.pdf_generator import VerityPDF, _norm_text


def _render_cover(pdf: VerityPDF, content: Dict[str, Any]):
    cover = content.get("cover", "오늘 시장 요약")
    metadata = content.get("metadata", {})
    sections = content.get("sections", {})
    temp = sections.get("temperature", {}) or {}

    pdf._set_font("B", 22)
    pdf.set_text_color(*pdf.WHITE)
    pdf.set_x(15)
    pdf.cell(0, 14, "VERITY DAILY")
    pdf.ln(15)

    pdf._set_font("", 9)
    pdf.set_text_color(*pdf.GRAY)
    pdf.set_x(15)
    pdf.cell(0, 5, now_kst().strftime("%Y년 %m월 %d일"))
    pdf.ln(8)

    # 워터마크 (검증 미완료)
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

    # 한 줄 요약 큰 글씨
    pdf._set_font("B", 16)
    pdf.set_text_color(*pdf.ACCENT)
    pdf.set_x(15)
    pdf.multi_cell(180, 9, _norm_text(cover), align="L")
    pdf.ln(8)

    # 시장 온도
    icon = temp.get("icon", "")
    summary = _norm_text(temp.get("summary", ""))
    detail = _norm_text(temp.get("detail", ""))

    pdf._set_font("B", 11)
    pdf.set_text_color(*pdf.WHITE)
    pdf.set_x(15)
    pdf.cell(0, 7, "지금 시장 온도")
    pdf.ln(8)

    pdf._set_font("", 14)
    pdf.set_text_color(*pdf.YELLOW)
    pdf.set_x(18)
    pdf.cell(0, 8, f"{icon}  {summary}")
    pdf.ln(10)

    pdf._set_font("", 10)
    pdf.set_text_color(204, 204, 204)
    pdf.set_x(18)
    pdf.multi_cell(177, pdf.LH_BODY, detail, align="L")


def _render_signals(pdf: VerityPDF, sections: Dict[str, Any]):
    pdf.add_page()
    pdf._set_font("B", 14)
    pdf.set_text_color(*pdf.WHITE)
    pdf.set_x(15)
    pdf.cell(0, 9, "글로벌 경제 신호등")
    pdf.ln(11)

    signals = sections.get("signals", {}) or {}
    items = [
        ("미국 경제", signals.get("us", {})),
        ("한국 경제", signals.get("kr", {})),
        ("환율 방향", signals.get("fx", {})),
    ]
    for label, sig in items:
        icon = sig.get("icon", "?")
        reason = _norm_text(sig.get("reason", ""))

        pdf._set_font("B", 11)
        pdf.set_text_color(*pdf.WHITE)
        pdf.set_x(18)
        pdf.cell(40, 7, label)
        pdf._set_font("", 14)
        pdf.set_text_color(*pdf.YELLOW)
        pdf.cell(15, 7, icon)
        pdf._set_font("", 10)
        pdf.set_text_color(204, 204, 204)
        pdf.cell(0, 7, reason[:80])
        pdf.ln(11)


def _render_sectors(pdf: VerityPDF, sections: Dict[str, Any]):
    pdf.add_page()
    pdf._set_font("B", 14)
    pdf.set_text_color(*pdf.WHITE)
    pdf.set_x(15)
    pdf.cell(0, 9, "이번 주 잘 된 분야 / 부진한 분야")
    pdf.ln(11)

    sectors = sections.get("sectors", {}) or {}
    winners = sectors.get("winners", []) or []
    losers = sectors.get("losers", []) or []

    pdf._set_font("B", 11)
    pdf.set_text_color(*pdf.GREEN)
    pdf.set_x(15)
    pdf.cell(0, 7, "▲ 잘 된 분야")
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


def _render_events(pdf: VerityPDF, sections: Dict[str, Any]):
    pdf.add_page()
    pdf._set_font("B", 14)
    pdf.set_text_color(*pdf.WHITE)
    pdf.set_x(15)
    pdf.cell(0, 9, "이번 주 놓치면 안 될 뉴스")
    pdf.ln(11)

    events = sections.get("events", []) or []
    if not events:
        pdf._set_font("", 10)
        pdf.set_text_color(*pdf.GRAY)
        pdf.set_x(18)
        pdf.cell(0, 7, "이번 주 주요 이벤트 없음")
        return
    pdf._set_font("", 10)
    pdf.set_text_color(204, 204, 204)
    for i, ev in enumerate(events[:3], 1):
        desc = _norm_text(ev.get("description", ""))
        pdf.set_x(18)
        pdf._set_font("B", 10)
        pdf.set_text_color(*pdf.YELLOW)
        pdf.cell(8, 6, f"{i}.")
        pdf._set_font("", 10)
        pdf.set_text_color(204, 204, 204)
        pdf.multi_cell(170, pdf.LH_BODY, desc, align="L")
        pdf.ln(3)


def _render_judgment(pdf: VerityPDF, sections: Dict[str, Any]):
    pdf.add_page()
    pdf._set_font("B", 14)
    pdf.set_text_color(*pdf.WHITE)
    pdf.set_x(15)
    pdf.cell(0, 9, "VERITY 오늘 판단")
    pdf.ln(11)

    judgment = sections.get("verity_judgment", {}) or {}
    icon_label = _norm_text(judgment.get("icon_label", ""))
    reasoning = _norm_text(judgment.get("reasoning", ""))

    pdf._set_font("B", 18)
    pdf.set_text_color(*pdf.ACCENT)
    pdf.set_x(15)
    pdf.multi_cell(180, 11, icon_label, align="L")
    pdf.ln(4)

    pdf._set_font("", 10)
    pdf.set_text_color(204, 204, 204)
    pdf.set_x(15)
    pdf.multi_cell(180, pdf.LH_BODY, reasoning, align="L")
    pdf.ln(6)

    # 자기 평가 (있으면)
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


def _render_disclaimer(pdf: VerityPDF):
    pdf.ln(10)
    pdf._set_font("", 8)
    pdf.set_text_color(*pdf.DARK_GRAY)
    pdf.set_x(15)
    pdf.multi_cell(180, pdf.LH_COMPACT,
                   "이 리포트는 투자 권유가 아닙니다. 모든 투자 결정은 본인 책임입니다. "
                   "VERITY 시스템 분석 결과로, 시장 상황을 이해하는 참고 자료로만 활용하세요.",
                   align="L")


def generate_daily_public_pdf(content: Dict[str, Any]) -> str:
    """일반인용 Daily PDF 생성. content 는 daily_public.generate_daily_public_text() 결과."""
    pdf = VerityPDF()
    pdf.add_page()

    sections = content.get("sections", {}) or {}

    _render_cover(pdf, content)
    _render_signals(pdf, sections)
    _render_sectors(pdf, sections)
    _render_events(pdf, sections)
    _render_judgment(pdf, sections)
    _render_disclaimer(pdf)

    out_dir = os.path.join(DATA_DIR, "reports")
    os.makedirs(out_dir, exist_ok=True)
    fname = f"verity_daily_public_{now_kst().strftime('%Y%m%d_%H%M')}.pdf"
    path = os.path.join(out_dir, fname)
    pdf.output(path)
    return path
