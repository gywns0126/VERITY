"""
report_summarizer — 증권사 리포트 PDF → Gemini AI 요약 → 구조화 점수.

흐름:
  1. data/analyst_reports.json (ReportScout 결과) 의 리포트 list 읽음
  2. PDF URL 다운로드 (download_report_pdf 재사용)
  3. pdfplumber 로 텍스트 추출
  4. Gemini Flash 호출 (JSON 출력) → summary/target_price/opinion/sentiment 등
  5. 종목별 집계 → analyst_sentiment_score, opinion_distribution 등

출력: data/report_summaries.json

비용 관리:
  - Gemini Flash 단독 ($0.075/1M input, ~$0.0008/콜)
  - 일일 처리 cap: MAX_DAILY_REPORTS=30
  - PDF URL hash 기반 캐시 (재요약 X)
  - 이미지 기반 PDF (text < 200 chars) skip
  - PDF 본문 첫 30K chars 만 AI 입력 (토큰 비용 제어)

Brain 통합 (Phase 3 후속):
  Brain 의 fact_score 에 analyst_sentiment_score 추가 예정.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import statistics
from collections import Counter
from datetime import timedelta
from typing import Any, Dict, List, Optional

from api.config import DATA_DIR, GEMINI_API_KEY, GEMINI_MODEL_DEFAULT, now_kst
from api.collectors.ReportScout import download_report_pdf
from api.mocks import mockable

logger = logging.getLogger(__name__)

# ─── 상수 ───────────────────────────────────────────────

REPORTS_JSON = os.path.join(DATA_DIR, "analyst_reports.json")
SUMMARIES_PATH = os.path.join(DATA_DIR, "report_summaries.json")

MAX_DAILY_REPORTS = 30
MIN_TEXT_LENGTH = 200
MAX_TEXT_FOR_AI = 30000
AGGREGATION_LOOKBACK_DAYS = 7

PROMPT_TEMPLATE = """아래는 {firm} 증권사의 {company_name} 분석 리포트입니다.

다음 항목을 JSON 으로 추출하세요. 다른 텍스트 없이 JSON 만 출력:

{{
  "summary": "핵심 투자 논점 3줄 요약 (한국어, 자연스러운 문장)",
  "target_price": 90000 또는 null,
  "opinion": "매수" | "중립" | "매도" | "보유",
  "opinion_change": "상향" | "유지" | "하향" | "신규",
  "key_catalysts": ["성장 동인 1", "성장 동인 2", "성장 동인 3"],
  "key_risks": ["리스크 1", "리스크 2", "리스크 3"],
  "earnings_revision": "상향" | "유지" | "하향",
  "sentiment": 0~100 정수 (50=중립, 100=극도로 긍정)
}}

