"""
배리티 데일리 콘텐츠 생성기 — 4 카테고리 카드 PNG + 캡션 + 해시태그.

출력: data/daily_content/{YYYY-MM-DD}/{category}/
  - card.png (1080x1080)
  - caption.txt (인스타 본문 — 복붙용)
  - hashtags.txt (해시태그 — 복붙용)
  - meta.json (생성 시각, 데이터 timestamp, 카테고리, 핵심 수치)

카테고리 (--category):
  - macro: 거시 (실질금리 / USD-KRW / 금-은비율 / VIX + Brain 진단)
  - sector: 섹터 (자본 흐름 top3 in/out)        [TODO step 2]
  - micro: 미시 (거래량/뉴스 급증 종목 top1)     [TODO step 2]
  - news_impact: 뉴스 영향 (Gemini v0)            [TODO step 3]
  - all: 전부

정책:
  - feedback_scope: 검증 전 종목 추천 X (micro/news_impact 는 *현상/영향* 만)
  - 디자인 토큰 정합 (Framer 마스터: bgPage #0E0F11, accent #B5FF19, success #22C55E, danger #EF4444)
"""

from __future__ import annotations
import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
PORTFOLIO_PATH = ROOT / "data" / "portfolio.json"
OUTPUT_ROOT = ROOT / "data" / "daily_content"

# 디자인 토큰 (Framer 마스터)
C_BG = (14, 15, 17)         # #0E0F11
C_CARD = (23, 24, 32)       # #171820
C_ELEVATED = (34, 35, 43)   # #22232B
C_TEXT = (242, 243, 245)    # #F2F3F5
C_SECONDARY = (168, 171, 178)
C_TERTIARY = (107, 110, 118)
C_ACCENT = (181, 255, 25)   # #B5FF19
C_SUCCESS = (34, 197, 94)
C_DANGER = (239, 68, 68)
C_WARN = (245, 158, 11)

# 폰트 후보 (macOS / ubuntu / fallback)
FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/AppleSDGothicNeo.ttc",
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJKkr-Regular.otf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def _resolve_font_path() -> str | None:
    for p in FONT_CANDIDATES:
        if Path(p).exists():
            return p
    return None


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """크기 + bold 옵션 폰트. Apple SD Gothic Neo 면 index 로 weight 분기."""
    path = _resolve_font_path()
    if not path:
        return ImageFont.load_default()
    try:
        if path.endswith(".ttc"):
            # Apple SD Gothic Neo: index 0=Regular, 1=Bold, 2=Light...
            # Noto CJK: index 0=Regular (Bold 별도 파일이라 fallback weight stroke)
            idx = 1 if (bold and "AppleSDGothic" in path) else 0
            font = ImageFont.truetype(path, size, index=idx)
        else:
            font = ImageFont.truetype(path, size)
        return font
    except Exception:
        return ImageFont.load_default()


def _draw_text(draw: ImageDraw.ImageDraw, xy, text, font, fill, anchor="la", stroke_width=0):
    """anchor 기본 left-ascender (la). 굵기 흉내 시 stroke_width 사용."""
    draw.text(xy, text, font=font, fill=fill, anchor=anchor, stroke_width=stroke_width, stroke_fill=fill)


def _wrap_text(draw, text, font, max_w):
    """공백 기반 line wrap — 한국어 띄어쓰기 단위."""
    words = text.split()
    lines, cur = [], ""
    for w in words:
        test = (cur + " " + w).strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] > max_w and cur:
            lines.append(cur)
            cur = w
        else:
            cur = test
    if cur:
        lines.append(cur)
    return lines


# ─────────────── 카테고리 1: 거시 ───────────────

