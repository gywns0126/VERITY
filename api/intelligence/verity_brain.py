"""
Verity Brain v1.0 — 배리티 터미널의 종합 판단 엔진

모든 개별 분석 결과(멀티팩터, 컨센서스, 예측, 백테스트, 타이밍,
원자재, 수출입, 뉴스, X감성, 매크로)를 종합하여 최종 판단을 내린다.

핵심 구조:
  Fact Score (객관적 수치)  × 0.7
+ Sentiment Score (심리)   × 0.3
+ VCI Bonus (괴리율 보정)
= Brain Score → 최종 등급

모든 가중치와 임계값은 verity_constitution.json에서 로드.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from api.config import DATA_DIR, MACRO_DGS10_DEFENSE_PCT

_CONSTITUTION_PATH = os.path.join(DATA_DIR, "verity_constitution.json")
_constitution_cache: Optional[Dict[str, Any]] = None


def _load_constitution() -> Dict[str, Any]:
    global _constitution_cache
    if _constitution_cache is not None:
        return _constitution_cache
    try:
        with open(_CONSTITUTION_PATH, "r", encoding="utf-8") as f:
            _constitution_cache = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        _constitution_cache = {}
    return _constitution_cache


def _clip(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


# ─── Fact Score ──────────────────────────────────────────────

def _compute_fact_score(stock: Dict[str, Any]) -> Dict[str, Any]:
    """객관적 수치 기반 종합 점수 (0~100)."""
    const = _load_constitution()
    w = const.get("fact_score", {}).get("weights", {})

    mf = stock.get("multi_factor", {})
    multi_factor_score = mf.get("multi_score", 50)

    consensus = stock.get("consensus", {})
    consensus_score = consensus.get("consensus_score", 50)

    pred = stock.get("prediction", {})
    prediction_score = _clip(pred.get("up_probability", 50))

    bt = stock.get("backtest", {})
    backtest_score = _backtest_to_score(bt)

    timing = stock.get("timing", {})
    timing_score = timing.get("timing_score", 50)

    cm = stock.get("commodity_margin", {})
    commodity_score = _commodity_to_score(cm)

    export_score = _export_to_score(stock)

    components = {
        "multi_factor": multi_factor_score,
        "consensus": consensus_score,
        "prediction": prediction_score,
        "backtest": backtest_score,
        "timing": timing_score,
        "commodity_margin": commodity_score,
        "export_trade": export_score,
    }

    total = 0.0
    for key, val in components.items():
        total += val * w.get(key, 0)

    return {
        "score": round(_clip(total)),
        "components": {k: round(v, 1) for k, v in components.items()},
    }


def _backtest_to_score(bt: Dict[str, Any]) -> float:
    """백테스트 결과 → 0~100 점수."""
    if not bt or bt.get("total_trades", 0) == 0:
        return 50.0
    wr = bt.get("win_rate", 50)
    sharpe = bt.get("sharpe_ratio", 0)
    score = wr * 0.6 + _clip(sharpe * 20 + 50) * 0.4
    return _clip(score)


def _commodity_to_score(cm: Dict[str, Any]) -> float:
    """원자재 마진 안심 점수 → 0~100 정규화."""
    pr = cm.get("primary") or cm
    ms = pr.get("margin_safety_score")
    if ms is None:
        return 50.0
    return _clip(float(ms))


def _export_to_score(stock: Dict[str, Any]) -> float:
    """수출입 데이터 기반 점수. 없으면 중립(50)."""
    cons = stock.get("consensus", {})
    warnings = cons.get("warnings", [])
    has_divergence = any("기관 낙관 주의" in w for w in warnings)

    vc = stock.get("value_chain") or {}
    has_vc_bonus = vc.get("active", False)

    score = 50.0
    if has_vc_bonus:
        score += int(vc.get("score_bonus", 0))
    if has_divergence:
        score -= 15
    return _clip(score)


# ─── Sentiment Score ─────────────────────────────────────────

def _compute_sentiment_score(
    stock: Dict[str, Any],
    portfolio: Dict[str, Any],
) -> Dict[str, Any]:
    """심리/감성 기반 종합 점수 (0~100)."""
    const = _load_constitution()
    w = const.get("sentiment_score", {}).get("weights", {})

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
        cons_opinion_score = 50.0

    components = {
        "news_sentiment": news_score,
        "x_sentiment": x_score,
        "market_mood": mood_score,
        "consensus_opinion": cons_opinion_score,
    }

    total = 0.0
    for key, val in components.items():
        total += val * w.get(key, 0)

    return {
        "score": round(_clip(total)),
        "components": {k: round(v, 1) for k, v in components.items()},
    }


# ─── VCI (Verity Contrarian Index) ──────────────────────────

def _compute_vci(fact: float, sentiment: float) -> Dict[str, Any]:
    """팩트와 심리의 괴리율 계산."""
    vci = round(fact - sentiment)

    const = _load_constitution()
    th = const.get("vci", {}).get("thresholds", {})
    strong_buy = th.get("strong_contrarian_buy", 25)
    mild_buy = th.get("mild_contrarian_buy", 15)
    mild_sell = th.get("mild_contrarian_sell", -15)
    strong_sell = th.get("strong_contrarian_sell", -25)

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

    return {
        "vci": vci,
        "signal": signal,
        "label": label,
    }


# ─── Red Flag Detection ─────────────────────────────────────

def _detect_red_flags(
    stock: Dict[str, Any],
    portfolio: Dict[str, Any],
) -> Dict[str, Any]:
    """레드플래그 자동 감지. auto_avoid / downgrade_one 분류."""
    auto_avoid = []
    downgrade = []

    risk_kw = stock.get("detected_risk_keywords") or []
    if risk_kw:
        auto_avoid.append(f"위험 키워드 감지: {', '.join(risk_kw)}")

    dart = stock.get("dart_financials", {})
    cf = dart.get("cashflow", {})
    fcf = cf.get("free_cashflow")
    debt = stock.get("debt_ratio", 0)
    if fcf is not None and fcf < 0 and debt > 80:
        auto_avoid.append(f"FCF 마이너스({fcf/1e8:,.0f}억) + 부채 {debt:.0f}%")
    elif fcf is not None and fcf < 0:
        downgrade.append(f"FCF 마이너스({fcf/1e8:,.0f}억)")

    macro = portfolio.get("macro", {})
    vix = macro.get("vix", {}).get("value", 0)
    mf_score = stock.get("multi_factor", {}).get("multi_score", 50)
    if vix > 35 and mf_score < 50:
        auto_avoid.append(f"VIX {vix} + 멀티팩터 {mf_score}")

    cons_warnings = stock.get("consensus", {}).get("warnings", [])
    if any("기관 낙관 주의" in w for w in cons_warnings):
        downgrade.append("컨센서스↑ vs 수출↓ 괴리")

    cm = stock.get("commodity_margin", {})
    pr = cm.get("primary") or cm
    ms = pr.get("margin_safety_score")
    if ms is not None and float(ms) < 30:
        cm_ticker = pr.get("commodity_ticker", "원자재")
        pct = pr.get("commodity_20d_pct", "?")
        downgrade.append(f"{cm_ticker} 급변({pct}%) + 마진안심 {ms}")

    timing = stock.get("timing", {})
    ts = timing.get("timing_score", 50)
    if ts <= 25:
        downgrade.append(f"타이밍 스코어 {ts} — 진입 부적합")

    earnings = stock.get("earnings", {})
    next_e = earnings.get("next_earnings")
    if next_e:
        from datetime import datetime
        try:
            d = datetime.strptime(next_e[:10], "%Y-%m-%d")
            days = (d - datetime.now()).days
            if 0 <= days <= 1:
                downgrade.append(f"실적 발표 D-{days}")
        except (ValueError, TypeError):
            pass

    return {
        "auto_avoid": auto_avoid,
        "downgrade": downgrade,
        "has_critical": len(auto_avoid) > 0,
        "downgrade_count": len(downgrade),
    }


# ─── Macro Override ──────────────────────────────────────────

def detect_macro_override(portfolio: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """매크로 환경이 극단적일 때 포트폴리오 레벨 오버라이드."""
    macro = portfolio.get("macro", {})
    vix = macro.get("vix", {}).get("value", 0)
    spread = macro.get("yield_spread", {}).get("value", 1)
    sp_chg = macro.get("sp500", {}).get("change_pct", 0)
    mood = macro.get("market_mood", {}).get("score", 50)

    y10: Optional[float] = None
    fred = macro.get("fred") or {}
    if fred.get("dgs10", {}).get("value") is not None:
        y10 = float(fred["dgs10"]["value"])
    else:
        u10 = macro.get("us_10y", {}).get("value", 0)
        if u10:
            y10 = float(u10)

    if vix > 35 or (spread is not None and spread < 0 and sp_chg < -3):
        msg = f"VIX {vix} / 스프레드 {spread}%p / S&P {sp_chg:+.1f}% — 신규 매수 금지, 현금 확보"
        return {
            "mode": "panic",
            "label": "패닉 모드",
            "message": msg,
            "reason": msg,
            "max_grade": "WATCH",
        }

    if y10 is not None and y10 >= MACRO_DGS10_DEFENSE_PCT:
        msg = (
            f"미 10년 국채 {y10:.2f}% (≥{MACRO_DGS10_DEFENSE_PCT}%) — "
            "할인율·밸류에이션 압력, 현금 비중 확대 권고"
        )
        return {
            "mode": "yield_defense",
            "label": "금리 방패",
            "message": msg,
            "reason": msg,
            "max_grade": "WATCH",
        }

    if vix < 12 and mood > 80:
        msg = f"VIX {vix} / 분위기 {mood}점 — 과열 경고, 차익 실현 고려"
        return {
            "mode": "euphoria",
            "label": "과열 모드",
            "message": msg,
            "reason": msg,
            "max_grade": "BUY",
        }

    return None


# ─── Brain Score & Final Judgment ────────────────────────────

GRADE_ORDER = ["STRONG_BUY", "BUY", "WATCH", "CAUTION", "AVOID"]
GRADE_LABELS = {
    "STRONG_BUY": "강력 매수",
    "BUY": "매수",
    "WATCH": "관망",
    "CAUTION": "주의",
    "AVOID": "회피",
}


def _score_to_grade(score: float) -> str:
    const = _load_constitution()
    grades = const.get("decision_tree", {}).get("grades", {})
    for g in GRADE_ORDER:
        info = grades.get(g, {})
        if score >= info.get("min_brain_score", 999):
            return g
    return "AVOID"


def _downgrade(grade: str, steps: int = 1) -> str:
    idx = GRADE_ORDER.index(grade) if grade in GRADE_ORDER else len(GRADE_ORDER) - 1
    new_idx = min(idx + steps, len(GRADE_ORDER) - 1)
    return GRADE_ORDER[new_idx]


def _cap_grade(grade: str, max_grade: str) -> str:
    """등급을 max_grade 이하로 제한."""
    g_idx = GRADE_ORDER.index(grade) if grade in GRADE_ORDER else len(GRADE_ORDER) - 1
    m_idx = GRADE_ORDER.index(max_grade) if max_grade in GRADE_ORDER else 0
    return GRADE_ORDER[max(g_idx, m_idx)]


def analyze_stock(
    stock: Dict[str, Any],
    portfolio: Dict[str, Any],
    macro_override: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    단일 종목에 대한 Verity Brain 종합 판단.

    Returns:
        brain_score, fact_score, sentiment_score, vci, grade,
        red_flags, reasoning 등을 포함한 dict.
    """
    fact = _compute_fact_score(stock)
    sentiment = _compute_sentiment_score(stock, portfolio)
    vci = _compute_vci(fact["score"], sentiment["score"])
    red_flags = _detect_red_flags(stock, portfolio)

    fs = fact["score"]
    ss = sentiment["score"]
    vci_val = vci["vci"]

    vci_bonus = 0
    if vci_val > 25 and fs >= 60:
        vci_bonus = 5
    elif vci_val < -25 and fs < 50:
        vci_bonus = -10

    brain_score = round(_clip(fs * 0.7 + ss * 0.3 + vci_bonus))
    grade = _score_to_grade(brain_score)

    if red_flags["has_critical"]:
        grade = "AVOID"
    elif red_flags["downgrade_count"] > 0:
        grade = _downgrade(grade, min(red_flags["downgrade_count"], 2))

    if macro_override:
        max_g = macro_override.get("max_grade", "WATCH")
        grade = _cap_grade(grade, max_g)

    reasoning = _build_reasoning(
        stock, fact, sentiment, vci, red_flags, brain_score, grade, macro_override
    )

    return {
        "brain_score": brain_score,
        "grade": grade,
        "grade_label": GRADE_LABELS.get(grade, grade),
        "fact_score": fact,
        "sentiment_score": sentiment,
        "vci": vci,
        "vci_bonus": vci_bonus,
        "red_flags": red_flags,
        "reasoning": reasoning,
        "macro_override": macro_override.get("mode") if macro_override else None,
    }


