"""
퀄리티 팩터 엔진

학술 근거:
  - Piotroski (2000): F-Score — 9개 재무 시그널로 가치주 중 '진짜 싼 주식' 선별
  - Novy-Marx (2013): Gross Profitability — 매출총이익/자산이 수익 예측에 강력
  - Altman (1968): Z-Score — 재무 건전성(파산 확률)
  - Asness, Frazzini & Pedersen (2019): Quality Minus Junk (QMJ) 팩터

구현 팩터:
  1. Piotroski F-Score (0~9)
  2. Gross Profitability Ratio
  3. Altman Z-Score (변형)
  4. 종합 퀄리티 점수 (0~100)
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


def compute_piotroski_f_score(stock: Dict[str, Any]) -> Tuple[int, List[str]]:
    """
    Piotroski F-Score (0~9).

    수익성 (4점):
      F1: ROA > 0
      F2: 영업현금흐름 > 0
      F3: ROA 전년 대비 개선
      F4: 영업현금흐름 > 순이익 (발생주의 품질)

    레버리지/유동성 (3점):
      F5: 부채비율 전년 대비 감소
      F6: 유동비율 전년 대비 개선
      F7: 신주 미발행

    효율성 (2점):
      F8: 매출총이익률 전년 대비 개선
      F9: 자산회전율 전년 대비 개선
    """
    f_score = 0
    details: List[str] = []

    roe = stock.get("roe") or 0
    roa = stock.get("roa") or (roe * 0.5 if roe else 0)
    op_margin = stock.get("operating_margin") or 0
    debt = stock.get("debt_ratio") or 0

    dart = stock.get("dart_financials") or {}
    cf = dart.get("cashflow") or {}
    fcf = cf.get("free_cashflow") or stock.get("free_cashflow") or 0
    op_cf = cf.get("operating_cashflow") or fcf

    prev = stock.get("prev_year") or {}
    prev_roa = prev.get("roa") or 0
    prev_debt = prev.get("debt_ratio") or debt
    prev_gp_margin = prev.get("gross_margin") or 0
    prev_asset_turnover = prev.get("asset_turnover") or 0

    gross_margin = stock.get("gross_margin") or (op_margin * 1.3 if op_margin > 0 else 0)
    asset_turnover = stock.get("asset_turnover") or 0
    net_income = stock.get("net_income") or 0

    # F1: ROA > 0
    if roa > 0:
        f_score += 1
        details.append("F1: ROA 양수")

    # F2: 영업현금흐름 > 0
    if op_cf > 0:
        f_score += 1
        details.append("F2: 영업CF 양수")

    # F3: ROA 전년 대비 개선
    if roa > prev_roa and prev_roa != 0:
        f_score += 1
        details.append("F3: ROA 개선")

    # F4: 현금흐름 > 순이익 (어닝 퀄리티)
    if op_cf > net_income and net_income != 0:
        f_score += 1
        details.append("F4: 현금흐름 > 순이익")
    elif op_cf > 0 and net_income <= 0:
        f_score += 1
        details.append("F4: CF 양수 / 순손실")

    # F5: 부채비율 감소
    if debt < prev_debt and prev_debt > 0:
        f_score += 1
        details.append("F5: 부채 감소")

    # F6: 유동비율 개선 (데이터 있을 때만)
    current_ratio = stock.get("current_ratio") or 0
    prev_current = prev.get("current_ratio") or 0
    if current_ratio > prev_current and prev_current > 0:
        f_score += 1
        details.append("F6: 유동성 개선")
    elif current_ratio >= 1.5:
        f_score += 1
        details.append("F6: 유동비율 양호")

    # F7: 신주 미발행 (데이터 없으면 통과)
    shares_issued = stock.get("shares_change_pct") or 0
    if shares_issued <= 0:
        f_score += 1
        details.append("F7: 희석 없음")

    # F8: 매출총이익률 개선
    if gross_margin > prev_gp_margin and prev_gp_margin > 0:
        f_score += 1
        details.append("F8: 총이익률 개선")
    elif gross_margin >= 30:
        f_score += 1
        details.append("F8: 총이익률 양호")

    # F9: 자산회전율 개선
    if asset_turnover > prev_asset_turnover and prev_asset_turnover > 0:
        f_score += 1
        details.append("F9: 자산효율 개선")
    elif asset_turnover >= 0.8:
        f_score += 1
        details.append("F9: 자산회전 양호")

    return f_score, details


def compute_gross_profitability(stock: Dict[str, Any]) -> float:
    """
    Novy-Marx Gross Profitability = 매출총이익 / 총자산.
    데이터가 없으면 영업이익률로 프록시.
    반환: 0.0~1.0+ (비율)
    """
    gp = stock.get("gross_profit")
    total_assets = stock.get("total_assets")

    if gp and total_assets and total_assets > 0:
        return round(gp / total_assets, 4)

    op_margin = stock.get("operating_margin") or 0
    revenue = stock.get("revenue") or 0
    if op_margin > 0 and revenue > 0 and total_assets and total_assets > 0:
        estimated_gp = revenue * (op_margin / 100) * 1.3
        return round(estimated_gp / total_assets, 4)

    return op_margin / 100 if op_margin > 0 else 0.0


def compute_altman_z(stock: Dict[str, Any]) -> Dict[str, Any]:
    """
    Altman Z-Score 변형 (비제조업 포함, 한국 시장 적응).

    원본: Z = 1.2*X1 + 1.4*X2 + 3.3*X3 + 0.6*X4 + 1.0*X5
      X1 = 운전자본/총자산
      X2 = 이익잉여금/총자산
      X3 = EBIT/총자산
      X4 = 시가총액/총부채
      X5 = 매출/총자산

    Z > 2.99: 안전, 1.81~2.99: 회색, Z < 1.81: 위험
    """
    total_assets = stock.get("total_assets") or 0
    if total_assets <= 0:
        return {"z_score": None, "zone": "unknown", "label": "데이터 부족"}

    # X1: 운전자본 / 총자산
    working_capital = stock.get("working_capital") or 0
    x1 = working_capital / total_assets

    # X2: 이익잉여금 / 총자산 (retained earnings proxy)
    retained = stock.get("retained_earnings") or 0
    if retained == 0:
        roe = stock.get("roe") or 0
        equity = total_assets * (1 - (stock.get("debt_ratio") or 50) / 100)
        retained = equity * (roe / 100) * 3 if roe > 0 else 0
    x2 = retained / total_assets

    # X3: EBIT / 총자산
    op_income = stock.get("operating_income") or 0
    if op_income == 0:
        op_margin = stock.get("operating_margin") or 0
        revenue = stock.get("revenue") or 0
        op_income = revenue * op_margin / 100
    x3 = op_income / total_assets

    # X4: 시가총액 / 총부채
    market_cap = stock.get("market_cap") or 0
    total_debt = stock.get("total_debt") or (total_assets * (stock.get("debt_ratio") or 50) / 100)
    x4 = market_cap / total_debt if total_debt > 0 else 5.0

    # X5: 매출 / 총자산
    revenue = stock.get("revenue") or 0
    x5 = revenue / total_assets

    z = 1.2 * x1 + 1.4 * x2 + 3.3 * x3 + 0.6 * x4 + 1.0 * x5

    if z > 2.99:
        zone = "safe"
        label = f"안전 (Z={z:.2f})"
    elif z > 1.81:
        zone = "grey"
        label = f"회색지대 (Z={z:.2f})"
    else:
        zone = "distress"
        label = f"위험 (Z={z:.2f})"

    return {
        "z_score": round(z, 2),
        "zone": zone,
        "label": label,
        "components": {
            "x1_working_capital": round(x1, 4),
            "x2_retained": round(x2, 4),
            "x3_ebit": round(x3, 4),
            "x4_market_debt": round(x4, 4),
            "x5_turnover": round(x5, 4),
        },
    }


def compute_quality_score(stock: Dict[str, Any]) -> Dict[str, Any]:
    """
    종합 퀄리티 점수 (0~100).

    배점:
      Piotroski F-Score (0~9 → 정규화): 35점
      Gross Profitability:              25점
      Altman Z-Score 안전도:            20점
      어닝 퀄리티 (CF > NI):           10점
      수익성 안정 (ROE 지속):           10점
    """
    signals: List[str] = []

    # 1. Piotroski F-Score (35점)
    f_score, f_details = compute_piotroski_f_score(stock)
    f_norm = (f_score / 9) * 35
    if f_score >= 7:
        signals.append(f"F-Score {f_score}/9 우량")
    elif f_score <= 3:
        signals.append(f"F-Score {f_score}/9 취약")

    # 2. Gross Profitability (25점)
    gp = compute_gross_profitability(stock)
    if gp >= 0.33:
        gp_score = 25
        signals.append(f"총이익률/자산 {gp:.1%} 고수익")
    elif gp >= 0.20:
        gp_score = 20
    elif gp >= 0.10:
        gp_score = 12
    elif gp > 0:
        gp_score = 5
    else:
        gp_score = 0

    # 3. Altman Z-Score (20점)
    altman = compute_altman_z(stock)
    z = altman.get("z_score")
    if z is not None:
        if z > 2.99:
            z_score = 20
        elif z > 2.5:
            z_score = 16
        elif z > 1.81:
            z_score = 10
            signals.append(f"Altman Z {z:.1f} 회색지대")
        else:
            z_score = 2
            signals.append(f"Altman Z {z:.1f} 위험")
    else:
        z_score = 10

    # 4. 어닝 퀄리티 (10점)
    dart = stock.get("dart_financials") or {}
    cf = dart.get("cashflow") or {}
    op_cf = cf.get("operating_cashflow") or cf.get("free_cashflow") or 0
    ni = stock.get("net_income") or 0
    if op_cf > 0 and ni > 0 and op_cf > ni:
        eq_score = 10
        signals.append("현금이익 > 회계이익")
    elif op_cf > 0:
        eq_score = 6
    else:
        eq_score = 2

    # 5. 수익성 안정 (10점)
    roe = stock.get("roe") or 0
    op_margin = stock.get("operating_margin") or 0
    stab_score = 0
    if roe >= 15 and op_margin >= 10:
        stab_score = 10
    elif roe >= 10 and op_margin >= 5:
        stab_score = 7
    elif roe >= 5:
        stab_score = 4
    elif roe > 0:
        stab_score = 2

    total = round(max(0, min(100, f_norm + gp_score + z_score + eq_score + stab_score)))

    return {
        "quality_score": total,
        "piotroski_f": f_score,
        "piotroski_details": f_details,
        "gross_profitability": round(gp, 4),
        "altman": altman,
        "components": {
            "f_score_pts": round(f_norm, 1),
            "gross_profit_pts": gp_score,
            "altman_pts": z_score,
            "earning_quality_pts": eq_score,
            "stability_pts": stab_score,
        },
        "signals": signals[:5],
    }
