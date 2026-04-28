"""
멀티팩터 통합 점수 엔진 v3 (Quant Enhancement)
- 기존 5팩터 + 학술 퀀트 4팩터 = 9팩터 체제
- 매크로 국면에 따른 동적 가중치
- 퀀트 팩터: 모멘텀, 퀄리티, 변동성, 평균회귀
- 신호 중복 제거 + 퀀트 시그널 통합
"""
from typing import Any, Dict, List, Optional


# ── 기존 5팩터 가중치 (합 = 0.70) ──
# 나머지 0.30은 퀀트 4팩터에 배분

BASE_WEIGHTS = {
    "fundamental": 0.18,
    "technical": 0.17,
    "sentiment": 0.10,
    "flow": 0.13,
    "macro": 0.12,
    "momentum": 0.10,
    "quality": 0.08,
    "volatility": 0.06,
    "mean_reversion": 0.06,
}

RISK_OFF_WEIGHTS = {
    "fundamental": 0.20,
    "technical": 0.12,
    "sentiment": 0.06,
    "flow": 0.10,
    "macro": 0.17,
    "momentum": 0.05,
    "quality": 0.14,
    "volatility": 0.10,
    "mean_reversion": 0.06,
}

RISK_ON_WEIGHTS = {
    "fundamental": 0.14,
    "technical": 0.18,
    "sentiment": 0.10,
    "flow": 0.16,
    "macro": 0.07,
    "momentum": 0.15,
    "quality": 0.05,
    "volatility": 0.05,
    "mean_reversion": 0.10,
}


# ── V7: bond_regime 기반 rate-environment 곱셈 보정 (Druckenmiller) ──
# 명제: "Liquidity > Earnings (intermediate term)" — 단 시대 의존적.
# 2008~2021 QE 시대엔 liquidity 우위, 2022~ QT 전환 후엔 earnings 우위.
# bond_regime.rate_environment 따라 동적 우위 전환.
#
# 매핑:
#   rate_low_accommodative (QE)  → macro/flow/momentum ↑, fundamental ↓ (liquidity 시각)
#   rate_normal                  → 중립 (multiplier 1.0)
#   rate_elevated (QT 시작)      → fundamental/quality ↑, macro/momentum ↓ (earnings 시각)
#   rate_high_restrictive (QT 강)→ fundamental/quality 더 ↑, momentum 더 ↓
#
# 하이브리드 구조: macro_score(mood) 기반 BASE/RISK_OFF/RISK_ON 위에 곱셈 보정 → 정규화.
RATE_ENV_MULTIPLIERS: Dict[str, Dict[str, float]] = {
    "rate_low_accommodative": {
        "macro":       1.35,
        "flow":        1.25,
        "momentum":    1.15,
        "fundamental": 0.80,
        "quality":     0.85,
    },
    "rate_normal": {},  # 모든 팩터 1.0 (중립)
    "rate_elevated": {
        "fundamental": 1.20,
        "quality":     1.20,
        "volatility":  1.10,
        "macro":       0.85,
        "momentum":    0.90,
    },
    "rate_high_restrictive": {
        "fundamental": 1.35,
        "quality":     1.35,
        "volatility":  1.20,
        "macro":       0.70,
        "momentum":    0.75,
        "flow":        0.85,
    },
}


def _get_dynamic_weights(
    macro_score: int,
    ff_factors: Optional[Dict[str, float]] = None,
    bond_regime: Optional[Dict[str, Any]] = None,
) -> Dict[str, float]:
    """매크로 점수에 따라 가중치 동적 조정.

    레이어:
      1. macro_score(mood) 기반 BASE/RISK_OFF/RISK_ON 선택
      2. bond_regime.rate_environment 곱셈 보정 (Druckenmiller — 시대 변화 가드)
      3. Fama-French SMB/HML 미세 보정
      4. 합 1.0 으로 정규화
    """
    if macro_score <= 35:
        w = dict(RISK_OFF_WEIGHTS)
    elif macro_score >= 65:
        w = dict(RISK_ON_WEIGHTS)
    else:
        w = dict(BASE_WEIGHTS)

    # bond_regime 곱셈 보정 — Druckenmiller "regime-dependent liquidity vs earnings"
    if bond_regime:
        rate_env = bond_regime.get("rate_environment", "unknown")
        mult = RATE_ENV_MULTIPLIERS.get(rate_env, {})
        for k, m in mult.items():
            if k in w:
                w[k] = w[k] * m

    if ff_factors:
        smb = ff_factors.get("SMB", 0)
        hml = ff_factors.get("HML", 0)
        if smb > 0.05:
            w["momentum"] = w.get("momentum", 0.10) * 1.05
        elif smb < -0.05:
            w["quality"] = w.get("quality", 0.08) * 1.05
        if hml > 0.05:
            w["fundamental"] = w.get("fundamental", 0.18) * 1.05
        elif hml < -0.05:
            w["momentum"] = w.get("momentum", 0.10) * 1.05

    # 정규화 — bond_regime / ff_factors 보정 후 합 1.0 으로
    total = sum(w.values())
    if total > 0:
        w = {k: round(v / total, 4) for k, v in w.items()}

    return w


