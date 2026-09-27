# -*- coding: utf-8 -*-
"""operator_ask 위임 질문 — 시장별 프레이밍 고정.

🚨 2026-08-08 실사고: TSLL(미국 레버리지 ETF) 질문이 "한국 상장사 TSLL(종목코드 TSLL)"
   로 생성되고 KIND·DART 를 1차 소스로 지정했다. 규칙 ④ "동명 해외 법인 혼동 금지 —
   한국 상장사만" 이 정답 방향을 **적극 차단**했다.
   위임 질문은 자체 데이터가 빈 종목에 쓰는 도구인데, 그 종목이 대개 미국 종목이다.
"""
from __future__ import annotations

import os
import runpy
import sys
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.intelligence import operator_ask as oa  # noqa: E402
from api.intelligence.operator_ask import _market_of, _move_pct, research_gaps  # noqa: E402


def _facts(ticker, name="", market=None, headline_count=0):
    secs = [{"label": "sentiment", "data": {"headline_count": headline_count}}]
    if market is not None:
        secs.append({"label": "리포트", "data": {"market": market}})
    return {"ticker": ticker, "name": name or ticker, "sections": secs}


@pytest.mark.parametrize("ticker,market,expect", [
    ("005930", "KOSPI", "KR"),
    ("094970", "KOSDAQ", "KR"),
    ("TSLL", None, "US"),
    ("AAPL", "NASDAQ", "US"),
    ("BRK.B", None, "US"),
    ("005930", None, "KR"),          # 시장 미상이면 6자리 숫자로 판별
])
def test_market_detection(ticker, market, expect):
    assert _market_of(_facts(ticker, market=market), ticker) == expect


def test_us_ticker_never_called_korean_listing():
    """🚨 미국 종목을 '한국 상장사 TSLL' 로 부르면 검색이 정답에서 멀어진다.

    규칙 ④ 의 "동명 **한국 상장사**와 혼동 금지" 는 정상 문구다 — 주어(질문 대상)만 본다.
    """
    gaps = research_gaps(_facts("TSLL"))
    assert gaps
    joined = "\n".join(g["query"] for g in gaps)
    assert "한국 상장사 TSLL" not in joined
    assert "미국 상장 종목 TSLL(티커 TSLL)" in joined


def test_us_rules_point_to_us_sources():
    joined = "\n".join(g["query"] for g in research_gaps(_facts("TSLL")))
    assert "SEC EDGAR" in joined
    assert "KIND" not in joined and "DART" not in joined
    # 정답 차단 규칙이 반대로 걸려 있어야 한다
    assert "동명 한국 상장사와 혼동 금지" in joined


def test_kr_framing_unchanged():
    """KR 경로는 회귀 없어야 한다 — 이 도구의 주 사용처다."""
    joined = "\n".join(g["query"] for g in research_gaps(_facts("005930", "삼성전자", "KOSPI")))
    assert "코스피 상장사 삼성전자(종목코드 005930)" in joined
    assert "국내 1차 소스" in joined
    assert "미국 1차 소스" not in joined


def test_kosdaq_segment_label():
    joined = "\n".join(g["query"] for g in research_gaps(_facts("094970", "제이엠티", "KOSDAQ")))
    assert "코스닥 상장사" in joined


def test_no_leftover_hardcoded_kr_rules():
    """질문 본문에 시장 무관 하드코딩이 남아 있으면 안 된다."""
    import inspect
    from api.intelligence import operator_ask as oa
    src = inspect.getsource(oa.research_gaps)
    assert "_PPLX_RULES" not in src, "시장별 rules 변수를 써야 한다"
    assert '"한국 상장사' not in src


def _quote(facts, label, move, as_of="", basis=""):
    facts["sections"].append({
        "label": label, "source": "fixture:quote", "as_of": as_of,
        "data": {"등락률": move, "기준": basis},
    })
    return facts


@pytest.mark.parametrize("label", [
    "실시간 시세 (KIS · 본인 이용)",
    "미국 실시간 시세 (KIS · 본인 이용) — 장중",
    "미국 시세 (KIS · 본인 이용) — 장 마감, 직전 거래일 종가",
    "미국 시세·일봉 (야후 실호출)",
    "종가 (T+1 · 실시간 아님)",
])
@pytest.mark.parametrize("move,expected", [("+6.25%", 6.25), ("-7.00%", -7.0), (0, 0.0)])
def test_move_pct_reads_quote_labels_and_zero(label, move, expected):
    assert _move_pct(_quote(_facts("AAPL"), label, move)) == expected


