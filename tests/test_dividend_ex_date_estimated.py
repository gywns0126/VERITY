"""배당락일이 추정치임을 산출물이 신고하는가 (2026-08-22).

🚨 실측: `dividends_kr.json` 1,322행의 ex_date 가 **전부 정확히 2025-12-30** 이다.
그건 실제 배당락일이 아니라 `_estimate_ex_date(2025, "year_end")` 의 하드코딩 반환값이다.
DART `alotMatter`(사업보고서 배당에 관한 사항)도 pykrx DPS 도 **배당락일을 주지 않는다**.

그런데 캘린더가 이를 "배당락" 으로만 표시해 **확정 사실처럼** 보였다(RULE 7 소지).
`is_confirmed` 는 **금액** 확정 여부이지 날짜가 아니라는 점이 혼동의 핵심이다.

🚨 한국은 배당절차 개선으로 배당기준일이 배당액 결정 이후로 이동 중이라
12/30 가정은 시간이 갈수록 빗나간다. 확정일은 현금·현물배당결정 공시 본문의
배당기준일을 봐야 한다(Tier 2 확장 = 별건).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
COL = ROOT / "api" / "collectors" / "dividend_kr.py"
CAL = ROOT / "api" / "builders" / "calendar_public_builder.py"
DIV = ROOT / "data" / "dividends_kr.json"
OUT = ROOT / "data" / "calendar_public.json"


def test_collector_flags_estimated_ex_date():
    s = COL.read_text(encoding="utf-8")
    assert s.count('"ex_date_estimated": True') >= 2, (
        "추정 ex_date 를 만드는 지점에 신고 필드가 빠졌다"
    )


def test_calendar_distinguishes_amount_vs_date_confidence():
    s = CAL.read_text(encoding="utf-8")
    assert "ex_date_estimated" in s, "캘린더가 날짜 추정 여부를 안 읽는다"
    assert "(추정일)" in s, "추정 날짜 태그가 사라졌다 — 확정으로 읽힌다"
    assert "date_estimated" in s, "이벤트에 날짜 추정 플래그가 안 실린다"


def test_no_estimated_row_lacks_flag():
    """🚨 _estimate_ex_date 산식과 일치하는 행은 반드시 추정으로 표기돼야 한다."""
    if not DIV.exists():
        pytest.skip("배당 데이터 없음")
    d = json.loads(DIV.read_text(encoding="utf-8"))
    bad = []
    for tk, rows in d.items():
        if not isinstance(rows, list):
            continue
        for r in rows:
            if not isinstance(r, dict) or "_meta" in r:
                continue
            e = r.get("ex_date")
            if not e:
                continue
            if r.get("dividend_type") == "year_end" and e == f"{e[:4]}-12-30":
                if not r.get("ex_date_estimated"):
                    bad.append((tk, e))
    assert not bad, f"추정 산식과 같은 날짜인데 미표기: {len(bad)}건 예 {bad[:3]}"


def test_calendar_dividend_events_carry_flag():
    if not OUT.exists():
        pytest.skip("캘린더 없음")
    d = json.loads(OUT.read_text(encoding="utf-8"))
    divs = [e for e in d["events"] if e.get("cat") == "dividend"]
    if not divs:
        pytest.skip("현재 창에 배당 이벤트 없음(정상 — 결산배당은 12월 말)")
    for e in divs:
        assert "date_estimated" in e, "배당 이벤트에 날짜 추정 플래그가 없다"
        if e["date_estimated"]:
            assert "추정" in e["tag"], f"추정인데 태그가 사실처럼 보인다: {e['tag']}"
