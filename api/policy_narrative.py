"""
policy_narrative.py — 정책 → 부동산 시장 영향 1줄 한줄평 (P2 Step 3)

빌더(estate_hero_briefing_builder)가 호출하는 AI 한줄평 모듈.
ScoreDetail 의 룰 기반 narrative (vercel-api/api/landex_narrative.py) 와는 책임 분리:
    - vercel-api/api/landex_narrative.py: ScoreDetailPanel 강점/약점, 룰 기반, AI 호출 X
    - 이 파일                          : HeroBriefing 정책 한줄평, AI 호출 (sonnet)

거짓말 트랩:
    T1·T9  fabricate·silent X — 실패 시 None + 명시 로그
    T2     mock 텍스트 폴백 X — "AI 분석 중입니다" 같은 placeholder 절대 X
    T8/T17 모델 = claude-sonnet-4-20250514 (변경 시 사전 승인. haiku/opus 금지)
    T18    logs/anthropic_calls.jsonl 한 줄 append (function_name="generate_policy_briefing")
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

# T8/T17 — 변경 시 사전 승인. haiku·opus 사용 금지.
ANTHROPIC_MODEL = "claude-sonnet-4-20250514"
ANTHROPIC_MAX_TOKENS = 200
ANTHROPIC_TIMEOUT_SEC = 15

# T18 — anthropic_calls.jsonl 누적 (api/policy_narrative.py → repo_root/logs/...)
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ANTHROPIC_LOG_PATH = os.path.join(_REPO_ROOT, "logs", "anthropic_calls.jsonl")

HEADLINE_MAX_CHARS = 50  # 명령서: 50자 이내 1줄 시그널 톤


def generate_policy_briefing(
    policy: Dict[str, Any],
    _llm_fn: Optional[Callable[[Dict[str, Any]], Optional[Dict[str, Any]]]] = None,
) -> Optional[Dict[str, Any]]:
    """
    정책 dict → 부동산 시장 영향 1줄 한줄평.

    Args:
        policy:  {id, title, source_name, raw_text, ...} (collect_policies 산출)
        _llm_fn: 테스트 주입용. None 이면 _call_anthropic 호출.

    Returns:
        {headline: str, confidence: float, tokens_used: int} 또는 None.
            - 입력 검증 실패         → None
            - LLM 호출 실패          → None
            - 응답 파싱 실패         → None
            - 빈 headline 응답       → None
            - 50자 초과 응답         → 자동 trim 후 반환

        T2 — None 반환은 명시. mock 텍스트 절대 X.
    """
    if not policy or not isinstance(policy, dict):
        logger.error("policy_narrative: invalid input (not dict): %r", type(policy).__name__)
        return None

    title = policy.get("title")
    if not title or not str(title).strip():
        logger.error("policy_narrative: invalid input — title missing/empty (id=%r)", policy.get("id"))
        return None

    llm_call = _llm_fn or _call_anthropic
    result = llm_call(policy)
    if result is None:
        return None  # 실패 로그는 _call_anthropic 안에서 남김

    headline_raw = str(result.get("headline") or "").strip()
    if not headline_raw:
        logger.error("policy_narrative: empty headline from LLM")
        return None

    headline = headline_raw[:HEADLINE_MAX_CHARS]

    raw_conf = result.get("confidence")
    if isinstance(raw_conf, (int, float)):
        confidence = max(0.0, min(1.0, float(raw_conf)))
    else:
        # 응답에 confidence 없거나 비정상 → 0.6 (sonnet 기본 신뢰도)
        # 임의 상수 X 정책: default 임을 명시 + 로그.
        logger.warning(
            "policy_narrative: missing/invalid confidence in LLM response (%r) — defaulting 0.6",
            raw_conf,
        )
        confidence = 0.6

    return {
        "headline": headline,
        "confidence": confidence,
        "tokens_used": int(result.get("tokens_used") or 0),
    }


def _call_anthropic(policy: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """T17 — claude-sonnet-4-20250514 호출. 실패 시 None + 명시 로그 (T9)."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("policy_narrative: ANTHROPIC_API_KEY missing — LLM skip")
        return None

    try:
        import anthropic
    except ImportError:
        logger.error("policy_narrative: anthropic SDK not installed")
        return None

    try:
        client = anthropic.Anthropic(api_key=api_key, timeout=ANTHROPIC_TIMEOUT_SEC)
    except Exception as e:
        logger.error("policy_narrative: anthropic client init failed: %s", e)
        return None

    prompt = _build_prompt(policy)

    try:
        msg = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=ANTHROPIC_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as e:
        logger.error("policy_narrative: anthropic call failed: %s", e)
        return None

    in_toks = int(getattr(msg.usage, "input_tokens", 0) or 0)
    out_toks = int(getattr(msg.usage, "output_tokens", 0) or 0)
    _log_anthropic_call(in_toks, out_toks)

    text = msg.content[0].text if getattr(msg, "content", None) else ""
    parsed = _parse_response(text)
    if parsed is None:
        logger.error("policy_narrative: response parse failed: %r", text[:200])
        return None

    parsed["tokens_used"] = in_toks + out_toks
    return parsed


def _build_prompt(policy: Dict[str, Any]) -> str:
    title = (policy.get("title") or "").strip()
    body = (policy.get("raw_text") or "")[:1000]
    source = policy.get("source_name") or "정부"

    return (
        "다음 한국 부동산 정책 발표에 대한 시장 영향을 한 줄 시그널로 요약하라.\n"
        "조건:\n"
        f"  - headline 은 {HEADLINE_MAX_CHARS}자 이내 한 문장.\n"
        "  - 사실 단순 요약 X. 매수/매도 압력·수급/금리/규제 충격 등 시그널 톤.\n"
        "  - 예측·전망 어조 (예: '~할 가능성', '~로 전환되는 구간').\n\n"
        f"출처: {source}\n"
        f"제목: {title}\n"
        f"본문: {body}\n\n"
        "응답은 오직 JSON object 하나:\n"
        "{\n"
        f'  "headline": "{HEADLINE_MAX_CHARS}자 이내 한 줄 시그널",\n'
        '  "confidence": 0.0~1.0\n'
        "}"
    )


def _parse_response(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    if "headline" not in obj:
        return None
    return obj


def _log_anthropic_call(input_tokens: int, output_tokens: int) -> None:
    """T18 — logs/anthropic_calls.jsonl 한 줄 append."""
    try:
        os.makedirs(os.path.dirname(ANTHROPIC_LOG_PATH), exist_ok=True)
        line = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "model": ANTHROPIC_MODEL,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "function_name": "generate_policy_briefing",
        }
        with open(ANTHROPIC_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.error("policy_narrative: anthropic log write failed: %s", e)
