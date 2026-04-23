"""
VERITY Chat Hybrid — 오케스트레이터 (Phase 2.5)

run_hybrid(query, session_id, recent_turns) 이 진입점.
NDJSON 이벤트 스트림을 yield — 호출 서버(vercel-api/api/chat.py)가 그대로 전송.

흐름:
  1. rate_limit 체크 → 초과 시 429 이벤트
  2. quick_intent (규칙) 또는 classifier → intent_type 결정
  3. 분기:
     - greeting / portfolio_only:
         Brain 즉시 → Claude 스트리밍 (TTFB ≤2s 목표)
     - external_only / hybrid:
         ThreadPoolExecutor 로 Brain + Perplexity + Gemini 병렬 실행,
         모두 완료 후 Claude 스트리밍 (TTFB 5-6s, 품질 우선 — Option C)
  4. 캐시: classifier 결과, perplexity/grounding 응답은 3단 캐시 hit 우선

환경변수:
  CHAT_HYBRID_ENABLED — "false" 면 호출자가 우회 (체크는 호출자 담당)
  CHAT_HYBRID_DEADLINE_SEC — 전체 deadline. 기본 12초 (= external 5s + claude 7s 여유)

이벤트 타입:
  {"type":"status","stage":"<이름>","latency_ms":int,...}
  {"type":"meta","model":..., "sources":[...], ...}
  {"type":"delta","text":"..."}
  {"type":"end","text":전체,"sources":[...],"usage":{...},"total_ms":int,"cost_est":float}
  {"type":"error","error":"...","stage":"..."}
  {"type":"rate_limit","reason":"...","retry_after_sec":int}
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, Iterator, List, Optional

from api.chat_hybrid import cache, rate_limit
from api.chat_hybrid.intent_classifier import classify, quick_intent_from_rules
from api.chat_hybrid.response_synthesizer import stream_response
from api.chat_hybrid.search import brain_client, gemini_grounding, perplexity_client

logger = logging.getLogger(__name__)
# 전용 로거 — Vercel Function Logs 에서 jq 로 파싱하기 쉽도록
_metrics_logger = logging.getLogger("chat_hybrid.metrics")


def _emit_metric(m: Dict[str, Any]) -> None:
    """한 줄 JSON 로그 — `chat_hybrid.metrics` 로거로 emit.

    Vercel Function Logs 에서:
      logs | grep 'chat_hybrid.metrics' | jq '.'
    """
    try:
        _metrics_logger.info("chat_hybrid.metrics %s", json.dumps(m, ensure_ascii=False, default=str))
    except Exception:
        pass  # 로깅 실패로 요청 흐름 깨지 않음


def _hash_session(sid: str) -> str:
    """session_id 해시 — 원본 IP 등 PII 로깅 방지."""
    return hashlib.sha256((sid or "").encode("utf-8")).hexdigest()[:10]


_DEADLINE_SEC = float(os.environ.get("CHAT_HYBRID_DEADLINE_SEC", "12"))
_EXTERNAL_PARALLEL_TIMEOUT = float(os.environ.get("CHAT_HYBRID_EXTERNAL_TIMEOUT", "6"))
_MAX_QUERY_LEN = int(os.environ.get("CHAT_HYBRID_MAX_QUERY_LEN", "500"))

# Defense-in-depth — chat.py 에서도 차단하지만 오케스트레이터 단독 호출 (테스트, 내부 툴) 대비.
#
# 2단 필터 (이전엔 부분일치 substring 만으로 false positive 과다:
#   "삼성전자 시스템 프롬프트 전환 리스크 어때?" 같은 정상 질문이 차단됐음):
#   1) _ALWAYS_BLOCKED — 시스템 프롬프트 문법/역할 마커. 정상 질문에 나올 일 없음.
#   2) _SUSPICIOUS — 공격 어휘 후보. 단독으론 일반 주제(삼성 system prompt 특허) 에도 나오므로
#      _ATTACK_VERBS (공개/노출/덮어쓰기 류) 와 공존할 때만 차단.
_ALWAYS_BLOCKED = (
    "```system", "<|system|>", "<|im_start|>", "<|im_end|>",
    "role: system", "role:system",
)

_SUSPICIOUS = (
    "ignore previous", "ignore the above",
    "disregard instructions", "disregard the above", "disregard previous",
    "시스템 프롬프트", "시스템프롬프트", "system prompt",
    "reveal your instructions", "reveal the system",
    "너의 프롬프트", "너의 지시", "당신의 지시", "당신의 프롬프트",
    "original system", "developer message",
    "print your instructions", "show me your instructions",
)

_ATTACK_VERBS = (
    "보여줘", "보여주", "보여 줘", "공개해", "공개하", "출력해", "출력하",
    "알려줘", "알려주", "드러내", "노출",
    "무시하고", "무시해", "잊어", "잊어버려",
    "reveal", "print", "show me", "dump", "leak",
    "override", "bypass", "disregard", "forget",
)


def _is_prompt_injection(q: str) -> bool:
    q_lower = (q or "").lower()
    if any(p in q_lower for p in _ALWAYS_BLOCKED):
        return True
    if any(s in q_lower for s in _SUSPICIOUS) and any(v in q_lower for v in _ATTACK_VERBS):
        return True
    return False


def _cached_perplexity(query: str, complexity: str, tickers: List[str], cache_key: str) -> Dict[str, Any]:
    cached = cache.get("perplexity", cache_key)
    if cached is not None:
        return {**cached, "_cache_hit": True}
    result = perplexity_client.search(query=query, complexity=complexity, tickers=tickers)
    if result.get("ok"):
        cache.set_value("perplexity", cache_key, result)
    return result


def _cached_grounding(query: str, tickers: List[str], cache_key: str) -> Dict[str, Any]:
    cached = cache.get("grounding", cache_key)
    if cached is not None:
        return {**cached, "_cache_hit": True}
    result = gemini_grounding.search(query=query, tickers=tickers)
    if result.get("ok"):
        cache.set_value("grounding", cache_key, result)
    return result


def _cached_classify(query: str, recent_turns: Optional[List[str]], cache_key: str) -> Dict[str, Any]:
    cached = cache.get("intent", cache_key)
    if cached is not None:
        return {**cached, "_cache_hit": True}
    result = classify(query=query, recent_turns=recent_turns)
    cache.set_value("intent", cache_key, result)
    return result


def _run_externals_parallel(
    query: str,
    intent: Dict[str, Any],
    brain_ctx_ref: Dict[str, Any],
) -> Dict[str, Any]:
    """Brain + (optional) Perplexity + (optional) Gemini Grounding 병렬.

    Brain 은 로컬 호출이라 별도 스레드 없이 호출하되, external 과 같은 타임라인
    관점에서 실행. 반환 dict 에 각 결과 또는 None.
    """
    results: Dict[str, Any] = {
        "brain": brain_ctx_ref,   # 이미 호출자가 채워둠 (호출자 선택)
        "perplexity": None,
        "grounding": None,
    }

    tickers = intent.get("related_tickers", [])
    complexity = intent.get("complexity", "simple")
    cache_key = intent.get("cache_key", "")
    needs_p = intent.get("needs_perplexity", False)
    needs_g = intent.get("needs_gemini_grounding", False)

    tasks = {}
    with ThreadPoolExecutor(max_workers=3) as ex:
        if needs_p:
            tasks["perplexity"] = ex.submit(
                _cached_perplexity, query, complexity, tickers, cache_key,
            )
        if needs_g:
            tasks["grounding"] = ex.submit(
                _cached_grounding, query, tickers, cache_key,
            )

        t0 = time.time()
        for name, fut in tasks.items():
            remaining = max(0.1, _EXTERNAL_PARALLEL_TIMEOUT - (time.time() - t0))
            try:
                results[name] = fut.result(timeout=remaining)
            except Exception as e:
                results[name] = {"ok": False, "error": f"{type(e).__name__}:{str(e)[:100]}"}

    return results


def run_hybrid(
    query: str,
    session_id: str = "anonymous",
    recent_turns: Optional[List[Dict[str, str]]] = None,
) -> Iterator[Dict[str, Any]]:
    """메인 엔트리 — NDJSON 이벤트 generator.

    호출자는 각 이벤트를 `json.dumps(ev) + "\\n"` 로 바로 내려보내면 됨.
    """
    t0 = time.time()
    query = (query or "").strip()

    # 구조화 로깅용 metrics — 단계별로 누적, finally 에서 한 줄 emit.
    metrics: Dict[str, Any] = {
        "t": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(t0)),
        "session_hash": _hash_session(session_id),
        "query_len": len(query),
        "outcome": "unknown",
        "stages": {},
    }

    try:
        if not query:
            metrics["outcome"] = "reject:empty"
            yield {"type": "error", "error": "빈 쿼리", "stage": "input"}
            return

        # 길이 제한 — chat.py 도 500자 cutoff 있지만 내부 호출자 대비.
        if len(query) > _MAX_QUERY_LEN:
            metrics["outcome"] = "reject:too_long"
            yield {"type": "error", "error": f"질문이 너무 깁니다 ({_MAX_QUERY_LEN}자 이내)", "stage": "input"}
            return

        # Prompt injection 방어 — chat.py 가 1차 차단하지만 defense-in-depth.
        if _is_prompt_injection(query):
            metrics["outcome"] = "reject:injection"
            yield {"type": "error", "error": "허용되지 않는 질문 형식입니다.", "stage": "input"}
            return

        # 1. Rate limit
        ok, info = rate_limit.check_and_consume(session_id)
        if not ok:
            metrics["outcome"] = f"reject:rate_limit:{(info or {}).get('limit_type', '?')}"
        # rest of body indented inside try — done via separate edits
        yield from _run_hybrid_core(query, session_id, recent_turns, t0, metrics, ok, info)
    except Exception as e:
        metrics["outcome"] = f"error:{type(e).__name__}"
        metrics["error_msg"] = str(e)[:200]
        raise
    finally:
        metrics["total_ms"] = int((time.time() - t0) * 1000)
        _emit_metric(metrics)


def _run_hybrid_core(
    query: str,
    session_id: str,
    recent_turns: Optional[List[Dict[str, str]]],
    t0: float,
    metrics: Dict[str, Any],
    rate_ok: bool,
    rate_info: Optional[Dict],
) -> Iterator[Dict[str, Any]]:
    """오케스트레이션 본체 — run_hybrid 의 try 블록에서 호출."""
    # rate_limit 판정은 caller 에서 이미 함
    ok = rate_ok
    info = rate_info
    if not ok:
        yield {"type": "rate_limit", **(info or {"reason": "rate limit"})}
        return

    # 2. 규칙 기반 ultra-fast intent (greeting 감지)
    quick = quick_intent_from_rules(query)
    intent: Dict[str, Any]

    if quick == "greeting":
        intent = {
            "intent_type": "greeting",
            "related_tickers": [],
            "complexity": "simple",
            "needs_perplexity": False,
            "needs_gemini_grounding": False,
            "cache_key": "",
            "_source": "quick_rules",
        }
        intent_ms = int((time.time() - t0) * 1000)
        metrics["stages"]["intent"] = intent_ms
        metrics["intent_source"] = "quick_rules"
        yield {"type": "status", "stage": "intent", "latency_ms": intent_ms,
               "intent_type": "greeting", "shortcut": True}
    else:
        # 3. Classifier (캐시 hit 시 수 ms)
        t_cls = time.time()
        from api.chat_hybrid.intent_classifier import _cache_key as _ck
        cache_key = _ck(query)
        recent_texts = None
        if recent_turns:
            recent_texts = [str(t.get("content", "")) for t in recent_turns[-3:]]
        intent = _cached_classify(query, recent_texts, cache_key)
        intent["cache_key"] = cache_key
        intent_ms = int((time.time() - t_cls) * 1000)
        metrics["stages"]["intent"] = intent_ms
        metrics["intent_source"] = intent.get("_source", "?")
        metrics["intent_cache_hit"] = bool(intent.get("_cache_hit"))
        yield {
            "type": "status",
            "stage": "intent",
            "latency_ms": intent_ms,
            "intent_type": intent.get("intent_type"),
            "related_tickers": intent.get("related_tickers", []),
            "complexity": intent.get("complexity"),
            "needs_perplexity": intent.get("needs_perplexity"),
            "needs_gemini_grounding": intent.get("needs_gemini_grounding"),
            "classifier_source": intent.get("_source"),
            "cache_hit": intent.get("_cache_hit", False),
        }

    intent_type = intent.get("intent_type", "hybrid")
    metrics["intent_type"] = intent_type
    metrics["related_tickers_count"] = len(intent.get("related_tickers", []))

    # 4. Brain 컨텍스트 — 모든 intent 에 주입 (greeting 도 시장 요약 있으면 활용)
    t_brain = time.time()
    brain_ctx = brain_client.fetch_brain_context(query=query, intent=intent, session_id=session_id)
    brain_ms = int((time.time() - t_brain) * 1000)
    metrics["stages"]["brain"] = brain_ms
    metrics["brain_matched"] = len(brain_ctx.get("matched_tickers", []))
    yield {
        "type": "status",
        "stage": "brain",
        "latency_ms": brain_ms,
        "matched_tickers": brain_ctx.get("matched_tickers", []),
    }

    # 5. External 호출 분기
    perplexity_result = None
    grounding_result = None

    if intent_type in ("external_only", "hybrid") and (
        intent.get("needs_perplexity") or intent.get("needs_gemini_grounding")
    ):
        t_ext = time.time()
        ext = _run_externals_parallel(query=query, intent=intent, brain_ctx_ref=brain_ctx)
        perplexity_result = ext.get("perplexity")
        grounding_result = ext.get("grounding")
        ext_ms = int((time.time() - t_ext) * 1000)
        metrics["stages"]["external"] = ext_ms
        metrics["perplexity"] = {
            "ok": bool(perplexity_result and perplexity_result.get("ok")),
            "cache_hit": bool((perplexity_result or {}).get("_cache_hit")),
            "citations": len((perplexity_result or {}).get("citations", [])),
        } if perplexity_result is not None else None
        metrics["grounding"] = {
            "ok": bool(grounding_result and grounding_result.get("ok")),
            "cache_hit": bool((grounding_result or {}).get("_cache_hit")),
            "citations": len((grounding_result or {}).get("citations", [])),
        } if grounding_result is not None else None

        yield {
            "type": "status",
            "stage": "external",
            "latency_ms": ext_ms,
            "perplexity": {
                "ok": bool(perplexity_result and perplexity_result.get("ok")),
                "latency_ms": (perplexity_result or {}).get("latency_ms"),
                "citations": len((perplexity_result or {}).get("citations", [])),
                "cache_hit": (perplexity_result or {}).get("_cache_hit", False),
                "error": (perplexity_result or {}).get("error") if perplexity_result and not perplexity_result.get("ok") else None,
            } if perplexity_result is not None else None,
            "grounding": {
                "ok": bool(grounding_result and grounding_result.get("ok")),
                "latency_ms": (grounding_result or {}).get("latency_ms"),
                "citations": len((grounding_result or {}).get("citations", [])),
                "cache_hit": (grounding_result or {}).get("_cache_hit", False),
                "error": (grounding_result or {}).get("error") if grounding_result and not grounding_result.get("ok") else None,
            } if grounding_result is not None else None,
        }

    # 6. Deadline 체크 — Claude 시작 전 마지막 체크
    elapsed = time.time() - t0
    if elapsed > _DEADLINE_SEC:
        metrics["outcome"] = "deadline_exceeded"
        yield {"type": "error", "error": f"deadline 초과 ({elapsed:.1f}s)", "stage": "pre_synth"}
        return

    # 7. Claude 스트리밍 합성
    final_text_parts: List[str] = []
    final_end: Dict[str, Any] = {}
    synth_error: Optional[str] = None
    t_synth = time.time()

    for ev in stream_response(
        query=query,
        brain_ctx=brain_ctx,
        perplexity_result=perplexity_result,
        grounding_result=grounding_result,
        recent_turns=recent_turns,
    ):
        etype = ev.get("type")
        if etype == "delta":
            final_text_parts.append(ev.get("text", ""))
            yield ev
        elif etype == "meta":
            yield ev
        elif etype == "end":
            final_end = ev
        elif etype == "error":
            synth_error = ev.get("error")
            yield ev

    metrics["stages"]["synth"] = int((time.time() - t_synth) * 1000)
    if synth_error:
        metrics["outcome"] = "synth_error"
        metrics["error_msg"] = str(synth_error)[:200]
        return
    if final_end.get("usage"):
        metrics["usage"] = final_end["usage"]
    metrics["cost_est"] = final_end.get("cost_est", 0)
    metrics["response_chars"] = sum(len(s) for s in final_text_parts)
    metrics["outcome"] = "success"

    # 8. 최종 집계 이벤트
    total_ms = int((time.time() - t0) * 1000)
    sources_used: List[str] = []
    if brain_ctx.get("ok"):
        sources_used.append("Brain")
    if perplexity_result and perplexity_result.get("ok"):
        sources_used.append(f"P({len(perplexity_result.get('citations', []))})")
    if grounding_result and grounding_result.get("ok"):
        sources_used.append(f"G({len(grounding_result.get('citations', []))})")

    # 원본 citations 수집 — UI 에서 링크 렌더용
    all_citations: List[Dict[str, str]] = []
    if perplexity_result and perplexity_result.get("ok"):
        all_citations.extend(perplexity_result.get("citations", []))
    if grounding_result and grounding_result.get("ok"):
        all_citations.extend(grounding_result.get("citations", []))
    # dedupe by url
    seen = set()
    deduped: List[Dict[str, str]] = []
    for c in all_citations:
        u = c.get("url", "")
        if u and u not in seen:
            seen.add(u)
            deduped.append(c)

    yield {
        "type": "end",
        "text": "".join(final_text_parts),
        "sources": sources_used,
        "citations": deduped[:10],
        "intent_type": intent_type,
        "matched_tickers": brain_ctx.get("matched_tickers", []),
        "usage": final_end.get("usage", {}),
        "cost_est": final_end.get("cost_est", 0),
        "total_ms": total_ms,
        "synth_ms": final_end.get("latency_ms"),
    }


def diagnostics() -> Dict[str, Any]:
    """디버깅/관리용 — 캐시 통계 + rate limit 상태 + 누적 비용."""
    return {
        "cache": cache.stats(),
        "rate_limit_global": rate_limit.get_status("__global__"),
        "perplexity": perplexity_client.get_session_stats(),
        "grounding": gemini_grounding.get_session_stats(),
    }