def _build_reasoning(
    stock: Dict[str, Any],
    fact: Dict[str, Any],
    sentiment: Dict[str, Any],
    vci: Dict[str, Any],
    red_flags: Dict[str, Any],
    brain_score: int,
    grade: str,
    macro_override: Optional[Dict[str, Any]],
) -> str:
    """사람이 읽을 수 있는 판단 근거 1~3줄 생성."""
    name = stock.get("name", "?")
    parts = []

    parts.append(
        f"{name}: 브레인 {brain_score}점 "
        f"(팩트 {fact['score']} / 심리 {sentiment['score']} / "
        f"VCI {vci['vci']:+d})"
    )

    fc = fact["components"]
    top_fact = max(fc, key=fc.get)
    bottom_fact = min(fc, key=fc.get)
    parts.append(
        f"팩트 최강 {top_fact}({fc[top_fact]:.0f}) "
        f"/ 최약 {bottom_fact}({fc[bottom_fact]:.0f})"
    )

    if vci["signal"] != "ALIGNED":
        parts.append(f"VCI: {vci['label']}")

    if red_flags["auto_avoid"]:
        parts.append(f"레드플래그(즉시회피): {'; '.join(red_flags['auto_avoid'])}")
    elif red_flags["downgrade"]:
        parts.append(f"하향조정: {'; '.join(red_flags['downgrade'])}")

    if macro_override:
        parts.append(f"매크로 {macro_override.get('label', '?')}: {macro_override.get('message', '')}")

    return " | ".join(parts)


