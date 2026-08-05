# -*- coding: utf-8 -*-
"""급변일 뉴스 근거 확대 — 일일 리포트 (2026-08-05).

배경 정정: "원인 연결 레이어 부재"라는 진단은 틀렸다. headlines 인자는 처음부터
있었고 호출부도 실데이터를 넘긴다(api/main.py). 실제 갭은 ① 관련성 무관 앞 5건 절단
② 지수 급변일에도 동일 취급. 이 테스트는 그 좁은 갭만 고정한다.

계약: 급변일(|지수| ≥ 1.5%)에만 창을 넓히고 인용을 요구하되, 인과 단정은 요구하지
않는다(RULE 7 — 검증 안 된 인과 주장 금지). 평상일 동작은 불변.
"""
import inspect

from api.analyzers import gemini_analyst as ga


def _src():
    return inspect.getsource(ga.generate_daily_report)


def test_threshold_is_explicit_constant():
    assert ga.BIGMOVE_PCT == 1.5


def test_headlines_wiring_still_present():
    """회귀 방지 — 배선 자체가 사라지면 진단이 사실이 되어버린다."""
    params = inspect.signature(ga.generate_daily_report).parameters
    assert "headlines" in params
    assert "market_summary" in params


def test_bigmove_widens_window_and_requires_citation():
    src = _src()
    assert "headlines[:12]" in src          # 급변일 창 확대
    assert "headlines[:5]" in src           # 평상일 기존 동작 보존
    assert "abs(_idx_move) >= BIGMOVE_PCT" in src


def test_causation_assertion_is_forbidden_in_prompt():
    """RULE 7 — 인과 단정 금지 문구가 프롬프트에 남아 있어야 한다."""
    src = _src()
    assert "인과 단정 금지" in src
    assert "보도가 있었다" in src            # 허용 형태를 명시


def test_move_block_reaches_both_market_prompts():
    src = _src()
    assert src.count("{move_block}") == 2   # US · KR 프롬프트 양쪽


def test_missing_market_summary_is_inert():
    """market_summary 부재(구 호출부·테스트)면 급변 로직이 발동하지 않아야 한다."""
    src = _src()
    assert 'move_block = ""' in src
    assert "isinstance(market_summary, dict)" in src