def render_macro(macro: dict, out_dir: Path, date_str: str) -> dict[str, Any]:
    img = Image.new("RGB", (1080, 1080), C_BG)
    d = ImageDraw.Draw(img)

    # Header: 브랜드 + 카테고리
    _draw_text(d, (80, 80), "VERITY", _font(36, bold=True), C_ACCENT, stroke_width=1)
    _draw_text(d, (80, 130), "거시 브리핑", _font(72, bold=True), C_TEXT, stroke_width=2)

    # 핵심 4 지표
    us10y = (macro.get("us_10y") or {}).get("value")
    bei = (macro.get("breakeven_inflation_10y") or {}).get("value")
    real_yield = (us10y - bei) if (us10y is not None and bei is not None) else None
    usd_krw = (macro.get("usd_krw") or {}).get("value")
    usd_chg = (macro.get("usd_krw") or {}).get("change_pct")
    gold = (macro.get("gold") or {}).get("value")
    silver = (macro.get("silver") or {}).get("value")
    gs_ratio = (gold / silver) if (gold and silver and silver > 0) else None
    vix = (macro.get("vix") or {}).get("value")

    metrics = [
        ("실질금리 10Y",
         f"{real_yield:.2f}%" if real_yield is not None else "—",
         (C_SUCCESS if (real_yield is not None and real_yield < 1.5)
          else C_DANGER if (real_yield is not None and real_yield > 2.0)
          else C_TEXT)),
        ("USD/KRW",
         f"{usd_krw:,.0f}" if usd_krw is not None else "—",
         (C_SUCCESS if (usd_chg is not None and usd_chg < 0)
          else C_DANGER if (usd_chg is not None and usd_chg > 0)
          else C_TEXT)),
        ("금/은 비율",
         f"{gs_ratio:.1f}" if gs_ratio is not None else "—",
         C_TEXT),
        ("VIX",
         f"{vix:.1f}" if vix is not None else "—",
         (C_DANGER if (vix is not None and vix > 25)
          else C_SUCCESS if (vix is not None and vix < 18)
          else C_WARN)),
    ]

    # 2x2 grid
    for i, (label, value, color) in enumerate(metrics):
        col, row = i % 2, i // 2
        x, y = 80 + col * 480, 280 + row * 220
        _draw_text(d, (x, y), label, _font(30), C_TERTIARY)
        _draw_text(d, (x, y + 56), value, _font(96, bold=True), color, stroke_width=2)

    # 진단 (Brain v0 룰)
    diagnosis = _build_macro_diagnosis(real_yield, usd_chg, vix)
    _draw_text(d, (80, 760), "BRAIN 진단", _font(28, bold=True), C_ACCENT, stroke_width=1)
    lines = _wrap_text(d, diagnosis, _font(38), max_w=920)
    for i, line in enumerate(lines[:4]):
        _draw_text(d, (80, 810 + i * 56), line, _font(38), C_TEXT)

    # Footer
    _draw_text(d, (80, 1000), date_str, _font(26), C_TERTIARY)
    _draw_text(d, (1000, 1000), "@verity_terminal", _font(26, bold=True), C_ACCENT, anchor="ra", stroke_width=1)

    out_path = out_dir / "card.png"
    img.save(out_path, "PNG", optimize=True)

    caption = _build_macro_caption(date_str, real_yield, usd_krw, usd_chg, gs_ratio, vix, diagnosis)
    (out_dir / "caption.txt").write_text(caption, encoding="utf-8")

    hashtags = ["#배리티", "#배리티터미널", "#거시경제", "#매크로", "#실질금리",
                "#환율", "#VIX", "#금가격", "#투자", "#주식"]
    (out_dir / "hashtags.txt").write_text(" ".join(hashtags), encoding="utf-8")

    return {
        "category": "macro",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "card_path": str(out_path.relative_to(ROOT)),
        "metrics": {
            "real_yield_10y": real_yield,
            "usd_krw": usd_krw,
            "usd_krw_chg_pct": usd_chg,
            "gs_ratio": gs_ratio,
            "vix": vix,
        },
        "diagnosis": diagnosis,
    }


def _build_macro_diagnosis(real_yield, usd_chg, vix) -> str:
    """v0 룰 기반 — Brain 정식 산식 별도. (TODO: verity_brain.py 의 macro_override 와 연결)"""
    parts = []
    if real_yield is not None:
        if real_yield < 1.0:
            parts.append("실질금리 둔화 — 위험자산 친화")
        elif real_yield > 2.0:
            parts.append("실질금리 부담 — 안전자산 선호")
        else:
            parts.append("실질금리 중립권")
    if usd_chg is not None:
        if usd_chg < -1:
            parts.append("원화 강세 (수출주 압박)")
        elif usd_chg > 1:
            parts.append("달러 강세 (수입물가 부담)")
    if vix is not None:
        if vix > 25:
            parts.append(f"VIX {vix:.0f} 변동성 경계")
        elif vix < 18:
            parts.append(f"VIX {vix:.0f} 안정권")
    return ". ".join(parts) + "." if parts else "데이터 부족."


