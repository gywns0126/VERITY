#!/usr/bin/env python3
"""publish-data: recommendations.json 공개 발행본 held-2027 자체 점수·산식·LLM 서술 strip.

원본 data/recommendations.json(내부 파이프라인·비공개 소비)은 건드리지 않고, _public_dist 발행
복사본에서만 crown-jewel 키를 제거한다. 공개 Blob = 팩트 + 뉴스 + recommendation/consensus 만 노출.

배경(2026-07-10): recommendations.json 이 raw 로 공개 Blob 발행되며 brain_score·score_breakdown
(가중치 실값)·ai_verdict 등 자체 산식이 직접 fetch 로 노출 → RULE 7(점수 2027 held) + 유리박스
화이트리스트 위반. 공개 소비자(PublicNewsTab=뉴스, StockDetailPanel/USDetailHub=recommendation+
consensus+팩트)가 strip 대상 키를 전혀 쓰지 않음을 사전 검증(파손 0) 후 도입.

🚨 2026-08-18 — consensus / analyst_consensus / analyst_report_summary **strip 추가** (PM 결정
"애널리스트는 공개용으로 안올리는걸로. 백엔드에만 냅둬서 오퍼레이터 산식에만 넣는 걸로").

종전 이 자리에는 "consensus 는 별도 PUBLIC_CONSENSUS 게이트로 미룬다" 고 적혀 있었다.
**그 게이트는 만들어지지 않았다** — 저장소 전체에서 `PUBLIC_CONSENSUS` 의 유일한 출현이
이 주석 자신이었다(2026-08-18 grep). 그 사이 결정이 갈렸다:
  · 2026-07-10 PM — `us_analyst_consensus.json` 재배포 금지 (파일 봉인 8/02)
  · 2026-07-21 PM — `consensus_data.json` = "KR 브로커 목표가·투자의견, 동일 법적 class" (봉인 8/16)
  · 그런데 **같은 숫자가 이 경로로는 계속 나갔다** — 라이브 blob 실측(8/18):
    target_price 63 · kis_target_price 18 · investment_opinion 56 · single_consensus_target_price 56.
    파일만 막고 통로를 안 막은 형태다.

소비 파손 0 확인 — public-probe 전수 grep 에서 `consensus.<필드>` 접근 **0건**.
`PublicStockReport.tsx:4935` 는 destructure 후 useMemo 의존성 배열에만 있고 렌더 경로가 없다.
`:402/548/564` 는 SAMPLE 상수(하드코딩 문자열)라 발행본과 무관하다.

원본 `data/` 는 그대로 둔다 — 오퍼레이터·백엔드 산식은 계속 쓴다. 막는 것은 **발행**뿐이다.

⚠️ recommendation(AVOID/BUY 문자열) = 페이지 소비 중, RULE 7 별도 검토 큐
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
    # 2026-08-03 display_verdict 게이트 — LLM 합의 원본(참고 관측)은 비공개.
    # display_verdict 자체는 STRIP_PAT(r"verdict") 자동 포착. recommendation 문자열만 공개.
    "analyst_view",
    # 🚨 2026-08-21 — 이월 자기신고 스탬프(api/main.py MERGE). 오퍼레이터 진단용이다.
    #   `frozen_fields` 가 verity_brain·overrides_applied·multi_factor 를 **이름으로**
    #   담는데 셋 다 이미 STRIP_KEYS 대상 = 값은 막고 구조 이름은 새는 형태가 된다.
    #   공개 Blob 계약은 "팩트+뉴스+recommendation+consensus" 이고 이월 여부는 그 밖이다.
    "_carried",
    # 2026-08-27 — stock_filter 내부 분류 플래그. 공개 소비자는 없고 진단에만 사용한다.
    "_turnaround",
    # 2026-08-04 신호 필터 F2·F3 진단 flag (PREREG_SIGNAL_FILTERS) — 자체 산식 파생, 오퍼레이터 전용.
    "value_guards",
    # 🚨 2026-08-18 애널리스트 컨센서스 3키 (PM 결정 — 공개 발행 금지, 백엔드 유지).
    #   consensus = 목표가·투자의견·실적추정 (KR 브로커 + KIS). 7/21 판정의 동일 법적 class.
    #   analyst_consensus = rec 최상위 사본(20건). equity_research_brief 안의 것은 그 키가
    #     이미 STRIP_KEYS 에 있어 함께 빠진다.
    #   analyst_report_summary = recent_reports[].target_price (7건) 보유.
    "consensus", "analyst_consensus", "analyst_report_summary",
    # 2026-08-20 — yfinance 컨센서스 오퍼레이터 주입분(api/main.py). 원본 파일이 manifest
    #   `banned` 이므로 파생 필드도 같은 class 다. 이름이 달라 위 키에 안 걸린다.
    "analyst_consensus_yf",
}
# 패턴 백스톱 — 미래 추가 점수/등급/판정 필드 누출 방지 (consensus/recommendation/팩트 미포착)
STRIP_PAT = re.compile(r"brain|score_break|verdict|fscore|lynch", re.IGNORECASE)


# sentiment 내부 슬림 (2026-08-04, PM "낭비는 확실히 아껴") — 공개 소비 실측:
# PublicNewsTab 등이 쓰는 하위 필드 = headline_count·top_headline_links 뿐.
# detail(13소스 세부, 항목당 ~2.7KB) = 공개 소비 0 + 내부 신호 구조 노출(봉인 정합) → strip.
# top_headlines(links 와 중복 텍스트) = 소비 0 → strip. 전송(br/gzip) 기준 파일 ~15-20% 절감.
_SENTIMENT_KEEP = {"score", "positive", "negative", "neutral", "headline_count", "top_headline_links"}


def _sanitize_rec(rec: dict) -> dict:
    out = {k: v for k, v in rec.items()
           if k not in STRIP_KEYS and not STRIP_PAT.search(k)}
    s = out.get("sentiment")
    if isinstance(s, dict):
        out["sentiment"] = {k: v for k, v in s.items() if k in _SENTIMENT_KEEP}
    return out


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
