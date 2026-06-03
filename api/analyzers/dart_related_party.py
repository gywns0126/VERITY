"""
dart_related_party — 사업보고서 "대주주 등과의 거래내용 / 특수관계자 거래" → 터널링 위험 분석.

2026-06-03 DART 2차 원문 심화 (v0). 한국 특유 지배구조 red flag = 터널링
(일감몰아주기·부당지원·사익편취). 글로벌 LLM·일반 개인이 한국 공시에서 체계적으로
못 잡는 영역 = VERITY 해자(한국 1차자료 깊이).

흐름:
  1. DartScout 가 business_facilities_raw 에 additive 로 넣은 related_party_text 사용
     (같은 document 라 추가 DART fetch 0).
  2. Gemini 로 터널링 위험 JSON 분석 (response_mime_type=application/json + robust parse +
     transient 503 retry → Pro fallback, 2026-06-03 공개리포트 503 교훈 반영).
  3. 캐시 — {ticker: {bsns_year: 분석결과}} (사업보고서 연 1회 → 월 ~$0.002).

🚨 관측 only (v0): 데이터 필드 + governance red_flag 만. Brain 점수 미반영
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

CACHE_PATH = os.path.join(DATA_DIR, "dart_related_party_cache.json")
MIN_RAW_TEXT_LENGTH = 300
MAX_TEXT_FOR_AI = 30000

PROMPT_TEMPLATE = """아래는 {company_name}의 사업보고서 "대주주 등과의 거래내용 / 특수관계자 거래" 섹션 원문입니다.

한국 기업 지배구조 관점에서 터널링(일감몰아주기·부당지원·사익편취) 위험을 분석하세요.
다른 텍스트 없이 JSON 만 출력:

{{
  "related_party_risk_score": 0~100 정수 (높을수록 위험),
  "severity": "low" | "medium" | "high",
  "tunneling_flags": ["구체 의심 정황 1", "..."],
  "major_transactions": ["상대방·유형·규모 요약 1", "..."],
  "summary": "한 줄 요약"
}}

판단 기준:
- 대주주/오너 일가 개인회사로의 매출·매입 집중 = 일감몰아주기 의심 (위험 ↑)
- 무담보·저리 자금 대여 / 지급보증 = 부당지원 의심 (위험 ↑)
- 거래 규모가 매출 대비 과대 = 위험 ↑
- 계열사 간 통상 거래·시장가 수준 = 정상 (낮음)
- 거래 내용 거의 없음 / 소규모 = low
- tunneling_flags / major_transactions 각 최대 5개

대주주 거래 본문:
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
    """Gemini Flash → JSON. transient 503 retry → Pro fallback (dart_report_analyzer 정합)."""
    if not GEMINI_API_KEY:
        logger.warning("[related_party] GEMINI_API_KEY 미설정")
        return None
    try:
        from google import genai
        client = genai.Client(api_key=GEMINI_API_KEY)
    except Exception as e:
        logger.warning("[related_party] genai client 실패: %s", e)
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
                logger.warning("[related_party] 분석 실패(%s): %s", company_name, str(e)[:80])
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


def analyze_all_related_party(
    stocks_dict: Dict[str, Any], auto_fetch_missing: bool = True,
) -> Dict[str, Dict[str, Any]]:
    """stocks dict 일괄 터널링 분석.

    related_party_text 우선순위: (1) stock_data.business_facilities_raw.related_party_text,
    (2) auto_fetch_missing 시 corp_code 로 DartScout 자체 fetch (business 흐름이 raw 를
    writeback 안 하므로 — dart_report_analyzer.analyze_business_report 정합).

    Returns: {ticker: {related_party_risk_score, severity, tunneling_flags, ...}}.
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
        if cached and cached.get("related_party_risk_score") is not None:
            out[ticker] = cached
            cached_count += 1
            continue

        bf = stock_data.get("business_facilities_raw") or {}
        rp_text = bf.get("related_party_text") if isinstance(bf, dict) else None
        if (not rp_text or len(rp_text) < MIN_RAW_TEXT_LENGTH) and auto_fetch_missing and corp_code:
            try:
                from api.collectors.DartScout import fetch_business_facilities_raw
                r = fetch_business_facilities_raw(corp_code, bsns_year)
                rp_text = (r or {}).get("related_party_text", "")
            except Exception as e:
                logger.warning("[related_party] fetch 실패(%s): %s", company_name, str(e)[:60])
                rp_text = ""
        if not rp_text or len(rp_text) < MIN_RAW_TEXT_LENGTH:
            out[ticker] = {"ticker": ticker, "_skip_reason": "no_related_party_text"}
            skipped += 1
            continue

        result = _analyze(rp_text, company_name)
        if not result or result.get("related_party_risk_score") is None:
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

    logger.info("[related_party] 신규 %d / 캐시 %d / skip %d", new_count, cached_count, skipped)
    return out
