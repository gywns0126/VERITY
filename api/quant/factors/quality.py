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

    금융/리츠 (KSIC 64~66, 68) — Perplexity Q-fin-5 2026-05-19:
      F5 "부채 감소 = 좋음" 신호가 학술 정합 X (예금/보험 부채 = 비즈니스 raw material).
      applicable=False 반환 → 호출처(compute_quality_score) 0점 처리.
      대체 = CAMELS / BIS CET1 proxy 컴포넌트 (별 sprint 큐).
    """
    from api.analyzers.sector_thresholds import is_financial_excluded

    if is_financial_excluded(stock):
        return (-1, ["F-Score 미적용 (금융/리츠 — CAMELS/BIS 별도)"])

    f_score = 0
    details: List[str] = []

    roe = stock.get("roe") or 0
    roa = stock.get("roa") or (roe * 0.5 if roe else 0)
    op_margin = stock.get("operating_margin") or 0
    debt = stock.get("debt_ratio") or 0

    dart = stock.get("dart_financials") or {}
    cf = dart.get("cashflow") or {}
    # op_cf fallback chain: dart_financials → stock(top-level) → fcf
    # 2026-05-20 fix — stock.get("operating_cashflow") 누락 (DART CFS 호출 후 stock dict
    # top-level 값 사용 못함 → F2/F4 영구 0 score 버그)
    fcf = cf.get("free_cashflow") or stock.get("free_cashflow") or 0
    op_cf = cf.get("operating_cashflow") or stock.get("operating_cashflow") or fcf

    # 시계열 Δ — fscore_deltas (사이클 섹터 8Q AND 게이트 포함) 1순위, prev_year 2순위.
    # 2026-05-20 wire ([[project_industry_themes_tracker]] sprint 후 자연 후속).
    # fscore_deltas = main.py:2635 직전에 attach_fscore_deltas(stock) 호출로 채워짐.
    deltas = stock.get("fscore_deltas") or {}
    delta_roa = deltas.get("delta_roa")
    delta_lev_neg = deltas.get("c5_delta_leverage_negative")
    delta_cr_pos = deltas.get("c6_delta_current_ratio_positive")
    delta_gm_pos = deltas.get("c8_delta_gross_margin_positive")
    delta_at_pos = deltas.get("c9_delta_asset_turnover_positive")

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

    # F3: ROA 전년 대비 개선 (fscore_deltas 1순위, prev_year 2순위)
    if delta_roa is not None and delta_roa > 0:
        f_score += 1
        details.append(f"F3: ΔROA={delta_roa:+.4f} 개선 (jsonl)")
    elif roa > prev_roa and prev_roa != 0:
        f_score += 1
        details.append("F3: ROA 개선 (prev_year)")

    # F4: 현금흐름 > 순이익 (어닝 퀄리티)
    if op_cf > net_income and net_income != 0:
        f_score += 1
        details.append("F4: 현금흐름 > 순이익")
    elif op_cf > 0 and net_income <= 0:
        f_score += 1
        details.append("F4: CF 양수 / 순손실")

    # F5: 부채비율 감소 (fscore_deltas 1순위)
    if delta_lev_neg is True:
        f_score += 1
        details.append("F5: 부채 감소 (jsonl)")
    elif delta_lev_neg is None and debt < prev_debt and prev_debt > 0:
        f_score += 1
        details.append("F5: 부채 감소 (prev_year)")

    # F6: 유동비율 개선 (fscore_deltas 1순위)
    current_ratio = stock.get("current_ratio") or 0
    prev_current = prev.get("current_ratio") or 0
    if delta_cr_pos is True:
        f_score += 1
        details.append("F6: 유동비율 개선 (jsonl)")
    elif delta_cr_pos is None and current_ratio > prev_current and prev_current > 0:
        f_score += 1
        details.append("F6: 유동성 개선 (prev_year)")
    elif delta_cr_pos is None and current_ratio >= 1.5:
        f_score += 1
        details.append("F6: 유동비율 양호")

    # F7: 신주 미발행 (데이터 없으면 통과)
    shares_issued = stock.get("shares_change_pct") or 0
    if shares_issued <= 0:
        f_score += 1
        details.append("F7: 희석 없음")

    # F8: 매출총이익률 개선 (fscore_deltas 1순위)
    if delta_gm_pos is True:
        f_score += 1
        details.append("F8: 총이익률 개선 (jsonl)")
    elif delta_gm_pos is None and gross_margin > prev_gp_margin and prev_gp_margin > 0:
        f_score += 1
        details.append("F8: 총이익률 개선 (prev_year)")
    elif delta_gm_pos is None and gross_margin >= 30:
        f_score += 1
        details.append("F8: 총이익률 양호")

    # F9: 자산회전율 개선 (fscore_deltas 1순위)
    if delta_at_pos is True:
        f_score += 1
        details.append("F9: 자산회전율 개선 (jsonl)")
    elif delta_at_pos is None and asset_turnover > prev_asset_turnover and prev_asset_turnover > 0:
        f_score += 1
        details.append("F9: 자산효율 개선 (prev_year)")
    elif delta_at_pos is None and asset_turnover >= 0.8:
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
    Altman Z-Score 한국 정합 (2026-05-19 재작성 — Perplexity Q-fin-1/2 학술 자문 + PM 승인).

    [WHY] 이전 = 원본 1968 미국식 (1.2/1.4/3.3/0.6/1.0, 컷 2.99/1.81). 한국 제조업 D/E
          100~150% vs 미국 60~80% 환경에서 systematic 저평가. 4대 금융지주 1176% →
          false distress. memory project_altman_z_korea_standard / q1_q6_batch 정합.

    [DATA] Perplexity Q-fin-1 (RISS/koreascience JAKO201535257998954) +
           Q-fin-2 (SSRN 5044057 리뷰).

    [EXPECTED] 시장별 산식 + 금융주 hard exclusion.

    분기:
      금융/리츠 (KSIC 64~66, 68) → applicable=False (CAMELS/BIS 별 sprint)
      KOSPI 제조업 → 원본 Z (1.2X1 + 1.4X2 + 3.3X3 + 0.6X4 + 1.0X5), 컷 Safe ≥ 2.3
      KOSDAQ 또는 비제조 → Z″ EM (3.25 + 6.56X1 + 3.26X2 + 6.72X3 + 1.05X4),
                            컷 Safe ≥ 2.6 / Grey 1.1~2.6 / Distress < 1.1, X5(매출/자산) 제거
      X1 = 운전자본/총자산 (계수 6.56, wallstreetprep/Altman 원전 정합 — 2026-05-20 정정)
      X3 = EBIT/총자산 (계수 6.72)
      X4 = 시가총액/총부채 (상장사 표준, Q-fin-2 답변 정합)
    """
    from api.analyzers.sector_thresholds import is_financial_excluded, resolve_sector_bucket

    # 1) 금융/리츠 hard exclusion (Perplexity Q-fin-5)
    if is_financial_excluded(stock):
        return {
            "z_score": None,
            "zone": "not_applicable",
            "label": "금융/리츠 — CAMELS/BIS 별도 평가",
            "model_variant": "excluded_financial",
            "applicable": False,
        }

    total_assets = stock.get("total_assets") or 0
    if total_assets <= 0:
        return {"z_score": None, "zone": "unknown", "label": "데이터 부족", "applicable": False}

    # X1: 운전자본 / 총자산
    working_capital = stock.get("working_capital") or 0
    x1 = working_capital / total_assets

    # X2: 이익잉여금 / 총자산
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
        revenue_for_ebit = stock.get("revenue") or 0
        op_income = revenue_for_ebit * op_margin / 100
    x3 = op_income / total_assets

    # X4: 시가총액 / 총부채 (Q-fin-2: 상장사 표준)
    market_cap = stock.get("market_cap") or 0
    total_debt = stock.get("total_debt") or (total_assets * (stock.get("debt_ratio") or 50) / 100)
    x4 = market_cap / total_debt if total_debt > 0 else 5.0

    # 2) 시장별 산식 dispatch
    market = str(stock.get("market") or "").upper()
    bucket = resolve_sector_bucket(stock)
    is_kospi_mfg = (market in ("KOSPI", "KS")) and (bucket == "제조")

    if is_kospi_mfg:
        # KOSPI 제조업 = 원본 Z + 한국 임계 2.3
        x5 = (stock.get("revenue") or 0) / total_assets
        z = 1.2 * x1 + 1.4 * x2 + 3.3 * x3 + 0.6 * x4 + 1.0 * x5
        model_variant = "korean_kospi_mfg"
        safe_cut, distress_cut = 2.3, 1.1
        components = {
            "x1_working_capital": round(x1, 4),
            "x2_retained": round(x2, 4),
            "x3_ebit": round(x3, 4),
            "x4_market_debt": round(x4, 4),
            "x5_turnover": round(x5, 4),
        }
    else:
        # KOSDAQ / 비제조 / 미상 = Z″ EM (Altman Emerging Market)
        # X1(W/C) 계수 = 6.56 학술 원전 (wallstreetprep / Altman/Hartzell/Peck 1995)
        # 2026-05-20 drift 정정 — 메모리 5/14 의 6.72 표기 + 5/19 commit 28e99a19 답습 wrong
        z = 3.25 + 6.56 * x1 + 3.26 * x2 + 6.72 * x3 + 1.05 * x4
        model_variant = "emerging_market_zpp"
        safe_cut, distress_cut = 2.6, 1.1
        components = {
            "x1_working_capital": round(x1, 4),
            "x2_retained": round(x2, 4),
            "x3_ebit": round(x3, 4),
            "x4_market_debt": round(x4, 4),
            "x5_turnover": None,
        }

    if z >= safe_cut:
        zone = "safe"
        label = f"안전 (Z={z:.2f}, cut={safe_cut})"
    elif z >= distress_cut:
        zone = "grey"
        label = f"회색지대 (Z={z:.2f})"
    else:
        zone = "distress"
        label = f"위험 (Z={z:.2f})"

    return {
        "z_score": round(z, 2),
        "zone": zone,
        "label": label,
        "model_variant": model_variant,
        "applicable": True,
        "safe_cut": safe_cut,
        "distress_cut": distress_cut,
        "components": components,
    }


