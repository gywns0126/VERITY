"""
VERITY Chat Hybrid — 최종 응답 합성기 (Claude Sonnet 스트리밍)

Brain 컨텍스트 + Perplexity + Gemini Grounding 결과를 받아 Claude 에 전달,
한국어 금융 답변을 스트리밍으로 생성한다.

정책:
  1. 포트폴리오 최우선 — Brain 컨텍스트는 항상 system prompt 에 주입
  2. 불일치 시 명시 — Brain 판단과 외부 정보가 다르면 "Brain: X / 외부: Y / 원인: Z"
  3. 인용 필수 — 외부 정보 인용 시 출처 표시
  4. 답변 길이 제한 — 3-5문장 + 필요시 불릿. 장황함 금지.
  5. 사실 없으면 추측 금지 — "관련 정보 없음" 명시

스트리밍:
  anthropic.messages.stream() 사용. orchestrator 가 NDJSON 으로 전달.

환경변수:
  ANTHROPIC_API_KEY    — 필수
  CHAT_HYBRID_SYNTH_MODEL — 기본 CLAUDE_MODEL_DEFAULT (sonnet)
  CHAT_HYBRID_SYNTH_MAX_TOKENS — 기본 800
"""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Dict, Iterator, List, Optional

logger = logging.getLogger(__name__)


def _default_model() -> str:
    from api.config import CLAUDE_MODEL_DEFAULT
    return os.environ.get("CHAT_HYBRID_SYNTH_MODEL", CLAUDE_MODEL_DEFAULT).strip()


_MAX_TOKENS = int(os.environ.get("CHAT_HYBRID_SYNTH_MAX_TOKENS", "800"))
_TEMPERATURE = float(os.environ.get("CHAT_HYBRID_SYNTH_TEMPERATURE", "0.3"))
# 호출당 근사 비용 (sonnet 4.6 기준 보수적 추정)
_EST_COST_PER_CALL = 0.012


_SYSTEM_PROMPT = """너는 VERITY — 한국 개인투자자를 위한 금융 분석 어시스턴트다.

[핵심 원칙]
1. 포트폴리오 최우선: [Brain 컨텍스트] 에 담긴 사용자 보유·관심 종목 데이터를 답변의 기준으로 삼는다.
2. 외부 정보 교차검증: [Perplexity] 와 [Gemini Grounding] 결과는 보조 자료. 둘이 일치하면 신뢰도↑, 충돌하면 둘 다 언급.
3. Brain vs 외부 충돌 시: 반드시 "Brain 판단: X / 외부 보도: Y / 불일치 원인: Z" 형식으로 명시.
4. 인용: 외부 정보를 쓰면 핵심 출처 1-2개를 마크다운 링크로 표기.
5. 추측 금지: 제공된 컨텍스트에 없는 사실을 만들어내지 말 것. 없으면 "제공된 데이터에서 확인 불가" 라고 답한다.
6. 한국어로, 3-5문장 핵심 요약 + 필요 시 불릿 2-4줄. 장황한 서론·결론 금지.

[답변 스타일]
- 숫자·티커·날짜 같은 구체 사실 우선 제시.
- "제 생각엔" / "아마도" 류 추측 표현 금지.
- 종목 언급 시 Brain 점수·등급·판정을 함께 제시 (있을 경우).
- 외부 정보가 Brain 과 충돌하면 사용자가 스스로 판단할 수 있게 양쪽 근거 모두 제시.

[답변 형식 예시]
- 단순 팩트 질문: 2-3문장 압축.
- 종목 분석 요청: Brain 요약 → 외부 뉴스 교차 → 판단 (3-5문장).
- 인사/잡담: 1-2문장 + 기능 안내."""


_lock = threading.Lock()
_call_count = 0
_total_cost = 0.0


