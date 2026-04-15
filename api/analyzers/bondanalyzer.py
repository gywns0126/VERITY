"""
bondanalyzer.py — 채권 YTM·듀레이션·스프레드 계산 엔진
의존: api/collectors/bonddata.py, api/collectors/bondus.py
역할: collectors가 수집한 raw 금리 데이터를 분석 지표로 가공
      → verity_brain.py의 bond_regime 판단에 input으로 사용
"""

import logging
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# 0. 유틸리티 — Phase 1 collector 포맷 변환
# ──────────────────────────────────────────────

def curve_list_to_dict(curve: List[Dict[str, Any]]) -> Dict[str, float]:
    """Phase 1 곡선 리스트 → 분석용 dict 변환.
    [{"tenor": "1Y", "yield": 3.15}, ...] → {"1Y": 3.15, ...}
    """
    return {c["tenor"]: c["yield"] for c in curve if "tenor" in c and "yield" in c}


# ──────────────────────────────────────────────
# 1. 채권 가격·수익률 핵심 공식
# ──────────────────────────────────────────────

def calc_bond_price(face: float, coupon_rate: float, ytm: float,
                    periods: int, freq: int = 2) -> float:
    """
    채권 이론가격 (현재가치 할인 모델).
    face       : 액면금액 (예: 10000)
    coupon_rate: 연 이표율 (예: 0.035 = 3.5%)
    ytm        : 만기수익률 (예: 0.040 = 4.0%)
    periods    : 총 이표 지급 횟수 (잔존만기 * freq)
    freq       : 연간 이표 지급 횟수 (국채 = 2, 회사채 = 1 또는 2)
    """
    coupon = face * coupon_rate / freq
    r = ytm / freq
    if r == 0:
        return face + coupon * periods
    price = sum(coupon / (1 + r) ** t for t in range(1, periods + 1))
    price += face / (1 + r) ** periods
    return round(price, 4)


def calc_macaulay_duration(face: float, coupon_rate: float, ytm: float,
                           periods: int, freq: int = 2) -> float:
    """맥컬리 듀레이션 (연 단위)."""
    coupon = face * coupon_rate / freq
    r = ytm / freq
    price = calc_bond_price(face, coupon_rate, ytm, periods, freq)
    if price == 0:
        return 0.0

    weighted_cf = sum(
        (t / freq) * (coupon / (1 + r) ** t)
        for t in range(1, periods + 1)
    )
    weighted_cf += (periods / freq) * (face / (1 + r) ** periods)

    return round(weighted_cf / price, 4)


def calc_modified_duration(face: float, coupon_rate: float, ytm: float,
                           periods: int, freq: int = 2) -> float:
    """수정 듀레이션 — 금리 1bp 변동 시 가격 민감도."""
    d_mac = calc_macaulay_duration(face, coupon_rate, ytm, periods, freq)
    r = ytm / freq
    d_mod = d_mac / (1 + r) if r != -1 else 0.0
    return round(d_mod, 4)


def calc_dv01(face: float, coupon_rate: float, ytm: float,
              periods: int, freq: int = 2) -> float:
    """DV01 (Dollar Value of 1bp) — 금리 1bp 상승 시 가격 하락폭."""
    price = calc_bond_price(face, coupon_rate, ytm, periods, freq)
    d_mod = calc_modified_duration(face, coupon_rate, ytm, periods, freq)
    dv01 = d_mod * price * 0.0001
    return round(dv01, 6)


def calc_price_impact_scenarios(face: float, coupon_rate: float, ytm: float,
                                periods: int, freq: int = 2) -> Dict[str, Optional[float]]:
    """
    금리 시나리오별 채권 가격 변동 시뮬레이션.
    반환: { "+100bp": -8.5, "+50bp": -4.3, ... }  (% 변동)
    """
    base_price = calc_bond_price(face, coupon_rate, ytm, periods, freq)
    if base_price == 0:
        return {}
    scenarios = {"+200bp": 200, "+100bp": 100, "+50bp": 50,
                 "-50bp": -50, "-100bp": -100, "-200bp": -200}
    result: Dict[str, Optional[float]] = {}
    for label, bp in scenarios.items():
        new_ytm = ytm + bp * 0.0001
        if new_ytm <= 0:
            result[label] = None
            continue
        new_price = calc_bond_price(face, coupon_rate, new_ytm, periods, freq)
        pct_change = (new_price - base_price) / base_price * 100
        result[label] = round(pct_change, 2)
    return result


