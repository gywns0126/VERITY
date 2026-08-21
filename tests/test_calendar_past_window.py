"""캘린더 과거 이벤트 창 — 회귀 가드 (2026-08-21).

사고: 배당 1,322건(전체의 **88%**)이 `2025-12-30` **하루**에 박제돼 있었다.
한국 결산배당 ex_date 가 12월 말에 몰리는데 우리가 가진 건 2025 결산분뿐이고
2026 결산배당은 11~12월에나 공시된다(`dividends_kr.json` 실측 = ex_date 2025-12 가
1,322/1,322 = 100%, dividend_type 전부 year_end).

그 결과 ① 2026 어느 달을 열어도 배당 0건 ② 월별 카운트·전체 통계가 8개월 전 하루로
왜곡 ③ 배당 필터 칩이 사실상 죽은 칩이었다.

🚨 창을 되돌리면 같은 왜곡이 재발한다. 미래 이벤트는 창과 무관하게 전부 남는다.
🚨 잘라낸 건수를 신고해야 한다 — "배당이 원래 없다" 와 "창 밖이라 뺐다" 는 다른 사실이다.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "api" / "builders" / "calendar_public_builder.py"
OUT = ROOT / "data" / "calendar_public.json"


def test_builder_has_past_window():
    s = SRC.read_text(encoding="utf-8")
    assert "PAST_WINDOW_DAYS" in s, "과거 창 상수가 사라졌다 — 화석 이벤트가 되돌아온다"
    assert "dropped_past" in s, "잘라낸 건수 자기신고가 사라졌다"


def test_output_selfreports_window():
    if not OUT.exists():
        pytest.skip("산출물 없음")
    m = json.loads(OUT.read_text(encoding="utf-8"))["_meta"]
    for k in ("past_window_days", "past_cutoff", "dropped_past", "dropped_total"):
        assert k in m, f"자기신고 키 누락: {k}"
    assert m["counts"]["total"] == m["counts"]["disclosure"] + m["counts"]["dividend"] + m["counts"]["ipo"]


def test_no_event_older_than_cutoff():
    if not OUT.exists():
        pytest.skip("산출물 없음")
    d = json.loads(OUT.read_text(encoding="utf-8"))
    cut = d["_meta"]["past_cutoff"]
    old = [e for e in d["events"] if e["date"] < cut]
    assert not old, f"창 밖 이벤트가 {len(old)}건 남아 있다: {old[:3]}"


def test_future_events_are_not_windowed():
    """🚨 미래는 자르면 안 된다 — IPO·예정 공시가 사라진다."""
    if not OUT.exists():
        pytest.skip("산출물 없음")
    d = json.loads(OUT.read_text(encoding="utf-8"))
    today = dt.date.today().isoformat()
    fut = [e for e in d["events"] if e["date"] > today]
    # 미래 이벤트가 하나라도 있으면 창이 미래를 안 자른다는 뜻(IPO 는 보통 존재)
    if not fut:
        pytest.skip("오늘 기준 미래 이벤트가 없는 날 — 판정 불가")
    assert len(fut) > 0


def test_single_day_does_not_dominate():
    """🚨 이 사고의 형태 — 한 날짜가 전체의 절반을 넘으면 화석일 가능성이 높다."""
    if not OUT.exists():
        pytest.skip("산출물 없음")
    d = json.loads(OUT.read_text(encoding="utf-8"))
    ev = d["events"]
    if len(ev) < 20:
        pytest.skip("표본 부족")
    from collections import Counter
    top_date, top_n = Counter(e["date"] for e in ev).most_common(1)[0]
    share = top_n / len(ev)
    assert share < 0.5, (
        f"{top_date} 하루가 전체의 {share:.0%} — 화석 이벤트 의심(2025-12-30 사고 형태)"
    )