def _deduplicate_signals(signals: list) -> list:
    """신호 중복 제거 (순서 유지), 비문자열 필터"""
    seen = set()
    result = []
    for s in signals:
        if not isinstance(s, str):
            continue
        key = s.split("(")[0].strip()
        if key not in seen:
            seen.add(key)
            result.append(s)
    return result


def compute_multi_factor_score(
    fundamental_score: int,
    technical: Dict,
    sentiment: Dict,
    flow: Dict,
    macro_mood: Dict,
    quant_factors: Optional[Dict[str, Any]] = None,
    social_sentiment: Optional[Dict[str, Any]] = None,
    bond_regime: Optional[Dict[str, Any]] = None,
) -> Dict:
    """
    9개 팩터를 동적 가중 합산하여 멀티팩터 점수 산출 (0~100)

    기존 5팩터: fundamental, technical, sentiment, flow, macro
    퀀트 4팩터: momentum, quality, volatility, mean_reversion
    """
    tech_score = technical.get("technical_score", 50)
    news_score = sentiment.get("score", 50)
    social = social_sentiment or {}
    social_score = social.get("score", 50) if social else 50
    sent_score = round(news_score * 0.6 + social_score * 0.4) if social else news_score
    flow_score = flow.get("flow_score", 50)
    macro_score = macro_mood.get("score", 50)

    qf = quant_factors or {}
    momentum_score = qf.get("momentum", {}).get("momentum_score", 50)
    quality_score = qf.get("quality", {}).get("quality_score", 50)
    volatility_score = qf.get("volatility", {}).get("volatility_score", 50)
    mr_score = qf.get("mean_reversion", {}).get("mean_reversion_score", 50)

    weights = _get_dynamic_weights(macro_score, bond_regime=bond_regime)
    regime = "risk_off" if macro_score <= 35 else "risk_on" if macro_score >= 65 else "neutral"
    rate_env = (bond_regime or {}).get("rate_environment", "unknown") if bond_regime else "unknown"

    breakdown = {
        "fundamental": fundamental_score,
        "technical": tech_score,
        "sentiment": sent_score,
        "flow": flow_score,
        "macro": macro_score,
        "momentum": momentum_score,
        "quality": quality_score,
        "volatility": volatility_score,
        "mean_reversion": mr_score,
    }

    multi = sum(breakdown[k] * weights.get(k, 0) for k in breakdown)
    multi = round(max(0, min(100, multi)))

    if multi >= 75:
        grade = "강력 매수"
    elif multi >= 60:
        grade = "매수"
    elif multi >= 45:
        grade = "관망"
    elif multi >= 30:
        grade = "주의"
    else:
        grade = "회피"

    all_signals: List[str] = []
    all_signals.extend(technical.get("signals", []))
    all_signals.extend(flow.get("flow_signals", []))

    if sent_score >= 70:
        all_signals.append("뉴스 긍정적")
    elif sent_score <= 30:
        all_signals.append("뉴스 부정적")
    if macro_score >= 65:
        all_signals.append("매크로 낙관")
    elif macro_score <= 35:
        all_signals.append("매크로 비관")

    for factor_key in ["momentum", "quality", "volatility", "mean_reversion"]:
        factor_data = qf.get(factor_key, {})
        for sig in factor_data.get("signals", []):
            all_signals.append(sig)

    all_signals = _deduplicate_signals(all_signals)

    contribution = {
        k: round(breakdown[k] * weights.get(k, 0), 1) for k in breakdown
    }

    quant_sub = {
        "momentum": momentum_score,
        "quality": quality_score,
        "volatility": volatility_score,
        "mean_reversion": mr_score,
    }

    return {
        "multi_score": multi,
        "grade": grade,
        "regime": regime,
        "rate_environment": rate_env,
        "weights_used": {k: round(v, 2) for k, v in weights.items()},
        "factor_breakdown": breakdown,
        "factor_contribution": contribution,
        "quant_factors": quant_sub,
        "all_signals": all_signals,
    }
