"""
변동성 팩터 엔진

학술 근거:
  - Ang, Hodrick, Xing & Zhang (2006): 저변동성 이상현상 — 변동성 낮은 주식이
    오히려 높은 위험조정 수익률을 보이는 시장 이상현상
  - Baker, Bradley & Wurgler (2011): 복권형 선호 편향으로 고변동성 주식이 과대평가
  - Blitz & van Vliet (2007): 저변동성 효과의 글로벌 실증

구현 팩터:
  1. 실현 변동성 (Realized Volatility): 20일/60일 수익률 표준편차
  2. 고유 변동성 (Idiosyncratic Vol): 시장 대비 잔차 변동성
  3. 변동성 추세: 변동성 확대/축소 방향
  4. 베타: 시장 민감도
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd


def compute_volatility_score(
    stock: Dict[str, Any],
    universe_stats: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    단일 종목의 변동성 팩터 점수 계산 (0~100).
    저변동성 = 높은 점수 (학술적으로 저변동성이 초과수익)

    stock에 필요한 키:
      volatility_20d, volatility_60d, beta, price_history (optional)
    universe_stats:
      median_vol_20d, median_vol_60d (유니버스 중앙값)
    """
    scores: Dict[str, float] = {}
    signals: List[str] = []

    vol_20 = stock.get("volatility_20d") or stock.get("technical", {}).get("volatility_20d")
    vol_60 = stock.get("volatility_60d")
    beta = stock.get("beta")

    if vol_20 is None and vol_60 is None:
        hist = stock.get("price_history")
        if hist and len(hist) >= 20:
            vol_20, vol_60 = _compute_vols_from_history(hist)

    # --- 1. 실현 변동성 순위 (반전: 저변동성 = 고점수) ---
    rv_score = 50.0
    if vol_20 is not None:
        ann_vol = vol_20 * np.sqrt(252) if vol_20 < 1 else vol_20
        if ann_vol <= 15:
            rv_score = 90
            signals.append(f"연 변동성 {ann_vol:.1f}% 초저변동")
        elif ann_vol <= 25:
            rv_score = 75
            signals.append(f"연 변동성 {ann_vol:.1f}% 저변동")
        elif ann_vol <= 35:
            rv_score = 55
        elif ann_vol <= 50:
            rv_score = 35
            signals.append(f"연 변동성 {ann_vol:.1f}% 고변동")
        else:
            rv_score = 15
            signals.append(f"연 변동성 {ann_vol:.1f}% 초고변동")

        if universe_stats and universe_stats.get("median_vol_20d"):
            med = universe_stats["median_vol_20d"]
            ratio = vol_20 / med if med > 0 else 1.0
            if ratio < 0.7:
                rv_score = min(rv_score + 10, 100)
                signals.append("유니버스 대비 저변동")
            elif ratio > 1.5:
                rv_score = max(rv_score - 10, 0)

    scores["realized_vol"] = rv_score

    # --- 2. 변동성 추세 (축소 = 긍정) ---
    trend_score = 50.0
    if vol_20 is not None and vol_60 is not None and vol_60 > 0:
        vol_ratio = vol_20 / vol_60
        if vol_ratio < 0.7:
            trend_score = 85
            signals.append("변동성 급축소 — 안정화")
        elif vol_ratio < 0.9:
            trend_score = 70
            signals.append("변동성 축소 추세")
        elif vol_ratio < 1.1:
            trend_score = 50
        elif vol_ratio < 1.3:
            trend_score = 30
            signals.append("변동성 확대 추세")
        else:
            trend_score = 15
            signals.append("변동성 급확대 — 경계")

    scores["vol_trend"] = trend_score

    # --- 3. 베타 (저베타 = 고점수) ---
    beta_score = 50.0
    if beta is not None:
        if beta <= 0.5:
            beta_score = 90
            signals.append(f"베타 {beta:.2f} 방어형")
        elif beta <= 0.8:
            beta_score = 75
        elif beta <= 1.2:
            beta_score = 50
        elif beta <= 1.5:
            beta_score = 30
            signals.append(f"베타 {beta:.2f} 공격형")
        else:
            beta_score = 15
            signals.append(f"베타 {beta:.2f} 고위험")

    scores["beta"] = beta_score

    # --- 4. 고유 변동성 (Idiosyncratic Vol) ---
    # 시장 설명 못하는 변동성 — 낮을수록 좋음
    idio_score = 50.0
    if vol_20 is not None and beta is not None:
        market_vol = 0.18  # KOSPI 연환산 변동성 근사
        systematic_vol = abs(beta) * market_vol
        daily_systematic = systematic_vol / np.sqrt(252)
        if vol_20 > daily_systematic:
            idio_vol = np.sqrt(max(vol_20**2 - daily_systematic**2, 0))
            ann_idio = idio_vol * np.sqrt(252) if idio_vol < 1 else idio_vol
            if ann_idio <= 10:
                idio_score = 85
            elif ann_idio <= 20:
                idio_score = 65
            elif ann_idio <= 35:
                idio_score = 40
            else:
                idio_score = 20
                signals.append(f"고유변동성 {ann_idio:.0f}% 과다")
        else:
            idio_score = 75

    scores["idiosyncratic"] = idio_score

    # --- 종합 ---
    weights = {
        "realized_vol": 0.35,
        "vol_trend": 0.25,
        "beta": 0.25,
        "idiosyncratic": 0.15,
    }

    total = sum(scores[k] * weights[k] for k in weights)
    total = max(0, min(100, round(total)))

    return {
        "volatility_score": total,
        "components": {k: round(v, 1) for k, v in scores.items()},
        "signals": signals[:5],
        "metrics": {
            "vol_20d": round(vol_20, 6) if vol_20 is not None else None,
            "vol_60d": round(vol_60, 6) if vol_60 is not None else None,
            "beta": round(beta, 3) if beta is not None else None,
        },
    }


def _compute_vols_from_history(prices: list) -> tuple:
    """가격 리스트에서 20일/60일 변동성 계산."""
    try:
        s = pd.Series(prices, dtype=float)
        rets = s.pct_change().dropna()
        vol_20 = float(rets.tail(20).std()) if len(rets) >= 20 else None
        vol_60 = float(rets.tail(60).std()) if len(rets) >= 60 else None
        return vol_20, vol_60
    except Exception:
        return None, None


def compute_universe_vol_stats(
    universe: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """유니버스 전체의 변동성 통계 (중앙값, 분위수)."""
    vols_20 = []
    vols_60 = []
    betas = []

    for s in universe:
        v20 = s.get("volatility_20d") or s.get("technical", {}).get("volatility_20d")
        v60 = s.get("volatility_60d")
        b = s.get("beta")

        if v20 is not None:
            vols_20.append(v20)
        if v60 is not None:
            vols_60.append(v60)
        if b is not None:
            betas.append(b)

    def _stats(arr):
        if not arr:
            return {}
        a = np.array(arr)
        return {
            "median": round(float(np.median(a)), 6),
            "q25": round(float(np.percentile(a, 25)), 6),
            "q75": round(float(np.percentile(a, 75)), 6),
            "mean": round(float(np.mean(a)), 6),
        }

    return {
        "median_vol_20d": float(np.median(vols_20)) if vols_20 else None,
        "median_vol_60d": float(np.median(vols_60)) if vols_60 else None,
        "vol_20d_stats": _stats(vols_20),
        "vol_60d_stats": _stats(vols_60),
        "beta_stats": _stats(betas),
    }
