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
ESTATE_BRAIN_PATH = ROOT / "data" / "estate_brain_snapshots.json"
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


# ─────────────── 카테고리 2: 섹터 (자본 흐름 top3 in/out) ───────────────

def render_sector(sectors: list, sector_rotation: dict, out_dir: Path, date_str: str) -> dict[str, Any]:
    """sectors (정렬됨) 의 change_pct 기준 top3 in / bottom3 out + cycle 라벨."""
    img = Image.new("RGB", (1080, 1080), C_BG)
    d = ImageDraw.Draw(img)

    _draw_text(d, (80, 80), "VERITY", _font(36, bold=True), C_ACCENT, stroke_width=1)
    _draw_text(d, (80, 130), "섹터 자본 흐름", _font(72, bold=True), C_TEXT, stroke_width=2)

    # 정렬 — change_pct 기준
    valid = [s for s in (sectors or []) if isinstance(s, dict) and s.get("change_pct") is not None]
    valid.sort(key=lambda s: s["change_pct"], reverse=True)
    top_in = valid[:3]
    top_out = valid[-3:][::-1]  # 가장 약한 게 위로

    # 사이클 진단
    cycle_label = (sector_rotation or {}).get("cycle_label") or "—"
    cycle_desc = (sector_rotation or {}).get("cycle_desc") or ""

    # IN 컬럼 (left)
    _draw_text(d, (80, 270), "유입 TOP 3", _font(32, bold=True), C_SUCCESS, stroke_width=1)
    for i, s in enumerate(top_in):
        y = 330 + i * 130
        name = (s.get("name") or "—")[:10]
        chg = s.get("change_pct")
        _draw_text(d, (80, y), name, _font(40, bold=True), C_TEXT, stroke_width=1)
        _draw_text(d, (80, y + 60), f"{chg:+.2f}%" if chg is not None else "—",
                   _font(46, bold=True), C_SUCCESS, stroke_width=2)

    # OUT 컬럼 (right)
    _draw_text(d, (560, 270), "유출 TOP 3", _font(32, bold=True), C_DANGER, stroke_width=1)
    for i, s in enumerate(top_out):
        y = 330 + i * 130
        name = (s.get("name") or "—")[:10]
        chg = s.get("change_pct")
        _draw_text(d, (560, y), name, _font(40, bold=True), C_TEXT, stroke_width=1)
        _draw_text(d, (560, y + 60), f"{chg:+.2f}%" if chg is not None else "—",
                   _font(46, bold=True), C_DANGER, stroke_width=2)

    # 사이클 진단
    _draw_text(d, (80, 760), "사이클", _font(28, bold=True), C_ACCENT, stroke_width=1)
    _draw_text(d, (80, 808), cycle_label, _font(46, bold=True), C_TEXT, stroke_width=2)
    if cycle_desc:
        lines = _wrap_text(d, cycle_desc, _font(30), max_w=920)
        for i, line in enumerate(lines[:3]):
            _draw_text(d, (80, 880 + i * 42), line, _font(30), C_SECONDARY)

    _draw_text(d, (80, 1000), date_str, _font(26), C_TERTIARY)
    _draw_text(d, (1000, 1000), "@verity_terminal", _font(26, bold=True), C_ACCENT, anchor="ra", stroke_width=1)

    out_path = out_dir / "card.png"
    img.save(out_path, "PNG", optimize=True)

    caption = _build_sector_caption(date_str, top_in, top_out, cycle_label, cycle_desc)
    (out_dir / "caption.txt").write_text(caption, encoding="utf-8")
    hashtags = ["#배리티", "#배리티터미널", "#섹터로테이션", "#자본흐름", "#섹터분석",
                "#KOSPI", "#KOSDAQ", "#투자", "#주식"]
    (out_dir / "hashtags.txt").write_text(" ".join(hashtags), encoding="utf-8")

    return {
        "category": "sector",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "card_path": str(out_path.relative_to(ROOT)),
        "top_in": [{"name": s.get("name"), "change_pct": s.get("change_pct")} for s in top_in],
        "top_out": [{"name": s.get("name"), "change_pct": s.get("change_pct")} for s in top_out],
        "cycle_label": cycle_label,
    }


