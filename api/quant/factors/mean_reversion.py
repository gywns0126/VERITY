"""
평균회귀 팩터 엔진

학술 근거:
  - Poterba & Summers (1988): 주가는 장기적으로 평균으로 회귀하는 경향
  - Lo & MacKinlay (1988): 분산비 검정 — 랜덤워크 여부 판별
  - Hurst (1951): Hurst Exponent — 시계열의 장기 기억/추세 vs 평균회귀 특성
  - Ornstein-Uhlenbeck: 연속시간 평균회귀 모델의 반감기 추정

구현 팩터:
  1. 가격 Z-Score: 이동평균 대비 표준편차 위치
  2. RSI 기반 평균회귀 신호
  3. Hurst Exponent 근사: 시계열이 추세형(>0.5)인지 회귀형(<0.5)인지
  4. 볼린저 밴드 % 위치
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd


def compute_mean_reversion_score(stock: Dict[str, Any]) -> Dict[str, Any]:
    """
    단일 종목의 평균회귀 점수 계산 (0~100).
    높은 점수 = 평균회귀 매수 기회가 큼 (과매도 + 회귀 특성 확인)

    stock에 필요한 키:
      price, ma20, ma60, ma120 (또는 technical dict 내부)
      technical.rsi, technical.bb_position
      price_history (리스트, optional)
    """
    scores: Dict[str, float] = {}
    signals: List[str] = []

    tech = stock.get("technical") or {}
    price = stock.get("price") or 0

    ma20 = tech.get("ma20") or stock.get("ma20")
    ma60 = tech.get("ma60") or stock.get("ma60")
    ma120 = tech.get("ma120") or stock.get("ma120")
    rsi = tech.get("rsi") or 50
    bb_pos = tech.get("bb_position")

    # --- 1. 가격 Z-Score (20일 기준) ---
    zscore_val = _price_zscore(stock)
    z_score_pts = 50.0

    if zscore_val is not None:
        if zscore_val <= -2.0:
            z_score_pts = 95
            signals.append(f"Z-Score {zscore_val:.2f} 극단적 과매도")
        elif zscore_val <= -1.5:
            z_score_pts = 85
            signals.append(f"Z-Score {zscore_val:.2f} 강한 과매도")
        elif zscore_val <= -1.0:
            z_score_pts = 70
            signals.append(f"Z-Score {zscore_val:.2f} 과매도")
        elif zscore_val <= -0.5:
            z_score_pts = 58
        elif zscore_val <= 0.5:
            z_score_pts = 50
        elif zscore_val <= 1.0:
            z_score_pts = 40
        elif zscore_val <= 1.5:
            z_score_pts = 28
            signals.append(f"Z-Score {zscore_val:.2f} 과매수")
        elif zscore_val <= 2.0:
            z_score_pts = 15
            signals.append(f"Z-Score {zscore_val:.2f} 강한 과매수")
        else:
            z_score_pts = 5
            signals.append(f"Z-Score {zscore_val:.2f} 극단적 과매수")

    scores["zscore"] = z_score_pts

    # --- 2. RSI 평균회귀 ---
    rsi_mr_score = 50.0
    if rsi <= 25:
        rsi_mr_score = 92
        signals.append(f"RSI {rsi} 극단적 과매도 — 반등 유력")
    elif rsi <= 35:
        rsi_mr_score = 75
        signals.append(f"RSI {rsi} 과매도 구간")
    elif rsi <= 45:
        rsi_mr_score = 58
    elif rsi <= 55:
        rsi_mr_score = 50
    elif rsi <= 65:
        rsi_mr_score = 42
    elif rsi <= 75:
        rsi_mr_score = 25
        signals.append(f"RSI {rsi} 과매수 — 되돌림 가능")
    else:
        rsi_mr_score = 10
        signals.append(f"RSI {rsi} 극단적 과매수")

    scores["rsi_reversion"] = rsi_mr_score

    # --- 3. 볼린저 밴드 위치 ---
    bb_score = 50.0
    if bb_pos is not None:
        if bb_pos <= 0.05:
            bb_score = 92
            signals.append("볼린저 하단 이탈 — 반등 기대")
        elif bb_pos <= 0.2:
            bb_score = 75
        elif bb_pos <= 0.4:
            bb_score = 60
        elif bb_pos <= 0.6:
            bb_score = 50
        elif bb_pos <= 0.8:
            bb_score = 40
        elif bb_pos <= 0.95:
            bb_score = 25
        else:
            bb_score = 8
            signals.append("볼린저 상단 이탈 — 과열")

    scores["bollinger"] = bb_score

    # --- 4. 이동평균 괴리율 ---
    ma_dev_score = 50.0
    if price > 0 and ma60:
        dev = (price - ma60) / ma60 * 100
        if dev <= -20:
            ma_dev_score = 90
            signals.append(f"MA60 대비 {dev:.1f}% 급괴리")
        elif dev <= -10:
            ma_dev_score = 75
        elif dev <= -5:
            ma_dev_score = 62
        elif dev <= 5:
            ma_dev_score = 50
        elif dev <= 10:
            ma_dev_score = 38
        elif dev <= 20:
            ma_dev_score = 25
        else:
            ma_dev_score = 10

    scores["ma_deviation"] = ma_dev_score

    # --- 5. Hurst Exponent 근사 ---
    hurst = _estimate_hurst(stock)
    hurst_score = 50.0
    if hurst is not None:
        # H < 0.5: 평균회귀 특성 → 평균회귀 전략에 유리
        # H = 0.5: 랜덤워크
        # H > 0.5: 추세 지속
        if hurst < 0.35:
            hurst_score = 85
            signals.append(f"Hurst {hurst:.2f} 강한 회귀 특성")
        elif hurst < 0.45:
            hurst_score = 70
            signals.append(f"Hurst {hurst:.2f} 회귀 특성")
        elif hurst < 0.55:
            hurst_score = 50
        elif hurst < 0.65:
            hurst_score = 35
        else:
            hurst_score = 20
            signals.append(f"Hurst {hurst:.2f} 추세 지속형")

    scores["hurst"] = hurst_score

    # --- 종합 ---
    weights = {
        "zscore": 0.30,
        "rsi_reversion": 0.20,
        "bollinger": 0.15,
        "ma_deviation": 0.15,
        "hurst": 0.20,
    }

    total = sum(scores[k] * weights[k] for k in weights)
    total = max(0, min(100, round(total)))

    return {
        "mean_reversion_score": total,
        "components": {k: round(v, 1) for k, v in scores.items()},
        "signals": signals[:5],
        "metrics": {
            "zscore": round(zscore_val, 3) if zscore_val is not None else None,
            "rsi": rsi,
            "bb_position": round(bb_pos, 3) if bb_pos is not None else None,
            "hurst": round(hurst, 3) if hurst is not None else None,
        },
    }


def _price_zscore(stock: Dict[str, Any]) -> Optional[float]:
    """현재 가격의 20일 이동평균 대비 Z-Score."""
    hist = stock.get("price_history")
    if hist and len(hist) >= 20:
        try:
            s = pd.Series(hist[-20:], dtype=float)
            mean = s.mean()
            std = s.std()
            if std > 0:
                return float((s.iloc[-1] - mean) / std)
        except Exception:
            pass

    price = stock.get("price") or 0
    tech = stock.get("technical") or {}
    ma20 = tech.get("ma20") or stock.get("ma20")
    std20 = tech.get("std20") or stock.get("std20")

    if price > 0 and ma20 and std20 and std20 > 0:
        return (price - ma20) / std20

    return None


def _estimate_hurst(stock: Dict[str, Any]) -> Optional[float]:
    """
    Rescaled Range (R/S) 방법으로 Hurst Exponent 근사.
    price_history가 있어야 계산 가능.
    """
    hist = stock.get("price_history")
    if not hist or len(hist) < 60:
        return None

    try:
        prices = np.array(hist[-120:], dtype=float) if len(hist) >= 120 else np.array(hist, dtype=float)
        log_returns = np.diff(np.log(prices))
        log_returns = log_returns[~np.isnan(log_returns)]

        if len(log_returns) < 40:
            return None

        n = len(log_returns)
        max_k = min(n // 2, 64)
        sizes = []
        rs_values = []

        for size in [8, 16, 32, max_k]:
            if size > max_k or size < 8:
                continue
            num_chunks = n // size
            if num_chunks < 1:
                continue

            rs_list = []
            for i in range(num_chunks):
                chunk = log_returns[i * size:(i + 1) * size]
                mean_c = np.mean(chunk)
                cumdev = np.cumsum(chunk - mean_c)
                r = np.max(cumdev) - np.min(cumdev)
                s = np.std(chunk, ddof=1)
                if s > 0:
                    rs_list.append(r / s)

            if rs_list:
                sizes.append(np.log(size))
                rs_values.append(np.log(np.mean(rs_list)))

        if len(sizes) < 2:
            return None

        coeffs = np.polyfit(sizes, rs_values, 1)
        hurst = float(coeffs[0])
        return max(0.0, min(1.0, hurst))

    except Exception:
        return None
