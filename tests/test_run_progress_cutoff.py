"""run_progress — 런타임 예산 소진 시 미처리 신고 회귀 테스트 (네트워크 0).

2026-08-13 신설. 고정하려는 사고:

  full run 31745952833 이 자체 예산 110분을 소진해 SIGTERM 종료됐다. 죽은 지점 = Gemini 배치
  **16/50** → 상위 50종목 중 34개가 AI 종합 없이 남았다. 그런데 발행 단계는 정상 완료해서
  (blob 1,331건 0 실패) `data_health` 는 **green** 이었다. 결손이 초록불 뒤에 숨는다.

  예산을 늘리는 건 별개 판단이고 늘려도 언젠가 또 걸린다. 그때도 안 보이는 게 진짜 문제라
  먼저 보이게 만든다. 이 모듈은 판정도 수정도 하지 않는다 — 신고만 한다.

계약:
  ① 끊긴 자리의 done/total 로 미처리 건수를 낸다
  ② 예산 소진과 외부 취소를 **구분**한다 — 섞으면 예산 문제 빈도를 잘못 센다
  ③ 결손 0 이어도, 진척 등록이 아예 없어도 **빈 문자열로 삼키지 않는다**
  ④ 장부 기록은 신호 핸들러에서 불리므로 절대 예외를 밖으로 내보내지 않는다
"""
from __future__ import annotations

import json

import pytest

from api.observability import run_progress as rp


@pytest.fixture(autouse=True)
def _reset():
    rp.reset()
    yield
    rp.reset()


def test_shortfall_counts_unprocessed():
    """① 8/13 실제 상황 재현 — Gemini 16/50 에서 끊기면 미처리 34."""
    rp.set_stage("gemini_batch", 16, 50, "종목")
    rp.mark_cutoff("runtime_budget")

    text = rp.format_shortfall()

    assert "런타임 예산 소진" in text
    assert "16/50종목" in text
    assert "미처리 34종목" in text
    assert "32%" in text


def test_budget_and_external_cancel_are_distinguished():
    """② 사유 구분 — watchdog 이 먼저 못박으면 예산, 아니면 외부 종료."""
    rp.set_stage("gemini_batch", 3, 10)
    assert "외부 종료" in rp.format_shortfall()

    rp.mark_cutoff("runtime_budget")
    assert "런타임 예산 소진" in rp.format_shortfall()

    # 먼저 기록된 사유가 이긴다 — 핸들러가 덮어쓰지 못한다
    rp.mark_cutoff("external_sigterm")
    assert "런타임 예산 소진" in rp.format_shortfall()


def test_completed_and_empty_are_still_reported():
    """③ 결손 0 · 등록 0 도 말로 남긴다. 빈 문자열 = 삼킴."""
    rp.mark_cutoff("runtime_budget")
    assert "진척 등록 단계 없음" in rp.format_shortfall()

    rp.set_stage("gemini_batch", 50, 50, "종목")
    text = rp.format_shortfall()
    assert text.strip() and "미처리 0" in text


def test_multiple_stages_only_incomplete_listed():
    rp.set_stage("collect", 120, 120, "종목")
    rp.set_stage("gemini_batch", 16, 50, "종목")
    rp.set_stage("claude_deep", 0, 5, "종목")
    rp.mark_cutoff("runtime_budget")

    text = rp.format_shortfall()
    assert "미처리 2개 단계" in text
    assert "collect" not in text
    assert "gemini_batch" in text and "claude_deep" in text


def test_append_row_writes_ledger(tmp_path):
    rp.set_stage("gemini_batch", 16, 50, "종목")
    rp.mark_cutoff("runtime_budget")
    p = tmp_path / "runtime_cutoff.jsonl"

    assert rp.append_cutoff_row(str(p), extra={"partial_portfolio_saved": True}) is True

    row = json.loads(p.read_text(encoding="utf-8").strip())
    assert row["reason"] == "runtime_budget"
    assert row["partial_portfolio_saved"] is True
    assert row["shortfall"] == [
        {"stage": "gemini_batch", "done": 16, "total": 50, "missing": 34, "unit": "종목"}
    ]


def test_append_row_never_raises(monkeypatch):
    """④ 신호 핸들러 안전 — 쓰기 실패해도 종료 흐름을 막지 않는다."""
    rp.set_stage("gemini_batch", 1, 2)

    def boom(*_a, **_k):
        raise OSError("read-only fs")

    monkeypatch.setattr(rp, "open", boom, raising=False)
    monkeypatch.setattr(rp.os, "makedirs", boom)

    assert rp.append_cutoff_row("/nope/runtime_cutoff.jsonl") is False


def test_zero_total_does_not_crash():
    """total=0 이면 비율을 못 내므로 결손으로 세지 않는다(0 나눗셈 방지)."""
    rp.set_stage("empty_stage", 0, 0)
    rp.mark_cutoff("runtime_budget")
    assert "미처리 0" in rp.format_shortfall()
