"""
Verity Brain v5.0 — 배리티 터미널의 종합 판단 엔진

V5 학습 소스:
  - Hedge Fund Masters Report (Hohn/McMurtrie/Tang/Dalio/Guindo)
  - Quant & Smart Money Trading Report (Renaissance/Soros/Cohen/Citadel)
  - 30권 투자 고전 통합 (brain_knowledge_base.json v1.0)

핵심 구조:
  Fact Score (객관 + Moat + Graham + CANSLIM) × 0.7
+ Sentiment Score (심리 + 동적 크립토 가중치) × 0.3
+ VCI v2.0 Bonus (Cohen 역발상 체크리스트)
+ Candle Psychology Bonus (Nison Rule of Multiple Techniques)
= Brain Score → 최종 등급 + Kelly 포지션 가이드

V5 추가 모듈:
  - Graham Value Score: 안전마진 + PER/PBR + 재무건전성 (Benjamin Graham)
  - CANSLIM Growth Score: EPS 가속 + RS Rating + 기관 매집 (William O'Neil)
  - Candle Psychology Score: Nison 3대원칙 + 확인 체크리스트 → timing 보너스
  - Bubble Detection: Mackay/Shiller/Taleb 기반 시장 레벨 경고 플래그

모든 가중치와 임계값은 verity_constitution.json v5.0에서 로드.
"""
from __future__ import annotations

import json
import math
import os
from typing import Any, Dict, List, Optional

from datetime import date as _date, datetime as _datetime

from api.config import (
    DATA_DIR, MACRO_DGS10_DEFENSE_PCT,
    US_IV_PERCENTILE_WARN, US_PUT_CALL_BEARISH, US_INSIDER_MSPR_PENALTY,
    now_kst,
)
from api.utils.portfolio_writer import read_section

_CONSTITUTION_PATH = os.path.join(DATA_DIR, "verity_constitution.json")
_constitution_cache: Optional[Dict[str, Any]] = None


def _load_constitution() -> Dict[str, Any]:
    global _constitution_cache
    if _constitution_cache is not None:
        return _constitution_cache
    try:
        with open(_CONSTITUTION_PATH, "r", encoding="utf-8") as f:
            _constitution_cache = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        _constitution_cache = {}
    return _constitution_cache


