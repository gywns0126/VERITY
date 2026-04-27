"""
LLM 호출 비용 ROI 추적 — Monthly~Annual 리포트.

매 LLM 호출 시 input/output 토큰 + 모델별 단가 계산 → 누적.
월간/분기/반기/연간 비용 vs VAMS 수익 ROI 측정.

저장: data/metadata/llm_cost.jsonl
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from api.config import DATA_DIR, now_kst

_PATH = os.path.join(DATA_DIR, "metadata", "llm_cost.jsonl")

# 모델별 토큰 단가 (USD per 1M tokens). 2026-04 기준 추정.
_PRICING = {
    # Anthropic (2026-04 기준 추정 — 실제 단가는 Anthropic console 확인)
    "claude-haiku-4-5": {"input": 1.0, "output": 5.0},
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
    "claude-opus-4-7": {"input": 15.0, "output": 75.0},
    # Google Gemini
    "gemini-2.5-flash": {"input": 0.30, "output": 1.20},
    "gemini-2.5-pro": {"input": 2.50, "output": 10.0},
    # Perplexity
    "sonar-pro": {"input": 3.0, "output": 15.0},
}


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """USD 추정 비용. 알 수 없는 모델은 0."""
    p = _PRICING.get(model)
    if not p:
        return 0.0
    return (input_tokens * p["input"] + output_tokens * p["output"]) / 1_000_000


def log_call(
    provider: str,
    model: str,
    call_type: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: Optional[float] = None,
    success: bool = True,
) -> Dict[str, Any]:
    """LLM 호출 1건 로깅."""
    os.makedirs(os.path.dirname(_PATH), exist_ok=True)
    if cost_usd is None:
        cost_usd = estimate_cost(model, input_tokens, output_tokens)
    entry = {
        "timestamp": now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "date": now_kst().strftime("%Y-%m-%d"),
        "provider": provider,
        "model": model,
        "call_type": call_type,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": round(cost_usd, 6),
        "success": success,
    }
    with open(_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def summarize_cost(days: int = 30) -> Dict[str, Any]:
    """기간별 비용 요약 — provider/model/call_type 분해."""
    if not os.path.exists(_PATH):
        return {"days": days, "total_usd": 0, "calls": 0}

    cutoff = (now_kst().date() - __import__("datetime").timedelta(days=days)).strftime("%Y-%m-%d")

    by_provider: Dict[str, float] = {}
    by_model: Dict[str, float] = {}
    by_type: Dict[str, float] = {}
    total = 0.0
    calls = 0
    failed = 0

    with open(_PATH, "r", encoding="utf-8") as f:
        for line in f:
            try:
                e = json.loads(line)
                if e.get("date", "") < cutoff:
                    continue
                cost = e.get("cost_usd", 0)
                total += cost
                calls += 1
                if not e.get("success", True):
                    failed += 1
                p = e.get("provider", "unknown")
                m = e.get("model", "unknown")
                t = e.get("call_type", "unknown")
                by_provider[p] = by_provider.get(p, 0) + cost
                by_model[m] = by_model.get(m, 0) + cost
                by_type[t] = by_type.get(t, 0) + cost
            except json.JSONDecodeError:
                continue

    return {
        "days": days,
        "total_usd": round(total, 2),
        "total_krw_est": round(total * 1380),  # 환율 1380 가정
        "calls": calls,
        "failed_calls": failed,
        "avg_cost_per_call": round(total / calls, 4) if calls else 0,
        "by_provider": {k: round(v, 2) for k, v in by_provider.items()},
        "by_model": {k: round(v, 2) for k, v in sorted(by_model.items(), key=lambda x: -x[1])[:5]},
        "by_type": {k: round(v, 2) for k, v in by_type.items()},
    }


def cost_roi(days: int = 30, vams_return_krw: float = 0) -> Dict[str, Any]:
    """LLM 비용 vs VAMS 수익 ROI 비율."""
    cost = summarize_cost(days)
    cost_krw = cost.get("total_krw_est", 0)
    if cost_krw == 0:
        return {**cost, "roi_pct": None}
    roi_pct = round((vams_return_krw / cost_krw) * 100, 1) if cost_krw > 0 else None
    return {**cost, "vams_return_krw": vams_return_krw, "roi_pct": roi_pct}
