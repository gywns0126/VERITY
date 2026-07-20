#!/usr/bin/env python3
"""publish-data: equity_research 공개 발행본에서 analyst_consensus(yfinance 목표가) strip.

원본 data/equity_research/<TICKER>.json(오퍼레이터 pages/us 소비)은 무변경. _public_dist 발행
복사본에서만 analyst_consensus 를 제거한다.

배경(2026-07-21 전수감사 후속): equity_research 브리프가 무인증 공개 Blob 에 raw 발행되며
analyst_consensus(price_target_avg/high/low/median 등 yfinance 애널리스트 목표가)가 그대로 노출
= us_analyst_consensus 재배포 금지(PM 2026-07-10 확정, 유료 라이선스 전 금지·allowlist 재추가 절대금지)
위반. 소비 컴포넌트(pages/us/EquityBriefCard·USDetailHub)는 analyst_consensus? 를 optional 렌더 →
부재 시 무손상(사전검증: EquityBriefCard.tsx:91 optional, USDetailHub.tsx:343 `|| {}` fallback).

주: brief_verdict(오퍼레이터 등급) / earnings_highlights.eps_estimate(과거 실적 서프라이즈) 는
공개-vs-오퍼레이터 경계 결정 큐 — 이번 strip 미포함. 신규 컨센서스류 키 추가 시 STRIP_KEYS 갱신.
"""
from __future__ import annotations

import json
import sys

# us_analyst_consensus 재배포 금지 (2026-07-10 PM 확정)
STRIP_KEYS = {"analyst_consensus"}


def main(path: str) -> int:
    try:
        with open(path, "r", encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        # fail-safe: 형식 미인지·로드 실패 시 원본 유지(공개본이 이미 복사됨) — 단 로그 명시.
        print(f"sanitize_equity_brief: 로드 실패({e}) — skip")
        return 0
    if not isinstance(doc, dict):
        print("sanitize_equity_brief: dict 아님 — skip")
        return 0

    stripped = [k for k in STRIP_KEYS if k in doc]
    for k in stripped:
        doc.pop(k, None)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))

    tail = path.rsplit("/", 1)[-1]
    print(f"sanitize_equity_brief: {tail} — strip {stripped or '(none)'}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: sanitize_equity_brief.py <path/to/brief.json>")
        sys.exit(1)
    sys.exit(main(sys.argv[1]))