def _clip(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def _safe_float(v: Any, default: Optional[float] = None) -> Optional[float]:
    """None/NaN/Infinity/비숫자 문자열을 안전하게 default로 반환."""
    if v is None:
        return default
    try:
        x = float(v)
        if math.isnan(x) or math.isinf(x):
            return default
        return x
    except (TypeError, ValueError):
        return default


# ─── V4: Moat Quality Score ──────────────────────────────────

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
    sector_key = "us" if is_us else "kr"
    excluded_list = excluded.get(sector_key, [])
    sector_combined = f"{sector} {sub_sector}".strip()
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

    if gpm is not None and rev_growth is not None:
        gpm = float(gpm)
        rev_growth = float(rev_growth)
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

    if pbr is not None:
        pbr = float(pbr)
        debt_ratio = float(debt_ratio)
        if 0 < pbr < 1.0 and debt_ratio < 50:
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
    if roe is not None:
        roe = float(roe)
        if roe > 20:
            score += 5
        elif roe < 0:
            score -= 5

    # 5) §22 — DART 사업보고서 AI 해자 지표 통합
    # dart_report_analyzer 가 추출한 moat_indicators (Gemini 정성 분석) 를
    # 정량 score 에 반영. 개수 + 핵심 키워드 매칭 이중 bonus (최대 +8).
    dart_moat = (stock.get("dart_business_analysis") or {}).get("moat_indicators")
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


# ─── V5: Graham Value Score ───────────────────────────────────

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

    # 재무건전성: 유동비율 200%+ (Graham 요구), 낮은 부채
    if current_ratio >= 200:
        score += 5
    elif current_ratio > 0 and current_ratio < 100:
        score -= 5

    if debt_ratio < 50:
        score += 5
    elif debt_ratio > 200:
        score -= 8

    # ROE 양호 (지속적 수익성 확인)
    if roe > 15:
        score += 5
    elif roe < 0:
        score -= 8

    return _clip(score)


# ─── V5: CANSLIM Growth Score ─────────────────────────────────

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


# ─── V5: Candle Psychology Score ──────────────────────────────

def _compute_candle_psychology_score(stock: Dict[str, Any]) -> float:
    """Nison Rule of Multiple Techniques: 캔들 패턴 + 확인 조건 → 보너스 점수.
    timing 팩터 보정에 사용. -10 ~ +10 범위의 보너스를 반환."""
    tech = stock.get("technical") or {}
    signals = tech.get("signals") or []
    vol_ratio = _safe_float(tech.get("vol_ratio"), 1.0)

    candle_base = 0
    bullish_count = 0
    bearish_count = 0

    bullish_patterns = [
        "망치", "hammer", "관통", "piercing", "아침별", "morning_star",
        "삼병정", "three_white", "상승장악", "bullish_engulf",
        "모닝", "상승잉태", "역전된망치", "inverted_hammer"
    ]
    bearish_patterns = [
        "교수형", "hanging", "흑운", "dark_cloud", "저녁별", "evening_star",
        "까마귀", "three_black", "하락장악", "bearish_engulf",
        "유성", "shooting_star", "하락잉태", "이브닝"
    ]

    for sig in signals:
        sig_lower = sig.lower() if isinstance(sig, str) else ""
        for bp in bullish_patterns:
            if bp in sig_lower:
                bullish_count += 1
                break
        for bp in bearish_patterns:
            if bp in sig_lower:
                bearish_count += 1
                break

    if bullish_count > bearish_count:
        candle_base = min(bullish_count * 1.5, 4)
    elif bearish_count > bullish_count:
        candle_base = max(bearish_count * -1.5, -4)

    if candle_base == 0:
        return 0.0

    # Nison 확인 조건: 거래량 동반 확인
    volume_bonus = 0
    if abs(candle_base) > 0 and vol_ratio > 1.5:
        volume_bonus = 1.5 if candle_base > 0 else -1.5

    # RSI 방향 일치 확인
    rsi = _safe_float(tech.get("rsi"))
    rsi_bonus = 0
    if rsi is not None:
        if candle_base > 0 and rsi < 40:
            rsi_bonus = 1.5
        elif candle_base < 0 and rsi > 60:
            rsi_bonus = -1.5

    # MACD 방향 일치 확인
    macd_hist = _safe_float(tech.get("macd_hist"))
    macd_bonus = 0
    if macd_hist is not None:
        if candle_base > 0 and macd_hist > 0:
            macd_bonus = 1.0
        elif candle_base < 0 and macd_hist < 0:
            macd_bonus = -1.0

    total = candle_base + volume_bonus + rsi_bonus + macd_bonus
    return max(-10.0, min(10.0, round(total, 1)))


# ─── V5: Bubble Detection ────────────────────────────────────

def _detect_bubble_signals(portfolio: Dict[str, Any]) -> Dict[str, Any]:
    """Mackay/Shiller/Taleb 기반 시장 레벨 버블 탐지.
    V5.1: 상관 지표를 그룹으로 묶어 그룹 내 최대 1점만 부여 (증폭 방지).
    Returns: {detected: bool, signals: [...], severity: 0~5}"""
    macro = portfolio.get("macro") or {}
    fred = macro.get("fred") or {}
    mood = macro.get("market_mood", {}).get("score", 50)

    signals = []

    # ── 그룹 A: 밸류에이션 (독립 지표) → 최대 2점 ──
    group_a = 0
    cape = fred.get("cape", {}).get("value")
    if cape is not None:
        cape = float(cape)
        if cape > 30:
            signals.append(f"CAPE {cape:.1f} > 30: 역사적 버블 수준 (Shiller)")
            group_a = 2
        elif cape > 25:
            signals.append(f"CAPE {cape:.1f} > 25: 과열 경고 (Shiller)")
            group_a = 1

    # ── 그룹 B: 시장 심리 (상관 지표 묶음) → 최대 1점 ──
    #    mood, VIX, CNN F&G는 모두 "시장 공포/탐욕"을 측정 → 개별 카운트 금지
    group_b = 0
    group_b_signals = []
    vix = macro.get("vix", {}).get("value", 20)
    mfg = portfolio.get("market_fear_greed") or {}
    mfg_val = mfg.get("value", 50) if mfg.get("ok") else 50

    if mood > 85:
        group_b_signals.append(f"시장 분위기 {mood}점")
    if vix < 12:
        group_b_signals.append(f"VIX {vix}(극저)")
    if mfg_val >= 85:
        group_b_signals.append(f"CNN F&G {mfg_val}")
    elif mfg_val <= 15:
        signals.append(f"CNN F&G {mfg_val}: 극단적 공포 (역발상 매수 구간)")

    if group_b_signals:
        signals.append(f"시장 심리 과열: {' / '.join(group_b_signals)} (Mackay/Taleb)")
        group_b = 1

    # ── 그룹 C: 자금 흐름 (독립 지표) → 최대 1점 ──
    group_c = 0
    ff = portfolio.get("fund_flows") or {}
    if ff.get("ok"):
        rot_sig = ff.get("rotation_signal", "neutral")
        if rot_sig == "risk_on" and ff.get("rotation_detail", {}).get("confidence", 0) >= 70:
            signals.append("펀드 플로우: 강한 위험자산 선호 (risk-on)")
            group_c = 1

    # ── 그룹 D: 크립토 과열 (독립 지표) → 최대 1점 ──
    group_d = 0
    crypto = portfolio.get("crypto_macro") or {}
    if crypto.get("available"):
        fng = crypto.get("fear_and_greed", {})
        if fng.get("ok") and fng.get("value", 50) >= 85:
            signals.append(f"크립토 F&G {fng['value']}: 극단적 탐욕")
            group_d = 1

    severity = group_a + group_b + group_c + group_d
    return {
        "detected": severity >= 2,
        "signals": signals,
        "severity": min(severity, 5),
    }


# ─── Fact Score ──────────────────────────────────────────────

_ic_adj_cache: Optional[Dict[str, Any]] = None


def _load_ic_adjustments() -> Dict[str, Any]:
    """IC/ICIR 기반 가중치 multiplier를 로드 (사이클당 1회 캐시)."""
    global _ic_adj_cache
    if _ic_adj_cache is not None:
        return _ic_adj_cache
    try:
        from api.quant.alpha.factor_decay import compute_ic_weight_adjustments
        _ic_adj_cache = compute_ic_weight_adjustments()
    except Exception as e:
        logger.debug("IC weight adjustments unavailable: %s", e)
        _ic_adj_cache = {"status": "error", "adjustments": {}, "log": []}
    return _ic_adj_cache


def reset_ic_cache():
    """새 사이클 시작 시 캐시 초기화."""
    global _ic_adj_cache
    _ic_adj_cache = None


# IC 팩터명 → fact_score weight 키 매핑
_IC_TO_WEIGHT_KEY = {
    "multi_factor": "multi_factor",
    "consensus": "consensus",
    "prediction": "prediction",
    "timing": "timing",
}

# IC 팩터명 → alpha_combined 보정에 영향주는 서브팩터
_IC_SUBFACTORS = {"momentum", "quality", "volatility", "mean_reversion",
                  "fundamental", "technical", "flow", "sentiment"}


def _compute_kr_fundamental_mean_reversion_score(stock: Dict[str, Any]) -> Optional[float]:
    """
    Brain Audit §11: DART KR backfill IC 기반 KR fundamental mean-reversion sub-score.

    측정 (scripts/dart_kr_backfill.py, 30 KR 종목 × 2015~2024, n=248, forward 30d):
      roe_pct:               IC -0.09 → high ROE 후 underperform (mean-reversion)
      operating_margin_pct:  IC -0.08 → high op_margin 후 underperform
      [노이즈]
        debt_ratio_pct:      IC +0.04 / -0.01 (Pearson/Spearman 부호 불일치)
        revenue_growth_pct:  IC -0.01 (noise)

    KRW 종목만 적용 (currency=KRW). 데이터 부족 시 None.
    가중치: |IC| 비례 정규화 — roe 0.53, op_margin 0.47.
    """
    if stock.get("currency") != "KRW":
        return None

    roe = stock.get("roe")
    op_margin = stock.get("operating_margin")
    if roe is None and op_margin is None:
        return None

    def _normalize_high_to_low(val, ref_high, ref_neutral):
        """val >= ref_high → 0, val == ref_neutral → 50, val << → 100. Linear."""
        try:
            v = float(val)
        except (TypeError, ValueError):
            return None
        # 선형 매핑: ref_high → 0, ref_neutral → 50, 2*ref_neutral - ref_high → 100
        slope = -50.0 / (ref_high - ref_neutral) if ref_high != ref_neutral else 0
        score = 50 + (v - ref_neutral) * slope
        return max(0.0, min(100.0, score))

    # ROE: 15% (high) → 0, 5% (neutral) → 50, -5% → 100
    s_roe = _normalize_high_to_low(roe, 15.0, 5.0) if roe is not None else None
    # op_margin: 15% (high) → 0, 5% (neutral) → 50, -5% → 100
    s_op = _normalize_high_to_low(op_margin, 15.0, 5.0) if op_margin is not None else None

    if s_roe is None and s_op is None:
        return None
    if s_roe is None:
        return round(s_op, 2)
    if s_op is None:
        return round(s_roe, 2)
    return round(s_roe * 0.53 + s_op * 0.47, 2)


def _compute_technical_mean_reversion_score(stock: Dict[str, Any]) -> Optional[float]:
    """
    Brain Audit §7: Backfill IC validated mean-reversion technical sub-score.

    측정 (scripts/historical_replay.py, 5종목 × 2020~2026, n=1355, forward 30d):
      rsi_14:              IC -0.05 → 높을수록 감점 (mean-reversion)
      price_to_ma120_pct:  IC -0.06 → 위로 멀수록 감점
      momentum_1m:         IC -0.03 → 강할수록 감점
      volatility_20d_ann:  IC +0.11 → 낮을수록 가산 (low-vol premium)
      [노이즈 IC<0.03 — 미사용]
        momentum_3m:       IC +0.025
        volume_ratio_20d:  IC +0.022

    가중치 (|IC| 비례 정규화, sum=1.0):
      vol 0.44, ma_gap 0.24, rsi 0.20, mom_1m 0.12

    데이터 부족 시 None — 호출자가 미적용 처리.
    """
    tech = stock.get("technical") or {}
    rsi = tech.get("rsi")
    ma_ref = tech.get("ma120") or tech.get("ma60")
    price = tech.get("price") or stock.get("price")
    spark = stock.get("sparkline") or []

    if rsi is None or price is None or ma_ref is None or len(spark) < 10:
        return None

    try:
        rsi_f = float(rsi)
        price_f = float(price)
        ma_f = float(ma_ref)
        if ma_f <= 0:
            return None
    except (TypeError, ValueError):
        return None

    # 1. RSI: 0→100 (oversold bullish), 100→0 (overbought bearish)
    s_rsi = max(0.0, min(100.0, 100 - rsi_f))

    # 2. price-to-MA gap: +30%→0, 0%→50, -30%→100 (ma120 사용; 200 부재 시 60)
    gap_pct = (price_f / ma_f - 1) * 100
    s_ma = max(0.0, min(100.0, 50 - gap_pct * 1.67))

    # 3. momentum_1m: sparkline 첫-끝. +10%→0, -10%→100
    try:
        p_first = float(spark[0])
        p_last = float(spark[-1])
        m1 = (p_last / p_first - 1) * 100 if p_first > 0 else 0.0
    except (TypeError, ValueError):
        m1 = 0.0
    s_m1 = max(0.0, min(100.0, 50 - m1 * 5))

    # 4. volatility (sparkline 일간 std × √252): 20%→100, 60%→0
    try:
        rets = []
        for i in range(1, len(spark)):
            p0 = float(spark[i - 1])
            p1 = float(spark[i])
            if p0 > 0:
                rets.append((p1 - p0) / p0)
        if len(rets) < 5:
            return None
        import statistics as _stats
        vol_ann = _stats.stdev(rets) * math.sqrt(252) * 100
    except Exception:
        return None
    s_vol = max(0.0, min(100.0, 100 - max(0.0, vol_ann - 20) * 2.5))

    score = s_vol * 0.44 + s_ma * 0.24 + s_rsi * 0.20 + s_m1 * 0.12
    return round(float(score), 2)


_PANIC_OVERRIDE_MODES = frozenset({
    "panic_stage_1", "panic_stage_2", "panic_stage_3", "panic_stage_4",
    "vix_spread_panic", "cape_bubble", "yield_defense", "vi_cascade",
    "fund_flow_cash_flight", "perplexity_critical", "us_recession",
})


def _is_regime_panic(portfolio: Optional[Dict[str, Any]],
                     macro_override: Optional[Dict[str, Any]]) -> bool:
    """위기장 게이트 — VIX > 30 또는 macro_override 가 panic/cape_bubble 류.

    True 시 mean-reversion bonus 비활성화 (가격 하락이 mean-reversion 점수를
    올려 거시 신호와 충돌하는 것 방지).
    """
    if macro_override:
        mode = macro_override.get("mode") or ""
        if mode in _PANIC_OVERRIDE_MODES:
            return True
    if portfolio:
        try:
            vix = float((portfolio.get("macro") or {}).get("vix", {}).get("value", 0) or 0)
            if vix > 30:
                return True
        except (TypeError, ValueError):
            pass
    return False


# §26: Postmortem time-decay penalty 상수
_PM_MAX_PENALTY = 2.0           # 최대 감점 (0일 = -2.0)
_PM_HALFLIFE_DAYS = 30.0        # 반감기 — 30일 지나면 절반, 60일 1/4


def _compute_postmortem_penalty(
    stock: Dict[str, Any],
    portfolio: Optional[Dict[str, Any]],
) -> tuple:
    """종목 ticker 가 최근 postmortem.failures 에 있으면 time-decay soft penalty.

    portfolio["postmortem"]["windows"] 의 7d/14d/30d 에서 매칭된 ticker 중
    가장 최신 (days 작은) window 의 경과일로 지수 감쇠 적용.
    halflife=30일 → penalty = -2.0 * 0.5 ** (days/30).

    Returns:
        (penalty: float<=0, memo: dict or None)
    """
    if not portfolio:
        return 0.0, None
    ticker = stock.get("ticker")
    if not ticker:
        return 0.0, None
    pm = portfolio.get("postmortem") or {}
    windows = pm.get("windows") or {}
    # 구 포맷 폴백: windows 없으면 top-level failures 를 30d 로 취급
    if not windows and pm.get("failures"):
        windows = {"30d": {"failures": pm["failures"]}}
    if not windows:
        return 0.0, None

    # window key → days 정수 (가장 최신부터 탐색)
    parsed = []
    for k, v in windows.items():
        try:
            d = int(str(k).rstrip("d"))
            parsed.append((d, v))
        except (ValueError, TypeError):
            continue
    parsed.sort(key=lambda x: x[0])  # 가장 최근 (7d) 먼저

    for days, w in parsed:
        for f in (w.get("failures") or []):
            if f.get("ticker") == ticker:
                decay = 0.5 ** (days / _PM_HALFLIFE_DAYS)
                penalty = -_PM_MAX_PENALTY * decay
                memo = {
                    "window": f"{days}d",
                    "days_since": days,
                    "type": f.get("type"),
                    "actual_return": f.get("actual_return"),
                    "misleading_factor": f.get("misleading_factor"),
                    "lesson": f.get("lesson") or f.get("postmortem"),
                    "penalty": round(penalty, 2),
                    "decay_factor": round(decay, 3),
                    "halflife_days": int(_PM_HALFLIFE_DAYS),
                }
                return penalty, memo
    return 0.0, None


def _compute_fact_score(
    stock: Dict[str, Any],
    portfolio: Optional[Dict[str, Any]] = None,
    macro_override: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """객관적 수치 기반 종합 점수 (0~100). V5: Graham + CANSLIM 컴포넌트 포함.
    V6: IC/ICIR 피드백으로 가중치 자동 조정.
    Brain Audit §7: regime-aware mean-reversion bonus (위기장에서 비활성)."""
    const = _load_constitution()
    w_raw = (const.get("fact_score") or {}).get("weights") or {}
    w = dict(w_raw)

    ic_adj = _load_ic_adjustments()
    ic_applied = {}
    if ic_adj.get("status") == "ok":
        for ic_factor, wk in _IC_TO_WEIGHT_KEY.items():
            adj = ic_adj["adjustments"].get(ic_factor)
            if adj and wk in w:
                mult = adj["multiplier"]
                original = w[wk]
                w[wk] = round(original * mult, 4)
                if mult != 1.0:
                    ic_applied[wk] = {"original": original, "adjusted": w[wk],
                                      "multiplier": mult, "status": adj["status"]}

    # 모든 직접 component get을 _safe_float 으로 감싸 None/NaN/문자열을 50으로 normalize.
    # (수집기가 dict 내부에 None 을 넣어도 종목 단위 polyfill 작동)
    mf = stock.get("multi_factor", {})
    multi_factor_score = _safe_float(mf.get("multi_score"), 50.0)

    consensus = stock.get("consensus", {})
    consensus_score = _safe_float(consensus.get("consensus_score"), 50.0)

    pred = stock.get("prediction", {})
    prediction_score = _clip(_safe_float(pred.get("up_probability"), 50.0))

    bt = stock.get("backtest", {})
    backtest_score = _backtest_to_score(bt)

    timing = stock.get("timing", {})
    timing_score = _safe_float(timing.get("timing_score"), 50.0)

    cm = stock.get("commodity_margin", {})
    commodity_score = _commodity_to_score(cm)

    export_score = _export_to_score(stock)

    moat_score = _compute_moat_score(stock)
    graham_score = _compute_graham_score(stock)
    canslim_score = _compute_canslim_score(stock)

    # Phase 3: 증권사 리포트 + DART 사업보고서 AI 분석 컴포넌트
    analyst_report = stock.get("analyst_report_summary") or {}
    analyst_score = _safe_float(analyst_report.get("analyst_sentiment_score"), 50.0)

    dart_analysis = stock.get("dart_business_analysis") or {}
    dart_health = _safe_float(dart_analysis.get("business_health_score"), 50.0)

    # #2a Perplexity 외부 리스크 — risk_level → 점수 매핑.
    # 스캔 미호출 종목은 50 (중립) 유지 → 부당 감점 없음.
    # 초기 가중치 0.02 (2%) — IC/ICIR 3개월 관찰 후 조정.
    _RISK_SCORE_MAP = {"LOW": 60.0, "MODERATE": 40.0, "HIGH": 15.0, "CRITICAL": 5.0}
    ext_risk = stock.get("external_risk") or {}
    _risk_level = str(ext_risk.get("risk_level", "")).upper()
    perplexity_risk_score = _RISK_SCORE_MAP.get(_risk_level, 50.0)

    components = {
        "multi_factor": multi_factor_score,
        "consensus": consensus_score,
        "prediction": prediction_score,
        "backtest": backtest_score,
        "timing": timing_score,
        "commodity_margin": commodity_score,
        "export_trade": export_score,
        "moat_quality": moat_score,
        "graham_value": graham_score,
        "canslim_growth": canslim_score,
        "analyst_report": analyst_score,
        "dart_health": dart_health,
        "perplexity_risk": perplexity_risk_score,
    }

    total = 0.0
    for key, val in components.items():
        total += val * w.get(key, 0)

    # 퀀트 팩터 보너스: alpha_combined가 있으면 Fact Score에 가산
    # V6: IC 서브팩터 평균 multiplier로 보너스 스케일링 (아래 블록에서 적용)
    alpha_combined = stock.get("alpha_combined", {})
    alpha_score = alpha_combined.get("score")
    alpha_bonus = 0.0
    if alpha_score is not None and alpha_combined.get("method") != "fallback":
        components["alpha_combined"] = alpha_score

    # 퀀트 서브팩터 요약 (있으면)
    quant_sub = mf.get("quant_factors", {})
    if quant_sub:
        for qk, default in [("momentum", 50), ("quality", 50), ("volatility", 50), ("mean_reversion", 50)]:
            v = quant_sub.get(qk, default)
            components[f"quant_{qk}"] = v if isinstance(v, (int, float)) else default

    # IC 서브팩터 보정: alpha_combined 보너스 스케일링
    alpha_ic_scale = 1.0
    if ic_adj.get("status") == "ok":
        sub_mults = []
        for sf in _IC_SUBFACTORS:
            adj_info = ic_adj["adjustments"].get(sf)
            if adj_info:
                sub_mults.append(adj_info["multiplier"])
        if sub_mults:
            alpha_ic_scale = sum(sub_mults) / len(sub_mults)
            alpha_ic_scale = max(0.5, min(1.3, alpha_ic_scale))

    if alpha_score is not None and alpha_combined.get("method") != "fallback":
        alpha_bonus = (alpha_score - 50) * 0.08 * alpha_ic_scale
        total += alpha_bonus

    # ── KIS 데이터 기반 보너스 (KR 종목) ──
    kis_bonus = _compute_kis_fact_bonus(stock)
    if kis_bonus["bonus"] != 0:
        total += kis_bonus["bonus"]
        components["kis_analysis"] = kis_bonus["score"]

    # ── Brain Audit §7: IC-validated technical mean-reversion bonus ──
    # backfill (2020~2026, n=1355) 결과 fact_score 의 모멘텀 가중이 거꾸로
    # (STRONG_BUY avg +2.35% vs CAUTION avg +4.06%). 부호 반전 sub-score 가산.
    # 1단계 (보수적): 가중치 0.07 → 0.03 — STRONG_BUY n=8 → n=30+ 회복 목표.
    # 2단계 (regime-aware): VIX>30 또는 panic/cape_bubble 시 비활성 —
    #   inflation_2022 같은 위기장에서 가격 하락 → mean-reversion 점수 ↑ →
    #   거시 신호와 충돌하는 것 방지.
    tmr_score = _compute_technical_mean_reversion_score(stock)
    if tmr_score is not None:
        components["technical_mean_reversion"] = tmr_score
        if _is_regime_panic(portfolio, macro_override):
            tmr_bonus = 0.0  # 위기장: bonus 비활성
            components["technical_mean_reversion_disabled_regime"] = True
        else:
            tmr_bonus = (tmr_score - 50) * 0.03  # ±50 → ±1.5 max
        total += tmr_bonus

    # ── Brain Audit §11: DART KR fundamental mean-reversion bonus ──
    # KR backfill (n=248, 30종목 10년) 검증 — high ROE/op_margin 후 mean-reversion.
    # KRW 종목만, regime-aware (panic/cape 시 비활성).
    krmr_score = _compute_kr_fundamental_mean_reversion_score(stock)
    if krmr_score is not None:
        components["kr_fundamental_mean_reversion"] = krmr_score
        if _is_regime_panic(portfolio, macro_override):
            krmr_bonus = 0.0
            components["kr_fundamental_mean_reversion_disabled_regime"] = True
        else:
            krmr_bonus = (krmr_score - 50) * 0.03  # ±50 → ±1.5 max
        total += krmr_bonus

    # ── Phase 3 §15: 거버넌스 시그널 (자사주 + 대주주 변동) ──
    # DartScout fetch_treasury_stock / fetch_major_shareholder_changes 결과 활용
    governance_bonus = 0.0
    governance_penalty = 0.0
    governance_meta: List[str] = []

    # 자사주 — 매입 우세 = 주주환원, 처분 우세 = 자금조달/지분매각 의심
    treasury = stock.get("treasury_stock") or {}
    if isinstance(treasury, dict):
        ts_signal = treasury.get("signal")
        net_change = treasury.get("net_change", 0) or 0
        if ts_signal == "positive" or (isinstance(net_change, (int, float)) and net_change > 0):
            governance_bonus += 1.5
            governance_meta.append("treasury_net_acq+1.5")
        elif ts_signal == "warning" or (isinstance(net_change, (int, float)) and net_change < 0):
            governance_penalty += 1.0
            governance_meta.append("treasury_net_dsp-1.0")

    # 대주주 변동 — delta_pct_pt 기준 (5%p 이상 감소 = 강한 경고)
    sh_changes = stock.get("major_shareholder_changes") or []
    if isinstance(sh_changes, list):
        for ch in sh_changes:
            if not isinstance(ch, dict):
                continue
            delta = ch.get("delta_pct_pt", 0)
            try:
                d = float(delta)
            except (TypeError, ValueError):
                continue
            # 5%p 이상 감소 = 강한 경고 (내부자 매도)
            if d <= -5.0:
                governance_penalty += 2.0
                governance_meta.append(f"major_shareholder_drop({d:+.1f}p)-2.0")
                break  # 한 번만 적용 (중복 방지)
            elif d > 0:
                governance_bonus += 1.0
                governance_meta.append(f"major_shareholder_up({d:+.1f}p)+1.0")
                break

    if governance_bonus or governance_penalty:
        # §24 governance cap — 이론 최대 bonus 2.5 (자사주 +1.5 + 대주주 +1.0),
        # 이론 최대 penalty 3.0 (자사주 -1.0 + 대주주 -2.0).
        # 미래 확장 (규제 리스크 등 추가 시) 에서 극단 누적 방어 — cap ±3.0.
        GOV_CAP = 3.0
        governance_bonus = min(governance_bonus, GOV_CAP)
        governance_penalty = min(governance_penalty, GOV_CAP)
        if governance_bonus == GOV_CAP:
            governance_meta.append("gov_bonus_capped")
        if governance_penalty == GOV_CAP:
            governance_meta.append("gov_penalty_capped")
        components["governance_bonus"] = round(governance_bonus, 2)
        components["governance_penalty"] = round(governance_penalty, 2)
        total += governance_bonus - governance_penalty
        # audit metadata — 어떤 조건이 발동했는지 + cap 적용 여부
        stock.setdefault("data_quality_fixes", []).extend(governance_meta)

    # §26: Postmortem 종목별 time-decay penalty
    # portfolio["postmortem"].windows 의 failures 에서 현재 ticker 매칭 시,
    # window 기반 근사 경과일로 지수 감쇠 soft penalty 부과.
    # halflife=30일: 0일 -2.0, 30일 -1.0, 60일 -0.5, 90일 -0.25.
    # strategy_evolver 의 "전체 패턴→constitution" 경로와 역할 분리 (종목 단위).
    pm_penalty, pm_memo = _compute_postmortem_penalty(stock, portfolio)
    if pm_penalty < 0:
        components["postmortem_penalty"] = round(pm_penalty, 2)
        total += pm_penalty
        stock["postmortem_memo"] = pm_memo
        stock.setdefault("data_quality_fixes", []).append("postmortem_caution")

    if not isinstance(total, (int, float)) or math.isnan(total) or math.isinf(total):
        total = 0.0

    result = {
        "score": round(_clip(total)),
        "components": {k: round(v, 1) for k, v in components.items() if isinstance(v, (int, float))},
    }
    if ic_applied:
        result["ic_adjustments"] = ic_applied
    return result


def _compute_kis_fact_bonus(stock: Dict[str, Any]) -> Dict[str, Any]:
    """KIS 데이터(재무비율/투자의견/추정실적/수급) → Fact 보너스."""
    if stock.get("currency") == "USD":
        return {"bonus": 0, "score": 50, "detail": {}}

    bonus = 0.0
    detail = {}

    # 1) 투자의견/목표가 보정
    #    (ROE/부채/유동비율은 graham_value + moat_quality에서 이미 반영 → 중복 제거)
    cons = stock.get("consensus", {})
    kis_target = cons.get("kis_target_price", 0)
    current = stock.get("current_price", 0) or stock.get("close", 0)
    if kis_target and current and current > 0:
        upside = (kis_target - current) / current * 100
        if upside > 30:
            bonus += 3
            detail["target_upside"] = f"+{upside:.0f}%"
        elif upside > 15:
            bonus += 1.5
            detail["target_upside"] = f"+{upside:.0f}%"
        elif upside < -10:
            bonus -= 2
            detail["target_upside"] = f"{upside:.0f}%"

    # 2) 프로그램매매 방향성
    #    (외인/기관 수급은 export_trade에서 전담 → 중복 제거)
    pgm = stock.get("kis_program_trade", {})
    pgm_net = pgm.get("net_buy_3d", 0)
    if pgm_net:
        if pgm_net > 0:
            bonus += 1
            detail["program_net"] = "매수 우위"
        elif pgm_net < 0:
            bonus -= 1
            detail["program_net"] = "매도 우위"

    total_score = _clip(50 + bonus / 0.15) if bonus else 50
    return {"bonus": round(bonus, 2), "score": round(total_score, 1), "detail": detail}


def _backtest_to_score(bt: Dict[str, Any]) -> float:
    """백테스트 결과 → 0~100 점수."""
    if not bt or bt.get("total_trades", 0) == 0:
        return 50.0
    wr = bt.get("win_rate", 50)
    sharpe = bt.get("sharpe_ratio", 0)
    score = wr * 0.6 + _clip(sharpe * 20 + 50) * 0.4
    return _clip(score)


def _commodity_to_score(cm: Dict[str, Any]) -> float:
    """원자재 마진 안심 점수 → 0~100 정규화."""
    pr = cm.get("primary") or cm
    ms = pr.get("margin_safety_score")
    if ms is None:
        return 50.0
    return _clip(float(ms))


def _export_to_score(stock: Dict[str, Any]) -> float:
    """수출입/수급 데이터 기반 점수. US: Finnhub 내부자+기관 데이터로 대체."""
    is_us = stock.get("currency") == "USD"

    if is_us:
        score = 50.0
        insider = stock.get("insider_sentiment") or {}
        mspr = insider.get("mspr", 0)
        if mspr > 0:
            score += min(mspr * 3, 15)
        elif mspr < 0:
            score += max(mspr * 3, -15)

        inst = stock.get("institutional_ownership") or {}
        inst_chg = inst.get("change_pct", 0)
        if inst_chg > 5:
            score += 10
        elif inst_chg < -5:
            score -= 10

        consensus = stock.get("analyst_consensus") or {}
        buy = consensus.get("buy", 0)
        sell = consensus.get("sell", 0)
        total = buy + consensus.get("hold", 0) + sell
        if total > 0:
            buy_pct = buy / total
            if buy_pct > 0.7:
                score += 8
            elif buy_pct < 0.3:
                score -= 8

        return _clip(score)

    cons = stock.get("consensus", {})
    warnings = cons.get("warnings", [])
    has_divergence = any("기관 낙관 주의" in w for w in warnings)

    vc = stock.get("value_chain") or {}
    has_vc_bonus = vc.get("active", False)

    score = 50.0
    if has_vc_bonus:
        score += int(vc.get("score_bonus", 0))
    if has_divergence:
        score -= 15

    # KIS 외인/기관 순매수 반영
    flow = stock.get("flow", {})
    fg = flow.get("kis_foreign_net", 0)
    inst = flow.get("kis_institution_net", 0)
    if fg > 0 and inst > 0:
        score += 8
    elif fg > 0 or inst > 0:
        score += 4
    elif fg < 0 and inst < 0:
        score -= 8
    elif fg < 0 or inst < 0:
        score -= 4

    return _clip(score)


# ─── Sentiment Score ─────────────────────────────────────────

def _compute_sentiment_score(
    stock: Dict[str, Any],
    portfolio: Dict[str, Any],
) -> Dict[str, Any]:
    """심리/감성 기반 종합 점수 (0~100)."""
    const = _load_constitution()
    w = (const.get("sentiment_score") or {}).get("weights") or {}

    sent = stock.get("sentiment", {})
    news_score = sent.get("score", 50)

    x_sent = portfolio.get("x_sentiment", {})
    x_score = x_sent.get("score", 50) if x_sent else 50

    macro = portfolio.get("macro", {})
    mood_score = macro.get("market_mood", {}).get("score", 50)

    cons = stock.get("consensus", {})
    opinion_num = cons.get("investment_opinion_numeric")
    if opinion_num is not None:
        try:
            cons_opinion_score = _clip(float(opinion_num) * 20)
        except (TypeError, ValueError):
            cons_opinion_score = 50.0
    else:
        cons_opinion_score = 50.0

    # 크립토 매크로 센서 반영 (보조 가중치)
    crypto = portfolio.get("crypto_macro", {})
    crypto_temp = 50.0
    if crypto.get("available"):
        comp = crypto.get("composite", {})
        crypto_temp = comp.get("score", 50)

    # CNN Fear & Greed (주식시장 심리)
    mfg = portfolio.get("market_fear_greed", {})
    mfg_score = 50.0
    if mfg.get("ok"):
        mfg_score = float(mfg.get("value", 50))

    social = stock.get("social_sentiment") or {}
    social_score = social.get("score", 50) if social else 50

    components = {
        "news_sentiment": news_score,
        "x_sentiment": x_score,
        "market_mood": mood_score,
        "consensus_opinion": cons_opinion_score,
        "crypto_macro": crypto_temp,
        "market_fear_greed": mfg_score,
        "social_sentiment": social_score,
    }

    # 가중치 합이 1.0이 되도록 정규화 (constitution 미정의 키는 기본값 적용)
    _default_w = {
        "news_sentiment": 0.25, "x_sentiment": 0.18, "market_mood": 0.18,
        "consensus_opinion": 0.12, "crypto_macro": 0.08,
        "market_fear_greed": 0.10, "social_sentiment": 0.09,
    }
    active_w = {}
    w_sum = 0.0
    for key in components:
        weight = w.get(key, _default_w.get(key, 0))
        active_w[key] = weight
        w_sum += weight

    # ── Brain Audit §12 (production 오심 #1, 삼성전자 2026-04-13): ──
    # consensus_opinion ≥ 95 (만점 직전 과열) → 호재 소진 패턴 → 가중치 ×0.7 dampen.
    # 외국인 매도 반전 시점 자주 출현 — 컨센서스 100점 자체가 contrarian 신호.
    if components.get("consensus_opinion", 50) >= 95:
        original_w = active_w.get("consensus_opinion", 0)
        active_w["consensus_opinion"] = original_w * 0.7
        w_sum = w_sum - original_w + active_w["consensus_opinion"]

    total = 0.0
    if w_sum > 0:
        norm = 1.0 / w_sum
        for key, val in components.items():
            total += val * active_w.get(key, 0) * norm

    # ── Retail sentiment 그룹 cap (Brain Audit §1-C) ──
    # x_sentiment(X/Twitter) + social_sentiment(news+naver+reddit+stocktwits 합산) 의 합산 기여가
    # 전체 sentiment_score 의 RETAIL_CAP(=20%) 을 넘지 않도록 제한.
    # 4개 retail 소스가 동시 펌프되는 밈 종목에서 sentiment_score 가 인위적 부풀림되는 위험 방어.
    RETAIL_GROUP_KEYS = ("x_sentiment", "social_sentiment")
    RETAIL_CAP = 0.20  # 전체 sentiment_score 기여 최대 20%
    retail_excess = 0.0
    if w_sum > 0:
        norm = 1.0 / w_sum
        retail_raw_score = sum(
            components.get(k, 50) * active_w.get(k, 0) * norm
            for k in RETAIL_GROUP_KEYS
        )
        retail_cap_score = RETAIL_CAP * 100  # = 20 점
        if retail_raw_score > retail_cap_score:
            retail_excess = retail_raw_score - retail_cap_score
            total -= retail_excess

    if not isinstance(total, (int, float)) or math.isnan(total) or math.isinf(total):
        total = 0.0

    return {
        "score": round(_clip(total)),
        "components": {k: round(v, 2) if isinstance(v, (int, float)) else v
                       for k, v in components.items()},
        "retail_cap_applied": retail_excess > 0,
        "retail_excess_score": round(retail_excess, 2),
    }


# ─── VCI v2.0 (Verity Contrarian Index + Cohen Checklist) ───

def _cohen_contrarian_checks(
    fact_score: float,
    stock: Dict[str, Any],
    portfolio: Dict[str, Any],
) -> Dict[str, Any]:
    """Steve Cohen 1987 역발상 체크리스트.
    패닉 구간에서 팩트가 좋은 종목의 역발상 매수 근거를 정량화한다."""
    macro = portfolio.get("macro", {})
    vix = macro.get("vix", {}).get("value", 0)
    mood = macro.get("market_mood", {}).get("score", 50)
    crypto = portfolio.get("crypto_macro", {})

    checks = []
    passed = 0

    # 1. 하락 원인: 수급(강제 청산) vs 펀더멘털 붕괴
    is_supply_driven = fact_score >= 60 and mood < 30
    checks.append({
        "name": "수급발 하락 (펀더멘털 아닌 강제 청산)",
        "passed": is_supply_driven,
    })
    if is_supply_driven:
        passed += 1

    # 2. VIX 역사적 극단
    vix_extreme = vix >= 40
    checks.append({
        "name": f"VIX 역사적 극단 ({vix})",
        "passed": vix_extreme,
    })
    if vix_extreme:
        passed += 1

    # 3. 크립토 디커플링 (BTC가 나스닥과 분리 움직임 = 독자적 헤지 신호)
    btc_corr = 0.5
    if crypto.get("available"):
        corr_data = crypto.get("btc_nasdaq_corr", {})
        if corr_data.get("ok"):
            btc_corr = corr_data.get("correlation", 0.5)
    crypto_decoupled = btc_corr < 0.3
    checks.append({
        "name": f"크립토 디커플링 (상관 {btc_corr:.2f})",
        "passed": crypto_decoupled,
    })
    if crypto_decoupled:
        passed += 1

    # 4. 기관 흡수(Absorption) 신호 — 외인+기관 순매수 + 가격 변동 안정
    flow = stock.get("flow", {})
    fg_net = flow.get("kis_foreign_net", 0)
    inst_net = flow.get("kis_institution_net", 0)
    # US: Finnhub 내부자 + 기관 보유 변화로 대체
    if stock.get("currency") == "USD":
        insider = stock.get("insider_sentiment") or {}
        inst_own = stock.get("institutional_ownership") or {}
        absorption = insider.get("mspr", 0) > 0 and inst_own.get("change_pct", 0) > 0
    else:
        absorption = fg_net > 0 and inst_net > 0
    checks.append({
        "name": "기관 흡수 신호 (순매수 + 가격 안정)",
        "passed": absorption,
    })
    if absorption:
        passed += 1

    const = _load_constitution()
    cohen_cfg = const.get("panic_stages", {}).get("cohen_checklist", {})
    bonus_per = cohen_cfg.get("bonus_per_check", 3)
    max_bonus = cohen_cfg.get("max_bonus", 12)

    bonus = min(passed * bonus_per, max_bonus)

    return {
        "checks": checks,
        "passed": passed,
        "total": len(checks),
        "bonus": bonus,
    }


def _compute_vci(
    fact: float,
    sentiment: float,
    stock: Optional[Dict[str, Any]] = None,
    portfolio: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """팩트와 심리의 괴리율 계산.
    V4: Cohen 역발상 체크리스트 보너스를 반영한 enhanced VCI."""
    base_vci = round(fact - sentiment)

    const = _load_constitution()
    th = const.get("vci", {}).get("thresholds", {})
    strong_buy = th.get("strong_contrarian_buy", 25)
    mild_buy = th.get("mild_contrarian_buy", 15)
    mild_sell = th.get("mild_contrarian_sell", -15)
    strong_sell = th.get("strong_contrarian_sell", -25)

    # V4: Cohen 체크리스트 적용 (팩트 좋은데 심리 비관일 때만)
    cohen = None
    cohen_bonus = 0
    if base_vci >= 20 and stock is not None and portfolio is not None:
        cohen = _cohen_contrarian_checks(fact, stock, portfolio)
        cohen_bonus = cohen["bonus"]

    # 버블 경계에서도 반대 방향 보정
    bubble_penalty = 0
    if base_vci <= -20 and stock is not None:
        # Soros 반사성: 심리만 좋고 팩트 나쁜 경우 추가 패널티
        funding_overheat = False
        if portfolio:
            crypto = portfolio.get("crypto_macro", {})
            if crypto.get("available"):
                fr = crypto.get("funding_rate", {})
                if fr.get("ok") and fr.get("rate_pct", 0) >= 0.05:
                    funding_overheat = True
        if funding_overheat:
            bubble_penalty = -5

    vci = base_vci + cohen_bonus + bubble_penalty

    if vci >= strong_buy:
        signal = "STRONG_CONTRARIAN_BUY"
        label = "팩트 좋은데 심리 과도 비관 → 역발상 매수"
    elif vci >= mild_buy:
        signal = "CONTRARIAN_BUY"
        label = "팩트 우위 — 시장이 아직 미반영"
    elif vci > mild_sell:
        signal = "ALIGNED"
        label = "팩트·심리 정렬 — 추세 추종 유효"
    elif vci > strong_sell:
        signal = "CONTRARIAN_SELL"
        label = "심리 과열 — 팩트 대비 고평가 주의"
    else:
        signal = "STRONG_CONTRARIAN_SELL"
        label = "심리만 좋고 팩트 나쁨 → 버블 경계"

    result = {
        "vci": vci,
        "base_vci": base_vci,
        "signal": signal,
        "label": label,
    }
    if cohen is not None:
        result["cohen_checklist"] = cohen
    if bubble_penalty:
        result["bubble_penalty"] = bubble_penalty
    return result


# ─── Red Flag Detection ─────────────────────────────────────

def _parse_event_date(event_date: Any) -> Optional[_date]:
    """event_date 입력(str/datetime/date/None) → date or None."""
    if event_date is None:
        return None
    if isinstance(event_date, _datetime):
        return event_date.date()
    if isinstance(event_date, _date):
        return event_date
    if isinstance(event_date, str):
        try:
            return _datetime.strptime(event_date[:10], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return None
    return None


def _compute_freshness(
    event_date: Any,
    drop_since_event_pct: Optional[float] = None,
    today: Optional[_date] = None,
) -> tuple[str, float, Optional[int]]:
    """이벤트 신선도 계산.

    Returns: (freshness, weight, days_since_event)

    - 발생일 없음            → ("FRESH", 1.0, None)  # 정적 지표(부채/PER 등) 기본값
    - days_since_event ≤ 7   → ("FRESH",   1.0)
    - days_since_event ≤ 30  → ("STALE",   0.5)
    - days_since_event > 30  → ("EXPIRED", 0.0)

    가격 반응 보정:
      이벤트 후 -10% 이상 하락 시 FRESH 도 STALE 로 강제 강등
      ('이미 시장에 반영된 악재' — 두 번 차감 금지).
      EXPIRED 는 이미 0 → 추가 강등 의미 없음.
    """
    parsed = _parse_event_date(event_date)
    if parsed is None:
        return ("FRESH", 1.0, None)

    if today is None:
        today = now_kst().date()
    days = max(0, (today - parsed).days)

    if days <= 7:
        freshness, weight = "FRESH", 1.0
    elif days <= 30:
        freshness, weight = "STALE", 0.5
    else:
        freshness, weight = "EXPIRED", 0.0

    if (
        drop_since_event_pct is not None
        and drop_since_event_pct <= -10
        and freshness == "FRESH"
    ):
        freshness, weight = "STALE", 0.5

    return (freshness, weight, days)


def _make_flag(
    text: str,
    event_date: Any = None,
    drop_since_event_pct: Optional[float] = None,
) -> Dict[str, Any]:
    """레드플래그 dict 빌더. freshness 자동 계산.

    스키마: {text, event_date(iso str|None), freshness, days_since_event, weight}
    """
    freshness, weight, days = _compute_freshness(event_date, drop_since_event_pct)
    parsed = _parse_event_date(event_date)
    return {
        "text": text,
        "event_date": parsed.isoformat() if parsed else None,
        "freshness": freshness,
        "days_since_event": days,
        "weight": weight,
    }


def _sec_risk_event_date(stock: Dict[str, Any], portfolio: Dict[str, Any]) -> Optional[str]:
    """portfolio.sec_risk_scan.filings 에서 해당 ticker 의 가장 최근 filed_date 조회."""
    ticker = (stock.get("ticker") or "").upper()
    if not ticker:
        return None
    scan = portfolio.get("sec_risk_scan") or {}
    filings = scan.get("filings") or []
    dates: list[str] = []
    for f in filings:
        if (f.get("ticker") or "").upper() != ticker:
            continue
        fd = f.get("filed_date")
        if isinstance(fd, str) and fd:
            dates.append(fd[:10])
    return max(dates) if dates else None


def _detect_red_flags(
    stock: Dict[str, Any],
    portfolio: Dict[str, Any],
) -> Dict[str, Any]:
    """레드플래그 자동 감지. auto_avoid / downgrade_one 분류 + 이벤트 신선도 가중.

    반환 dict:
      auto_avoid (list[str])           — 후방 호환용 텍스트 (EXPIRED 제외)
      downgrade  (list[str])           — 후방 호환용 텍스트 (EXPIRED 제외)
      auto_avoid_detail (list[dict])   — 전체 audit 메타 (EXPIRED 포함)
      downgrade_detail  (list[dict])   — 전체 audit 메타 (EXPIRED 포함)
      has_critical (bool)              — FRESH/STALE auto_avoid 1건 이상
      downgrade_count (float)          — weight 합 (예: STALE=0.5 기여)
    """
    auto_avoid_d: list[Dict[str, Any]] = []
    downgrade_d: list[Dict[str, Any]] = []
    is_us = stock.get("currency") == "USD"

    risk_kw = stock.get("detected_risk_keywords") or []
    if risk_kw:
        auto_avoid_d.append(_make_flag(f"위험 키워드 감지: {', '.join(risk_kw)}"))

    sec_risk = stock.get("sec_risk_flags") or []
    if sec_risk:
        unique_kw = list(dict.fromkeys(sec_risk))[:3]
        sec_event_date = _sec_risk_event_date(stock, portfolio)
        downgrade_d.append(_make_flag(
            f"SEC 8-K 리스크 공시: {', '.join(unique_kw)}",
            event_date=sec_event_date,
        ))

    if is_us:
        sec_fin = stock.get("sec_financials") or {}
        us_fcf = sec_fin.get("fcf")
        us_debt_ratio = sec_fin.get("debt_ratio") or stock.get("debt_ratio", 0)
        if us_fcf is not None and us_fcf < 0 and us_debt_ratio > 80:
            auto_avoid_d.append(_make_flag(f"FCF ${us_fcf/1e6:,.0f}M + 부채 {us_debt_ratio:.0f}%"))
        elif us_fcf is not None and us_fcf < 0:
            downgrade_d.append(_make_flag(f"FCF ${us_fcf/1e6:,.0f}M (음수)"))

        insider = stock.get("insider_sentiment") or {}
        mspr = insider.get("mspr", 0)
        if mspr < US_INSIDER_MSPR_PENALTY:
            downgrade_d.append(_make_flag(f"내부자 MSPR {mspr:.2f} (대량 매도)"))

        opts = stock.get("options_flow") or {}
        pc_ratio = opts.get("put_call_ratio")
        avg_iv = opts.get("avg_iv")
        if pc_ratio is not None and pc_ratio > US_PUT_CALL_BEARISH:
            downgrade_d.append(_make_flag(f"약세 옵션 시그널: P/C {pc_ratio:.2f}"))
        if avg_iv is not None and avg_iv > US_IV_PERCENTILE_WARN:
            downgrade_d.append(_make_flag(f"고변동성 경고: IV {avg_iv:.0f}%"))

        short = stock.get("short_interest") or {}
        short_pct = short.get("short_pct")
        if short_pct is not None and short_pct > 20:
            downgrade_d.append(_make_flag(f"공매도 비율 {short_pct:.1f}%"))
    else:
        dart = stock.get("dart_financials", {})
        cf = dart.get("cashflow", {})
        fcf = cf.get("free_cashflow")
        debt = stock.get("debt_ratio", 0)
        if fcf is not None and fcf < 0 and debt > 80:
            auto_avoid_d.append(_make_flag(f"FCF 마이너스({fcf/1e8:,.0f}억) + 부채 {debt:.0f}%"))
        elif fcf is not None and fcf < 0:
            downgrade_d.append(_make_flag(f"FCF 마이너스({fcf/1e8:,.0f}억)"))

        # KIS 공매도 비율 경고
        ks = stock.get("kis_short_sale", {})
        short_r = ks.get("avg_short_ratio_5d", 0)
        if short_r > 15:
            auto_avoid_d.append(_make_flag(f"공매도 비율 5일 평균 {short_r:.1f}% (과다)"))
        elif short_r > 8:
            downgrade_d.append(_make_flag(f"공매도 비율 주의 {short_r:.1f}%"))

        # KIS 신용잔고 경고
        kc = stock.get("kis_credit_balance", {})
        credit_rate = kc.get("credit_rate", 0)
        if credit_rate > 10:
            downgrade_d.append(_make_flag(f"신용잔고율 {credit_rate:.1f}% (레버리지 과다)"))
        elif credit_rate > 5:
            downgrade_d.append(_make_flag(f"신용잔고율 주의 {credit_rate:.1f}%"))

        # KIS 재무비율 직접 검증
        kfr = stock.get("kis_financial_ratio", {})
        if kfr.get("source") == "kis":
            kis_debt = kfr.get("debt_ratio", 0)
            kis_roe = kfr.get("roe", 0)
            if kis_debt > 300:
                auto_avoid_d.append(_make_flag(f"부채비율 {kis_debt:.0f}% (KIS 기준)"))
            elif kis_debt > 200:
                downgrade_d.append(_make_flag(f"고부채 {kis_debt:.0f}% (KIS 기준)"))
            if kis_roe < -20:
                downgrade_d.append(_make_flag(f"ROE {kis_roe:.1f}% (KIS 기준)"))

    # V5: Graham PBR×PER 기준 위반
    _per = stock.get("per") or stock.get("price_to_earnings")
    _pbr = stock.get("pbr") or stock.get("price_to_book")
    if _per is not None and _pbr is not None:
        try:
            pb_pe = float(_pbr) * float(_per)
            if pb_pe > 22.5 and float(_per) > 0 and float(_pbr) > 0:
                downgrade_d.append(_make_flag(f"PBR×PER {pb_pe:.1f} > 22.5 (Graham 기준)"))
        except (TypeError, ValueError):
            pass

    macro = portfolio.get("macro", {})
    vix = macro.get("vix", {}).get("value", 0)
    mf_score = stock.get("multi_factor", {}).get("multi_score", 50)
    if vix > 35 and mf_score < 50:
        auto_avoid_d.append(_make_flag(f"VIX {vix} + 멀티팩터 {mf_score}"))

    cons_warnings = stock.get("consensus", {}).get("warnings", [])
    if not is_us and any("기관 낙관 주의" in w for w in cons_warnings):
        downgrade_d.append(_make_flag("컨센서스↑ vs 수출↓ 괴리"))

    cm = stock.get("commodity_margin", {})
    pr = cm.get("primary") or cm
    ms = pr.get("margin_safety_score")
    if ms is not None and float(ms) < 30:
        cm_ticker = pr.get("commodity_ticker", "원자재")
        pct = pr.get("commodity_20d_pct", "?")
        downgrade_d.append(_make_flag(f"{cm_ticker} 급변({pct}%) + 마진안심 {ms}"))

    timing = stock.get("timing", {})
    ts = timing.get("timing_score", 50)
    if ts <= 25:
        downgrade_d.append(_make_flag(f"타이밍 스코어 {ts} — 진입 부적합"))

    earnings = stock.get("earnings", {})
    next_e = earnings.get("next_earnings")
    if next_e:
        from datetime import datetime
        try:
            d = datetime.strptime(next_e[:10], "%Y-%m-%d")
            days = (d - datetime.now()).days
            if 0 <= days <= 1:
                # next_earnings 는 미래 이벤트 — freshness 미적용 (event_date 생략)
                downgrade_d.append(_make_flag(f"실적 발표 D-{days}"))
        except (ValueError, TypeError):
            pass

    # ── KIS 시장전반 크로스체크 ──
    ticker = stock.get("ticker", "")
    kis_mkt = portfolio.get("kis_market", {})
    if kis_mkt and not is_us:
        short_top = kis_mkt.get("short_sale_rank", [])
        for item in short_top[:10]:
            if item.get("mksc_shrn_iscd", "") == str(ticker).zfill(6):
                downgrade_d.append(_make_flag("공매도 시장 상위 10 종목 (KIS)"))
                break
        fi_list = kis_mkt.get("foreign_institution", [])
        for item in fi_list[:15]:
            if item.get("mksc_shrn_iscd", "") == str(ticker).zfill(6):
                ntby = int(item.get("ntby_qty", 0) or 0)
                if ntby < 0:
                    downgrade_d.append(_make_flag("외인·기관 순매도 상위 (KIS)"))
                break

    # ── 후방 호환: text-only 리스트 (EXPIRED 제외 — weight=0 이므로 표시 가치 없음) ──
    auto_avoid_text = [d["text"] for d in auto_avoid_d if d["freshness"] != "EXPIRED"]
    downgrade_text = [d["text"] for d in downgrade_d if d["freshness"] != "EXPIRED"]
    has_critical = any(d["freshness"] != "EXPIRED" for d in auto_avoid_d)
    weighted_dc = round(sum(d["weight"] for d in downgrade_d), 2)

    return {
        "auto_avoid": auto_avoid_text,
        "downgrade": downgrade_text,
        "auto_avoid_detail": auto_avoid_d,
        "downgrade_detail": downgrade_d,
        "has_critical": has_critical,
        "downgrade_count": weighted_dc,
    }


# ─── V4: Panic Stage Detection (Soros Reflexivity) ──────────

def _detect_panic_stage(
    vix: float, mood: float, spread: Optional[float], sp_chg: float,
) -> Optional[Dict[str, Any]]:
    """Soros 반사성 이론 기반 패닉 4단계 판별.
    Stage 3(패닉) 구간에서 Cohen 역발상 매수 가능성을 열어둔다."""
    const = _load_constitution()
    stages = const.get("panic_stages", {}).get("stages", {})

    # Stage 3: 패닉 — VIX 극단 + 극도의 공포
    if vix >= 40 and mood < 15:
        stg = stages.get("panic", {})
        msg = (
            f"[패닉 3단계] VIX {vix} / 무드 {mood}점 — "
            "강제 청산·Quality Liquidation 구간. "
            "Cohen 역발상: VCI 극단 시 선별 매수 허용"
        )
        return {
            "mode": "panic_stage3",
            "label": stg.get("label", "패닉"),
            "stage": 3,
            "message": msg,
            "reason": msg,
            "max_grade": stg.get("max_grade", "WATCH"),
            "contrarian_upgrade": stg.get("contrarian_upgrade", True),
        }

    # Stage 4: 절망(Wyckoff 누적) — VIX 하락 중 + 가격 안정화(S&P 하락 완화)
    # Stage 2와 범위가 겹치므로, S&P 변화율로 "하락 가속 vs 안정화" 구분
    if 25 <= vix < 40 and 10 <= mood < 25 and sp_chg > -1.0:
        stg = stages.get("despair", {})
        msg = (
            f"[패닉 4단계] VIX {vix} / 무드 {mood}점 / S&P {sp_chg:+.1f}% — "
            "강제 매도 소진, Wyckoff 누적 구간. 분할 매수 재개"
        )
        return {
            "mode": "panic_stage4",
            "label": stg.get("label", "절망"),
            "stage": 4,
            "message": msg,
            "reason": msg,
            "max_grade": stg.get("max_grade", "BUY"),
            "contrarian_upgrade": True,
        }

    # Stage 2: 두려움 — 기관 리스크 관리 발동 (아직 하락 중)
    if vix >= 30 and mood < 30:
        stg = stages.get("fear", {})
        msg = (
            f"[패닉 2단계] VIX {vix} / 무드 {mood}점 — "
            "기관 리스크 관리 발동, 패시브 환매 압력"
        )
        return {
            "mode": "panic_stage2",
            "label": stg.get("label", "두려움"),
            "stage": 2,
            "message": msg,
            "reason": msg,
            "max_grade": stg.get("max_grade", "WATCH"),
            "contrarian_upgrade": False,
        }

    # Stage 1: 부정 — 하락 초기
    if vix >= 20 and mood < 50 and (
        (spread is not None and spread < 0.3) or sp_chg < -1.5
    ):
        stg = stages.get("denial", {})
        msg = (
            f"[패닉 1단계] VIX {vix} / 무드 {mood}점 / S&P {sp_chg:+.1f}% — "
            "하락 초기, 신규 진입 축소 권고"
        )
        return {
            "mode": "panic_stage1",
            "label": stg.get("label", "부정"),
            "stage": 1,
            "message": msg,
            "reason": msg,
            "max_grade": stg.get("max_grade", "BUY"),
            "contrarian_upgrade": False,
        }

    return None


# ─── V4: Bridgewater Economic Quadrant ──────────────────────

def detect_economic_quadrant(portfolio: Dict[str, Any]) -> Dict[str, Any]:
    """Bridgewater All-Weather 4분면: 성장 × 인플레이션.
    FRED GDP/CPI 또는 매크로 프록시로 분면을 판별한다."""
    macro = portfolio.get("macro", {})
    fred = macro.get("fred") or {}

    gdp_growth = fred.get("gdp_growth", {}).get("value")
    cpi_yoy = fred.get("cpi_yoy", {}).get("value")

    if gdp_growth is None:
        pmi = fred.get("ism_pmi", {}).get("value")
        if pmi is not None:
            gdp_growth = float(pmi) - 50
        else:
            mood = macro.get("market_mood", {}).get("score", 50)
            gdp_growth = (mood - 50) * 0.06

    if cpi_yoy is None:
        pce = fred.get("pce_yoy", {}).get("value")
        if pce is not None:
            cpi_yoy = float(pce)
        else:
            cpi_yoy = 2.5

    gdp_growth = float(gdp_growth) if gdp_growth is not None else 0
    cpi_yoy = float(cpi_yoy)

    growth_up = gdp_growth > 1.5
    inflation_up = cpi_yoy > 3.0

    if growth_up and inflation_up:
        quadrant = "growth_up_inflation_up"
    elif growth_up and not inflation_up:
        quadrant = "growth_up_inflation_down"
    elif not growth_up and inflation_up:
        quadrant = "growth_down_inflation_up"
    else:
        quadrant = "growth_down_inflation_down"

    const = _load_constitution()
    q_cfg = const.get("economic_quadrant", {}).get("quadrants", {}).get(quadrant, {})

    return {
        "quadrant": quadrant,
        "label": q_cfg.get("label", quadrant),
        "favored": q_cfg.get("favored", []),
        "unfavored": q_cfg.get("unfavored", []),
        "crypto_bias": q_cfg.get("crypto_bias", "neutral"),
        "gdp_growth": round(gdp_growth, 2),
        "cpi_yoy": round(cpi_yoy, 2),
    }


# ─── V4.1: Bond Regime Integration ───────────────────────────

import logging as _logging
logger = _logging.getLogger(__name__)
_br_logger = logger


def _load_bond_regime() -> Dict[str, Any]:
    """portfolio.json bonds 섹션에서 bond_regime 읽기.
    없으면 중립 기본값 반환."""
    _defaults = {
        "rate_environment": "unknown",
        "curve_shape":      "unknown",
        "credit_cycle":     "neutral",
        "recession_signal": False,
        "macro_override":   False,
    }
    try:
        bonds = read_section("bonds")
        regime = bonds.get("bond_regime", {})
        return {k: regime.get(k, v) for k, v in _defaults.items()}
    except Exception as e:
        _br_logger.warning(f"[verity_brain] bond_regime 로드 실패: {e}")
        return _defaults


def _reclassify_signal(vci: float) -> str:
    """VCI 점수 → 시그널 재분류 (verity_constitution vci.thresholds 동기화)."""
    if vci >= 75:
        return "STRONG_BUY"
    if vci >= 60:
        return "BUY"
    if vci >= 45:
        return "WATCH"
    if vci >= 30:
        return "CAUTION"
    return "AVOID"


def _apply_bond_regime(brain_result: Dict[str, Any], bond_regime: Dict[str, Any]) -> Dict[str, Any]:
    """bond_regime 신호를 VCI 보정 및 macro_override에 반영.

    규칙:
    1. recession_signal → macro_override 강제 + 전 종목 VCI -10
    2. curve_shape=inverted → 금융/리츠 -5, 채권/금 ETF +5
    3. credit_cycle=stress → HY 관련 AVOID 강제
    4. rate_environment → 팩터 바이어스 힌트 주입
    """
    if not bond_regime:
        return brain_result

    recession    = bond_regime.get("recession_signal", False)
    curve_shape  = bond_regime.get("curve_shape", "unknown")
    credit_cycle = bond_regime.get("credit_cycle", "neutral")
    rate_env     = bond_regime.get("rate_environment", "unknown")

    if recession:
        existing_ov = brain_result.get("macro_override")
        if existing_ov is None:
            brain_result["macro_override"] = {
                "mode": "bond_recession",
                "label": "채권 경기침체 신호",
                "message": "수익률 곡선 역전 — 방어 모드 전환",
                "reason": "yield_curve_inversion",
                "max_grade": "WATCH",
            }
        else:
            secondary = existing_ov.get("secondary_signals", [])
            secondary.append({"mode": "bond_recession", "label": "채권 경기침체 신호", "max_grade": "WATCH"})
            existing_ov["secondary_signals"] = secondary
            existing_max = existing_ov.get("max_grade", "WATCH")
            if GRADE_ORDER.index("WATCH") > GRADE_ORDER.index(existing_max):
                existing_ov["max_grade"] = "WATCH"

        for s in brain_result.get("stocks", []):
            orig = s.get("brain_score", 0)
            new_score = max(0, orig - 10)
            s["brain_score"] = new_score
            s["bond_penalty"] = -10
            # 기존 grade보다 완화 금지: red_flags/macro_override cap 보존
            recomputed = _score_to_grade(new_score)
            prev_grade = s.get("grade", "AVOID")
            s["grade"] = _cap_grade(recomputed, prev_grade)
            s["grade_confidence"] = _grade_confidence(new_score, s["grade"])

    if curve_shape == "inverted":
        penalty_cats = {"sector_financial", "alternative_reit", "sector_finance"}
        bonus_cats = {"bond_us_long", "bond_us_mid", "alternative_gold",
                      "commodity_gold", "bond_kr", "bond_us_agg"}
        for s in brain_result.get("stocks", []):
            cat = s.get("category", "")
            sector = (s.get("sector") or "").lower()
            if cat in penalty_cats or "금융" in sector or "부동산" in sector:
                new_score = max(0, s.get("brain_score", 0) - 5)
                s["brain_score"] = new_score
                s["bond_curve_adj"] = -5
                recomputed = _score_to_grade(new_score)
                prev_grade = s.get("grade", "AVOID")
                s["grade"] = _cap_grade(recomputed, prev_grade)
                s["grade_confidence"] = _grade_confidence(new_score, s["grade"])

    if credit_cycle == "stress":
        for s in brain_result.get("stocks", []):
            cat = s.get("category", "")
            name = s.get("name", "").lower()
            if "hy" in cat or "high_yield" in name or "하이일드" in name:
                s["grade"] = "AVOID"
                s["brain_score"] = min(s.get("brain_score", 30), 25)
                s["credit_override"] = "HY_STRESS_AVOID"
                s["grade_confidence"] = "firm"

    rate_hint = {
        "rate_high_restrictive":  {"value_bias": +5, "momentum_bias": -5},
        "rate_elevated":          {"value_bias": +2, "momentum_bias": -2},
        "rate_normal":            {"value_bias":  0, "momentum_bias":  0},
        "rate_low_accommodative": {"value_bias": -5, "momentum_bias": +5},
    }
    brain_result["bond_regime_applied"] = {
        "rate_environment": rate_env,
        "curve_shape":      curve_shape,
        "credit_cycle":     credit_cycle,
        "recession_signal": recession,
        "factor_bias":      rate_hint.get(rate_env, {}),
    }

    return brain_result


# ─── Macro Override (V4 통합) ───────────────────────────────

def detect_macro_override(portfolio: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """매크로 환경이 극단적일 때 포트폴리오 레벨 오버라이드.
    V5.1: 모든 활성 시그널을 수집 → 최고 심각도 primary + 나머지 secondary.
    기존 first-match-return 방식의 시그널 누락 문제 해결."""
    macro = portfolio.get("macro", {})
    vix = macro.get("vix", {}).get("value", 0)
    spread = macro.get("yield_spread", {}).get("value", 1)
    sp_chg = macro.get("sp500", {}).get("change_pct", 0)
    mood = macro.get("market_mood", {}).get("score", 50)

    y10: Optional[float] = None
    fred = macro.get("fred") or {}
    if fred.get("dgs10", {}).get("value") is not None:
        y10 = float(fred["dgs10"]["value"])
    else:
        u10 = macro.get("us_10y", {}).get("value", 0)
        if u10:
            y10 = float(u10)

    _GRADE_SEVERITY = {
        "AVOID": 5, "CAUTION": 4, "WATCH": 3, "BUY": 2, "STRONG_BUY": 1,
    }

    signals: List[Dict[str, Any]] = []

    def _add(sig: Dict[str, Any]) -> None:
        sig["_severity"] = _GRADE_SEVERITY.get(sig.get("max_grade", "BUY"), 2)
        signals.append(sig)

    # ── Soros 패닉 4단계 ──
    panic_stage = _detect_panic_stage(vix, mood, spread, sp_chg)
    if panic_stage is not None:
        panic_stage["quadrant"] = detect_economic_quadrant(portfolio)
        _add(panic_stage)

    # ── VIX/스프레드 패닉 ──
    if vix > 35 or (spread is not None and spread < 0 and sp_chg < -3):
        if not panic_stage:
            msg = f"VIX {vix} / 스프레드 {spread}%p / S&P {sp_chg:+.1f}% — 신규 매수 금지, 현금 확보"
            _add({"mode": "panic", "label": "패닉 모드", "message": msg, "reason": msg, "max_grade": "WATCH"})

    # ── 금리 방패 ──
    if y10 is not None and y10 >= MACRO_DGS10_DEFENSE_PCT:
        msg = f"미 10년 국채 {y10:.2f}% (≥{MACRO_DGS10_DEFENSE_PCT}%) — 할인율·밸류에이션 압력, 현금 비중 확대 권고"
        _add({"mode": "yield_defense", "label": "금리 방패", "message": msg, "reason": msg, "max_grade": "WATCH"})

    # ── 유포리아 ──
    if vix < 12 and mood > 80:
        msg = f"VIX {vix} / 분위기 {mood}점 — 과열 경고, 차익 실현 고려"
        _add({"mode": "euphoria", "label": "과열 모드", "message": msg, "reason": msg, "max_grade": "BUY"})

    # ── KIS VI 연쇄 ──
    kis_mkt = portfolio.get("kis_market", {})
    if kis_mkt:
        vi_stocks = kis_mkt.get("vi_status", [])
        if len(vi_stocks) >= 5 and vix > 25:
            names = ", ".join(s.get("hts_kor_isnm", "?") for s in vi_stocks[:3])
            msg = f"VI 발동 {len(vi_stocks)}종목 ({names} 등) + VIX {vix} — 시장 급변동 경계"
            _add({"mode": "vi_cascade", "label": "VI 연쇄 경보", "message": msg, "reason": msg, "max_grade": "WATCH"})

    # ── 한국 기준금리 ──
    ecos = macro.get("ecos") or {}
    kr_rate = ecos.get("korea_policy_rate", {}).get("value")
    if kr_rate is not None and float(kr_rate) >= 4.5 and mood < 40:
        msg = f"한국 기준금리 {kr_rate}% + 무드 {mood}점 — 고금리·비관 복합, 보수적 접근"
        _add({"mode": "kr_rate_defense", "label": "기준금리 방패", "message": msg, "reason": msg, "max_grade": "WATCH"})

    # ── 리세션 확률 ──
    rec = fred.get("us_recession_smoothed_prob", {}).get("pct")
    if rec is not None and float(rec) >= 50:
        msg = f"미국 리세션 확률 {rec}% — 극단적 방어 국면"
        _add({"mode": "recession_alert", "label": "리세션 경보", "message": msg, "reason": msg, "max_grade": "WATCH"})

    # ── Perplexity 이벤트 ──
    for ei in portfolio.get("event_insights", []):
        if ei.get("severity") == "CRITICAL" and "error" not in ei:
            ev_name = ei.get("event", "매크로 이벤트")
            msg = f"Perplexity 실시간 분석: {ev_name} — CRITICAL 영향. {ei.get('us_impact', '')[:60]}"
            _add({"mode": "perplexity_event_critical", "label": "이벤트 긴급 경보", "message": msg, "reason": msg, "max_grade": "WATCH"})
            break

    # ── 펀드 플로우 ──
    ff = portfolio.get("fund_flows", {})
    if ff.get("ok"):
        rot_sig = ff.get("rotation_signal", "neutral")
        rot_detail = ff.get("rotation_detail", {})
        if rot_sig == "cash_flight" and rot_detail.get("confidence", 0) >= 60:
            msg = f"펀드 플로우: 주식·채권 동반 유출 (현금 선호). {rot_detail.get('detail', '')}"
            _add({"mode": "fund_flow_cash_flight", "label": "자금 이탈 경보", "message": msg, "reason": msg, "max_grade": "WATCH"})

    # ── CFTC COT ──
    cot = portfolio.get("cftc_cot", {})
    if cot.get("ok"):
        cot_summary = cot.get("summary", {})
        cot_signal = cot_summary.get("overall_signal", "neutral")
        cot_conviction = cot_summary.get("conviction_level", 0)
        if cot_signal == "bearish" and cot_conviction >= 70:
            sp_data = cot.get("instruments", {}).get("SP500", {})
            net_str = f"S&P500 순포지션 {sp_data.get('net_managed_money', 0):+,}" if sp_data.get("ok") else ""
            msg = f"CFTC COT 기관 순매도 강화 (확신도 {cot_conviction}%). {net_str}"
            _add({"mode": "cot_bearish", "label": "기관 포지셔닝 약세 경보", "message": msg, "reason": msg, "max_grade": "BUY"})

    # ── CNN Fear & Greed ──
    mfg = portfolio.get("market_fear_greed", {})
    if mfg.get("ok"):
        mfg_val = mfg.get("value", 50)
        if mfg_val >= 90:
            msg = f"CNN Fear & Greed {mfg_val} (극도탐욕) — 시장 과열, 신규 매수 자제"
            _add({"mode": "market_extreme_greed", "label": "시장 극단 탐욕 경보", "message": msg, "reason": msg, "max_grade": "BUY"})

    # ── 크립토 과열 ──
    crypto = portfolio.get("crypto_macro", {})
    if crypto.get("available"):
        fng = crypto.get("fear_and_greed", {})
        funding = crypto.get("funding_rate", {})
        kimchi = crypto.get("kimchi_premium", {})
        fng_val = fng.get("value", 50) if fng.get("ok") else 50
        funding_pct = funding.get("rate_pct", 0) if funding.get("ok") else 0
        kimchi_pct = kimchi.get("premium_pct", 0) if kimchi.get("ok") else 0

        if fng_val >= 80 and funding_pct >= 0.06 and kimchi_pct >= 5:
            parts = [f"크립토 F&G {fng_val}(극단 탐욕)", f"펀딩비 {funding_pct:+.3f}%", f"김프 {kimchi_pct:+.1f}%"]
            msg = " / ".join(parts) + " — 위험자산 전체 과열, 차익 실현 고려"
            _add({"mode": "crypto_overheat", "label": "크립토 과열 경보", "message": msg, "reason": msg, "max_grade": "BUY"})

    # ── Shiller CAPE 버블 ──
    # constitution.json:577~581 의 cape_bubble_mode(CAPE>30 시 신규 매수 보수적·포지션 축소)을 실제 등급 cap으로 연결.
    # max_grade=WATCH 로 panic_stages / cboe_panic 과 동일 패턴 (BUY/STRONG_BUY 종목이 WATCH 이하로 강제됨).
    cape = fred.get("cape", {}).get("value")
    if cape is not None:
        try:
            cape_val = float(cape)
            if cape_val > 30:
                msg = f"Shiller CAPE {cape_val:.1f} > 30 — 역사적 버블 수준 (1929/2000/2007 전조)"
                _add({
                    "mode": "cape_bubble",
                    "label": "CAPE 버블",
                    "message": msg,
                    "reason": msg,
                    "max_grade": "WATCH",
                })
        except (TypeError, ValueError):
            pass

    # ── 섹터 로테이션 vs quadrant 정합성 (constitution drift 탐지) ──
    # KOSPI 5일 누적 수익률 기준 top3/bottom3 가 현재 quadrant 의 favored/unfavored 와
    # 어긋나면 secondary_signal 로 첨부. 텔레그램 알림은 모듈 내부에서 자동 발송.
    try:
        from api.intelligence.sector_rotation_detector import (
            detect_sector_rotation, to_macro_signal as _sector_to_signal,
        )
        # 이미 panic_stage 가 quadrant 를 계산했으면 재사용 (중복 호출 회피)
        _quad = None
        for _s in signals:
            if isinstance(_s.get("quadrant"), dict):
                _quad = _s["quadrant"]
                break
        if _quad is None:
            _quad = detect_economic_quadrant(portfolio)
        _rot = detect_sector_rotation(portfolio, quadrant_info=_quad, notify=True)
        portfolio["sector_rotation_check"] = _rot
        _sig = _sector_to_signal(_rot)
        if _sig:
            _add(_sig)
    except Exception as _e:
        logger.debug("sector_rotation_detector skipped: %s", _e)

    if not signals:
        return None

    # 최고 심각도를 primary로, 나머지를 secondary_signals로 보존
    signals.sort(key=lambda s: s["_severity"], reverse=True)
    primary = signals[0]
    primary.pop("_severity", None)

    secondary = []
    for s in signals[1:]:
        s.pop("_severity", None)
        secondary.append({"mode": s["mode"], "label": s["label"], "max_grade": s["max_grade"]})

    if secondary:
        primary["secondary_signals"] = secondary
        combined_msgs = [primary.get("label", "")]
        combined_msgs += [s["label"] for s in secondary]
        primary["combined_warning"] = " + ".join(combined_msgs)

    # max_grade는 전체 시그널 중 가장 제한적인 것 적용
    most_restrictive = "STRONG_BUY"
    for s in signals:
        g = s.get("max_grade", "BUY")
        if GRADE_ORDER.index(g) > GRADE_ORDER.index(most_restrictive):
            most_restrictive = g
    primary["max_grade"] = most_restrictive

    return primary


# ─── Group Structure Bonus ────────────────────────────────────

def _compute_group_structure_bonus(stock: Dict[str, Any]) -> float:
    """지분구조(대주주 집중도, NAV 할인) → Brain Score 보너스."""
    gs = stock.get("group_structure")
    if not gs:
        return 0.0

    bonus = 0.0

    shareholders = gs.get("major_shareholders", [])
    if shareholders:
        top_pct = _safe_float(shareholders[0].get("ownership_pct"), 0.0)
        if top_pct >= 30:
            bonus += 2
        elif top_pct >= 20:
            bonus += 1

    nav = gs.get("nav_analysis", {})
    discount = _safe_float(nav.get("nav_discount_pct"))
    if discount is not None:
        if discount < -30:
            bonus += 3
        elif discount < -15:
            bonus += 1.5
        elif discount > 50:
            bonus -= 2

    # Brain Audit §2-C: 명시적 cap [-3, +5]. 향후 가산 조건 추가 시 무한 누적 방어.
    return round(min(5.0, max(-3.0, bonus)), 2)


# ─── Brain Score & Final Judgment ────────────────────────────

GRADE_ORDER = ["STRONG_BUY", "BUY", "WATCH", "CAUTION", "AVOID"]
GRADE_LABELS = {
    "STRONG_BUY": "강력 매수",
    "BUY": "매수",
    "WATCH": "관망",
    "CAUTION": "주의",
    "AVOID": "회피",
}


def _score_to_grade(score: float) -> str:
    const = _load_constitution()
    grades = const.get("decision_tree", {}).get("grades", {})
    for g in GRADE_ORDER:
        info = grades.get(g, {})
        if score >= info.get("min_brain_score", 999):
            return g
    return "AVOID"


def _downgrade(grade: str, steps: int = 1) -> str:
    idx = GRADE_ORDER.index(grade) if grade in GRADE_ORDER else len(GRADE_ORDER) - 1
    new_idx = min(idx + steps, len(GRADE_ORDER) - 1)
    return GRADE_ORDER[new_idx]


def _cap_grade(grade: str, max_grade: str) -> str:
    """등급을 max_grade 이하로 제한."""
    g_idx = GRADE_ORDER.index(grade) if grade in GRADE_ORDER else len(GRADE_ORDER) - 1
    m_idx = GRADE_ORDER.index(max_grade) if max_grade in GRADE_ORDER else 0
    return GRADE_ORDER[max(g_idx, m_idx)]


# ─── V4: Position Sizing Guide (Kelly Criterion) ────────────

def _compute_position_guide(
    brain_score: int,
    grade: str,
    red_flags: Dict[str, Any],
) -> Dict[str, Any]:
    """Kelly Criterion 간소화 + McMurtrie 상한 기반 포지션 비중 가이드.
    brain_score를 승률 프록시로 사용, 보수적 payoff ratio 적용."""
    const = _load_constitution()
    ps = const.get("position_sizing", {})
    kelly_params = ps.get("kelly_params", {})
    max_pct_map = ps.get("max_position_pct", {})

    b = kelly_params.get("payoff_ratio", 1.5)
    p = brain_score / 100.0
    q = 1.0 - p

    kelly_raw = max(0, (b * p - q) / b) * 100 if b > 0 else 0
    max_pct = max_pct_map.get(grade, 0)

    if red_flags.get("has_critical"):
        recommended = 0.0
        rationale = "레드플래그(즉시회피) — 포지션 불가"
    elif red_flags.get("downgrade_count", 0) >= 2:
        recommended = min(kelly_raw * 0.5, max_pct)
        rationale = f"하향조정 {red_flags['downgrade_count']}건 — 비중 절반 축소"
    else:
        recommended = min(kelly_raw, max_pct)
        rationale = f"Kelly {kelly_raw:.1f}% → {grade} 상한 {max_pct}% 적용"

    return {
        "recommended_pct": round(recommended, 1),
        "kelly_raw_pct": round(kelly_raw, 1),
        "max_pct": max_pct,
        "rationale": rationale,
    }


def _get_brain_weights(quadrant_name: Optional[str] = None) -> Dict[str, float]:
    """경제 사이클 분면에 따른 fact/sentiment 가중치를 반환한다.
    수축기일수록 감성 노이즈가 커지므로 fact 비중을 높인다."""
    const = _load_constitution()
    dt = const.get("decision_tree", {})
    bw = dt.get("brain_weights", {})
    default = bw.get("default", {"fact": 0.70, "sentiment": 0.30})

    override_q = dt.get("quadrant_override")
    if override_q and override_q in bw:
        return bw[override_q]

    if quadrant_name and quadrant_name in bw:
        return bw[quadrant_name]

    return default


def analyze_stock(
    stock: Dict[str, Any],
    portfolio: Dict[str, Any],
    macro_override: Optional[Dict[str, Any]] = None,
    quadrant_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    단일 종목에 대한 Verity Brain 종합 판단.

    Returns:
        brain_score, fact_score, sentiment_score, vci, grade,
        red_flags, reasoning 등을 포함한 dict.
    """
    # Brain Audit §2-D: 모든 강등/상향 단계가 audit 가능하도록 빈 리스트로 초기화.
    stock.setdefault("overrides_applied", [])

    # Brain Audit §13 (production 오심 #2, 현대모비스 2026-04-18):
    # PBR 데이터 오류로 멀티팩터 과소평가 → AVOID → +6.1% 미스.
    # PBR ≤ 0 또는 None 일 때 중립값 1.0 (시장 평균 PBR ≈ 1.5 이지만 보수적으로 1.0).
    # 2-A _safe_float 패턴 동일.
    _pbr_raw = stock.get("pbr")
    try:
        _pbr_v = float(_pbr_raw) if _pbr_raw is not None else None
    except (TypeError, ValueError):
        _pbr_v = None
    if _pbr_v is None or _pbr_v <= 0:
        stock["pbr"] = 1.0
        stock["pbr_normalized_neutral"] = True
        stock.setdefault("data_quality_fixes", []).append("pbr_invalid_to_1.0")

    fact = _compute_fact_score(stock, portfolio=portfolio, macro_override=macro_override)
    sentiment = _compute_sentiment_score(stock, portfolio)
    vci = _compute_vci(fact["score"], sentiment["score"], stock, portfolio)
    red_flags = _detect_red_flags(stock, portfolio)

    fs = float(fact["score"] or 0)
    ss = float(sentiment["score"] or 0)
    vci_val = vci["vci"]

    vci_bonus = 0
    if vci_val > 25 and fs >= 60:
        vci_bonus = 5
    elif vci_val < -25 and fs < 50:
        vci_bonus = -10

    bw = _get_brain_weights(quadrant_name)
    w_fact = bw["fact"]
    w_sent = bw["sentiment"]

    gs_bonus = _compute_group_structure_bonus(stock)

    # V5: Nison 캔들 심리 보너스
    candle_bonus = _compute_candle_psychology_score(stock)

    # V6: 13F 기관 스마트머니 보너스 (US 종목만, 분기 수집 후 존재 시)
    inst_bonus = 0
    if stock.get("currency") == "USD":
        inst_13f = portfolio.get("institutional_13f", {}).get("signal", {})
        if inst_13f.get("ok"):
            ticker_sig = inst_13f.get("ticker_signal", {})
            issuer_key = (stock.get("name") or "").upper()
            matched = ticker_sig.get(issuer_key, {})
            if not matched:
                for k, v in ticker_sig.items():
                    if v.get("issuer", "").upper() in issuer_key or issuer_key in v.get("issuer", "").upper():
                        matched = v
                        break
            if matched:
                iscore = _safe_float(matched.get("score"), 50.0)
                if iscore >= 70:
                    inst_bonus = 3
                elif iscore >= 60:
                    inst_bonus = 1

    red_flag_penalty = min(red_flags["downgrade_count"] * 5, 20)
    raw = fs * w_fact + ss * w_sent + vci_bonus + gs_bonus + candle_bonus + inst_bonus - red_flag_penalty
    if not isinstance(raw, (int, float)) or math.isnan(raw) or math.isinf(raw):
        raw = 0.0
    # Brain Audit §3-C: clip(0, 100) 적용 전 raw 값을 별도 보존.
    # raw 는 100 초과 가능 (이론적 최대 123) — STRONG_BUY 동률 종목의 강도 차이 보존용.
    raw_brain_score = round(raw, 2)
    stock["raw_brain_score"] = raw_brain_score
    brain_score = round(_clip(raw))
    grade = _score_to_grade(brain_score)

    if red_flags["has_critical"]:
        grade = "AVOID"
    elif red_flags["downgrade_count"] >= 1:
        # weighted float → 등급 강등 단계는 int (FRESH 1건=1단계, FRESH 2+ 또는 weighted≥2=2단계)
        steps = 2 if red_flags["downgrade_count"] >= 2 else 1
        grade = _downgrade(grade, steps)

    # Brain Audit §8: AVOID 라벨 재정의 — fact_score 단독으로는 AVOID 부여 금지.
    # backfill 검증 (30종목 5년 8130행) 에서 AVOID 등급 평균 +3.23% > BUY 의 +1.67%.
    # 대형주 universe 의 low brain_score = oversold → mean-reversion 반등 후보.
    # AVOID 는 펀더멘털 결함(has_critical) 또는 macro_override 위기 cap 에만 한정.
    if grade == "AVOID" and not red_flags["has_critical"]:
        grade = "CAUTION"

    # Brain Audit §14 (production 오심 #3, Coinbase 2026-04-18):
    # multi_factor 단독 거부권으로 AVOID 부여돼 +27.3% 미스.
    # brain_score ≥ 55 (펀더멘털 양호) AND ai_upside ≥ 65 (AI 강한 호재) 동시 충족 시
    # AVOID → CAUTION 완화 (외생 이벤트 / 섹터 모멘텀 인정).
    # has_critical 여부 무관 — AI 신호가 회계 노이즈를 압도하는 케이스 허용.
    _ai_upside = float(stock.get("prediction", {}).get("up_probability", 0) or 0)
    if grade == "AVOID" and brain_score >= 55 and _ai_upside >= 65:
        grade = "CAUTION"
        stock.setdefault("overrides_applied", []).append("ai_upside_relax")

    if macro_override:
        max_g = macro_override.get("max_grade", "WATCH")
        _pre_cap = grade
        grade = _cap_grade(grade, max_g)
        if grade != _pre_cap:
            # cap 이 실제 발동했을 때만 overrides_applied 에 mode 기록 (audit 용).
            # primary mode 는 most_restrictive 시그널 = 실제 cap 결정 주체.
            _mo_mode = macro_override.get("mode")
            if _mo_mode and _mo_mode not in stock["overrides_applied"]:
                stock["overrides_applied"].append(_mo_mode)

        # V5.1: 패닉 stage 3+4에서 Cohen 체크 3개 이상 통과 시 한 단계 상향
        #   Stage 3(패닉): STRONG_CONTRARIAN_BUY 필요
        #   Stage 4(절망/Wyckoff 누적): MILD_CONTRARIAN_BUY 이상이면 허용
        #   단, auto_avoid 종목은 펀더멘털 사망 신호 우선 — 역발상 상향 금지
        if macro_override.get("contrarian_upgrade") and not red_flags.get("has_critical"):
            vci_signal = vci.get("signal", "")
            stage = macro_override.get("stage", 0)
            contrarian_ok = (
                vci_signal == "STRONG_CONTRARIAN_BUY"
                or (stage == 4 and vci_signal in ("STRONG_CONTRARIAN_BUY", "CONTRARIAN_BUY"))
            )
            if contrarian_ok:
                cohen = vci.get("cohen_checklist")
                if cohen and cohen["passed"] >= 3:
                    g_idx = GRADE_ORDER.index(grade) if grade in GRADE_ORDER else 2
                    if g_idx > 0:
                        grade = GRADE_ORDER[g_idx - 1]
                        stock["overrides_applied"].append("contrarian_upgrade")

    # ── 경제 사이클 분면별 unfavored 섹터 패널티 ──
    # constitution.json:281~327 의 quadrant.unfavored 정의를 실제 grade 강등으로 연결.
    # 예: 스태그플레이션(growth_down_inflation_up) → "주식/회사채/성장주" unfavored.
    # 이미 has_critical로 AVOID 강제된 종목은 추가 강등 의미 없음.
    quadrant_info = stock.get("quadrant_info", {}) or {}
    unfavored = quadrant_info.get("unfavored", []) or []
    stock_sector = (stock.get("sector") or "").strip()
    if unfavored and stock_sector and not red_flags.get("has_critical"):
        sector_lower = stock_sector.lower()
        matched = next((u for u in unfavored if u and u.lower() in sector_lower), None)
        if matched:
            brain_score = max(0, brain_score - 5)
            grade = _downgrade(grade, 1)
            stock.setdefault("overrides_applied", []).append("quadrant_unfavored")
            stock["quadrant_unfavored_match"] = {
                "quadrant": quadrant_info.get("quadrant"),
                "matched_unfavored": matched,
                "stock_sector": stock_sector,
            }

    # ── Brain Audit §6: score_breakdown (감사용 항목별 기여도 분해) ──
    # 모든 등급 조정이 끝난 직후, position_guide / reasoning 이전에 분해 기록.
    # raw_before_penalty + penalties.red_flag = raw_brain_score (clip 전 합산값).
    fact_contrib = round(fs * w_fact, 1)
    sent_contrib = round(ss * w_sent, 1)
    raw_before = round(
        fs * w_fact + ss * w_sent + vci_bonus + candle_bonus + gs_bonus + inst_bonus, 1
    )
    quadrant_unfav_pen = -5 if "quadrant_unfavored" in (stock.get("overrides_applied") or []) else 0
    stock["score_breakdown"] = {
        "fact_contribution": fact_contrib,
        "sentiment_contribution": sent_contrib,
        "vci_bonus": round(vci_bonus, 1),
        "candle_bonus": round(candle_bonus, 1),
        "gs_bonus": round(gs_bonus, 2),
        "inst_bonus": round(inst_bonus, 1),
        "raw_before_penalty": raw_before,
        "penalties": {
            "red_flag": -round(red_flag_penalty, 1),
            "quadrant_unfavored": quadrant_unfav_pen,
        },
        "final_score": brain_score,
        "raw_brain_score": stock.get("raw_brain_score", brain_score),
        "grade": grade,
        "grade_caps_applied": [
            o for o in (stock.get("overrides_applied") or [])
            if o not in ("quadrant_unfavored", "contrarian_upgrade")
        ],
    }

    # V4: Kelly Criterion 기반 포지션 비중 가이드
    position_guide = _compute_position_guide(brain_score, grade, red_flags)

    reasoning = _build_reasoning(
        stock, fact, sentiment, vci, red_flags, brain_score, grade, macro_override
    )

    return {
        "brain_score": brain_score,
        "raw_brain_score": raw_brain_score,
        "grade": grade,
        "grade_label": GRADE_LABELS.get(grade, grade),
        "fact_score": fact,
        "sentiment_score": sentiment,
        "vci": vci,
        "vci_bonus": vci_bonus,
        "candle_bonus": candle_bonus,
        "inst_13f_bonus": inst_bonus,
        "brain_weights": {"fact": w_fact, "sentiment": w_sent, "quadrant": quadrant_name},
        "red_flag_penalty": red_flag_penalty,
        "red_flags": red_flags,
        "position_guide": position_guide,
        "reasoning": reasoning,
        "macro_override": macro_override.get("mode") if macro_override else None,
    }


def _build_reasoning(
    stock: Dict[str, Any],
    fact: Dict[str, Any],
    sentiment: Dict[str, Any],
    vci: Dict[str, Any],
    red_flags: Dict[str, Any],
    brain_score: int,
    grade: str,
    macro_override: Optional[Dict[str, Any]],
) -> str:
    """사람이 읽을 수 있는 판단 근거 1~3줄 생성."""
    name = stock.get("name", "?")
    parts = []

    parts.append(
        f"{name}: 브레인 {brain_score}점 "
        f"(팩트 {fact['score']} / 심리 {sentiment['score']} / "
        f"VCI {vci['vci']:+d})"
    )

    fc = fact["components"]
    core_keys = {"multi_factor", "consensus", "prediction", "backtest",
                 "timing", "commodity_margin", "export_trade"}
    core_fc = {k: v for k, v in fc.items() if k in core_keys}
    if core_fc:
        top_fact = max(core_fc, key=core_fc.get)
        bottom_fact = min(core_fc, key=core_fc.get)
        parts.append(
            f"팩트 최강 {top_fact}({core_fc[top_fact]:.0f}) "
            f"/ 최약 {bottom_fact}({core_fc[bottom_fact]:.0f})"
        )

    # 퀀트 팩터 인사이트
    quant_parts = []
    mf = stock.get("multi_factor", {})
    qf = mf.get("quant_factors", {})
    if qf:
        def _qf_num(v, fallback=50):
            return v if isinstance(v, (int, float)) else fallback
        mom = _qf_num(qf.get("momentum", 50))
        qual = _qf_num(qf.get("quality", 50))
        vol = _qf_num(qf.get("volatility", 50))
        mr = _qf_num(qf.get("mean_reversion", 50))

        if mom >= 75:
            quant_parts.append(f"모멘텀↑{mom}")
        elif mom <= 25:
            quant_parts.append(f"모멘텀↓{mom}")
        if qual >= 75:
            quant_parts.append(f"퀄리티↑{qual}")
        elif qual <= 25:
            quant_parts.append(f"퀄리티↓{qual}")
        if mr >= 75:
            quant_parts.append(f"평균회귀매수↑{mr}")
        if vol >= 75:
            quant_parts.append(f"저변동↑{vol}")
        elif vol <= 25:
            quant_parts.append(f"고변동↓{vol}")

    if quant_parts:
        parts.append("퀀트: " + " | ".join(quant_parts))

    # V5: Graham + CANSLIM 인사이트
    v5_parts = []
    graham_v = fc.get("graham_value")
    if graham_v is not None and graham_v != 50:
        if graham_v >= 70:
            v5_parts.append(f"Graham가치↑{graham_v:.0f}")
        elif graham_v <= 35:
            v5_parts.append(f"Graham가치↓{graham_v:.0f}")
    canslim_v = fc.get("canslim_growth")
    if canslim_v is not None and canslim_v != 50:
        if canslim_v >= 70:
            v5_parts.append(f"CANSLIM↑{canslim_v:.0f}")
        elif canslim_v <= 35:
            v5_parts.append(f"CANSLIM↓{canslim_v:.0f}")
    if v5_parts:
        parts.append("V5: " + " | ".join(v5_parts))

    # KIS 분석 인사이트
    kis_parts = []
    kis_an = fc.get("kis_analysis")
    if kis_an is not None and kis_an != 50:
        flow = stock.get("flow", {})
        fg = flow.get("kis_foreign_net", 0)
        inst = flow.get("kis_institution_net", 0)
        if fg or inst:
            fg_dir = "매수" if fg > 0 else "매도" if fg < 0 else ""
            inst_dir = "매수" if inst > 0 else "매도" if inst < 0 else ""
            if fg_dir:
                kis_parts.append(f"외인{fg_dir}")
            if inst_dir:
                kis_parts.append(f"기관{inst_dir}")
        ks = stock.get("kis_short_sale", {})
        sr = ks.get("avg_short_ratio_5d", 0)
        if sr > 5:
            kis_parts.append(f"공매도{sr:.1f}%")
        kc = stock.get("kis_credit_balance", {})
        cr = kc.get("credit_rate", 0)
        if cr > 3:
            kis_parts.append(f"신용{cr:.1f}%")
    if kis_parts:
        parts.append("KIS: " + " | ".join(kis_parts))

    gs = stock.get("group_structure")
    if gs:
        gs_parts = []
        shareholders = gs.get("major_shareholders", [])
        if shareholders:
            top = shareholders[0]
            gs_parts.append(f"최대주주 {top.get('name','?')} {top.get('ownership_pct',0)}%")
        nav_d = gs.get("nav_analysis", {}).get("nav_discount_pct")
        if nav_d is not None:
            if nav_d < 0:
                gs_parts.append(f"NAV {nav_d}% 할인")
            elif nav_d > 0:
                gs_parts.append(f"NAV +{nav_d}% 할증")
        if gs_parts:
            parts.append("지분: " + " | ".join(gs_parts))

    if vci["signal"] != "ALIGNED":
        parts.append(f"VCI: {vci['label']}")

    is_us = stock.get("currency") == "USD"
    if is_us:
        us_missing = []
        if not stock.get("analyst_consensus"):
            us_missing.append("애널리스트컨센서스")
        if not stock.get("insider_sentiment"):
            us_missing.append("내부자거래")
        if not stock.get("options_flow"):
            us_missing.append("옵션플로우")
        if not stock.get("sec_financials"):
            us_missing.append("SEC재무")
        if us_missing:
            parts.append(f"US 미수집: {', '.join(us_missing)}")

    if red_flags["auto_avoid"]:
        parts.append(f"레드플래그(즉시회피): {'; '.join(red_flags['auto_avoid'])}")
    elif red_flags["downgrade"]:
        parts.append(f"하향조정: {'; '.join(red_flags['downgrade'])}")

    if macro_override:
        parts.append(f"매크로 {macro_override.get('label', '?')}: {macro_override.get('message', '')}")

    return " | ".join(parts)


# ─── Market Structure Override (V5.2: 만기일 + 프로그램 매매) ─────

def _apply_market_structure_override(
    result: Dict[str, Any],
    portfolio: Dict[str, Any],
) -> Dict[str, Any]:
    """만기일 관망 + 프로그램 매도폭탄을 brain result에 오버라이드 적용."""
    from api.collectors.expiry_calendar import get_expiry_status
    from api.collectors.program_trading_collector import get_program_trading_today

    expiry = get_expiry_status()
    program = portfolio.get("program_trading") or get_program_trading_today()

    market_brain = result.get("market_brain", {})

    position_cap = expiry["position_size_cap"]

    if program.get("sell_bomb"):
        position_cap = 0.0

    market_brain["expiry"] = {
        "watch_level": expiry["watch_level"],
        "reason": expiry["reason"],
        "days_to_kr_option": expiry["days_to_kr_option"],
        "days_to_kr_futures": expiry["days_to_kr_futures"],
        "days_to_us_quad": expiry["days_to_us_quad"],
        "next_kr_option": expiry["next_kr_option"],
        "next_kr_futures": expiry["next_kr_futures"],
        "next_us_quad": expiry["next_us_quad"],
        "chase_buy_allowed": expiry["chase_buy_allowed"],
        "position_size_cap": position_cap,
    }

    market_brain["program_trading"] = {
        "signal": program.get("signal", "NEUTRAL"),
        "arb_net_bn": program.get("arb_net_bn", 0),
        "non_arb_net_bn": program.get("non_arb_net_bn", 0),
        "total_net_bn": program.get("total_net_bn", 0),
        "sell_bomb": program.get("sell_bomb", False),
        "sell_bomb_reason": program.get("sell_bomb_reason"),
    }

    # 만기 FULL_WATCH 또는 매도폭탄 → BUY 종목을 WATCH로 강등
    if not expiry["chase_buy_allowed"] or program.get("sell_bomb"):
        downgrade_reason = (
            program.get("sell_bomb_reason", "프로그램 매도 폭탄")
            if program.get("sell_bomb")
            else expiry["reason"]
        )
        for stock in result.get("stocks", []):
            if stock.get("grade") in ("STRONG_BUY", "BUY"):
                stock["grade"] = "WATCH"
                stock["grade_label"] = "관망"
                stock["grade_confidence"] = _grade_confidence(stock.get("brain_score", 0), "WATCH")
                stock["reasoning"] = (
                    f"[만기/프로그램 강등] {downgrade_reason} | "
                    + stock.get("reasoning", "")
                )
                # Brain Audit §2-D: market_structure 강등 audit
                stock.setdefault("overrides_applied", []).append("market_structure_downgrade")
        # 등급 분포 재집계
        dist = {g: 0 for g in ("STRONG_BUY", "BUY", "WATCH", "CAUTION", "AVOID")}
        for s in result.get("stocks", []):
            g = s.get("grade", "AVOID")
            dist[g] = dist.get(g, 0) + 1
        market_brain["grade_distribution"] = dist

    result["market_brain"] = market_brain
    return result


def _apply_cboe_pcr_override(
    result: Dict[str, Any],
    portfolio: Dict[str, Any],
) -> Dict[str, Any]:
    """CBOE 풋/콜 비율 시그널을 VCI 보정 + 패닉 시 등급 상한 적용."""
    pcr = portfolio.get("cboe_pcr", {})
    if not pcr:
        return result

    market_brain = result.get("market_brain", {})
    vci_adj = pcr.get("vci_adjustment", 0.0)
    panic = pcr.get("panic_trigger", False)
    signal = pcr.get("signal", "NEUTRAL")

    if vci_adj and market_brain.get("vci") is not None:
        orig_vci = market_brain["vci"]
        market_brain["vci"] = round(max(0, min(100, orig_vci + vci_adj)), 2)
        market_brain["vci_signal"] = _reclassify_signal(market_brain["vci"])

    market_brain["cboe_pcr"] = {
        "signal": signal,
        "panic_trigger": panic,
        "vci_adjustment": vci_adj,
        "pcr_latest": pcr.get("total_pcr_latest"),
    }

    if panic:
        max_grade = "WATCH"
        existing_ov = result.get("macro_override")
        if existing_ov is None:
            result["macro_override"] = {
                "mode": "cboe_panic",
                "label": "CBOE 풋/콜 패닉",
                "message": f"PCR 극단 — {pcr.get('panic_reason', '')}",
                "reason": "cboe_pcr_panic",
                "max_grade": max_grade,
            }
        else:
            secondary = existing_ov.get("secondary_signals", [])
            secondary.append({"mode": "cboe_panic", "label": "CBOE 풋/콜 패닉", "max_grade": max_grade})
            existing_ov["secondary_signals"] = secondary

        for s in result.get("stocks", []):
            if s.get("grade") in ("STRONG_BUY", "BUY"):
                s["grade"] = max_grade
                s["grade_label"] = GRADE_LABELS.get(max_grade, max_grade)
                s["grade_confidence"] = _grade_confidence(s.get("brain_score", 0), max_grade)
                s["cboe_downgrade"] = True

    result["market_brain"] = market_brain
    return result


# ─── Batch Analysis ──────────────────────────────────────────

def analyze_all(
    candidates: List[Dict[str, Any]],
    portfolio: Dict[str, Any],
) -> Dict[str, Any]:
    """
    전체 후보 종목 + 포트폴리오에 대한 Verity Brain 일괄 분석.

    Returns:
        {
            "macro_override": {...} or None,
            "market_brain": {...},
            "stocks": [ {...brain result per stock...} ],
        }
    """
    macro_ov = detect_macro_override(portfolio)

    quadrant_info = detect_economic_quadrant(portfolio)
    q_name = quadrant_info.get("quadrant")

    # V6: 레짐 자동 감지 + 팩터 가중치 multiplier
    regime_info: Dict[str, Any] = {}
    try:
        from api.analyzers.macro_adjustments import detect_market_regime
        regime_info = detect_market_regime(portfolio.get("macro", {}))
    except Exception as e:
        logger.debug("Regime detection skipped: %s", e)

    _empty_rf = {
        "auto_avoid": [], "downgrade": [],
        "auto_avoid_detail": [], "downgrade_detail": [],
        "has_critical": False, "downgrade_count": 0, "weighted_penalty": 0,
    }
    stock_results = []
    for stock in candidates:
        # 분면 정보 attach (analyze_stock 내부 unfavored 섹터 패널티 로직이 사용)
        stock["quadrant_info"] = quadrant_info
        try:
            result = analyze_stock(stock, portfolio, macro_ov, quadrant_name=q_name)
        except Exception as exc:
            logger.warning("analyze_stock failed for %s: %s", stock.get("ticker"), exc)
            result = {
                "brain_score": 0, "raw_brain_score": 0.0,
                "grade": "WATCH", "grade_label": "관망",
                "grade_confidence": "firm", "data_coverage": 0.0,
                "fact_score": {"score": 0, "components": {}, "data_coverage": 0.0},
                "sentiment_score": {"score": 0, "components": {}},
                "vci": {"vci": 0}, "vci_bonus": 0, "candle_bonus": 0,
                "brain_weights": {}, "red_flag_penalty": 0,
                "red_flags": _empty_rf,
                "position_guide": {"recommended_pct": 0, "kelly_raw_pct": 0, "max_pct": 0, "rationale": "분석 오류"},
                "reasoning": f"분석 중 오류 발생: {exc}",
                "macro_override": None,
            }
        stock_results.append({
            "ticker": stock.get("ticker"),
            "name": stock.get("name"),
            **result,
        })

    # Brain Audit §3-C: 다중 키 안정 정렬.
    #   1차 brain_score (clip 100) DESC → 등급 그룹화
    #   2차 raw_brain_score (clip 전, 100 초과 가능) DESC → 동률 시 강도 우선
    #   3차 ticker ASC → 그래도 같으면 결정적 순서 보장
    stock_results.sort(key=lambda x: (
        -float(x.get("brain_score", 0) or 0),
        -float(x.get("raw_brain_score", 0) or 0),
        str(x.get("ticker") or ""),
    ))

    scores = [r.get("brain_score", 0) for r in stock_results]
    facts = [(r.get("fact_score") or {}).get("score", 0) for r in stock_results]
    sents = [(r.get("sentiment_score") or {}).get("score", 0) for r in stock_results]

    avg = lambda xs: round(sum(xs) / len(xs)) if xs else 0
    market_brain = {
        "avg_brain_score": avg(scores),
        "avg_fact_score": avg(facts),
        "avg_sentiment_score": avg(sents),
        "avg_vci": avg(facts) - avg(sents),
        "grade_distribution": _count_grades(stock_results),
        "top_picks": [
            {
                "ticker": r["ticker"], "name": r["name"],
                "score": r["brain_score"], "grade": r["grade"],
                "grade_confidence": r.get("grade_confidence", "firm"),
                "data_coverage": r.get("data_coverage", 1.0),
            }
            for r in stock_results if r["grade"] in ("STRONG_BUY", "BUY")
        ][:5],
        "red_flag_stocks": [
            {"ticker": r["ticker"], "name": r["name"],
             "flags": (r.get("red_flags") or _empty_rf)["auto_avoid"] + (r.get("red_flags") or _empty_rf)["downgrade"]}
            for r in stock_results
            if (r.get("red_flags") or _empty_rf).get("has_critical")
            or (r.get("red_flags") or _empty_rf).get("downgrade_count", 0) >= 2
        ],
    }

    # 펀드 플로우 요약 첨부
    ff = portfolio.get("fund_flows", {})
    if ff.get("ok"):
        market_brain["fund_flows"] = {
            "rotation_signal": ff.get("rotation_signal"),
            "rotation_detail": ff.get("rotation_detail", {}).get("detail"),
            "equity_flow": ff.get("equity_flow_score"),
            "bond_flow": ff.get("bond_flow_score"),
            "safe_haven_flow": ff.get("safe_haven_flow_score"),
        }

    # CFTC COT 요약 첨부
    cot = portfolio.get("cftc_cot", {})
    if cot.get("ok"):
        market_brain["cftc_cot"] = {
            "report_date": cot.get("report_date"),
            "summary": cot.get("summary", {}),
            "sp500_net": cot.get("instruments", {}).get("SP500", {}).get("net_managed_money"),
            "gold_net": cot.get("instruments", {}).get("GOLD", {}).get("net_managed_money"),
        }

    # CNN Fear & Greed 요약 첨부
    mfg = portfolio.get("market_fear_greed", {})
    if mfg.get("ok"):
        market_brain["market_fear_greed"] = {
            "value": mfg.get("value"),
            "signal": mfg.get("signal"),
            "description_kr": mfg.get("description_kr"),
            "change_1d": mfg.get("change_1d"),
            "sub_indicators": mfg.get("sub_indicators", {}),
        }

    # 크립토 매크로 센서 요약 첨부
    crypto = portfolio.get("crypto_macro", {})
    if crypto.get("available"):
        market_brain["crypto_macro"] = {
            "composite": crypto.get("composite", {}),
            "fear_and_greed": crypto.get("fear_and_greed", {}).get("value"),
            "funding_rate_pct": crypto.get("funding_rate", {}).get("rate_pct"),
            "kimchi_premium_pct": crypto.get("kimchi_premium", {}).get("premium_pct"),
            "btc_nasdaq_corr": crypto.get("btc_nasdaq_corr", {}).get("correlation"),
            "stablecoin_mcap_b": crypto.get("stablecoin_mcap", {}).get("total_mcap_b"),
        }

    # V4: Bridgewater 경제 사이클 4분면 (이미 위에서 감지)
    market_brain["economic_quadrant"] = quadrant_info
    bw = _get_brain_weights(q_name)
    market_brain["brain_weights"] = {"fact": bw["fact"], "sentiment": bw["sentiment"], "quadrant": q_name}

    # V6: 레짐 감지 결과
    if regime_info:
        market_brain["regime"] = {
            "regime": regime_info.get("regime", "sideways"),
            "confidence": regime_info.get("confidence", 0),
            "method": regime_info.get("method", "unknown"),
        }

    # V6: IC 피드백 루프 상태
    ic_adj = _load_ic_adjustments()
    if ic_adj.get("status") == "ok" and ic_adj.get("log"):
        market_brain["ic_feedback"] = {
            "status": "active",
            "adjustments_count": len([
                v for v in ic_adj["adjustments"].values()
                if v.get("multiplier", 1.0) != 1.0
            ]),
            "log": ic_adj["log"][:10],
        }

    # V5: 버블 탐지 (Mackay/Shiller/Taleb)
    bubble = _detect_bubble_signals(portfolio)
    if bubble["detected"]:
        market_brain["bubble_warning"] = bubble

    result = {
        "macro_override": macro_ov,
        "market_brain": market_brain,
        "stocks": stock_results,
    }

    # V4.1: bond_regime 통합 — 채권 시장 신호로 최종 보정
    bond_regime = _load_bond_regime()
    if bond_regime.get("curve_shape") != "unknown":
        result = _apply_bond_regime(result, bond_regime)

    # V5.2: 만기일 + 프로그램 매매 구조 오버라이드
    result = _apply_market_structure_override(result, portfolio)

    # V5.3: CBOE 풋/콜 비율 시그널 반영
    result = _apply_cboe_pcr_override(result, portfolio)

    return result


def _count_grades(results: List[Dict[str, Any]]) -> Dict[str, int]:
    dist = {g: 0 for g in GRADE_ORDER}
    for r in results:
        g = r.get("grade", "AVOID")
        dist[g] = dist.get(g, 0) + 1
    return dist
