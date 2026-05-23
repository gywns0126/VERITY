"""Mean-reversion sub-scores — KR fundamental + technical.

Backfill IC validated (scripts/dart_kr_backfill.py, historical_replay.py).
원본: api/intelligence/verity_brain.py:605-721 (분해 전).
"""
from __future__ import annotations

import math
from typing import Any, Dict, Optional


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