def _build_sector_caption(date_str, top_in, top_out, cycle_label, cycle_desc) -> str:
    lines = [f"📊 배리티 섹터 자본 흐름 · {date_str}", ""]
    lines.append("🟢 유입 TOP 3")
    for s in top_in:
        chg = s.get("change_pct")
        lines.append(f"  · {s.get('name')} {chg:+.2f}%" if chg is not None else f"  · {s.get('name')}")
    lines.append("")
    lines.append("🔴 유출 TOP 3")
    for s in top_out:
        chg = s.get("change_pct")
        lines.append(f"  · {s.get('name')} {chg:+.2f}%" if chg is not None else f"  · {s.get('name')}")
    lines += ["", f"🧠 사이클: {cycle_label}"]
    if cycle_desc:
        lines.append(f"   {cycle_desc}")
    lines += ["", "verity-terminal.framer.website"]
    return "\n".join(lines)


# ─────────────── 카테고리 3: 미시 (현상만, 종목 추천 X — feedback_scope) ───────────────

def render_micro(recommendations: list, out_dir: Path, date_str: str) -> dict[str, Any]:
    """recommendations 의 volume / change_pct / drop_from_high_pct 기반 시장 *현상* 만 노출.

    정책: feedback_scope — 검증 전 종목 추천 X. 종목명은 *현상 사례* 형식으로 노출.
    """
    img = Image.new("RGB", (1080, 1080), C_BG)
    d = ImageDraw.Draw(img)

    _draw_text(d, (80, 80), "VERITY", _font(36, bold=True), C_ACCENT, stroke_width=1)
    _draw_text(d, (80, 130), "오늘의 시장 현상", _font(72, bold=True), C_TEXT, stroke_width=2)

    valid = [r for r in (recommendations or []) if isinstance(r, dict)]

    # 거래대금 1위 (보통 trading_value 큰 종목)
    by_value = sorted(
        [r for r in valid if r.get("trading_value")],
        key=lambda r: r["trading_value"], reverse=True,
    )
    top_value = by_value[0] if by_value else None

    # 52주 최고가 대비 -30%↓ 종목 수 (역가치)
    deep_drops = [r for r in valid if (r.get("drop_from_high_pct") or 0) <= -30]
    deep_drop_count = len(deep_drops)

    # 시총 1조원+ + drop_from_high -50%↓ 1위 (가장 깊은 낙폭)
    fallen_giants = sorted(
        [r for r in valid if (r.get("market_cap") or 0) >= 1_000_000_000_000
         and (r.get("drop_from_high_pct") or 0) <= -30],
        key=lambda r: r["drop_from_high_pct"],
    )
    fallen_top = fallen_giants[0] if fallen_giants else None

    # 카드 1: 거래대금 1위 (현상)
    _draw_text(d, (80, 270), "거래대금 1위", _font(28, bold=True), C_TERTIARY)
    if top_value:
        name = (top_value.get("name") or "—")[:14]
        tv = top_value.get("trading_value") or 0
        tv_str = f"{tv / 1_000_000_000_000:.2f}조원" if tv >= 1_000_000_000_000 else f"{tv / 100_000_000:.0f}억원"
        _draw_text(d, (80, 320), name, _font(46, bold=True), C_TEXT, stroke_width=2)
        _draw_text(d, (80, 386), tv_str, _font(56, bold=True), C_ACCENT, stroke_width=2)

    # 카드 2: -30%↓ 종목 수
    _draw_text(d, (80, 500), "52주 고점 대비 -30%↓ 종목", _font(28, bold=True), C_TERTIARY)
    _draw_text(d, (80, 550), f"{deep_drop_count}개", _font(96, bold=True),
               (C_DANGER if deep_drop_count >= 5 else C_WARN), stroke_width=2)

    # 카드 3: 시총 큰 낙폭주 1
    _draw_text(d, (80, 720), "시총 1조+ 깊은 낙폭", _font(28, bold=True), C_TERTIARY)
    if fallen_top:
        name = (fallen_top.get("name") or "—")[:14]
        drop = fallen_top.get("drop_from_high_pct")
        _draw_text(d, (80, 770), name, _font(40, bold=True), C_TEXT, stroke_width=1)
        _draw_text(d, (80, 826), f"{drop:.1f}%" if drop is not None else "—",
                   _font(50, bold=True), C_DANGER, stroke_width=2)
    else:
        _draw_text(d, (80, 770), "해당 없음", _font(40), C_TERTIARY)

    # Disclaimer (feedback_scope)
    _draw_text(d, (80, 920), "※ 시장 현상 정보 — 매수/매도 추천 아님",
               _font(22), C_TERTIARY)

    _draw_text(d, (80, 1000), date_str, _font(26), C_TERTIARY)
    _draw_text(d, (1000, 1000), "@verity_terminal", _font(26, bold=True), C_ACCENT, anchor="ra", stroke_width=1)

    out_path = out_dir / "card.png"
    img.save(out_path, "PNG", optimize=True)

    caption = _build_micro_caption(date_str, top_value, deep_drop_count, fallen_top)
    (out_dir / "caption.txt").write_text(caption, encoding="utf-8")
    hashtags = ["#배리티", "#배리티터미널", "#시장현상", "#거래대금", "#52주최저가",
                "#KOSPI", "#KOSDAQ", "#주식시장", "#투자정보"]
    (out_dir / "hashtags.txt").write_text(" ".join(hashtags), encoding="utf-8")

    return {
        "category": "micro",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "card_path": str(out_path.relative_to(ROOT)),
        "top_value": ({"name": top_value.get("name"), "trading_value": top_value.get("trading_value")}
                      if top_value else None),
        "deep_drop_count": deep_drop_count,
        "fallen_top": ({"name": fallen_top.get("name"), "drop_from_high_pct": fallen_top.get("drop_from_high_pct")}
                       if fallen_top else None),
    }


