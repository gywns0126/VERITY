"""dart_catalyst — DART 정정공시 + 주요사항 catalyst 수집.

목적:
  운영 풀 KR 종목의 직전 N일 catalyst (정정공시 / 주요사항 / 발행공시 / 지분공시) 자동 감지.
  Perplexity narrative 자동화 (별 모듈 dart_catalyst_alert.py) 의 input.

DART pblntf_ty 분류 (OpenDART 사양):
  A: 정기공시 (사업보고서 등) — catalyst 아님, 제외
  B: 주요사항보고 ← M&A, 자기주식, 배당, 영업양수도 등 = catalyst
  C: 발행공시       ← 신주발행, CB/BW = catalyst
  D: 지분공시       ← 5% 보고, 임원 등 = catalyst (sentiment 영향)
  E: 기타공시
  F: 외부감사 관련
  G: 펀드공시
  H: 자산유동화
  I: 거래소공시
  J: 공정위공시

정정공시 (corr_yn="Y") = 사후 정정 = restatement risk (audit trail).

산식 동결 가드 ([[project_verity_backtest_sprint]] B 옵션 6월 중순 진입):
  본 모듈 = brain 산식 영향 X, 별 reporting / alert 만. 정합.

CROSS: [[feedback_no_new_llm_narrative_features]] — 본 모듈은 본인 자산 강화 path (운영
풀 catalyst 자동 감지 + 운영 trail 누적). 신규 narrative 컴포넌트 X. Perplexity 호출은
별 모듈에서.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from api.collectors.DartScout import _call
from api.config import DATA_DIR, now_kst

logger = logging.getLogger(__name__)

OUTPUT_PATH = os.path.join(DATA_DIR, "dart_catalyst_alerts.jsonl")

# pblntf_ty 별 catalyst 분류 (사용자 facing label)
PBLNTF_LABELS: Dict[str, str] = {
    "B": "주요사항보고",
    "C": "발행공시",
    "D": "지분공시",
}

# catalyst 강도 (사용자 PM 우선순위 — narrative 생성 trigger 임계)
CATALYST_SEVERITY: Dict[str, int] = {
    "B": 3,  # 주요사항 = HIGH (M&A, 자기주식, 배당 등)
    "C": 2,  # 발행공시 = MEDIUM (CB/BW = dilution risk)
    "D": 2,  # 지분공시 = MEDIUM (5% 변동 sentiment 영향)
    "corr": 1,  # 정정공시 = LOW (audit trail, 직접 영향 작음)
}


def _fetch_catalyst_by_type(
    corp_code: str,
    bgn_de: str,
    end_de: str,
    pblntf_ty: str,
) -> List[Dict[str, Any]]:
    """단일 pblntf_ty 의 공시 list 수집.

    Returns: list of {rcept_no, report_nm, rcept_dt, flr_nm, corr_yn}
    """
    data = _call("list.json", {
        "corp_code": corp_code,
        "bgn_de": bgn_de,
        "end_de": end_de,
        "pblntf_ty": pblntf_ty,
        "page_count": "30",
        "sort": "date",
        "sort_mth": "desc",
    })
    out: List[Dict[str, Any]] = []
    for d in data.get("list", []):
        out.append({
            "rcept_no": d.get("rcept_no", ""),
            "report_nm": d.get("report_nm", ""),
            "rcept_dt": d.get("rcept_dt", ""),
            "flr_nm": d.get("flr_nm", ""),
            "corr_yn": d.get("corr_yn", "N"),
            "pblntf_ty": pblntf_ty,
        })
    return out


def fetch_catalysts_for_stock(
    ticker: str,
    name: str,
    corp_code: str,
    lookback_days: int = 7,
) -> List[Dict[str, Any]]:
    """단일 종목의 직전 N일 catalyst events 수집.

    Returns: list of {ticker, name, rcept_no, report_nm, rcept_dt, flr_nm,
                       pblntf_ty, pblntf_label, severity, is_correction}
    """
    end_dt = now_kst().date()
    bgn_dt = end_dt - timedelta(days=lookback_days)
    end_de = end_dt.strftime("%Y%m%d")
    bgn_de = bgn_dt.strftime("%Y%m%d")

    all_events: List[Dict[str, Any]] = []
    for ty in ("B", "C", "D"):
        try:
            events = _fetch_catalyst_by_type(corp_code, bgn_de, end_de, ty)
            for e in events:
                is_corr = (e.get("corr_yn") == "Y")
                severity = CATALYST_SEVERITY.get("corr") if is_corr \
                    else CATALYST_SEVERITY.get(ty, 1)
                all_events.append({
                    "ticker": ticker,
                    "name": name,
                    "rcept_no": e["rcept_no"],
                    "report_nm": e["report_nm"],
                    "rcept_dt": e["rcept_dt"],
                    "flr_nm": e["flr_nm"],
                    "pblntf_ty": ty,
                    "pblntf_label": PBLNTF_LABELS.get(ty, ty),
                    "severity": severity,
                    "is_correction": is_corr,
                    "detected_at": now_kst().isoformat(timespec="seconds"),
                })
        except Exception as e:
            logger.warning(
                "[dart_catalyst] %s (%s) %s fetch 실패: %s",
                name, ticker, ty, str(e)[:120],
            )
    return all_events


def fetch_catalysts_for_pool(
    stocks_dict: Dict[str, Dict[str, Any]],
    lookback_days: int = 7,
) -> Dict[str, Any]:
    """운영 풀 KR 종목 batch catalyst 수집.

    Args:
        stocks_dict: {ticker6: {name, corp_code}} format (DART STEP 5.88 정합)

    Returns:
        {
          "events": [list of catalyst events],
          "stats": {"total": N, "by_ticker": {...}, "by_type": {...}, "corrections": N},
          "lookback_days": int,
          "window": {"bgn": str, "end": str},
        }
    """
    all_events: List[Dict[str, Any]] = []
    by_ticker: Dict[str, int] = {}
    by_type: Dict[str, int] = {}
    corrections = 0

    end_dt = now_kst().date()
    bgn_dt = end_dt - timedelta(days=lookback_days)

    for ticker, info in stocks_dict.items():
        name = info.get("name", ticker)
        corp_code = info.get("corp_code")
        if not corp_code:
            continue
        events = fetch_catalysts_for_stock(ticker, name, corp_code, lookback_days)
        all_events.extend(events)
        if events:
            by_ticker[ticker] = len(events)
        for e in events:
            ty = e["pblntf_ty"]
            by_type[ty] = by_type.get(ty, 0) + 1
            if e.get("is_correction"):
                corrections += 1

    return {
        "events": all_events,
        "stats": {
            "total": len(all_events),
            "by_ticker": by_ticker,
            "by_type": by_type,
            "corrections": corrections,
        },
        "lookback_days": lookback_days,
        "window": {
            "bgn": bgn_dt.strftime("%Y-%m-%d"),
            "end": end_dt.strftime("%Y-%m-%d"),
        },
        "fetched_at": now_kst().isoformat(timespec="seconds"),
    }


def persist_catalyst_alerts(events: List[Dict[str, Any]]) -> int:
    """events 를 data/dart_catalyst_alerts.jsonl 에 append.

    중복 회피 (rcept_no 기준) — 같은 공시 다시 처리 X.
    Returns: 신규 append 한 entry 수.
    """
    if not events:
        return 0

    # 기존 rcept_no 로드 (dedupe)
    seen: set = set()
    if os.path.isfile(OUTPUT_PATH):
        try:
            with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        d = json.loads(line.strip())
                        rno = d.get("rcept_no")
                        if rno:
                            seen.add(rno)
                    except json.JSONDecodeError:
                        continue
        except OSError as e:
            logger.warning("[dart_catalyst] 기존 file 읽기 실패: %s", e)

    new_count = 0
    try:
        with open(OUTPUT_PATH, "a", encoding="utf-8") as f:
            for e in events:
                if e.get("rcept_no") in seen:
                    continue
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
                new_count += 1
    except OSError as e:
        logger.error("[dart_catalyst] persist 실패: %s", e)

    return new_count
