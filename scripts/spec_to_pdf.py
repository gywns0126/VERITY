#!/usr/bin/env python3
"""docs/VERITY_SYSTEM_SPEC_2026.md → docs/VERITY_SYSTEM_SPEC_2026.pdf

fpdf2 사용 (이미 운영 PDF 생성기와 동일 폰트 / 패턴).
한글: NanumGothic (api/reports/fonts/NanumGothic.ttf).
"""
from __future__ import annotations

import os
import re
import sys

from fpdf import FPDF

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "docs", "VERITY_SYSTEM_SPEC_2026.md")
DST = os.path.join(ROOT, "docs", "VERITY_SYSTEM_SPEC_2026.pdf")
FONT_REG = os.path.join(ROOT, "api", "reports", "fonts", "NanumGothic.ttf")
FONT_BOLD = os.path.join(ROOT, "api", "reports", "fonts", "NanumGothicBold.ttf")


class SpecPDF(FPDF):
    def __init__(self):
        super().__init__(format="A4", unit="mm")
        self.set_auto_page_break(auto=True, margin=15)
        self.set_margins(left=15, top=15, right=15)
        # 한글 폰트
        self.add_font("Nanum", "", FONT_REG, uni=True)
        if os.path.exists(FONT_BOLD):
            self.add_font("Nanum", "B", FONT_BOLD, uni=True)
        else:
            self.add_font("Nanum", "B", FONT_REG, uni=True)
        self.set_font("Nanum", size=9)

    def footer(self):
        self.set_y(-12)
        self.set_font("Nanum", size=7)
        self.set_text_color(140, 140, 140)
        self.cell(0, 6, f"VERITY SPEC v3.3 — {self.page_no()} / {{nb}}", align="C")
        self.set_text_color(0, 0, 0)


def _safe(text: str) -> str:
    """fpdf2 가 처리 가능한 형태로 정규화 (긴 라인 wrap 등)."""
    # 표현 가능 ASCII control char 제거
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    # 너무 긴 단어 (30자+) 강제 wrap
    text = re.sub(r"(\S{30})", r"\1 ", text)
    # 이모지 / 변형 선택자 / 4-byte UTF (NanumGothic 미커버) 제거
    text = "".join(ch for ch in text if ord(ch) < 0xFFFF)
    return text


def _safe_multi_cell(pdf, h, text, font_name="Nanum", font_size=9):
    """fpdf2 의 'Not enough horizontal space' 발생 시 폰트 줄여 재시도, 마지막엔 skip."""
    safe = _safe(text)
    for sz in (font_size, font_size - 1, font_size - 2):
        try:
            pdf.set_font(font_name, size=sz)
            pdf.multi_cell(0, h, safe)
            if sz != font_size:
                pdf.set_font(font_name, size=font_size)
            return
        except Exception:
            continue
    # 마지막 fallback: 길이 자르기
    try:
        pdf.set_font(font_name, size=font_size - 2)
        pdf.multi_cell(0, h, safe[:80] + " …")
        pdf.set_font(font_name, size=font_size)
    except Exception:
        pass


def render(md_path: str, pdf_path: str):
    with open(md_path, encoding="utf-8") as f:
        lines = f.readlines()

    pdf = SpecPDF()
    pdf.alias_nb_pages()
    pdf.add_page()

    in_code = False
    for raw in lines:
        line = raw.rstrip("\n")

        # 코드 블록 토글
        if line.strip().startswith("```"):
            in_code = not in_code
            pdf.ln(1)
            continue

        if in_code:
            pdf.set_text_color(60, 60, 60)
            _safe_multi_cell(pdf, 4, line or " ", font_name="Courier", font_size=8)
            pdf.set_font("Nanum", size=9)
            pdf.set_text_color(0, 0, 0)
            continue

        # 빈 줄
        if not line.strip():
            pdf.ln(2)
            continue

        # H1 — # 제목
        if line.startswith("# "):
            pdf.set_font("Nanum", "B", 16)
            pdf.set_text_color(20, 80, 20)
            pdf.multi_cell(0, 8, _safe(line[2:].strip()))
            pdf.set_text_color(0, 0, 0)
            pdf.set_font("Nanum", size=9)
            pdf.ln(2)
            continue

        # H2 — ## 제목
        if line.startswith("## "):
            if pdf.get_y() > 220:
                pdf.add_page()
            pdf.ln(3)
            pdf.set_font("Nanum", "B", 13)
            pdf.set_text_color(40, 40, 40)
            pdf.multi_cell(0, 7, _safe(line[3:].strip()))
            pdf.set_text_color(0, 0, 0)
            pdf.set_font("Nanum", size=9)
            pdf.ln(1)
            continue

        # H3 — ### 제목
        if line.startswith("### "):
            pdf.ln(2)
            pdf.set_font("Nanum", "B", 11)
            pdf.set_text_color(60, 60, 60)
            pdf.multi_cell(0, 6, _safe(line[4:].strip()))
            pdf.set_text_color(0, 0, 0)
            pdf.set_font("Nanum", size=9)
            pdf.ln(0.5)
            continue

        # 표 (간단 처리: 텍스트 그대로, mono)
        if line.lstrip().startswith("|"):
            _safe_multi_cell(pdf, 4, line, font_name="Courier", font_size=7)
            pdf.set_font("Nanum", size=9)
            continue

        # 리스트 (- 또는 *)
        m = re.match(r"^(\s*)([-*])\s+(.*)$", line)
        if m:
            indent_units = len(m.group(1)) // 2
            text = "  " * indent_units + "• " + m.group(3)
            _safe_multi_cell(pdf, 5, text)
            continue

        # 번호 리스트
        m = re.match(r"^(\s*)(\d+)\.\s+(.*)$", line)
        if m:
            text = m.group(2) + ". " + m.group(3)
            _safe_multi_cell(pdf, 5, text)
            continue

        # 일반 본문
        text = re.sub(r"\*\*(.+?)\*\*", r"\1", line)
        text = re.sub(r"`([^`]+)`", r"\1", text)
        _safe_multi_cell(pdf, 5, text)

    pdf.output(pdf_path)
    return pdf_path


if __name__ == "__main__":
    if not os.path.exists(SRC):
        print(f"ERROR: spec md 없음: {SRC}", file=sys.stderr)
        sys.exit(1)
    if not os.path.exists(FONT_REG):
        print(f"ERROR: 폰트 없음: {FONT_REG}", file=sys.stderr)
        sys.exit(1)
    out = render(SRC, DST)
    size_kb = os.path.getsize(out) / 1024
    print(f"✓ {out}")
    print(f"  size: {size_kb:.1f} KB")
