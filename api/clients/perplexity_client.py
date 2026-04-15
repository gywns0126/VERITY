"""
Perplexity Sonar API 공용 클라이언트

모든 Perplexity 호출(분기 리서치, 매크로 이벤트, 실적 요약, 리스크 탐지)이
이 모듈을 경유한다. 호출 카운터·비용을 중앙에서 추적.
"""
from __future__ import annotations

import threading
from typing import Any, Dict, Optional

import requests

from api.config import PERPLEXITY_API_KEY, PERPLEXITY_MODEL

_API_URL = "https://api.perplexity.ai/v1/sonar"

_lock = threading.Lock()
_call_count = 0
_total_cost = 0.0


def call_perplexity(
    query: str,
    system_prompt: str = "",
    max_tokens: int = 2000,
    temperature: float = 0.1,
) -> Dict[str, Any]:
    """Perplexity Sonar API 단일 호출.

    Returns:
        성공: {"content": str, "citations": list, "model": str, "usage": dict}
        실패: {"error": str}
    """
    global _call_count, _total_cost

    if not PERPLEXITY_API_KEY:
        return {"error": "PERPLEXITY_API_KEY 미설정"}

    headers = {
        "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
        "Content-Type": "application/json",
    }
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": query})

    payload = {
        "model": PERPLEXITY_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    try:
        resp = requests.post(_API_URL, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        return {"error": str(e)}

    choice = data.get("choices", [{}])[0]
    message = choice.get("message", {})
    usage = data.get("usage", {})

    cost_obj = usage.get("cost", {})
    run_cost = 0.0
    if isinstance(cost_obj, dict):
        run_cost = cost_obj.get("total_cost", 0)
    elif isinstance(cost_obj, (int, float)):
        run_cost = float(cost_obj)

    with _lock:
        _call_count += 1
        _total_cost += run_cost

    return {
        "content": message.get("content", ""),
        "citations": data.get("citations", []),
        "model": data.get("model", ""),
        "usage": usage,
    }


def get_session_stats() -> Dict[str, Any]:
    """현재 프로세스의 Perplexity 누적 호출 수·비용."""
    with _lock:
        return {"calls": _call_count, "cost_usd": round(_total_cost, 4)}


def reset_session_stats() -> None:
    """세션 통계 초기화 (테스트용)."""
    global _call_count, _total_cost
    with _lock:
        _call_count = 0
        _total_cost = 0.0
