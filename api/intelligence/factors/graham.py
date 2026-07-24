"""Graham value score + Lynch PEG 보정.

원본: api/intelligence/verity_brain.py:235-338 (분해 전).
"""
from __future__ import annotations

from typing import Any, Dict

from api.intelligence.factors._common import _clip, _safe_float


def _compute_graham_score(stock: Dict[str, Any]) -> float:
    """Graham 방어적 투자자 기준: 안전마진 + PER/PBR + 재무건전성 → 0~100."""
    score = 50.0
    is_us = stock.get("currency") == "USD"

    per = stock.get("per") or stock.get("price_to_earnings")
    pbr = stock.get("pbr") or stock.get("price_to_book")

    if is_us:
        sec_fin = stock.get("sec_financials") or {}
        if per is None:
            per = sec_fin.get("pe_ratio")
        if pbr is None:
            pbr = sec_fin.get("price_to_book")
        debt_ratio = sec_fin.get("debt_ratio") or stock.get("debt_ratio", 100)
        roe = sec_fin.get("roe") or stock.get("roe", 0)
        current_ratio = sec_fin.get("current_ratio", 0)
    else:
        kfr = stock.get("kis_financial_ratio") or {}
        if kfr.get("source") == "kis":
            if per is None:
                per = kfr.get("per")
            if pbr is None:
                pbr = kfr.get("pbr")
            debt_ratio = kfr.get("debt_ratio", 100)
            roe = kfr.get("roe", 0)
            current_ratio = kfr.get("current_ratio", 0)
        else:
            debt_ratio = stock.get("debt_ratio", 100)
            roe = stock.get("roe", 0)
            current_ratio = 0

    # 2026-06-03: 무방어 float() → _safe_float (per/pbr/roe 등이 'N/A'·'-' 비숫자 문자열이면
    #   ValueError 로 _compute_graham_score 전체 크래시 → 상위에서 삼켜지면 fact_score silent 결손).
    per = _safe_float(per, 0) or 0
    pbr = _safe_float(pbr, 0) or 0
    debt_ratio = _safe_float(debt_ratio, 100) or 100
    roe = _safe_float(roe, 0) or 0
    current_ratio = _safe_float(current_ratio, 0) or 0

    # PER <= 15: Graham 기준 충족
    if 0 < per <= 15:
        score += 12
    elif 0 < per <= 20:
        score += 5
    elif per > 30:
        score -= 8

    # PBR × PER <= 22.5: Graham 복합 기준 (15 P/E × 1.5 P/B)
    # 2026-07-24 fix: 결측 PBR sentinel(verity_brain 이 None/≤0 을 1.0 으로 mutate, pbr_normalized_neutral)
    # 은 진짜 PBR 아님 → 복합기준에서 per≤22.5 인 종목 전원 부당 +10 획득(fail-open, 실측 10/53). sentinel
    # 종목은 복합기준 skip(진짜 book value 없음 = 가치/과대 판정 불가). moat.py:97 배제 패턴과 정합.
    if per > 0 and pbr > 0 and not stock.get("pbr_normalized_neutral"):
        pb_pe = pbr * per
        if pb_pe <= 22.5:
            score += 10
        elif pb_pe > 50:
            score -= 8

    # ── Lynch PEG 보정 (배리티 브레인 투자 바이블 ④, Perplexity 권고) ──
    # PEG = PER ÷ EPS 성장률. Lynch: PEG < 1 매력적, PEG > 2 위험.
    # 데이터 소스 우선순위:
    #   1) consensus.eps_growth_yoy_pct       — 가장 정확
    #   2) consensus.eps_growth_qoq_pct       — 분기 추정치
    #   3) consensus.operating_profit_yoy_est_pct — 영업이익 성장 (EPS proxy, 한국 빈번)
    #   4) stock.revenue_growth               — 매출 성장 (약한 proxy)
    # graham_value 와 충돌 방지: PEG 단독 ±15 (Lynch 본인이 PEG 단독 의존 경고).
    # 2026-07-24 fix: PEG 분모 = EPS 성장(정의). 옛 fallback 이 죽은 consensus.eps_growth_*(실 0건) →
    # operating_profit → revenue_growth(매출성장 ≠ EPS!)로 붕괴 → US 15종목 중 13 을 매출성장 기반 오산
    # PEG 로 잘못된 -15 penalty(가치주 오탈락 = 기회손실=돈). red_flags PEG fix(#153) 와 정합. 실 소스
    # eps_quarterly_growth(%, 50/53). + PEGY(Lynch One Up 배당 팩터): 배당수익률을 분모에 가산 —
    # 고배당 가치주는 성장이 낮아도 총수익(성장+배당)으로 평가(PEG>2 오탈락 방지).
    cons_local = stock.get("consensus") or {}
    eps_growth_raw = stock.get("eps_quarterly_growth")
    if eps_growth_raw is None:
        eps_growth_raw = cons_local.get("operating_profit_yoy_est_pct")
    if per > 0 and eps_growth_raw is not None:
        try:
            eps_growth = float(eps_growth_raw)
            _pegy_denom = eps_growth + float(stock.get("div_yield") or 0)  # PEGY = 성장 + 배당수익률(%)
            if _pegy_denom > 0:
                peg = per / _pegy_denom
                if peg < 0.5:
                    score += 15  # 매우 매력적 (Lynch tenbagger 후보)
                elif peg < 1.0:
                    score += 8   # 매력적 (Lynch 표준 기준)
                elif peg <= 2.0:
                    pass  # 중립
                else:
                    score -= 15  # PEG > 2 = Lynch 경고
        except (TypeError, ValueError):
            pass

    # 재무건전성: 유동비율 200%+ (Graham 요구), 낮은 부채
    if current_ratio >= 200:
        score += 5
    elif current_ratio > 0 and current_ratio < 100:
        score -= 5

    from api.analyzers.sector_thresholds import resolve_sector_bucket, get_debt_ratio_thresholds
    _debt_t_g = get_debt_ratio_thresholds(resolve_sector_bucket(stock))
    if debt_ratio < _debt_t_g["normal_max"] * 0.5:
        score += 5
    elif debt_ratio > _debt_t_g["high"]:
        score -= 8

    # ROE 양호 (지속적 수익성 확인)
    if roe > 15:
        score += 5
    elif roe < 0:
        score -= 8

    return _clip(score)
