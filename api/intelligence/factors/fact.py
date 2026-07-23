"""Fact score — V5 Graham + CANSLIM + Moat + V6 IC/ICIR 자동 조정.

원본: api/intelligence/verity_brain.py:724~1290 (분해 전).
  - _PANIC_OVERRIDE_MODES / _is_regime_panic
  - _PM_MAX_PENALTY / _PM_HALFLIFE_DAYS / _compute_postmortem_penalty
  - _IC_TO_WEIGHT_KEY / _IC_SUBFACTORS
  - _compute_fact_score (main)
  - _compute_kis_fact_bonus / _backtest_to_score / _commodity_to_score / _export_to_score
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from api.intelligence.factors._common import (
    _clip,
    _load_constitution,
    _load_ic_adjustments,
    _safe_float,
)
from api.intelligence.factors.canslim import _compute_canslim_score
from api.intelligence.factors.graham import _compute_graham_score
from api.intelligence.factors.mean_reversion import (
    _compute_kr_fundamental_mean_reversion_score,
    _compute_technical_mean_reversion_score,
)
from api.intelligence.factors.moat import _compute_moat_score


# ─── Regime panic gate (mean-reversion bonus 차단) ───────────

_PANIC_OVERRIDE_MODES = frozenset({
    "panic_stage_1", "panic_stage_2", "panic_stage_3", "panic_stage_4",
    "vix_spread_panic", "cape_bubble", "yield_defense", "vi_cascade",
    "fund_flow_cash_flight", "perplexity_critical", "us_recession",
})


def _is_regime_panic(portfolio: Optional[Dict[str, Any]],
                     macro_override: Optional[Dict[str, Any]]) -> bool:
    """위기장 게이트 — VIX > 30 또는 macro_override 가 panic/cape_bubble 류.

    True 시 mean-reversion bonus 비활성화 (가격 하락이 mean-reversion 점수를
    올려 거시 신호와 충돌하는 것 방지).
    """
    if macro_override:
        mode = macro_override.get("mode") or ""
        if mode in _PANIC_OVERRIDE_MODES:
            return True
    if portfolio:
        try:
            vix = float((portfolio.get("macro") or {}).get("vix", {}).get("value", 0) or 0)
            if vix > 30:
                return True
        except (TypeError, ValueError):
            pass
    return False


# ─── §26 Postmortem time-decay penalty ───────────────────────

_PM_MAX_PENALTY = 2.0           # 최대 감점 (0일 = -2.0)
_PM_HALFLIFE_DAYS = 30.0        # 반감기 — 30일 지나면 절반, 60일 1/4


def _compute_postmortem_penalty(
    stock: Dict[str, Any],
    portfolio: Optional[Dict[str, Any]],
) -> tuple:
    """종목 ticker 가 최근 postmortem.failures 에 있으면 time-decay soft penalty.

    portfolio["postmortem"]["windows"] 의 7d/14d/30d 에서 매칭된 ticker 중
    가장 최신 (days 작은) window 의 경과일로 지수 감쇠 적용.
    halflife=30일 → penalty = -2.0 * 0.5 ** (days/30).

    Returns:
        (penalty: float<=0, memo: dict or None)
    """
    if not portfolio:
        return 0.0, None
    ticker = stock.get("ticker")
    if not ticker:
        return 0.0, None
    pm = portfolio.get("postmortem") or {}
    windows = pm.get("windows") or {}
    # 구 포맷 폴백: windows 없으면 top-level failures 를 30d 로 취급
    if not windows and pm.get("failures"):
        windows = {"30d": {"failures": pm["failures"]}}
    if not windows:
        return 0.0, None

    # window key → days 정수 (가장 최신부터 탐색)
    parsed = []
    for k, v in windows.items():
        try:
            d = int(str(k).rstrip("d"))
            parsed.append((d, v))
        except (ValueError, TypeError):
            continue
    parsed.sort(key=lambda x: x[0])  # 가장 최근 (7d) 먼저

    for days, w in parsed:
        for f in (w.get("failures") or []):
            if f.get("ticker") == ticker:
                # 버그픽스: failure type 별 penalty 분기
                #   false_buy         = BUY 했는데 하락 → 실제 과대평가 → penalty
                #   missed_opportunity = AVOID 했는데 상승 → 오히려 과소평가 → penalty 주면 역효과.
                #     이 경우 penalty 0 (중립) + memo 만 부착 (UI 경고용).
                ftype = f.get("type")
                decay = 0.5 ** (days / _PM_HALFLIFE_DAYS)
                if ftype == "false_buy":
                    penalty = -_PM_MAX_PENALTY * decay
                else:
                    # missed_opportunity 또는 기타 — 감점 없음
                    penalty = 0.0
                memo = {
                    "window": f"{days}d",
                    "days_since": days,
                    "type": ftype,
                    "actual_return": f.get("actual_return"),
                    "misleading_factor": f.get("misleading_factor"),
                    "lesson": f.get("lesson") or f.get("postmortem"),
                    "penalty": round(penalty, 2),
                    "decay_factor": round(decay, 3),
                    "halflife_days": int(_PM_HALFLIFE_DAYS),
                    "penalty_applied": penalty < 0,
                }
                # missed_opportunity 도 memo 는 리턴 (UI 경고 + audit 목적)
                return penalty, memo
    return 0.0, None


# ─── IC factor 매핑 ──────────────────────────────────────────

# IC 팩터명 → fact_score weight 키 매핑
_IC_TO_WEIGHT_KEY = {
    "multi_factor": "multi_factor",
    "consensus": "consensus",
    "prediction": "prediction",
    "timing": "timing",
}

# IC 팩터명 → alpha_combined 보정에 영향주는 서브팩터
_IC_SUBFACTORS = {"momentum", "quality", "volatility", "mean_reversion",
                  "fundamental", "technical", "flow", "sentiment"}


# ─── 보조 score 변환기 ──────────────────────────────────────

def _backtest_to_score(bt: Dict[str, Any]) -> float:
    """백테스트 결과 → 0~100 점수."""
    if not bt or bt.get("total_trades", 0) == 0:
        return 50.0
    wr = bt.get("win_rate", 50)
    sharpe = bt.get("sharpe_ratio", 0)
    score = wr * 0.6 + _clip(sharpe * 20 + 50) * 0.4
    return _clip(score)


# Q5 RULE 7 (2026-05-26, Perplexity 자문 자체 결정 fix, PM 승인):
# 금융/헬스케어/커뮤니케이션 sector = 원자재 가격 상관 통계 무의미
# (`docs/PERPLEXITY_ANSWERS_20260526.md` Q5: 한국 금융/의료기기/엔터 commodity 상관 통계 X)
# yfinance sector 명명 직접 사용 (sector_thresholds 5 bucket 매핑은 Tech 와 Communication 을 IT 로 통합 → 분리 의무).
COMMODITY_MARGIN_EXEMPT_SECTORS = frozenset({
    "Financial Services",       # 금융 (은행/증권/보험/금융지주)
    "Healthcare",               # 헬스케어 (바이오/제약/의료기기/진단)
    "Communication Services",   # 통신/미디어/엔터
})


def _commodity_to_score(cm: Dict[str, Any], stock: Optional[Dict[str, Any]] = None) -> float:
    """원자재 마진 안심 점수 → 0~100 정규화.

    2026-05-18 fix — scale mismatch. CommodityScout._margin_safety_formula 는
    pricing_power*0.6 - raw_vol*0.4 = small range (~0~15) 반환.
    옛: _clip(float(ms)) → 0~15 만 = fact_score 강력 부정 시그널 (fallback 50 ↓ -35점).
    신: 50 + ms shift → 중립 50 기준 ±50 normalize. trigger #4 회귀 (μ40.64→35.52) hotfix.

    2026-05-26 Q5 RULE 7 — sector 면제 (PM 사전등록 2026-05-26, Perplexity 자문):
      stock.sector ∈ COMMODITY_MARGIN_EXEMPT_SECTORS 시 50.0 (neutral) 반환
      → factor 가중치 0 처리 효과 (multi_factor.commodity_margin → 50 neutral)
      → red_flags.py:266 의 commodity_margin ms<30 downgrade flag 도 skip ([[project_sector_aware_exemption_2026_05_26]] 정합)
      sector 미적재 종목 = 기존 산식 적용 (보수성 default).
    """
    if stock and (stock.get("sector") or "") in COMMODITY_MARGIN_EXEMPT_SECTORS:
        return 50.0
    pr = cm.get("primary") or cm
    ms = pr.get("margin_safety_score")
    if ms is None:
        return 50.0
    # 2026-07-21 감사: +50 shift 를 producer(CommodityScout)로 이동 → ms 는 이미 0~100 정규화됨.
    # 기존 _clip(50+ms) 와 수학적 동일(producer 가 50 을 더해 clip[0,100] 하므로). 회귀 0.
    return _clip(float(ms))


def _export_to_score(stock: Dict[str, Any]) -> float:
    """수출입/수급 데이터 기반 점수. US: Finnhub 내부자+기관 데이터로 대체."""
    is_us = stock.get("currency") == "USD"

    if is_us:
        score = 50.0
        insider = stock.get("insider_sentiment") or {}
        mspr = insider.get("mspr", 0)
        if mspr > 0:
            score += min(mspr * 3, 15)
        elif mspr < 0:
            score += max(mspr * 3, -15)

        inst = stock.get("institutional_ownership") or {}
        inst_chg = inst.get("change_pct", 0)
        if inst_chg > 5:
            score += 10
        elif inst_chg < -5:
            score -= 10

        consensus = stock.get("analyst_consensus") or {}
        buy = consensus.get("buy", 0)
        sell = consensus.get("sell", 0)
        total = buy + consensus.get("hold", 0) + sell
        if total > 0:
            buy_pct = buy / total
            if buy_pct > 0.7:
                score += 8
            elif buy_pct < 0.3:
                score -= 8
        else:
            # 2026-05-19 E1 fix — equity_research_brief fallback (Perplexity 가 SEC/yfinance
            # 통해 가져온 recommendation_mean 활용). top-level analyst_consensus.buy/hold/sell
            # 부재 시 (US 5/15 종목) recommendation_mean (1=Strong Buy ~ 5=Strong Sell) 매핑.
            # docs/BRAIN_SCORE_AUDIT_20260518.md §3 export_trade US 53% fallback 의 일부 회복.
            # M1/C2 와 동일 패턴 — 데이터 풍부, 산식 path mismatch.
            ac = (stock.get("equity_research_brief") or {}).get("analyst_consensus") or {}
            rm = ac.get("recommendation_mean")
            if isinstance(rm, (int, float)) and rm > 0:
                if rm <= 2.0:
                    score += 8
                elif rm >= 4.0:
                    score -= 8

        return _clip(score)

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

    # KIS 외인/기관 순매수 반영
    flow = stock.get("flow", {})
    fg = flow.get("kis_foreign_net", 0)
    inst = flow.get("kis_institution_net", 0)
    if fg > 0 and inst > 0:
        score += 8
    elif fg > 0 or inst > 0:
        score += 4
    elif fg < 0 and inst < 0:
        score -= 8
    elif fg < 0 or inst < 0:
        score -= 4

    return _clip(score)


def _compute_kis_fact_bonus(stock: Dict[str, Any]) -> Dict[str, Any]:
    """KIS 데이터(재무비율/투자의견/추정실적/수급) → Fact 보너스."""
    if stock.get("currency") == "USD":
        return {"bonus": 0, "score": 50, "detail": {}}

    bonus = 0.0
    detail = {}

    # 1) 투자의견/목표가 보정
    #    (ROE/부채/유동비율은 graham_value + moat_quality에서 이미 반영 → 중복 제거)
    cons = stock.get("consensus", {})
    kis_target = cons.get("kis_target_price", 0)
    current = stock.get("current_price", 0) or stock.get("close", 0)
    if kis_target and current and current > 0:
        upside = (kis_target - current) / current * 100
        if upside > 30:
            bonus += 3
            detail["target_upside"] = f"+{upside:.0f}%"
        elif upside > 15:
            bonus += 1.5
            detail["target_upside"] = f"+{upside:.0f}%"
        elif upside < -10:
            bonus -= 2
            detail["target_upside"] = f"{upside:.0f}%"

    # 2) 프로그램매매 방향성
    #    (외인/기관 수급은 export_trade에서 전담 → 중복 제거)
    pgm = stock.get("kis_program_trade", {})
    pgm_net = pgm.get("net_buy_3d", 0)
    if pgm_net:
        if pgm_net > 0:
            bonus += 1
            detail["program_net"] = "매수 우위"
        elif pgm_net < 0:
            bonus -= 1
            detail["program_net"] = "매도 우위"

    total_score = _clip(50 + bonus / 0.15) if bonus else 50
    return {"bonus": round(bonus, 2), "score": round(total_score, 1), "detail": detail}


# ─── Fact Score (메인) ──────────────────────────────────────

def _compute_fact_score(
    stock: Dict[str, Any],
    portfolio: Optional[Dict[str, Any]] = None,
    macro_override: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """객관적 수치 기반 종합 점수 (0~100). V5: Graham + CANSLIM 컴포넌트 포함.
    V6: IC/ICIR 피드백으로 가중치 자동 조정.
    Brain Audit §7: regime-aware mean-reversion bonus (위기장에서 비활성)."""
    const = _load_constitution()
    w_raw = (const.get("fact_score") or {}).get("weights") or {}
    w = dict(w_raw)

    ic_adj = _load_ic_adjustments()
    ic_applied = {}
    # 2026-05-25 IC-DEAD freeze (PM 사전등록 [[project_ic_dead_freeze_2026_05_23]]):
    # "ok" 외 "frozen_2026_05_23" status 도 적용. frozen 은 4 PM disable factor 만
    # multiplier 0.0 적용됨, 나머지 9 factor 는 adjustments dict 부재 → 자동 neutral.
    if ic_adj.get("status") in ("ok", "frozen_2026_05_23"):
        for ic_factor, wk in _IC_TO_WEIGHT_KEY.items():
            adj = ic_adj["adjustments"].get(ic_factor)
            if adj and wk in w:
                mult = adj["multiplier"]
                original = w[wk]
                w[wk] = round(original * mult, 4)
                if mult != 1.0:
                    ic_applied[wk] = {"original": original, "adjusted": w[wk],
                                      "multiplier": mult, "status": adj["status"]}

    # Sprint 11 결함 2 (베테랑 due diligence): Graham vs CANSLIM regime switching.
    # 두 철학 충돌 (가치 vs 성장) → 가중평균 시 양쪽 어정쩡. regime 따라 활성화 차등.
    # bull: CANSLIM 우세 (성장+모멘텀), bear: Graham 우세 (가치+안전마진).
    # regime_diagnostics 는 strategy_evolver._classify_regime 가 attach.
    regime_diag = (portfolio or {}).get("regime_diagnostics") or {}
    trailing_s = regime_diag.get("trailing_score")
    leading_s = regime_diag.get("leading_score")
    regime_avg = None
    if isinstance(trailing_s, (int, float)):
        if isinstance(leading_s, (int, float)):
            # leading 가중 1.5× — 선행 신호에 더 무게
            regime_avg = (trailing_s + leading_s * 1.5) / 2.5
        else:
            regime_avg = trailing_s
    regime_applied = {"applied": False, "regime_score": regime_avg, "mode": "default"}
    if isinstance(regime_avg, (int, float)) and "graham_value" in w and "canslim_growth" in w:
        regime_applied["applied"] = True
        if regime_avg > 0.3:  # bull regime
            # CANSLIM 1.5× / Graham 0.5× — 성장 우세
            w["graham_value"] = round(w["graham_value"] * 0.5, 4)
            w["canslim_growth"] = round(w["canslim_growth"] * 1.5, 4)
            regime_applied["mode"] = "bull_canslim_dominant"
        elif regime_avg < -0.3:  # bear regime
            # Graham 1.5× / CANSLIM 0.5× — 가치 우세
            w["graham_value"] = round(w["graham_value"] * 1.5, 4)
            w["canslim_growth"] = round(w["canslim_growth"] * 0.5, 4)
            regime_applied["mode"] = "bear_graham_dominant"
        else:  # mixed
            regime_applied["mode"] = "mixed_balanced"
        regime_applied["graham_weight"] = w["graham_value"]
        regime_applied["canslim_weight"] = w["canslim_growth"]

    # 모든 직접 component get을 _safe_float 으로 감싸 None/NaN/문자열을 50으로 normalize.
    # (수집기가 dict 내부에 None 을 넣어도 종목 단위 polyfill 작동)
    mf = stock.get("multi_factor", {})
    multi_factor_score = _safe_float(mf.get("multi_score"), 50.0)

    consensus = stock.get("consensus", {})
    consensus_score = _safe_float(consensus.get("consensus_score"), 50.0)

    pred = stock.get("prediction", {})
    prediction_score = _clip(_safe_float(pred.get("up_probability"), 50.0))

    bt = stock.get("backtest", {})
    backtest_score = _backtest_to_score(bt)

    timing = stock.get("timing", {})
    timing_score = _safe_float(timing.get("timing_score"), 50.0)

    cm = stock.get("commodity_margin", {})
    commodity_score = _commodity_to_score(cm, stock)

    export_score = _export_to_score(stock)

    moat_score = _compute_moat_score(stock)
    graham_score = _compute_graham_score(stock)
    canslim_score = _compute_canslim_score(stock)

    # Phase 3: 증권사 리포트 + DART 사업보고서 AI 분석 컴포넌트
    analyst_report = stock.get("analyst_report_summary") or {}
    analyst_score = _safe_float(analyst_report.get("analyst_sentiment_score"), 50.0)

    dart_analysis = stock.get("dart_business_analysis") or {}
    dart_health = _safe_float(dart_analysis.get("business_health_score"), 50.0)

    # #2a Perplexity 외부 리스크 — risk_level → 점수 매핑.
    # 스캔 미호출 종목은 50 (중립) 유지 → 부당 감점 없음.
    # 초기 가중치 0.02 (2%) — IC/ICIR 3개월 관찰 후 조정.
    _RISK_SCORE_MAP = {"LOW": 60.0, "MODERATE": 40.0, "HIGH": 15.0, "CRITICAL": 5.0}
    ext_risk = stock.get("external_risk") or {}
    _risk_level = str(ext_risk.get("risk_level", "")).upper()
    perplexity_risk_score = _RISK_SCORE_MAP.get(_risk_level, 50.0)

    # Brain v6 prep (2026-05-17): equity_research_brief verdict → fact_score component.
    # Perplexity Sonar Pro institutional brief (project_perplexity_equity_brief).
    # 미장 US15 만 데이터 존재. KR 종목 = 50 neutral (data 부재).
    # 초기 weight 0.03 (3%) — IC/ICIR 3개월 관찰 후 조정.
    _BRIEF_VERDICT_MAP = {
        "STRONG_BUY": 90.0, "BUY": 75.0, "HOLD": 50.0,
        "AVOID": 25.0, "STRONG_AVOID": 10.0,
    }
    brief = stock.get("equity_research_brief") or {}
    _brief_verdict = str(brief.get("brief_verdict", "")).upper()
    equity_brief_score = _BRIEF_VERDICT_MAP.get(_brief_verdict, 50.0)

    # US Piotroski F-Score (2026-05-20 PM 승인 RULE 7, weight 0.03, 단일 변수).
    # us_financials calibration (data/us_financials) main.py attach. 0~9 → 0~100.
    # US-only — KR/데이터 부재 = 50 neutral. project_us_financials_sec_edgar v0.4.
    _us_fscore_raw = stock.get("us_fscore")
    us_fscore_score = (_safe_float(_us_fscore_raw) / 9.0 * 100.0) \
        if isinstance(_us_fscore_raw, (int, float)) else 50.0

    components = {
        "multi_factor": multi_factor_score,
        "consensus": consensus_score,
        "prediction": prediction_score,
        "backtest": backtest_score,
        "timing": timing_score,
        "commodity_margin": commodity_score,
        "export_trade": export_score,
        "moat_quality": moat_score,
        "graham_value": graham_score,
        "canslim_growth": canslim_score,
        "analyst_report": analyst_score,
        "dart_health": dart_health,
        "perplexity_risk": perplexity_risk_score,
        "equity_brief_verdict": equity_brief_score,  # Brain v6 prep
        "us_fscore": us_fscore_score,  # 2026-05-20 US Piotroski F-Score (RULE 7 승인, 3%)
    }

    # ── P0-1 fix (2026-05-16): IC + regime 적용 후 weight 합 normalize ──
    # 결함: IC=DEAD 시 weight × 0.3 적용 → multi_factor 0.188→0.056, prediction 0.085→0.026,
    #       timing 0.060→0.018. 합 1.000 → ~0.6 으로 떨어짐 → fact_score 자연 ~40% 감점.
    #       brain_score max 46 / BUY 0건 / grade 임계 75/60/45 비현실 결함의 root cause.
    # Fix: weight 합 normalize 적용해 살아있는 factor 비중 보존 (DEAD 비중 → 살아있는 factor 재분배).
    #       의미: "DEAD factor 가 alpha 없으면 그 비중을 alpha 있는 factor 로 옮긴다" — 합리적.
    #       theoretical max 100 도달 가능. grade 임계 정상 작동.
    w_sum = sum(w.values())
    if w_sum > 0 and abs(w_sum - 1.0) > 0.01:
        for k in list(w.keys()):
            w[k] = w[k] / w_sum

    # ── 2026-05-20 data_coverage 진단 (informational only — 점수 변경 X) ──
    # PM 승인 의제로 "결측 컴포넌트 50 fallback 제외+재정규화" 검토 → 수학적으로 no-op 입증:
    #   "결측=50 imputation" ≡ "결측 제외 + present 재정규화 + 50초과분 coverage deflate".
    #   즉 현 imputation 이 이미 보수적 coverage 처리. 점수 변경은 deflate 없는 순수 제외만 가능한데
    #   그건 thin-data 소형주 과대평가 (feedback_seed_size_conservatism 위배). → 가중 로직 미변경.
    # data_coverage 는 저점수가 (데이터 부재) vs (실제 약신호) 인지 구분하는 진단 필드로만 노출.
    def _num(x):
        return isinstance(x, (int, float)) and not (isinstance(x, float) and math.isnan(x))
    _missing = set()
    if not _num(mf.get("multi_score")): _missing.add("multi_factor")
    if not _num(consensus.get("consensus_score")): _missing.add("consensus")
    if not _num(pred.get("up_probability")): _missing.add("prediction")
    if (bt or {}).get("total_trades", 0) == 0: _missing.add("backtest")
    if not _num(timing.get("timing_score")): _missing.add("timing")
    if not _num(analyst_report.get("analyst_sentiment_score")): _missing.add("analyst_report")
    if not _num(dart_analysis.get("business_health_score")): _missing.add("dart_health")
    if _risk_level not in _RISK_SCORE_MAP: _missing.add("perplexity_risk")
    if _brief_verdict not in _BRIEF_VERDICT_MAP: _missing.add("equity_brief_verdict")
    if not _num(_us_fscore_raw): _missing.add("us_fscore")
    _total_w = sum(w.get(k, 0) for k in components)
    _present_w = sum(w.get(k, 0) for k in components if k not in _missing)
    data_coverage = (_present_w / _total_w) if _total_w > 0 else 0.0

    total = 0.0
    for key, val in components.items():
        total += val * w.get(key, 0)

    # 퀀트 팩터 보너스: alpha_combined가 있으면 Fact Score에 가산
    # V6: IC 서브팩터 평균 multiplier로 보너스 스케일링 (아래 블록에서 적용)
    alpha_combined = stock.get("alpha_combined", {})
    alpha_score = alpha_combined.get("score")
    alpha_bonus = 0.0
    if alpha_score is not None and alpha_combined.get("method") != "fallback":
        components["alpha_combined"] = alpha_score

    # 퀀트 서브팩터 요약 (있으면)
    quant_sub = mf.get("quant_factors", {})
    if quant_sub:
        for qk, default in [("momentum", 50), ("quality", 50), ("volatility", 50), ("mean_reversion", 50)]:
            v = quant_sub.get(qk, default)
            components[f"quant_{qk}"] = v if isinstance(v, (int, float)) else default

    # IC 서브팩터 보정: alpha_combined 보너스 스케일링
    # 2026-05-25 IC-DEAD freeze: frozen status 도 적용 (4 PM disable factor 만 0.0).
    alpha_ic_scale = 1.0
    if ic_adj.get("status") in ("ok", "frozen_2026_05_23"):
        sub_mults = []
        for sf in _IC_SUBFACTORS:
            adj_info = ic_adj["adjustments"].get(sf)
            if adj_info:
                sub_mults.append(adj_info["multiplier"])
        if sub_mults:
            alpha_ic_scale = sum(sub_mults) / len(sub_mults)
            alpha_ic_scale = max(0.5, min(1.3, alpha_ic_scale))

    if alpha_score is not None and alpha_combined.get("method") != "fallback":
        alpha_bonus = (alpha_score - 50) * 0.08 * alpha_ic_scale
        total += alpha_bonus

    # ── KIS 데이터 기반 보너스 (KR 종목) ──
    kis_bonus = _compute_kis_fact_bonus(stock)
    if kis_bonus["bonus"] != 0:
        total += kis_bonus["bonus"]
        components["kis_analysis"] = kis_bonus["score"]

    # ── Brain Audit §7: IC-validated technical mean-reversion bonus ──
    # backfill (2020~2026, n=1355) 결과 fact_score 의 모멘텀 가중이 거꾸로
    # (STRONG_BUY avg +2.35% vs CAUTION avg +4.06%). 부호 반전 sub-score 가산.
    # 1단계 (보수적): 가중치 0.07 → 0.03 — STRONG_BUY n=8 → n=30+ 회복 목표.
    # 2단계 (regime-aware): VIX>30 또는 panic/cape_bubble 시 비활성 —
    #   inflation_2022 같은 위기장에서 가격 하락 → mean-reversion 점수 ↑ →
    #   거시 신호와 충돌하는 것 방지.
    tmr_score = _compute_technical_mean_reversion_score(stock)
    if tmr_score is not None:
        components["technical_mean_reversion"] = tmr_score
        if _is_regime_panic(portfolio, macro_override):
            tmr_bonus = 0.0  # 위기장: bonus 비활성
            components["technical_mean_reversion_disabled_regime"] = True
        else:
            tmr_bonus = (tmr_score - 50) * 0.03  # ±50 → ±1.5 max
        total += tmr_bonus

    # ── Brain Audit §11: DART KR fundamental mean-reversion bonus ──
    # KR backfill (n=248, 30종목 10년) 검증 — high ROE/op_margin 후 mean-reversion.
    # KRW 종목만, regime-aware (panic/cape 시 비활성).
    krmr_score = _compute_kr_fundamental_mean_reversion_score(stock)
    if krmr_score is not None:
        components["kr_fundamental_mean_reversion"] = krmr_score
        if _is_regime_panic(portfolio, macro_override):
            krmr_bonus = 0.0
            components["kr_fundamental_mean_reversion_disabled_regime"] = True
        else:
            krmr_bonus = (krmr_score - 50) * 0.03  # ±50 → ±1.5 max
        total += krmr_bonus

    # ── Phase 3 §15: 거버넌스 시그널 (자사주 + 대주주 변동) ──
    # DartScout fetch_treasury_stock / fetch_major_shareholder_changes 결과 활용
    governance_bonus = 0.0
    governance_penalty = 0.0
    governance_meta: List[str] = []

    # 자사주 — 매입 우세 = 주주환원, 처분 우세 = 자금조달/지분매각 의심
    # 2026-06-23 — KR-전용 DART 거버넌스. US 명시 가드(US 데이터 부착 시 KR 보너스 누출 차단).
    _gov_us = stock.get("currency") == "USD"
    treasury = {} if _gov_us else (stock.get("treasury_stock") or {})
    if isinstance(treasury, dict):
        ts_signal = treasury.get("signal")
        net_change = treasury.get("net_change", 0) or 0
        if ts_signal == "positive" or (isinstance(net_change, (int, float)) and net_change > 0):
            governance_bonus += 1.5
            governance_meta.append("treasury_net_acq+1.5")
        elif ts_signal == "warning" or (isinstance(net_change, (int, float)) and net_change < 0):
            governance_penalty += 1.0
            governance_meta.append("treasury_net_dsp-1.0")

    # 대주주 변동 — delta_pct_pt 기준 (5%p 이상 감소 = 강한 경고). US 가드(KR-전용 DART).
    sh_changes = [] if _gov_us else (stock.get("major_shareholder_changes") or [])
    if isinstance(sh_changes, list):
        for ch in sh_changes:
            if not isinstance(ch, dict):
                continue
            delta = ch.get("delta_pct_pt", 0)
            try:
                d = float(delta)
            except (TypeError, ValueError):
                continue
            # 5%p 이상 감소 = 강한 경고 (내부자 매도)
            if d <= -5.0:
                governance_penalty += 2.0
                governance_meta.append(f"major_shareholder_drop({d:+.1f}p)-2.0")
                break  # 한 번만 적용 (중복 방지)
            elif d > 0:
                governance_bonus += 1.0
                governance_meta.append(f"major_shareholder_up({d:+.1f}p)+1.0")
                break

    if governance_bonus or governance_penalty:
        # §24 governance cap — 이론 최대 bonus 2.5 (자사주 +1.5 + 대주주 +1.0),
        # 이론 최대 penalty 3.0 (자사주 -1.0 + 대주주 -2.0).
        # 미래 확장 (규제 리스크 등 추가 시) 에서 극단 누적 방어 — cap ±3.0.
        GOV_CAP = 3.0
        governance_bonus = min(governance_bonus, GOV_CAP)
        governance_penalty = min(governance_penalty, GOV_CAP)
        if governance_bonus == GOV_CAP:
            governance_meta.append("gov_bonus_capped")
        if governance_penalty == GOV_CAP:
            governance_meta.append("gov_penalty_capped")
        components["governance_bonus"] = round(governance_bonus, 2)
        components["governance_penalty"] = round(governance_penalty, 2)
        total += governance_bonus - governance_penalty
        # audit metadata — 어떤 조건이 발동했는지 + cap 적용 여부
        stock.setdefault("data_quality_fixes", []).extend(governance_meta)

    # §26: Postmortem 종목별 time-decay penalty
    # portfolio["postmortem"].windows 의 failures 에서 현재 ticker 매칭 시,
    # window 기반 근사 경과일로 지수 감쇠 soft penalty 부과.
    # halflife=30일: 0일 -2.0, 30일 -1.0, 60일 -0.5, 90일 -0.25.
    # strategy_evolver 의 "전체 패턴→constitution" 경로와 역할 분리 (종목 단위).
    pm_penalty, pm_memo = _compute_postmortem_penalty(stock, portfolio)
    if pm_memo is not None:
        # missed_opportunity 도 memo 는 부착 (UI 경고 · audit)
        stock["postmortem_memo"] = pm_memo
        stock.setdefault("data_quality_fixes", []).append("postmortem_caution")
    if pm_penalty < 0:
        # false_buy 만 실제 점수 차감 (missed_opportunity 는 중립)
        components["postmortem_penalty"] = round(pm_penalty, 2)
        total += pm_penalty

    if not isinstance(total, (int, float)) or math.isnan(total) or math.isinf(total):
        total = 0.0

    result = {
        "score": round(_clip(total)),
        "components": {k: round(v, 1) for k, v in components.items() if isinstance(v, (int, float))},
        "data_coverage": round(data_coverage, 3),
        "missing_components": sorted(_missing),
    }
    if ic_applied:
        result["ic_adjustments"] = ic_applied
    if regime_applied.get("applied"):
        result["regime_weighting"] = regime_applied
    return result
