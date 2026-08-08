# -*- coding: utf-8 -*-
"""operator_ask 위임 질문 — 시장별 프레이밍 고정.

🚨 2026-08-08 실사고: TSLL(미국 레버리지 ETF) 질문이 "한국 상장사 TSLL(종목코드 TSLL)"
   로 생성되고 KIND·DART 를 1차 소스로 지정했다. 규칙 ④ "동명 해외 법인 혼동 금지 —
   한국 상장사만" 이 정답 방향을 **적극 차단**했다.
   위임 질문은 자체 데이터가 빈 종목에 쓰는 도구인데, 그 종목이 대개 미국 종목이다.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.intelligence.operator_ask import _market_of, research_gaps  # noqa: E402


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
