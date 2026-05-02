#!/usr/bin/env python3
"""md → PDF (Korean) via matplotlib (handles system TTC)."""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", str(Path(__file__).resolve().parent / ".mplconfig"))
Path(os.environ["MPLCONFIGDIR"]).mkdir(parents=True, exist_ok=True)

import matplotlib

matplotlib.use("pdf")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.backends.backend_pdf import PdfPages

# macOS: Apple SD Gothic Neo (TTC) — wide Hangul coverage
FONT_PATH = "/System/Library/Fonts/AppleSDGothicNeo.ttc"


def main() -> None:
    root = Path(__file__).resolve().parent
    md = root / "VERITY_ESTATE_Implementation_Plan_2026-04-26.md"
    out = root / "VERITY_ESTATE_Implementation_Plan_2026-04-26.pdf"
    if len(sys.argv) >= 2:
        md = Path(sys.argv[1])
    if len(sys.argv) >= 3:
        out = Path(sys.argv[2])

    text = md.read_text(encoding="utf-8")
    lines = text.splitlines()

    prop = font_manager.FontProperties(fname=FONT_PATH)
    with PdfPages(str(out)) as pdf:
        fig, ax = plt.subplots(figsize=(8.27, 11.69), dpi=150)  # A4
        ax.axis("off")
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        y = 0.97
        line_h = 0.0225
        margin_x = 0.06

        for line in lines:
            if y < 0.05:
                pdf.savefig(fig, bbox_inches="tight")
                plt.close(fig)
                fig, ax = plt.subplots(figsize=(8.27, 11.69), dpi=150)
                ax.axis("off")
                ax.set_xlim(0, 1)
                ax.set_ylim(0, 1)
                y = 0.97
            s = line.rstrip()
            if s.strip() == "---":
                ax.plot([margin_x, 1 - margin_x], [y, y], color="0.7", lw=0.5, transform=ax.transAxes)
                y -= line_h * 1.5
                continue
            if not s:
                y -= line_h * 0.4
                continue
            m = re.match(r"^(#{1,3})\s+(.*)$", s)
            if m:
                lv, title = m.group(1), m.group(2)
                size = 16 if lv == "#" else 13 if lv == "##" else 11
                wrapped = [title[i : i + 50] for i in range(0, len(title), 50)] or [title]
                for part in wrapped:
                    ax.text(
                        margin_x,
                        y,
                        part,
                        fontproperties=prop,
                        fontsize=size,
                        fontweight="bold" if lv == "#" else "normal",
                        va="top",
                        ha="left",
                        transform=ax.transAxes,
                    )
                    y -= line_h * (1.0 + size / 12 * 0.1)
                y -= line_h * 0.2
                continue
            if s.startswith("- "):
                body = "· " + s[2:].strip()
            else:
                body = s
            # simple wrap: ~52 chars for A4
            w = 52
            chunks = [body[i : i + w] for i in range(0, len(body), w)]
            for part in chunks:
                if y < 0.05:
                    pdf.savefig(fig, bbox_inches="tight")
                    plt.close(fig)
                    fig, ax = plt.subplots(figsize=(8.27, 11.69), dpi=150)
                    ax.axis("off")
                    ax.set_xlim(0, 1)
                    ax.set_ylim(0, 1)
                    y = 0.97
                ax.text(
                    margin_x,
                    y,
                    part,
                    fontproperties=prop,
                    fontsize=9.5,
                    va="top",
                    ha="left",
                    transform=ax.transAxes,
                )
                y -= line_h * 1.05
        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)
    print(out)


if __name__ == "__main__":
    main()
