"""
모멘텀 팩터 엔진

학술 근거:
  - Jegadeesh & Titman (1993): 3~12개월 과거 수익률이 미래 수익률을 예측
  - Moskowitz, Ooi & Pedersen (2012): 시계열 모멘텀 (TSMOM)

구현 팩터:
  1. 교차 모멘텀 (Cross-Sectional): 유니버스 내 상대 수익률 순위
  2. 시계열 모멘텀 (Time-Series): 자기 자신의 과거 대비 추세
  3. 52주 신고가 근접도 (George & Hwang, 2004)
  4. 가속 모멘텀: 단기 vs 장기 모멘텀 차이
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd


def _safe_pct(current: float, past: float) -> Optional[float]:
    if past is None or past == 0 or current is None:
        return None
    return (current - past) / abs(past) * 100


def compute_momentum_score(
    stock: Dict[str, Any],
    universe: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    단일 종목의 모멘텀 점수 계산 (0~100).

    stock에 필요한 키:
      price, price_1m, price_3m, price_6m, price_12m,
      high_52w, low_52w
    universe: 교차 모멘텀 순위 계산용 전체 종목 리스트 (없으면 시계열만)
    """
    scores: Dict[str, float] = {}
    signals: List[str] = []

    price = stock.get("price") or 0
    p1m = stock.get("price_1m")
    p3m = stock.get("price_3m")
    p6m = stock.get("price_6m")
    p12m = stock.get("price_12m")
    high_52 = stock.get("high_52w") or 0
    low_52 = stock.get("low_52w") or 0

    # --- 1. 시계열 모멘텀 (TSMOM) ---
    # Moskowitz et al.: 12개월 수익률 부호가 미래 방향을 예측
    tsmom_score = 50.0
    ret_12m = _safe_pct(price, p12m)
    ret_6m = _safe_pct(price, p6m)
    ret_3m = _safe_pct(price, p3m)
    ret_1m = _safe_pct(price, p1m)

    # 12-1 모멘텀 (최근 1개월 제외 = 단기 반전 회피, Jegadeesh & Titman)
    ret_12_1 = None
    if ret_12m is not None and ret_1m is not None and p1m:
        past_12m = p12m or 0
        if past_12m > 0:
            ret_12_1 = _safe_pct(p1m, past_12m)

    if ret_12_1 is not None:
        if ret_12_1 > 30:
            tsmom_score = 90
            signals.append(f"12-1M 모멘텀 +{ret_12_1:.1f}% 강력")
        elif ret_12_1 > 15:
            tsmom_score = 75
            signals.append(f"12-1M 모멘텀 +{ret_12_1:.1f}%")
        elif ret_12_1 > 0:
            tsmom_score = 60
        elif ret_12_1 > -15:
            tsmom_score = 40
        elif ret_12_1 > -30:
            tsmom_score = 25
            signals.append(f"12-1M 역모멘텀 {ret_12_1:.1f}%")
        else:
            tsmom_score = 10
            signals.append(f"12-1M 강한 하락 {ret_12_1:.1f}%")
    elif ret_6m is not None:
        if ret_6m > 20:
            tsmom_score = 80
        elif ret_6m > 0:
            tsmom_score = 60
        elif ret_6m > -20:
            tsmom_score = 35
        else:
            tsmom_score = 15

    scores["tsmom"] = tsmom_score

    # --- 2. 52주 신고가 근접도 ---
    # George & Hwang (2004): 52주 고점 대비 비율이 모멘텀보다 강력한 예측자
    high_prox_score = 50.0
    if high_52 > 0 and price > 0:
        proximity = price / high_52
        if proximity >= 0.95:
            high_prox_score = 90
            signals.append(f"52주 고점 {proximity:.0%} 근접")
        elif proximity >= 0.85:
            high_prox_score = 70
        elif proximity >= 0.70:
            high_prox_score = 50
        elif proximity >= 0.55:
            high_prox_score = 30
            signals.append(f"52주 고점 대비 {(1-proximity):.0%} 하락")
        else:
            high_prox_score = 15
            signals.append(f"52주 고점 대비 {(1-proximity):.0%} 급락")

    scores["high_proximity"] = high_prox_score

    # --- 3. 가속 모멘텀 (Acceleration) ---
    # 단기 모멘텀 > 장기 모멘텀이면 가속 중
    accel_score = 50.0
    if ret_3m is not None and ret_12m is not None:
        monthly_3m = ret_3m / 3 if ret_3m else 0
        monthly_12m = ret_12m / 12 if ret_12m else 0
        accel = monthly_3m - monthly_12m

        if accel > 5:
            accel_score = 85
            signals.append("모멘텀 강 가속")
        elif accel > 2:
            accel_score = 70
            signals.append("모멘텀 가속 중")
        elif accel > -2:
            accel_score = 50
        elif accel > -5:
            accel_score = 30
            signals.append("모멘텀 감속")
        else:
            accel_score = 15
            signals.append("모멘텀 급감속")

    scores["acceleration"] = accel_score

    # --- 4. 교차 모멘텀 (Cross-Sectional) ---
    cs_score = 50.0
    if universe and len(universe) >= 5:
        cs_score = _cross_sectional_rank(stock, universe)
        if cs_score >= 80:
            signals.append(f"교차 모멘텀 상위 {100 - cs_score:.0f}%")
        elif cs_score <= 20:
            signals.append(f"교차 모멘텀 하위 {cs_score:.0f}%")

    scores["cross_sectional"] = cs_score

    # --- 종합 점수 ---
    weights = {
        "tsmom": 0.35,
        "high_proximity": 0.25,
        "acceleration": 0.20,
        "cross_sectional": 0.20,
    }

    total = sum(scores[k] * weights[k] for k in weights)
    total = max(0, min(100, round(total)))

    return {
        "momentum_score": total,
        "components": {k: round(v, 1) for k, v in scores.items()},
        "signals": signals[:5],
        "returns": {
            "1m": round(ret_1m, 2) if ret_1m is not None else None,
            "3m": round(ret_3m, 2) if ret_3m is not None else None,
            "6m": round(ret_6m, 2) if ret_6m is not None else None,
            "12m": round(ret_12m, 2) if ret_12m is not None else None,
            "12_1m": round(ret_12_1, 2) if ret_12_1 is not None else None,
        },
    }