@pytest.mark.parametrize("invalid", [None, "", "unknown", "NaN", "inf", "-inf", True])
def test_invalid_move_falls_back_to_valid_quote(invalid):
    facts = _quote(_facts("005930"), "실시간 시세", invalid)
    _quote(facts, "종가 (T+1 · 실시간 아님)", "-6%")
    assert _move_pct(facts) == -6.0


def test_current_zero_does_not_fall_back_to_previous_surge():
    facts = _quote(_facts("005930"), "종가", "+12%")
    _quote(facts, "실시간 시세", 0)
    assert _move_pct(facts) == 0.0
    assert "catalyst" not in {g["key"] for g in research_gaps(facts)}


@pytest.mark.parametrize("dart", [None, {"건수": 0}, {
    "건수": 1, "공시": [{"date": "2026-09-25", "title": "한국 공시"}],
}])
def test_us_catalyst_uses_us_sources_even_with_dart_section(dart):
    facts = _quote(_facts("TSLL"), "미국 시세·일봉 (야후 실호출)", "+8.5%",
                   "2026-09-26T05:00:00+09:00", "미국장 마감 · 2026-09-25 (ET) 종가")
    if dart is not None:
        facts["sections"].append({"label": "DART 공시", "data": dart})
    catalyst = next(g for g in research_gaps(facts) if g["key"] == "catalyst")
    assert "+8.5%" in catalyst["query"]
    assert "SEC EDGAR" in catalyst["query"]
    assert "발행사" in catalyst["query"]
    assert "KIND" not in catalyst["query"]
    assert "DART" not in catalyst["query"]
    assert "한국 공시" not in catalyst["query"]


@pytest.mark.parametrize("label,basis,stamp", [
    ("종가 (T+1 · 실시간 아님)", "", "2026-09-25"),
    ("실시간 시세 (KIS · 본인 이용)", "", ""),
    ("미국 실시간 시세 (KIS · 본인 이용) — 장중", "미국장 개폐 판정 불가", ""),
    ("미국 시세·일봉 (야후 실호출)", "미국장 마감 · 2026-09-25 (ET) 종가",
     "2026-09-26T05:00:00+09:00"),
    ("미국 시세·일봉 (야후 실호출)", "미국장 개장 중 · 장중 체결가 (2026-09-25 ET 세션)",
     "2026-09-26T01:00:00+09:00"),
])
def test_catalyst_preserves_quote_basis_without_inventing_today(monkeypatch, label, basis, stamp):
    monkeypatch.setattr(oa, "_now", lambda: datetime(2026, 9, 27, tzinfo=timezone.utc))
    ticker = "AAPL" if label.startswith("미국") else "005930"
    facts = _quote(_facts(ticker), label, "-8%", stamp, basis)
    catalyst = next(g for g in research_gaps(facts) if g["key"] == "catalyst")
    assert catalyst["recency"] == ""
    query = catalyst["query"]
    assert "2026년 09월 27일" not in query
    assert "오늘" not in query
    assert "장중 -8.0%" not in query
    assert "fixture:quote" in query
    assert (stamp or "기준일·시각 미확인") in query
    assert (basis or (label if label.startswith("종가") else "장 개폐·가격 기준 미확인")) in query


def test_catalyst_uses_timestamp_from_selected_quote():
    facts = _quote(_facts("AAPL"), "미국 시세·일봉", "+12%", "2026-09-24")
    _quote(facts, "미국 실시간 시세", "-6%", "2026-09-25T15:00:00-04:00",
           "미국장 개장 중 · 장중 체결가 (2026-09-25 ET 세션)")
    query = next(g["query"] for g in research_gaps(facts) if g["key"] == "catalyst")
    assert "-6.0%" in query
    assert "2026-09-25T15:00:00-04:00" in query
    assert "2026-09-24" not in query


@pytest.mark.parametrize("dart", [None, {"건수": 0}, {
    "건수": 1, "공시": [{"date": "2026-09-25", "title": "공급계약"}],
}])
def test_kr_catalyst_keeps_disclosures_without_today_claim(dart):
    facts = _quote(_facts("005930"), "종가 (T+1 · 실시간 아님)", "+6%", "2026-09-25")
    if dart is not None:
        facts["sections"].append({"label": "DART 공시", "data": dart})
    query = next(g["query"] for g in research_gaps(facts) if g["key"] == "catalyst")
    assert "KIND" in query and "DART" in query
    assert "오늘" not in query
    if dart and dart.get("공시"):
        assert "공급계약" in query