def _build_context_message(
    query: str,
    brain_ctx: Optional[Dict[str, Any]] = None,
    perplexity_result: Optional[Dict[str, Any]] = None,
    grounding_result: Optional[Dict[str, Any]] = None,
    recent_turns: Optional[List[Dict[str, str]]] = None,
) -> str:
    """Claude 에 전달할 사용자 메시지 구성 — 컨텍스트 + 질문."""
    blocks: List[str] = []

    # Brain — 항상 포함 (빈 경우도 명시)
    if brain_ctx and brain_ctx.get("ok") and brain_ctx.get("text"):
        blocks.append(f"[Brain 컨텍스트]\n{brain_ctx['text']}")
    else:
        blocks.append("[Brain 컨텍스트]\n(포트폴리오 데이터 조회 실패 또는 비어있음)")

    # Perplexity — 있으면
    if perplexity_result and perplexity_result.get("ok") and perplexity_result.get("text"):
        p_text = perplexity_result["text"]
        cites = perplexity_result.get("citations", [])
        cite_lines = []
        for i, c in enumerate(cites[:5], 1):
            url = c.get("url", "")
            title = c.get("title", "") or url[:60]
            if url:
                cite_lines.append(f"  [{i}] {title} — {url}")
        cite_block = ("\n출처:\n" + "\n".join(cite_lines)) if cite_lines else ""
        blocks.append(
            f"[Perplexity 외부 검색 ({perplexity_result.get('model', '?')})]\n"
            f"{p_text}{cite_block}"
        )
    elif perplexity_result and not perplexity_result.get("ok"):
        blocks.append(f"[Perplexity] 조회 실패 ({perplexity_result.get('error', '?')})")

    # Gemini Grounding — 있으면
    if grounding_result and grounding_result.get("ok") and grounding_result.get("text"):
        g_text = grounding_result["text"]
        cites = grounding_result.get("citations", [])
        cite_lines = []
        for i, c in enumerate(cites[:5], 1):
            url = c.get("url", "")
            title = c.get("title", "") or url[:60]
            if url:
                cite_lines.append(f"  [{i}] {title} — {url}")
        cite_block = ("\n출처:\n" + "\n".join(cite_lines)) if cite_lines else ""
        blocks.append(
            f"[Gemini Grounding (Google Search)]\n{g_text}{cite_block}"
        )
    elif grounding_result and not grounding_result.get("ok"):
        blocks.append(f"[Gemini Grounding] 조회 실패 ({grounding_result.get('error', '?')})")

    # 최근 대화 맥락
    if recent_turns:
        turn_lines = []
        for t in recent_turns[-4:]:
            role = t.get("role", "?")
            content = str(t.get("content", ""))[:200]
            turn_lines.append(f"  {role}: {content}")
        if turn_lines:
            blocks.append("[최근 대화]\n" + "\n".join(turn_lines))

    blocks.append(f"[질문]\n{query}")
    return "\n\n".join(blocks)


