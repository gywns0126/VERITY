"""분기 재분배 — 드리프트 하이브리드 (갭2).

사전등록 = docs/PREREG_TRADING_BANDS_REBALANCE_2026_08_02.md Part B (private repo).
PM 승인 2026-08-02. 순수 캘린더 재분배 금지(1926~ 60/40: 분기/월=연간 대비 무개선, 비용만↑) —
분기 "점검" + tier 드리프트 밴드 초과 종목만 + Leland(2000) 부분 재분배(목표가 아니라 밴드
가장자리까지 = 비용 ~50%↓) + 비용 인지 게이트.

입력 = 목표비중(중용 3층 산출 — 빌더 #4 랜딩 전엔 페이퍼/수동 입력). 출력 = 표시값 액션 리스트
(자동 매매 없음 — trade_plan v0 철학). brain_score 미투입(중용 사전등록 정합: 자기참조 차단).

비용 상수(사실): 2026 증권거래세 매도 0.20%(코스피=거래세0.05+농특세0.15 / 코스닥 0.20).
이득-모델 기반 게이트는 v2(사전등록 추가 후) — v1 게이트 = tier 최소거래액 + 비용 명시 노출.
"""
from __future__ import annotations

from typing import Any, Dict, List

from api.portfolio.band_scaler import band_profile

SELL_TAX = 0.0020        # 매도 시 증권거래세 (2026 코스피·코스닥 공통 0.20%)
COMMISSION = 0.00015     # 위탁수수료 근사(편도)


def quarterly_rebalance(
    holdings: Dict[str, float],
    targets: Dict[str, float],
    total_value_krw: float,
) -> Dict[str, Any]:
    """분기 점검 1회 호출 — 드리프트 밴드 초과 종목만 부분 재분배 액션 산출.

    Args:
        holdings: {ticker: 현재 비중(0~1)}
        targets:  {ticker: 목표 비중(0~1)} — 중용 3층 산출
        total_value_krw: 포트 총액(KRW) — tier/최소거래액 결정

    Returns:
        {actions:[{ticker,side,amount_krw,cost_krw,gated,from_w,to_w,target_w,rel_drift}],
         review:[targets 에 없는 보유 — 자동 산출 없이 검토 표기],
         profile: tier 프로파일, skipped_in_band: n}
    """
    prof = band_profile(total_value_krw)
    band = float(prof["drift_band_rel_pct"]) / 100.0
    min_trade = float(prof["min_trade_krw"])
    total = max(float(total_value_krw), 0.0)

    actions: List[Dict[str, Any]] = []
    in_band = 0
    for tk, w_target in targets.items():
        w_t = float(w_target or 0)
        if w_t <= 0:
            continue
        w_c = float(holdings.get(tk, 0.0) or 0.0)
        rel = (w_c - w_t) / w_t
        if abs(rel) <= band:
            in_band += 1
            continue
        # Leland 부분 재분배 — 목표가 아니라 "밴드 가장자리"까지만
        edge = w_t * (1.0 + band) if rel > 0 else w_t * (1.0 - band)
        amount = abs(w_c - edge) * total
        side = "sell" if rel > 0 else "buy"
        cost = amount * ((SELL_TAX + COMMISSION) if side == "sell" else COMMISSION)
        actions.append({
            "ticker": tk,
            "side": side,
            "amount_krw": round(amount),
            "cost_krw": round(cost),
            "gated": amount < min_trade,          # tier 최소거래액 미달 = 실행 보류 표기
            "from_w": round(w_c, 4),
            "to_w": round(edge, 4),               # 밴드 edge (목표 복귀 아님)
            "target_w": round(w_t, 4),
            "rel_drift": round(rel, 4),
        })

    review = sorted(tk for tk, w in holdings.items() if float(w or 0) > 0 and tk not in targets)
    actions.sort(key=lambda a: -a["amount_krw"])
    return {
        "actions": actions,
        "review": review,               # 목표비중 없는 보유 = 수동 검토(자동 청산 산출 금지)
        "profile": prof,
        "skipped_in_band": in_band,
        "note": "표시값 — 자동 매매 아님 · Leland 부분(edge) · 비용 명시 · 이득모델 게이트=v2 사전등록 후",
    }
