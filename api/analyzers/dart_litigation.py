"""
dart_litigation — 사업보고서/재무제표 주석 "소송·우발부채·제재" → 잠재손실 위험 분석.

2026-06-06 DART 2차 원문 심화. distress(회생·파산, dart_disclosure_events)가 못 잡는
영역 = 진행 중 소송의 *규모*·우발채무·약정·제재. 충당부채로 아직 인식 안 된 잠재 손실은
재무제표 표면에 안 드러나므로 원문 주석을 LLM 으로 구조화. 한국 공시 특유 영역
(글로벌 LLM·일반 개인이 체계적으로 못 추출) = VERITY 해자(한국 1차자료 깊이).

흐름 (dart_related_party 와 동형):
  1. DartScout 가 _extract_section_from_rcept 에 additive 로 넣은 litigation_text 사용
     (같은 document 라 추가 DART fetch 0).
  2. Gemini Flash → JSON (response_mime_type + robust parse + transient 503 retry → Pro fallback).
  3. 캐시 — {ticker: {bsns_year: 분석결과}} (사업보고서 연 1회 → 월 ~$0.002).

🚨 관측 only (v0): 데이터 필드 + litigation red_flag 만. Brain 점수 미반영
   (RULE 7 — 점수 반영은 N 누적 후 사전등록 + PM 승인). field_coverage "DART한국" 보강.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any, Dict, Optional

from api.config import DATA_DIR, GEMINI_API_KEY, GEMINI_MODEL_DEFAULT, GEMINI_MODEL_CRITICAL, now_kst

logger = logging.getLogger(__name__)

CACHE_PATH = os.path.join(DATA_DIR, "dart_litigation_cache.json")
MIN_RAW_TEXT_LENGTH = 200
MAX_TEXT_FOR_AI = 30000

PROMPT_TEMPLATE = """아래는 {company_name}의 공시 원문 중 "소송·우발부채·약정·제재" 관련 섹션입니다.

진행 중인 소송, 우발부채(충당부채로 미인식된 잠재 손실), 중요 제재를 분석하세요.
다른 텍스트 없이 JSON 만 출력:

{{
  "litigation_risk_score": 0~100 정수 (높을수록 위험),
  "severity": "low" | "medium" | "high",
  "pending_litigation": [{{"counterparty": "상대방", "claim_amount": "청구금액(원문 표기)", "issue": "쟁점 요약"}}],
  "contingent_liabilities": ["우발부채·지급보증·약정 요약 1", "..."],
  "material_sanctions": ["제재·과징금·시정명령 요약 1", "..."],
  "summary": "한 줄 요약"
}}

판단 기준:
- 청구금액이 자기자본/시총 대비 큰 소송 = 위험 ↑ (패소 시 손실 규모)
- 다수의 진행 중 소송 / 반복되는 제재 = 위험 ↑
- 대규모 지급보증·우발채무가 재무제표 본문에 미반영 = 위험 ↑ (숨은 레버리지)
- 통상적 소액 분쟁·종결 임박·승소 가능성 높음 = 낮음
- 소송·우발부채 거의 없음 = low
- pending_litigation / contingent_liabilities / material_sanctions 각 최대 5개
- 금액은 원문 표기 그대로 (임의 환산·생성 금지). 원문에 없으면 빈 배열.

