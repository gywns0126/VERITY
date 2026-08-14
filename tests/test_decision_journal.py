# -*- coding: utf-8 -*-
"""실험 노트(판단 저장) 계약 테스트.

🚨 이 모듈의 존재 이유는 **나중에 채점할 수 있게** 하는 것이다. 그래서 지키는 선이
   "기록이 남는다" 가 아니라 "채점 가능한 형태로 남는다" 다. 아래가 그 계약이다.
     · verdict 폐쇄 집합 — 산문이면 채점 불가 → N 이 안 쌓인다
     · 회전 수집 파일 기준가 거부 — 잘못된 기준가는 채점을 조용히 틀리게 만든다
     · 지문이 입력 변화에 반응 — 갱신된 데이터로 소급 평가하면 결과가 오염된다
     · 기록 실패는 예외 — 안 남은 판단은 없는 판단이다(#46 계열)
"""
from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.intelligence import decision_journal as dj  # noqa: E402


def _facts(close=71500, source="kr_close_latest.json", as_of="2026-08-08", ticker="005930"):
    return {
        "ticker": ticker, "name": "삼성전자", "missing": [],
        "sections": [
            {"label": "종가 (T+1 · 실시간 아님)", "source": source,
             "as_of": as_of, "data": {"close": close}},
        ],
    }


@pytest.fixture
def path(tmp_path):
    return str(tmp_path / "verdicts.jsonl")


# ── verdict 폐쇄 집합 ────────────────────────────────────────────────────────

@pytest.mark.parametrize("v", ["관심", "보류", "회피"])
def test_verdict_closed_set_accepts(v, path):
    rec = dj.record(_facts(), v, "medium", ["fscore8"], "근거", path=path)
    assert rec["verdict"] == v


@pytest.mark.parametrize("v", ["매수", "강한관심", "buy", "", "관심 ", None])
def test_verdict_outside_closed_set_rejected(v, path):
    with pytest.raises(dj.JournalError, match="폐쇄 집합"):
        dj.record(_facts(), v, "medium", ["fscore8"], "근거", path=path)
    assert not os.path.exists(path), "거부된 판단이 파일에 남으면 안 된다"


@pytest.mark.parametrize("c", ["보통", "MEDIUM", "", None])
def test_confidence_validated(c, path):
    with pytest.raises(dj.JournalError):
        dj.record(_facts(), "관심", c, ["fscore8"], "근거", path=path)


def test_ticker_required(path):
    f = _facts()
    f["ticker"] = None
    with pytest.raises(dj.JournalError, match="ticker"):
        dj.record(f, "관심", "medium", [], "근거", path=path)


# ── 기준가 규율 ──────────────────────────────────────────────────────────────

def test_rotating_collector_price_source_rejected(path):
    """🚨 stock_flow_5d 의 close 는 가격이 아니다 — 수급만 유효하다."""
    f = _facts(source="stock_flow_5d.json")
    with pytest.raises(dj.JournalError, match="회전 수집"):
        dj.record(f, "관심", "medium", [], "근거", path=path)


def test_ref_price_records_source_and_key(path):
    rec = dj.record(_facts(), "관심", "medium", [], "근거", path=path)
    assert rec["ref_price"] == 71500
    assert rec["ref_price_source"] == "kr_close_latest.json"
    assert rec["ref_price_key"] == "close"


def test_missing_price_is_null_not_guessed(path):
    """값을 억지로 채우지 않는다 — 없는 정밀도를 있는 척하면 채점이 조용히 틀린다."""
    f = _facts()
    f["sections"][0]["data"] = {"volume": 1234}
    rec = dj.record(f, "보류", "low", [], "근거", path=path)
    assert rec["ref_price"] is None
    assert rec["ref_price_key"] is None
    assert rec["ref_price_source"] == "kr_close_latest.json"


# ── 지문 (소급 평가 오염 방지) ───────────────────────────────────────────────

def test_fingerprint_changes_when_data_changes():
    a = dj.facts_fingerprint(_facts(close=71500))
    b = dj.facts_fingerprint(_facts(close=71600))
    assert a != b


def test_fingerprint_changes_when_as_of_changes():
    a = dj.facts_fingerprint(_facts(as_of="2026-08-08"))
    b = dj.facts_fingerprint(_facts(as_of="2026-08-09"))
    assert a != b


def test_fingerprint_stable_for_same_input():
    assert dj.facts_fingerprint(_facts()) == dj.facts_fingerprint(_facts())


# ── 조용한 실패 금지 ─────────────────────────────────────────────────────────

def test_write_failure_raises(tmp_path):
    """기록 실패가 조용히 넘어가면 '기록했다고 믿는 안 된 판단'이 생긴다."""
    blocker = tmp_path / "blocked"
    blocker.write_text("파일이라 하위 경로를 만들 수 없다", encoding="utf-8")
    target = str(blocker / "decisions" / "verdicts.jsonl")
    with pytest.raises(dj.JournalError, match="기록 실패"):
        dj.record(_facts(), "관심", "medium", [], "근거", path=target)


