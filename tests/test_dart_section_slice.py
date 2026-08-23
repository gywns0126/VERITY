# -*- coding: utf-8 -*-
"""사업보고서 'II. 사업의 내용' 섹션 선택 규칙 (2026-08-23 신설).

## 왜

선택 규칙이 **두 번** 틀렸고, 두 번 다 조용했다. 산출물(`raw_text`)은 매번 그럴듯한
분량으로 채워졌기 때문에 길이·건수 어느 지표로도 잡히지 않았다. 실제로 드러난 건
「1. 사업의 개요」를 뽑으려 했을 때, **대형주만 골라서** 실패하면서였다.

| 결함 | 실측 | 여파 |
|---|---|---|
| `max(matches, key=len)` | 삼성전자 pat1 매칭 4개 중 최장 131,262자가 'I. 회사의 개요' 종속기업 표에서 시작 | 60,000자 상한에 잘려 개요가 통째로 소멸 |
| pat1 이 600자만 넘으면 확정 | 현대차·SK 는 pat1 에 소제목 있는 매칭이 없는데 거기서 끝남 | pat3 의 정답에 도달 못 함 |
| 캡처가 소제목을 소비 | 삼성전기 본문 5,442자는 정확히 개요인데 머리가 잘림 | 하류가 앵커를 못 찾음 |

시총 상위 60 중 **23종목**이 이 형태였다. "가장 많이 보는 종목이 가장 얇다"(PM).
"""
from __future__ import annotations

from api.collectors.DartScout import _select_business_section

PROSE = "당사는 반도체 장비를 제조하고 있습니다. 주요 고객은 국내외 반도체 제조사입니다. "
REAL_SECTION = ("II. 사업의 내용\n\n1. 사업의 개요\n\n" + PROSE * 30
                + "\n\n2. 주요 제품 및 서비스\n\n제품 표\n\n")
# 상호참조에서 시작해 다음 'III. 재무' 까지 삼키는 잘못된 스팬. 실제 문서에서는 이쪽이 **더 길다**
# (삼성전자 실측 131,262자 vs 진짜 39,270자).
DECOY_SECTION = ("II. 사업의 내용을 참고하시기 바랍니다.\n\n마. 연결대상 종속회사 현황\n\n"
                 + "표 셀\n\n" * 2000 + "III. 재무에 관한 사항\n\n(목차 끝)\n\n")


def test_prefers_the_headed_match_over_the_longer_decoy():
    """🚨 최장 매칭이 아니라 **소제목을 머리에 가진** 매칭을 고른다 (삼성전자 형태)."""
    doc = ("I. 회사의 개요\n\n" + DECOY_SECTION + REAL_SECTION
           + "III. 재무에 관한 사항\n\n재무제표\n")
    sec = _select_business_section(doc)
    # 미끼가 4배 이상 길지만 선택되면 안 된다
    assert len(DECOY_SECTION) > 4 * len(REAL_SECTION)
    assert sec.startswith("II. 사업의 내용\n")
    assert "1. 사업의 개요" in sec[:200]
    assert "연결대상 종속회사 현황" not in sec


def test_falls_through_to_a_later_pattern_when_pattern1_has_no_heading():
    """🚨 pat1 이 600자를 넘겨도 소제목이 없으면 확정하지 않는다 (현대차·SK 형태)."""
    doc = ("II. 사업의 내용을 참조\n\n" + "잡동사니 표\n\n" * 200
           + "III. 재무에 관한 사항\n\n"
           + "사업의 개요\n\n" + PROSE * 30 + "\n\n이사의 경영진단\n")
    sec = _select_business_section(doc)
    assert sec.startswith("사업의 개요")
    assert "잡동사니" not in sec


def test_heading_is_kept_inside_the_slice():
    """🚨 소제목을 소비하면 하류가 개요를 찾을 수 없다 (삼성전기 형태)."""
    doc = "사업의 개요\n\n" + PROSE * 30 + "\n\n재무제표\n"
    sec = _select_business_section(doc)
    assert sec.startswith("사업의 개요")


def test_short_table_of_contents_entry_does_not_win():
    """목차의 '1. 사업의 개요 ----- 16' 은 소제목이지만 실질 본문이 아니다(>600자 요구)."""
    toc = "II. 사업의 내용\n\n1. 사업의 개요\n\n-----------------\n\n16\n\n"
    doc = (toc + "III. 재무에 관한 사항\n\n목차 끝\n\n"
           + "사업의 개요\n\n" + PROSE * 30 + "\n\n재무제표\n")
    sec = _select_business_section(doc)
    assert len(sec) > 600
    assert PROSE.strip() in sec


def test_falls_back_to_longest_when_no_heading_anywhere():
    """하위호환 — 소제목이 어디에도 없으면 종전 규칙(최장)을 쓴다. 침묵 반환 금지."""
    doc = "II. 사업의 내용\n\n" + "본문 서술이 이어집니다. " * 60 + "\n\nIII. 재무에 관한 사항\n"
    sec = _select_business_section(doc)
    assert len(sec) > 600
    assert "본문 서술" in sec


def test_no_match_returns_empty_string():
    assert _select_business_section("V. 회계감사인의 감사의견\n\n표\n") == ""
