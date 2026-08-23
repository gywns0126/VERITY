# -*- coding: utf-8 -*-
"""사업보고서 「1. 사업의 개요」 추출 (2026-08-23 신설).

## 왜

PM 지적 = "1,210종목 사업보고서 원문을 이미 받아놓고 「사업의 개요」를 안 뽑고 있다".
원천(`dart_raw_cache` 의 `raw_text`)은 이미 디스크에 있었고, 뽑는 코드만 없었다.
공개 리포트의 `business` 는 운영풀 태그라인이라 16/1,790(0.9%)뿐이었다.

## 여기서 고정하는 것

이 파일은 **캘리브레이션 회귀 방지**가 목적이다. 게이트를 감으로 조이거나 풀면
아래 실측 사례들이 다시 깨진다.

| 사례 | 실측 | 고정 |
|---|---|---|
| 주어 토큰 게이트 | "당사/회사" 요구 → 86건 반려, 표본은 **정상 개요** | 주어 요구 금지 |
| 카카오 소제목 | `1. (제조서비스업)사업의 개요` | 괄호 수식어 허용 |
| 다음 소제목 오검출 | `3.8%` 가 "3. 8%" 로 잡힘 | 점 뒤 공백 + 비숫자 요구 |
| 용어정리표 머리 | 사피엔반도체·리메드 등 서술밀도 <2.5 | 앞머리 절단 후 재판정 |
| 표 슬라이스 | 신용평가표·계열회사표 | 서술밀도 하한으로 반려 |
"""
from __future__ import annotations

import pytest

from api.analyzers.dart_business_overview import (
    ANCHOR,
    NEXT_HEAD,
    extract_overview,
    row_from_doc,
)

PROSE = ("당사는 반도체 장비를 제조하고 있습니다. 주요 고객은 국내외 반도체 제조사입니다. "
         "생산능력은 연간 1,200대이며 수출 비중은 60%입니다. ")


def _doc(head: str, body: str = PROSE * 6, tail: str = "\n\n2. 주요 제품 및 서비스\n\n표") -> str:
    return f"I. 회사의 개요\n\n연혁 표\n\nII. 사업의 내용\n\n{head}\n\n{body}{tail}"


# ── 소제목 인식 ──────────────────────────────────────────────────────────────
@pytest.mark.parametrize("head", [
    "1. 사업의 개요",
    "가. 사업의 개요",
    "사업의 개요",
    "1. 사업 개요",
    "1. (제조서비스업)사업의 개요",   # 🚨 카카오 2025 실측 — 이 한 글자에 대형주가 걸렸다
])
def test_anchor_variants_are_recognized(head):
    r = extract_overview(_doc(head))
    assert r["ok"], r["reason"]
    assert r["text"].startswith("당사는 반도체")


def test_inline_mention_is_not_an_anchor():
    """본문 안 '사업의 개요를 참조' 는 소제목이 아니다 — 줄 전체일 때만 앵커."""
    raw = "II. 사업의 내용\n\n자세한 내용은 사업의 개요를 참조하시기 바랍니다.\n\n" + PROSE * 6
    assert not ANCHOR.search(raw)


# ── 종료 경계 ────────────────────────────────────────────────────────────────
def test_next_heading_bounds_the_body():
    r = extract_overview(_doc("1. 사업의 개요"))
    assert r["next_heading"] == "2. 주요 제품 및 서비스"
    assert "주요 제품 및 서비스" not in r["text"]


def test_decimal_number_is_not_mistaken_for_a_heading():
    """🚨 '3.8%' 를 'N. 제목' 으로 읽으면 본문이 거기서 잘린다 (실측 오검출)."""
    assert NEXT_HEAD.search("3.8%") is None
    assert NEXT_HEAD.search("2.06%") is None
    assert NEXT_HEAD.search("2. 주요 제품 및 서비스") is not None


