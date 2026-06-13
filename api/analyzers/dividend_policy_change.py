"""
dividend_policy_change — KR 배당 *정책 변화 이벤트* 탐지 (1차자료 해자 심화).

2026-06-13 신설. VERITY 의 한국 1차자료(DART) 해자 확장 — 대형사가 안 건드리는 영역.
기존 dart_disclosure_events 는 "곧 가격을 움직일 공시 이벤트"(유상증자/distress)를 잡고,
dividend_kr 수집기는 배당 *금액*을 기록하나, 둘 다 배당 **정책의 방향 전환**
(개시 / 삭감 / 중단)을 이벤트로 분류하지 않았다. 이게 갭.

배당 정책 변화 = 경영진 신호:
  - 개시(initiation): 무배당 → 배당 시작 = positive (현금흐름 자신감, 주주환원 전환)
  - 삭감(cut): 직전 대비 일정 비율 이상 감액 = caution (distress 동형 약신호)
  - 중단(omission): 배당 → 무배당 = distress 동형 (강한 약신호)
  - 무변화(maintained) / 증액(raise) = neutral~positive

데이터 source = 기존 dividends_kr.json history (DART/pykrx 이미 수집). 추가 DART 콜 0 —
배당 *정책 변화*는 history 의 year-over-year 비교로 도출(순수 함수). dart_audit_signals /
dart_disclosure_events 와 동일 패턴(pure classify + scan wrapper).

🚨 관측 only (RULE 7): dividend_policy_change 데이터 필드로만 부착. scored risk_flags
미주입 — cut/omission 약신호도 Brain 점수/verdict 에 피드백 0. 점수 반영은 N 누적 후
사전등록 + PM 승인. 임계(cut_ratio)는 강제 *원칙값*(절반=대표적 정책 후퇴 라인) — 자유
파라미터 fit surface 아님. 매핑 변경은 사전등록 의무.

spec: docs/dividend_policy_change_spec_v0_2026_06_13.md.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 삭감 판정 비율 — 직전 유효배당 대비 이 비율 이상 감액 시 'cut'.
# 강제 원칙값: 0.5(반토막) = 대표적 배당정책 후퇴 라인(자유 fit 아님, 변경=사전등록).
CUT_RATIO = 0.5
# 증액 판정 비율 — 직전 대비 이 비율 이상 증액 시 'raise'(positive). 강제 원칙값.
RAISE_RATIO = 0.5


def _effective_amount(rec: Dict[str, Any]) -> Optional[float]:
    """한 배당 레코드의 '유효 주당 배당액'. confirmed 우선, 없으면 announced.
    음수/0/결손은 None(=무배당 또는 미확정) 으로 정규화."""
    for key in ("confirmed_amount_per_share", "announced_amount_per_share"):
        v = rec.get(key)
        if v is None:
            continue
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if f > 0:
            return f
    return None


def _annual_series(history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """배당 history → 연도별 1점 시계열(연말배당 기준 정규화).

    같은 연도 복수 레코드(중간/분기 포함)는 유효액 합산 — 연간 총배당으로 비교.
    🚨 명시적 무배당(amount=0)도 *점으로 보존* — 레코드는 있으나 유효액이 없는 연도는
    "그 해 배당 0" 으로 기록(개시/중단 전이 판별에 필수). _meta / ex_date 결손은 제외.
    반환은 연도 오름차순.
    """
    by_year: Dict[int, float] = {}
    for rec in history or []:
        if not isinstance(rec, dict) or rec.get("_meta"):
            continue
        ex = str(rec.get("ex_date") or "")
        if len(ex) < 4 or not ex[:4].isdigit():
            continue
        year = int(ex[:4])
        amt = _effective_amount(rec)  # None = 그 레코드는 무배당(0 으로 정규화)
        by_year[year] = by_year.get(year, 0.0) + (amt or 0.0)
    return [{"year": y, "amount": round(by_year[y], 4)} for y in sorted(by_year)]


def classify_dividend_history(history: List[Dict[str, Any]]) -> Dict[str, Any]:
    """배당 history → 정책 변화 이벤트 분류. 순수 함수(I/O 없음, 완전 테스트 가능).

    직전 유효 연도 → 최신 유효 연도 전이를 본다 (year-over-year):
      - prev 무배당, curr 배당     → initiation (positive)
      - prev 배당, curr 무배당     → omission   (distress 동형)
      - curr <= prev*(1-CUT_RATIO) → cut        (caution)
      - curr >= prev*(1+RAISE_RATIO)→ raise      (positive)
      - 그 외 배당 유지            → maintained  (neutral)
      - 둘 다 무배당 / 비교 불가    → none        (neutral)

    🚨 관측 only — 어떤 점수/결정에도 피드백 0 (RULE 7).
    """
    series = _annual_series(history)
    base = {
        "change_type": "none",
        "severity": "none",
        "prev_year": None,
        "prev_amount": None,
        "curr_year": None,
        "curr_amount": None,
        "change_pct": None,
        "years_observed": len(series),
        "summary": "비교 가능한 배당 이력 부족",
    }
    if len(series) < 2:
        # 단일 연도 = 개시/유지 판별 불가 (이전 baseline 없음). 관측만 누적.
        if series:
            base["curr_year"] = series[-1]["year"]
            base["curr_amount"] = series[-1]["amount"]
            base["summary"] = "단일 연도 — 정책 변화 비교 불가 (baseline 부재)"
        return base

    prev, curr = series[-2], series[-1]
    pa, ca = prev["amount"], curr["amount"]
    prev_paid = pa > 0
    curr_paid = ca > 0

    if not prev_paid and curr_paid:
        change_type, severity = "initiation", "positive"
    elif prev_paid and not curr_paid:
        change_type, severity = "omission", "high"      # 중단 = distress 동형(강 약신호)
    elif prev_paid and curr_paid and ca <= pa * (1.0 - CUT_RATIO):
        change_type, severity = "cut", "medium"         # 삭감 = caution(약 약신호)
    elif prev_paid and curr_paid and ca >= pa * (1.0 + RAISE_RATIO):
        change_type, severity = "raise", "positive"
    elif prev_paid and curr_paid:
        change_type, severity = "maintained", "none"
    else:
        change_type, severity = "none", "none"

    change_pct = None
    if prev_paid and curr_paid:
        change_pct = round((ca - pa) / pa * 100.0, 2)

    label = {
        "initiation": "배당 개시(positive)",
        "omission": "배당 중단(distress 동형)",
        "cut": f"배당 삭감 {change_pct}%" if change_pct is not None else "배당 삭감",
        "raise": f"배당 증액 {change_pct}%" if change_pct is not None else "배당 증액",
        "maintained": "배당 유지",
        "none": "특이 변화 없음",
    }[change_type]
    summary = f"{prev['year']}→{curr['year']} {label}"

    return {
        "change_type": change_type,
        "severity": severity,
        "prev_year": prev["year"],
        "prev_amount": pa,
        "curr_year": curr["year"],
        "curr_amount": ca,
        "change_pct": change_pct,
        "years_observed": len(series),
        "summary": summary,
    }


def scan_dividend_policy_changes(
    stocks_dict: Dict[str, Any], dividends_db: Optional[Dict[str, List[dict]]] = None,
) -> Dict[str, Dict[str, Any]]:
    """KR 종목별 배당 정책 변화 스캔. 기존 dividends_kr.json history 재사용 (추가 DART 콜 0).

    dividends_db 미지정 시 dividend_kr.load_dividends_db() 로 로드. 결손/예외 = graceful skip.
    """
    if dividends_db is None:
        try:
            from api.collectors.dividend_kr import load_dividends_db
            dividends_db = load_dividends_db()
        except Exception as e:
            logger.warning("[dividend_policy] DB 로드 실패: %s", str(e)[:60])
            return {}

    out: Dict[str, Dict[str, Any]] = {}
    scanned = flagged = 0
    for ticker in stocks_dict or {}:
        t6 = str(ticker).split(".")[0].zfill(6)
        history = dividends_db.get(t6) or dividends_db.get(str(ticker)) or []
        try:
            ev = classify_dividend_history(history)
        except Exception as e:
            logger.warning("[dividend_policy] 분류 실패(%s): %s", ticker, str(e)[:60])
            continue
        if ev["change_type"] == "none" and ev["years_observed"] < 2:
            continue  # baseline 부재 = 부착 안 함 (noise 회피)
        ev["ticker"] = t6
        out[t6] = ev
        scanned += 1
        if ev["severity"] in ("high", "medium", "positive"):
            flagged += 1

    logger.info("[dividend_policy] 스캔 %d / 변화 %d (관측 only)", scanned, flagged)
    return out
