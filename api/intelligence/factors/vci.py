"""VCI v2.0 — Verity Contrarian Index + Cohen 1987 역발상 체크리스트.

원본: api/intelligence/verity_brain.py:1517-1684 (분해 전).
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from api.intelligence.factors._common import _load_constitution


def _cohen_contrarian_checks(
    fact_score: float,
    stock: Dict[str, Any],
    portfolio: Dict[str, Any],
) -> Dict[str, Any]:
    """Steve Cohen 1987 역발상 체크리스트.
    패닉 구간에서 팩트가 좋은 종목의 역발상 매수 근거를 정량화한다."""
    macro = portfolio.get("macro", {})
    vix = macro.get("vix", {}).get("value", 0)
    mood = macro.get("market_mood", {}).get("score", 50)
    crypto = portfolio.get("crypto_macro", {})

    checks = []
    passed = 0

    # 1. 하락 원인: 수급(강제 청산) vs 펀더멘털 붕괴
    is_supply_driven = fact_score >= 60 and mood < 30
    checks.append({
        "name": "수급발 하락 (펀더멘털 아닌 강제 청산)",
        "passed": is_supply_driven,
    })
    if is_supply_driven:
        passed += 1

    # 2. VIX 역사적 극단
    vix_extreme = vix >= 40
    checks.append({
        "name": f"VIX 역사적 극단 ({vix})",
        "passed": vix_extreme,
    })
    if vix_extreme:
        passed += 1

    # 3. 크립토 디커플링 (BTC가 나스닥과 분리 움직임 = 독자적 헤지 신호)
    btc_corr = 0.5
    if crypto.get("available"):
        corr_data = crypto.get("btc_nasdaq_corr", {})
        if corr_data.get("ok"):
            btc_corr = corr_data.get("correlation", 0.5)
    crypto_decoupled = btc_corr < 0.3
    checks.append({
        "name": f"크립토 디커플링 (상관 {btc_corr:.2f})",
        "passed": crypto_decoupled,
    })
    if crypto_decoupled:
        passed += 1

    # 4. 기관 흡수(Absorption) 신호 — 외인+기관 순매수 + 가격 변동 안정
    flow = stock.get("flow", {})
    fg_net = flow.get("kis_foreign_net", 0)
    inst_net = flow.get("kis_institution_net", 0)
    # US: Finnhub 내부자 + 기관 보유 변화로 대체
    if stock.get("currency") == "USD":
        insider = stock.get("insider_sentiment") or {}
        inst_own = stock.get("institutional_ownership") or {}
        absorption = insider.get("mspr", 0) > 0 and inst_own.get("change_pct", 0) > 0
    else:
        absorption = fg_net > 0 and inst_net > 0
    checks.append({
        "name": "기관 흡수 신호 (순매수 + 가격 안정)",
        "passed": absorption,
    })
    if absorption:
        passed += 1

    const = _load_constitution()
    cohen_cfg = const.get("panic_stages", {}).get("cohen_checklist", {})
    bonus_per = cohen_cfg.get("bonus_per_check", 3)
    max_bonus = cohen_cfg.get("max_bonus", 12)

    bonus = min(passed * bonus_per, max_bonus)

    return {
        "checks": checks,
        "passed": passed,
        "total": len(checks),
        "bonus": bonus,
    }


def _compute_vci(
    fact: float,
    sentiment: float,
    stock: Optional[Dict[str, Any]] = None,
    portfolio: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """팩트와 심리의 괴리율 계산.
    V4: Cohen 역발상 체크리스트 보너스를 반영한 enhanced VCI."""
    base_vci = round(fact - sentiment)

    const = _load_constitution()
    th = const.get("vci", {}).get("thresholds", {})
    strong_buy = th.get("strong_contrarian_buy", 25)
    mild_buy = th.get("mild_contrarian_buy", 15)
    mild_sell = th.get("mild_contrarian_sell", -15)
    strong_sell = th.get("strong_contrarian_sell", -25)

    # V4: Cohen 체크리스트 적용 (팩트 좋은데 심리 비관일 때만)
    cohen = None
    cohen_bonus = 0
    if base_vci >= 20 and stock is not None and portfolio is not None:
        cohen = _cohen_contrarian_checks(fact, stock, portfolio)
        cohen_bonus = cohen["bonus"]

    # 버블 경계에서도 반대 방향 보정
    bubble_penalty = 0
    if base_vci <= -20 and stock is not None:
        # Soros 반사성: 심리만 좋고 팩트 나쁜 경우 추가 패널티
        funding_overheat = False
        if portfolio:
            crypto = portfolio.get("crypto_macro", {})
            if crypto.get("available"):
                fr = crypto.get("funding_rate", {})
                if fr.get("ok") and fr.get("rate_pct", 0) >= 0.05:
                    funding_overheat = True
        if funding_overheat:
            bubble_penalty = -5

    vci = base_vci + cohen_bonus + bubble_penalty

    if vci >= strong_buy:
        signal = "STRONG_CONTRARIAN_BUY"
        label = "팩트 좋은데 심리 과도 비관 → 역발상 매수"
    elif vci >= mild_buy:
        signal = "CONTRARIAN_BUY"
        label = "팩트 우위 — 시장이 아직 미반영"
    elif vci > mild_sell:
        signal = "ALIGNED"
        label = "팩트·심리 정렬 — 추세 추종 유효"
    elif vci > strong_sell:
        signal = "CONTRARIAN_SELL"
        label = "심리 과열 — 팩트 대비 고평가 주의"
    else:
        signal = "STRONG_CONTRARIAN_SELL"
        label = "심리만 좋고 팩트 나쁨 → 버블 경계"

    # ── Mispricing Score (fact-sentiment z-score gap, Baker-Wurgler 2006 정합) ──
    # 2026-05-16 Perplexity MED-A2 검증: 단순 |VCI| 절댓값 보다 z-score gap 기반이
    # 사이클 국면 노이즈 회피에 우월. base_vci = fact - sentiment 를 z-score 환산.
    # σ = 15 (정규 fact/sentiment 분포 표준편차 가정, ±1σ = 15p ≈ VCI ±15).
    # mispricing_score = base_vci / 15 (z-score, ±1.0=mild contrarian / ±2.0=strong)
    mispricing_z = round(base_vci / 15.0, 2)
    if mispricing_z >= 2.0:
        mispricing_signal = "extreme_undervalued"  # fact > sentiment 2σ — 강 매수
    elif mispricing_z >= 1.0:
        mispricing_signal = "mild_undervalued"
    elif mispricing_z <= -2.0:
        mispricing_signal = "extreme_overvalued"  # sentiment > fact 2σ — 강 매도
    elif mispricing_z <= -1.0:
        mispricing_signal = "mild_overvalued"
    else:
        mispricing_signal = "fair_value"

    result = {
        "vci": vci,
        "base_vci": base_vci,
        "signal": signal,
        "label": label,
        "mispricing_z": mispricing_z,
        "mispricing_signal": mispricing_signal,
    }
    if cohen is not None:
        result["cohen_checklist"] = cohen
    if bubble_penalty:
        result["bubble_penalty"] = bubble_penalty
    return result
