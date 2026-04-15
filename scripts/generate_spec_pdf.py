from pathlib import Path

from fpdf import FPDF


ROOT = Path(__file__).resolve().parents[1]
INPUT_MD = ROOT / "docs" / "VERITY_SYSTEM_SPEC_2026.md"
OUTPUT_PDF = ROOT / "docs" / "VERITY_SYSTEM_SPEC_2026.pdf"
FONT_REGULAR = ROOT / "api" / "reports" / "fonts" / "NanumGothic.ttf"
FONT_BOLD = ROOT / "api" / "reports" / "fonts" / "NanumGothicBold.ttf"


def _soft_break_long_tokens(text: str, max_token_len: int = 45) -> str:
    out = []
    for token in text.split(" "):
        if len(token) <= max_token_len:
            out.append(token)
            continue
        chunks = [token[i : i + max_token_len] for i in range(0, len(token), max_token_len)]
        out.append(" ".join(chunks))
    return " ".join(out)


def _wrap_for_pdf(pdf: FPDF, text: str, max_width: float) -> list:
    lines = []
    current = ""
    for ch in text:
        test = current + ch
        if pdf.get_string_width(test) <= max_width:
            current = test
            continue
        if current:
            lines.append(current)
            current = ch
        else:
            # 글리프 폭 계산이 비정상인 문자는 대체
            lines.append("?")
            current = ""
    if current:
        lines.append(current)
    return lines if lines else [""]


def _write_line(pdf: FPDF, text: str, h: int = 7) -> None:
    safe = _soft_break_long_tokens(text.strip()).replace("\t", "    ")
    max_width = pdf.w - pdf.l_margin - pdf.r_margin
    wrapped = _wrap_for_pdf(pdf, safe, max_width)
    for row in wrapped:
        pdf.cell(0, h, row, new_x="LMARGIN", new_y="NEXT")


def main() -> None:
    text = INPUT_MD.read_text(encoding="utf-8")

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    pdf.add_font("Nanum", "", str(FONT_REGULAR))
    pdf.add_font("Nanum", "B", str(FONT_BOLD))

    for line in text.splitlines():
        line = line.rstrip()
        if line.startswith("# "):
            pdf.set_font("Nanum", "B", 16)
            _write_line(pdf, line[2:], h=9)
            pdf.ln(1)
        elif line.startswith("## "):
            pdf.set_font("Nanum", "B", 13)
            _write_line(pdf, line[3:], h=8)
            pdf.ln(1)
        elif line.startswith("- "):
            pdf.set_font("Nanum", "", 11)
            _write_line(pdf, f"- {line[2:]}", h=7)
        elif line.strip() == "":
            pdf.ln(3)
        else:
            pdf.set_font("Nanum", "", 11)
            _write_line(pdf, line, h=7)

    pdf.output(str(OUTPUT_PDF))
    print(f"Generated: {OUTPUT_PDF}")


if __name__ == "__main__":
    main()

