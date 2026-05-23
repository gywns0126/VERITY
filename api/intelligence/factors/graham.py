"""Graham value score + Lynch PEG 보정.

원본: api/intelligence/verity_brain.py:235-338 (분해 전).
"""
from __future__ import annotations

from typing import Any, Dict

from api.intelligence.factors._common import _clip


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

    per = float(per) if per is not None else 0
    pbr = float(pbr) if pbr is not None else 0
    debt_ratio = float(debt_ratio)
    roe = float(roe)

    # PER <= 15: Graham 기준 충족
    if 0 < per <= 15:
        score += 12
    elif 0 < per <= 20:
        score += 5
    elif per > 30:
        score -= 8

    # PBR × PER <= 22.5: Graham 복합 기준
    if per > 0 and pbr > 0:
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
    cons_local = stock.get("consensus") or {}
    eps_growth_raw = (
        cons_local.get("eps_growth_yoy_pct")
        or cons_local.get("eps_growth_qoq_pct")
        or cons_local.get("operating_profit_yoy_est_pct")
        or stock.get("revenue_growth")
    )
    if per > 0 and eps_growth_raw is not None:
        try:
            eps_growth = float(eps_growth_raw)
            if eps_growth > 0:
                peg = per / eps_growth
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