def stream_response(
    query: str,
    brain_ctx: Optional[Dict[str, Any]] = None,
    perplexity_result: Optional[Dict[str, Any]] = None,
    grounding_result: Optional[Dict[str, Any]] = None,
    recent_turns: Optional[List[Dict[str, str]]] = None,
    model: Optional[str] = None,
    max_tokens: Optional[int] = None,
) -> Iterator[Dict[str, Any]]:
    """Claude Sonnet 스트리밍 응답 generator.

    Yields:
      {"type": "delta", "text": "..."} — 토큰
      {"type": "meta", ...} — 시작 시 모델/컨텍스트 정보
      {"type": "end", "text": 전체, "usage": {...}, "cost_est": float} — 종료
      {"type": "error", "error": "..."} — 실패

    호출자는 이 이벤트 스트림을 NDJSON 으로 그대로 전달하면 된다.
    """
    global _call_count, _total_cost

    t0 = time.time()
    query = (query or "").strip()
    if not query:
        yield {"type": "error", "error": "빈 쿼리"}
        return

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        yield {"type": "error", "error": "ANTHROPIC_API_KEY 미설정"}
        return

    try:
        import anthropic
    except ImportError as e:
        yield {"type": "error", "error": f"anthropic SDK 미설치: {e}"}
        return

    use_model = (model or _default_model()).strip()
    use_max_tokens = max_tokens or _MAX_TOKENS

    user_message = _build_context_message(
        query=query,
        brain_ctx=brain_ctx,
        perplexity_result=perplexity_result,
        grounding_result=grounding_result,
        recent_turns=recent_turns,
    )

    sources_used = []
    if brain_ctx and brain_ctx.get("ok"):
        sources_used.append("Brain")
    if perplexity_result and perplexity_result.get("ok"):
        sources_used.append(f"P({len(perplexity_result.get('citations', []))})")
    if grounding_result and grounding_result.get("ok"):
        sources_used.append(f"G({len(grounding_result.get('citations', []))})")

    yield {
        "type": "meta",
        "model": use_model,
        "sources": sources_used,
        "prompt_chars": len(user_message),
    }

    collected: List[str] = []
    usage: Dict[str, Any] = {}

    try:
        client = anthropic.Anthropic(api_key=api_key)
        with client.messages.stream(
            model=use_model,
            max_tokens=use_max_tokens,
            temperature=_TEMPERATURE,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        ) as stream:
            for text_chunk in stream.text_stream:
                if text_chunk:
                    collected.append(text_chunk)
                    yield {"type": "delta", "text": text_chunk}

            final_msg = stream.get_final_message()
            if final_msg and getattr(final_msg, "usage", None):
                u = final_msg.usage
                usage = {
                    "input_tokens": getattr(u, "input_tokens", 0),
                    "output_tokens": getattr(u, "output_tokens", 0),
                }

    except Exception as e:
        err = f"{type(e).__name__}: {str(e)[:200]}"
        logger.warning("synthesizer 스트리밍 실패: %s", err)
        yield {"type": "error", "error": err, "partial": "".join(collected)}
        return

    with _lock:
        _call_count += 1
        _total_cost += _EST_COST_PER_CALL

    yield {
        "type": "end",
        "text": "".join(collected),
        "model": use_model,
        "usage": usage,
        "cost_est": _EST_COST_PER_CALL,
        "latency_ms": int((time.time() - t0) * 1000),
        "sources": sources_used,
    }


def synthesize_blocking(
    query: str,
    brain_ctx: Optional[Dict[str, Any]] = None,
    perplexity_result: Optional[Dict[str, Any]] = None,
    grounding_result: Optional[Dict[str, Any]] = None,
    recent_turns: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    """비스트리밍 호출 — 테스트 및 폴백용.

    Returns: {"ok": bool, "text": str, "usage": {...}, "latency_ms": int, ...}
    """
    text_parts: List[str] = []
    meta: Dict[str, Any] = {}
    end: Dict[str, Any] = {}
    error: Optional[str] = None

    for ev in stream_response(
        query=query,
        brain_ctx=brain_ctx,
        perplexity_result=perplexity_result,
        grounding_result=grounding_result,
        recent_turns=recent_turns,
    ):
        if ev["type"] == "delta":
            text_parts.append(ev["text"])
        elif ev["type"] == "meta":
            meta = ev
        elif ev["type"] == "end":
            end = ev
        elif ev["type"] == "error":
            error = ev.get("error")
            text_parts.append(ev.get("partial", ""))

    if error:
        return {"ok": False, "error": error, "text": "".join(text_parts)}

    return {
        "ok": True,
        "text": "".join(text_parts),
        "model": end.get("model", meta.get("model", "?")),
        "usage": end.get("usage", {}),
        "latency_ms": end.get("latency_ms", 0),
        "cost_est": end.get("cost_est", 0),
        "sources": end.get("sources", []),
    }


def get_session_stats() -> Dict[str, Any]:
    with _lock:
        return {"calls": _call_count, "cost_usd": round(_total_cost, 4)}


def reset_session_stats() -> None:
    global _call_count, _total_cost
    with _lock:
        _call_count = 0
        _total_cost = 0.0
