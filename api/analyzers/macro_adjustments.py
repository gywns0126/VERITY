"""
매크로(특히 FRED DGS10)에 따른 멀티팩터 펀더멘털 감점 등.
V6: 3-state 레짐 자동 감지 (HMM 우선, 변동성 클러스터링 fallback).
"""
import json
import logging
import os
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

# ── 레짐 분류기 설정 ─────────────────────────────────────────────
REGIME_WINDOW = int(os.environ.get("REGIME_WINDOW_DAYS", "120"))
REGIME_MIN_CONFIDENCE = float(os.environ.get("REGIME_MIN_CONFIDENCE", "0.55"))
REGIME_USE_HMM = os.environ.get("REGIME_USE_HMM", "1").strip().lower() in ("1", "true", "yes", "on")

REGIME_LABELS = {0: "bull", 1: "sideways", 2: "panic"}
REGIME_WEIGHT_MULTIPLIERS = {
    "bull": {
        "momentum": 1.15, "quality": 0.90, "volatility": 0.85,
        "mean_reversion": 0.90, "fundamental": 0.95, "technical": 1.10,
        "flow": 1.05, "sentiment": 1.05,
    },
    "sideways": {
        "momentum": 0.95, "quality": 1.05, "volatility": 1.00,
        "mean_reversion": 1.10, "fundamental": 1.05, "technical": 0.95,
        "flow": 1.00, "sentiment": 0.95,
    },
    "panic": {
        "momentum": 0.70, "quality": 1.20, "volatility": 1.15,
        "mean_reversion": 1.15, "fundamental": 1.10, "technical": 0.80,
        "flow": 0.85, "sentiment": 0.75,
    },
}


def fundamental_penalty_from_macro(macro: Dict[str, Any]) -> int:
    """
    미 10년물 급등 구간에서 펀더멘털 점수(merge_fundamental_with_consensus 입력) 감점.
    FRED change_5d_pp 우선, 없으면 yfinance us_10y.change_pct(일) 임계.
    """
    pen = int(os.environ.get("MACRO_FUNDAMENTAL_PENALTY_SURGE", "15"))
    fred = macro.get("fred") or {}
    d = fred.get("dgs10") or {}
    ch = d.get("change_5d_pp")
    if ch is not None:
        thr_pp = float(os.environ.get("MACRO_DGS10_SURGE_PP", "0.12"))
        if float(ch) >= thr_pp:
            return pen
        return 0
    u = macro.get("us_10y") or {}
    chg = float(u.get("change_pct") or 0)
    thr_pct = float(os.environ.get("MACRO_DGS10_SURGE_YF_PCT", "3"))
    if chg >= thr_pct:
        return pen
    return 0


# ── 레짐 자동 감지 엔진 ─────────────────────────────────────────

def _extract_regime_features(macro: Dict[str, Any]) -> Optional[Dict[str, float]]:
    """VIX, 금리 변화, S&P500 변화율에서 레짐 분류 입력을 추출."""
    vix = macro.get("vix", {}).get("value")
    sp_chg = macro.get("sp500", {}).get("change_pct")
    fred = macro.get("fred") or {}
    dgs10_val = fred.get("dgs10", {}).get("value")
    mood = macro.get("market_mood", {}).get("score")

    if vix is None:
        return None

    return {
        "vix": float(vix),
        "sp_change_pct": float(sp_chg or 0),
        "dgs10": float(dgs10_val or 3.5),
        "mood": float(mood or 50),
    }


def _classify_regime_rules(features: Dict[str, float]) -> Dict[str, Any]:
    """규칙 기반 레짐 분류 (HMM fallback). 변동성 클러스터링 근사."""
    vix = features["vix"]
    mood = features["mood"]
    sp_chg = features["sp_change_pct"]

    if vix >= 30 or (mood < 25 and sp_chg < -2):
        regime = "panic"
        confidence = min(0.60 + (vix - 30) * 0.01, 0.95) if vix >= 30 else 0.65
    elif vix <= 16 and mood >= 55 and sp_chg > -0.5:
        regime = "bull"
        confidence = min(0.55 + (65 - vix) * 0.005, 0.90)
    else:
        regime = "sideways"
        confidence = 0.55 + abs(50 - mood) * 0.002

    confidence = max(REGIME_MIN_CONFIDENCE, min(0.95, confidence))

    return {
        "regime": regime,
        "confidence": round(float(confidence), 3),
        "method": "volatility_cluster_rules",
        "features": {k: round(float(v), 2) for k, v in features.items()},
    }


def _classify_regime_hmm(features: Dict[str, float]) -> Optional[Dict[str, Any]]:
    """HMM(hmmlearn) 기반 레짐 분류. 라이브러리 미설치 시 None."""
    try:
        from hmmlearn.hmm import GaussianHMM
    except ImportError:
        return None

    cache_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "data", "regime_hmm_history.json",
    )
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            history = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        history = []

    entry = {
        "vix": features["vix"],
        "mood": features["mood"],
        "sp_chg": features["sp_change_pct"],
    }
    history.append(entry)
    history = history[-REGIME_WINDOW:]

    try:
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False)
    except Exception:
        pass

    if len(history) < 30:
        return None

    X = np.array([[h["vix"], h["mood"], h["sp_chg"]] for h in history])
    X_norm = (X - X.mean(axis=0)) / (X.std(axis=0) + 1e-8)

    try:
        model = GaussianHMM(n_components=3, covariance_type="diag",
                            n_iter=50, random_state=42)
        model.fit(X_norm)
        states = model.predict(X_norm)
        current_state = int(states[-1])

        proba = model.predict_proba(X_norm[-1:].reshape(1, -1))[0]
        confidence = float(proba[current_state])

        means = model.means_
        vix_col = 0
        state_vix_order = np.argsort(means[:, vix_col])
        label_map = {}
        label_map[int(state_vix_order[0])] = "bull"
        label_map[int(state_vix_order[1])] = "sideways"
        label_map[int(state_vix_order[2])] = "panic"

        regime = label_map.get(current_state, "sideways")

        return {
            "regime": regime,
            "confidence": round(confidence, 3),
            "method": "hmm_gaussian",
            "features": {k: round(float(v), 2) for k, v in features.items()},
            "hmm_state": current_state,
            "history_len": len(history),
        }
    except Exception as e:
        logger.debug("HMM regime detection failed: %s", e)
        return None


def detect_market_regime(macro: Dict[str, Any]) -> Dict[str, Any]:
    """매크로 데이터에서 현재 시장 레짐을 자동 감지.

    Returns:
        {regime: "bull"|"sideways"|"panic",
         confidence: 0.0~1.0,
         method: "hmm_gaussian"|"volatility_cluster_rules",
         weight_multipliers: {...}}
    """
    features = _extract_regime_features(macro)
    if features is None:
        return {
            "regime": "sideways",
            "confidence": 0.0,
            "method": "default_fallback",
            "weight_multipliers": REGIME_WEIGHT_MULTIPLIERS["sideways"],
        }

    result = None
    if REGIME_USE_HMM:
        result = _classify_regime_hmm(features)

    if result is None:
        result = _classify_regime_rules(features)

    regime = result["regime"]
    result["weight_multipliers"] = REGIME_WEIGHT_MULTIPLIERS.get(
        regime, REGIME_WEIGHT_MULTIPLIERS["sideways"]
    )

    return result
