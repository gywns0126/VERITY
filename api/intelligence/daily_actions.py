"""Sprint 11 결함 7 (베테랑 due diligence) — '오늘의 액션 3개' 단일 카드 backend.

베테랑 평가 핵심:
  "49개 Framer 컴포넌트 — 정보는 풍부한데 사용자가 다음에 뭘 해야 하는지 분산.
   StockDashboard, BrainPanel, AlertDashboard, VAMSPanel 이 병렬 정보 제공이라
   사용자가 매번 종합해야 한다. 이건 decision fatigue 를 유발하고, 결국 시스템을
   안 쓰게 되는 가장 큰 이유야."

월가 PM 데일리 워크플로우:
  아침: "오늘의 액션 3개 (매수 1, 매도 1, 관찰 1)" — 첫 화면
  장중: "변경된 시그널만"
  마감: "오늘 의사결정 vs Brain 추천 정합성"

이 모듈: portfolio 에서 BUY 1 / SELL 1 / WATCH 1 단순 추출. Framer 가
`portfolio.daily_actions` 를 fetch 해서 단일 카드 렌더링.

가드:
  - 모든 진입점 try/except + 빈 결과 fallback
  - 외부 호출 없음 — portfolio 데이터만 사용
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _grade_of(rec: Dict[str, Any]) -> Optional[str]:
    """recommendations[i].verity_brain.grade (실제 위치). top-level grade 는 None 흔함."""
    vb = rec.get("verity_brain") if isinstance(rec, dict) else None
    if isinstance(vb, dict):
        return vb.get("grade")
    return rec.get("grade") if isinstance(rec, dict) else None


def _brain_score_of(rec: Dict[str, Any]) -> float:
    """verity_brain.brain_score 우선, top-level fallback."""
    if not isinstance(rec, dict):
        return 0.0
    vb = rec.get("verity_brain") or {}
    score = vb.get("brain_score")
    if isinstance(score, (int, float)):
        return float(score)
    score = rec.get("brain_score")
    return float(score) if isinstance(score, (int, float)) else 0.0


def _format_action(rec: Dict[str, Any], action_type: str) -> Dict[str, Any]:
    """Framer 카드용 슬림 dict — 필수 필드만."""
    vb = rec.get("verity_brain") or {}
    return {
        "action": action_type,
        "ticker": rec.get("ticker"),
        "name": rec.get("name") or rec.get("ticker"),
        "price": rec.get("price") or rec.get("current_price"),
        "grade": _grade_of(rec),
        "brain_score": _brain_score_of(rec),
        "verdict": rec.get("ai_verdict") or rec.get("recommendation"),
        "reason": vb.get("rationale") or rec.get("recommendation_reason") or "",
        "sector": rec.get("sector"),
        "currency": rec.get("currency", "KRW"),
    }


def _format_holding_action(holding: Dict[str, Any], action_type: str,
                          reason: str = "") -> Dict[str, Any]:
    """보유 종목용 — sell action 시 사용."""
    return {
        "action": action_type,
        "ticker": holding.get("ticker"),
        "name": holding.get("name") or holding.get("ticker"),
        "buy_price": holding.get("buy_price"),
        "current_price": holding.get("current_price"),
        "return_pct": holding.get("return_pct"),
        "quantity": holding.get("quantity"),
        "buy_date": holding.get("buy_date"),
        "reason": reason,
        "currency": holding.get("currency", "KRW"),
    }


def compute_daily_actions(portfolio: Dict[str, Any]) -> Dict[str, Any]:
    """오늘의 액션 3개 (BUY/SELL/WATCH) 산출.

    선정 룰:
      - BUY: STRONG_BUY/BUY 등급 + 보유 중 아닌 종목 중 brain_score 최고
      - SELL: 보유 중 종목 중 return_pct 최저 (손절 임박 우선) — 단, 임박 X 이면
              유보. -3% 이내는 hold 유지.
      - WATCH: brain_score 55-69 (BUY 직전 영역) + 보유 중 아닌 종목 중 최고

    각 영역에 후보 없으면 None — Framer 가 "이번 cron 액션 없음" 표시.
    """
    if not isinstance(portfolio, dict):
        return {"buy": None, "sell": None, "watch": None,
                "_meta": {"error": "no_portfolio"}}

    try:
        recs = portfolio.get("recommendations") or []
        holdings = (portfolio.get("vams") or {}).get("holdings") or []
        held_tickers = {h.get("ticker") for h in holdings if h.get("ticker")}

        # ── BUY: brain_score 최고 STRONG_BUY/BUY (보유 중 X) ──
        buy_candidates = [
            r for r in recs
            if _grade_of(r) in ("STRONG_BUY", "BUY")
            and r.get("ticker") not in held_tickers
        ]
        buy_candidates.sort(key=_brain_score_of, reverse=True)
        top_buy = _format_action(buy_candidates[0], "buy") if buy_candidates else None

        # ── SELL: 보유 중 손절 임박 (return_pct 최저, 단 임박 한정) ──
        # -3% 미만은 정상 노이즈로 간주, hold 유지
        SELL_THRESHOLD = -3.0
        if holdings:
            sell_sorted = sorted(holdings, key=lambda h: h.get("return_pct", 0))
            worst = sell_sorted[0]
            worst_ret = worst.get("return_pct", 0)
            if isinstance(worst_ret, (int, float)) and worst_ret < SELL_THRESHOLD:
                top_sell = _format_holding_action(
                    worst, "sell",
                    reason=f"손실 {worst_ret:.1f}% (임계 {SELL_THRESHOLD}%)"
                )
            else:
                top_sell = None
        else:
            top_sell = None

        # ── WATCH: brain_score 55-69 + 보유 중 X ──
        watch_candidates = [
            r for r in recs
            if 55 <= _brain_score_of(r) <= 69
            and r.get("ticker") not in held_tickers
            and _grade_of(r) not in ("STRONG_BUY", "BUY")  # 그건 BUY 영역
        ]
        watch_candidates.sort(key=_brain_score_of, reverse=True)
        top_watch = _format_action(watch_candidates[0], "watch") if watch_candidates else None

        return {
            "buy": top_buy,
            "sell": top_sell,
            "watch": top_watch,
            "_meta": {
                "buy_candidates_count": len(buy_candidates),
                "watch_candidates_count": len(watch_candidates),
                "sell_threshold_pct": SELL_THRESHOLD,
                "holdings_count": len(holdings),
            },
        }
    except Exception as e:  # noqa: BLE001 — 가드 정책
        logger.warning("daily_actions: failed: %s", e, exc_info=True)
        return {"buy": None, "sell": None, "watch": None,
                "_meta": {"error": str(e)[:200]}}


def attach_to_portfolio(portfolio: Dict[str, Any]) -> Dict[str, Any]:
    """portfolio 에 daily_actions 부착. main.py 호출 진입점."""
    actions = compute_daily_actions(portfolio)
    portfolio["daily_actions"] = actions
    return portfolio
