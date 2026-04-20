"""
dart_report_analyzer — DART 사업보고서 "II. 사업의 내용" → Gemini AI 분석 → 사업 건전성 점수.

흐름:
  1. DartScout.fetch_business_facilities_raw() 의 raw_text (사업의 내용 섹션 원문)
  2. Gemini Flash 로 JSON 분석
     (business_health_score 0-100 + moat_indicators + risk_factors
      + growth_drivers + capex_direction + employee_trend + one_line_summary)
  3. 캐시 — {ticker: {bsns_year: 분석결과}}

비용 관리:
  - 사업보고서는 연 1회 발행 → (ticker, bsns_year) 단위 캐시
  - 같은 키 재호출 X — 매년 1회 × 30종목 = 월 ~2.5콜 (~$0.002/월)
  - raw_text < 500 chars 면 skip
  - 본문 첫 40K chars 만 AI 입력 (사업보고서가 길어서 cut)

Brain 통합 (Phase 3 후속):
  fact_score 에 dart_health_score 추가 예정. moat_indicators 는 기존 _compute_moat_score 보강.
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

from api.config import DATA_DIR, GEMINI_API_KEY, GEMINI_MODEL_DEFAULT, now_kst
from api.mocks import mockable

logger = logging.getLogger(__name__)

CACHE_PATH = os.path.join(DATA_DIR, "dart_analysis_cache.json")

MIN_RAW_TEXT_LENGTH = 500
MAX_TEXT_FOR_AI = 40000  # 사업보고서는 길어서 cut. 첫 40K (보통 사업의 내용 핵심 섹션 충분)

PROMPT_TEMPLATE = """아래는 {company_name}의 사업보고서 "II. 사업의 내용" 섹션 원문입니다.

다음을 JSON으로 분석하세요. 다른 텍스트 없이 JSON 만 출력:

{{
  "business_health_score": 0~100 정수 (사업 건전성 종합 점수),
  "moat_indicators": ["경제적 해자 지표 1", "..."],
  "risk_factors": ["핵심 리스크 1", "..."],
  "growth_drivers": ["성장 동인 1", "..."],
  "capex_direction": "확대" | "유지" | "축소" | "불명",
  "employee_trend": "인력 추이 한 줄 해석",
  "one_line_summary": "사업 현황 한 줄 요약"
}}

판단 기준:
- business_health_score:
  매출 다변화·경쟁 우위·시장 성장성·리스크 종합 판단.
  매출처 집중도 높으면 감점 (단일 고객 50%↑ → -20).
  R&D 비중 높으면 가점 (산업 특성 고려).
  해외 매출 비중 확대 추세면 가점.
  소송/규제/환율/원자재 리스크 언급 많으면 감점.
- moat_indicators: 특허·시장점유율·브랜드·전환비용·네트워크 효과 등 구체 근거.
- risk_factors / growth_drivers 각 최대 5개.

