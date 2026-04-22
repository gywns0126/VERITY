"""
VERITY Chat Hybrid — Perplexity Sonar 클라이언트

기존 api/clients/perplexity_client.py 가 분기 리서치 전용이라 무거움.
Chat hybrid 는 다음이 핵심:
  - 5초 timeout (graceful degrade)
  - complexity → 모델 분기 (sonar / sonar-pro)
  - citations 추출 + 정제
  - 비용 추적 (hybrid 전용 카운터)

기존 api.clients.perplexity_client 는 재사용 안 함 (분리 원칙).

환경변수:
  PERPLEXITY_API_KEY — 필수
  CHAT_HYBRID_PERPLEXITY_TIMEOUT — 기본 5초
"""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


_API_URL = "https://api.perplexity.ai/chat/completions"
_TIMEOUT_SEC = float(os.environ.get("CHAT_HYBRID_PERPLEXITY_TIMEOUT", "5"))

# 모델 분기 (명령서: sonar 기본, complexity=complex 만 sonar-pro)
_MODEL_SIMPLE = "sonar"
_MODEL_COMPLEX = "sonar-pro"

# 비용 근사 (2025 년 기준, 호출당 추정 — 실제는 usage.cost 필드 신뢰)
_EST_COST = {"sonar": 0.002, "sonar-pro": 0.006}


_SYSTEM_PROMPT_KO = """You are a Korean financial news researcher.
Answer in Korean in 3-5 concise sentences. Cite specific sources.
If the query involves Korean stocks, prioritize Korean sources (Naver, 매일경제, 연합뉴스).
Do NOT speculate; only report confirmed facts from sources found.
If nothing relevant found in the last 7 days, say "최근 관련 뉴스 없음"."""


_lock = threading.Lock()
_call_count = 0
_total_cost = 0.0


def _select_model(complexity: str) -> str:
    return _MODEL_COMPLEX if str(complexity).lower() == "complex" else _MODEL_SIMPLE


def search(
    query: str,
    complexity: str = "simple",
    max_tokens: int = 500,
    tickers: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Perplexity Sonar 검색.

    Returns:
        성공: {
            "ok": True,
            "text": 요약,
            "citations": [{"url", "title"}, ...],
            "model": 사용된 모델,
            "latency_ms": 응답 시간,
            "cost_est": 추정 비용,
            "usage": {...},
        }
        실패: {
            "ok": False,
            "error": 에러 문자열,
            "latency_ms": 경과 시간,
        }

    호출자는 ok=False 시 graceful degrade — "외부 서치 지연" 안내.
    """
    global _call_count, _total_cost

    t0 = time.time()
    query = (query or "").strip()
    if not query:
        return {"ok": False, "error": "빈 쿼리", "latency_ms": 0}

    api_key = os.environ.get("PERPLEXITY_API_KEY", "")
    if not api_key:
        return {"ok": False, "error": "PERPLEXITY_API_KEY 미설정", "latency_ms": 0}

    model = _select_model(complexity)

    # 티커 힌트 추가 — 검색 정확도 향상
    user_content = query
    if tickers:
        user_content = f"{query}\n(related tickers: {', '.join(tickers[:5])})"

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT_KO},
            {"role": "user", "content": user_content},
        ],
        "max_tokens": max_tokens,
        "temperature": 0.2,
        "return_citations": True,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        resp = requests.post(_API_URL, headers=headers, json=payload, timeout=_TIMEOUT_SEC)
    except requests.Timeout:
        return {"ok": False, "error": f"timeout ({_TIMEOUT_SEC}s)", "latency_ms": int((time.time() - t0) * 1000)}
    except requests.RequestException as e:
        # raw exception string 은 로그에만, 반환은 유형만
        logger.warning("perplexity 네트워크 오류: %s", e)
        return {"ok": False, "error": f"network:{type(e).__name__}", "latency_ms": int((time.time() - t0) * 1000)}

    latency_ms = int((time.time() - t0) * 1000)
    if resp.status_code != 200:
        # 응답 본문은 로그에만 (API 내부 구조·prompt 주입 노출 방지).
        # 사용자 경로로 전달되는 error 필드는 상태코드와 일반 카테고리만.
        logger.warning("perplexity HTTP %s: %s", resp.status_code, resp.text[:300])
        if resp.status_code == 429:
            generic = "rate_limit"
        elif 500 <= resp.status_code < 600:
            generic = "upstream_error"
        elif resp.status_code == 401 or resp.status_code == 403:
            generic = "auth_error"
        else:
            generic = "http_error"
        return {"ok": False, "error": f"{generic} (HTTP {resp.status_code})", "latency_ms": latency_ms}

    try:
        data = resp.json()
    except ValueError:
        return {"ok": False, "error": "JSON 파싱 실패", "latency_ms": latency_ms}

    choice = (data.get("choices") or [{}])[0]
    content = (choice.get("message") or {}).get("content", "")

    # citations 정제 (URL 리스트 또는 {url, title} dict 리스트 둘 다 가능)
    raw_citations = data.get("citations") or []
    citations: List[Dict[str, str]] = []
    for c in raw_citations[:10]:
        if isinstance(c, str):
            citations.append({"url": c, "title": ""})
        elif isinstance(c, dict):
            url = c.get("url") or c.get("href") or ""
            if url:
                citations.append({"url": url, "title": c.get("title", "")})

    usage = data.get("usage", {})
    cost_obj = usage.get("cost") if isinstance(usage, dict) else None
    run_cost = 0.0
    if isinstance(cost_obj, dict):
        run_cost = float(cost_obj.get("total_cost", 0) or 0)
    elif isinstance(cost_obj, (int, float)):
        run_cost = float(cost_obj)
    if run_cost <= 0:
        run_cost = _EST_COST.get(model, 0.003)

    with _lock:
        _call_count += 1
        _total_cost += run_cost

    return {
        "ok": True,
        "text": content.strip(),
        "citations": citations,
        "model": data.get("model", model),
        "latency_ms": latency_ms,
        "cost_est": round(run_cost, 5),
        "usage": usage,
    }


def get_session_stats() -> Dict[str, Any]:
    """현 프로세스 Perplexity 누적 호출 수·비용."""
    with _lock:
        return {"calls": _call_count, "cost_usd": round(_total_cost, 4)}


def reset_session_stats() -> None:
    """테스트용 세션 초기화."""
    global _call_count, _total_cost
    with _lock:
        _call_count = 0
        _total_cost = 0.0
