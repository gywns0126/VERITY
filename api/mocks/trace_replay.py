"""
Trace Replay — data/runs/ 아카이브에서 key별 최신 성공 AI 응답을 로드.

@mockable 키 → trace의 call_type/provider 매핑 예:
  "gemini.daily_report"  → provider=gemini, call_type=daily_report
  "claude.deep"          → provider=claude, call_type=deep_analysis
  "perplexity.sonar"     → provider=perplexity, call_type=sonar_search
"""
from __future__ import annotations

import gzip
import json
import os
from typing import Any, Dict, Optional

from api.config import DATA_DIR

_TRACE_DIR = os.path.join(DATA_DIR, "runs")

_KEY_TO_TRACE: Dict[str, Dict[str, str]] = {
    "gemini.stock_analysis": {"provider": "gemini", "call_type": "stock_analysis"},
    "gemini.daily_report": {"provider": "gemini", "call_type": "daily_report"},
    "gemini.periodic_report": {"provider": "gemini", "call_type": "periodic_report"},
    "claude.deep": {"provider": "claude", "call_type": "deep_analysis"},
    "claude.light": {"provider": "claude", "call_type": "claude_util"},
    "perplexity.sonar": {"provider": "perplexity", "call_type": "sonar_search"},
}

_cache: Dict[str, Optional[Any]] = {}


def _parse_trace_file(path: str) -> Optional[Dict[str, Any]]:
    try:
        if path.endswith(".gz"):
            with gzip.open(path, "rb") as f:
                return json.loads(f.read().decode("utf-8"))
        else:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        return None


def _find_latest_traces(limit: int = 5):
    """최근 N개 trace 파일 경로를 반환 (내림차순)."""
    if not os.path.isdir(_TRACE_DIR):
        return []
    files = []
    for f in os.listdir(_TRACE_DIR):
        if f.endswith((".json", ".json.gz")):
            files.append(os.path.join(_TRACE_DIR, f))
    files.sort(reverse=True)
    return files[:limit]


def load_latest_trace(key: str) -> Optional[Any]:
    """mock 키에 해당하는 최신 AI 응답을 trace에서 추출. 없으면 None."""
    if key in _cache:
        return _cache[key]

    mapping = _KEY_TO_TRACE.get(key)
    if not mapping:
        _cache[key] = None
        return None

    target_provider = mapping["provider"]
    target_call_type = mapping["call_type"]

    for trace_path in _find_latest_traces(10):
        data = _parse_trace_file(trace_path)
        if not data:
            continue
        ai_calls = data.get("ai_calls") or []
        for call in reversed(ai_calls):
            if (call.get("provider") == target_provider
                    and call.get("call_type") == target_call_type
                    and call.get("response_preview")):
                preview = call["response_preview"]
                try:
                    parsed = json.loads(preview)
                    _cache[key] = parsed
                    return parsed
                except (json.JSONDecodeError, TypeError):
                    _cache[key] = preview
                    return preview

    _cache[key] = None
    return None