def calc_convexity(face: float, coupon_rate: float, ytm: float,
                   periods: int, freq: int = 2) -> float:
    """볼록성(Convexity) — 대폭 금리 변동 시 듀레이션 오차 보정."""
    coupon = face * coupon_rate / freq
    r = ytm / freq
    price = calc_bond_price(face, coupon_rate, ytm, periods, freq)
    if price == 0 or freq == 0:
        return 0.0

    convexity_sum = sum(
        (t * (t + 1) * coupon) / ((1 + r) ** (t + 2))
        for t in range(1, periods + 1)
    )
    convexity_sum += (periods * (periods + 1) * face) / ((1 + r) ** (periods + 2))

    return round(convexity_sum / (price * freq ** 2), 4)


# ──────────────────────────────────────────────
# 2. 수익률 곡선 분석
# ──────────────────────────────────────────────

def analyze_yield_curve(curve_data: Dict[str, float], market: str = "KR") -> Dict[str, Any]:
    """
    수익률 곡선 종합 분석.
    curve_data: { "1Y": 3.15, "3Y": 3.22, "10Y": 3.48, ... }
    market: "KR" | "US"
    """
    result: Dict[str, Any] = {"market": market, "analyzed_at": datetime.now().isoformat()}

    y_1m = curve_data.get("1M")
    y_3m = curve_data.get("3M")
    y_1y = curve_data.get("1Y")
    y_2y = curve_data.get("2Y")
    y_3y = curve_data.get("3Y")
    y_5y = curve_data.get("5Y")
    y_10y = curve_data.get("10Y")
    y_30y = curve_data.get("30Y")

    spreads: Dict[str, float] = {}
    if y_1y is not None and y_10y is not None:
        spreads["1y_10y_bp"] = round((y_10y - y_1y) * 100, 1)
    if y_2y is not None and y_10y is not None:
        spreads["2y_10y_bp"] = round((y_10y - y_2y) * 100, 1)
    if y_3m is not None and y_10y is not None:
        spreads["3m_10y_bp"] = round((y_10y - y_3m) * 100, 1)
    if y_3y is not None and y_10y is not None:
        spreads["3y_10y_bp"] = round((y_10y - y_3y) * 100, 1)
    if y_5y is not None and y_30y is not None:
        spreads["5y_30y_bp"] = round((y_30y - y_5y) * 100, 1)
    result["key_spreads"] = spreads

    # 경기침체 신호 — 3M-10Y 역전 (Fed 리서치 표준)
    recession_signal = False
    if "3m_10y_bp" in spreads:
        recession_signal = spreads["3m_10y_bp"] < -10
    elif "2y_10y_bp" in spreads:
        recession_signal = spreads["2y_10y_bp"] < -10
    result["recession_signal"] = recession_signal

    # 곡선 형태 분류
    primary_spread = spreads.get("2y_10y_bp") or spreads.get("1y_10y_bp")
    if primary_spread is not None:
        if primary_spread > 100:
            shape = "steep"
        elif primary_spread > 25:
            shape = "normal"
        elif primary_spread >= -10:
            shape = "flat"
        else:
            shape = "inverted"
    else:
        shape = "unknown"
    result["shape"] = shape

    # 레짐 판단 (단기 금리 수준 기반)
    short_rate = y_3m or y_1y
    if short_rate is not None:
        if market == "US":
            if short_rate > 5.0:
                regime = "rate_high_restrictive"
            elif short_rate > 3.5:
                regime = "rate_elevated"
            elif short_rate > 2.0:
                regime = "rate_normal"
            else:
                regime = "rate_low_accommodative"
        else:
            if short_rate > 4.0:
                regime = "rate_high_restrictive"
            elif short_rate > 3.0:
                regime = "rate_elevated"
            elif short_rate > 1.5:
                regime = "rate_normal"
            else:
                regime = "rate_low_accommodative"
        result["regime"] = regime

    # 투자 함의 텍스트
    interp_parts: List[str] = []
    if shape == "inverted":
        interp_parts.append("수익률 곡선 역전: 단기금리 > 장기금리, 경기침체 선행신호.")
    elif shape == "flat":
        interp_parts.append("수익률 곡선 플래트닝: 경기 불확실성 확대 국면.")
    elif shape == "steep":
        interp_parts.append("가파른 우상향 곡선: 경기회복 기대 및 인플레이션 우려 반영.")
    else:
        interp_parts.append("정상 우상향 곡선: 건전한 경기 확장 국면.")
    if recession_signal:
        interp_parts.append("경기침체 선행지표 발동 — 방어적 자산배분 고려.")
    result["interpretation"] = " ".join(interp_parts)

    return result


# ──────────────────────────────────────────────
# 3. 신용 스프레드 분석
# ──────────────────────────────────────────────

