"""
Gemini 대화 엔진 — 텔레그램 봇 + 인앱 채팅 공용.
portfolio.json 컨텍스트를 system prompt에 주입하여 데이터 기반 답변.
"""
import json
import logging
import os
from typing import Any, Dict, Optional

from google import genai
from api.config import GEMINI_API_KEY, GEMINI_MODEL, DATA_DIR

logger = logging.getLogger(__name__)

_PORTFOLIO_PATH = os.path.join(DATA_DIR, "portfolio.json")

SYSTEM_PROMPT = """너는 VERITY — AI 자산 보안 비서다.
사용자의 투자 관련 질문에 한국어로 간결하게 답한다.

핵심 원칙:
- 데이터 기반: 아래 제공된 최신 포트폴리오 데이터를 근거로 답변
- 솔직함: 확실하지 않으면 "데이터가 부족합니다"라고 답변
- 경고 우선: 리스크가 있으면 반드시 먼저 언급
- 간결함: 3~5문장 이내. 필요하면 bullet point 사용
- 투자 조언 면책: 최종 투자 결정은 본인 책임임을 상기

절대 하지 말 것:
- 특정 가격/날짜 예측 ("내일 5% 오릅니다" 식)
- 존재하지 않는 데이터 날조
- 매수/매도를 단정적으로 지시
"""


def _load_portfolio_context() -> str:
    """portfolio.json에서 핵심 컨텍스트만 추출 (토큰 절약)."""
    try:
        with open(_PORTFOLIO_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return "포트폴리오 데이터 없음."

    parts = []

    updated = data.get("updated_at", "?")
    parts.append(f"데이터 갱신: {updated}")

    macro = data.get("macro", {})
    mood = macro.get("market_mood", {})
    parts.append(f"시장무드: {mood.get('score', '?')}점 ({mood.get('label', '?')})")

    vix = macro.get("vix", {}).get("value")
    if vix:
        parts.append(f"VIX: {vix}")
    usd = macro.get("usd_krw", {}).get("value")
    if usd:
        parts.append(f"USD/KRW: {usd}")

    cf = macro.get("capital_flow", {})
    if cf.get("interpretation"):
        parts.append(f"자금흐름: {cf['interpretation']}")

    recs = data.get("recommendations", [])
    if recs:
        top5 = recs[:5]
        rec_lines = []
        for r in top5:
            name = r.get("name", "?")
            rec_type = r.get("recommendation", "?")
            brain = r.get("brain_score", "?")
            price = r.get("price", "?")
            rec_lines.append(f"  {name}: {rec_type} (브레인 {brain}, 현재가 {price})")
        parts.append("추천 TOP5:\n" + "\n".join(rec_lines))

    alerts = data.get("alerts", [])
    if alerts:
        alert_texts = [a.get("text", a.get("message", "?")) for a in alerts[:5]]
        parts.append("최근 알림:\n  " + "\n  ".join(alert_texts))

    briefing = data.get("briefing", {})
    if briefing.get("headline"):
        parts.append(f"브리핑: {briefing['headline']}")

    brain = data.get("verity_brain", {})
    mb = brain.get("market_brain", {})
    if mb.get("avg_brain_score"):
        parts.append(f"시장 평균 브레인: {mb['avg_brain_score']}점")

    return "\n".join(parts)


def _build_stock_context(question: str, portfolio_data: Optional[dict] = None) -> str:
    """질문에 언급된 종목이 있으면 해당 종목 데이터를 추가."""
    if portfolio_data is None:
        try:
            with open(_PORTFOLIO_PATH, "r", encoding="utf-8") as f:
                portfolio_data = json.load(f)
        except Exception:
            return ""

    recs = portfolio_data.get("recommendations", [])
    holdings = portfolio_data.get("holdings", [])
    all_stocks = recs + holdings

    matched = []
    for s in all_stocks:
        name = s.get("name", "")
        ticker = s.get("ticker", "")
        if name and name in question:
            matched.append(s)
        elif ticker and ticker in question:
            matched.append(s)

    if not matched:
        return ""

    parts = []
    for s in matched[:3]:
        info = [f"\n종목: {s.get('name', '?')} ({s.get('ticker', '?')})"]
        if s.get("price"):
            info.append(f"현재가: {s['price']}")
        if s.get("recommendation"):
            info.append(f"추천: {s['recommendation']}")
        if s.get("brain_score"):
            info.append(f"브레인: {s['brain_score']}")
        if s.get("ai_verdict"):
            info.append(f"AI의견: {s['ai_verdict']}")
        sent = s.get("social_sentiment") or s.get("sentiment") or {}
        if sent.get("score"):
            info.append(f"감성: {sent['score']}점")
        parts.append(" | ".join(info))

    return "\n".join(parts)


def ask(
    question: str,
    context: Optional[Dict[str, Any]] = None,
) -> str:
    """
    사용자 질문 → Gemini 답변.

    Args:
        question: 사용자 질문 텍스트
        context: 추가 컨텍스트 (portfolio dict 등), 없으면 파일에서 로드

    Returns:
        답변 문자열
    """
    if not GEMINI_API_KEY:
        return "Gemini API 키가 설정되지 않았습니다."

    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
    except Exception as e:
        logger.error(f"Gemini 초기화 실패: {e}")
        return "AI 비서 연결에 실패했습니다."

    portfolio_ctx = _load_portfolio_context()
    stock_ctx = _build_stock_context(question, context)

    full_system = f"{SYSTEM_PROMPT}\n\n─── 최신 데이터 ───\n{portfolio_ctx}"
    if stock_ctx:
        full_system += f"\n\n─── 관련 종목 ───\n{stock_ctx}"

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=question,
            config={
                "system_instruction": full_system,
                "temperature": 0.3,
                "max_output_tokens": 500,
            },
        )
        return (response.text or "").strip() or "답변을 생성하지 못했습니다."
    except Exception as e:
        logger.error(f"Gemini 응답 오류: {e}")
        err = str(e)
        if "429" in err or "RESOURCE_EXHAUSTED" in err or "quota" in err.lower():
            return (
                "Gemini 할당량 초과입니다. Google AI Studio 결제/쿼터를 확인하거나 "
                "환경변수 GEMINI_MODEL을 gemini-2.5-flash-lite 등으로 바꿔 보세요."
            )
        return f"AI 비서 응답 오류: {e}"