def _build_micro_caption(date_str, top_value, deep_drop_count, fallen_top) -> str:
    lines = [f"📊 배리티 시장 현상 · {date_str}", ""]
    if top_value:
        tv = top_value.get("trading_value") or 0
        tv_str = f"{tv / 1_000_000_000_000:.2f}조원" if tv >= 1_000_000_000_000 else f"{tv / 100_000_000:.0f}억원"
        lines.append(f"💰 거래대금 1위: {top_value.get('name')} ({tv_str})")
    lines.append(f"📉 52주 고점 대비 -30%↓ 종목: {deep_drop_count}개")
    if fallen_top:
        drop = fallen_top.get("drop_from_high_pct")
        lines.append(f"🔻 시총 1조+ 깊은 낙폭: {fallen_top.get('name')} ({drop:.1f}%)")
    lines += ["", "※ 시장 현상 정보 — 매수/매도 추천 아님",
              "", "verity-terminal.framer.website"]
    return "\n".join(lines)


# ─────────────── 카테고리 4: 뉴스 영향 (V0 = 룰 기반, V1 Gemini) ───────────────

def render_news_impact(headlines: list, out_dir: Path, date_str: str) -> dict[str, Any]:
    """headlines 의 sentiment + credibility + urgency 결합 score top1 노출.

    정책: feedback_scope — *영향*만 노출, 종목 추천 X.
    V0 = 룰 기반 score. V1 = Gemini 분석 (TODO).
    """
    img = Image.new("RGB", (1080, 1080), C_BG)
    d = ImageDraw.Draw(img)

    _draw_text(d, (80, 80), "VERITY", _font(36, bold=True), C_ACCENT, stroke_width=1)
    _draw_text(d, (80, 130), "오늘의 영향 뉴스", _font(72, bold=True), C_TEXT, stroke_width=2)

    valid = [h for h in (headlines or []) if isinstance(h, dict) and h.get("title")]
    # V0 score = credibility × urgency (둘 다 있을 때) + sentiment 가중
    def _score(h):
        cred = h.get("credibility") or 0
        urg = h.get("urgency") or 0
        senti = 1.0 if h.get("sentiment") in ("positive", "negative") else 0.3
        return cred * (urg if urg else 0.5) * senti
    valid.sort(key=_score, reverse=True)
    top = valid[0] if valid else None

    if top:
        title = top.get("title") or "—"
        source = top.get("source") or ""
        sentiment = top.get("sentiment") or "—"
        senti_color = (C_SUCCESS if sentiment == "positive"
                       else C_DANGER if sentiment == "negative"
                       else C_TERTIARY)
        senti_label = ({"positive": "긍정", "negative": "부정", "neutral": "중립"}
                       .get(sentiment, sentiment))

        # 제목 (큰 글씨, wrap 4줄)
        lines = _wrap_text(d, title, _font(48, bold=True), max_w=920)
        for i, line in enumerate(lines[:5]):
            _draw_text(d, (80, 280 + i * 64), line, _font(48, bold=True), C_TEXT, stroke_width=2)

        # 메타 (source / sentiment)
        meta_y = 280 + min(len(lines), 5) * 64 + 40
        _draw_text(d, (80, meta_y), source, _font(28), C_TERTIARY)
        _draw_text(d, (80, meta_y + 50), f"성향: {senti_label}",
                   _font(32, bold=True), senti_color, stroke_width=1)

    else:
        _draw_text(d, (80, 400), "뉴스 데이터 부족", _font(48), C_TERTIARY)

    _draw_text(d, (80, 920), "※ 영향 분석 — 매수/매도 추천 아님",
               _font(22), C_TERTIARY)

    _draw_text(d, (80, 1000), date_str, _font(26), C_TERTIARY)
    _draw_text(d, (1000, 1000), "@verity_terminal", _font(26, bold=True), C_ACCENT, anchor="ra", stroke_width=1)

    out_path = out_dir / "card.png"
    img.save(out_path, "PNG", optimize=True)

    caption = _build_news_caption(date_str, top)
    (out_dir / "caption.txt").write_text(caption, encoding="utf-8")
    hashtags = ["#배리티", "#배리티터미널", "#오늘의뉴스", "#시장영향", "#경제뉴스",
                "#투자뉴스", "#주식시장", "#증시"]
    (out_dir / "hashtags.txt").write_text(" ".join(hashtags), encoding="utf-8")

    return {
        "category": "news_impact",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "card_path": str(out_path.relative_to(ROOT)),
        "top_news": ({"title": top.get("title"), "source": top.get("source"),
                      "sentiment": top.get("sentiment")} if top else None),
    }


