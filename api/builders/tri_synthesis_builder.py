"""tri_synthesis_builder — 3종 LLM 종합 사전계산 (비용 한정, 주 1회 cron).

🚨 비용 설계 (PM 2026-08-01 "비용 너무 커지면 안됨"):
  - LLM 호출은 **여기 한 곳**에서만. 온디맨드 실시간 호출 없음(비용 폭주 방지, v2 하드캡 이연).
  - 대상 = 추천 상위 TRI_MAX_TICKERS(기본 25) 종목만 (brain_score 순).
  - fingerprint 캐시 = 사실 안 바뀐 종목 재호출 스킵 (tri_llm_synthesis 내장).
  - 주 1회 cadence (workflow cron). 실측 종목당 ~$0.05 → 25×주1 ≈ $5/월 예측가능.
  - 예상 비용 로그 출력(관측). 캡 초과 절대 없음(슬라이스 상한).

산출: data/tri_synthesis.json — 오퍼레이터 전용(Brain grounding). 공개 blob 아님 → private 업로드
  (upload_operator_data_to_supabase 경로) + authed /api/admin?type=tri_synthesis 서빙.
  RULE 7: LLM 의견 provenance 분리·Brain 가설 라벨 유지(tri_llm_synthesis 산출 그대로).
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List

from api.config import DATA_DIR, now_kst

logger = logging.getLogger(__name__)

OUTPUT_PATH = os.path.join(DATA_DIR, "tri_synthesis.json")
RECS_PATH = os.path.join(DATA_DIR, "recommendations.json")

# 비용 상한 — 한 run 에서 3-LLM 을 도는 최대 종목 수. env override 가능.
TRI_MAX_TICKERS = int(os.environ.get("TRI_MAX_TICKERS", "25"))
# 종목당 대략 단가(USD, 관측 로그용). Perplexity+Gemini+Claude opus-5 effort-low.
_EST_COST_PER_TICKER = 0.05


def _brain_score(rec: Dict[str, Any]) -> float:
    vb = rec.get("verity_brain") or {}
    for v in (vb.get("brain_score"), rec.get("brain_score"), rec.get("raw_brain_score")):
        if isinstance(v, (int, float)):
            return float(v)
    return -1.0


def _select_tickers(recs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """brain_score 상위 TRI_MAX_TICKERS. 상한 = 비용 하드 캡."""
    ranked = sorted(recs, key=_brain_score, reverse=True)
    return ranked[:TRI_MAX_TICKERS]


def build() -> Dict[str, Any]:
    now = now_kst()
    if not os.path.isfile(RECS_PATH):
        return {"_meta": {"generated_at": now.isoformat(), "error": "recommendations.json 부재"}, "syntheses": {}}
    try:
        with open(RECS_PATH, "r", encoding="utf-8") as f:
            recs = json.load(f) or []
    except (OSError, json.JSONDecodeError) as e:
        return {"_meta": {"generated_at": now.isoformat(), "error": f"recs 로드 실패: {e}"}, "syntheses": {}}

    from api.intelligence.tri_llm_synthesis import synthesize

    picks = _select_tickers(recs)
    syntheses: Dict[str, Any] = {}
    computed = 0
    cache_hits = 0
    errors = 0

    for rec in picks:
        ticker = (rec.get("ticker") or "").strip().upper()
        if not ticker:
            continue
        name = rec.get("name") or ticker
        try:
            r = synthesize(ticker, name, use_cache=True)   # fingerprint 캐시 = 재호출 스킵
        except Exception as e:
            logger.warning("[tri_synthesis] %s 실패: %s", ticker, e)
            errors += 1
            continue
        if r.get("_cache") == "hit":
            cache_hits += 1
        elif (r.get("sources") or {}).get("claude", {}).get("content"):
            computed += 1
        else:
            errors += 1
        # 저장본 = provenance + trail + disclosure (LLM 의견 분리, RULE 7). 내부 캐시필드 제거.
        syntheses[ticker] = {k: v for k, v in r.items() if k != "_cache"}

    est_cost = round(computed * _EST_COST_PER_TICKER, 2)
    meta = {
        "generated_at": now.isoformat(),
        "universe": "추천 상위 brain_score",
        "max_tickers": TRI_MAX_TICKERS,
        "n_syntheses": len(syntheses),
        "computed_this_run": computed,
        "cache_hits": cache_hits,
        "errors": errors,
        "est_cost_usd_this_run": est_cost,
        "note": "3종 LLM 종합(Perplexity 신선사실·Gemini 구조화·Claude opus-5 종합). "
                "LLM 의견=의견(provenance 분리), Brain=가설(N<252). 채점 입력 아님. 오퍼레이터 전용.",
    }
    return {"_meta": meta, "syntheses": syntheses}


def main() -> int:
    result = build()
    try:
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, separators=(",", ":"))
    except OSError as e:
        logger.error("[tri_synthesis] 쓰기 실패: %s", e)
        return 1
    m = result["_meta"]
    print(f"[tri_synthesis] {m.get('n_syntheses')}건 (신규 {m.get('computed_this_run')} · "
          f"캐시 {m.get('cache_hits')} · 오류 {m.get('errors')}) · 예상비용 ${m.get('est_cost_usd_this_run')} "
          f"→ {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
