"""
멀티팩터 통합 점수 엔진 v2 (Sprint 3)
- 매크로 국면에 따른 동적 가중치
- 신호 중복 제거
- 상세 팩터 기여도 제공
"""
from typing import Dict


BASE_WEIGHTS = {
    "fundamental": 0.25,
    "technical": 0.25,
    "sentiment": 0.15,
    "flow": 0.20,
    "macro": 0.15,
}

RISK_OFF_WEIGHTS = {
    "fundamental": 0.30,
    "technical": 0.20,
    "sentiment": 0.10,
    "flow": 0.15,
    "macro": 0.25,
}

RISK_ON_WEIGHTS = {
    "fundamental": 0.20,
    "technical": 0.30,
    "sentiment": 0.15,
    "flow": 0.25,
    "macro": 0.10,
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
) -> Dict:
    """
    5개 팩터를 동적 가중 합산하여 멀티팩터 점수 산출 (0~100)
    """
    tech_score = technical.get("technical_score", 50)
    sent_score = sentiment.get("score", 50)
    flow_score = flow.get("flow_score", 50)
    macro_score = macro_mood.get("score", 50)

    weights = _get_dynamic_weights(macro_score)
    regime = "risk_off" if macro_score <= 35 else "risk_on" if macro_score >= 65 else "neutral"

    multi = (
        fundamental_score * weights["fundamental"]
        + tech_score * weights["technical"]
        + sent_score * weights["sentiment"]
        + flow_score * weights["flow"]
        + macro_score * weights["macro"]
    )
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

    all_signals = []
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

    all_signals = _deduplicate_signals(all_signals)

    breakdown = {
        "fundamental": fundamental_score,
        "technical": tech_score,
        "sentiment": sent_score,
        "flow": flow_score,
        "macro": macro_score,
    }

    contribution = {
        k: round(breakdown[k] * weights[k], 1) for k in weights
    }

    return {
        "multi_score": multi,
        "grade": grade,
        "regime": regime,
        "weights_used": {k: round(v, 2) for k, v in weights.items()},
        "factor_breakdown": breakdown,
        "factor_contribution": contribution,
        "all_signals": all_signals,
    }