def _cross_sectional_rank(
    stock: Dict[str, Any],
    universe: List[Dict[str, Any]],
) -> float:
    """유니버스 내 6개월 수익률 기준 백분위 순위 → 0~100 점수."""
    def _ret6(s: Dict[str, Any]) -> Optional[float]:
        p = s.get("price") or 0
        p6 = s.get("price_6m")
        return _safe_pct(p, p6)

    rets = []
    target_ret = _ret6(stock)
    if target_ret is None:
        return 50.0

    for s in universe:
        r = _ret6(s)
        if r is not None:
            rets.append(r)

    if len(rets) < 5:
        return 50.0

    rank = sum(1 for r in rets if r < target_ret)
    percentile = rank / len(rets) * 100
    return round(max(0, min(100, percentile)), 1)


def enrich_momentum_prices(
    stock: Dict[str, Any],
    ticker_yf: str,
) -> Dict[str, Any]:
    """
    yfinance에서 과거 가격을 가져와 stock dict에 모멘텀 계산용 키 추가.
    이미 값이 있으면 스킵.
    """
    needed = ["price_1m", "price_3m", "price_6m", "price_12m", "high_52w", "low_52w"]
    if all(stock.get(k) is not None for k in needed):
        return stock

    try:
        import yfinance as yf
        t = yf.Ticker(ticker_yf)
        hist = t.history(period="1y")
        if hist.empty or len(hist) < 20:
            return stock

        close = hist["Close"]
        current = float(close.iloc[-1])

        stock.setdefault("price", current)
        stock.setdefault("high_52w", float(close.max()))
        stock.setdefault("low_52w", float(close.min()))

        offsets = {"price_1m": 21, "price_3m": 63, "price_6m": 126, "price_12m": 252}
        for key, days in offsets.items():
            if stock.get(key) is None and len(close) > days:
                stock[key] = float(close.iloc[-days])

    except Exception:
        pass

    return stock