소송·우발부채 본문:
{raw_text}
"""


def _is_transient(exc: Exception) -> bool:
    msg = str(exc).lower()
    if any(m in msg for m in ("401", "403", "404", "permission", "quota exceeded",
                              "api_key", "invalid argument")):
        return False
    return any(m in msg for m in ("503", "unavailable", "rate limit", "rate_limit",
                                  "timeout", "deadline exceeded", "internal",
                                  "resource exhausted"))


def _extract_json(text: str) -> dict:
    """서론 prose / 코드펜스 / 후행 텍스트 내성 (2026-06-03 gemini 서론 drift 교훈)."""
    t = (text or "").strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", t, re.DOTALL)
    if m:
        t = m.group(1).strip()
    start, end = t.find("{"), t.rfind("}")
    if start != -1 and end > start:
        t = t[start:end + 1]
    return json.loads(t)


def _call_once(client, model: str, prompt: str) -> Dict[str, Any]:
    response = client.models.generate_content(
        model=model, contents=prompt,
        config={"response_mime_type": "application/json"},
    )
    return _extract_json((response.text or "").strip())


def _analyze(raw_text: str, company_name: str) -> Optional[Dict[str, Any]]:
    """Gemini Flash → JSON. transient 503 retry → Pro fallback (dart_related_party 정합)."""
    if not GEMINI_API_KEY:
        logger.warning("[litigation] GEMINI_API_KEY 미설정")
        return None
    try:
        from google import genai
        client = genai.Client(api_key=GEMINI_API_KEY)
    except Exception as e:
        logger.warning("[litigation] genai client 실패: %s", e)
        return None

    prompt = PROMPT_TEMPLATE.format(company_name=company_name, raw_text=raw_text[:MAX_TEXT_FOR_AI])
    # 1) Flash 즉시 → 2) Flash 3s backoff(transient) → 3) Pro 8s backoff(transient)
    for attempt, (model, wait) in enumerate(
            [(GEMINI_MODEL_DEFAULT, 0), (GEMINI_MODEL_DEFAULT, 3), (GEMINI_MODEL_CRITICAL, 8)]):
        if wait:
            time.sleep(wait)
        try:
            return _call_once(client, model, prompt)
        except Exception as e:
            if not _is_transient(e) or attempt == 2:
                logger.warning("[litigation] 분석 실패(%s): %s", company_name, str(e)[:80])
                return None
    return None


def _load_cache() -> Dict[str, Any]:
    if os.path.exists(CACHE_PATH):
        try:
            with open(CACHE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            pass
    return {"updated_at": None, "by_ticker": {}}


def _save_cache(cache: Dict[str, Any]) -> None:
    cache["updated_at"] = now_kst().isoformat()
    tmp = CACHE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    os.replace(tmp, CACHE_PATH)


def analyze_all_litigation(
    stocks_dict: Dict[str, Any], auto_fetch_missing: bool = True,
) -> Dict[str, Dict[str, Any]]:
    """stocks dict 일괄 소송·우발부채 분석.

    litigation_text 우선순위: (1) stock_data.business_facilities_raw.litigation_text,
    (2) auto_fetch_missing 시 corp_code 로 DartScout 자체 fetch (business 흐름이 raw 를
    writeback 안 하므로 — dart_related_party 정합).

    Returns: {ticker: {litigation_risk_score, severity, pending_litigation, ...}}.
    """
    cache = _load_cache()
    by_ticker: Dict[str, Any] = cache.get("by_ticker", {})
    out: Dict[str, Dict[str, Any]] = {}
    new_count = cached_count = skipped = 0

    for ticker, stock_data in stocks_dict.items():
        bsns_year = str(stock_data.get("bsns_year") or "")
        company_name = stock_data.get("name", ticker)
        corp_code = stock_data.get("corp_code")

        ticker_cache = by_ticker.get(ticker, {})
        cached = ticker_cache.get(bsns_year)
        if cached and cached.get("litigation_risk_score") is not None:
            out[ticker] = cached
            cached_count += 1
            continue

        bf = stock_data.get("business_facilities_raw") or {}
        lit_text = bf.get("litigation_text") if isinstance(bf, dict) else None
        if (not lit_text or len(lit_text) < MIN_RAW_TEXT_LENGTH) and auto_fetch_missing and corp_code:
            try:
                from api.collectors.DartScout import fetch_business_facilities_raw
                r = fetch_business_facilities_raw(corp_code, bsns_year)
                lit_text = (r or {}).get("litigation_text", "")
            except Exception as e:
                logger.warning("[litigation] fetch 실패(%s): %s", company_name, str(e)[:60])
                lit_text = ""
        if not lit_text or len(lit_text) < MIN_RAW_TEXT_LENGTH:
            out[ticker] = {"ticker": ticker, "_skip_reason": "no_litigation_text"}
            skipped += 1
            continue

        result = _analyze(lit_text, company_name)
        if not result or result.get("litigation_risk_score") is None:
            out[ticker] = {"ticker": ticker, "_skip_reason": "ai_fail"}
            skipped += 1
            continue

        result["ticker"] = ticker
        result["bsns_year"] = bsns_year
        result["analyzed_at"] = now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00")
        out[ticker] = result
        ticker_cache[bsns_year] = result
        by_ticker[ticker] = ticker_cache
        new_count += 1

    if new_count:
        cache["by_ticker"] = by_ticker
        _save_cache(cache)

    logger.info("[litigation] 신규 %d / 캐시 %d / skip %d", new_count, cached_count, skipped)
    return out