def _build_news_caption(date_str, top) -> str:
    lines = [f"📰 배리티 영향 뉴스 · {date_str}", ""]
    if top:
        senti_label = ({"positive": "긍정", "negative": "부정", "neutral": "중립"}
                       .get(top.get("sentiment"), top.get("sentiment") or "—"))
        lines += [f"📌 {top.get('title')}", "",
                  f"출처: {top.get('source') or '—'}",
                  f"성향: {senti_label}"]
    else:
        lines.append("뉴스 데이터 부족")
    lines += ["", "※ 영향 분석 — 매수/매도 추천 아님",
              "", "verity-terminal.framer.website"]
    return "\n".join(lines)


# ─────────────── 카테고리 5: 통합 (주식 + 부동산 한 카드) ───────────────

def render_integrated(macro: dict, recommendations: list, sectors: list,
                      sector_rotation: dict, estate_brain: dict,
                      out_dir: Path, date_str: str) -> dict[str, Any]:
    """주식 + 부동산 결합 카드. 상단 주식 / 하단 부동산 수평 분할.

    배리티 터미널 = 주식+부동산 결합 시스템 정합. 메인 포스팅용.
    """
    img = Image.new("RGB", (1080, 1080), C_BG)
    d = ImageDraw.Draw(img)

    # === Header (전체) ===
    _draw_text(d, (80, 50), "VERITY", _font(36, bold=True), C_ACCENT, stroke_width=1)
    _draw_text(d, (80, 100), "오늘의 시장", _font(72, bold=True), C_TEXT, stroke_width=2)

    # 분할선 (530px 부근)
    d.line([(60, 540), (1020, 540)], fill=C_TERTIARY, width=2)

    # ============ 상단: 주식 (y 200~530) ============
    _draw_text(d, (80, 210), "📈 주식", _font(32, bold=True), C_ACCENT, stroke_width=1)

    # 주식 핵심 4 지표 (좌 2 / 우 2)
    us10y = (macro.get("us_10y") or {}).get("value")
    bei = (macro.get("breakeven_inflation_10y") or {}).get("value")
    real_yield = (us10y - bei) if (us10y is not None and bei is not None) else None
    vix = (macro.get("vix") or {}).get("value")

    valid_recs = [r for r in (recommendations or []) if isinstance(r, dict)]
    by_value = sorted(
        [r for r in valid_recs if r.get("trading_value")],
        key=lambda r: r["trading_value"], reverse=True,
    )
    top_value = by_value[0] if by_value else None

    valid_sectors = [s for s in (sectors or []) if isinstance(s, dict) and s.get("change_pct") is not None]
    valid_sectors.sort(key=lambda s: s["change_pct"], reverse=True)
    top_sector = valid_sectors[0] if valid_sectors else None

    # 좌측 (주식 매크로)
    _draw_text(d, (80, 270), "실질금리", _font(24), C_TERTIARY)
    _draw_text(d, (80, 302), f"{real_yield:.2f}%" if real_yield is not None else "—",
               _font(54, bold=True),
               (C_SUCCESS if (real_yield is not None and real_yield < 1.5)
                else C_DANGER if (real_yield is not None and real_yield > 2.0) else C_TEXT),
               stroke_width=2)
    _draw_text(d, (80, 380), "VIX", _font(24), C_TERTIARY)
    _draw_text(d, (80, 412), f"{vix:.1f}" if vix is not None else "—",
               _font(54, bold=True),
               (C_DANGER if (vix is not None and vix > 25)
                else C_SUCCESS if (vix is not None and vix < 18) else C_WARN),
               stroke_width=2)

    # 우측 (시장 현상)
    _draw_text(d, (560, 270), "거래대금 1위", _font(24), C_TERTIARY)
    if top_value:
        name = (top_value.get("name") or "—")[:10]
        tv = top_value.get("trading_value") or 0
        tv_str = f"{tv / 1_000_000_000_000:.1f}조" if tv >= 1_000_000_000_000 else f"{tv / 100_000_000:.0f}억"
        _draw_text(d, (560, 302), name, _font(34, bold=True), C_TEXT, stroke_width=1)
        _draw_text(d, (560, 350), tv_str, _font(38, bold=True), C_ACCENT, stroke_width=1)

    _draw_text(d, (560, 410), "유입 1위 섹터", _font(24), C_TERTIARY)
    if top_sector:
        sname = (top_sector.get("name") or "—")[:10]
        chg = top_sector.get("change_pct")
        _draw_text(d, (560, 442), sname, _font(34, bold=True), C_TEXT, stroke_width=1)
        _draw_text(d, (560, 488), f"{chg:+.2f}%" if chg is not None else "—",
                   _font(38, bold=True), C_SUCCESS, stroke_width=1)

    # ============ 하단: 부동산 (y 570~960) ============
    _draw_text(d, (80, 580), "🏠 부동산", _font(32, bold=True), C_ACCENT, stroke_width=1)

    estate_macro = (estate_brain or {}).get("macro") or {}
    kr_rate = estate_macro.get("treasury_10y_pct")
    income_won = estate_macro.get("annual_median_income_won")

    # 강남구 시그널 (대표 — 25구 중 가장 인지도 높음)
    gu_data = ((estate_brain or {}).get("gu_aggregates") or {}).get("강남구") or {}
    cycle = (gu_data.get("cycle_analog") or {})
    current_phase = cycle.get("current_phase") or "—"
    lead = cycle.get("lead_time_signals") or {}
    jeonse_ratio_pct = (lead.get("jeonse_ratio_24m") or {}).get("value_pct")
    jeonse_verdict = (lead.get("jeonse_ratio_24m") or {}).get("verdict")

    # 좌측 (부동산 매크로)
    _draw_text(d, (80, 640), "한국 10Y", _font(24), C_TERTIARY)
    _draw_text(d, (80, 672), f"{kr_rate:.2f}%" if kr_rate is not None else "—",
               _font(54, bold=True), C_TEXT, stroke_width=2)

    _draw_text(d, (80, 750), "가구 평균 소득", _font(24), C_TERTIARY)
    income_str = f"{income_won / 10_000_000:.1f}천만원" if income_won else "—"
    _draw_text(d, (80, 782), income_str, _font(40, bold=True), C_TEXT, stroke_width=1)

    # 우측 (강남구 시그널)
    _draw_text(d, (560, 640), "강남구 전세가율", _font(24), C_TERTIARY)
    ratio_color = (C_DANGER if (jeonse_ratio_pct is not None and jeonse_ratio_pct < 45)
                   else C_SUCCESS if (jeonse_ratio_pct is not None and jeonse_ratio_pct > 60)
                   else C_WARN)
    _draw_text(d, (560, 672), f"{jeonse_ratio_pct:.1f}%" if jeonse_ratio_pct is not None else "—",
               _font(54, bold=True), ratio_color, stroke_width=2)

    _draw_text(d, (560, 750), "사이클", _font(24), C_TERTIARY)
    _draw_text(d, (560, 782), current_phase[:14], _font(30, bold=True), C_ACCENT, stroke_width=1)

    # ============ 진단 + Footer ============
    diagnosis = _build_integrated_diagnosis(real_yield, vix, kr_rate, jeonse_verdict, current_phase)
    _draw_text(d, (80, 880), "🧠 통합 진단", _font(24, bold=True), C_ACCENT, stroke_width=1)
    diag_lines = _wrap_text(d, diagnosis, _font(26), max_w=920)
    for i, line in enumerate(diag_lines[:2]):
        _draw_text(d, (80, 920 + i * 36), line, _font(26), C_TEXT)

    _draw_text(d, (80, 1020), date_str, _font(22), C_TERTIARY)
    _draw_text(d, (1000, 1020), "@verity_terminal", _font(22, bold=True), C_ACCENT, anchor="ra", stroke_width=1)

    out_path = out_dir / "card.png"
    img.save(out_path, "PNG", optimize=True)

    caption = _build_integrated_caption(date_str, real_yield, vix, top_value, top_sector,
                                        kr_rate, jeonse_ratio_pct, current_phase, diagnosis)
    (out_dir / "caption.txt").write_text(caption, encoding="utf-8")
    hashtags = ["#배리티", "#배리티터미널", "#주식", "#부동산", "#매크로",
                "#섹터", "#전세가율", "#투자정보", "#시장분석", "#일일브리핑"]
    (out_dir / "hashtags.txt").write_text(" ".join(hashtags), encoding="utf-8")

    return {
        "category": "integrated",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "card_path": str(out_path.relative_to(ROOT)),
        "equity": {
            "real_yield_10y": real_yield, "vix": vix,
            "top_value_name": top_value.get("name") if top_value else None,
            "top_sector": top_sector.get("name") if top_sector else None,
        },
        "estate": {
            "kr_treasury_10y_pct": kr_rate,
            "annual_median_income_won": income_won,
            "gangnam_jeonse_ratio_pct": jeonse_ratio_pct,
            "current_phase": current_phase,
        },
        "diagnosis": diagnosis,
    }


