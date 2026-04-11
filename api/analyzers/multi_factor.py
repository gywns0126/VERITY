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


def _get_dynamic_weights(macro_score: int) -> Dict[str, float]:
    """매크로 점수에 따라 가중치 동적 조정"""
    if macro_score <= 35:
        return RISK_OFF_WEIGHTS
    elif macro_score >= 65:
        return RISK_ON_WEIGHTS
    return BASE_WEIGHTS


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

    weights = _get_dynamic_weights(macro_score)
    regime = "risk_off" if macro_score <= 35 else "risk_on" if macro_score >= 65 else "neutral"

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
        "weights_used": {k: round(v, 2) for k, v in weights.items()},
        "factor_breakdown": breakdown,
        "factor_contribution": contribution,
        "quant_factors": quant_sub,
        "all_signals": all_signals,
    }
