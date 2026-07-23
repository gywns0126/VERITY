"""CANSLIM growth score — O'Neil 7 요소.

원본: api/intelligence/verity_brain.py:343-412 (분해 전).
"""
from __future__ import annotations

from typing import Any, Dict

from api.intelligence.factors._common import _clip, _safe_float


def _compute_canslim_score(stock: Dict[str, Any]) -> float:
    """O'Neil CANSLIM 요소: EPS 성장률 가속 + RS Rating + 기관 매집 → 0~100."""
    score = 50.0
    is_us = stock.get("currency") == "USD"

    # C: Current EPS Growth (최근 분기 EPS 성장률 ≥ 25%)
    # 2026-07-24 fix: consensus.eps_growth_qoq_pct/yoy_pct = 미존재 필드(실 종목 0건 populate) → C 영구
    # dead 였음. 실 소스 = stock.eps_quarterly_growth(yfinance earningsQuarterlyGrowth, %단위 실측
    # 172.2/35.4/-29.0 → O'Neil C 정의 정합·임계 25/50과 단위 일치). consensus 참조 제거.
    cons = stock.get("consensus") or {}
    eps_growth = _safe_float(stock.get("eps_quarterly_growth"))
    if eps_growth is not None:
        if eps_growth >= 50:
            score += 15
        elif eps_growth >= 25:
            score += 10
        elif eps_growth >= 10:
            score += 3
        elif eps_growth < 0:
            score -= 8

    # A: Annual EPS Growth (연간 성장률)
    annual_growth = _safe_float(cons.get("operating_profit_yoy_est_pct"))
    if annual_growth is not None:
        if annual_growth >= 25:
            score += 8
        elif annual_growth >= 10:
            score += 3
        elif annual_growth < 0:
            score -= 5

    # L: Leader — RS Rating (상대 강도, 기술적 모멘텀 프록시)
    tech = stock.get("technical") or {}
    # 52주 고점 대비 하락 비율을 RS 프록시로 활용
    # 2026-07-24 fix: 결측 default 0(=신고가) 제거 — drop 부재 종목이 최강 리더 +8 부당획득(fail-open) 차단.
    drop = _safe_float(stock.get("drop_from_high_pct"))
    if drop is not None:
        drop = abs(drop)
        if drop < 5:
            score += 8
        elif drop < 15:
            score += 3
        elif drop > 40:
            score -= 5

    # S: Supply & Demand — 거래량 확인
    vol_ratio = _safe_float(tech.get("vol_ratio", 1.0))
    if vol_ratio is not None:
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

    # N: New High — 신고가 근접
    # 2026-07-24 fix: tech.signals 실 어휘(MACD/RSI 뿐)에 '고가/신고/돌파' 부재로 N 영구 dead 였음
    # (문자열 키워드 매칭 미성립). drop_from_high_pct 직접 사용(신고가 프록시) — 52주 고점 대비 3% 이내 = 신고가권.
    _drop_nh = _safe_float(stock.get("drop_from_high_pct"))
    if _drop_nh is not None and abs(_drop_nh) < 3:
        score += 5

    return _clip(score)
