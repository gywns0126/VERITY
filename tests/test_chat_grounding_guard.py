"""
챗 환각 가드 회귀 테스트 (2026-06-03 삼성전자 65,000원 환각 사고).

근본원인: 유니버스 밖 종목(삼성전자) 질의 → brain 컨텍스트 비고 + portfolio_only
분류로 외부 grounding 하드 차단 → 합성 LLM 이 학습 기억(옛 가격)으로 환각.

정공법 가드 2축:
  1) response_synthesizer: 시세 미확인 종목에 '수치 생성 금지' 하드 마커 + system prompt 규칙
  2) orchestrator: ungrounded 티커 감지 시 web grounding 강제 (여기선 1축만 단위검증)
"""
from api.chat_hybrid.response_synthesizer import _build_context_message, _SYSTEM_PROMPT


def test_system_prompt_has_hard_numeric_guard():
    # 모든 시장 수치는 컨텍스트 출처가 있을 때만 — 학습 기억 가격 금지
    assert "수치 grounding" in _SYSTEM_PROMPT
    assert "실시간 시세는 확인되지 않음" in _SYSTEM_PROMPT
    assert "학습" in _SYSTEM_PROMPT  # 학습 시점 가격 신뢰 불가 경고


def test_ungrounded_ticker_emits_no_price_marker():
    # 유니버스 밖 + grounding 전무 → '시세 미확인 — 수치 생성 금지' 블록
    msg = _build_context_message(
        query="삼성전자 어때?",
        brain_ctx={"ok": False},
        ungrounded_tickers=["005930", "삼성전자"],
    )
    assert "시세 미확인" in msg
    assert "005930" in msg
    assert "추정하거나 학습 기억으로 생성하지 말" in msg


def test_grounded_price_suppresses_marker():
    # grounding 이 실제 가격을 가져오면 경고 억제 + 실가격이 컨텍스트에 주입
    grounding = {
        "ok": True,
        "text": "삼성전자(005930) 현재가 365,000원, 전일 종가 349,000원",
        "citations": [],
    }
    msg = _build_context_message(
        query="삼성전자 어때?",
        brain_ctx={"ok": False},
        grounding_result=grounding,
        ungrounded_tickers=["005930"],
    )
    assert "시세 미확인" not in msg
    assert "365,000" in msg


def test_no_ungrounded_no_marker():
    # ungrounded 없음 (유니버스 내 종목 등) → 경고 블록 미노출
    msg = _build_context_message(
        query="내 포지션 어때?",
        brain_ctx={"ok": True, "text": "보유 종목 요약..."},
        ungrounded_tickers=[],
    )
    assert "시세 미확인" not in msg