def annualize_quarterly_cumulative(value: float, reprt_code: str) -> Optional[float]:
    """DART 분기 보고서 누적값 → 연간 환산 (Perplexity Q-fin-3 — TTM 우선 권고, ×4 = 임시 추정치).

    [WHY] DART fnlttSinglAcntAll 분기 응답 IS/CF 항목 = 누적값.
          1Q=3M / 반기=6M / 3Q=9M / 연간=12M. 미환산 시 1Q 종목이 연간 종목 대비
          1/4 EBIT 로 systematic 저평가 (Altman X3 등).

    [WHEN] 임시 추정치. TTM 4Q rolling sum 인프라 (dart_quarterly_snapshots.jsonl
           누적 ≥ 2년 후) 구축 전까지 fallback. F-Score 시계열 Δ sprint 와 함께 진입.

    reprt_code: "11011" 연간 / "11012" 반기 / "11013" 1Q / "11014" 3Q
    """
    if value is None:
        return None
    months_map = {"11013": 3, "11012": 6, "11014": 9, "11011": 12}
    months = months_map.get(reprt_code)
    if not months or months == 12:
        return value
    return value * (12.0 / months)


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

    # 1. Piotroski F-Score (35점) — 금융/리츠 미적용 (Perplexity Q-fin-5)
    f_score, f_details = compute_piotroski_f_score(stock)
    if f_score < 0:
        f_norm = 0
        signals.append("F-Score 미적용 (금융/리츠)")
    else:
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

    # 3. Altman Z-Score (20점) — 시장별 cut 동적 매핑 (Perplexity Q-fin-1)
    altman = compute_altman_z(stock)
    z = altman.get("z_score")
    safe_cut = altman.get("safe_cut") or 2.3
    distress_cut = altman.get("distress_cut") or 1.1
    if altman.get("applicable") is False:
        # 금융/리츠 — CAMELS/BIS proxy 컴포넌트 신설 전까지 배점 0 + 명시 (RULE 6 정합 신호)
        z_score = 0
        signals.append("Altman 미적용 (금융/리츠)")
    elif z is not None:
        # safe_cut~safe_cut+0.7 사이는 보강 점수, distress~safe 사이 grey, distress 미만 위험
        if z >= safe_cut + 0.7:
            z_score = 20
        elif z >= safe_cut:
            z_score = 16
        elif z >= distress_cut:
            z_score = 10
            signals.append(f"Altman Z {z:.1f} 회색지대 (cut {safe_cut})")
        else:
            z_score = 2
            signals.append(f"Altman Z {z:.1f} 위험 (cut {distress_cut})")
    else:
        z_score = 10

    # 4. 어닝 퀄리티 (10점)
    dart = stock.get("dart_financials") or {}
    cf = dart.get("cashflow") or {}
    op_cf = (cf.get("operating_cashflow") or stock.get("operating_cashflow")
             or cf.get("free_cashflow") or 0)
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