사업보고서 본문:
{raw_text}
"""


# ─── 캐시 ───────────────────────────────────────────────


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


# ─── Gemini 호출 ────────────────────────────────────────


def _analyze_with_gemini(raw_text: str, company_name: str) -> Optional[Dict[str, Any]]:
    """Gemini Flash → JSON dict. 실패 시 None."""
    if not GEMINI_API_KEY:
        logger.warning("[Gemini] GEMINI_API_KEY 미설정")
        return None
    try:
        from google import genai
        client = genai.Client(api_key=GEMINI_API_KEY)
        prompt = PROMPT_TEMPLATE.format(
            company_name=company_name or "?",
            raw_text=raw_text[:MAX_TEXT_FOR_AI],
        )
        response = client.models.generate_content(
            model=GEMINI_MODEL_DEFAULT,
            contents=prompt,
        )
        raw = (response.text or "").strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        return json.loads(raw)
    except Exception as e:
        logger.warning("[Gemini] DART 분석 실패 %s: %s", company_name, str(e)[:120])
        return None


# ─── 단일 종목 분석 ────────────────────────────────────


def analyze_business_report(
    ticker: str,
    raw_text: Optional[str] = None,
    corp_code: Optional[str] = None,
    bsns_year: Optional[str] = None,
    company_name: str = "?",
) -> Dict[str, Any]:
    """단일 사업보고서 AI 분석.

    raw_text 우선. 없으면 corp_code+bsns_year 로 자동 fetch.
    raw_text < 500 chars → skip.

    Returns:
      성공: {ticker, business_health_score, moat_indicators, ..., bsns_year, analyzed_at}
      실패: {ticker, _skip_reason: "..."}
    """
    if not raw_text and corp_code:
        try:
            from api.collectors.DartScout import fetch_business_facilities_raw
            r = fetch_business_facilities_raw(corp_code, bsns_year)
            raw_text = r.get("raw_text", "")
        except Exception as e:
            logger.warning("[DART analyzer] fetch 실패 %s: %s", ticker, e)
            return {"ticker": ticker, "_skip_reason": "fetch_failed"}

    if not raw_text or len(raw_text) < MIN_RAW_TEXT_LENGTH:
        return {"ticker": ticker, "_skip_reason": "no_raw_or_too_short",
                "raw_len": len(raw_text or "")}

    result = _analyze_with_gemini(raw_text, company_name)
    if not result:
        return {"ticker": ticker, "_skip_reason": "ai_fail"}

    result["ticker"] = ticker
    result["bsns_year"] = bsns_year
    result["company_name"] = company_name
    result["analyzed_at"] = now_kst().isoformat()
    result["raw_text_chars"] = len(raw_text)
    return result


# ─── 배치 ──────────────────────────────────────────────


@mockable("gemini.dart_business_analysis")
def analyze_all_business_reports(
    stocks_dict: Dict[str, Any],
    auto_fetch_missing: bool = True,
) -> Dict[str, Dict[str, Any]]:
    """raw_data.json 의 stocks dict 일괄 분석.

    Args:
        stocks_dict: {ticker6: stock_data} — DartScout.scout_all() 결과의 "stocks" 키.
                     stock_data 에 'corp_code', 'bsns_year', 'business_facilities_raw'
                     (선택) 키 필요.
        auto_fetch_missing: True 면 raw_text 없을 때 corp_code 로 자동 fetch.

    Returns:
        {ticker6: 분석 결과} (캐시 hit + 신규 분석 모두 포함).
        분석 캐시는 data/dart_analysis_cache.json 에 atomic 저장.

    VERITY_MODE=dev/staging 시 @mockable 로 빈 results 반환 (Gemini 비용 0).
    """
    cache = _load_cache()
    by_ticker: Dict[str, Any] = cache.get("by_ticker", {})

    out: Dict[str, Dict[str, Any]] = {}
    new_count = 0
    cached_count = 0
    skipped_count = 0

    for ticker, stock_data in stocks_dict.items():
        bsns_year = str(stock_data.get("bsns_year") or "")
        company_name = stock_data.get("name", ticker)
        corp_code = stock_data.get("corp_code")

        # 캐시 확인 (ticker, bsns_year)
        ticker_cache = by_ticker.get(ticker, {})
        cached = ticker_cache.get(bsns_year)
        if cached and cached.get("business_health_score") is not None:
            out[ticker] = cached
            cached_count += 1
            continue

        # raw_text 추출 — stock_data 에 있거나 자동 fetch
        bf = stock_data.get("business_facilities_raw") or {}
        raw_text = bf.get("raw_text") if isinstance(bf, dict) else None
        if not raw_text and not auto_fetch_missing:
            out[ticker] = {"ticker": ticker, "_skip_reason": "no_raw_no_autofetch"}
            skipped_count += 1
            continue

        result = analyze_business_report(
            ticker=ticker,
            raw_text=raw_text,
            corp_code=corp_code,
            bsns_year=bsns_year,
            company_name=company_name,
        )

        if "_skip_reason" in result:
            out[ticker] = result
            # skip 도 캐시에 기록 — 같은 (ticker, year) 무한 재시도 방지
            ticker_cache[bsns_year] = result
            skipped_count += 1
        else:
            out[ticker] = result
            ticker_cache[bsns_year] = result
            new_count += 1

        by_ticker[ticker] = ticker_cache

    cache["by_ticker"] = by_ticker
    _save_cache(cache)

    return {
        "results": out,
        "stats": {
            "total": len(stocks_dict),
            "new_analyzed": new_count,
            "cache_hit": cached_count,
            "skipped": skipped_count,
        },
    }


# ─── CLI ──────────────────────────────────────────────


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--ticker":
        # 단일 종목 테스트: python -m api.analyzers.dart_report_analyzer --ticker 005930 [bsns_year]
        ticker6 = sys.argv[2]
        bsns_year = sys.argv[3] if len(sys.argv) > 3 else "2023"
        from api.collectors.dart_corp_code import get_corp_code
        from api.collectors.stock_data import ALL_STOCKS

        # ALL_STOCKS 의 KEY 는 ticker_yf (예: 005930.KS) — 6자리로 매칭
        ticker_yf = next((t for t in ALL_STOCKS if t.startswith(ticker6 + ".")), None)
        company = ALL_STOCKS.get(ticker_yf, ticker6) if ticker_yf else ticker6
        cc = get_corp_code(ticker_yf or ticker6)

        print(f"분석: {ticker6} ({company}) — {bsns_year} 사업보고서")
        result = analyze_business_report(
            ticker=ticker6, corp_code=cc, bsns_year=bsns_year, company_name=company,
        )
        print()
        print(json.dumps(result, ensure_ascii=False, indent=2)[:2000])
    else:
        # 기본: raw_data.json 일괄 처리
        raw_data_path = os.path.join(DATA_DIR, "raw_data.json")
        if not os.path.exists(raw_data_path):
            print(f"❌ {raw_data_path} 미존재 — DartScout.scout_all() 먼저 실행 필요")
            sys.exit(1)
        with open(raw_data_path) as f:
            d = json.load(f)
        stocks = d.get("stocks", {})
        print(f"입력: {len(stocks)} 종목")
        result = analyze_all_business_reports(stocks, auto_fetch_missing=True)
        print()
        print("=" * 60)
        print("Stats")
        print("=" * 60)
        for k, v in result["stats"].items():
            print(f"  {k:>15}: {v}")
        print()
        print(f"저장: {CACHE_PATH}")
