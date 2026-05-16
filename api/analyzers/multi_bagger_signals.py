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


def detect_revenue_acceleration(stock: Dict[str, Any]) -> Dict[str, Any]:
    """신호 1 — 분기 매출 성장률이 직전 4분기 평균 대비 가속.

    출처: Mauboussin & Rappaport, *Expectations Investing* (2001) — value driver "sales growth".
    데이터: stock.dart_financials.quarterly_revenue (KR) / sec_financials.revenue_history (US).
    """
    # 데이터 구조 미정착 — 단순 yoy 가속 proxy
    rev_growth = _safe_float(stock.get("revenue_growth"))
    if rev_growth is None:
        return {"triggered": False, "score": 50, "reason": "revenue_growth 미수집"}
    # proxy: 직전 yoy > 0 + 가속 임계 ≥ 15% (Mauboussin Stage 2 정의)
    triggered = rev_growth >= 15
    score = min(100, 50 + rev_growth * 2)
    return {
        "triggered": triggered, "score": int(score),
        "reason": f"매출 YoY {rev_growth:+.1f}% ({'가속 발화' if triggered else '미가속'})",
    }


def detect_operating_leverage(stock: Dict[str, Any]) -> Dict[str, Any]:
    """신호 2 — 분기 영업이익 성장률 > 매출 성장률 × 3.

    출처: Mauboussin, *More Than You Know* — firm-level operating leverage.
    """
    rev_growth = _safe_float(stock.get("revenue_growth"))
    op_growth = _safe_float(
        stock.get("operating_profit_growth")
        or stock.get("eps_quarterly_growth")  # proxy
    )
    if rev_growth is None or op_growth is None:
        return {"triggered": False, "score": 50, "reason": "rev/op growth 미수집"}
    if rev_growth <= 0:
        return {"triggered": False, "score": 50, "reason": f"매출 감소 ({rev_growth:+.1f}%) — 레버리지 평가 X"}
    leverage_ratio = op_growth / rev_growth if rev_growth else 0
    triggered = leverage_ratio > 3
    score = min(100, 50 + leverage_ratio * 8)
    return {
        "triggered": triggered, "score": int(score),
        "reason": f"OP {op_growth:+.1f}% / Rev {rev_growth:+.1f}% = {leverage_ratio:.1f}x "
                  f"({'발화' if triggered else '미발화'} > 3x)",
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

    # 1) 시총 top 1 판정 (전체 peer 중 본 종목이 1위)
    peer_caps = [_safe_float(r.get("market_cap")) or 0 for r in sector_peers]
    is_top = market_cap > max(peer_caps)

    # 2) 매출 가속 격차 — 본 종목 vs sector 평균
    peer_rev_growths = [_safe_float(r.get("revenue_growth")) for r in sector_peers]
    peer_rev_growths = [v for v in peer_rev_growths if v is not None]
    if not peer_rev_growths:
        return {"triggered": False, "score": 50,
                "reason": f"sector '{sector}' peer revenue_growth 데이터 0"}
    sector_avg_growth = sum(peer_rev_growths) / len(peer_rev_growths)
    growth_gap = rev_growth - sector_avg_growth
    is_widening = growth_gap > 5  # 5%p 격차 임계 (자체 설정)

    triggered = is_top and is_widening
    score = 50
    if is_top:
        score += 20
    if is_widening:
        score += 20
    return {
        "triggered": triggered, "score": int(score),
        "reason": (
            f"sector '{sector}': 시총 {'1위' if is_top else f'< {len(sector_peers)} peer 평균'} / "
            f"매출 격차 {growth_gap:+.1f}%p (sector 평균 {sector_avg_growth:+.1f}%) "
            f"{'카테고리 리더 발화' if triggered else '미발화'}"
        ),
        "is_top": is_top,
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