def _build_integrated_diagnosis(real_yield, vix, kr_rate, jeonse_verdict, current_phase) -> str:
    parts = []
    # 주식 part
    if real_yield is not None:
        if real_yield > 2.0:
            parts.append("미국 실질금리 부담")
        elif real_yield < 1.0:
            parts.append("미국 실질금리 둔화")
    if vix is not None and vix > 25:
        parts.append(f"변동성 경계(VIX {vix:.0f})")
    # 부동산 part
    if jeonse_verdict == "reverse_lease_risk":
        parts.append("전세가율 역레버리지 리스크")
    elif jeonse_verdict == "tightening_pressure":
        parts.append("전세 상승 압력")
    if current_phase and current_phase != "—":
        parts.append(f"부동산 사이클 「{current_phase}」")
    return ". ".join(parts) + "." if parts else "주식·부동산 데이터 정합 진행 중."


def _build_integrated_caption(date_str, real_yield, vix, top_value, top_sector,
                              kr_rate, jeonse_ratio, current_phase, diagnosis) -> str:
    lines = [f"📊 배리티 통합 브리핑 · {date_str}", "",
             "━━ 📈 주식 ━━"]
    if real_yield is not None:
        lines.append(f"실질금리(10Y): {real_yield:.2f}%")
    if vix is not None:
        lines.append(f"VIX: {vix:.1f}")
    if top_value:
        tv = top_value.get("trading_value") or 0
        tv_str = f"{tv / 1_000_000_000_000:.2f}조원" if tv >= 1_000_000_000_000 else f"{tv / 100_000_000:.0f}억원"
        lines.append(f"거래대금 1위: {top_value.get('name')} ({tv_str})")
    if top_sector:
        chg = top_sector.get("change_pct")
        lines.append(f"유입 1위 섹터: {top_sector.get('name')} ({chg:+.2f}%)")
    lines += ["", "━━ 🏠 부동산 ━━"]
    if kr_rate is not None:
        lines.append(f"한국 10Y 금리: {kr_rate:.2f}%")
    if jeonse_ratio is not None:
        lines.append(f"강남구 전세가율: {jeonse_ratio:.1f}%")
    if current_phase and current_phase != "—":
        lines.append(f"사이클: {current_phase}")
    lines += ["", f"🧠 {diagnosis}",
              "",
              "📈 주식: verity-terminal.framer.website",
              "🏠 부동산: verity-estate.framer.website"]
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
    parser.add_argument("--category", choices=["macro", "sector", "micro", "news_impact", "integrated", "all"],
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

    cats = ["integrated", "macro", "sector", "micro", "news_impact"] if args.category == "all" else [args.category]

    # 추가 입력 (sector / micro / news_impact / integrated)
    sectors_data = portfolio.get("sectors") or []
    sector_rotation_data = portfolio.get("sector_rotation") or {}
    recommendations_data = json.loads((ROOT / "data" / "recommendations.json").read_text(encoding="utf-8")) \
        if (ROOT / "data" / "recommendations.json").exists() else []
    headlines_data = portfolio.get("headlines") or portfolio.get("bloomberg_google_headlines") or []
    estate_brain_data = json.loads(ESTATE_BRAIN_PATH.read_text(encoding="utf-8")) \
        if ESTATE_BRAIN_PATH.exists() else {}

    if "integrated" in cats:
        out = out_root / "integrated"
        out.mkdir(exist_ok=True)
        meta = render_integrated(macro, recommendations_data, sectors_data,
                                 sector_rotation_data, estate_brain_data, out, date_str)
        (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        results.append(meta)
        print(f"✓ integrated → {out.relative_to(ROOT)} ⭐")

    if "macro" in cats:
        out = out_root / "macro"
        out.mkdir(exist_ok=True)
        meta = render_macro(macro, out, date_str)
        (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        results.append(meta)
        print(f"✓ macro → {out.relative_to(ROOT)}")

    if "sector" in cats:
        out = out_root / "sector"
        out.mkdir(exist_ok=True)
        meta = render_sector(sectors_data, sector_rotation_data, out, date_str)
        (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        results.append(meta)
        print(f"✓ sector → {out.relative_to(ROOT)}")

    if "micro" in cats:
        out = out_root / "micro"
        out.mkdir(exist_ok=True)
        meta = render_micro(recommendations_data, out, date_str)
        (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        results.append(meta)
        print(f"✓ micro → {out.relative_to(ROOT)}")

    if "news_impact" in cats:
        out = out_root / "news_impact"
        out.mkdir(exist_ok=True)
        meta = render_news_impact(headlines_data, out, date_str)
        (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        results.append(meta)
        print(f"✓ news_impact → {out.relative_to(ROOT)}")

    print(f"\n생성 완료: {len(results)}건 · {out_root.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
