"""earnings_surprise — Earnings Surprise / PEAD 관측 신호 (SHADOW only, Phase 1a US).

스펙: docs/earnings_surprise_pead_spec_v0_2026_06_19.md (사전등록 v0, 2026-06-19).

🚨 SHADOW ONLY — brain 점수/등급/추천 입력 0 (brain_input=False, weight 0 park 안 함).
   N>=50 + market별 IC 유의(+1d~+20d 부호 일관 |NW-t|>=2) + PM 사전등록 1회 전까지 verdict 무영향 (RULE 7).

Phase 1a (2026-06-29): **US earnings surprise 캡처만**.
   KR(영업이익 분기 서프라이즈)은 ConsensusScout 추정치가 연간(E)-only → DART 분기 actual 과
   period mismatch 로 막힘 (annual est ÷ quarterly actual = 무의미). 순이익 추정 필드도 부재.
   KR 신호 정의(연간추정 vs 분기actual 정합 방법) = PM 결정 큐. 본 모듈 KR 경로 미구현.

2단계 채점 (스펙 §4): ① 발표 감지 시 event append(forward=null) ② forward eval cron 이
   +1/+5/+20/+60 영업일 도달 시 forward_return 채움 (Phase 1b — 별도 cron, prediction_scoring 동형).
신규 산식 0 — surprise_pct = finnhub surprisePercent 그대로 (재구축 금지, 스펙 §3).

배선: fair_value_gap 관측 동형 = candidates 순회 → jsonl append → summary 반환.
   (스펙 §5 의 "portfolio weight-0 park" 은 fair_value_gap 실제엔 없음 — jsonl append-only 패턴 채택.)
"""
from __future__ import annotations

import json
import os
from datetime import datetime, date, timedelta
from typing import Any, Dict, List, Optional

from api.config import DATA_DIR, now_kst

SHADOW_OUT = os.path.join(DATA_DIR, "observations", "earnings_surprise.jsonl")

# forward drift 측정 윈도 (영업일). 스펙 §2 측정 윈도.
_FORWARD_HORIZONS: Dict[str, int] = {"d1": 1, "d5": 5, "d20": 20, "d60": 60}

# site/PM 노출 시 병기 의무 (스펙 §8).
_CAVEAT = (
    "관측-only 가설, N<50 점수 미반영(brain_input=0, weight 0). "
    "KR=영업이익 기반 / US=EPS 기반 → 혼재, market별 분리 해석. Phase 1a=US-only "
    "(KR Naver 컨센서스 연간추정 → 분기 join 막힘, PM 결정 대기). "
    "forward_return survivorship: prediction_scoring 상폐 종결 재사용(단일조건 한계). "
    "wire=market별 N>=50 IC 유의(+1d~+20d 부호 일관 |NW-t|>=2)+PM 사전등록 1회."
)


def _add_business_days(start: date, n: int) -> date:
    """start 로부터 n 영업일 후(주말만 스킵, 휴장일 미반영 — v0 근사).
    실제 forward 채점은 eval_date 최근접 price snapshot 으로 하므로 휴장일 정합은 그 단계에서 흡수."""
    d = start
    added = 0
    while added < n:
        d = d + timedelta(days=1)
        if d.weekday() < 5:  # 토(5)/일(6) 제외
            added += 1
    return d


def _load_seen_keys() -> set:
    """기존 trail 에서 (ticker, report_quarter) dedup 키 — 분기당 1회만 append (중복 차단, 스펙 §3)."""
    seen: set = set()
    if not os.path.exists(SHADOW_OUT):
        return seen
    try:
        with open(SHADOW_OUT, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                for ev in rec.get("events", []):
                    t = str(ev.get("ticker", "")).strip()
                    q = str(ev.get("report_quarter", "")).strip()
                    if t and q:
                        seen.add((t, q))
    except Exception:
        pass
    return seen


def normalize_us_surprise(stock: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """stock["earnings_surprises"] (finnhub_client.get_earnings_surprises, 최근 4분기) →
    가장 최근 발표 1건의 event schema. 추정 부재/surprise None → None (산입 제외, 스펙 §3)."""
    rows = stock.get("earnings_surprises")
    if not isinstance(rows, list) or not rows:
        return None
    valid = [r for r in rows if isinstance(r, dict) and r.get("period")]
    if not valid:
        return None
    latest = max(valid, key=lambda r: str(r.get("period", "")))  # period=YYYY-MM-DD, 최신 분기
    est = latest.get("estimate")
    sp = latest.get("surprise_pct")
    if est in (None, 0) or sp is None:  # est 0/None → null 처리 (스펙 §3 산입 제외)
        return None
    ticker = str(stock.get("ticker") or stock.get("symbol") or "").strip()
    if not ticker:
        return None
    announce = str(latest.get("period", "")).strip()
    try:
        adate = datetime.strptime(announce[:10], "%Y-%m-%d").date()
    except Exception:
        return None
    ep = stock.get("price")
    if ep is None:
        ep = stock.get("current_price")
    if ep is None:
        ep = stock.get("close")
    fwd_dates = {k: _add_business_days(adate, n).isoformat() for k, n in _FORWARD_HORIZONS.items()}
    return {
        "ticker": ticker,
        "market": "US",
        "report_quarter": announce,   # US: finnhub period(분기 기준일)을 분기키로 사용
        "announce_date": announce,
        "surprise_pct": round(float(sp), 2),
        "metric": "eps",
        "est_source": "finnhub",
        "actual_source": "finnhub",
        "entry_price": float(ep) if isinstance(ep, (int, float)) else None,
        "forward_eval_dates": fwd_dates,   # Phase 1b 채점이 도달 판정에 사용
        "forward": {k: None for k in _FORWARD_HORIZONS},  # Phase 1b 가 채움
    }


def run_shadow(stocks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """신규 US 발표 감지 → 1 라인 append(events[]). (ticker, report_quarter) dedup.
    관측-only(shadow=True, brain_input=False). 반환 = 요약 dict."""
    seen = _load_seen_keys()
    events: List[Dict[str, Any]] = []
    skipped = 0
    for st in (stocks or []):
        if not isinstance(st, dict):
            continue
        ev = normalize_us_surprise(st)
        if not ev:
            continue
        key = (ev["ticker"], ev["report_quarter"])
        if key in seen:
            skipped += 1
            continue
        seen.add(key)
        events.append(ev)
    if events:
        entry = {
            "ts_kst": now_kst().isoformat(),
            "shadow": True,
            "brain_input": False,
            "caveat": _CAVEAT,
            "events": events,
        }
        try:
            os.makedirs(os.path.dirname(SHADOW_OUT), exist_ok=True)
            with open(SHADOW_OUT, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass
    return {"new_events": len(events), "skipped_seen": skipped, "universe": len(stocks or [])}
