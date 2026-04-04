"""
안정 추천 엔진 — 배당주 + 단기 국채 파킹 안내

배당주 필터링 기준:
  1. 배당수익률 > 시중금리(한국 3년물 기준)
  2. 배당성향 < 60% (지속 가능성)
  3. 부채비율 < 80%
  4. 영업이익률 > 5% (수익 안정성)

단기 국채 안내:
  환율/금리 상황에 따라 "현금보다 안전한 파킹 공간" 제안
"""
from typing import List, Dict, Optional


def filter_dividend_stocks(candidates: List[dict], macro: dict) -> List[dict]:
    """배당주 필터링: 배당률 > 시중금리 & 배당성향 < 60%"""
    kr_3y = macro.get("us_10y", {}).get("value", 3.5)
    threshold_yield = max(kr_3y * 0.8, 2.0)

    safe_picks = []
    for stock in candidates:
        div_yield = stock.get("div_yield", 0)
        debt_ratio = stock.get("debt_ratio", 0)
        op_margin = stock.get("operating_margin", 0)
        roe = stock.get("roe", 0)

        if div_yield <= threshold_yield:
            continue
        if debt_ratio > 80:
            continue
        if op_margin < 5:
            continue

        payout_ratio = 0
        eps = stock.get("eps", 0)
        price = stock.get("price", 0)
        if eps > 0 and price > 0 and div_yield > 0:
            dps = price * div_yield / 100
            payout_ratio = (dps / eps) * 100

        if payout_ratio > 60:
            continue

        safety_tier = "A"
        if div_yield >= 4 and debt_ratio < 50 and op_margin > 10:
            safety_tier = "S"
        elif div_yield < 3 or debt_ratio > 60:
            safety_tier = "B"

        safe_picks.append({
            "ticker": stock["ticker"],
            "ticker_yf": stock.get("ticker_yf", ""),
            "name": stock["name"],
            "price": stock.get("price", 0),
            "div_yield": round(div_yield, 2),
            "payout_ratio": round(payout_ratio, 1),
            "debt_ratio": round(debt_ratio, 1),
            "operating_margin": round(op_margin, 1),
            "roe": round(roe, 1),
            "safety_tier": safety_tier,
            "safety_score": stock.get("safety_score", 0),
            "reason": _build_reason(stock, div_yield, payout_ratio, threshold_yield),
        })

    safe_picks.sort(key=lambda x: ("S", "A", "B").index(x["safety_tier"]) * 100 - x["div_yield"] * 10)
    return safe_picks[:10]


def _build_reason(stock: dict, div_yield: float, payout_ratio: float, threshold: float) -> str:
    parts = []
    parts.append(f"배당 {div_yield:.1f}%(기준 {threshold:.1f}% 초과)")
    if payout_ratio > 0:
        parts.append(f"배당성향 {payout_ratio:.0f}%")
    if stock.get("debt_ratio", 0) < 40:
        parts.append("저부채")
    if stock.get("operating_margin", 0) > 15:
        parts.append("고수익")
    return " · ".join(parts)


def assess_parking_options(macro: dict) -> Dict:
    """단기 국채/MMF 등 현금 파킹 옵션 평가"""
    usd_krw = macro.get("usd_krw", {}).get("value", 0)
    us_10y = macro.get("us_10y", {}).get("value", 0)
    us_2y = macro.get("us_2y", {}).get("value", 0)
    vix = macro.get("vix", {}).get("value", 0)
    mood_score = macro.get("market_mood", {}).get("score", 50)

    options = []

    kr_rate_est = max(us_10y - 0.5, 2.5)
    options.append({
        "type": "kr_bond",
        "name": "한국 단기국채 (1-3년)",
        "est_yield": round(kr_rate_est, 2),
        "risk": "매우 낮음",
        "liquidity": "높음",
        "suitable": True,
    })

    if us_2y > 3.5:
        options.append({
            "type": "us_tbill",
            "name": "미국 단기국채 (T-Bill)",
            "est_yield": round(us_2y, 2),
            "risk": "매우 낮음 (환위험 존재)",
            "liquidity": "높음",
            "suitable": usd_krw < 1400,
            "note": f"환율 {usd_krw:,.0f}원" + (" — 원화 강세 시 유리" if usd_krw < 1300 else " — 환헤지 고려"),
        })

    options.append({
        "type": "mmf",
        "name": "MMF/CMA (수시입출금)",
        "est_yield": round(max(kr_rate_est - 0.5, 2.0), 2),
        "risk": "매우 낮음",
        "liquidity": "최고",
        "suitable": True,
    })

    if vix > 25 or mood_score < 35:
        recommendation = "defensive"
        message = f"VIX {vix}, 시장 불안 — 현금/국채 비중 확대 강력 권고"
    elif mood_score < 45:
        recommendation = "cautious"
        message = "시장 관망 구간 — 안전자산 30~40% 유지 권장"
    else:
        recommendation = "balanced"
        message = "시장 안정 — 안전자산 10~20% 유지로 충분"

    return {
        "options": options,
        "recommendation": recommendation,
        "message": message,
        "kr_base_rate_est": round(kr_rate_est, 2),
        "usd_krw": usd_krw,
    }


def generate_safe_recommendations(candidates: List[dict], macro: dict) -> Dict:
    """안정 추천 종합 생성"""
    dividend_picks = filter_dividend_stocks(candidates, macro)
    parking = assess_parking_options(macro)

    return {
        "dividend_stocks": dividend_picks,
        "parking_options": parking,
        "total_safe_picks": len(dividend_picks),
    }