def test_roman_section_bounds_the_body():
    raw = ("II. 사업의 내용\n\n1. 사업의 개요\n\n" + PROSE * 6
           + "\n\nIII. 재무에 관한 사항\n\n재무제표")
    r = extract_overview(raw)
    assert r["ok"]
    assert "재무에 관한 사항" not in r["text"]


# ── 게이트 ───────────────────────────────────────────────────────────────────
def test_subject_token_is_not_required():
    """🚨 회귀 방지 — 주어를 요구하면 정상 개요 86건이 죽는다.

    실측 반례: 푸른저축은행 '당 저축은행' · 백산 '지배기업인 (주)백산' · 송원산업 '연결기업'.
    """
    body = ("지배기업 및 종속기업의 주요 제품은 합성피혁으로서 스포츠용 신발과 "
            "전자제품 케이스용으로 생산되고 있습니다. 주요 시장은 동남아시아입니다. ") * 4
    r = extract_overview(_doc("1. 사업의 개요", body=body))
    assert r["ok"], r["reason"]
    assert "당사" not in r["text"]


def test_table_slice_is_rejected_by_prose_density():
    body = "\n\n".join(["평가일", "평가내용", "기업신용등급", "A", "한국평가데이터", "-"] * 40)
    r = extract_overview(_doc("1. 사업의 개요", body=body, tail=""))
    assert not r["ok"]
    assert r["reason"].startswith("not_prose") or r["reason"] == "too_short"


def test_short_reference_stub_is_rejected():
    r = extract_overview(_doc("1. 사업의 개요", body="'7. 기타 참고사항'을 참조하시기 바랍니다.",
                              tail=""))
    assert not r["ok"]
    assert r["reason"] == "too_short"


def test_glossary_head_is_stripped_before_judging():
    """용어정리표가 앞에 붙어 서술밀도를 끌어내리는 형태 — 잘라내고 다시 본다."""
    glossary = "[용어 정리]\n\n용어\n\n설명\n\nDDIC\n\n디스플레이 구동 IC\n\nAP\n\n애플리케이션 프로세서\n\n"
    r = extract_overview(_doc("1. 사업의 개요", body=glossary + PROSE * 6, tail=""))
    assert r["ok"], r["reason"]
    assert r["glossary_stripped"] is True
    assert r["text"].startswith("당사는 반도체")


def test_missing_anchor_reports_a_reason():
    """🚨 반려는 사유를 남긴다 — 숫자 하나로 뭉개면 무엇이 빠졌는지 영영 모른다(RULE 13 ③)."""
    r = extract_overview("V. 회계감사인의 감사의견 등\n\n감사인 표\n\n" + PROSE)
    assert not r["ok"]
    assert r["reason"] == "anchor_not_found"


def test_empty_input_reports_a_reason():
    assert extract_overview("")["reason"] == "raw_text_empty"


# ── 절단 ─────────────────────────────────────────────────────────────────────
def test_truncation_is_self_reported_and_cut_at_a_sentence():
    r = extract_overview(_doc("1. 사업의 개요", body=PROSE * 60, tail=""), max_chars=400)
    assert r["ok"]
    assert r["truncated"] is True
    assert len(r["text"]) <= 400
    assert r["text"].rstrip().endswith("다.")


def test_row_from_doc_carries_provenance():
    doc = {"raw_text": _doc("1. 사업의 개요"), "rcept_no": "20260310002820",
           "rcept_dt": "20260310", "bsns_year": "2025", "report_nm": "사업보고서 (2025.12)"}
    row = row_from_doc(doc, "00126380", "2025", name="삼성전자")
    assert row is not None
    # 출처 추적 3종 — 접수번호·접수일·사업연도가 없으면 원문 대조가 불가능해진다
    assert row["rcept_no"] == "20260310002820"
    assert row["rcept_dt"] == "20260310"
    assert row["bsns_year"] == "2025"
    assert row["char_count"] == len(row["text"])


def test_row_from_doc_returns_none_on_reject():
    assert row_from_doc({"raw_text": "표\n\n표\n\n표"}, "00000000", "2025") is None