# ── 관측 규율 4종 (data/observations 계보) ──────────────────────────────────

def test_observation_discipline_fields(path):
    rec = dj.record(_facts(), "회피", "high", ["offering_priced"], "근거", path=path)
    assert rec["shadow"] is True
    assert rec["brain_input"] is False
    assert "N<252" in rec["caveat"]
    assert rec["horizon_days"] == list(dj.HORIZON_DAYS)
    assert rec["scored"] is None
    assert rec["ts_kst"].endswith("+09:00"), "tz-aware KST 여야 한다"


def test_brain_verdict_recorded_for_paired_comparison(path):
    """산식 baseline 이 같이 남아야 짝지은 비교가 된다."""
    rec = dj.record(_facts(), "관심", "medium", [], "근거",
                    brain_verdict="B", path=path)
    assert rec["brain_verdict"] == "B"


# ── 되읽기 ───────────────────────────────────────────────────────────────────

def test_read_recent_filters_by_ticker_and_sorts_desc(path):
    dj.record(_facts(ticker="005930"), "관심", "medium", [], "1번", path=path)
    dj.record(_facts(ticker="000660"), "회피", "low", [], "다른 종목", path=path)
    dj.record(_facts(ticker="005930"), "보류", "low", [], "2번", path=path)

    rows = dj.read_recent("005930", path=path)
    assert len(rows) == 2
    assert all(r["ticker"] == "005930" for r in rows)
    assert rows[0]["ts_kst"] >= rows[1]["ts_kst"]


def test_read_recent_missing_file_returns_empty(tmp_path):
    assert dj.read_recent("005930", path=str(tmp_path / "none.jsonl")) == []


def test_read_recent_survives_corrupt_line(path):
    dj.record(_facts(), "관심", "medium", [], "정상", path=path)
    with open(path, "a", encoding="utf-8") as f:
        f.write("{손상된 행\n")
    rows = dj.read_recent("005930", path=path)
    assert len(rows) == 1, "손상 행 1개가 전체 조회를 막으면 안 된다"


def test_appends_do_not_overwrite(path):
    dj.record(_facts(), "관심", "medium", [], "1", path=path)
    dj.record(_facts(), "보류", "low", [], "2", path=path)
    with open(path, encoding="utf-8") as f:
        lines = [json.loads(x) for x in f if x.strip()]
    assert len(lines) == 2


# ── due 큐 (배치 판단 대상 선정) ────────────────────────────────────────────

def _rec_file(tmp_path, tickers):
    import json as _j
    p = tmp_path / "recs.json"
    p.write_text(_j.dumps([{"ticker": t, "name": t, "market": "KOSPI"} for t in tickers]),
                 encoding="utf-8")
    return str(p)


def test_due_includes_new_tickers(tmp_path, path):
    rec = _rec_file(tmp_path, ["000270", "005930"])
    due = dj.due_candidates(path=path, rec_path=rec)
    assert {d["ticker"] for d in due} == {"000270", "005930"}
    assert all(d["last_ts"] is None for d in due)


def test_due_excludes_recently_judged(tmp_path, path):
    """🚨 매일 찍으면 forward 창이 겹쳐 N 이 안 는다 — 20거래일 안은 제외."""
    dj.record(_facts(ticker="005930"), "관심", "medium", [], "최근 판단", path=path)
    rec = _rec_file(tmp_path, ["000270", "005930"])
    due = dj.due_candidates(path=path, rec_path=rec)
    assert {d["ticker"] for d in due} == {"000270"}


def test_due_after_boundary():
    """경계 = REJUDGE_TRADING_DAYS 거래일. 그 전은 제외, 지나면 포함."""
    from datetime import timedelta
    now = dj.now_kst()
    span_days = dj.REJUDGE_TRADING_DAYS / 5 * 7
    assert dj._due_after("") is True, "기록 없으면 항상 due"
    assert dj._due_after((now - timedelta(days=span_days - 2)).isoformat()) is False
    assert dj._due_after((now - timedelta(days=span_days + 2)).isoformat()) is True


def test_due_survives_missing_or_broken_recs(tmp_path, path):
    assert dj.due_candidates(path=path, rec_path=str(tmp_path / "none.json")) == []
    bad = tmp_path / "bad.json"
    bad.write_text("{깨진", encoding="utf-8")
    assert dj.due_candidates(path=path, rec_path=str(bad)) == []


def test_rejudge_interval_matches_prereg_horizon():
    """🚨 20 은 사전등록 시계에서 따온 값이지 새로 고른 숫자가 아니다."""
    assert dj.REJUDGE_TRADING_DAYS in dj.HORIZON_DAYS