리포트 본문:
{report_text}
"""


# ─── 헬퍼 ────────────────────────────────────────────────


def _hash_url(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def _load_existing_cache() -> Dict[str, Any]:
    if os.path.exists(SUMMARIES_PATH):
        try:
            with open(SUMMARIES_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            pass
    return {"updated_at": None, "summaries": {}, "_processed_hashes": {}}


def _extract_pdf_text(pdf_path: str, max_chars: int = MAX_TEXT_FOR_AI) -> Optional[str]:
    """pdfplumber 로 PDF 텍스트 추출.

    text < MIN_TEXT_LENGTH → 이미지 기반 PDF 로 간주 → None.
    """
    try:
        import pdfplumber
        parts = []
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                t = page.extract_text() or ""
                parts.append(t)
                if sum(len(p) for p in parts) >= max_chars:
                    break
        text = "\n".join(parts).strip()
        if len(text) < MIN_TEXT_LENGTH:
            return None
        return text[:max_chars]
    except Exception as e:
        logger.warning("[PDF] 텍스트 추출 실패 %s: %s", pdf_path, e)
        return None


def _summarize_with_gemini(text: str, firm: str, company_name: str) -> Optional[Dict[str, Any]]:
    """Gemini Flash 호출 → JSON dict 반환.

    실패 (API 키 없음 / JSON 파싱 실패 / 네트워크) → None.
    """
    if not GEMINI_API_KEY:
        logger.warning("[Gemini] GEMINI_API_KEY 미설정 — 요약 스킵")
        return None
    try:
        from google import genai
        client = genai.Client(api_key=GEMINI_API_KEY)
        prompt = PROMPT_TEMPLATE.format(
            firm=firm or "?",
            company_name=company_name or "?",
            report_text=text[:MAX_TEXT_FOR_AI],
        )
        response = client.models.generate_content(
            model=GEMINI_MODEL_DEFAULT,
            contents=prompt,
        )
        raw = (response.text or "").strip()
        # JSON 코드펜스 제거
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        return json.loads(raw)
    except Exception as e:
        logger.warning("[Gemini] 요약 실패 %s/%s: %s",
                       firm, company_name, str(e)[:120])
        return None


# ─── 단일 리포트 + 집계 ───────────────────────────────


def summarize_report(report: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """단일 리포트 요약. 캐시 확인은 호출자 책임.

    Returns:
      None — PDF URL 없거나 다운로드 실패
      {"_skip_reason": ...} — 텍스트 추출 실패 또는 AI 실패
      summary dict — 정상 (firm/date/pdf_url/ticker 메타 포함)
    """
    pdf_url = report.get("pdf_url")
    if not pdf_url:
        return None
    pdf_path = download_report_pdf(pdf_url)
    if not pdf_path:
        return None
    text = _extract_pdf_text(pdf_path)
    if not text:
        return {"_skip_reason": "image_pdf_or_short"}
    summary = _summarize_with_gemini(
        text, report.get("firm", "?"), report.get("company_name", "?"),
    )
    if not summary:
        return {"_skip_reason": "ai_fail"}
    summary["firm"] = report.get("firm")
    summary["date"] = report.get("date")
    summary["pdf_url"] = pdf_url
    summary["ticker"] = report.get("ticker")
    return summary


def aggregate_reports_for_stock(
    ticker: str, summaries: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """단일 종목의 최근 N일 리포트 → 집계 통계.

    Returns:
      {analyst_sentiment_score, avg_target_price, target_price_dispersion,
       opinion_distribution, revision_ratio, report_count, recent_reports[]}
    """
    if not summaries:
        return {}

    sentiments = [s.get("sentiment") for s in summaries
                  if isinstance(s.get("sentiment"), (int, float))]
    targets = [s.get("target_price") for s in summaries
               if isinstance(s.get("target_price"), (int, float)) and s["target_price"] > 0]
    opinions = [s.get("opinion") for s in summaries if s.get("opinion")]
    revisions = [s.get("opinion_change") for s in summaries if s.get("opinion_change")]

    revision_up = sum(1 for r in revisions if r == "상향")
    revision_down = sum(1 for r in revisions if r == "하향")
    revision_total = revision_up + revision_down

    return {
        "analyst_sentiment_score": round(statistics.mean(sentiments), 1) if sentiments else None,
        "avg_target_price": round(statistics.mean(targets), 0) if targets else None,
        "target_price_dispersion": round(statistics.stdev(targets), 0) if len(targets) >= 2 else 0,
        "opinion_distribution": dict(Counter(opinions)),
        "revision_ratio": round(revision_up / revision_total, 2) if revision_total else None,
        "report_count": len(summaries),
        "recent_reports": [{
            "firm": s.get("firm"),
            "date": s.get("date"),
            "summary": s.get("summary", ""),
            "target_price": s.get("target_price"),
            "opinion": s.get("opinion"),
            "sentiment": s.get("sentiment"),
        } for s in summaries[:5]],
    }


# ─── 메인 진입점 ────────────────────────────────────────


@mockable("gemini.report_summarizer")
def run_report_summarizer(
    max_daily: int = MAX_DAILY_REPORTS,
    lookback_days: int = AGGREGATION_LOOKBACK_DAYS,
) -> Dict[str, Any]:
    """analyst_reports.json 읽고 신규 요약 + 종목별 집계 + atomic 저장.

    Returns: payload (status / summaries / stats / _processed_hashes)

    VERITY_MODE=dev/staging 시 @mockable 로 빈 summaries 반환 (Gemini 비용 0).
    """
    if not os.path.exists(REPORTS_JSON):
        logger.warning("[Summarizer] %s 미존재 — ReportScout 먼저 실행 필요", REPORTS_JSON)
        return {"status": "no_reports"}

    with open(REPORTS_JSON, "r", encoding="utf-8") as f:
        reports_data = json.load(f)
    company_reports = reports_data.get("company_reports", [])
    if not company_reports:
        return {"status": "empty_input"}

    cache = _load_existing_cache()
    processed_hashes: Dict[str, Any] = cache.get("_processed_hashes", {})

    today = now_kst().date()
    cutoff = (today - timedelta(days=lookback_days)).strftime("%Y-%m-%d")

    # 신규 후보 — 캐시 미존재 + PDF URL 보유 + lookback 내
    candidates = []
    for r in company_reports:
        if r.get("date", "") < cutoff:
            continue
        url = r.get("pdf_url")
        if not url:
            continue
        h = _hash_url(url)
        if h in processed_hashes:
            continue
        candidates.append((h, r))

    candidates.sort(key=lambda x: x[1].get("date", ""), reverse=True)
    to_process = candidates[:max_daily]

    print(f"[Summarizer] 신규 {len(to_process)}/{len(candidates)} 리포트 "
          f"(cap {max_daily}, lookback {lookback_days}d)")

    new_summaries = 0
    skipped = 0
    for i, (h, r) in enumerate(to_process, 1):
        ticker_label = r.get("ticker") or "------"
        company = (r.get("company_name") or "?")[:14]
        firm = (r.get("firm") or "?")[:8]
        print(f"  [{i}/{len(to_process)}] {r.get('date')} {ticker_label} "
              f"{company:14s} ({firm:8s}) ...", end=" ", flush=True)

        result = summarize_report(r)
        if not result:
            print("FAIL (no PDF)")
            processed_hashes[h] = {"status": "no_pdf", "date": r.get("date")}
            skipped += 1
            continue
        if "_skip_reason" in result:
            print(f"SKIP ({result['_skip_reason']})")
            processed_hashes[h] = {"status": result["_skip_reason"], "date": r.get("date")}
            skipped += 1
            continue
        processed_hashes[h] = {
            "status": "summarized",
            "date": r.get("date"),
            "ticker": r.get("ticker"),
            "summary_data": result,
        }
        new_summaries += 1
        print(f"OK (sent={result.get('sentiment')}, opin={result.get('opinion')})")

    # 종목별 집계 — lookback 내 summarized 만
    by_ticker: Dict[str, List[Dict[str, Any]]] = {}
    for h, info in processed_hashes.items():
        if info.get("status") != "summarized":
            continue
        if info.get("date", "") < cutoff:
            continue
        ticker = info.get("ticker")
        if not ticker:
            continue
        by_ticker.setdefault(ticker, []).append(info["summary_data"])

    aggregated: Dict[str, Any] = {}
    for ticker, summaries in by_ticker.items():
        summaries.sort(key=lambda s: s.get("date", ""), reverse=True)
        aggregated[ticker] = aggregate_reports_for_stock(ticker, summaries)

    payload = {
        "updated_at": now_kst().isoformat(),
        "lookback_days": lookback_days,
        "summaries": aggregated,
        "_processed_hashes": processed_hashes,
        "stats": {
            "total_reports_in_input": len(company_reports),
            "new_summaries_this_run": new_summaries,
            "skipped_this_run": skipped,
            "tickers_aggregated": len(aggregated),
            "total_processed_lifetime": len(processed_hashes),
        },
    }

    tmp = SUMMARIES_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp, SUMMARIES_PATH)

    return payload


# ─── CLI ──────────────────────────────────────────────


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    import sys
    cap = int(sys.argv[1]) if len(sys.argv) > 1 else MAX_DAILY_REPORTS
    result = run_report_summarizer(max_daily=cap)
    print()
    print("=" * 60)
    print("Stats")
    print("=" * 60)
    if result.get("stats"):
        for k, v in result["stats"].items():
            print(f"  {k:>30}: {v}")
        print()
        print(f"집계된 종목 ({len(result['summaries'])}):")
        for tk, agg in list(result["summaries"].items())[:8]:
            print(f"  {tk}: sentiment={agg.get('analyst_sentiment_score')}, "
                  f"target_avg={agg.get('avg_target_price')}, "
                  f"reports={agg.get('report_count')}, "
                  f"opinion={agg.get('opinion_distribution')}")
    print()
    print(f"저장: {SUMMARIES_PATH}")
