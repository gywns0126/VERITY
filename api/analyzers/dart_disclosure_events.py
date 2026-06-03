"""
dart_disclosure_events — DART 공시 리스트에서 near-term 코퍼레이트 액션 이벤트 탐지.

2026-06-04 정보 심화 (DART 2차 원문 후속). VERITY 는 서술 데이터(밸류·수급·재무)는
풍부하나 "곧 가격을 움직일 이벤트" 가 얇다. 특히 개미가 blindside 당하는 것 —
유상증자(희석 충격) / 정정공시(부실 경영) / 불성실공시 / 회생·감자(distress).

기존 DartScout.fetch_disclosures(list.json, report_nm) 재사용 — **키워드 분류만**
(Gemini 불필요, 비용 0). related-party 와 달리 시점 이벤트라 최근 window(기본 90일).

🚨 관측 only: dart_disclosure_events 데이터 필드로만 부착. scored risk_flags 미주입
(auto_avoid→Brain 점수 영향 = RULE 7). 점수 반영은 N 누적 후 사전등록 + PM 승인.
CB/BW 희석은 fetch_cb_bw 가 이미 담당 → 여기선 주식 발행 희석(유상증자) 중심.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# report_nm 키워드 → 이벤트 카테고리. severity 높을수록 위험.
_DILUTION_KW = ("유상증자", "제3자배정", "주주배정", "증자결정", "신주발행")
_CORRECTION_KW = ("정정",)  # [기재정정]/[첨부정정]/…정정 prefix·포함
_UNFAITHFUL_KW = ("불성실공시", "공시번복", "공시불이행")
_DISTRESS_KW = ("회생절차", "파산", "영업정지", "감자결정", "관리종목", "상장폐지", "거래정지")


def classify_disclosures(disclosures: List[Dict[str, Any]], window_days: int = 90) -> Dict[str, Any]:
    """공시 리스트(report_nm 포함) → 이벤트 분류. 순수 함수(I/O 없음, 완전 테스트 가능)."""
    dilution: List[str] = []
    distress: List[str] = []
    correction = 0
    unfaithful = False

    for d in disclosures or []:
        nm = str(d.get("report_nm") or "")
        dt = str(d.get("rcept_dt") or "")
        tag = f"{nm} ({dt})" if dt else nm
        if any(k in nm for k in _DILUTION_KW):
            dilution.append(tag)
        if any(k in nm for k in _DISTRESS_KW):
            distress.append(tag)
        if any(k in nm for k in _CORRECTION_KW):
            correction += 1
        if any(k in nm for k in _UNFAITHFUL_KW):
            unfaithful = True

    # severity: distress 있으면 high / 유상증자·불성실 medium / 정정多 low~medium
    if distress:
        severity = "high"
    elif dilution or unfaithful or correction >= 3:
        severity = "medium"
    elif correction >= 1:
        severity = "low"
    else:
        severity = "none"

    parts = []
    if distress:
        parts.append(f"distress {len(distress)}건")
    if dilution:
        parts.append(f"희석(유상증자) {len(dilution)}건")
    if unfaithful:
        parts.append("불성실공시")
    if correction:
        parts.append(f"정정공시 {correction}건")
    summary = " / ".join(parts) if parts else "특이 이벤트 없음"

    return {
        "dilution_events": dilution[:5],
        "distress_events": distress[:5],
        "correction_count": correction,
        "unfaithful_disclosure": unfaithful,
        "event_count": len(dilution) + len(distress) + correction + (1 if unfaithful else 0),
        "severity": severity,
        "summary": summary,
        "window_days": window_days,
    }


def scan_disclosure_events(
    stocks_dict: Dict[str, Any], window_days: int = 90,
) -> Dict[str, Dict[str, Any]]:
    """KR 종목별 최근 공시 이벤트 스캔. fetch_disclosures(DART list.json) 재사용.

    캐시 없음 — 이벤트는 시점성이라 매 full run fresh fetch (LLM 0, DART list 콜만).
    """
    from datetime import timedelta
    from api.config import now_kst

    out: Dict[str, Dict[str, Any]] = {}
    end_dt = now_kst()
    bgn = (end_dt - timedelta(days=window_days)).strftime("%Y%m%d")
    end = end_dt.strftime("%Y%m%d")
    scanned = flagged = 0

    for ticker, stock_data in stocks_dict.items():
        corp_code = stock_data.get("corp_code")
        if not corp_code:
            continue
        try:
            from api.collectors.DartScout import fetch_disclosures
            disclosures = fetch_disclosures(corp_code, bgn, end)
        except Exception as e:
            logger.warning("[disclosure_events] fetch 실패(%s): %s", ticker, str(e)[:60])
            continue
        ev = classify_disclosures(disclosures, window_days=window_days)
        ev["ticker"] = ticker
        out[ticker] = ev
        scanned += 1
        if ev["severity"] in ("high", "medium"):
            flagged += 1

    logger.info("[disclosure_events] 스캔 %d / 이벤트 %d", scanned, flagged)
    return out