# ─── Batch Analysis ──────────────────────────────────────────

def analyze_all(
    candidates: List[Dict[str, Any]],
    portfolio: Dict[str, Any],
) -> Dict[str, Any]:
    """
    전체 후보 종목 + 포트폴리오에 대한 Verity Brain 일괄 분석.

    Returns:
        {
            "macro_override": {...} or None,
            "market_brain": {...},
            "stocks": [ {...brain result per stock...} ],
        }
    """
    macro_ov = detect_macro_override(portfolio)

    stock_results = []
    for stock in candidates:
        result = analyze_stock(stock, portfolio, macro_ov)
        stock_results.append({
            "ticker": stock.get("ticker"),
            "name": stock.get("name"),
            **result,
        })

    stock_results.sort(key=lambda x: x["brain_score"], reverse=True)

    scores = [r["brain_score"] for r in stock_results]
    facts = [r["fact_score"]["score"] for r in stock_results]
    sents = [r["sentiment_score"]["score"] for r in stock_results]

    avg = lambda xs: round(sum(xs) / len(xs)) if xs else 0
    market_brain = {
        "avg_brain_score": avg(scores),
        "avg_fact_score": avg(facts),
        "avg_sentiment_score": avg(sents),
        "avg_vci": avg(facts) - avg(sents),
        "grade_distribution": _count_grades(stock_results),
        "top_picks": [
            {"ticker": r["ticker"], "name": r["name"], "score": r["brain_score"], "grade": r["grade"]}
            for r in stock_results if r["grade"] in ("STRONG_BUY", "BUY")
        ][:5],
        "red_flag_stocks": [
            {"ticker": r["ticker"], "name": r["name"], "flags": r["red_flags"]["auto_avoid"] + r["red_flags"]["downgrade"]}
            for r in stock_results if r["red_flags"]["has_critical"] or r["red_flags"]["downgrade_count"] >= 2
        ],
    }

    return {
        "macro_override": macro_ov,
        "market_brain": market_brain,
        "stocks": stock_results,
    }


def _count_grades(results: List[Dict[str, Any]]) -> Dict[str, int]:
    dist = {g: 0 for g in GRADE_ORDER}
    for r in results:
        g = r.get("grade", "AVOID")
        dist[g] = dist.get(g, 0) + 1
    return dist
