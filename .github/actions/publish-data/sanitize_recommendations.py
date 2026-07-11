#!/usr/bin/env python3
"""publish-data: recommendations.json 공개 발행본 held-2027 자체 점수·산식·LLM 서술 strip.

원본 data/recommendations.json(내부 파이프라인·비공개 소비)은 건드리지 않고, _public_dist 발행
복사본에서만 crown-jewel 키를 제거한다. 공개 Blob = 팩트 + 뉴스 + recommendation/consensus 만 노출.

배경(2026-07-10): recommendations.json 이 raw 로 공개 Blob 발행되며 brain_score·score_breakdown
(가중치 실값)·ai_verdict 등 자체 산식이 직접 fetch 로 노출 → RULE 7(점수 2027 held) + 유리박스
화이트리스트 위반. 공개 소비자(PublicNewsTab=뉴스, StockDetailPanel/USDetailHub=recommendation+
consensus+팩트)가 strip 대상 키를 전혀 쓰지 않음을 사전 검증(파손 0) 후 도입.

⚠️ consensus / analyst_consensus / recommendation 은 여기서 제거하지 않음(별 트랙):
   - consensus = 별도 PUBLIC_CONSENSUS 게이트 + USDetailHub 렌더 정리(쟁점3/4)
   - recommendation(AVOID/BUY 문자열) = 페이지 소비 중, RULE 7 별도 검토 큐
신규 held 점수 필드 추가 시 STRIP_KEYS 갱신 또는 STRIP_PAT 로 자동 포착.
"""
from __future__ import annotations

import json
import re
import sys

# 명시 strip — 자체 점수 / 산식 분해 / ML 예측 / LLM 서술 / 내부 라우팅
STRIP_KEYS = {
    "verity_brain", "raw_brain_score", "brain_score_pre_macro", "score_breakdown",
    "ai_verdict", "safety_score", "us_fscore", "fscore_deltas", "lynch_kr",
    "timing_signal", "multi_factor", "prediction", "confidence", "backtest",
    "trade_plan", "gold_insight", "silver_insight", "macro_multiplier",
    "quant_factors", "overrides_applied", "quadrant_info", "value_chain",
    "external_risk", "commodity_margin", "niche_data", "insider_sentiment",
    "social_sentiment", "equity_research_brief", "_gemini_model", "rec_price",
    "account_route",
}
# 패턴 백스톱 — 미래 추가 점수/등급/판정 필드 누출 방지 (consensus/recommendation/팩트 미포착)
STRIP_PAT = re.compile(r"brain|score_break|verdict|fscore|lynch", re.IGNORECASE)


def _sanitize_rec(rec: dict) -> dict:
    return {k: v for k, v in rec.items()
            if k not in STRIP_KEYS and not STRIP_PAT.search(k)}


def main(path: str) -> int:
    try:
        with open(path, "r", encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"sanitize_recommendations: 로드 실패({e}) — 원본 유지, skip")
        return 0

    stripped_total = 0
    n_recs = 0
    if isinstance(doc, list):
        recs = doc
    elif isinstance(doc, dict) and isinstance(doc.get("recommendations"), list):
        recs = doc["recommendations"]
    elif isinstance(doc, dict):
        # ticker-keyed dict {TICKER:{...}} — 값이 rec dict 면 sanitize (fail-CLOSED, IP 누출 방지).
        # 🚨 형식 미인지로 skip = fail-open = held 점수 raw 발행 = 스크립트 존재 이유 위배.
        recs = None
        for k, v in list(doc.items()):
            if isinstance(v, dict):
                before = len(v)
                doc[k] = _sanitize_rec(v)
                stripped_total += before - len(doc[k])
                n_recs += 1
    else:
        print("sanitize_recommendations: list/dict 아님 — 원본 유지, skip")
        return 0

    if recs is not None:
        for i, r in enumerate(recs):
            if isinstance(r, dict):
                before = len(r)
                recs[i] = _sanitize_rec(r)
                stripped_total += before - len(recs[i])
        n_recs = len(recs)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))

    print(f"sanitize_recommendations: {n_recs} recs · held/IP 키 {stripped_total}개 strip 완료")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: sanitize_recommendations.py <path/to/recommendations.json>")
        sys.exit(1)
    sys.exit(main(sys.argv[1]))
