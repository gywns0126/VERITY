"""
policy_classifier.py — 정책 분류기 (P2 Step 2)

입력: policy dict (collect_policies 산출)
출력: {category, stage, affected_regions, confidence, method, keywords_matched, llm}

흐름:
  ① 1차 키워드 매칭 (policy_keywords.keyword_matches)
     → 매칭 ≥ KEYWORD_SHORT_CIRCUIT_MIN_MATCHES 개 + 단일 카테고리 ≥ 90% 집중
       → 1차 종결 (T19 — LLM skip)
  ② 2차 LLM 호출 (claude-haiku-4-5-20251001 — T17)
     → 모호하거나 1차 신뢰도 낮을 때만
     → 호출 시 logs/anthropic_calls.jsonl 한 줄 기록 (T18)
  ③ LLM 실패 → 1차 결과 + 페널티 confidence 로 폴백 (T1, T9)

거짓말 트랩 컴플라이언스:
    T1  fabricate X — LLM 실패 시 가짜 응답 X. 1차 폴백 또는 no_match.
    T4  confidence 임의 상수 X — 매칭 수·집중도·LLM 응답 confidence 산식 도출.
    T8  LLM 모델 변경 X — claude-haiku-4-5-20251001 상수 박힘 (T17).
    T9  silent 실패 X — 모든 실패 logger.error.
    T17 모델 = claude-haiku-4-5-20251001 (변경 시 사전 승인)
    T18 anthropic_calls.jsonl 누적
    T19 1차 종결 임계 (skip 비율 측정 가능)
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from api.analyzers.policy_keywords import CATEGORY_KEYWORDS, keyword_matches

logger = logging.getLogger(__name__)

# T17 — 변경 시 사전 승인 (opus·sonnet 사용 금지)
ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"
ANTHROPIC_MAX_TOKENS = 300
ANTHROPIC_TIMEOUT_SEC = 15

# T18 — anthropic_calls.jsonl 누적 경로 (repo_root/logs/...)
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ANTHROPIC_LOG_PATH = os.path.join(_REPO_ROOT, "logs", "anthropic_calls.jsonl")

# T19 — 1차 종결 임계
KEYWORD_SHORT_CIRCUIT_MIN_MATCHES = 3
KEYWORD_SHORT_CIRCUIT_CONCENTRATION = 0.9

VALID_CATEGORIES = set(CATEGORY_KEYWORDS.keys())  # 8 카테고리

# specific vs fallback 분리 — catalyst 는 다른 7개 매칭 0건일 때만 사용.
# 사유: catalyst 의 일반 단어 ('주택','부동산','아파트') 가 specific 카테고리에 leak 시
#       concentration 깎아먹어 LLM 호출 빈도 ↑. 사용자 결정 보강 #6 정신 (T19 효과 보장).
SPECIFIC_CATEGORIES = ["regulation", "supply", "tax", "loan", "redev", "rental", "anomaly"]
FALLBACK_CATEGORY = "catalyst"

# 자치구 추출 — 서울 25구 + 광역시·도 17개
_SEOUL_GU = (
    "강남|서초|송파|성동|용산|마포|영등포|광진|성북|중랑|동대문|종로"
    "|강서|양천|구로|금천|동작|관악|서대문|은평|노원|도봉|강북|강동"
)
_REGION_PREFIX = "서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충북|충남|전북|전남|경북|경남|제주"
_GU_PATTERN = re.compile(
    rf"(?:({_REGION_PREFIX})\s?)?({_SEOUL_GU})구?",
)


def classify(
    policy: Dict[str, Any],
    _llm_fn: Optional[callable] = None,
) -> Dict[str, Any]:
    """
    정책을 카테고리·stage·affected_regions·confidence 로 분류.

    Args:
        policy:  collect_policies() 산출 dict.
        _llm_fn: 테스트 주입용. None 이면 _classify_with_llm 호출.

    Returns:
        dict {
            category:         str ∈ VALID_CATEGORIES,
            stage:            int 0~4,
            affected_regions: list[str],
            confidence:       float 0.0~1.0,
            method:           "keywords" | "llm" | "keywords_fallback" | "no_match",
            keywords_matched: dict {category: [kw, ...]},
            llm:              dict | None,
        }
    """
    matches = keyword_matches(policy)

    specific_counts = {c: len(matches[c]) for c in SPECIFIC_CATEGORIES}
    specific_total = sum(specific_counts.values())
    fallback_count = len(matches[FALLBACK_CATEGORY])

    if specific_total == 0 and fallback_count == 0:
        logger.warning(
            "policy_classifier: 0 keyword matches for policy id=%s",
            policy.get("id"),
        )
        return _no_match_result()

    if specific_total > 0:
        # specific 매칭 우선. catalyst 매칭은 분모에서 제외 (T19 효과 보장).
        top_cat = max(SPECIFIC_CATEGORIES, key=lambda c: specific_counts[c])
        top_count = specific_counts[top_cat]
        denom = specific_total
    else:
        top_cat = FALLBACK_CATEGORY
        top_count = fallback_count
        denom = fallback_count

    concentration = top_count / denom if denom else 0.0

    affected = _extract_regions(policy)

    # T19 — 1차 종결
    if (top_count >= KEYWORD_SHORT_CIRCUIT_MIN_MATCHES
            and concentration >= KEYWORD_SHORT_CIRCUIT_CONCENTRATION):
        return {
            "category": top_cat,
            "stage": _stage_from_keywords(top_cat, top_count),
            "affected_regions": affected,
            "confidence": _keyword_confidence(top_count, concentration),
            "method": "keywords",
            "keywords_matched": matches,
            "llm": None,
        }

    # 2차 — LLM
    llm_call = _llm_fn or _classify_with_llm
    llm_result = llm_call(policy)

    if llm_result is None:
        # T1·T9 — fabricate X, silent X (실패 로그는 _classify_with_llm 안에서)
        return {
            "category": top_cat,
            "stage": _stage_from_keywords(top_cat, top_count),
            "affected_regions": affected,
            "confidence": round(_keyword_confidence(top_count, concentration) * 0.7, 3),
            "method": "keywords_fallback",
            "keywords_matched": matches,
            "llm": None,
        }

    cat = llm_result.get("category", top_cat)
    if cat not in VALID_CATEGORIES:
        logger.warning(
            "policy_classifier: invalid LLM category %r → fallback to top_cat=%r",
            cat, top_cat,
        )
        cat = top_cat

    return {
        "category": cat,
        "stage": int(llm_result.get("stage", _stage_from_keywords(top_cat, top_count))),
        "affected_regions": llm_result.get("affected_regions") or affected,
        "confidence": float(llm_result.get("confidence", 0.6)),
        "method": "llm",
        "keywords_matched": matches,
        "llm": llm_result.get("_meta"),
    }


# ─── helpers ───

def _no_match_result() -> Dict[str, Any]:
    return {
        "category": "catalyst",
        "stage": 0,
        "affected_regions": [],
        "confidence": 0.0,
        "method": "no_match",
        "keywords_matched": {cat: [] for cat in CATEGORY_KEYWORDS},
        "llm": None,
    }


def _keyword_confidence(top_count: int, concentration: float) -> float:
    """
    T4 — 산식 도출 (임의 상수 X).
        base = min(0.9, 0.5 + 0.1 * top_count)
        결과 = base * (0.4 + 0.6 * concentration)
    예: top_count=3, concentration=1.0  →  0.8 * 1.0 = 0.800
        top_count=4, concentration=0.9  →  0.9 * 0.94 = 0.846
    """
    base = min(0.9, 0.5 + 0.1 * top_count)
    return round(base * (0.4 + 0.6 * concentration), 3)


def _stage_from_keywords(category: str, match_count: int) -> int:
    """
    1차 stage — 카테고리 위험도 + 매칭 수 기반.
    anomaly·regulation 은 시장 영향 큼 (기본 3). supply·redev 는 보수적 (1).
    매칭 ≥5 시 +1 (cap 4).
    """
    base = {
        "anomaly": 3,
        "regulation": 3,
        "tax": 2,
        "loan": 2,
        "rental": 2,
        "supply": 1,
        "redev": 1,
        "catalyst": 1,
    }.get(category, 1)
    if match_count >= 5:
        base = min(4, base + 1)
    return base


def _extract_regions(policy: Dict[str, Any]) -> List[str]:
    """제목 + 본문에서 (광역+자치구) 패턴 추출. 중복 제거 + 입력 순서 유지."""
    text = (policy.get("title") or "") + " " + (policy.get("raw_text") or "")
    found = _GU_PATTERN.findall(text)
    out: List[str] = []
    for region, gu in found:
        canonical = (f"{region} {gu}구" if region else f"{gu}구").strip()
        if canonical not in out:
            out.append(canonical)
    return out


def _classify_with_llm(policy: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    T17 — claude-haiku-4-5-20251001 호출.
    실패 시 None + 명시 로그 (T9). 호출 성공 시 anthropic_calls.jsonl 기록 (T18).
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("policy_classifier: ANTHROPIC_API_KEY missing — LLM skip")
        return None

    try:
        import anthropic
    except ImportError:
        logger.error("policy_classifier: anthropic SDK not installed")
        return None

    try:
        client = anthropic.Anthropic(api_key=api_key, timeout=ANTHROPIC_TIMEOUT_SEC)
    except Exception as e:
        logger.error("policy_classifier: anthropic client init failed: %s", e)
        return None

    prompt = _build_prompt(policy)

    try:
        msg = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=ANTHROPIC_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as e:
        logger.error("policy_classifier: anthropic call failed: %s", e)
        return None

    in_toks = int(getattr(msg.usage, "input_tokens", 0) or 0)
    out_toks = int(getattr(msg.usage, "output_tokens", 0) or 0)
    _log_anthropic_call(in_toks, out_toks)

    text = msg.content[0].text if getattr(msg, "content", None) else ""
    parsed = _parse_llm_response(text)
    if parsed is None:
        logger.error("policy_classifier: LLM response parse failed: %r", text[:200])
        return None

    parsed["_meta"] = {
        "model": ANTHROPIC_MODEL,
        "input_tokens": in_toks,
        "output_tokens": out_toks,
    }
    return parsed


def _build_prompt(policy: Dict[str, Any]) -> str:
    title = policy.get("title", "")
    body = (policy.get("raw_text") or "")[:1000]
    return (
        "다음 한국 부동산 정책을 분류하라. 응답은 오직 JSON object 하나.\n\n"
        f"제목: {title}\n"
        f"본문: {body}\n\n"
        "응답 형식:\n"
        "{\n"
        '  "category": "regulation|supply|tax|loan|redev|rental|anomaly|catalyst",\n'
        '  "stage": 0~4 (시장 영향: 0=없음, 1=관망, 2=주의, 3=경계, 4=충격),\n'
        '  "affected_regions": ["서울 강남구", ...] 또는 [],\n'
        '  "confidence": 0.0~1.0\n'
        "}"
    )


def _parse_llm_response(text: str) -> Optional[Dict[str, Any]]:
    """JSON object 1개 추출 — markdown fence·앞뒤 prose 허용."""
    if not text:
        return None
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def _log_anthropic_call(input_tokens: int, output_tokens: int) -> None:
    """T18 — logs/anthropic_calls.jsonl 한 줄 append."""
    try:
        os.makedirs(os.path.dirname(ANTHROPIC_LOG_PATH), exist_ok=True)
        line = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "model": ANTHROPIC_MODEL,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "function_name": "policy_classifier.classify",
        }
        with open(ANTHROPIC_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.error("policy_classifier: anthropic log write failed: %s", e)
