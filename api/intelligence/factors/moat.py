"""Moat quality score — Hohn / McMurtrie / 가격결정력 / 청산가치.

원본: api/intelligence/verity_brain.py:75-230 (분해 전).
"""
from __future__ import annotations

from typing import Any, Dict

from api.intelligence.factors._common import _clip, _load_constitution, _safe_float


def _compute_moat_score(stock: Dict[str, Any]) -> float:
    """Hohn 해자 검증 + McMurtrie 구조적 수요자 + 가격 결정력 → 0~100.
    섹터 배제, 진입 장벽, 수급 구조, 청산가치 하방보호를 통합 평가한다."""
    const = _load_constitution()
    hfp = const.get("hedge_fund_principles", {})
    excluded = hfp.get("excluded_sectors", {})
    penalty = excluded.get("penalty", -15)

    score = 50.0
    is_us = stock.get("currency") == "USD"

    # 1) Hohn: 섹터 배제 — 구조적으로 해자가 약한 업종 감점
    sector = stock.get("sector", "") or ""
    sub_sector = stock.get("sub_sector", "") or stock.get("industry", "") or ""
    # 2026-07-20 감사 P1: excluded kr 목록은 한글(은행/증권/보험..)인데 sector/industry 는 yfinance 영문
    # → KR penalty 무발화. company_type(한글 필드)을 매칭축에 포함(no-regression: 부재 시 "").
    company_type = stock.get("company_type", "") or ""
    sector_key = "us" if is_us else "kr"
    excluded_list = excluded.get(sector_key, [])
    sector_combined = f"{sector} {sub_sector} {company_type}".strip()
    if any(ex.lower() in sector_combined.lower() for ex in excluded_list if ex):
        score += penalty

    # 2) Hohn: 가격 결정력 — 매출총이익률(GPM) 추세 + 매출 성장
    if is_us:
        sec_fin = stock.get("sec_financials") or {}
        gpm = sec_fin.get("gross_margin")
        rev_growth = sec_fin.get("revenue_growth")
    else:
        dart = stock.get("dart_financials") or {}
        inc = dart.get("income_statement") or {}
        gpm = inc.get("gross_profit_margin")
        rev_growth = inc.get("revenue_growth_yoy")
        if gpm is None:
            kfr = stock.get("kis_financial_ratio") or {}
            if kfr.get("source") == "kis":
                gpm = kfr.get("gross_margin")

    # 2026-05-19 M1 fix — top-level fallback (KIS/yfinance 가 제공하는 풍부한 데이터).
    # 진단 (docs/BRAIN_SCORE_AUDIT_20260518.md §3): nested path (sec_financials /
    # dart_financials / kis_financial_ratio.gross_margin) 모두 0/N → fallback 50
    # 60%. top-level gross_margins(22/25)/revenue_growth(24/25) 풍부. gpm=0 은
    # invalid (실제 0% gross margin 사실상 없음) 처리.
    if gpm is None:
        _v = stock.get("gross_margins")
        if isinstance(_v, (int, float)) and _v != 0:
            gpm = _v
    if rev_growth is None:
        _v = stock.get("revenue_growth")
        if isinstance(_v, (int, float)):
            rev_growth = _v

    gpm = _safe_float(gpm)
    rev_growth = _safe_float(rev_growth)
    if gpm is not None and rev_growth is not None:
        if gpm > 40 and rev_growth > 5:
            score += 15
        elif gpm > 30 and rev_growth > 0:
            score += 8
        elif gpm < 15:
            score -= 8

    # 3) McMurtrie: 청산가치 하방보호 — PBR < 1.0 + 낮은 부채
    #    (수급 데이터는 export_trade에서 전담 — 중복 방지)
    pbr = stock.get("pbr") or stock.get("price_to_book")
    debt_ratio = stock.get("debt_ratio", 100)
    if is_us:
        sec_fin = stock.get("sec_financials") or {}
        if pbr is None:
            pbr = sec_fin.get("price_to_book")
        if sec_fin.get("debt_ratio") is not None:
            debt_ratio = sec_fin.get("debt_ratio", 100)
    else:
        kfr = stock.get("kis_financial_ratio") or {}
        if kfr.get("source") == "kis":
            if pbr is None:
                pbr = kfr.get("pbr")
            if kfr.get("debt_ratio") is not None:
                debt_ratio = kfr.get("debt_ratio", 100)

    pbr = _safe_float(pbr)
    if pbr is not None:
        debt_ratio = _safe_float(debt_ratio, 100.0)
        from api.analyzers.sector_thresholds import resolve_sector_bucket, get_debt_ratio_thresholds
        _debt_t = get_debt_ratio_thresholds(resolve_sector_bucket(stock))
        if 0 < pbr < 1.0 and debt_ratio < _debt_t["normal_max"] * 0.5:
            score += 10
        elif 0 < pbr < 0.7:
            score += 5
        elif pbr > 10:
            score -= 5

    # 4) Hohn: ROE 기반 복리 성장력 — 양질의 비즈니스 확인
    #    (점수 축소: graham_value에서도 ROE 평가하므로 해자 관점 최소화)
    roe = None
    if is_us:
        sec_fin = stock.get("sec_financials") or {}
        roe = sec_fin.get("roe")
    else:
        kfr = stock.get("kis_financial_ratio") or {}
        if kfr.get("source") == "kis":
            roe = kfr.get("roe")
    # 2026-05-19 M1 fix — top-level fallback (US sec_financials.roe 0/15 회복).
    # KR 은 KIS path 10/10 정상 — top-level fallback 거의 redundant 이나 KIS source
    # 미확인 케이스 보호.
    if roe is None:
        _v = stock.get("roe")
        if isinstance(_v, (int, float)):
            roe = _v
    roe = _safe_float(roe)
    if roe is not None:
        if roe > 20:
            score += 5
        elif roe < 0:
            score -= 5

    # 5) §22 — DART 사업보고서 AI 해자 지표 통합
    # dart_report_analyzer 가 추출한 moat_indicators (Gemini 정성 분석) 를
    # 정량 score 에 반영. 개수 + 핵심 키워드 매칭 이중 bonus (최대 +8).
    # 2026-06-23 — KR-전용 DART 시그널. US 명시 가드(다른 factor 패턴 정합, US 데이터 부착 시 KR 보너스 누출 차단).
    dart_moat = None if is_us else (stock.get("dart_business_analysis") or {}).get("moat_indicators")
    if isinstance(dart_moat, list) and dart_moat:
        valid = [m for m in dart_moat if isinstance(m, str) and m.strip()]
        # 해자 개수 보너스
        if len(valid) >= 3:
            score += 5      # 복수 해자 (brand+tech+scale 등)
        elif len(valid) >= 1:
            score += 2      # 일부 해자

        # 핵심 해자 유형 키워드 매칭 (중복 카운트 1회)
        all_text = " ".join(valid).lower()
        moat_keywords = [
            "특허", "patent",           # 지식재산
            "점유율", "1위", "market share", "dominant",  # 시장 지위
            "브랜드", "brand",          # 브랜드 파워
            "전환비용", "switching",    # 고객 락인
            "네트워크", "network effect",  # 네트워크 효과
            "라이선스", "license",      # 규제 진입장벽
            "수직계열화", "vertical",   # 비용 우위
        ]
        # 중복 카테고리 매칭 방지 — keyword 중 하나만 매치해도 카테고리 1개
        categories = [
            ("특허", "patent"),
            ("점유율", "1위", "market share", "dominant"),
            ("브랜드", "brand"),
            ("전환비용", "switching"),
            ("네트워크", "network effect"),
            ("라이선스", "license"),
            ("수직계열화", "vertical"),
        ]
        categories_hit = sum(
            1 for cat_kws in categories
            if any(kw.lower() in all_text for kw in cat_kws)
        )
        if categories_hit >= 3:
            score += 3      # 다차원 해자
        elif categories_hit >= 1:
            score += 1      # 단일 해자 유형

    return _clip(score)
