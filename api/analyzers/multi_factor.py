"""
멀티팩터 통합 점수 엔진
기술적 지표 + 펀더멘털 + 뉴스 감성 + 수급 + 매크로를 하나의 점수로 통합
"""
from typing import Dict


WEIGHTS = {
    "fundamental": 0.25,
    "technical": 0.25,
    "sentiment": 0.15,
    "flow": 0.20,
    "macro": 0.15,
}


def compute_multi_factor_score(
    fundamental_score: int,
    technical: Dict,
    sentiment: Dict,
    flow: Dict,
    macro_mood: Dict,
) -> Dict:
    """
    5개 팩터를 가중 합산하여 멀티팩터 점수 산출 (0~100)

    반환:
      multi_score, grade, factor_breakdown, all_signals, factor_detail
    """
    tech_score = technical.get("technical_score", 50)
    sent_score = sentiment.get("score", 50)
    flow_score = flow.get("flow_score", 50)
    macro_score = macro_mood.get("score", 50)

    multi = (
        fundamental_score * WEIGHTS["fundamental"]
        + tech_score * WEIGHTS["technical"]
        + sent_score * WEIGHTS["sentiment"]
        + flow_score * WEIGHTS["flow"]
        + macro_score * WEIGHTS["macro"]
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

    breakdown = {
        "fundamental": fundamental_score,
        "technical": tech_score,
        "sentiment": sent_score,
        "flow": flow_score,
        "macro": macro_score,
    }

    return {
        "multi_score": multi,
        "grade": grade,
        "factor_breakdown": breakdown,
        "all_signals": all_signals,
    }