@pytest.fixture
def collected_bundle(monkeypatch):
    facts = _facts("AAPL")
    collect = Mock(return_value=facts)
    monkeypatch.setattr(oa.ticker_facts, "collect", collect)
    monkeypatch.setattr(oa.ticker_facts, "render_text", lambda _: "fixture facts")
    return facts, collect


@pytest.mark.parametrize("facts_only", [False, True])
@pytest.mark.parametrize("no_cache", [False, True])
def test_ask_flags_and_retired_chain_contract(collected_bundle, facts_only, no_cache):
    facts, collect = collected_bundle
    out = oa.ask("AAPL", "  최근 변화  ", facts_only=facts_only, no_cache=no_cache)
    if no_cache:
        collect.assert_called_once_with("AAPL", no_cache=True)
    else:
        collect.assert_called_once_with("AAPL")
    assert out["facts"] is facts
    assert out["_meta"] == {
        "contract": "operator-facts-v2", "llm_calls": 0,
        "final_reasoner": "codex_session", "legacy_chain_retired": True,
    }
    assert ("research_questions" in out) is not facts_only
    assert ("question" in out) is not facts_only
    if not facts_only:
        assert out["question"] == "최근 변화"
        assert out["research_questions"]


def test_default_collect_stays_compatible_with_single_argument_lambda(monkeypatch):
    monkeypatch.setattr(oa.ticker_facts, "collect", lambda query: _facts(query))
    monkeypatch.setattr(oa.ticker_facts, "render_text", lambda _: "facts")
    assert oa.ask("AAPL")["facts"]["ticker"] == "AAPL"


@pytest.mark.parametrize("ticker,question,facts_only", [
    ("", "급등 이유", False), ("AAPL", "   ", False), ("AAPL", "급등 이유", True),
])
def test_ask_does_not_generate_questions_when_inapplicable(monkeypatch, ticker, question, facts_only):
    monkeypatch.setattr(oa.ticker_facts, "collect", lambda _: _facts(ticker))
    monkeypatch.setattr(oa.ticker_facts, "render_text", lambda _: "facts")
    gaps = Mock(side_effect=AssertionError("research_gaps must not run"))
    monkeypatch.setattr(oa, "research_gaps", gaps)
    out = oa.ask("input", question, facts_only=facts_only)
    assert "research_questions" not in out
    assert "question" not in out
    gaps.assert_not_called()


@pytest.mark.parametrize("mode", [[], ["--facts-only"], ["--questions"]])
@pytest.mark.parametrize("no_cache", [False, True])
def test_cli_forwards_cache_flag_and_respects_mode(monkeypatch, capsys, collected_bundle, mode, no_cache):
    _, collect = collected_bundle
    monkeypatch.setitem(sys.modules, "ticker_facts", oa.ticker_facts)
    monkeypatch.setattr(sys, "argv", [oa.__file__, "AAPL", "--q", "최근 변화"] + mode
                        + (["--no-cache"] if no_cache else []))
    if mode == ["--questions"]:
        with pytest.raises(SystemExit) as exc:
            runpy.run_path(oa.__file__, run_name="__main__")
        assert exc.value.code == 0
    else:
        runpy.run_path(oa.__file__, run_name="__main__")
    if no_cache:
        collect.assert_called_once_with("AAPL", no_cache=True)
    else:
        collect.assert_called_once_with("AAPL")
    output = capsys.readouterr().out
    if mode == ["--facts-only"]:
        assert "fixture facts" in output
        assert "최근 뉴스·이슈" not in output
    else:
        assert "최근 뉴스·이슈" in output


def test_cli_rejects_conflicting_output_modes(monkeypatch, capsys, collected_bundle):
    _, collect = collected_bundle
    monkeypatch.setitem(sys.modules, "ticker_facts", oa.ticker_facts)
    monkeypatch.setattr(sys, "argv", [oa.__file__, "AAPL", "--facts-only", "--questions"])
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(oa.__file__, run_name="__main__")
    assert exc.value.code == 2
    assert "--facts-only" in capsys.readouterr().err
    collect.assert_not_called()
