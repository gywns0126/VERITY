"""CANSLIM growth score — O'Neil 7 요소.

원본: api/intelligence/verity_brain.py:343-412 (분해 전).
"""
from __future__ import annotations

from typing import Any, Dict

from api.intelligence.factors._common import _clip


def _compute_canslim_score(stock: Dict[str, Any]) -> float:
    """O'Neil CANSLIM 요소: EPS 성장률 가속 + RS Rating + 기관 매집 → 0~100."""
    score = 50.0
    is_us = stock.get("currency") == "USD"

    # C: Current EPS Growth (최근 분기 EPS 성장률 ≥ 25%)
    cons = stock.get("consensus") or {}
    eps_growth = cons.get("eps_growth_qoq_pct") or cons.get("eps_growth_yoy_pct")
    if eps_growth is not None:
        eps_growth = float(eps_growth)
        if eps_growth >= 50:
            score += 15
        elif eps_growth >= 25:
            score += 10
        elif eps_growth >= 10:
            score += 3
        elif eps_growth < 0:
            score -= 8

    # A: Annual EPS Growth (연간 성장률)
    annual_growth = cons.get("operating_profit_yoy_est_pct")
    if annual_growth is not None:
        annual_growth = float(annual_growth)
        if annual_growth >= 25:
            score += 8
        elif annual_growth >= 10:
            score += 3
        elif annual_growth < 0:
            score -= 5

    # L: Leader — RS Rating (상대 강도, 기술적 모멘텀 프록시)
    tech = stock.get("technical") or {}
    # 52주 고점 대비 하락 비율을 RS 프록시로 활용
    drop = stock.get("drop_from_high_pct", 0)
    if drop is not None:
        drop = abs(float(drop))
        if drop < 5:
            score += 8
        elif drop < 15:
            score += 3
        elif drop > 40:
            score -= 5

    # S: Supply & Demand — 거래량 확인
    vol_ratio = tech.get("vol_ratio", 1.0)
    if vol_ratio is not None:
        vol_ratio = float(vol_ratio)
        if vol_ratio > 2.0:
            score += 5
        elif vol_ratio > 1.5:
            score += 2

    # I: Institutional Sponsorship — US만 기관 보유 변화 확인
    #    (KR 수급은 export_trade에서 전담 — 중복 방지)
    if is_us:
        inst_own = stock.get("institutional_ownership") or {}
        inst_chg = inst_own.get("change_pct", 0)
        if inst_chg > 5:
            score += 8
        elif inst_chg > 0:
            score += 3
        elif inst_chg < -5:
            score -= 5

    # N: New High — 신고가 여부
    signals = tech.get("signals") or []
    if any("고가" in s or "신고" in s or "돌파" in s for s in signals):
        score += 5

    return _clip(score)
