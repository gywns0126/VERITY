"""
매수/매도 시점 예측 모듈
기술적 지표 + XGBoost 확률 + 수급을 결합하여
BUY/SELL/HOLD 타이밍 시그널 생성
"""


def compute_timing_signal(stock: dict) -> dict:
    """
    종합 타이밍 시그널 계산.
    0-100 스코어: 0에 가까울수록 SELL, 100에 가까울수록 BUY.
    """
    tech = stock.get("technical", {})
    pred = stock.get("prediction", {})
    flow = stock.get("flow", {})
    mf = stock.get("multi_factor", {})

    score = 50.0
    reasons = []

    # 1) RSI 기반 (과매수/과매도)
    rsi = tech.get("rsi", 50)
    if rsi <= 30:
        score += 15
        reasons.append(f"RSI {rsi} 과매도 — 반등 가능")
    elif rsi <= 40:
        score += 8
        reasons.append(f"RSI {rsi} 저평가 구간")
    elif rsi >= 70:
        score -= 15
        reasons.append(f"RSI {rsi} 과매수 — 차익실현 고려")
    elif rsi >= 60:
        score -= 5
        reasons.append(f"RSI {rsi} 고평가 접근")

    # 2) MACD 시그널
    signals = tech.get("signals", [])
    for sig in signals:
        if "골든크로스" in sig:
            score += 12
            reasons.append("MACD 골든크로스 — 상승전환")
        elif "데드크로스" in sig:
            score -= 12
            reasons.append("MACD 데드크로스 — 하락전환")
        elif "MACD 반전" in sig or "MACD 매수" in sig:
            score += 8
            reasons.append("MACD 상승반전 신호")

    # 3) 볼린저밴드 위치
    for sig in signals:
        if "볼린저 하단 이탈" in sig:
            score += 10
            reasons.append("볼린저밴드 하단 이탈 — 반등 기대")
        elif "볼린저 상단 돌파" in sig:
            score -= 8
            reasons.append("볼린저밴드 상단 — 과열 경고")

    # 4) 이동평균선 배열
    for sig in signals:
        if "정배열" in sig:
            score += 6
            reasons.append("이동평균 정배열 — 상승 추세")
        elif "역배열" in sig:
            score -= 6
            reasons.append("이동평균 역배열 — 하락 추세")

    # 5) 거래량 방향
    vol_dir = tech.get("vol_direction", "flat")
    if "거래폭증" in str(signals):
        if vol_dir == "up":
            score += 8
            reasons.append("거래량 폭증 + 상승 — 매집 신호")
        elif vol_dir == "down":
            score -= 8
            reasons.append("거래량 폭증 + 하락 — 투매 경고")

    # 6) XGBoost 상승 확률
    up_prob = pred.get("up_probability", 50)
    if up_prob >= 65:
        score += 10
        reasons.append(f"AI 상승확률 {up_prob}% — 강한 매수 신호")
    elif up_prob >= 55:
        score += 5
        reasons.append(f"AI 상승확률 {up_prob}%")
    elif up_prob <= 35:
        score -= 10
        reasons.append(f"AI 상승확률 {up_prob}% — 강한 하락 신호")
    elif up_prob <= 45:
        score -= 5
        reasons.append(f"AI 상승확률 {up_prob}%")

    # 7) 수급 (외국인/기관)
    flow_score = flow.get("flow_score", 50)
    if flow_score >= 70:
        score += 8
        reasons.append("외국인·기관 강한 순매수")
    elif flow_score >= 60:
        score += 4
        reasons.append("수급 우호적")
    elif flow_score <= 30:
        score -= 8
        reasons.append("외국인·기관 강한 순매도")
    elif flow_score <= 40:
        score -= 4
        reasons.append("수급 비우호적")

    # 8) 추세 강도
    trend = tech.get("trend_strength", "")
    if trend == "strong_up":
        score += 5
        reasons.append("강한 상승 추세")
    elif trend == "strong_down":
        score -= 5
        reasons.append("강한 하락 추세")

    score = max(0, min(100, round(score)))

    if score >= 70:
        action = "STRONG_BUY"
        label = "적극 매수"
        color = "#22C55E"
    elif score >= 55:
        action = "BUY"
        label = "매수 고려"
        color = "#86EFAC"
    elif score >= 45:
        action = "HOLD"
        label = "관망"
        color = "#888"
    elif score >= 30:
        action = "SELL"
        label = "매도 고려"
        color = "#FCA5A5"
    else:
        action = "STRONG_SELL"
        label = "적극 매도"
        color = "#EF4444"

    return {
        "timing_score": score,
        "action": action,
        "label": label,
        "color": color,
        "reasons": reasons[:5],
    }
