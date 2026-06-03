"""
필드 커버리지 측정 — 데이터 품질 = breadth × 정확성 × 신선도 × **커버리지**.

배경 (2026-06-03): collector 60+ / Brain factor 10 으로 breadth 는 압도적이나,
실효 품질은 종목별 핵심 필드의 충족률에 좌우된다. 6/3 사고(stock_analysis
80% AI_ANALYSIS_FAILED / 공개 리포트 40% 빈 생성)가 trust_score 8조건을 모두
통과하고 silent 로 지나간 이유 = trust_score 는 시스템 GO/NO-GO(소스 up/down)만
재고, **필드·출력 단위 완전성은 안 쟀기 때문**. 본 모듈이 그 갭을 메운다.

trust_score(시스템 레벨) 와 직교 — 여기는 종목·필드 레벨. 못 재는 품질은 못 올린다.

산출: 종목별 완전성 + 필드별 커버리지 % + 카테고리별 % + AI verdict 실패율
(6/3 누수 직격) + 최약 필드/종목. data/metadata/field_coverage.jsonl 에 종적 적재.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from api.config import DATA_DIR, now_kst

_PATH = os.path.join(DATA_DIR, "metadata", "field_coverage.jsonl")

# AI verdict 가 "생성됐지만 실패 내용"인 케이스 — 존재만으론 유효 X (6/3 누수 핵심).
_VERDICT_FAIL_MARKERS = (
    "AI_ANALYSIS_FAILED", "파싱 실패", "분석 오류", "분석 실패", "수동 확인",
)


def _has_value(v: Any) -> bool:
    """기본 존재 — None/빈문자/빈리스트/빈딕트 = 결손. 숫자 0 은 존재로 인정."""
    if v is None:
        return False
    if isinstance(v, str):
        return v.strip() != ""
    if isinstance(v, (list, dict)):
        return len(v) > 0
    return True


def _pos(v: Any) -> bool:
    """양수 필수 — 가격/시총 등 0 이면 결손으로 간주하는 필드용."""
    try:
        return float(v) > 0
    except (TypeError, ValueError):
        return False


def _dict_ok(v: Any) -> bool:
    """비어있지 않은 dict + 에러 마커 없음."""
    if not isinstance(v, dict) or not v:
        return False
    if v.get("_error") or v.get("error"):
        return False
    return True


def _verdict_ok(v: Any) -> bool:
    """AI verdict 존재 + 실패 문구 미포함 (6/3 AI_ANALYSIS_FAILED 누수 직격)."""
    if not isinstance(v, str) or not v.strip():
        return False
    return not any(m in v for m in _VERDICT_FAIL_MARKERS)


# 큐레이션: 분석 품질에 critical 한 필드만 (전체 ~90 중).
# (category, field, validator, scope) — scope "all"=전 종목 / "kr"=한국 종목만
# (KIS/DART/lynch_kr 는 한국 전용 → US 종목엔 N/A, 결손으로 세면 noise).
_SPEC: List[tuple] = [
    # 펀더멘털
    ("펀더멘털", "roe", _has_value, "all"),
    ("펀더멘털", "per", _has_value, "all"),
    ("펀더멘털", "pbr", _has_value, "all"),
    ("펀더멘털", "debt_ratio", _has_value, "all"),
    ("펀더멘털", "operating_margin", _has_value, "all"),
    ("펀더멘털", "revenue_growth", _has_value, "all"),
    ("펀더멘털", "free_cashflow", _has_value, "nonfin"),  # 금융주 N/A (FCF 미정의)
    ("펀더멘털", "operating_cashflow", _has_value, "all"),
    # 가격/가치
    ("가격가치", "current_price", _pos, "all"),
    ("가격가치", "market_cap", _pos, "all"),
    ("가격가치", "high_52w", _pos, "all"),
    ("가격가치", "low_52w", _pos, "all"),
    # Brain/분석
    ("Brain분석", "verity_brain", _dict_ok, "all"),
    ("Brain분석", "raw_brain_score", _has_value, "all"),
    ("Brain분석", "multi_factor", _dict_ok, "all"),
    ("Brain분석", "score_breakdown", _dict_ok, "all"),
    # AI verdict (6/3 누수 핵심)
    ("AI판정", "ai_verdict", _verdict_ok, "all"),
    # 수급/KIS (한국 전용 — 6/3 4 silent fail 복구 대상)
    ("수급KIS", "flow", _dict_ok, "all"),
    ("수급KIS", "kis_financial_ratio", _dict_ok, "kr"),
    ("수급KIS", "kis_short_sale", _dict_ok, "kr"),
    ("수급KIS", "kis_credit_balance", _dict_ok, "kr"),
    # 센티먼트
    ("센티먼트", "sentiment", _dict_ok, "all"),
    ("센티먼트", "social_sentiment", _dict_ok, "all"),
    # 컨센서스/실적
    ("컨센실적", "consensus", _dict_ok, "all"),
    ("컨센실적", "earnings", _dict_ok, "all"),
    ("컨센실적", "prediction", _dict_ok, "all"),
    # 한국 1차자료 (DART — 유일 해자, 한국 전용)
    ("DART한국", "dart_business_analysis", _dict_ok, "kr"),
    ("DART한국", "dart_related_party", _dict_ok, "kr"),  # 2026-06-03 2차 원문 심화
    ("DART한국", "dart_disclosure_events", _dict_ok, "kr"),  # 2026-06-04 공시 이벤트
    ("DART한국", "dart_audit_signals", _dict_ok, "kr"),  # 2026-06-04 going-concern
    ("DART한국", "fscore_deltas", _dict_ok, "all"),
    # Lynch/value (한국 전용)
    ("Lynch", "lynch_kr", _dict_ok, "kr"),
]

_TOTAL_FIELDS = len(_SPEC)


def _is_kr(stock: Dict[str, Any]) -> bool:
    """한국 종목 여부 — KIS/DART 필드 적용 대상 판정."""
    mkt = str(stock.get("market") or "").upper()
    cur = str(stock.get("currency") or "").upper()
    return mkt in ("KOSPI", "KOSDAQ", "KONEX") or cur == "KRW"


def _is_financial(stock: Dict[str, Any]) -> bool:
    """금융 섹터 여부 — free_cashflow 가 N/A 인 대상 판정.

    은행/보험/증권/여신은 전통적 capex 개념이 없어 FCF(=OCF−capex) 미정의 →
    yfinance 도 freeCashflow None 반환. 결손이 아니라 N/A (2026-06-04 진단:
    BAC/JPM 은행·SOFI Credit 결손 = 금융주 only, 비금융 22종목 FCF 100%).
    """
    s = (str(stock.get("sector") or "") + str(stock.get("industry") or "")
         + str(stock.get("company_type") or ""))
    return any(k in s for k in (
        "Financ", "Bank", "Insurance", "Capital Markets", "Credit Services",
        "은행", "금융", "보험", "증권", "여신"))


def _applies(scope: str, is_kr: bool, is_fin: bool) -> bool:
    if scope == "kr":
        return is_kr
    if scope == "nonfin":
        return not is_fin  # free_cashflow 등 금융주 N/A 필드
    return scope == "all"


def compute_field_coverage(recommendations: List[Dict[str, Any]]) -> Dict[str, Any]:
    """종목 리스트 → 필드 커버리지 리포트 (순수 함수, I/O 없음)."""
    recs = [r for r in (recommendations or []) if isinstance(r, dict)]
    n = len(recs)
    if n == 0:
        return {
            "n_stocks": 0,
            "overall_coverage_pct": 0.0,
            "by_category": {},
            "by_field": {},
            "ai_verdict_failed_pct": 0.0,
            "worst_fields": [],
            "weak_stocks": [],
            "total_fields": _TOTAL_FIELDS,
            "generated_at": now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        }

    field_valid: Dict[str, int] = {f: 0 for _, f, _, _ in _SPEC}
    field_appl: Dict[str, int] = {f: 0 for _, f, _, _ in _SPEC}  # 적용 대상 수(분모)
    cat_valid: Dict[str, int] = {}
    cat_cells: Dict[str, int] = {}
    per_stock: List[Dict[str, Any]] = []
    ai_failed = 0

    for r in recs:
        is_kr = _is_kr(r)
        is_fin = _is_financial(r)
        stock_valid = 0
        stock_appl = 0
        for cat, field, validator, scope in _SPEC:
            if not _applies(scope, is_kr, is_fin):
                continue  # N/A 필드는 분자·분모 모두 제외 (noise 방지)
            field_appl[field] += 1
            stock_appl += 1
            cat_cells[cat] = cat_cells.get(cat, 0) + 1
            if validator(r.get(field)):
                field_valid[field] += 1
                stock_valid += 1
                cat_valid[cat] = cat_valid.get(cat, 0) + 1
        per_stock.append({
            "ticker": r.get("ticker", "?"),
            "name": r.get("name", "?"),
            "market": "KR" if is_kr else "US",
            "completeness_pct": round(100.0 * stock_valid / stock_appl, 1) if stock_appl else 0.0,
        })
        # AI verdict 실패 = verdict 무효 OR risk_flags 에 AI_ANALYSIS_FAILED
        rf = r.get("risk_flags") or []
        if (not _verdict_ok(r.get("ai_verdict"))) or ("AI_ANALYSIS_FAILED" in rf):
            ai_failed += 1

    by_field = {
        f: {
            "valid": field_valid[f],
            "applicable": field_appl[f],
            "pct": round(100.0 * field_valid[f] / field_appl[f], 1) if field_appl[f] else None,
        }
        for _, f, _, _ in _SPEC
    }
    by_category = {
        c: round(100.0 * cat_valid.get(c, 0) / cat_cells[c], 1) for c in cat_cells
    }
    total_valid = sum(field_valid.values())
    total_appl = sum(field_appl.values())
    overall = round(100.0 * total_valid / total_appl, 1) if total_appl else 0.0
    worst_fields = sorted(
        ([f, by_field[f]["pct"]] for _, f, _, _ in _SPEC if by_field[f]["pct"] is not None),
        key=lambda x: x[1],
    )[:5]
    weak_stocks = sorted(per_stock, key=lambda x: x["completeness_pct"])[:5]

    return {
        "n_stocks": n,
        "overall_coverage_pct": overall,
        "by_category": by_category,
        "by_field": by_field,
        "ai_verdict_failed_pct": round(100.0 * ai_failed / n, 1),
        "worst_fields": worst_fields,
        "weak_stocks": weak_stocks,
        "total_fields": _TOTAL_FIELDS,
        "generated_at": now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
    }


def log_field_coverage(report: Dict[str, Any]) -> None:
    """종적 trail 적재 — 시간 경과에 따른 품질 추세 (compact 1줄)."""
    try:
        os.makedirs(os.path.dirname(_PATH), exist_ok=True)
        line = {
            "ts": report.get("generated_at"),
            "n": report.get("n_stocks"),
            "overall": report.get("overall_coverage_pct"),
            "ai_verdict_failed": report.get("ai_verdict_failed_pct"),
            "by_category": report.get("by_category"),
            "worst_fields": report.get("worst_fields"),
        }
        with open(_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
    except Exception:
        pass  # 적재 실패가 파이프라인을 막지 않음


def summary_line(report: Dict[str, Any]) -> str:
    wf = report.get("worst_fields") or []
    wf_str = ", ".join(f"{f}:{p}%" for f, p in wf[:3])
    return (f"전체 {report.get('overall_coverage_pct')}% | "
            f"AI verdict 실패 {report.get('ai_verdict_failed_pct')}% | "
            f"최약 [{wf_str}]")
