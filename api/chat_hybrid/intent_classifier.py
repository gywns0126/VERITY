"""
VERITY Chat Hybrid — 의도 분류기

사용자 질문을 Gemini Flash 로 분석해서 다음을 결정:
  1. intent_type: portfolio_only / external_only / hybrid / greeting
  2. related_tickers: 질문에 언급되거나 암시된 티커
  3. complexity: simple (sonar) / complex (sonar-pro) — 외부 모델 선택 기준
  4. needs_perplexity: 뉴스/해설 필요 여부
  5. needs_gemini_grounding: 최신 수치/공식 정보 여부
  6. cache_key: 정규화된 쿼리 hash

외부 호출 0회 분기의 핵심 게이트 — 정확도가 전체 비용과 품질을 좌우.

환경변수:
  GEMINI_API_KEY       — 필수
  CHAT_HYBRID_CLASSIFIER_MODEL — 기본 gemini-2.5-flash-lite (빠르고 저렴)
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


_CLASSIFIER_MODEL = os.environ.get(
    "CHAT_HYBRID_CLASSIFIER_MODEL", "gemini-2.5-flash-lite"
).strip()
_TIMEOUT_SEC = float(os.environ.get("CHAT_HYBRID_CLASSIFIER_TIMEOUT", "3"))


_SYSTEM_PROMPT = """너는 VERITY 금융 챗봇의 의도 분류기다. 사용자 질문을 분석해서 JSON으로만 답한다.

분류 기준:
- portfolio_only: 사용자의 보유/관심 종목, 내부 점수, 자체 알림에만 관련
  예: "내 포지션 어때?", "삼성전자 안심점수?", "위험 종목 있어?"
- external_only: 외부 뉴스·시세·매크로 등 실시간 정보가 주
  예: "엔비디아 최근 뉴스", "FOMC 언제야?", "오늘 VIX"
- hybrid: 외부 정보 + 포트폴리오 영향 둘 다 필요
  예: "SK하이닉스 요즘 어때?", "내 종목 중 FOMC 영향 받는 거?"
- greeting: 인사, 잡담, 시스템 질문
  예: "안녕", "뭐 할 수 있어?"

필드 설명:
- related_tickers: 질문에서 언급되거나 암시되는 티커 (한국 6자리 / 미국 알파벳). 없으면 []
- complexity: "simple" 또는 "complex"
  * simple: 단순 뉴스·팩트 (예: "엔비디아 오늘 주가")
  * complex: 다단계 추론·비교·원인 분석 (예: "왜 반도체 섹터가 하락했나?")
- needs_perplexity: 뉴스·해설이 필요하면 true
- needs_gemini_grounding: 최신 수치·공식 정보가 필요하면 true (FOMC 일정, 지수 값 등)
"""


_JSON_SCHEMA_HINT = """
JSON 형식 (필수 필드):
{
  "intent_type": "portfolio_only" | "external_only" | "hybrid" | "greeting",
  "related_tickers": ["005930", "NVDA"],
  "complexity": "simple" | "complex",
  "needs_perplexity": true | false,
  "needs_gemini_grounding": true | false,
  "reason": "분류 근거 한 줄"
}
"""


_FALLBACK = {
    "intent_type": "hybrid",  # 안전하게 외부 호출 — 품질 우선
    "related_tickers": [],
    "complexity": "simple",
    "needs_perplexity": True,
    "needs_gemini_grounding": False,  # 비용 절감
    "reason": "classifier fallback",
    "_source": "fallback",
}


def _cache_key(query: str) -> str:
    """정규화된 쿼리 해시 — 3단 캐시의 종목뉴스 / perplexity 캐시 키로 사용."""
    norm = re.sub(r"\s+", " ", query).strip().lower()
    norm = re.sub(r"[?!.,]", "", norm)
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]


def _parse_json(text: str) -> Optional[Dict[str, Any]]:
    """Gemini 응답에서 JSON 추출 — ```json 블록, 중괄호 첫 매치 순으로."""
    if not text:
        return None
    # fenced
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    # raw json
    m = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return None


def _validate(obj: Dict[str, Any]) -> Dict[str, Any]:
    """최소 필드 검증 + 기본값 보정."""
    valid_intents = ("portfolio_only", "external_only", "hybrid", "greeting")
    intent = obj.get("intent_type", "hybrid")
    if intent not in valid_intents:
        intent = "hybrid"

    tickers = obj.get("related_tickers", [])
    if not isinstance(tickers, list):
        tickers = []
    tickers = [str(t).strip().upper() for t in tickers if t][:10]

    complexity = obj.get("complexity", "simple")
    if complexity not in ("simple", "complex"):
        complexity = "simple"

    needs_p = bool(obj.get("needs_perplexity", False))
    needs_g = bool(obj.get("needs_gemini_grounding", False))

    # portfolio_only / greeting 은 외부 호출 강제 차단 — 모델이 실수해도 비용 방어.
    if intent in ("portfolio_only", "greeting"):
        needs_p = False
        needs_g = False

    return {
        "intent_type": intent,
        "related_tickers": tickers,
        "complexity": complexity,
        "needs_perplexity": needs_p,
        "needs_gemini_grounding": needs_g,
        "reason": str(obj.get("reason", ""))[:200],
    }


def classify(query: str, recent_turns: Optional[List[str]] = None) -> Dict[str, Any]:
    """사용자 질문 → 라우팅 결정.

    실패 시 fallback (intent=hybrid, needs_perplexity=True).
    항상 dict 반환 — 호출자가 raise 대응 불필요.
    """
    query = (query or "").strip()
    if not query:
        return {**_FALLBACK, "cache_key": _cache_key(""), "_source": "empty_query"}

    result = {"cache_key": _cache_key(query)}

    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        logger.warning("GEMINI_API_KEY 미설정 → classifier fallback")
        return {**_FALLBACK, **result}

    prompt_parts = [_SYSTEM_PROMPT, _JSON_SCHEMA_HINT, f"질문: {query}"]
    if recent_turns:
        prompt_parts.append("최근 대화: " + " | ".join(str(t)[:200] for t in recent_turns[-3:]))
    prompt = "\n\n".join(prompt_parts)

    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        resp = client.models.generate_content(
            model=_CLASSIFIER_MODEL,
            contents=prompt,
            config={
                "temperature": 0.0,
                "max_output_tokens": 300,
                "response_mime_type": "application/json",
            },
        )
        text = (resp.text or "").strip()
        parsed = _parse_json(text)
        if not parsed:
            logger.warning("classifier JSON 파싱 실패: %s", text[:200])
            return {**_FALLBACK, **result, "_source": "parse_fail"}

        validated = _validate(parsed)
        return {**validated, **result, "_source": _CLASSIFIER_MODEL, "_raw": text[:500]}

    except Exception as e:
        logger.warning("classifier 호출 실패: %s", e)
        return {**_FALLBACK, **result, "_source": f"error:{type(e).__name__}"}


def quick_intent_from_rules(query: str) -> Optional[str]:
    """규칙 기반 초고속 분기 — classifier 호출 전 확실한 케이스 캐치.

    매우 보수적으로만 사용. 확실하지 않으면 None 반환 → classifier 에 맡김.
    """
    q = query.strip().lower()
    if not q:
        return None
    if q in ("안녕", "hi", "hello", "반가워", "ㅎㅇ"):
        return "greeting"
    if len(q) <= 3 and not any(c.isalnum() for c in q):
        return "greeting"
    return None
