"""veteran_triggers — 헤지펀드 베테랑 정량 활동주의 trigger.

기존 박힘 (보존):
  · Druckenmiller regime_weight: api/analyzers/multi_factor.py rate-environment 곱셈
  · Hohn 4 룰: api/intelligence/verity_brain.py _compute_moat_score (해자 + 가격결정력 + 청산가치 + ROE)

신규 박힘 (2026-05-16 Sprint Day 1, 큐 b445ba47/839dc388/0b7aadbc):
  · Druckenmiller conviction concentration (확신 집중 베팅) — Brain score + VCI + macro regime 정합
  · Ackman activist target detector — value + activist potential 패턴
  · Hohn capital allocation 부실 — FCF 양수 but 환원 비율 < 30%

각 trigger 는 stock + portfolio → {triggered: bool, score: 0-100, signals: [...], reason: str}.
verity_brain.analyze_stock 에서 stock.veteran_signals 로 attach.

출처: docs/VERITY_SYSTEM_SPEC_2026.md §27 + 배리티 브레인 학습 도서 (저작권 자료, 로컬만)
       memory project_brain_kb_learning / feedback_source_attribution_discipline
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def _safe_float(v: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        f = float(v)
        if f != f:  # NaN
            return default
        return f
    except (TypeError, ValueError):
        return default


def _clip(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def detect_druckenmiller_conviction(
    stock: Dict[str, Any], portfolio: Dict[str, Any],
) -> Dict[str, Any]:
    """Druckenmiller "확신 있을 때 집중 베팅" 정량화 — Conviction Score (CS) 공식.

    2026-05-16 Perplexity 검증 반영 (docs/PERPLEXITY_VERIFICATION_RESULTS_v0.1.md Q3):
    - 정합 (|VCI|<15) = **필요조건이지 충분조건 X** (Druckenmiller 명시)
    - 3-레이어 (펀더멘털 + 기술 + 촉매) 동시 정렬 시 최대 사이즈
    - CS 공식: 0.45 × Fact + 0.35 × (100-|VCI|) + 0.20 × CatalystFlag
    - CS 임계: ≥75 Full / 55-75 중간 / 35-55 Invest-then-Investigate / <35 관망

    출처: Sohn 2022 ("Sizing is 70-80% of equation"), Norges Bank 2024
          (NAV 25% 채권 숏 = 중간 확신), GBP 1992 (200% 레버리지 = 일방적 확신)
    """
    vb = stock.get("verity_brain", {}) or stock.get("_brain_result", {}) or {}
    fact_data = vb.get("fact_score") or {}
    fact_score = _safe_float(fact_data.get("score") if isinstance(fact_data, dict)
                              else fact_data) or 50.0
    vci_data = vb.get("vci") or {}
    vci_val = _safe_float(vci_data.get("vci")) or 0.0
    brain_score = _safe_float(vb.get("brain_score")) or 0.0

    # ── Catalyst 검출 (3-레이어 중 외생 촉매) ──
    # 정책 결정자 발언 / 중앙은행 행동 / event_insights CRITICAL
    catalyst_flag = 0  # 0 or 20
    catalyst_sources: List[str] = []

    # 1) Perplexity event_insights CRITICAL
    event_insights = portfolio.get("event_insights") or []
    for ei in event_insights:
        if isinstance(ei, dict) and ei.get("severity") == "CRITICAL":
            catalyst_flag = 20
            catalyst_sources.append(f"Perplexity event: {ei.get('event', '?')[:40]}")
            break

    # 2) bond_regime 전환 (Druckenmiller 핵심 — 금리 환경 변화)
    bonds = portfolio.get("bonds") or {}
    bond_regime = (bonds.get("bond_regime") or {}).get("rate_environment")
    if bond_regime in ("rate_low_accommodative", "rate_elevated", "rate_high_restrictive"):
        if catalyst_flag == 0:
            catalyst_flag = 10  # 부분 catalyst (regime 자체)
        catalyst_sources.append(f"bond regime: {bond_regime}")

    # 3) market_horizon 전환점 (early_correction = catalyst)
    mh = portfolio.get("market_horizon") or {}
    cycle = mh.get("cycle_stage")
    if cycle == "early_correction":
        catalyst_flag = max(catalyst_flag, 15)
        catalyst_sources.append("market_horizon: early_correction 전환점")
    elif cycle == "panic":
        # panic = 진입 보류 (전환점 X)
        return {
            "triggered": False, "score": 30,
            "signals": [f"market_horizon: panic — Druckenmiller 진입 보류"],
            "reason": "panic regime: Invest-then-Investigate 모드 전환",
            "conviction_score": 30, "cs_tier": "관망",
        }

    # ── Conviction Score (CS) 공식 ──
    # Perplexity 권장: 0.45 × Fact + 0.35 × (100-|VCI|) + 0.20 × CatalystFlag
    vci_alignment = max(0.0, 100 - abs(vci_val))  # |VCI|=0 → 100, |VCI|≥50 → 0
    cs = 0.45 * fact_score + 0.35 * vci_alignment + 0.20 * catalyst_flag
    cs_int = int(_clip(cs))

    # ── 4단계 tier 매핑 (Druckenmiller 사이징 룰) ──
    if cs >= 75:
        cs_tier = "Full conviction (15-25% 포지션)"
        triggered = True
    elif cs >= 55:
        cs_tier = "중간 확신 (5-15% 포지션, NAV 25% 수준)"
        triggered = True
    elif cs >= 35:
        cs_tier = "Invest-then-Investigate (1-5% 감시 포지션)"
        triggered = False
    else:
        cs_tier = "관망 (확신 부재)"
        triggered = False

    signals = [
        f"Fact {fact_score:.0f}점 × 0.45",
        f"VCI 정합 {vci_alignment:.0f} × 0.35 (|VCI|={abs(vci_val):.0f})",
        f"Catalyst {catalyst_flag} × 0.20",
    ]
    if catalyst_sources:
        signals.append("촉매: " + " / ".join(catalyst_sources[:2]))
    signals.append(f"Brain score {brain_score:.0f}점 (참고)")

    reason = (
        f"Druckenmiller CS {cs_int} → {cs_tier} "
        f"({'발화' if triggered else '미발화'})"
    )
    return {
        "triggered": triggered,
        "score": cs_int,
        "conviction_score": cs_int,
        "cs_tier": cs_tier,
        "signals": signals,
        "reason": reason,
        "catalyst_flag": catalyst_flag,
        "catalyst_sources": catalyst_sources,
    }


def detect_ackman_activist_target(
    stock: Dict[str, Any], portfolio: Dict[str, Any],
) -> Dict[str, Any]:
    """Ackman (Pershing Square) activist target potential 정량화.

    원칙: "저평가 + 경영 비효율 + 카탈리스트 가능성 = activist 진입 target".
    - 저평가: PBR < 1.5 + EV/EBITDA < 8 (정량 valuation 미달)
    - 경영 비효율: ROE < 산업 평균 (또는 절대 < 8%) + GPM > 30% (잠재 mark 있음)
    - 카탈리스트 가능성: 부채 < 200% (균형) + 시총 ≥ 1000억 (소형주 X — activist target 사이즈)
    - 보너스: SEC 13F 에 Pershing Square (CIK 1336528) holding 신호
    """
    signals: List[str] = []
    score = 50.0
    is_us = stock.get("currency") == "USD"

    pbr = _safe_float(stock.get("pbr") or stock.get("price_to_book"))
    if is_us:
        sec_fin = stock.get("sec_financials") or {}
        pbr = pbr if pbr is not None else _safe_float(sec_fin.get("price_to_book"))
        roe = _safe_float(sec_fin.get("roe"))
        gpm = _safe_float(sec_fin.get("gross_margin"))
        debt_ratio = _safe_float(sec_fin.get("debt_ratio"))
        market_cap = _safe_float(sec_fin.get("market_cap"))
        ev_ebitda = _safe_float(sec_fin.get("ev_ebitda"))
    else:
        kfr = stock.get("kis_financial_ratio") or {}
        pbr = pbr if pbr is not None else _safe_float(kfr.get("pbr"))
        roe = _safe_float(kfr.get("roe"))
        gpm = _safe_float(kfr.get("gross_margin"))
        debt_ratio = _safe_float(kfr.get("debt_ratio"))
        market_cap = _safe_float(stock.get("market_cap"))
        ev_ebitda = _safe_float(stock.get("ev_ebitda"))

    # 1) 저평가 - PBR + EV/EBITDA 동시 충족 시 강한 신호
    val_hits = 0
    if pbr is not None and 0 < pbr < 1.5:
        signals.append(f"PBR {pbr:.2f} < 1.5 (저평가)")
        val_hits += 1
        score += 10
    if ev_ebitda is not None and 0 < ev_ebitda < 8:
        signals.append(f"EV/EBITDA {ev_ebitda:.1f} < 8 (저평가)")
        val_hits += 1
        score += 8
    if val_hits == 0:
        return {
            "triggered": False, "score": int(score), "signals": [],
            "reason": "valuation 게이트 미통과 (PBR ≥ 1.5 + EV/EBITDA ≥ 8)",
        }

    # 2) 경영 비효율 — 낮은 ROE + 높은 GPM (잠재 vs 실현 gap)
    if roe is not None and gpm is not None:
        if roe < 8 and gpm > 30:
            signals.append(f"ROE {roe:.1f}% < 8 + GPM {gpm:.1f}% > 30 (경영 비효율 — activist 개선 여지)")
            score += 15
        elif roe < 0:
            signals.append(f"ROE {roe:.1f}% 음수 (회사 부진 — activist turnaround 후보)")
            score += 8

    # 3) 카탈리스트 가능성 — 부채 적정 + 시총 충분
    if debt_ratio is not None and debt_ratio < 200:
        signals.append(f"부채비율 {debt_ratio:.0f}% < 200 (균형 — activist 진입 부담 적음)")
        score += 5
    if market_cap is not None:
        # KR: 1000억 원 (1e11) / US: $500M (5e8)
        threshold = 5e8 if is_us else 1e11
        if market_cap >= threshold:
            signals.append(f"시총 {market_cap:.0f} ≥ {threshold:.0e} (activist target size)")
            score += 5
        else:
            score -= 10
            signals.append(f"시총 {market_cap:.0f} < {threshold:.0e} (소형주 — activist 부적합)")

    # 4) 보너스: SEC 13F Pershing Square holding
    sec_13f = portfolio.get("sec_13f") or {}
    pershing = (sec_13f.get("holdings_by_fund") or {}).get("1336528") or {}
    ticker = stock.get("ticker") or ""
    if ticker and pershing.get("holdings"):
        tickers_held = [h.get("ticker") for h in pershing["holdings"]]
        if ticker.upper() in [t.upper() for t in tickers_held if t]:
            signals.append("Pershing Square 13F 보유 — activist 진입 확정 신호")
            score += 25

    triggered = score >= 70
    return {
        "triggered": triggered,
        "score": int(_clip(score)),
        "signals": signals,
        "reason": f"Ackman activist target {'발화' if triggered else '약함'} — " + " / ".join(signals[:3]),
    }


def detect_hohn_capital_allocation_inefficiency(
    stock: Dict[str, Any], portfolio: Dict[str, Any],
) -> Dict[str, Any]:
    """Hohn (TCI) capital allocation 부실 detector — activist target 6번째 요소.

    원칙: "FCF 양수인데 환원율 낮으면 capital allocation 부실, activist 진입 후보".
    - FCF 양수 (현금 창출력 검증)
    - 배당 + 자사주 매입 비율 < 30% (Hohn 임계, TCI 캠페인 사례 정합)
    - 대안: cash hoarding (현금성 자산 ≥ 시총 30%) → 자본 배분 비효율
    - 보너스: ROE > 10% (좋은 사업인데 자본 비효율 — 강한 activist trigger)
    """
    signals: List[str] = []
    score = 50.0
    is_us = stock.get("currency") == "USD"

    if is_us:
        sec_fin = stock.get("sec_financials") or {}
        fcf = _safe_float(sec_fin.get("free_cash_flow"))
        dividend_yield = _safe_float(sec_fin.get("dividend_yield"))
        buyback_ratio = _safe_float(sec_fin.get("buyback_yield"))
        cash_to_mc = _safe_float(sec_fin.get("cash_to_market_cap"))
        roe = _safe_float(sec_fin.get("roe"))
        market_cap = _safe_float(sec_fin.get("market_cap"))
    else:
        kfr = stock.get("kis_financial_ratio") or {}
        dart = stock.get("dart_financials") or {}
        cf = (dart.get("cash_flow") or {})
        fcf = _safe_float(cf.get("free_cash_flow"))
        dividend_yield = _safe_float(kfr.get("dividend_yield") or stock.get("dividend_yield"))
        buyback_ratio = _safe_float(stock.get("buyback_yield"))  # KR 미수집 가능성
        cash_to_mc = _safe_float(kfr.get("cash_to_market_cap"))
        roe = _safe_float(kfr.get("roe"))
        market_cap = _safe_float(stock.get("market_cap"))

    # 1) FCF 양수 검증 — 환원 능력 있음에도 부실인지 판단
    if fcf is None or fcf <= 0:
        return {
            "triggered": False, "score": int(score), "signals": [],
            "reason": "FCF 음수/미수집 — capital allocation 평가 불가",
        }
    signals.append(f"FCF 양수 (환원 능력 확인)")
    score += 5

    # 2) 환원 비율 검증
    total_return = (dividend_yield or 0) + (buyback_ratio or 0)
    if total_return < 1.0:  # < 1% 환원
        signals.append(f"환원율 {total_return:.1f}% < 1% (Hohn 임계 부실)")
        score += 25
    elif total_return < 3.0:
        signals.append(f"환원율 {total_return:.1f}% < 3% (낮음)")
        score += 10
    else:
        signals.append(f"환원율 {total_return:.1f}% 적정 (≥ 3%)")
        score -= 5

    # 3) Cash hoarding — 현금성 자산이 시총 30%+ 인데 환원 안 하면 강한 신호
    if cash_to_mc is not None and cash_to_mc >= 30:
        signals.append(f"Cash/시총 {cash_to_mc:.0f}% ≥ 30% (cash hoarding — 자본 비효율)")
        score += 15

    # 4) 보너스 — ROE > 10% (좋은 사업) + 환원 부실 = 강한 activist trigger
    if roe is not None and roe > 10 and total_return < 3.0:
        signals.append(f"ROE {roe:.1f}% > 10 + 환원 부실 = 강한 activist trigger (TCI 캠페인 패턴)")
        score += 15

    triggered = score >= 70
    return {
        "triggered": triggered,
        "score": int(_clip(score)),
        "signals": signals,
        "reason": f"Hohn capital allocation {'부실 발화' if triggered else '정상/약함'} — "
                  + " / ".join(signals[:3]),
    }


def evaluate_all_veteran_triggers(
    stock: Dict[str, Any], portfolio: Dict[str, Any],
) -> Dict[str, Any]:
    """3 베테랑 trigger 일괄 평가 — verity_brain.analyze_stock 에서 호출.

    Returns:
        {
            "druckenmiller_conviction": {...},
            "ackman_activist_target": {...},
            "hohn_capital_allocation": {...},
            "veteran_alert_count": int (triggered=True 개수),
        }
    """
    drk = detect_druckenmiller_conviction(stock, portfolio)
    ack = detect_ackman_activist_target(stock, portfolio)
    hoh = detect_hohn_capital_allocation_inefficiency(stock, portfolio)
    count = sum(1 for r in (drk, ack, hoh) if r.get("triggered"))
    return {
        "druckenmiller_conviction": drk,
        "ackman_activist_target": ack,
        "hohn_capital_allocation": hoh,
        "veteran_alert_count": count,
    }
