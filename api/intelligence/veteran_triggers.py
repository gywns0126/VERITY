"""veteran_triggers — 헤지펀드 베테랑 정량 활동주의 trigger.

기존 구현 (보존):
  · Druckenmiller regime_weight: api/analyzers/multi_factor.py rate-environment 곱셈
  · Hohn 4 룰: api/intelligence/verity_brain.py _compute_moat_score (해자 + 가격결정력 + 청산가치 + ROE)

신규 추가 (2026-05-16 Sprint Day 1, 큐 b445ba47/839dc388/0b7aadbc):
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
    """Ackman (Pershing Square) activist target potential 정량화 — v2 (Perplexity MED-B 재설계).

    2026-05-16 Perplexity 검증 (docs/PERPLEXITY_VERIFICATION_RESULTS_v0.3.md MED-B):
    - PBR < 1.5 ❌ 부적합 (PS 진입 분포 0.6× JCP ~ 9× Chipotle, McD/Lowe/Hilton 모두 3-8×)
    - EV/EBITDA < 8 ❌ 부적합 (평균 10-14×, ADP 18×, Chipotle 15-25×)
    - ROE < 8% + GPM > 30% ⚠️ 부분 (핵심은 peer 대비 ROE gap ≥ 10%p)
    - 시총 임계: PS 메가캡 선호 (Hilton/ADP/Chipotle/Air Products 모두 $5B+)
                 KR 활동주의 (KCGI/Align) 5000억-2조 평균

    v2 재설계 (정합 PS 패턴):
    1. 메가캡 게이트 (US $5B+ / KR 5000억+) — PS 진입 사이즈
    2. peer 대비 ROE gap ≥ 10%p (Align Partners 은행주 PBR 0.34× vs 글로벌 1.3× 패턴)
    3. GPM > 30% = 해자 확인 필터 (브랜드 자산 정상화 잠재)
    4. 부채비율 < 200% (PS 진입 부담 적음 — 유지)
    5. SEC 13F Pershing Square holding 강한 보너스
    6. (보조) value gap — PBR/EV-EBITDA 가 peer 평균 보다 20% 이상 할인
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

    # 1) 메가캡 게이트 (필요조건) — PS 패턴 $5B+ / KR Align 5000억+
    if market_cap is None:
        return {"triggered": False, "score": int(score), "signals": [],
                "reason": "market_cap 미수집 — activist target 평가 불가"}
    threshold = 5e9 if is_us else 5e11  # US $5B / KR 5000억
    if market_cap < threshold:
        return {
            "triggered": False, "score": int(score), "signals": [],
            "reason": (f"시총 {market_cap:,.0f} < {threshold:.0e} "
                      f"({'PS 메가캡 선호 $5B+' if is_us else 'KR Align Partners 5000억+'})"),
        }
    signals.append(f"메가캡 게이트 통과 ({market_cap:,.0f})")
    score += 10

    # 2) peer 대비 ROE gap ≥ 10%p (핵심 — Pershing Square "잠재 vs 실현 ROE gap")
    sector = stock.get("sector")
    ticker = stock.get("ticker")
    recs = portfolio.get("recommendations") or []
    sector_peers = []
    if sector:
        sector_peers = [r for r in recs
                        if r.get("sector") == sector and r.get("ticker") != ticker]
    peer_roes = []
    for p in sector_peers:
        if is_us:
            p_roe = _safe_float((p.get("sec_financials") or {}).get("roe"))
        else:
            p_roe = _safe_float((p.get("kis_financial_ratio") or {}).get("roe"))
        if p_roe is not None:
            peer_roes.append(p_roe)
    if peer_roes and roe is not None and len(peer_roes) >= 2:
        peer_median_roe = sorted(peer_roes)[len(peer_roes) // 2]
        roe_gap = peer_median_roe - roe  # peer median 대비 본인이 얼마나 낮나
        if roe_gap >= 10:
            signals.append(
                f"ROE gap +{roe_gap:.1f}%p (본인 {roe:.1f} vs peer median {peer_median_roe:.1f}) "
                f"— Ackman 잠재 ROE gap 핵심 임계 충족"
            )
            score += 25  # 가장 중요한 시그널
        elif roe_gap >= 5:
            signals.append(f"ROE gap +{roe_gap:.1f}%p (peer 대비 약한 비효율)")
            score += 10
    elif roe is not None and roe < 0:
        # peer 데이터 없으면 fallback: ROE 음수 = 명백한 turnaround 후보
        signals.append(f"ROE {roe:.1f}% 음수 (turnaround 후보, peer 데이터 부족)")
        score += 15

    # 3) GPM > 30% = 해자 확인 필터 (브랜드/프랜차이즈 자산 — 정상화 잠재)
    if gpm is not None and gpm > 30:
        signals.append(f"GPM {gpm:.1f}% > 30 (해자/브랜드 확인 — 정상화 잠재)")
        score += 10

    # 4) 부채비율 < sector high 임계 (PS 진입 부담 적음) — sector_aware
    from api.analyzers.sector_thresholds import resolve_sector_bucket, get_debt_ratio_thresholds
    _debt_t_v = get_debt_ratio_thresholds(resolve_sector_bucket(stock))
    if debt_ratio is not None and debt_ratio < _debt_t_v["high"]:
        signals.append(
            f"부채비율 {debt_ratio:.0f}% < {_debt_t_v['high']:.0f} (활동주의 진입 부담 적음)"
        )
        score += 5

    # 5) 보조 — value gap (PBR/EV-EBITDA 가 peer 평균 보다 20%+ 할인)
    peer_pbrs = []
    for p in sector_peers:
        p_pbr = _safe_float(p.get("pbr") or p.get("price_to_book"))
        if p_pbr is not None and p_pbr > 0:
            peer_pbrs.append(p_pbr)
    if peer_pbrs and pbr is not None and pbr > 0 and len(peer_pbrs) >= 2:
        peer_median_pbr = sorted(peer_pbrs)[len(peer_pbrs) // 2]
        if pbr <= peer_median_pbr * 0.8:
            discount_pct = round((1 - pbr / peer_median_pbr) * 100, 0)
            signals.append(f"PBR {pbr:.2f} vs peer median {peer_median_pbr:.2f} "
                          f"(-{discount_pct}% 할인)")
            score += 10

    # 6) SEC 13F Pershing Square holding — 확정 신호 강한 보너스
    sec_13f = portfolio.get("sec_13f") or {}
    pershing = (sec_13f.get("holdings_by_fund") or {}).get("1336528") or {}
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
        "reason": (f"Ackman activist target {'발화' if triggered else '약함'} (v2 — peer ROE gap "
                  f"중심) — " + " / ".join(signals[:3])),
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
