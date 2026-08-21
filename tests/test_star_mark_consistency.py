"""보유/관심 별 마크 일관성 — 회귀 가드 (2026-08-22).

PM 지적: 둥지 보유종목 추가 UI 가 **보라 배경 + 문자 ★** 였는데
리포트 헤더는 **소프트골드 둥근 SVG** 였다. 같은 사이트에서 같은 뜻의 마크가
두 형태로 보였다 — *"리포트에서 쓰는것처럼 노랑색 모서리가 둥근 별 모양으로 바꿔"*.

🚨 문자 ★ 로 되돌리지 말 것 — 폰트마다 모양·굵기가 달라 렌더가 흔들린다.
🚨 path 는 리포트와 **동일해야** 한다. 한쪽만 바꾸면 두 화면이 갈린다.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
HOLD = ROOT / "framer-components" / "public-probe" / "PublicHoldingsTab.tsx"
REPORT = ROOT / "framer-components" / "public-probe" / "PublicStockReport.tsx"

# 리포트 헤더 별의 path 앞부분 — 두 파일이 같은 자산을 쓰는지 대조하는 지문
STAR_PATH_HEAD = "M11.525 2.295a.53.53 0 0 1 .95 0l2.31 4.679"
GOLD = "#f6b93b"


def _src(p):
    if not p.exists():
        pytest.skip(f"{p.name} 없음")
    return p.read_text(encoding="utf-8")


def test_holdings_uses_svg_star_not_glyph():
    s = _src(HOLD)
    assert "function StarMark" in s, "StarMark 컴포넌트가 사라졌다"
    # 렌더 텍스트에 문자 ★ 가 남아 있으면 안 된다(주석은 허용).
    # 🚨 startswith 로 주석을 가르면 블록 주석 **본문 줄**(들여쓴 설명·JSX 주석)을 못 거른다
    #    — 내가 1차에 그렇게 짜서 오탐 3건이 났다. 블록/라인 주석을 실제로 제거하고 본다.
    stripped = re.sub(r"/\*.*?\*/", "", s, flags=re.S)
    stripped = re.sub(r"^\s*//.*$", "", stripped, flags=re.M)
    render_lines = [l for l in stripped.splitlines() if "★" in l]
    assert not render_lines, f"렌더 경로에 문자 ★ 잔존: {render_lines[:2]}"


def test_star_color_is_soft_gold():
    s = _src(HOLD)
    assert GOLD in s, f"소프트골드 {GOLD} 가 사라졌다"
    assert "AN_STAR_GOLD" in s


def test_star_path_matches_report():
    """🚨 두 화면이 같은 별을 써야 한다 — 한쪽만 바뀌면 갈린다."""
    h, r = _src(HOLD), _src(REPORT)
    assert STAR_PATH_HEAD in r, "리포트 별 path 가 바뀌었다 — 이 테스트의 기준을 갱신할 것"
    assert STAR_PATH_HEAD in h, "둥지 별 path 가 리포트와 다르다"


def test_rounded_corners_preserved():
    s = _src(HOLD)
    i = s.find("function StarMark")
    blk = s[i:i + 900]
    assert 'strokeLinejoin="round"' in blk, "모서리 둥글림(strokeLinejoin)이 사라졌다"
    assert 'strokeLinecap="round"' in blk
