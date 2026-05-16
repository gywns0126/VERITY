"""multi_bagger_signals — Multi-bagger Watch 결정 22 5 신호 정량 함수.

memory project_multi_bagger_watch 결정 22 — 텐버거 후보 신호 (매도 자제 보조).
정식 active 운영 = 2026-09 이후 (Phase 2-D 안정화 + 1년 paper trading).

이 모듈은 **코드 구현만** — 운영 적용은 후속 (multi_bagger_signals_active env gate).

5 신호:
  1. revenue_acceleration (Mauboussin & Rappaport, Expectations Investing 2001)
  2. operating_leverage (Mauboussin, More Than You Know — firm-level)
  3. category_leader  ⭐ P0a 정정 의제 (자체 정량 룰 — 점유율 1위 + 4분기 격차 확대)
  4. industry_s_curve (Everett Rogers, Diffusion of Innovations 1962)
  5. hold_pnl_threshold (Lynch One Up 1989 정성 원칙, 180d/+50% 정량은 자체 설정)

연관: docs/DECISION_LOG_MASTER.md 5/2 P0a (commit 7916b1f5 정정)
      memory project_multi_bagger_watch / project_phase_0_staged_framework
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def _safe_float(v: Any) -> Optional[float]:
    try:
        f = float(v)
        if f != f:
            return None
        return f
    except (TypeError, ValueError):
        return None


def _clip(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def detect_revenue_acceleration(stock: Dict[str, Any]) -> Dict[str, Any]:
    """신호 1 — 분기 매출 성장률이 직전 4분기 평균 대비 가속.

    출처: Mauboussin & Rappaport, *Expectations Investing* (2001) — value driver "sales growth".
    2026-05-16 Perplexity MED-C 검증: ≥ 15% YoY 임계 ✅ 정합
      (KOSPI/KOSDAQ 30Y 텐배거 128종목 진입 시점 분포에서 15-25% 구간이 50% 집중).
    보강: **2분기 연속 가속 확인** (단일 스파이크 = 기저효과 노이즈).

    데이터: stock.dart_financials.quarterly_revenue (KR) / sec_financials.revenue_history (US).
    """
    rev_growth = _safe_float(stock.get("revenue_growth"))
    if rev_growth is None:
        return {"triggered": False, "score": 50, "reason": "revenue_growth 미수집"}

    # ── 2분기 연속 가속 확인 (Perplexity 권장 보강) ──
    # quarterly_revenue history 있으면 직전 분기 대비 가속 검증
    consecutive_acceleration = None
    quarterly_history = (stock.get("dart_financials") or {}).get("quarterly_revenue")
    if not quarterly_history:
        quarterly_history = (stock.get("sec_financials") or {}).get("quarterly_revenue")
    if isinstance(quarterly_history, list) and len(quarterly_history) >= 3:
        try:
            q_growths = []
            for i in range(len(quarterly_history) - 1):
                prev = _safe_float(quarterly_history[i + 1])
                curr = _safe_float(quarterly_history[i])
                if prev and prev > 0:
                    q_growths.append((curr - prev) / prev * 100)
            if len(q_growths) >= 2:
                consecutive_acceleration = q_growths[0] > q_growths[1]
        except Exception:
            pass

    triggered = rev_growth >= 15
    # 2분기 연속 확인 시 점수 가산, 단일 스파이크면 점수 차감
    if consecutive_acceleration is True:
        score_boost = 10
    elif consecutive_acceleration is False:
        score_boost = -5
    else:
        score_boost = 0
    score = min(100, 50 + rev_growth * 2 + score_boost)

    reason_parts = [f"매출 YoY {rev_growth:+.1f}%"]
    if consecutive_acceleration is True:
        reason_parts.append("2Q 연속 가속 ✓ (Perplexity 권장 보강)")
    elif consecutive_acceleration is False:
        reason_parts.append("단일 분기 스파이크 (기저효과 의심)")
    else:
        reason_parts.append("quarterly_history 미수집 (가속 연속성 평가 불가)")
    reason_parts.append("가속 발화" if triggered else "미가속")
    return {
        "triggered": triggered, "score": int(score),
        "reason": " / ".join(reason_parts),
        "consecutive_acceleration": consecutive_acceleration,
    }


def detect_operating_leverage(stock: Dict[str, Any]) -> Dict[str, Any]:
    """신호 2 — 영업 레버리지 (DOL = OP Growth / Rev Growth).

    출처: Mauboussin, *More Than You Know* — firm-level operating leverage.
    2026-05-16 Perplexity MED-C 검증:
    - 임계 **DOL ≥ 2.5x** (3x → 2.5x 조정, Threshold Margin 시작점)
    - **OPM 절대값 ≥ 5% 필터 필수** (LGES 2021 사례: DOL 5.3x 였지만 OPM 4.3%
      → 기저효과 왜곡, 절대값 낮으면 노이즈)
    - 한국 슈퍼사이클 실증: 삼성전자 2017 DOL 4.5x / SK하이닉스 2017 DOL 4.2x /
      LGES 2021 DOL 5.3x (이익률 4.3% — 필터 미통과 예시)
    """
    rev_growth = _safe_float(stock.get("revenue_growth"))
    op_growth = _safe_float(
        stock.get("operating_profit_growth")
        or stock.get("eps_quarterly_growth")  # proxy
    )
    if rev_growth is None or op_growth is None:
        return {"triggered": False, "score": 50, "reason": "rev/op growth 미수집"}
    if rev_growth <= 0:
        return {"triggered": False, "score": 50,
                "reason": f"매출 감소 ({rev_growth:+.1f}%) — 레버리지 평가 X"}
    leverage_ratio = op_growth / rev_growth if rev_growth else 0

    # OPM 절대값 필터 (LGES 사례 교훈 — 기저효과 왜곡 방지)
    opm = _safe_float(stock.get("operating_margin") or stock.get("op_margin"))
    if opm is None:
        kfr = stock.get("kis_financial_ratio") or {}
        opm = _safe_float(kfr.get("operating_margin") or kfr.get("op_margin"))
    if opm is None:
        sec = stock.get("sec_financials") or {}
        opm = _safe_float(sec.get("operating_margin"))

    # 임계 정정 (Perplexity): 3x → 2.5x
    dol_threshold = 2.5
    triggered = leverage_ratio >= dol_threshold

    # OPM 5% 미달 시 기저효과 의심 → triggered=False 강제 (필터)
    opm_filter_passed = opm is None or opm >= 5.0
    if not opm_filter_passed:
        triggered = False

    score = min(100, 50 + leverage_ratio * 8)
    if opm is not None and opm >= 5.0:
        score += 5  # OPM 5%+ 보너스 (LGES 패턴 회피)
    elif opm is not None and opm < 5.0:
        score -= 10  # OPM 5% 미달 페널티

    opm_msg = f"OPM {opm:.1f}%" if opm is not None else "OPM 미수집"
    filter_msg = ""
    if opm is not None and opm < 5.0:
        filter_msg = " — OPM 5% 미달 (LGES 기저효과 패턴, triggered 강제 False)"
    return {
        "triggered": triggered, "score": int(_clip(score)),
        "reason": (f"OP {op_growth:+.1f}% / Rev {rev_growth:+.1f}% = DOL {leverage_ratio:.1f}x "
                  f"({'발화 ≥ 2.5x' if leverage_ratio >= dol_threshold else f'미발화 < 2.5x'}) "
                  f"· {opm_msg}{filter_msg}"),
        "dol": round(leverage_ratio, 2),
        "opm_filter_passed": opm_filter_passed,
    }


def detect_category_leader(
    stock: Dict[str, Any], portfolio: Dict[str, Any],
) -> Dict[str, Any]:
    """신호 3 ⭐ P0a — 카테고리 리더 (산업 점유율 1위 + 4분기 격차 확대).

    P0a 정정 (2026-05-02): Lynch *One Up* Ch.7 인용 부정확.
    자체 정량 룰 라벨링 = (점유율 1위 + 4분기 격차) 자체 설정.

    구현 (sector 시총 proxy + 매출 가속 격차):
      1) 같은 sector 내 종목들 (portfolio.recommendations 모집단) 중 시가총액 top 1
      2) 종목 매출 가속 > sector 평균 매출 가속 (격차 확대)

    데이터 의존:
      · stock.sector + stock.market_cap (top 1 판정)
      · stock.revenue_growth (격차)
      · portfolio.recommendations 가 같은 sector 종목 모집단

    현 운영 상태: sector 필드 propagation 결함으로 sector=None 다수 (별 audit 의제).
    sector 데이터 보강 후 자동 활성화.
    """
    sector = stock.get("sector")
    market_cap = _safe_float(stock.get("market_cap"))
    rev_growth = _safe_float(stock.get("revenue_growth"))
    ticker = stock.get("ticker")

    if not sector or market_cap is None or rev_growth is None:
        return {
            "triggered": False, "score": 50,
            "reason": f"필수 데이터 부족 (sector={sector}, mc={market_cap}, rev_g={rev_growth})",
        }

    # 같은 sector 종목 모집단 (recommendations 기준)
    recs = portfolio.get("recommendations") or []
    sector_peers = [
        r for r in recs
        if r.get("sector") == sector and r.get("ticker") != ticker
    ]
    if len(sector_peers) < 2:
        return {
            "triggered": False, "score": 50,
            "reason": f"sector '{sector}' peer < 2 (모집단 부족 — 자체 정량 룰 N/A)",
        }

    # 2026-05-16 Perplexity 검증 (docs/PERPLEXITY_VERIFICATION_RESULTS_v0.1.md Q4):
    # - Lynch 원전 점유율 격차 임계 X (fast grower = EPS 20-25% + PEG≤1)
    # - 한국 실증 (SK하이닉스 HBM 14-17%p / CATL vs LG엔솔 매출 2.8×) 권장:
    #   점유율 격차 ≥ 10%p AND 매출 배율 ≥ 2× = multi-bagger 발화점
    # 5%p → 10%p 정정 + 매출 배율 게이트 추가.

    # 1) 시총 top 1 판정 + 격차 배율 (peer 2위와 비교)
    peer_caps = sorted([_safe_float(r.get("market_cap")) or 0 for r in sector_peers], reverse=True)
    is_top = market_cap > peer_caps[0]
    cap_ratio = (market_cap / peer_caps[0]) if peer_caps and peer_caps[0] > 0 else 1.0
    is_wide_lead = cap_ratio >= 2.0  # 한국 실증: 매출 배율 2× (NAVER/SK하이닉스/CATL 패턴)

    # 2) 매출 가속 격차 — 본 종목 vs sector 평균. 임계 10%p (Perplexity 권장)
    peer_rev_growths = [_safe_float(r.get("revenue_growth")) for r in sector_peers]
    peer_rev_growths = [v for v in peer_rev_growths if v is not None]
    if not peer_rev_growths:
        return {"triggered": False, "score": 50,
                "reason": f"sector '{sector}' peer revenue_growth 데이터 0"}
    sector_avg_growth = sum(peer_rev_growths) / len(peer_rev_growths)
    growth_gap = rev_growth - sector_avg_growth
    is_widening = growth_gap >= 10  # 5%p → 10%p (한국 실증 정정 2026-05-16)

    # triggered = 시총 1위 + (격차 배율 2× OR 성장 격차 10%p)
    # 두 조건 중 1 만 충족해도 발화 — 매출 배율은 격차 신호로 보강
    triggered = is_top and (is_widening or is_wide_lead)
    score = 50
    if is_top:
        score += 15
    if is_wide_lead:
        score += 15  # 매출 배율 2× (한국 multi-bagger 패턴)
    if is_widening:
        score += 15  # 성장 격차 10%p (Perplexity 권장)
    return {
        "triggered": triggered, "score": int(score),
        "reason": (
            f"sector '{sector}': 시총 {'1위' if is_top else f'< {len(sector_peers)} peer'} "
            f"(2위 대비 {cap_ratio:.1f}×{', 2× 격차' if is_wide_lead else ''}) / "
            f"매출 격차 {growth_gap:+.1f}%p (sector 평균 {sector_avg_growth:+.1f}%, "
            f"{'≥10%p ✓' if is_widening else '<10%p'}) "
            f"{'카테고리 리더 발화' if triggered else '미발화'}"
        ),
        "is_top": is_top,
        "is_wide_lead": is_wide_lead,
        "cap_ratio_to_2nd": round(cap_ratio, 2),
        "growth_gap": round(growth_gap, 2),
        "sector_avg_growth": round(sector_avg_growth, 2),
        "peer_count": len(sector_peers),
    }


def detect_industry_s_curve(
    stock: Dict[str, Any], portfolio: Dict[str, Any],
) -> Dict[str, Any]:
    """신호 4 — 산업 매출 가속 (2년 CAGR > 직전 5년 CAGR × 1.5).

    출처: Everett Rogers, *Diffusion of Innovations* (1962). S-curve 채택 단계.
    """
    # 산업 CAGR 데이터 미수집 (sector_trends 활용 후속)
    return {"triggered": False, "score": 50,
            "reason": "산업 CAGR 데이터 미수집 (portfolio.sector_trends 보강 후 활성)"}


def detect_hold_pnl_threshold(stock: Dict[str, Any]) -> Dict[str, Any]:
    """신호 5 — 보유 180일+ AND 미실현 +50%+.

    출처: Lynch *One Up* 1989 정성 원칙 ("꽃을 뽑지마"). 180d/+50% 임계 자체 설정.
    """
    days = stock.get("hold_days") or stock.get("days_held")
    pnl = _safe_float(stock.get("unrealized_pnl_pct") or stock.get("return_pct"))
    if days is None or pnl is None:
        return {"triggered": False, "score": 50,
                "reason": "보유 일수 또는 미실현 손익률 미수집"}
    try:
        days = int(days)
    except (TypeError, ValueError):
        return {"triggered": False, "score": 50, "reason": "hold_days 파싱 실패"}
    triggered = days >= 180 and pnl >= 50
    return {
        "triggered": triggered, "score": 50 + (30 if triggered else 0),
        "reason": f"보유 {days}일 / 미실현 {pnl:+.1f}% "
                  f"({'발화 (180d + 50%)' if triggered else '미충족'})",
    }


def evaluate_multi_bagger_signals(
    stock: Dict[str, Any], portfolio: Dict[str, Any],
) -> Dict[str, Any]:
    """5 신호 일괄 평가. project_multi_bagger_watch 결정 22 정합.

    Returns:
        {
            "revenue_acceleration": {...},
            "operating_leverage": {...},
            "category_leader": {...},  ⭐ P0a
            "industry_s_curve": {...},
            "hold_pnl_threshold": {...},
            "alert_count": int (triggered=True 개수),
        }
    """
    s1 = detect_revenue_acceleration(stock)
    s2 = detect_operating_leverage(stock)
    s3 = detect_category_leader(stock, portfolio)
    s4 = detect_industry_s_curve(stock, portfolio)
    s5 = detect_hold_pnl_threshold(stock)
    count = sum(1 for r in (s1, s2, s3, s4, s5) if r.get("triggered"))
    return {
        "revenue_acceleration": s1,
        "operating_leverage": s2,
        "category_leader": s3,
        "industry_s_curve": s4,
        "hold_pnl_threshold": s5,
        "alert_count": count,
    }
