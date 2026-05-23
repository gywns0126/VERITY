"""Sentiment score — 13-source composite (Brain Signal Plan v0.2 Phase B).

원본: api/intelligence/verity_brain.py:1295-1514 (분해 전).
"""
from __future__ import annotations

import math
from typing import Any, Dict

from api.intelligence.factors._common import _clip, _load_constitution


def _compute_sentiment_score(
    stock: Dict[str, Any],
    portfolio: Dict[str, Any],
) -> Dict[str, Any]:
    """심리/감성 기반 종합 점수 (0~100)."""
    const = _load_constitution()
    w = (const.get("sentiment_score") or {}).get("weights") or {}

    sent = stock.get("sentiment", {})
    news_score = sent.get("score", 50)

    x_sent = portfolio.get("x_sentiment", {})
    x_score = x_sent.get("score", 50) if x_sent else 50

    macro = portfolio.get("macro", {})
    mood_score = macro.get("market_mood", {}).get("score", 50)

    cons = stock.get("consensus", {})
    opinion_num = cons.get("investment_opinion_numeric")
    if opinion_num is not None:
        try:
            cons_opinion_score = _clip(float(opinion_num) * 20)
        except (TypeError, ValueError):
            cons_opinion_score = 50.0
    else:
        # 2026-05-19 S4 fix — US 종목 fallback (equity_research_brief.recommendation_mean).
        # 진단: stock.consensus.investment_opinion_numeric 가 US 15/15 None (KIS 미작동) →
        # cons_opinion_score 50 평면 → sentiment_score US 변별력 손실.
        # equity_research_brief.analyst_consensus.recommendation_mean (1=Strong Buy ~
        # 5=Strong Sell, Yahoo/SEC 표준) 활용. KIS scale (5=Strong Buy~1=Sell) 와
        # 역방향 → 변환: kr_equivalent = 6 - rec_mean → score = equivalent * 20.
        # M1/C2/E1 와 동일 path mismatch 패턴.
        ac = (stock.get("equity_research_brief") or {}).get("analyst_consensus") or {}
        rm = ac.get("recommendation_mean")
        if isinstance(rm, (int, float)) and 0 < rm <= 5:
            cons_opinion_score = _clip((6.0 - float(rm)) * 20.0)
        else:
            cons_opinion_score = 50.0

    # 크립토 매크로 센서 반영 (보조 가중치)
    crypto = portfolio.get("crypto_macro", {})
    crypto_temp = 50.0
    if crypto.get("available"):
        comp = crypto.get("composite", {})
        crypto_temp = comp.get("score", 50)

    # CNN Fear & Greed (주식시장 심리)
    mfg = portfolio.get("market_fear_greed", {})
    mfg_score = 50.0
    if mfg.get("ok"):
        mfg_score = float(mfg.get("value", 50))

    social = stock.get("social_sentiment") or {}
    social_score = social.get("score", 50) if social else 50

    # ── 6 신규 sub-component (Brain Signal Plan v0.2 Phase B, 2026-05-16) ──
    # 32 미반영 시그널 통합. 각 sub 50 = 중립, > 50 = 위험회피·우호 / < 50 = 우려.

    # 1) fx_sentiment — USD/KRW change_pct → 점수 (큰 변동 = 외인 자금 신호 = 낮음)
    fx_chg = (macro.get("usd_krw") or {}).get("change_pct")
    if fx_chg is not None:
        try:
            fx_chg_f = float(fx_chg)
            # |chg| 0%→50, |1%|→35, |2%|→20 (역방향 penalty)
            fx_sentiment = max(0, 50 - abs(fx_chg_f) * 15)
        except (TypeError, ValueError):
            fx_sentiment = 50.0
    else:
        fx_sentiment = 50.0

    # 2) commodity_sentiment — WTI·gold·copper composite (역상관 가중)
    wti_chg = (macro.get("wti_oil") or {}).get("change_pct") or 0
    gold_chg = (macro.get("gold") or {}).get("change_pct") or 0
    copper_chg = (macro.get("copper") or {}).get("change_pct") or 0
    try:
        # 원유 상승 = 인플레 우려(낮음) / 금 상승 = 위험회피(낮음) / 구리 상승 = 경기 우호(높음)
        commodity_sentiment = _clip(
            50 - float(wti_chg) * 2 - float(gold_chg) * 3 + float(copper_chg) * 2
        )
    except (TypeError, ValueError):
        commodity_sentiment = 50.0

    # 3) global_index_decoupling — NASDAQ vs KOSPI gap (디커플링 큰 변화 = 낮음)
    nq_chg = (macro.get("nasdaq") or {}).get("change_pct") or 0
    kospi_chg = ((portfolio.get("market_summary") or {}).get("kospi") or {}).get("change_pct") or 0
    try:
        gap = float(nq_chg) - float(kospi_chg)
        # gap 0 = 동조화 (50점) / gap +3 (KR 단독 약세) = 30 / gap -3 = 70
        global_index_decoupling = _clip(50 - gap * 5)
    except (TypeError, ValueError):
        global_index_decoupling = 50.0

    # 4) geopolitical_score — geopolitical_hotspots severity 합산 (낮을수록 우호)
    geo = portfolio.get("geopolitical_hotspots") or {}
    geo_severity = 0
    if isinstance(geo, dict):
        for ev in (geo.get("events") or []):
            try:
                geo_severity += int(ev.get("severity") or 0)
            except (TypeError, ValueError):
                pass
    # severity 0=50, severity 5=35, severity 10+=20
    geopolitical_score = max(20, 50 - geo_severity * 3)

    # 5) macro_headlines — bloomberg/news headlines sentiment 평균
    macro_headlines = 50.0
    headlines = portfolio.get("bloomberg_google_headlines") or portfolio.get("headlines") or []
    if isinstance(headlines, list) and headlines:
        # 단순 카운트 기반 (negative keywords 감지)
        neg_words = ("recession", "crash", "panic", "war", "rate hike", "default", "bankrupt",
                     "위기", "폭락", "전쟁", "디폴트", "파산")
        pos_words = ("rally", "boom", "surge", "growth", "rate cut",
                     "상승", "호조", "낙관", "금리 인하")
        score = 50.0
        # 주의: 함수 scope 의 w (weights dict) 와 변수명 충돌 회피 — kw 사용
        for h in headlines[:20]:
            title = (h.get("title") or "").lower()
            for kw in neg_words:
                if kw in title:
                    score -= 2
            for kw in pos_words:
                if kw in title:
                    score += 2
        macro_headlines = _clip(score)

    # 6) market_horizon_link — V2.1 cycle_stage 매핑 (역설적 — euphoria 낮음, panic 높음 = 역발상)
    mh = portfolio.get("market_horizon") or {}
    cycle = mh.get("cycle_stage")
    horizon_map = {
        "panic": 85, "capitulation": 90, "early_correction": 70,
        "recovery": 60, "normal": 50, "expansion": 45,
        "late_cycle": 35, "euphoria": 25,
    }
    market_horizon_link = horizon_map.get(cycle, 50.0)

    components = {
        # 기존 7
        "news_sentiment": news_score,
        "x_sentiment": x_score,
        "market_mood": mood_score,
        "consensus_opinion": cons_opinion_score,
        "crypto_macro": crypto_temp,
        "market_fear_greed": mfg_score,
        "social_sentiment": social_score,
        # 신규 6 (Brain Signal Plan v0.2 Phase B)
        "fx_sentiment": fx_sentiment,
        "commodity_sentiment": commodity_sentiment,
        "global_index_decoupling": global_index_decoupling,
        "geopolitical_score": geopolitical_score,
        "macro_headlines": macro_headlines,
        "market_horizon_link": market_horizon_link,
    }

    # 가중치 합 = 1.000 hard-wire (post-hoc normalize 폐기, audit 가능성).
    # 2026-05-16 Phase B 13 component 권장값 (Perplexity 자문 기반):
    #   - MSCI Multi-Factor / Bloomberg Intelligence prior normalization 모범.
    #   - 기존 7-source 합 0.93 (1.0 미만) 결함 정정 + 신규 6 source 편입.
    #   - retail (x + social) 21% → RETAIL_CAP_BASE 22% 미만 (정상 운영 dead),
    #     meme trigger 시만 RETAIL_CAP_MEME 18% 동적 강화 (Phase 2 TODO).
    #   - geopolitical 0.060 가장 큰 신규 비중 (한국 시장 지정학 민감도).
    _default_w = {
        # 기존 7 (재분배 — 합 0.740)
        "news_sentiment": 0.175, "x_sentiment": 0.125, "market_mood": 0.125,
        "consensus_opinion": 0.100, "crypto_macro": 0.065,
        "market_fear_greed": 0.065, "social_sentiment": 0.085,
        # 신규 6 (합 0.260)
        "fx_sentiment": 0.050, "commodity_sentiment": 0.040,
        "global_index_decoupling": 0.040, "geopolitical_score": 0.060,
        "macro_headlines": 0.050, "market_horizon_link": 0.020,
    }
    # sum = 1.000 ✓ (hard-wire, audit 가능)
    active_w = {}
    w_sum = 0.0
    for key in components:
        weight = w.get(key, _default_w.get(key, 0))
        active_w[key] = weight
        w_sum += weight

    # ── Brain Audit §12 (production 오심 #1, 삼성전자 2026-04-13): ──
    # consensus_opinion ≥ 95 (만점 직전 과열) → 호재 소진 패턴 → 가중치 ×0.7 dampen.
    # 외국인 매도 반전 시점 자주 출현 — 컨센서스 100점 자체가 contrarian 신호.
    if components.get("consensus_opinion", 50) >= 95:
        original_w = active_w.get("consensus_opinion", 0)
        active_w["consensus_opinion"] = original_w * 0.7
        w_sum = w_sum - original_w + active_w["consensus_opinion"]

    total = 0.0
    if w_sum > 0:
        norm = 1.0 / w_sum
        for key, val in components.items():
            total += val * active_w.get(key, 0) * norm

    # ── Retail sentiment 그룹 cap (Brain Audit §1-C, 2026-05-16 Perplexity 자문 후 변경) ──
    # x_sentiment + social_sentiment 합산 기여가 RETAIL_CAP 초과 시 제한.
    # 13-source 권장 weight (x 0.125 + social 0.085 = 0.21) 에서 정상 운영 시 cap 22% 미발동.
    # meme trigger (x>0.7 AND social>0.7 AND volume_spike>2σ) 시 RETAIL_CAP_MEME 18% 동적 강화 — Phase 2 TODO.
    RETAIL_GROUP_KEYS = ("x_sentiment", "social_sentiment")
    RETAIL_CAP = 0.22  # 13-source 체제 base. 정상 운영 dead (x+social 합 21%). meme 강화 후속.
    retail_excess = 0.0
    if w_sum > 0:
        norm = 1.0 / w_sum
        retail_raw_score = sum(
            components.get(k, 50) * active_w.get(k, 0) * norm
            for k in RETAIL_GROUP_KEYS
        )
        retail_cap_score = RETAIL_CAP * 100  # = 20 점
        if retail_raw_score > retail_cap_score:
            retail_excess = retail_raw_score - retail_cap_score
            total -= retail_excess

    if not isinstance(total, (int, float)) or math.isnan(total) or math.isinf(total):
        total = 0.0

    return {
        "score": round(_clip(total)),
        "components": {k: round(v, 2) if isinstance(v, (int, float)) else v
                       for k, v in components.items()},
        "retail_cap_applied": retail_excess > 0,
        "retail_excess_score": round(retail_excess, 2),
    }