def _build_macro_caption(date_str, real_yield, usd_krw, usd_chg, gs_ratio, vix, diagnosis) -> str:
    lines = [f"📊 배리티 거시 브리핑 · {date_str}", ""]
    if real_yield is not None:
        lines.append(f"실질금리(10Y): {real_yield:.2f}%")
    if usd_krw is not None:
        chg = f" ({usd_chg:+.2f}%)" if usd_chg is not None else ""
        lines.append(f"USD/KRW: {usd_krw:,.0f}원{chg}")
    if gs_ratio is not None:
        lines.append(f"금/은 비율: {gs_ratio:.1f}")
    if vix is not None:
        lines.append(f"VIX: {vix:.1f}")
    lines += ["", f"🧠 {diagnosis}", "", "verity-terminal.framer.website"]
    return "\n".join(lines)


# ─────────────── portfolio race-window 가드 ───────────────

# 핵심 매크로 키 — 이 중 N개가 null 이면 race window 의심 → 재read.
_CORE_MACRO_KEYS = ("usd_krw", "us_10y", "vix", "gold", "silver")
_RETRY_MAX = 2          # 최대 재시도 횟수
_RETRY_SLEEP = 1.5      # 재시도 사이 대기 (sec) — portfolio.json atomic write 안정화


def _portfolio_health(macro: dict) -> tuple[int, int]:
    """(present, total) — 핵심 매크로 키 중 dict + value 모두 존재하는 수."""
    total = len(_CORE_MACRO_KEYS)
    present = 0
    for k in _CORE_MACRO_KEYS:
        v = macro.get(k)
        if isinstance(v, dict) and v.get("value") is not None:
            present += 1
    return present, total


def _load_portfolio_with_retry() -> tuple[dict, dict]:
    """portfolio.json read — race window 시 최대 2회 재시도. silent skip 차단."""
    last_macro: dict = {}
    last_portfolio: dict = {}
    for attempt in range(_RETRY_MAX + 1):
        portfolio = json.loads(PORTFOLIO_PATH.read_text(encoding="utf-8"))
        macro = portfolio.get("macro") or {}
        present, total = _portfolio_health(macro)
        last_portfolio, last_macro = portfolio, macro

        # 절반 이상 정상이면 통과
        if present * 2 >= total:
            if attempt > 0:
                print(f"  retry {attempt} OK ({present}/{total} 핵심 매크로 정상)", file=sys.stderr)
            return portfolio, macro

        if attempt < _RETRY_MAX:
            print(f"  ⚠ portfolio race 의심 — {present}/{total} 핵심 매크로만 정상. "
                  f"{_RETRY_SLEEP}s 후 재read (attempt {attempt + 1}/{_RETRY_MAX})", file=sys.stderr)
            time.sleep(_RETRY_SLEEP)

    # 모든 재시도 실패 — 최종 상태 명시 (silent skip 금지, feedback_data_collection_verification_mandatory)
    present, total = _portfolio_health(last_macro)
    print(f"  ❌ portfolio race retry {_RETRY_MAX}회 모두 fail ({present}/{total} 핵심 매크로). "
          f"카드 데이터 부족 가능성 — 진행 강행.", file=sys.stderr)
    return last_portfolio, last_macro


# ─────────────── main ───────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="배리티 데일리 콘텐츠 생성기")
    parser.add_argument("--category", choices=["macro", "sector", "micro", "news_impact", "all"],
                        default="all")
    parser.add_argument("--date", default=None, help="YYYY-MM-DD (default: today KST)")
    args = parser.parse_args()

    if not PORTFOLIO_PATH.exists():
        print(f"❌ portfolio.json 없음: {PORTFOLIO_PATH}")
        return 1
    portfolio, macro = _load_portfolio_with_retry()

    date_str = args.date or datetime.now().strftime("%Y-%m-%d")
    out_root = OUTPUT_ROOT / date_str
    out_root.mkdir(parents=True, exist_ok=True)

    results: list[dict] = []

    cats = ["macro", "sector", "micro", "news_impact"] if args.category == "all" else [args.category]

    if "macro" in cats:
        out = out_root / "macro"
        out.mkdir(exist_ok=True)
        meta = render_macro(macro, out, date_str)
        (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        results.append(meta)
        print(f"✓ macro → {out.relative_to(ROOT)}")

    # TODO step 2: sector / micro
    # TODO step 3: news_impact (Gemini v0)
    skipped = [c for c in cats if c not in {"macro"}]
    if skipped:
        print(f"  (TODO 카테고리: {', '.join(skipped)})")

    print(f"\n생성 완료: {len(results)}건 · {out_root.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
