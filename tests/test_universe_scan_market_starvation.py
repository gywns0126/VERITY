"""universe scan — market 단위 결식 가드.

2026-07-27 실사고 재현 방지. 기존 fallback 은 candidates *전체* 0 건만 봤고, 한쪽 시장만
비면 통과시켜 오염 snapshot 이 굳었다:
  · 15:30 스캔 `[Phase 2-A] KR universe build 실패 → KRX OpenAPI K1 빈 응답`
    → snapshot 후보 15건 전부 US (kr_count=0 인데 ok=true / used_prev_snapshot=false)
  · 16:07 daily_analysis_full 이 fast path 로 그 snapshot 을 물어 `최종 후보: 15개`
    → 그날 KR 추천 11 → 1 붕괴(관심종목 1건만 잔존)
  · 19:41 재스캔은 KR 10 자가복구했으나 이미 산출된 recommendations 는 KR 1 고정
"""
import json
from datetime import datetime, timedelta, timezone

import pytest

import api.builders.universe_scan_builder as USB


_KST = timezone(timedelta(hours=9))


def _ago(hours: float) -> str:
    """지금부터 N시간 전 KST 문자열.

    🚨 2026-07-28: 여기에 고정 날짜를 쓰면 테스트가 달력과 함께 썩는다. 실제로
    "2026-07-24T15:37:38+09:00" 이 승계 상한(96h)을 넘긴 7/28 오후에 CI 가 깨졌다
    (age=99.7h). 검증 대상은 **상대 나이**지 특정 날짜가 아니므로 now 기준으로 만든다.
    """
    return (datetime.now(_KST) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%S+09:00")


def _kr(t):
    return {"ticker": t, "currency": "KRW", "market": "KOSPI"}


def _us(t):
    return {"ticker": t, "currency": "USD", "market": "NASDAQ"}


@pytest.fixture
def snap(tmp_path, monkeypatch):
    """OUTPUT_PATH 를 tmp 로 돌리고, 이번 run 산출을 주입하는 헬퍼 반환."""
    out = tmp_path / "universe_candidates.json"
    monkeypatch.setattr(USB, "OUTPUT_PATH", str(out))
    # 🚨 2026-08-25 — 승격 소스도 격리한다. 되돌리지 말 것.
    #   `merge_promoted`(6e0a2cfa9, 상승 신호 승격)가 실제 `data/metadata/multibagger_promote.json`
    #   을 읽는데 이 픽스처가 그걸 안 막았다. 8/24 크론이 그 파일을 승격 20종목으로 채우자
    #   기대 2 vs 실제 22 로 깨졌다 — **기능 결함이 아니라 테스트가 실데이터를 새로 읽은 것**이다.
    #   그전까지 통과한 이유는 파일이 비어 있었기 때문일 뿐이다(초록이 안전이 아니었던 사례).
    monkeypatch.setattr(USB, "PROMOTE_PATH", str(tmp_path / "no_promote.json"))

    def _run(this_run, prev=None):
        if prev is not None:
            out.write_text(json.dumps(prev, ensure_ascii=False), encoding="utf-8")
        monkeypatch.setattr(
            "api.analyzers.stock_filter.run_filter_pipeline_with_ramp_up",
            lambda market_scope="all": this_run,
        )
        return USB.build()

    return _run


def test_kr_starvation_splices_prev_kr_and_keeps_fresh_us(snap):
    """실사고 재현: 이번 run US-only → 직전 KR 승계, 신선 US 유지."""
    fresh = _ago(24)  # 승계 상한(96h) 안 — 날짜 고정 금지
    prev = {
        "collected_at": fresh,
        "candidates": [_kr("000660"), _kr("005930"), _us("OLD")],
    }
    res = snap([_us("ACN"), _us("CTSH")], prev=prev)
    d = res["diagnostics"]

    assert d["kr_used_prev"] is True
    assert d["kr_starved"] is False
    assert d["kr_count"] == 2
    assert d["us_count"] == 2                      # 신선 US 만 — 직전 US(OLD) 는 미승계
    tickers = {c["ticker"] for c in res["candidates"]}
    assert {"ACN", "CTSH", "000660", "005930"} == tickers
    assert d["kr_prev_collected_at"] == fresh


def test_normal_run_untouched(snap):
    """양쪽 다 있으면 승계 로직 미개입."""
    prev = {"collected_at": _ago(24), "candidates": [_kr("999999")]}
    res = snap([_kr("000660"), _us("ACN")], prev=prev)
    d = res["diagnostics"]
    assert d["kr_used_prev"] is False
    assert d["kr_starved"] is False
    assert {c["ticker"] for c in res["candidates"]} == {"000660", "ACN"}


def test_stale_prev_not_spliced(snap):
    """상한(96h) 초과 직전분은 승계 금지 — 낡은 KR 후보 무한 연장 차단."""
    prev = {
        "collected_at": _ago(24 * 27),   # 수 주 전
        "candidates": [_kr("000660")],
    }
    res = snap([_us("ACN")], prev=prev)
    d = res["diagnostics"]
    assert d["kr_used_prev"] is False
    assert d["kr_starved"] is True
    assert d["kr_count"] == 0


def test_splice_chain_uses_origin_scan_time(snap):
    """직전이 이미 승계본이면 원 스캔 시각을 승계 — 무한 연쇄 방지."""
    prev = {
        "collected_at": _ago(4),                               # 승계가 일어난 시각(최근)
        "candidates": [_kr("000660")],
        "diagnostics": {"kr_used_prev": True,
                        "kr_prev_collected_at": _ago(24 * 27)},  # 원 스캔=수 주 전
    }
    res = snap([_us("ACN")], prev=prev)
    d = res["diagnostics"]
    assert d["kr_used_prev"] is False      # 원 스캔 기준으로 만료 → 승계 거부
    assert d["kr_starved"] is True


def test_total_zero_still_uses_full_prev(snap):
    """기존 전체-0 fallback 은 그대로 (회귀 없음)."""
    prev = {
        "collected_at": _ago(9),
        "candidates": [_kr("000660"), _us("ACN")],
    }
    res = snap([], prev=prev)
    d = res["diagnostics"]
    assert d["used_prev_snapshot"] is True
    assert d["kr_used_prev"] is False       # 전체 승계라 KR 별도 splice 불필요
    assert d["kr_count"] == 1 and d["us_count"] == 1


def test_no_prev_snapshot_marks_starved(snap):
    """직전 snapshot 자체가 없으면 결식으로 표시 (조용히 넘기지 않음)."""
    res = snap([_us("ACN")])
    assert res["diagnostics"]["kr_starved"] is True
    assert res["diagnostics"]["kr_used_prev"] is False
