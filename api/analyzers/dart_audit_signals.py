"""
dart_audit_signals — 감사보고서 going-concern(계속기업 불확실성) / 강조사항 탐지.

2026-06-04 정보 심화 ④. 감사의견 게이트(DartScout.check_audit)는 적정/한정만 보는데,
**계속기업 불확실성 / 강조사항**은 부도 *선행* 신호인데 구조화 API 필드가 없다 →
감사보고서 문서 키워드 스캔 (DartScout ZIP 이 본문+감사보고서 번들 시 포착).

🚨 false-positive 회피 핵심: "계속기업을 전제로 작성"은 *모든 정상 보고서* 표준 문구.
따라서 doubt 전용 구문("계속기업 관련 중요한 불확실성" = 불확실성 있을 때만 쓰는
KICAR 표준 heading)만 매칭. 정상 boilerplate 는 안 잡는다.

관측 only: dart_audit_signals 데이터 필드만. scored 미반영 = RULE 7.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

# doubt 전용 — 계속기업 불확실성이 *있을 때만* 쓰이는 구문 (정상 boilerplate 제외).
_GC_DOUBT = (
    "계속기업 관련 중요한 불확실성",
    "계속기업가정의 불확실성",
    "계속기업 가정의 불확실성",
    "계속기업으로서의 존속능력에 유의적 의문을 초래",
    "계속기업으로서의 존속능력에 중대한 의문",
    "계속기업으로서의 존속능력에 대한 유의적 의문",
)
_EMPHASIS_HDR = "강조사항"


def detect_going_concern(text: str) -> Dict[str, Any]:
    """감사보고서 텍스트 → going-concern doubt / 강조사항. 순수 함수(완전 테스트 가능).

    🚨 "계속기업을 전제로"(정상 boilerplate)는 매칭 안 함 — doubt 전용 구문만.
    """
    t = text or ""
    doubt = next((p for p in _GC_DOUBT if p in t), None)
    emphasis = _EMPHASIS_HDR in t
    snippet = ""
    if doubt:
        i = t.find(doubt)
        snippet = t[max(0, i - 40):i + 220].strip()
    severity = "high" if doubt else ("low" if emphasis else "none")
    return {
        "going_concern_doubt": bool(doubt),
        "emphasis_of_matter": emphasis,
        "severity": severity,
        "matched_phrase": doubt or "",
        "snippet": snippet,
    }


def scan_audit_signals(stocks_dict: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """KR 종목별 감사 신호 스캔. DartScout 가 business_facilities_raw 에 채운
    going_concern_* 필드 사용 (DartScout._extract_section_from_rcept 가 detect_going_concern
    호출). raw 미존재 시 corp_code 로 자체 fetch (related-party 정합).
    """
    out: Dict[str, Dict[str, Any]] = {}
    scanned = flagged = 0
    for ticker, stock_data in stocks_dict.items():
        corp_code = stock_data.get("corp_code")
        bsns_year = str(stock_data.get("bsns_year") or "")
        bf = stock_data.get("business_facilities_raw") or {}
        gc = None
        if isinstance(bf, dict) and "going_concern_doubt" in bf:
            gc = {
                "going_concern_doubt": bf.get("going_concern_doubt", False),
                "emphasis_of_matter": bf.get("emphasis_of_matter", False),
                "severity": bf.get("going_concern_severity", "none"),
                "matched_phrase": bf.get("going_concern_phrase", ""),
                "snippet": bf.get("going_concern_snippet", ""),
            }
        elif corp_code:
            try:
                from api.collectors.DartScout import fetch_business_facilities_raw
                r = fetch_business_facilities_raw(corp_code, bsns_year) or {}
                gc = {
                    "going_concern_doubt": r.get("going_concern_doubt", False),
                    "emphasis_of_matter": r.get("emphasis_of_matter", False),
                    "severity": r.get("going_concern_severity", "none"),
                    "matched_phrase": r.get("going_concern_phrase", ""),
                    "snippet": r.get("going_concern_snippet", ""),
                }
            except Exception as e:
                logger.warning("[audit_signals] fetch 실패(%s): %s", ticker, str(e)[:60])
                continue
        if gc is None:
            continue
        gc["ticker"] = ticker
        out[ticker] = gc
        scanned += 1
        if gc["severity"] in ("high", "low") and (gc["going_concern_doubt"] or gc["emphasis_of_matter"]):
            flagged += 1
    logger.info("[audit_signals] 스캔 %d / 신호 %d", scanned, flagged)
    return out
