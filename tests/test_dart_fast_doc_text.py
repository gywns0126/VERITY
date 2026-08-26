# -*- coding: utf-8 -*-
"""DART 문서 본문 스트립 — BeautifulSoup 대체 (2026-08-26 신설).

## 왜

개요 드립이 종목당 **3~7초 → 25~38초**로 느려졌다. 구간 계측 결과
`BeautifulSoup(html.parser)` 가 **전체의 80%**(13.84MB 문서에서 4.94s / 6.17s)였다.
이 속도면 잔여 479종목에 18일이 걸린다.

실측 5개 사업보고서(9.0~16.2MB) — 슬라이스 결과 **공백 제거 기준 전건 동일**,
3.78~5.64s → **0.25~0.42s (13~16배)**.

## 🚨 여기서 고정하는 것 — 한글 꺾쇠

순진한 `<[^>]+>` 는 **본문의 한글 꺾쇠를 태그로 오인해 지운다.**
삼성전자 사업보고서 실측 — `<TV시장점유율추이>` `<스마트폰시장점유율추이>`
`<DRAM시장점유율추이>` `<스마트폰패널시장점유율추이>` `<디지털콕핏시장점유율추이>`
**표 제목 5건이 통째로 삭제**돼 BeautifulSoup 대비 66자를 잃었다.
그래서 태그명을 **ASCII 로 한정**한다.

## 2026-05-26 lxml 교훈과의 관계

그건 **파서가 비표준 구조에서 본문을 조용히 버린** 사건이다. 여기는 파싱하지 않고
태그만 지우므로 같은 실패를 하지 않는다. 다만 형태를 못 따라갈 경우에 대비해
호출부에 **비율 안전망**(본문/원시 1% 하한, 실측 5.51~8.31%)을 둔다.
"""
from __future__ import annotations

import re

from api.collectors import DartScout as D


def _txt(s):
    return re.sub(r"\s", "", D._fast_doc_text(s))


def test_strips_real_tags():
    assert _txt("<P>가나</P>") == "가나"
    assert _txt('<P ALIGN="CENTER">가</P>') == "가"
    assert _txt("<TABLE><TR><TD>가</TD></TR></TABLE>") == "가"
    assert _txt("<BR/>가") == "가"


def test_keeps_hangul_angle_brackets():
    """🚨 핵심 회귀 방지 — 본문의 한글 꺾쇠는 태그가 아니다(삼성전자 표 제목 5건)."""
    for s in ("<TV시장점유율추이>", "<스마트폰시장점유율추이>", "<DRAM시장점유율추이>",
              "<디지털콕핏시장점유율추이>"):
        assert s.replace(" ", "") in _txt(f"<P>{s}</P>"), f"한글 꺾쇠가 지워졌다: {s}"


def test_keeps_non_ascii_leading_angle_text():
    assert "<사업의개요>" in _txt("<P><사업의 개요></P>")


def test_strips_comments_and_declarations():
    assert _txt("<!-- 주석 > 안에 꺾쇠 -->가") == "가"
    assert _txt('<?xml version="1.0"?><P>가</P>') == "가"
    assert _txt("<!DOCTYPE html><P>가</P>") == "가"


def test_cdata_content_is_kept():
    assert "가나" in _txt("<P><![CDATA[가나]]></P>")


def test_script_and_style_bodies_are_dropped():
    assert _txt("<style>.x{a:1}</style><P>가</P>") == "가"
    assert _txt("<script>var a='<b>';</script><P>가</P>") == "가"


def test_entities_are_unescaped():
    assert _txt("<P>&amp;&lt;&gt;</P>") == "&<>"


def test_tags_become_newlines_so_line_anchors_survive():
    """🚨 공백이 아니라 **개행**으로 바꾼다 — 슬라이스가 줄 앵커(`(?m)^…$`)에 의존한다."""
    out = D._fast_doc_text("<P>1. 사업의 개요</P><P>당사는</P>")
    assert re.search(r"(?m)^\s*1\. 사업의 개요\s*$", out), "줄 경계가 사라졌다"


def test_safety_net_threshold_is_defined_and_conservative():
    assert hasattr(D, "_STRIP_MIN_RATIO")
    assert 0 < D._STRIP_MIN_RATIO <= 0.02, "실측 하한 5.51% 대비 여유가 있어야 한다"
