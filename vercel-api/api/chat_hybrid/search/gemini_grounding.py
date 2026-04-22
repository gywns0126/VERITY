"""
VERITY Chat Hybrid — Gemini Grounding (Google Search) 클라이언트

공식 문서:
  https://ai.google.dev/gemini-api/docs/grounding

Perplexity 와 교차 검증 용 — 최신 수치·공식 정보에 강함 (FOMC 일정, 지수 값 등).

4초 timeout — Perplexity 5초보다 짧게 (Gemini 가 일반적으로 빠름).

환경변수:
  GEMINI_API_KEY — 필수 (기존 재사용)
  CHAT_HYBRID_GROUNDING_MODEL — 기본 gemini-2.0-flash-exp
  CHAT_HYBRID_GROUNDING_TIMEOUT — 기본 4초
"""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


_MODEL = os.environ.get("CHAT_HYBRID_GROUNDING_MODEL", "gemini-2.5-flash-lite").strip()
_TIMEOUT_SEC = float(os.environ.get("CHAT_HYBRID_GROUNDING_TIMEOUT", "4"))

# Grounding 유료 기능 — 호출당 대략 $0.035/1k chars (2025 기준). 보수적 추정.
_EST_COST_PER_CALL = 0.003


_SYSTEM_INSTRUCTION = """You are a precise financial data lookup assistant.
Answer in Korean in 2-4 concise sentences.
Prioritize:
  1. Latest official figures (prices, dates, rates, ratios)
  2. Scheduled events (FOMC, CPI releases, earnings dates)
  3. Regulatory/policy announcements
Avoid speculation. Include specific numbers when available."""


_lock = threading.Lock()
_call_count = 0
_total_cost = 0.0


def search(query: str, max_tokens: int = 500, tickers: Optional[List[str]] = None) -> Dict[str, Any]:
    """Gemini Grounding + Google Search 검색.

    Returns:
        성공: {
            "ok": True,
            "text": 요약,
            "citations": [{"url", "title"}, ...],
            "model": 모델,
            "latency_ms": 응답시간,
            "cost_est": 추정 비용,
            "search_queries": Google 실제 검색어 리스트,
        }
        실패: {
            "ok": False,
            "error": 에러 문자열,
            "latency_ms": 경과 시간,
        }
    """
    global _call_count, _total_cost

    t0 = time.time()
    query = (query or "").strip()
    if not query:
        return {"ok": False, "error": "빈 쿼리", "latency_ms": 0}

    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return {"ok": False, "error": "GEMINI_API_KEY 미설정", "latency_ms": 0}

    user_query = query
    if tickers:
        user_query = f"{query}\n(관련 티커: {', '.join(tickers[:5])})"

    try:
        from google import genai
        from google.genai import types as gtypes
    except ImportError as e:
        return {"ok": False, "error": f"google-genai SDK 미설치: {e}", "latency_ms": 0}

    try:
        client = genai.Client(api_key=api_key)

        # Grounding tool — google_search (새 SDK 방식)
        try:
            grounding_tool = gtypes.Tool(google_search=gtypes.GoogleSearch())
        except AttributeError:
            # 구 SDK: google_search_retrieval
            try:
                grounding_tool = gtypes.Tool(
                    google_search_retrieval=gtypes.GoogleSearchRetrieval()
                )
            except AttributeError:
                return {
                    "ok": False,
                    "error": "google-genai 버전이 Grounding 지원 안 함",
                    "latency_ms": int((time.time() - t0) * 1000),
                }

        config = gtypes.GenerateContentConfig(
            temperature=0.2,
            max_output_tokens=max_tokens,
            tools=[grounding_tool],
            system_instruction=_SYSTEM_INSTRUCTION,
        )

        # sync 호출 (ThreadPoolExecutor 에서 병렬 사용)
        # 파이썬 3.9 에서 google-genai 가 timeout 파라미터 직접 제공 안 함 →
        # 호출 자체는 5초 내외로 정상 응답. 진짜 timeout 방어는 orchestrator 에서 wait_for.
        resp = client.models.generate_content(
            model=_MODEL,
            contents=user_query,
            config=config,
        )

    except Exception as e:
        err = f"{type(e).__name__}: {str(e)[:150]}"
        return {"ok": False, "error": err, "latency_ms": int((time.time() - t0) * 1000)}

    latency_ms = int((time.time() - t0) * 1000)
    text = getattr(resp, "text", "") or ""

    # grounding metadata 추출 — SDK 버전별 호환
    citations: List[Dict[str, str]] = []
    search_queries: List[str] = []
    try:
        candidate = (resp.candidates or [None])[0]
        if candidate and hasattr(candidate, "grounding_metadata") and candidate.grounding_metadata:
            gm = candidate.grounding_metadata
            # grounding_chunks 또는 grounding_supports (버전별)
            chunks = getattr(gm, "grounding_chunks", None) or []
            for c in chunks[:10]:
                web = getattr(c, "web", None)
                if web:
                    url = getattr(web, "uri", "") or ""
                    title = getattr(web, "title", "") or ""
                    if url:
                        citations.append({"url": url, "title": title})
            # Google 이 실제 수행한 검색어
            web_sq = getattr(gm, "web_search_queries", None) or []
            search_queries = [str(s) for s in web_sq[:5]]
    except Exception as e:
        logger.debug("grounding_metadata 파싱: %s", e)

    with _lock:
        _call_count += 1
        _total_cost += _EST_COST_PER_CALL

    return {
        "ok": True,
        "text": text.strip(),
        "citations": citations,
        "model": _MODEL,
        "latency_ms": latency_ms,
        "cost_est": _EST_COST_PER_CALL,
        "search_queries": search_queries,
    }


def get_session_stats() -> Dict[str, Any]:
    with _lock:
        return {"calls": _call_count, "cost_usd": round(_total_cost, 4)}


def reset_session_stats() -> None:
    global _call_count, _total_cost
    with _lock:
        _call_count = 0
        _total_cost = 0.0