def analyze_credit_spreads(spreads: Dict[str, Any]) -> Dict[str, Any]:
    """
    신용 스프레드 수준 해석 → Verity Brain credit_cycle 판단 input.
    spreads: { "IG_OAS": 1.05, "HY_OAS": 3.52 } 또는 Phase 1 형식 키
    """
    ig = spreads.get("IG_OAS") or spreads.get("us_ig_oas")
    hy = spreads.get("HY_OAS") or spreads.get("us_hy_oas")

    result: Dict[str, Any] = {"analyzed_at": datetime.now().isoformat()}

    if hy is not None:
        if hy < 3.0:
            credit_cycle = "tightening"
            risk_appetite = "AGGRESSIVE"
        elif hy < 4.5:
            credit_cycle = "neutral"
            risk_appetite = "MODERATE"
        elif hy < 6.5:
            credit_cycle = "easing"
            risk_appetite = "CAUTIOUS"
        else:
            credit_cycle = "stress"
            risk_appetite = "DEFENSIVE"
        result["credit_cycle"] = credit_cycle
        result["risk_appetite"] = risk_appetite
        result["hy_oas"] = hy

    if ig is not None and hy is not None:
        result["ig_hy_gap_bp"] = round((hy - ig) * 100, 1)

    if hy is not None:
        if hy < 3.0:
            result["bond_strategy"] = "단기 하이일드 비중 확대 고려. 스프레드 추가 축소 제한적."
        elif hy < 4.5:
            result["bond_strategy"] = "투자등급 중심 유지. 하이일드 선별적 접근."
        elif hy < 6.5:
            result["bond_strategy"] = "하이일드 비중 축소. 투자등급 및 국채로 이동."
        else:
            result["bond_strategy"] = "국채·단기채 피난처 선호. 하이일드 회피."

    return result


# ──────────────────────────────────────────────
# 4. 메인 — portfolio.json bonds 섹션 분석 결과 생성
# ──────────────────────────────────────────────

def run_bond_analysis(portfolio_bonds: Dict[str, Any]) -> Dict[str, Any]:
    """
    portfolio.json의 bonds 섹션을 받아 분석 결과 dict 반환.
    verity_brain.py에서 호출하는 메인 인터페이스.

    portfolio_bonds: Phase 1 yieldcurve.py의 get_full_yield_curve_data() 반환값
    {
        "yield_curves": {
            "kr": {"curve": [{"tenor":"1Y","yield":3.15}, ...], "curve_shape": "normal"},
            "us": {"curve": [{"tenor":"1M","yield":5.31}, ...], "curve_shape": "flat", ...}
        },
        "credit_spreads": {"us_ig_oas": 1.05, "us_hy_oas": 3.52, ...}
    }
    """
    result: Dict[str, Any] = {"analyzed_at": datetime.now().isoformat()}

    yc = portfolio_bonds.get("yield_curves", {})

    kr_curve_list = yc.get("kr", {}).get("curve", [])
    us_curve_list = yc.get("us", {}).get("curve", [])

    if kr_curve_list:
        kr_dict = curve_list_to_dict(kr_curve_list)
        if kr_dict:
            result["kr_curve_analysis"] = analyze_yield_curve(kr_dict, "KR")

    if us_curve_list:
        us_dict = curve_list_to_dict(us_curve_list)
        if us_dict:
            result["us_curve_analysis"] = analyze_yield_curve(us_dict, "US")

    credit = portfolio_bonds.get("credit_spreads", {})
    if credit:
        result["credit_analysis"] = analyze_credit_spreads(credit)

    # Verity Brain용 종합 bond_regime
    us_shape = result.get("us_curve_analysis", {}).get("shape", "unknown")
    us_regime = result.get("us_curve_analysis", {}).get("regime", "unknown")
    credit_cycle = result.get("credit_analysis", {}).get("credit_cycle", "neutral")
    recession = result.get("us_curve_analysis", {}).get("recession_signal", False)

    result["bond_regime"] = {
        "rate_environment": us_regime,
        "curve_shape": us_shape,
        "credit_cycle": credit_cycle,
        "recession_signal": recession,
        "macro_override": recession,
    }

    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_us = {"3M": 5.28, "2Y": 4.82, "5Y": 4.62, "10Y": 4.55, "30Y": 4.61}
    print(json.dumps(analyze_yield_curve(test_us, "US"), ensure_ascii=False, indent=2))

    test_spreads = {"IG_OAS": 1.05, "HY_OAS": 3.52}
    print(json.dumps(analyze_credit_spreads(test_spreads), ensure_ascii=False, indent=2))
