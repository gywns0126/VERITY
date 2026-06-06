"""
Verity Brain v5.0 — 배리티 터미널의 종합 판단 엔진

V5 학습 소스:
  - Hedge Fund Masters Report (Hohn/McMurtrie/Tang/Dalio/Guindo)
  - Quant & Smart Money Trading Report (Renaissance/Soros/Cohen/Citadel)
  - 30권 투자 고전 통합 (brain_knowledge_base.json v1.0)

핵심 구조:
  Fact Score (객관 + Moat + Graham + CANSLIM) × 0.7
+ Sentiment Score (심리 + 동적 크립토 가중치) × 0.3
+ VCI v2.0 Bonus (Cohen 역발상 체크리스트)
+ Candle Psychology Bonus (Nison Rule of Multiple Techniques)
= Brain Score → 최종 등급 + Kelly 포지션 가이드

V5 추가 모듈:
  - Graham Value Score: 안전마진 + PER/PBR + 재무건전성 (Benjamin Graham)
  - CANSLIM Growth Score: EPS 가속 + RS Rating + 기관 매집 (William O'Neil)
  - Candle Psychology Score: Nison 3대원칙 + 확인 체크리스트 → timing 보너스
  - Bubble Detection: Mackay/Shiller/Taleb 기반 시장 레벨 경고 플래그

모든 가중치와 임계값은 verity_constitution.json v5.0에서 로드.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from api.config import MACRO_DGS10_DEFENSE_PCT
from api.utils.portfolio_writer import read_section

# 2026-05-24 분해 — analyze_stock 3,738줄 monolith → factor 모듈.
# 산식/임계/가중치 변경 X (CLAUDE.md RULE 7 정합), schema 변경 X, signature 변경 X.
# tests 가 verity_brain 에서 직접 import 하는 _compute_fact_score / _compute_sentiment_score 보존.
from api.intelligence.factors._common import (
    _clip,
    _load_constitution,
    _load_ic_adjustments,
    _safe_float,
    reset_ic_cache,  # main.py:3515 외부 caller 보호
)
from api.intelligence.factors.candle import _compute_candle_psychology_score
from api.intelligence.factors.fact import (
    _compute_fact_score,
    _compute_postmortem_penalty,
    _is_regime_panic,
)
from api.intelligence.factors.mean_reversion import (
    _compute_kr_fundamental_mean_reversion_score,
    _compute_technical_mean_reversion_score,
)
from api.intelligence.factors.red_flags import (
    _compute_freshness,
    _detect_red_flags,
    _make_flag,
    _parse_event_date,
    _sec_risk_event_date,
)
from api.intelligence.factors.sentiment import _compute_sentiment_score
from api.intelligence.factors.vci import _cohen_contrarian_checks, _compute_vci


# (V4 Moat / V5 Graham / V5 CANSLIM / V5 Candle Psychology = factors.{moat,graham,canslim,candle} 으로 이동, 2026-05-24)


# ─── V5: Bubble Detection ────────────────────────────────────

def _detect_bubble_signals(portfolio: Dict[str, Any]) -> Dict[str, Any]:
    """Mackay/Shiller/Taleb 기반 시장 레벨 버블 탐지.
    V5.1: 상관 지표를 그룹으로 묶어 그룹 내 최대 1점만 부여 (증폭 방지).
    Returns: {detected: bool, signals: [...], severity: 0~5}"""
    macro = portfolio.get("macro") or {}
    fred = macro.get("fred") or {}
    mood = macro.get("market_mood", {}).get("score", 50)

    signals = []

    # ── 그룹 A: 밸류에이션 (독립 지표) → 최대 2점 ──
    group_a = 0
    cape = fred.get("cape", {}).get("value")
    if cape is not None:
        cape = float(cape)
        if cape > 30:
            signals.append(f"CAPE {cape:.1f} > 30: 역사적 버블 수준 (Shiller)")
            group_a = 2
        elif cape > 25:
            signals.append(f"CAPE {cape:.1f} > 25: 과열 경고 (Shiller)")
            group_a = 1

    # ── 그룹 B: 시장 심리 (상관 지표 묶음) → 최대 1점 ──
    #    mood, VIX, CNN F&G는 모두 "시장 공포/탐욕"을 측정 → 개별 카운트 금지
    group_b = 0
    group_b_signals = []
    vix = macro.get("vix", {}).get("value", 20)
    mfg = portfolio.get("market_fear_greed") or {}
    mfg_val = mfg.get("value", 50) if mfg.get("ok") else 50

    if mood > 85:
        group_b_signals.append(f"시장 분위기 {mood}점")
    if vix < 12:
        group_b_signals.append(f"VIX {vix}(극저)")
    if mfg_val >= 85:
        group_b_signals.append(f"CNN F&G {mfg_val}")
    elif mfg_val <= 15:
        signals.append(f"CNN F&G {mfg_val}: 극단적 공포 (역발상 매수 구간)")

    if group_b_signals:
        signals.append(f"시장 심리 과열: {' / '.join(group_b_signals)} (Mackay/Taleb)")
        group_b = 1

    # ── 그룹 C: 자금 흐름 (독립 지표) → 최대 1점 ──
    group_c = 0
    ff = portfolio.get("fund_flows") or {}
    if ff.get("ok"):
        rot_sig = ff.get("rotation_signal", "neutral")
        if rot_sig == "risk_on" and ff.get("rotation_detail", {}).get("confidence", 0) >= 70:
            signals.append("펀드 플로우: 강한 위험자산 선호 (risk-on)")
            group_c = 1

    # ── 그룹 D: 크립토 과열 (독립 지표) → 최대 1점 ──
    group_d = 0
    crypto = portfolio.get("crypto_macro") or {}
    if crypto.get("available"):
        fng = crypto.get("fear_and_greed", {})
        if fng.get("ok") and fng.get("value", 50) >= 85:
            signals.append(f"크립토 F&G {fng['value']}: 극단적 탐욕")
            group_d = 1

    # ── 그룹 E: Market Horizon cycle_stage (독립 지표) → 최대 2점 (2026-05-16 V2.1 통합) ──
    # cycle_stage = euphoria + cape_percentile ≥ 95 = 강한 버블 신호 (다중 indicator 종합).
    # CAPE/VIX/펀드플로우 와 별개 차원 — 사이클 단계 자체가 입력.
    group_e = 0
    mh = portfolio.get("market_horizon") or {}
    cycle = mh.get("cycle_stage")
    cape_pct = mh.get("cape_percentile")
    if cycle == "euphoria":
        signals.append(f"Market Horizon 사이클: euphoria (CAPE P{cape_pct or '?'}, 11-signal V2.1)")
        group_e = 2 if (cape_pct and cape_pct >= 95) else 1

    severity = group_a + group_b + group_c + group_d + group_e
    return {
        "detected": severity >= 2,
        "signals": signals,
        "severity": min(severity, 5),
    }


# (Fact / Sentiment / VCI / Red Flags = factors.{fact,sentiment,vci,red_flags} 으로 이동, 2026-05-24)
# 분해 대상:
#   _ic_adj_cache / _load_ic_adjustments / reset_ic_cache → factors._common
#   _IC_TO_WEIGHT_KEY / _IC_SUBFACTORS → factors.fact
#   _compute_kr_fundamental_mean_reversion_score → factors.mean_reversion
#   _compute_technical_mean_reversion_score → factors.mean_reversion
#   _PANIC_OVERRIDE_MODES / _is_regime_panic → factors.fact
#   _PM_MAX_PENALTY / _PM_HALFLIFE_DAYS / _compute_postmortem_penalty → factors.fact
#   _compute_fact_score / _compute_kis_fact_bonus → factors.fact
#   _backtest_to_score / _commodity_to_score / _export_to_score → factors.fact
#   _compute_sentiment_score → factors.sentiment
#   _cohen_contrarian_checks / _compute_vci → factors.vci
#   _parse_event_date / _compute_freshness / _make_flag / _sec_risk_event_date / _detect_red_flags → factors.red_flags


# ─── V4: Panic Stage Detection (Soros Reflexivity) ──────────

def _detect_panic_stage(
    vix: float, mood: float, spread: Optional[float], sp_chg: float,
) -> Optional[Dict[str, Any]]:
    """Soros 반사성 이론 기반 패닉 4단계 판별.
    Stage 3(패닉) 구간에서 Cohen 역발상 매수 가능성을 열어둔다."""
    const = _load_constitution()
    stages = const.get("panic_stages", {}).get("stages", {})

    # Stage 3: 패닉 — VIX 극단 + 극도의 공포
    if vix >= 40 and mood < 15:
        stg = stages.get("panic", {})
        msg = (
            f"[패닉 3단계] VIX {vix} / 무드 {mood}점 — "
            "강제 청산·Quality Liquidation 구간. "
            "Cohen 역발상: VCI 극단 시 선별 매수 허용"
        )
        return {
            "mode": "panic_stage3",
            "label": stg.get("label", "패닉"),
            "stage": 3,
            "message": msg,
            "reason": msg,
            "max_grade": stg.get("max_grade", "WATCH"),
            "contrarian_upgrade": stg.get("contrarian_upgrade", True),
        }

    # Stage 4: 절망(Wyckoff 누적) — VIX 하락 중 + 가격 안정화(S&P 하락 완화)
    # Stage 2와 범위가 겹치므로, S&P 변화율로 "하락 가속 vs 안정화" 구분
    if 25 <= vix < 40 and 10 <= mood < 25 and sp_chg > -1.0:
        stg = stages.get("despair", {})
        msg = (
            f"[패닉 4단계] VIX {vix} / 무드 {mood}점 / S&P {sp_chg:+.1f}% — "
            "강제 매도 소진, Wyckoff 누적 구간. 분할 매수 재개"
        )
        return {
            "mode": "panic_stage4",
            "label": stg.get("label", "절망"),
            "stage": 4,
            "message": msg,
            "reason": msg,
            "max_grade": stg.get("max_grade", "BUY"),
            "contrarian_upgrade": True,
        }

    # Stage 2: 두려움 — 기관 리스크 관리 발동 (아직 하락 중)
    if vix >= 30 and mood < 30:
        stg = stages.get("fear", {})
        msg = (
            f"[패닉 2단계] VIX {vix} / 무드 {mood}점 — "
            "기관 리스크 관리 발동, 패시브 환매 압력"
        )
        return {
            "mode": "panic_stage2",
            "label": stg.get("label", "두려움"),
            "stage": 2,
            "message": msg,
            "reason": msg,
            "max_grade": stg.get("max_grade", "WATCH"),
            "contrarian_upgrade": False,
        }

    # Stage 1: 부정 — 하락 초기
    if vix >= 20 and mood < 50 and (
        (spread is not None and spread < 0.3) or sp_chg < -1.5
    ):
        stg = stages.get("denial", {})
        msg = (
            f"[패닉 1단계] VIX {vix} / 무드 {mood}점 / S&P {sp_chg:+.1f}% — "
            "하락 초기, 신규 진입 축소 권고"
        )
        return {
            "mode": "panic_stage1",
            "label": stg.get("label", "부정"),
            "stage": 1,
            "message": msg,
            "reason": msg,
            "max_grade": stg.get("max_grade", "BUY"),
            "contrarian_upgrade": False,
        }

    return None


# ─── V4: Bridgewater Economic Quadrant ──────────────────────

def detect_economic_quadrant(portfolio: Dict[str, Any]) -> Dict[str, Any]:
    """Bridgewater All-Weather 4분면: 성장 × 인플레이션.
    FRED GDP/CPI 또는 매크로 프록시로 분면을 판별한다."""
    macro = portfolio.get("macro", {})
    fred = macro.get("fred") or {}

    gdp_growth = fred.get("gdp_growth", {}).get("value")
    cpi_yoy = fred.get("cpi_yoy", {}).get("value")

    if gdp_growth is None:
        pmi = fred.get("ism_pmi", {}).get("value")
        if pmi is not None:
            gdp_growth = float(pmi) - 50
        else:
            mood = macro.get("market_mood", {}).get("score", 50)
            gdp_growth = (mood - 50) * 0.06

    if cpi_yoy is None:
        pce = fred.get("pce_yoy", {}).get("value")
        if pce is not None:
            cpi_yoy = float(pce)
        else:
            cpi_yoy = 2.5

    gdp_growth = float(gdp_growth) if gdp_growth is not None else 0
    cpi_yoy = float(cpi_yoy)

    growth_up = gdp_growth > 1.5
    inflation_up = cpi_yoy > 3.0

    if growth_up and inflation_up:
        quadrant = "growth_up_inflation_up"
    elif growth_up and not inflation_up:
        quadrant = "growth_up_inflation_down"
    elif not growth_up and inflation_up:
        quadrant = "growth_down_inflation_up"
    else:
        quadrant = "growth_down_inflation_down"

    const = _load_constitution()
    q_cfg = const.get("economic_quadrant", {}).get("quadrants", {}).get(quadrant, {})

    return {
        "quadrant": quadrant,
        "label": q_cfg.get("label", quadrant),
        "favored": q_cfg.get("favored", []),
        "unfavored": q_cfg.get("unfavored", []),
        "crypto_bias": q_cfg.get("crypto_bias", "neutral"),
        "gdp_growth": round(gdp_growth, 2),
        "cpi_yoy": round(cpi_yoy, 2),
    }


# ─── V4.1: Bond Regime Integration ───────────────────────────

import logging as _logging
logger = _logging.getLogger(__name__)
_br_logger = logger


def _load_bond_regime() -> Dict[str, Any]:
    """portfolio.json bonds 섹션에서 bond_regime 읽기.
    없으면 중립 기본값 반환."""
    _defaults = {
        "rate_environment": "unknown",
        "curve_shape":      "unknown",
        "credit_cycle":     "neutral",
        "recession_signal": False,
        "macro_override":   False,
    }
    try:
        bonds = read_section("bonds")
        regime = bonds.get("bond_regime", {})
        return {k: regime.get(k, v) for k, v in _defaults.items()}
    except Exception as e:
        _br_logger.warning(f"[verity_brain] bond_regime 로드 실패: {e}")
        return _defaults


def _reclassify_signal(market_vci_0_100: float) -> str:
    """시장 VCI(0-100 composite) → 시그널.

    2026-06-07: 등급 사다리를 constitution `decision_tree.grades` 단일 출처로 통일
    (기존 하드코드 75/60/45/30 → _score_to_grade 위임, CAUTION 25). 주석도 정정 —
    여기 인자는 종목 contrarian VCI(±25, constitution vci.thresholds)가 아니라
    시장 0-100 composite 다(혼동 주의). 종목 등급(_score_to_grade)과 동일 사다리 사용.
    """
    return _score_to_grade(market_vci_0_100)


def _apply_bond_regime(brain_result: Dict[str, Any], bond_regime: Dict[str, Any]) -> Dict[str, Any]:
    """bond_regime 신호를 VCI 보정 및 macro_override에 반영.

    규칙:
    1. recession_signal → macro_override 강제 + 전 종목 VCI -10
    2. curve_shape=inverted → 금융/리츠 -5, 채권/금 ETF +5
    3. credit_cycle=stress → HY 관련 AVOID 강제
    4. rate_environment → 팩터 바이어스 힌트 주입
    """
    if not bond_regime:
        return brain_result

    recession    = bond_regime.get("recession_signal", False)
    curve_shape  = bond_regime.get("curve_shape", "unknown")
    credit_cycle = bond_regime.get("credit_cycle", "neutral")
    rate_env     = bond_regime.get("rate_environment", "unknown")

    if recession:
        existing_ov = brain_result.get("macro_override")
        if existing_ov is None:
            brain_result["macro_override"] = {
                "mode": "bond_recession",
                "label": "채권 경기침체 신호",
                "message": "수익률 곡선 역전 — 방어 모드 전환",
                "reason": "yield_curve_inversion",
                "max_grade": "WATCH",
            }
        else:
            secondary = existing_ov.get("secondary_signals", [])
            secondary.append({"mode": "bond_recession", "label": "채권 경기침체 신호", "max_grade": "WATCH"})
            existing_ov["secondary_signals"] = secondary
            existing_max = existing_ov.get("max_grade", "WATCH")
            if GRADE_ORDER.index("WATCH") > GRADE_ORDER.index(existing_max):
                existing_ov["max_grade"] = "WATCH"

        for s in brain_result.get("stocks", []):
            orig = s.get("brain_score", 0)
            new_score = max(0, orig - 10)
            s["brain_score"] = new_score
            s["bond_penalty"] = -10
            # 기존 grade보다 완화 금지: red_flags/macro_override cap 보존
            recomputed = _score_to_grade(new_score)
            prev_grade = s.get("grade", "AVOID")
            s["grade"] = _cap_grade(recomputed, prev_grade)
            s["grade_confidence"] = _grade_confidence(new_score, s["grade"])

    if curve_shape == "inverted":
        penalty_cats = {"sector_financial", "alternative_reit", "sector_finance"}
        bonus_cats = {"bond_us_long", "bond_us_mid", "alternative_gold",
                      "commodity_gold", "bond_kr", "bond_us_agg"}
        for s in brain_result.get("stocks", []):
            cat = s.get("category", "")
            sector = (s.get("sector") or "").lower()
            if cat in penalty_cats or "금융" in sector or "부동산" in sector:
                new_score = max(0, s.get("brain_score", 0) - 5)
                s["brain_score"] = new_score
                s["bond_curve_adj"] = -5
                recomputed = _score_to_grade(new_score)
                prev_grade = s.get("grade", "AVOID")
                s["grade"] = _cap_grade(recomputed, prev_grade)
                s["grade_confidence"] = _grade_confidence(new_score, s["grade"])

    if credit_cycle == "stress":
        for s in brain_result.get("stocks", []):
            cat = s.get("category", "")
            name = s.get("name", "").lower()
            if "hy" in cat or "high_yield" in name or "하이일드" in name:
                s["grade"] = "AVOID"
                s["brain_score"] = min(s.get("brain_score", 30), 25)
                s["credit_override"] = "HY_STRESS_AVOID"
                s["grade_confidence"] = "firm"

    rate_hint = {
        "rate_high_restrictive":  {"value_bias": +5, "momentum_bias": -5},
        "rate_elevated":          {"value_bias": +2, "momentum_bias": -2},
        "rate_normal":            {"value_bias":  0, "momentum_bias":  0},
        "rate_low_accommodative": {"value_bias": -5, "momentum_bias": +5},
    }
    brain_result["bond_regime_applied"] = {
        "rate_environment": rate_env,
        "curve_shape":      curve_shape,
        "credit_cycle":     credit_cycle,
        "recession_signal": recession,
        "factor_bias":      rate_hint.get(rate_env, {}),
    }

    return brain_result


# ─── Macro Override (V4 통합) ───────────────────────────────

def detect_macro_override(portfolio: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """매크로 환경이 극단적일 때 포트폴리오 레벨 오버라이드.
    V5.1: 모든 활성 시그널을 수집 → 최고 심각도 primary + 나머지 secondary.
    기존 first-match-return 방식의 시그널 누락 문제 해결."""
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

    _GRADE_SEVERITY = {
        "AVOID": 5, "CAUTION": 4, "WATCH": 3, "BUY": 2, "STRONG_BUY": 1,
    }

    signals: List[Dict[str, Any]] = []

    def _add(sig: Dict[str, Any]) -> None:
        sig["_severity"] = _GRADE_SEVERITY.get(sig.get("max_grade", "BUY"), 2)
        signals.append(sig)

    # ── Soros 패닉 4단계 ──
    panic_stage = _detect_panic_stage(vix, mood, spread, sp_chg)
    if panic_stage is not None:
        panic_stage["quadrant"] = detect_economic_quadrant(portfolio)
        _add(panic_stage)

    # ── VIX/스프레드 패닉 ──
    if vix > 35 or (spread is not None and spread < 0 and sp_chg < -3):
        if not panic_stage:
            msg = f"VIX {vix} / 스프레드 {spread}%p / S&P {sp_chg:+.1f}% — 신규 매수 금지, 현금 확보"
            _add({"mode": "panic", "label": "패닉 모드", "message": msg, "reason": msg, "max_grade": "WATCH"})

    # ── 금리 방패 ──
    if y10 is not None and y10 >= MACRO_DGS10_DEFENSE_PCT:
        msg = f"미 10년 국채 {y10:.2f}% (≥{MACRO_DGS10_DEFENSE_PCT}%) — 할인율·밸류에이션 압력, 현금 비중 확대 권고"
        _add({"mode": "yield_defense", "label": "금리 방패", "message": msg, "reason": msg, "max_grade": "WATCH"})

    # ── 유포리아 ──
    if vix < 12 and mood > 80:
        msg = f"VIX {vix} / 분위기 {mood}점 — 과열 경고, 차익 실현 고려"
        _add({"mode": "euphoria", "label": "과열 모드", "message": msg, "reason": msg, "max_grade": "BUY"})

    # ── KIS VI 연쇄 ──
    kis_mkt = portfolio.get("kis_market", {})
    if kis_mkt:
        vi_stocks = kis_mkt.get("vi_status", [])
        if len(vi_stocks) >= 5 and vix > 25:
            names = ", ".join(s.get("hts_kor_isnm", "?") for s in vi_stocks[:3])
            msg = f"VI 발동 {len(vi_stocks)}종목 ({names} 등) + VIX {vix} — 시장 급변동 경계"
            _add({"mode": "vi_cascade", "label": "VI 연쇄 경보", "message": msg, "reason": msg, "max_grade": "WATCH"})

    # ── 한국 기준금리 ──
    ecos = macro.get("ecos") or {}
    kr_rate = ecos.get("korea_policy_rate", {}).get("value")
    if kr_rate is not None and float(kr_rate) >= 4.5 and mood < 40:
        msg = f"한국 기준금리 {kr_rate}% + 무드 {mood}점 — 고금리·비관 복합, 보수적 접근"
        _add({"mode": "kr_rate_defense", "label": "기준금리 방패", "message": msg, "reason": msg, "max_grade": "WATCH"})

    # ── 리세션 확률 ──
    rec = fred.get("us_recession_smoothed_prob", {}).get("pct")
    if rec is not None and float(rec) >= 50:
        msg = f"미국 리세션 확률 {rec}% — 극단적 방어 국면"
        _add({"mode": "recession_alert", "label": "리세션 경보", "message": msg, "reason": msg, "max_grade": "WATCH"})

    # ── Perplexity 이벤트 ──
    for ei in portfolio.get("event_insights", []):
        if ei.get("severity") == "CRITICAL" and "error" not in ei:
            ev_name = ei.get("event", "매크로 이벤트")
            msg = f"Perplexity 실시간 분석: {ev_name} — CRITICAL 영향. {ei.get('us_impact', '')[:60]}"
            _add({"mode": "perplexity_event_critical", "label": "이벤트 긴급 경보", "message": msg, "reason": msg, "max_grade": "WATCH"})
            break

    # ── 펀드 플로우 ──
    ff = portfolio.get("fund_flows", {})
    if ff.get("ok"):
        rot_sig = ff.get("rotation_signal", "neutral")
        rot_detail = ff.get("rotation_detail", {})
        if rot_sig == "cash_flight" and rot_detail.get("confidence", 0) >= 60:
            msg = f"펀드 플로우: 주식·채권 동반 유출 (현금 선호). {rot_detail.get('detail', '')}"
            _add({"mode": "fund_flow_cash_flight", "label": "자금 이탈 경보", "message": msg, "reason": msg, "max_grade": "WATCH"})

    # ── CFTC COT ──
    cot = portfolio.get("cftc_cot", {})
    if cot.get("ok"):
        cot_summary = cot.get("summary", {})
        cot_signal = cot_summary.get("overall_signal", "neutral")
        cot_conviction = cot_summary.get("conviction_level", 0)
        if cot_signal == "bearish" and cot_conviction >= 70:
            sp_data = cot.get("instruments", {}).get("SP500", {})
            net_str = f"S&P500 순포지션 {sp_data.get('net_managed_money', 0):+,}" if sp_data.get("ok") else ""
            msg = f"CFTC COT 기관 순매도 강화 (확신도 {cot_conviction}%). {net_str}"
            _add({"mode": "cot_bearish", "label": "기관 포지셔닝 약세 경보", "message": msg, "reason": msg, "max_grade": "BUY"})

    # ── CNN Fear & Greed ──
    mfg = portfolio.get("market_fear_greed", {})
    if mfg.get("ok"):
        mfg_val = mfg.get("value", 50)
        if mfg_val >= 90:
            msg = f"CNN Fear & Greed {mfg_val} (극도탐욕) — 시장 과열, 신규 매수 자제"
            _add({"mode": "market_extreme_greed", "label": "시장 극단 탐욕 경보", "message": msg, "reason": msg, "max_grade": "BUY"})

    # ── 크립토 과열 ──
    crypto = portfolio.get("crypto_macro", {})
    if crypto.get("available"):
        fng = crypto.get("fear_and_greed", {})
        funding = crypto.get("funding_rate", {})
        kimchi = crypto.get("kimchi_premium", {})
        fng_val = fng.get("value", 50) if fng.get("ok") else 50
        funding_pct = funding.get("rate_pct", 0) if funding.get("ok") else 0
        kimchi_pct = kimchi.get("premium_pct", 0) if kimchi.get("ok") else 0

        if fng_val >= 80 and funding_pct >= 0.06 and kimchi_pct >= 5:
            parts = [f"크립토 F&G {fng_val}(극단 탐욕)", f"펀딩비 {funding_pct:+.3f}%", f"김프 {kimchi_pct:+.1f}%"]
            msg = " / ".join(parts) + " — 위험자산 전체 과열, 차익 실현 고려"
            _add({"mode": "crypto_overheat", "label": "크립토 과열 경보", "message": msg, "reason": msg, "max_grade": "BUY"})

    # ── Phase A 신규 매크로 게이트 (2026-05-15, Brain Signal Integration v0.1) ──
    # 32 미반영 신호 중 영향도 TOP 4 — 즉시 통합. 임계값 출처: docs/BRAIN_SIGNAL_INTEGRATION_PLAN_v0.1.md §2.
    # ※ 5/17 sprint 후 65 거래일 운영 검증으로 임계값 fine-tune.

    # ── USD/KRW 환율 — 90일 동적 σ 기반 (Perplexity 2026-05-16) ──
    # 정상 σ ≈ 0.50%/일 (2010-2024 평균) / 2025-2026 σ ≈ 0.60% (NYU VLAB).
    # 고정 ±1.5% (3σ 정상기) → 동적 3σ 자동 계산 (regime adaptive).
    # fat-tail (excess kurtosis 4-6) 로 정규분포 가정 대비 실제 3-4배 발생.
    usd_krw = macro.get("usd_krw", {}) or {}
    fx_chg = usd_krw.get("change_pct")
    if fx_chg is not None:
        try:
            fx_chg_f = float(fx_chg)
            # 동적 σ — 직전 90일 snapshot 에서 산출. 2026-05-24 RULE 7 사전 등록 (PM 결정 trail):
            #   Perplexity Q5 정합 (docs/PERPLEXITY_ANSWERS_20260524.md):
            #     - EWMA(λ=0.94, RiskMetrics 표준, mean=0 returns 가정) 우선 — fat-tail 정합 (kurtosis 4-6)
            #     - 90d rolling std = fallback / 보수 결합용
            #     - σ_final = max(σ_floor, min(σ_EWMA, σ_simple)) — Perplexity 권고 산식
            #     - σ_floor 0.30% soft floor (operational baseline)
            #   미래 sprint (별도 사전 등록 의무):
            #     - GARCH(1,1) 보정 (arch 라이브러리 의존 추가, 안정기 ↔ 위기기 전환 정합)
            #     - Quantile threshold (Q1/Q5/Q95/Q99) 병행 — 정규 ±3σ = 0.27% 이론과 실제 1%+ 빈도 mismatch 보정
            LAMBDA_EWMA = 0.94      # RiskMetrics 표준
            SIGMA_FLOOR = 0.30      # operational soft floor
            sigma_dyn = SIGMA_FLOOR
            sigma_method = "floor"
            actual_n = 0
            try:
                from api.workflows.archiver import load_snapshots_range
                snaps90 = load_snapshots_range(90) or []
                chgs = []
                for s in snaps90:
                    c = ((s.get("macro") or {}).get("usd_krw") or {}).get("change_pct")
                    if c is not None:
                        try:
                            chgs.append(float(c))
                        except (TypeError, ValueError):
                            continue
                actual_n = len(chgs)
                if actual_n >= 20:
                    # EWMA(λ=0.94) recursion — mean=0 returns 가정 (RiskMetrics)
                    sigma_sq = chgs[0] ** 2  # 초기값 = r₀²
                    for c in chgs[1:]:
                        sigma_sq = LAMBDA_EWMA * sigma_sq + (1 - LAMBDA_EWMA) * (c ** 2)
                    sigma_ewma = sigma_sq ** 0.5
                    # 90d simple std (비교 + fallback)
                    mean_c = sum(chgs) / actual_n
                    var_simple = sum((c - mean_c) ** 2 for c in chgs) / actual_n
                    sigma_simple = var_simple ** 0.5
                    # Perplexity Q5 권고: σ_final = max(σ_floor, min(σ_EWMA, σ_simple))
                    sigma_dyn = max(SIGMA_FLOOR, min(sigma_ewma, sigma_simple))
                    sigma_method = "EWMA" if sigma_ewma <= sigma_simple else "90d std"
            except Exception:
                pass

            # ── Quantile threshold 병행 (Q5 답변 정합, 2026-05-24 RULE 7 사전 등록 + impl) ──
            #   excess kurtosis 4-6 fat-tail → 정규 ±3σ = 0.27% 이론 vs 실제 1%+ 빈도 mismatch.
            #   3σ 단독 게이트 = 누락 risk. Quantile (Q1/Q5/Q95/Q99) 병행 = 비대칭 보정 + 분포 기반 학술 정합.
            #   N≥20: Q5/Q95 산출 (5% tail, 신뢰도 mid)
            #   N≥100: Q1/Q99 추가 (1% tail, 신뢰도 high — VERITY 자연 회복 ~2026-08 무렵)
            #   PM 결정 trail: 사용자 명시 "박아" (2026-05-24 d94baa41 후속).
            quantile_alert = None
            quantile_thresholds: Dict[str, float] = {}
            if actual_n >= 20:
                try:
                    chgs_sorted = sorted(chgs)
                    q5_idx = max(0, int(actual_n * 0.05))
                    q95_idx = min(actual_n - 1, int(actual_n * 0.95))
                    quantile_thresholds["q5"] = round(chgs_sorted[q5_idx], 3)
                    quantile_thresholds["q95"] = round(chgs_sorted[q95_idx], 3)
                    if actual_n >= 100:
                        q1_idx = max(0, int(actual_n * 0.01))
                        q99_idx = min(actual_n - 1, int(actual_n * 0.99))
                        quantile_thresholds["q1"] = round(chgs_sorted[q1_idx], 3)
                        quantile_thresholds["q99"] = round(chgs_sorted[q99_idx], 3)
                    # 현재 fx_chg 분위수 위치 (가장 강한 신호부터 매칭)
                    if "q1" in quantile_thresholds and fx_chg_f <= quantile_thresholds["q1"]:
                        quantile_alert = f"Q1 극단 ({quantile_thresholds['q1']:+.2f}%, 1% 하단 tail)"
                    elif "q99" in quantile_thresholds and fx_chg_f >= quantile_thresholds["q99"]:
                        quantile_alert = f"Q99 극단 ({quantile_thresholds['q99']:+.2f}%, 1% 상단 tail)"
                    elif fx_chg_f <= quantile_thresholds["q5"]:
                        quantile_alert = f"Q5 주의 ({quantile_thresholds['q5']:+.2f}%, 5% 하단 tail)"
                    elif fx_chg_f >= quantile_thresholds["q95"]:
                        quantile_alert = f"Q95 압력 ({quantile_thresholds['q95']:+.2f}%, 5% 상단 tail)"
                except (IndexError, ValueError, TypeError):
                    pass

            threshold_3sigma = round(sigma_dyn * 3, 2)
            # fx_shock 게이트: 3σ 또는 Quantile alert (Q1/Q99 극단 또는 |chg| ≥ 3σ)
            triggered_3sigma = abs(fx_chg_f) >= threshold_3sigma
            triggered_quantile_extreme = quantile_alert is not None and ("Q1 극단" in quantile_alert or "Q99 극단" in quantile_alert)
            if triggered_3sigma or triggered_quantile_extreme:
                direction = "원화 급락 (수입주·내수주 압박)" if fx_chg_f > 0 else "원화 급등 (수출주 압박)"
                # trail label: actual 일수 + method (Q5 정합)
                n_label = f"최근 {actual_n}d" if 20 <= actual_n < 90 else "90일"
                quantile_extra = f" / {quantile_alert}" if quantile_alert else ""
                msg = (f"USD/KRW {usd_krw.get('value', '?')}원 {fx_chg_f:+.2f}% — "
                       f"{direction}, 외인 자금 신호 ({n_label} {sigma_method} σ={sigma_dyn:.2f}%, 3σ={threshold_3sigma}%{quantile_extra})")
                _add({"mode": "fx_shock", "label": "환율 급변동", "message": msg, "reason": msg, "max_grade": "WATCH"})
        except (TypeError, ValueError):
            pass

    # ── WTI 원유 3단계 (Perplexity 2026-05-16) ──
    # 일간 σ ≈ 1.95%, 연 vol ~31%. 거래일 비중: ±2% 36% / ±3% 13.5% / ±5% 4.8% / ±7% 1.9%.
    # ±2% = 1σ 일상 잡음 (게이트 부적합). 3단계: OPEC/뉴스 → 정치·공급 → 극단 지정학.
    wti = macro.get("wti_oil", {}) or {}
    wti_chg = wti.get("change_pct")
    if wti_chg is not None:
        try:
            wti_chg_f = float(wti_chg)
            abs_chg = abs(wti_chg_f)
            direction = "급등 (인플레·운송 부담)" if wti_chg_f > 0 else "급락 (정유주 충격)"
            # Tier 3 — 극단 지정학 (쿠웨이트 침공 +14% / 우크라 +8% 패턴)
            if abs_chg >= 7.0:
                msg = f"WTI ${wti.get('value', '?')} {wti_chg_f:+.2f}% {direction} — 극단 지정학 충격"
                _add({"mode": "oil_geopolitical_shock", "label": "원유 지정학 극단", "message": msg, "reason": msg, "max_grade": "WATCH"})
            # Tier 2 — 정치/공급 충격 (OPEC, Abqaiq 등)
            elif abs_chg >= 5.0:
                msg = f"WTI ${wti.get('value', '?')} {wti_chg_f:+.2f}% {direction} — 정치·공급 충격"
                _add({"mode": "oil_shock", "label": "원유 급변동", "message": msg, "reason": msg, "max_grade": "WATCH"})
            # Tier 1 — OPEC 성명·EIA 재고 서프라이즈 (정유·항공·화학 즉각 반응 임계)
            elif abs_chg >= 3.0:
                msg = (f"WTI ${wti.get('value', '?')} {wti_chg_f:+.2f}% — OPEC/재고 뉴스 반응 "
                       f"(정유 ±3% / 항공 ±5% / 화학 ±5% 섹터 영향)")
                _add({"mode": "oil_news_reaction", "label": "원유 뉴스 반응", "message": msg, "reason": msg, "max_grade": "BUY"})
        except (TypeError, ValueError):
            pass

    # ── HY spread 5단계 + 변화 속도 보조 (Perplexity 2026-05-16) ──
    # FRED BAMLH0A0HYM2 historical (1997-2026):
    #   평균 4.28%p / 중위 4.53%p / P80 ~6%p / 2008 피크 21.82 / 2020 10.87 / 2022 5.82
    # 5단계: TIGHT(<3.5) / NORMAL(3.5-4.5) / WATCH(4.5-6) / AVOID(6-8) / CRISIS(>8)
    # 보조 트리거: 월간 변화 +100bps 이상 (속도 신호 — 2020-3 단 3개월 360→1087bps 사례).
    hy = macro.get("hy_spread", {}) or {}
    hy_val = hy.get("value")
    hy_chg_30d = hy.get("change_30d_pp") or hy.get("change_4w_pp")  # 월간 변화 (있을 경우)
    if hy_val is not None:
        try:
            hy_f = float(hy_val)
            # CRISIS — 전면 디레버리지
            if hy_f >= 8.0:
                msg = f"HY spread {hy_f:.2f}%p — 신용 위기 극단 (2008/2020 수준), 전면 방어 모드"
                _add({"mode": "credit_crisis", "label": "신용 위기 극단", "message": msg, "reason": msg, "max_grade": "AVOID"})
            # AVOID — 위험자산 축소
            elif hy_f >= 6.0:
                msg = f"HY spread {hy_f:.2f}%p — 명백한 스트레스 (2022 5.82 < 현재 < 2020/2008 진입 직전)"
                _add({"mode": "credit_stress_severe", "label": "신용 위기", "message": msg, "reason": msg, "max_grade": "AVOID"})
            # WATCH — 노출 축소 시작
            elif hy_f >= 4.5:
                msg = f"HY spread {hy_f:.2f}%p — 신용 리스크 확대 (중위값 4.53 상회, P50~P80)"
                _add({"mode": "credit_stress", "label": "신용 리스크 경보", "message": msg, "reason": msg, "max_grade": "WATCH"})
            # TIGHT — 신용 과소평가 경계 (역설적 — risk-off 도 아니지만 위험 인식 부족 신호)
            elif hy_f < 3.5:
                msg = (f"HY spread {hy_f:.2f}%p — 역사적 분포 하위 ~16% (P15.8 = 2.82 = 현재).\n"
                       f"신용 리스크 과소평가 가능성, 신용민감 고배당주·BBB- 익스포저 점검")
                _add({"mode": "credit_complacency", "label": "신용 과열 경계 (TIGHT)", "message": msg, "reason": msg, "max_grade": "BUY"})

            # 보조 트리거: 월간 변화 속도 (절대값 임계 도달 전 조기 경보)
            if hy_chg_30d is not None:
                try:
                    chg_f = float(hy_chg_30d)
                    if chg_f >= 1.0:
                        msg = (f"HY spread 30일 변화 {chg_f:+.2f}%p — 속도 경보 (2020-3 패턴: "
                               f"단 3개월 360→1087bps). 절대값 {hy_f:.2f}%p 와 별개로 노출 점검")
                        _add({"mode": "credit_velocity_spike", "label": "신용 스프레드 급변", "message": msg, "reason": msg, "max_grade": "WATCH"})
                except (TypeError, ValueError):
                    pass
        except (TypeError, ValueError):
            pass

    # ── Gold 급등 (flight to safety 시그널) ──
    # Perplexity 검증 (2026-05-16): 금 +3% 단독 게이트는 false positive 위험.
    # DB 1987~2026 지정학 위기 29건 중 83%가 25일 내 출발가 아래로 회귀,
    # VIX 30+ 후 금 1주 평균 +0.43% < S&P500 +1.44%. 단순 가설 데이터 미지지.
    # 복합 조건 (Gold +2% AND 위험회피 동반 ≥1개) 으로 변경. 출처: docs/...PLAN_v0.2.md §A4.
    gold = macro.get("gold", {}) or {}
    gold_chg = gold.get("change_pct")
    if gold_chg is not None:
        try:
            gold_chg_f = float(gold_chg)
            # 1차 조건: Gold ≥ +2.0% (정상 일변동 σ≈1% 의 2σ)
            if gold_chg_f >= 2.0:
                # 위험회피 동반 시그널 카운트 (1개 이상이면 진성 flight-to-safety)
                risk_off_signals = []
                if vix and vix > 25:
                    risk_off_signals.append(f"VIX {vix}(>25)")
                if sp_chg <= -1.5:
                    risk_off_signals.append(f"S&P -{abs(sp_chg):.2f}%")
                # DXY 약세 (있으면) — macro.dxy.change_pct 우선, fallback usd_krw 강세
                dxy = macro.get("dxy", {}) or {}
                dxy_chg = dxy.get("change_pct")
                if dxy_chg is not None and float(dxy_chg) <= -0.5:
                    risk_off_signals.append(f"DXY {dxy_chg:+.2f}%")

                if risk_off_signals:
                    parts = [f"Gold ${gold.get('value', '?')} {gold_chg_f:+.2f}%"] + risk_off_signals
                    msg = " / ".join(parts) + " — 진성 flight-to-safety (위험회피 동반)"
                    _add({"mode": "flight_to_safety", "label": "안전자산 선호 (복합)", "message": msg, "reason": msg, "max_grade": "BUY"})
                # 단독 Gold +3% 이상은 secondary 정보만 (위험회피 미동반 = false positive 가능성)
                elif gold_chg_f >= 3.0:
                    msg = f"Gold {gold_chg_f:+.2f}% 단독 급등 — 위험회피 미동반 (중앙은행 매수·달러 약세 단독 가능성, 게이트 미발동)"
                    _add({"mode": "gold_solo_spike", "label": "금 단독 급등 (참고)", "message": msg, "reason": msg, "max_grade": "STRONG_BUY"})
        except (TypeError, ValueError):
            pass

    # ── Phase B 우선 2 게이트 (2026-05-16 pre-stage, Perplexity IC 검증) ──
    # 5/17 sprint 정식 진입 전 미리 박힘 (verdict=OK 후 자동 작동).
    # 상세 근거: docs/BRAIN_SIGNAL_INTEGRATION_PLAN_v0.1.md §3-B.

    # ── B-1. US 10Y Breakeven (인플레 기대) ──
    # Perplexity IC: ~-0.10 (N<10 표본). 3% 단독 임계는 overfitting 위험 (2022 단 1회 돌파).
    # 권고: 2.5% + 5d 변화 +20bp 동시 충족 — 표본 N≈20 확대.
    be = (fred or {}).get("breakeven_10y") or (fred or {}).get("t10yie") or {}
    if not be:
        be = macro.get("breakeven_inflation_10y") or {}
    be_val = be.get("value")
    be_chg5 = be.get("change_5d_pp")
    if be_val is not None:
        try:
            be_f = float(be_val)
            be_c = float(be_chg5) if be_chg5 is not None else 0.0
            if be_f >= 3.0:
                msg = f"10Y Breakeven {be_f:.2f}% — 인플레 기대 극단 (2022 패턴), 밸류에이션 압박"
                _add({"mode": "inflation_breakeven_extreme", "label": "기대 인플레 극단", "message": msg, "reason": msg, "max_grade": "WATCH"})
            elif be_f >= 2.5 and be_c >= 0.20:
                msg = f"10Y Breakeven {be_f:.2f}% + 5d Δ{be_c:+.2f}%p — 인플레 기대 가속, 실질금리 상승 채널"
                _add({"mode": "inflation_breakeven_rising", "label": "기대 인플레 가속", "message": msg, "reason": msg, "max_grade": "WATCH"})
        except (TypeError, ValueError):
            pass

    # ── B-3. US 2Y 일급등 (rate shock — Perplexity IC -0.10 ~ -0.15, 5 게이트 중 가장 견고) ──
    # 임계: +10bp (상위 5% tail event). yfinance us_2y.change_pct → 절대 bp 환산.
    # 비대칭성: 급등 충격이 급락 완화보다 KOSPI 반응 2배+. Half-life 2-5일.
    us_2y = macro.get("us_2y", {}) or {}
    us_2y_now = us_2y.get("value")
    if us_2y_now is not None:
        try:
            now_f = float(us_2y_now)
            # 직전 snapshot 값과 비교 (change_pct 가 0.0 인 경우 fallback)
            prev_val = None
            try:
                from api.workflows.archiver import load_snapshots_range
                snaps2 = load_snapshots_range(2) or []
                for s in reversed(snaps2):
                    pv = ((s.get("macro") or {}).get("us_2y") or {}).get("value")
                    if pv is not None:
                        prev_val = float(pv)
                        break
            except Exception:
                pass
            if prev_val is not None and prev_val > 0:
                chg_bp = round((now_f - prev_val) * 100, 1)  # 1%p = 100bp
                if chg_bp >= 10.0:
                    msg = f"US 2Y {now_f:.2f}% 전일 대비 +{chg_bp}bp — rate shock (KOSPI 외인 매도 1차 신호)"
                    _add({"mode": "rate_shock_up", "label": "단기 금리 급등 충격", "message": msg, "reason": msg, "max_grade": "WATCH"})
                elif chg_bp <= -10.0:
                    msg = f"US 2Y {now_f:.2f}% 전일 대비 {chg_bp}bp — 금리 급락 (비대칭 — 급등의 50% 영향)"
                    _add({"mode": "rate_shock_down", "label": "단기 금리 급락", "message": msg, "reason": msg, "max_grade": "BUY"})
        except (TypeError, ValueError):
            pass

    # ── B-4. NASDAQ-KOSPI 5d 동조화 vs 디커플링 (Perplexity IC 0.08-0.15, half-life 1-2주) ──
    # 시변 상관 (regime). 디커플링 (NASDAQ↑ but KOSPI↓ 3%+) = KR 단독 약세 = 외인 회피 신호.
    nasdaq = macro.get("nasdaq", {}) or {}
    nq_chg = nasdaq.get("change_pct")
    kospi_data = (portfolio.get("market_summary") or {}).get("kospi") or {}
    kp_chg = kospi_data.get("change_pct")
    if nq_chg is not None and kp_chg is not None:
        try:
            nq_f = float(nq_chg)
            kp_f = float(kp_chg)
            gap = nq_f - kp_f  # NASDAQ - KOSPI
            # KR 단독 약세: NASDAQ 상승했는데 KOSPI 더 하락 (gap > +3%p) 또는 NASDAQ 하락 폭보다 KOSPI 더 하락
            if gap >= 3.0 and kp_f < 0:
                msg = (f"NASDAQ {nq_f:+.2f}% vs KOSPI {kp_f:+.2f}% (gap +{gap:.2f}%p) "
                       f"— KR 단독 약세, 외인 회피·디커플링 신호")
                _add({"mode": "kr_decoupling_weak", "label": "KR 디커플링 (약세)", "message": msg, "reason": msg, "max_grade": "WATCH"})
            # KR 단독 강세 (역의 경우): KOSPI 가 NASDAQ 보다 +3%p 강세 = 보조 BUY 신호
            elif gap <= -3.0 and kp_f > 0:
                msg = f"KOSPI {kp_f:+.2f}% vs NASDAQ {nq_f:+.2f}% — KR 단독 강세 (gap {gap:.2f}%p)"
                _add({"mode": "kr_decoupling_strong", "label": "KR 디커플링 (강세)", "message": msg, "reason": msg, "max_grade": "STRONG_BUY"})
        except (TypeError, ValueError):
            pass

    # ── B-5. Fed B/S 4주 변동 (QE/QT regime shock — Perplexity IC 0.04-0.09) ──
    # WALCL.change_4w_pct ≥ ±3% = 레짐 전환 신호. Half-life 3-6주.
    # EM 비대칭: QT 가 QE 보다 강한 반응 → QT shock 우선.
    walcl = macro.get("fed_balance_sheet") or (fred or {}).get("walcl") or {}
    walcl_4w = walcl.get("change_4w_pct")
    if walcl_4w is not None:
        try:
            w_f = float(walcl_4w)
            if w_f <= -3.0:
                msg = (f"Fed B/S 4주 {w_f:+.2f}% — QT shock (달러 유동성 축소). "
                       f"외인 KOSPI 순매도 2-3주 시차 우려")
                _add({"mode": "fed_qt_shock", "label": "Fed QT 가속", "message": msg, "reason": msg, "max_grade": "WATCH"})
            elif w_f >= 3.0:
                msg = f"Fed B/S 4주 {w_f:+.2f}% — QE 가속 (위험자산 우호)"
                _add({"mode": "fed_qe_acceleration", "label": "Fed QE 가속", "message": msg, "reason": msg, "max_grade": "STRONG_BUY"})
        except (TypeError, ValueError):
            pass

    # ── B-2. Dr.Copper 5d rolling crash (글로벌 경기 선행) ──
    # Perplexity IC: 1d 0.03 (노이즈), 5d-3m 0.07-0.12 (유의). lookback 5d 채택.
    # Half-life 3-5개월 → 5d rolling 신호로 capex 사이클 약화 조기 포착.
    copper_now = (macro.get("copper") or {}).get("value")
    if copper_now is not None:
        try:
            copper_now_f = float(copper_now)
            # 직전 5 snapshot 평균과 비교 (heavy import 회피용 lazy)
            try:
                from api.workflows.archiver import load_snapshots_range
                snaps5 = load_snapshots_range(5) or []
                hist_vals = []
                for s in snaps5:
                    cv = ((s.get("macro") or {}).get("copper") or {}).get("value")
                    if cv is not None:
                        try:
                            hist_vals.append(float(cv))
                        except (TypeError, ValueError):
                            continue
                if len(hist_vals) >= 3:
                    avg_5d = sum(hist_vals) / len(hist_vals)
                    chg_5d_pct = round((copper_now_f - avg_5d) / avg_5d * 100, 2) if avg_5d else 0
                    if chg_5d_pct <= -5.0:
                        msg = (f"Dr.Copper ${copper_now_f:.2f} / 5d avg ${avg_5d:.2f} "
                               f"({chg_5d_pct:+.2f}%) — 글로벌 capex 사이클 약화 선행 신호 (3-5개월 시차)")
                        _add({"mode": "dr_copper_recession",
                              "label": "구리 5d 급락 (경기 선행)",
                              "message": msg, "reason": msg, "max_grade": "WATCH"})
            except Exception as _e:
                logger.debug("dr_copper 5d rolling skipped: %s", _e)
        except (TypeError, ValueError):
            pass

    # ── Shiller CAPE 버블 ──
    # constitution.json:577~581 의 cape_bubble_mode(CAPE>30 시 신규 매수 보수적·포지션 축소)을 실제 등급 cap으로 연결.
    # max_grade=WATCH 로 panic_stages / cboe_panic 과 동일 패턴 (BUY/STRONG_BUY 종목이 WATCH 이하로 강제됨).
    cape = fred.get("cape", {}).get("value")
    if cape is not None:
        try:
            cape_val = float(cape)
            if cape_val > 30:
                msg = f"Shiller CAPE {cape_val:.1f} > 30 — 역사적 버블 수준 (1929/2000/2007 전조)"
                _add({
                    "mode": "cape_bubble",
                    "label": "CAPE 버블",
                    "message": msg,
                    "reason": msg,
                    "max_grade": "WATCH",
                })
        except (TypeError, ValueError):
            pass

    # ── Market Horizon V2.1 통합 (cycle_stage gate) ──
    # portfolio.market_horizon (CAPE multpl + 11 signal + 8 analog + cycle/signal)
    # = V2.1 박힌 모듈 전체 통합 (memory project_market_horizon).
    # cycle_stage 매핑 → 등급 cap. project_market_horizon 현 verdict = euphoria.
    mh = portfolio.get("market_horizon") or {}
    cycle = mh.get("cycle_stage")
    if cycle:
        verdict_str = mh.get("verdict", "")
        cape_pct = mh.get("cape_percentile")
        if cycle == "panic" or cycle == "capitulation":
            msg = (f"Market Horizon: {cycle} — {verdict_str[:100]}. "
                   f"극단 방어, 신규 매수 금지")
            _add({"mode": "horizon_panic", "label": "사이클 패닉",
                  "message": msg, "reason": msg, "max_grade": "AVOID"})
        elif cycle == "euphoria":
            cp_str = f" CAPE P{cape_pct}" if cape_pct else ""
            msg = (f"Market Horizon: 과열 (Euphoria){cp_str} — {verdict_str[:120]}. "
                   f"신규 매수 보수적, 차익 실현 고려")
            _add({"mode": "horizon_euphoria", "label": "사이클 과열",
                  "message": msg, "reason": msg, "max_grade": "BUY"})
        elif cycle == "early_correction":
            msg = (f"Market Horizon: 조정 초기 — {verdict_str[:120]}. "
                   f"역발상 진입 기회 (Cohen contrarian check 활성)")
            _add({"mode": "horizon_correction", "label": "사이클 조정",
                  "message": msg, "reason": msg, "max_grade": "STRONG_BUY"})

    # ── 섹터 로테이션 vs quadrant 정합성 (constitution drift 탐지) ──
    # KOSPI 5일 누적 수익률 기준 top3/bottom3 가 현재 quadrant 의 favored/unfavored 와
    # 어긋나면 secondary_signal 로 첨부. 텔레그램 알림은 모듈 내부에서 자동 발송.
    try:
        from api.intelligence.sector_rotation_detector import (
            detect_sector_rotation, to_macro_signal as _sector_to_signal,
        )
        # 이미 panic_stage 가 quadrant 를 계산했으면 재사용 (중복 호출 회피)
        _quad = None
        for _s in signals:
            if isinstance(_s.get("quadrant"), dict):
                _quad = _s["quadrant"]
                break
        if _quad is None:
            _quad = detect_economic_quadrant(portfolio)
        _rot = detect_sector_rotation(portfolio, quadrant_info=_quad, notify=True)
        portfolio["sector_rotation_check"] = _rot
        _sig = _sector_to_signal(_rot)
        if _sig:
            _add(_sig)
    except Exception as _e:
        logger.debug("sector_rotation_detector skipped: %s", _e)

    if not signals:
        return None

    # 최고 심각도를 primary로, 나머지를 secondary_signals로 보존
    signals.sort(key=lambda s: s["_severity"], reverse=True)
    primary = signals[0]
    primary.pop("_severity", None)

    secondary = []
    for s in signals[1:]:
        s.pop("_severity", None)
        secondary.append({"mode": s["mode"], "label": s["label"], "max_grade": s["max_grade"]})

    if secondary:
        primary["secondary_signals"] = secondary
        combined_msgs = [primary.get("label", "")]
        combined_msgs += [s["label"] for s in secondary]
        primary["combined_warning"] = " + ".join(combined_msgs)

    # max_grade는 전체 시그널 중 가장 제한적인 것 적용
    most_restrictive = "STRONG_BUY"
    for s in signals:
        g = s.get("max_grade", "BUY")
        if GRADE_ORDER.index(g) > GRADE_ORDER.index(most_restrictive):
            most_restrictive = g
    primary["max_grade"] = most_restrictive

    return primary


# ─── Group Structure Bonus ────────────────────────────────────

def _compute_group_structure_bonus(stock: Dict[str, Any]) -> float:
    """지분구조(대주주 집중도, NAV 할인) → Brain Score 보너스."""
    gs = stock.get("group_structure")
    if not gs:
        return 0.0

    bonus = 0.0

    shareholders = gs.get("major_shareholders", [])
    if shareholders:
        top_pct = _safe_float(shareholders[0].get("ownership_pct"), 0.0)
        if top_pct >= 30:
            bonus += 2
        elif top_pct >= 20:
            bonus += 1

    nav = gs.get("nav_analysis", {})
    discount = _safe_float(nav.get("nav_discount_pct"))
    if discount is not None:
        if discount < -30:
            bonus += 3
        elif discount < -15:
            bonus += 1.5
        elif discount > 50:
            bonus -= 2

    # Brain Audit §2-C: 명시적 cap [-3, +5]. 향후 가산 조건 추가 시 무한 누적 방어.
    return round(min(5.0, max(-3.0, bonus)), 2)


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


def _compute_macro_multiplier(stock: Dict[str, Any],
                              portfolio: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    """B-continuous macro overlay (2026-05-18 PM 승인 박힘).

    근거 (Perplexity batch 5/18, learning_materials/perplexity_caution_answers_2026_05_18.md):
    - PBR > 3.0 + CAPE 99%ile = Max DD -52.4% (저PBR -15.2% 대비 3.5배)
    - 고PER + 고PBR forward 12M = 1.9% vs 저밸류 27.1% (격차 25.2%p)
    - CAPE-10Y 상관 -0.7 (CFA Institute)
    - 한국 대신증권: B/P Q1 vs Q4 Sharpe 1.0 vs 0.1

    설계 (B2 권고 정합): binary cutoff (WATCH→AVOID 강등) 아닌 continuous score multiplier.
    binary = threshold 민감 + 경계 turnover + 정보 손실. soft gate = score discount.

    multiplier = 1 - clip(valuation_penalty + currency_penalty + cape_penalty, 0, 0.30)
    - max 30% cap = 극단 환경에서도 brain_score 부분 보존 (crisis-only binary X)
    - PBR 기반 (PER 손익관리 노이즈 큼)
    - currency_penalty KR 종목만 (외국인 자금 이탈 위험)
    - CAPE penalty = US Shiller 활용 (KR CAPE 임계 부재, KR-specific 후속 큐잉)

    Returns: (multiplier 0.7~1.0, meta dict)
    """
    macro = portfolio.get("macro") or {}
    horizon = portfolio.get("market_horizon") or {}

    pbr = _safe_float(stock.get("pbr"), 1.0) or 1.0
    valuation_penalty = max(0.0, min(0.15, (pbr - 1.0) / 3.0 * 0.15))

    currency_penalty = 0.0
    usdkrw = None
    if stock.get("currency") == "KRW":
        usdkrw = _safe_float((macro.get("usd_krw") or {}).get("value"), 0.0) or 0.0
        if usdkrw >= 1400:
            currency_penalty = max(0.0, min(0.075, (usdkrw - 1400) / 200 * 0.15))

    cape_pct = _safe_float(horizon.get("cape_percentile"), 50.0) or 50.0
    cape_penalty = 0.0
    if cape_pct >= 90:
        cape_penalty = max(0.0, min(0.075, (cape_pct - 90) / 10 * 0.15))

    total_penalty = min(0.30, valuation_penalty + currency_penalty + cape_penalty)
    multiplier = round(1.0 - total_penalty, 3)

    meta = {
        "multiplier": multiplier,
        "total_penalty": round(total_penalty, 3),
        "valuation_penalty": round(valuation_penalty, 3),
        "currency_penalty": round(currency_penalty, 3),
        "cape_penalty": round(cape_penalty, 3),
        "inputs": {
            "pbr": pbr,
            "usdkrw": usdkrw,
            "cape_pct": cape_pct,
            "currency": stock.get("currency"),
        },
        "version": "v0_2026_05_18",
        "rule_reference": "perplexity_caution_answers_2026_05_18.md B1+B2",
    }
    return multiplier, meta


def _downgrade(grade: str, steps: int = 1) -> str:
    idx = GRADE_ORDER.index(grade) if grade in GRADE_ORDER else len(GRADE_ORDER) - 1
    new_idx = min(idx + steps, len(GRADE_ORDER) - 1)
    return GRADE_ORDER[new_idx]


def _cap_grade(grade: str, max_grade: str) -> str:
    """등급을 max_grade 이하로 제한."""
    g_idx = GRADE_ORDER.index(grade) if grade in GRADE_ORDER else len(GRADE_ORDER) - 1
    m_idx = GRADE_ORDER.index(max_grade) if max_grade in GRADE_ORDER else 0
    return GRADE_ORDER[max(g_idx, m_idx)]


def _grade_confidence(score: float, grade: str) -> str:
    """등급 판정의 견고성 라벨 — "firm" / "soft".

    2026-06-03 정의 신설 (RULE 10 audit): 395/411/1705/1769 에서 호출되나 정의·import
    부재 → 만기주(chase_buy_allowed=False)+BUY 종목 시 NameError 로 analyze_all 전체
    크래시하던 잠복 P0 차단. 호출부 시그니처(score, grade) 그대로 수용.

    산식 (자기 산식 — 가설, 검증 N 누적 중): brain_score 가 해당 등급 구간의 경계
    (하한 min_brain_score / 상한 = 다음 상위 등급 min)에서 margin(5점) 이내면 "soft"
    (작은 입력 변동에 등급이 흔들림), 구간 중앙이면 "firm". 임계는 constitution
    decision_tree.grades 단일 출처 로드 (하드코드 X, RULE 7 정합).
    """
    const = _load_constitution()
    grades = const.get("decision_tree", {}).get("grades", {})
    margin = 5.0
    idx = GRADE_ORDER.index(grade) if grade in GRADE_ORDER else len(GRADE_ORDER) - 1
    lo = grades.get(grade, {}).get("min_brain_score", 0)
    hi = 100.0
    if idx > 0:  # 다음 상위 등급의 min = 현재 등급의 상한
        hi = grades.get(GRADE_ORDER[idx - 1], {}).get("min_brain_score", 100.0)
    near_lo = (score - lo) < margin
    near_hi = idx > 0 and (hi - score) < margin
    return "soft" if (near_lo or near_hi) else "firm"


# ─── V4: Position Sizing Guide (Kelly Criterion) ────────────

def _compute_position_guide(
    brain_score: int,
    grade: str,
    red_flags: Dict[str, Any],
) -> Dict[str, Any]:
    """Kelly Criterion 간소화 + McMurtrie 상한 기반 포지션 비중 가이드.
    brain_score를 승률 프록시로 사용, 보수적 payoff ratio 적용."""
    const = _load_constitution()
    ps = const.get("position_sizing", {})
    kelly_params = ps.get("kelly_params", {})
    max_pct_map = ps.get("max_position_pct", {})

    b = kelly_params.get("payoff_ratio", 1.5)
    p = brain_score / 100.0
    q = 1.0 - p

    kelly_raw = max(0, (b * p - q) / b) * 100 if b > 0 else 0
    max_pct = max_pct_map.get(grade, 0)

    if red_flags.get("has_critical"):
        recommended = 0.0
        rationale = "레드플래그(즉시회피) — 포지션 불가"
    elif red_flags.get("downgrade_count", 0) >= 2:
        recommended = min(kelly_raw * 0.5, max_pct)
        rationale = f"하향조정 {red_flags['downgrade_count']}건 — 비중 절반 축소"
    else:
        recommended = min(kelly_raw, max_pct)
        rationale = f"Kelly {kelly_raw:.1f}% → {grade} 상한 {max_pct}% 적용"

    return {
        "recommended_pct": round(recommended, 1),
        "kelly_raw_pct": round(kelly_raw, 1),
        "max_pct": max_pct,
        "rationale": rationale,
    }


# ── timing_signal — sentiment + technical 분리 노출 ────────
# 베테랑 due diligence 결함 5 후속 (2026-05-01):
# brain_score 의 sentiment 가중치는 점진 감소 트랙 (env override). 그러나 sentiment +
# technical 자체는 단기 진입 타이밍 시그널로 가치 있음 → brain_score 에서 떼어내 별도
# timing_signal 객체로 노출. 즉 "브레인 (펀더멘털 중심)" + "타이밍 (단기 시그널)" 두
# 트랙 분리. UI/리포트는 둘 다 표시 — 동시 confirm 시 강한 신호.
TIMING_SENTIMENT_WEIGHT = 0.70
TIMING_TECHNICAL_WEIGHT = 0.30


def _compute_timing_signal(stock: Dict[str, Any],
                           sentiment_block: Dict[str, Any]) -> Dict[str, Any]:
    """sentiment + technical 별도 점수. brain_score 결정 입력에서 분리.

    score >= 70 STRONG_BUY / 60 BUY / 50 NEUTRAL / 40 WEAK / else WAIT.
    sentiment alpha decay 1-3일 (Tetlock 2007+) 이라 brain_score 보다 단기. 별도 트랙.
    """
    try:
        sent_score = float(sentiment_block.get("score") or 50)
    except (TypeError, ValueError):
        sent_score = 50.0
    tech = stock.get("technical", {}) or {}
    try:
        tech_score = float(tech.get("technical_score") or 50)
    except (TypeError, ValueError):
        tech_score = 50.0

    timing = round(sent_score * TIMING_SENTIMENT_WEIGHT + tech_score * TIMING_TECHNICAL_WEIGHT, 1)
    if timing >= 70:
        signal = "STRONG_BUY"
    elif timing >= 60:
        signal = "BUY"
    elif timing >= 50:
        signal = "NEUTRAL"
    elif timing >= 40:
        signal = "WEAK"
    else:
        signal = "WAIT"

    return {
        "score": timing,
        "signal": signal,
        "sentiment_component": round(sent_score, 1),
        "technical_component": round(tech_score, 1),
        "weights": {"sentiment": TIMING_SENTIMENT_WEIGHT, "technical": TIMING_TECHNICAL_WEIGHT},
        "version": "v1",
        "note": "brain_score (펀더멘털) 와 분리. 단기 진입 타이밍 보조 — 동시 confirm 시 강한 신호",
    }


def _get_brain_weights(quadrant_name: Optional[str] = None) -> Dict[str, float]:
    """경제 사이클 분면에 따른 fact/sentiment 가중치를 반환한다.
    수축기일수록 감성 노이즈가 커지므로 fact 비중을 높인다.

    Sprint 11 결함 5 (베테랑 due diligence 부분 대응):
      env override BRAIN_FACT_WEIGHT_OVERRIDE / BRAIN_SENTIMENT_WEIGHT_OVERRIDE 가
      설정되면 모든 quadrant 우선. 베테랑 권고 비율 (0.85/0.15) 점진 적용 위함.
      sentiment alpha decay 1-3일 (Tetlock 2007+) 이라 portfolio decision factor
      로는 과대평가 — env 로 조정해서 운영 비교 후 default 갱신.
    """
    import os
    env_fact = os.environ.get("BRAIN_FACT_WEIGHT_OVERRIDE")
    env_sent = os.environ.get("BRAIN_SENTIMENT_WEIGHT_OVERRIDE")
    if env_fact and env_sent:
        try:
            wf = float(env_fact)
            ws = float(env_sent)
            if 0.0 <= wf <= 1.0 and 0.0 <= ws <= 1.0:
                return {"fact": wf, "sentiment": ws, "_source": "env_override"}
        except ValueError:
            pass

    const = _load_constitution()
    dt = const.get("decision_tree", {})
    bw = dt.get("brain_weights", {})
    default = bw.get("default", {"fact": 0.70, "sentiment": 0.30})

    override_q = dt.get("quadrant_override")
    if override_q and override_q in bw:
        return bw[override_q]

    if quadrant_name and quadrant_name in bw:
        return bw[quadrant_name]

    return default


def analyze_stock(
    stock: Dict[str, Any],
    portfolio: Dict[str, Any],
    macro_override: Optional[Dict[str, Any]] = None,
    quadrant_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    단일 종목에 대한 Verity Brain 종합 판단.

    Returns:
        brain_score, fact_score, sentiment_score, vci, grade,
        red_flags, reasoning 등을 포함한 dict.
    """
    # Brain Audit §2-D: 모든 강등/상향 단계가 audit 가능하도록 빈 리스트로 초기화.
    stock.setdefault("overrides_applied", [])

    # Brain Audit §13 (production 오심 #2, 현대모비스 2026-04-18):
    # PBR 데이터 오류로 멀티팩터 과소평가 → AVOID → +6.1% 미스.
    # PBR ≤ 0 또는 None 일 때 중립값 1.0 (시장 평균 PBR ≈ 1.5 이지만 보수적으로 1.0).
    # 2-A _safe_float 패턴 동일.
    _pbr_raw = stock.get("pbr")
    try:
        _pbr_v = float(_pbr_raw) if _pbr_raw is not None else None
    except (TypeError, ValueError):
        _pbr_v = None
    if _pbr_v is None or _pbr_v <= 0:
        stock["pbr"] = 1.0
        stock["pbr_normalized_neutral"] = True
        stock.setdefault("data_quality_fixes", []).append("pbr_invalid_to_1.0")

    fact = _compute_fact_score(stock, portfolio=portfolio, macro_override=macro_override)
    sentiment = _compute_sentiment_score(stock, portfolio)
    # timing_signal — sentiment + technical 분리 노출 (brain_score 결정 입력 X).
    # 단기 진입 타이밍 보조. 결함 5 후속 (2026-05-01).
    stock["timing_signal"] = _compute_timing_signal(stock, sentiment)
    vci = _compute_vci(fact["score"], sentiment["score"], stock, portfolio)
    red_flags = _detect_red_flags(stock, portfolio)

    fs = float(fact["score"] or 0)
    ss = float(sentiment["score"] or 0)
    vci_val = vci["vci"]

    vci_bonus = 0
    if vci_val > 25 and fs >= 60:
        vci_bonus = 5
    elif vci_val < -25 and fs < 50:
        vci_bonus = -10

    bw = _get_brain_weights(quadrant_name)
    w_fact = bw["fact"]
    w_sent = bw["sentiment"]

    gs_bonus = _compute_group_structure_bonus(stock)

    # V5: Nison 캔들 심리 보너스
    candle_bonus = _compute_candle_psychology_score(stock)

    # V6: 13F 기관 스마트머니 보너스 (US 종목만, 분기 수집 후 존재 시)
    inst_bonus = 0
    if stock.get("currency") == "USD":
        inst_13f = portfolio.get("institutional_13f", {}).get("signal", {})
        if inst_13f.get("ok"):
            ticker_sig = inst_13f.get("ticker_signal", {})
            issuer_key = (stock.get("name") or "").upper()
            matched = ticker_sig.get(issuer_key, {})
            if not matched:
                for k, v in ticker_sig.items():
                    if v.get("issuer", "").upper() in issuer_key or issuer_key in v.get("issuer", "").upper():
                        matched = v
                        break
            if matched:
                iscore = _safe_float(matched.get("score"), 50.0)
                if iscore >= 70:
                    inst_bonus = 3
                elif iscore >= 60:
                    inst_bonus = 1

    red_flag_penalty = min(red_flags["downgrade_count"] * 5, 20)
    raw = fs * w_fact + ss * w_sent + vci_bonus + gs_bonus + candle_bonus + inst_bonus - red_flag_penalty
    if not isinstance(raw, (int, float)) or math.isnan(raw) or math.isinf(raw):
        raw = 0.0
    # Brain Audit §3-C: clip(0, 100) 적용 전 raw 값을 별도 보존.
    # raw 는 100 초과 가능 (이론적 최대 123) — STRONG_BUY 동률 종목의 강도 차이 보존용.
    raw_brain_score = round(raw, 2)
    stock["raw_brain_score"] = raw_brain_score
    brain_score_pre_macro = round(_clip(raw))

    # Regime-aware 분리 (2026-05-23 PM 승인, RULE 7): macro/regime multiplier 를
    # 점수 레이어 → 포지션 사이징 레이어로 이전. brain_score = 종목 내재 점수(pre-macro),
    # macro_mult 은 VAMS execute_buy 의 사이징에 적용(0.7~1.0×, stock["macro_multiplier"]).
    # 근거: project_regime_aware_position_sizing (5/19 Q4 학술, AQR/Vanguard/RAFI/Robeco/GMO
    #   5/5 정합) = "절대 임계 60 고정 + regime multiplier 는 사이징". 5/18 점수-multiplier 가
    #   pre_macro 60(=BUY) 종목을 51(WATCH)로 강등(BUY-0 root cause) → 신호 ⊥ 사이징 분리.
    #   SHADOW(2026-05-23): 점수 이전 시 BUY 1 / WATCH 14 / CAUTION 10 (봇물 아님, 보수적).
    # macro 보수성 보존: 등급은 내재 점수로 유지, macro 비관 시 포지션을 multiplier 배 축소.
    # (B-continuous overlay 2026-05-18 원안의 soft-gate 의도 유지 — 적용 레이어만 이동.)
    _macro_mult, _macro_mult_meta = _compute_macro_multiplier(stock, portfolio)
    brain_score = brain_score_pre_macro  # 등급 = 내재 점수 (macro 는 사이징으로 이전)
    stock["brain_score_pre_macro"] = brain_score_pre_macro
    stock["macro_multiplier"] = _macro_mult_meta

    grade = _score_to_grade(brain_score)

    if red_flags["has_critical"]:
        # NOTE: has_critical 시 grade 만 AVOID 강제, brain_score 자체는 보존.
        # 의도: 펀더멘털 점수 (brain_score=70 등) 정보 보존 → mean-reversion oversold 식별 가능.
        # AdminDashboard / 리포트는 grade 와 brain_score 따로 표시 — "점수 좋아도 회피" 사례 명시.
        grade = "AVOID"
    elif red_flags["downgrade_count"] >= 1:
        # weighted float → 등급 강등 단계는 int (FRESH 1건=1단계, FRESH 2+ 또는 weighted≥2=2단계)
        steps = 2 if red_flags["downgrade_count"] >= 2 else 1
        grade = _downgrade(grade, steps)

    # Brain Audit §8: AVOID 라벨 재정의 — fact_score 단독으로는 AVOID 부여 금지.
    # backfill 검증 (30종목 5년 8130행) 에서 AVOID 등급 평균 +3.23% > BUY 의 +1.67%.
    # 대형주 universe 의 low brain_score = oversold → mean-reversion 반등 후보.
    # AVOID 는 펀더멘털 결함(has_critical) 또는 macro_override 위기 cap 에만 한정.
    if grade == "AVOID" and not red_flags["has_critical"]:
        grade = "CAUTION"

    # Brain Audit §14 (production 오심 #3, Coinbase 2026-04-18):
    # multi_factor 단독 거부권으로 AVOID 부여돼 +27.3% 미스.
    # brain_score ≥ 55 (펀더멘털 양호) AND ai_upside ≥ 65 (AI 강한 호재) 동시 충족 시
    # AVOID → CAUTION 완화 (외생 이벤트 / 섹터 모멘텀 인정).
    # has_critical 여부 무관 — AI 신호가 회계 노이즈를 압도하는 케이스 허용.
    _ai_upside = float(stock.get("prediction", {}).get("up_probability", 0) or 0)
    if grade == "AVOID" and brain_score >= 55 and _ai_upside >= 65:
        grade = "CAUTION"
        stock.setdefault("overrides_applied", []).append("ai_upside_relax")

    if macro_override:
        max_g = macro_override.get("max_grade", "WATCH")
        _pre_cap = grade
        grade = _cap_grade(grade, max_g)
        if grade != _pre_cap:
            # cap 이 실제 발동했을 때만 overrides_applied 에 mode 기록 (audit 용).
            # primary mode 는 most_restrictive 시그널 = 실제 cap 결정 주체.
            _mo_mode = macro_override.get("mode")
            if _mo_mode and _mo_mode not in stock["overrides_applied"]:
                stock["overrides_applied"].append(_mo_mode)

        # V5.1: 패닉 stage 3+4에서 Cohen 체크 3개 이상 통과 시 한 단계 상향
        #   Stage 3(패닉): STRONG_CONTRARIAN_BUY 필요
        #   Stage 4(절망/Wyckoff 누적): MILD_CONTRARIAN_BUY 이상이면 허용
        #   단, auto_avoid 종목은 펀더멘털 사망 신호 우선 — 역발상 상향 금지
        if macro_override.get("contrarian_upgrade") and not red_flags.get("has_critical"):
            vci_signal = vci.get("signal", "")
            stage = macro_override.get("stage", 0)
            contrarian_ok = (
                vci_signal == "STRONG_CONTRARIAN_BUY"
                or (stage == 4 and vci_signal in ("STRONG_CONTRARIAN_BUY", "CONTRARIAN_BUY"))
            )
            if contrarian_ok:
                cohen = vci.get("cohen_checklist")
                if cohen and cohen["passed"] >= 3:
                    g_idx = GRADE_ORDER.index(grade) if grade in GRADE_ORDER else 2
                    if g_idx > 0:
                        grade = GRADE_ORDER[g_idx - 1]
                        stock["overrides_applied"].append("contrarian_upgrade")

    # ── 경제 사이클 분면별 unfavored 섹터 패널티 ──
    # constitution.json:281~327 의 quadrant.unfavored 정의를 실제 grade 강등으로 연결.
    # 예: 스태그플레이션(growth_down_inflation_up) → "주식/회사채/성장주" unfavored.
    # 이미 has_critical로 AVOID 강제된 종목은 추가 강등 의미 없음.
    quadrant_info = stock.get("quadrant_info", {}) or {}
    unfavored = quadrant_info.get("unfavored", []) or []
    stock_sector = (stock.get("sector") or "").strip()
    if unfavored and stock_sector and not red_flags.get("has_critical"):
        sector_lower = stock_sector.lower()
        matched = next((u for u in unfavored if u and u.lower() in sector_lower), None)
        if matched:
            brain_score = max(0, brain_score - 5)
            grade = _downgrade(grade, 1)
            stock.setdefault("overrides_applied", []).append("quadrant_unfavored")
            stock["quadrant_unfavored_match"] = {
                "quadrant": quadrant_info.get("quadrant"),
                "matched_unfavored": matched,
                "stock_sector": stock_sector,
            }

    # ── Brain Audit §6: score_breakdown (감사용 항목별 기여도 분해) ──
    # 모든 등급 조정이 끝난 직후, position_guide / reasoning 이전에 분해 기록.
    # raw_before_penalty + penalties.red_flag = raw_brain_score (clip 전 합산값).
    fact_contrib = round(fs * w_fact, 1)
    sent_contrib = round(ss * w_sent, 1)
    raw_before = round(
        fs * w_fact + ss * w_sent + vci_bonus + candle_bonus + gs_bonus + inst_bonus, 1
    )
    quadrant_unfav_pen = -5 if "quadrant_unfavored" in (stock.get("overrides_applied") or []) else 0
    stock["score_breakdown"] = {
        "fact_contribution": fact_contrib,
        "sentiment_contribution": sent_contrib,
        "vci_bonus": round(vci_bonus, 1),
        "candle_bonus": round(candle_bonus, 1),
        "gs_bonus": round(gs_bonus, 2),
        "inst_bonus": round(inst_bonus, 1),
        "raw_before_penalty": raw_before,
        "penalties": {
            "red_flag": -round(red_flag_penalty, 1),
            "quadrant_unfavored": quadrant_unfav_pen,
        },
        "final_score": brain_score,
        "raw_brain_score": stock.get("raw_brain_score", brain_score),
        "grade": grade,
        "grade_caps_applied": [
            o for o in (stock.get("overrides_applied") or [])
            if o not in ("quadrant_unfavored", "contrarian_upgrade")
        ],
    }

    # V4: Kelly Criterion 기반 포지션 비중 가이드
    position_guide = _compute_position_guide(brain_score, grade, red_flags)

    reasoning = _build_reasoning(
        stock, fact, sentiment, vci, red_flags, brain_score, grade, macro_override
    )

    # ── 베테랑 정량 trigger 평가 (2026-05-16 신규, PR #26 후속) ──
    # Druckenmiller conviction + Ackman activist + Hohn capital allocation.
    # stock 에 brain_score 결과를 임시 주입 후 평가 (recursive 회피).
    veteran_signals = {}
    try:
        from api.intelligence.veteran_triggers import evaluate_all_veteran_triggers
        # brain_score 결과 임시 주입 (druckenmiller 가 brain_score + vci 참조)
        stock_view = dict(stock)
        stock_view["verity_brain"] = {"brain_score": brain_score, "vci": vci}
        veteran_signals = evaluate_all_veteran_triggers(stock_view, portfolio)
    except Exception as _e:
        logger.debug("veteran_triggers skipped: %s", _e)

    return {
        "brain_score": brain_score,
        "raw_brain_score": raw_brain_score,
        "grade": grade,
        "grade_label": GRADE_LABELS.get(grade, grade),
        # 2026-06-03 P1-3: 정상 경로 confidence/coverage 실측 (이전엔 정상 return 에 부재 →
        # 소비단 default "firm"/1.0 placeholder 로 Brier 채점·리포트 신호 0 이던 것 정정).
        "grade_confidence": _grade_confidence(brain_score, grade),
        "data_coverage": round(_safe_float(fact.get("data_coverage"), 1.0) or 1.0, 3),
        "fact_score": fact,
        "sentiment_score": sentiment,
        "vci": vci,
        "vci_bonus": vci_bonus,
        "candle_bonus": candle_bonus,
        "inst_13f_bonus": inst_bonus,
        "brain_weights": {"fact": w_fact, "sentiment": w_sent, "quadrant": quadrant_name},
        "red_flag_penalty": red_flag_penalty,
        "red_flags": red_flags,
        "position_guide": position_guide,
        "reasoning": reasoning,
        "macro_override": macro_override.get("mode") if macro_override else None,
        "veteran_signals": veteran_signals,
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
    core_keys = {"multi_factor", "consensus", "prediction", "backtest",
                 "timing", "commodity_margin", "export_trade"}
    core_fc = {k: v for k, v in fc.items() if k in core_keys}
    if core_fc:
        top_fact = max(core_fc, key=core_fc.get)
        bottom_fact = min(core_fc, key=core_fc.get)
        parts.append(
            f"팩트 최강 {top_fact}({core_fc[top_fact]:.0f}) "
            f"/ 최약 {bottom_fact}({core_fc[bottom_fact]:.0f})"
        )

    # 퀀트 팩터 인사이트
    quant_parts = []
    mf = stock.get("multi_factor", {})
    qf = mf.get("quant_factors", {})
    if qf:
        def _qf_num(v, fallback=50):
            return v if isinstance(v, (int, float)) else fallback
        mom = _qf_num(qf.get("momentum", 50))
        qual = _qf_num(qf.get("quality", 50))
        vol = _qf_num(qf.get("volatility", 50))
        mr = _qf_num(qf.get("mean_reversion", 50))

        if mom >= 75:
            quant_parts.append(f"모멘텀↑{mom}")
        elif mom <= 25:
            quant_parts.append(f"모멘텀↓{mom}")
        if qual >= 75:
            quant_parts.append(f"퀄리티↑{qual}")
        elif qual <= 25:
            quant_parts.append(f"퀄리티↓{qual}")
        if mr >= 75:
            quant_parts.append(f"평균회귀매수↑{mr}")
        if vol >= 75:
            quant_parts.append(f"저변동↑{vol}")
        elif vol <= 25:
            quant_parts.append(f"고변동↓{vol}")

    if quant_parts:
        parts.append("퀀트: " + " | ".join(quant_parts))

    # V5: Graham + CANSLIM 인사이트
    v5_parts = []
    graham_v = fc.get("graham_value")
    if graham_v is not None and graham_v != 50:
        if graham_v >= 70:
            v5_parts.append(f"Graham가치↑{graham_v:.0f}")
        elif graham_v <= 35:
            v5_parts.append(f"Graham가치↓{graham_v:.0f}")
    canslim_v = fc.get("canslim_growth")
    if canslim_v is not None and canslim_v != 50:
        if canslim_v >= 70:
            v5_parts.append(f"CANSLIM↑{canslim_v:.0f}")
        elif canslim_v <= 35:
            v5_parts.append(f"CANSLIM↓{canslim_v:.0f}")
    if v5_parts:
        parts.append("V5: " + " | ".join(v5_parts))

    # KIS 분석 인사이트
    kis_parts = []
    kis_an = fc.get("kis_analysis")
    if kis_an is not None and kis_an != 50:
        flow = stock.get("flow", {})
        fg = flow.get("kis_foreign_net", 0)
        inst = flow.get("kis_institution_net", 0)
        if fg or inst:
            fg_dir = "매수" if fg > 0 else "매도" if fg < 0 else ""
            inst_dir = "매수" if inst > 0 else "매도" if inst < 0 else ""
            if fg_dir:
                kis_parts.append(f"외인{fg_dir}")
            if inst_dir:
                kis_parts.append(f"기관{inst_dir}")
        ks = stock.get("kis_short_sale", {})
        sr = ks.get("avg_short_ratio_5d", 0)
        if sr > 5:
            kis_parts.append(f"공매도{sr:.1f}%")
        kc = stock.get("kis_credit_balance", {})
        cr = kc.get("credit_rate", 0)
        if cr > 3:
            kis_parts.append(f"신용{cr:.1f}%")
    if kis_parts:
        parts.append("KIS: " + " | ".join(kis_parts))

    gs = stock.get("group_structure")
    if gs:
        gs_parts = []
        shareholders = gs.get("major_shareholders", [])
        if shareholders:
            top = shareholders[0]
            gs_parts.append(f"최대주주 {top.get('name','?')} {top.get('ownership_pct',0)}%")
        nav_d = gs.get("nav_analysis", {}).get("nav_discount_pct")
        if nav_d is not None:
            if nav_d < 0:
                gs_parts.append(f"NAV {nav_d}% 할인")
            elif nav_d > 0:
                gs_parts.append(f"NAV +{nav_d}% 할증")
        if gs_parts:
            parts.append("지분: " + " | ".join(gs_parts))

    if vci["signal"] != "ALIGNED":
        parts.append(f"VCI: {vci['label']}")

    is_us = stock.get("currency") == "USD"
    if is_us:
        us_missing = []
        if not stock.get("analyst_consensus"):
            us_missing.append("애널리스트컨센서스")
        if not stock.get("insider_sentiment"):
            us_missing.append("내부자거래")
        if not stock.get("options_flow"):
            us_missing.append("옵션플로우")
        if not stock.get("sec_financials"):
            us_missing.append("SEC재무")
        if us_missing:
            parts.append(f"US 미수집: {', '.join(us_missing)}")

    if red_flags["auto_avoid"]:
        parts.append(f"레드플래그(즉시회피): {'; '.join(red_flags['auto_avoid'])}")
    elif red_flags["downgrade"]:
        parts.append(f"하향조정: {'; '.join(red_flags['downgrade'])}")

    if macro_override:
        parts.append(f"매크로 {macro_override.get('label', '?')}: {macro_override.get('message', '')}")

    return " | ".join(parts)


# ─── Market Structure Override (V5.2: 만기일 + 프로그램 매매) ─────

def _apply_market_structure_override(
    result: Dict[str, Any],
    portfolio: Dict[str, Any],
) -> Dict[str, Any]:
    """만기일 관망 + 프로그램 매도폭탄을 brain result에 오버라이드 적용."""
    from api.collectors.expiry_calendar import get_expiry_status
    from api.collectors.program_trading_collector import get_program_trading_today

    expiry = get_expiry_status()
    program = portfolio.get("program_trading") or get_program_trading_today()

    market_brain = result.get("market_brain", {})

    position_cap = expiry["position_size_cap"]

    if program.get("sell_bomb"):
        position_cap = 0.0

    market_brain["expiry"] = {
        "watch_level": expiry["watch_level"],
        "reason": expiry["reason"],
        "days_to_kr_option": expiry["days_to_kr_option"],
        "days_to_kr_futures": expiry["days_to_kr_futures"],
        "days_to_us_quad": expiry["days_to_us_quad"],
        "next_kr_option": expiry["next_kr_option"],
        "next_kr_futures": expiry["next_kr_futures"],
        "next_us_quad": expiry["next_us_quad"],
        "chase_buy_allowed": expiry["chase_buy_allowed"],
        "position_size_cap": position_cap,
    }

    market_brain["program_trading"] = {
        "signal": program.get("signal", "NEUTRAL"),
        "arb_net_bn": program.get("arb_net_bn", 0),
        "non_arb_net_bn": program.get("non_arb_net_bn", 0),
        "total_net_bn": program.get("total_net_bn", 0),
        "sell_bomb": program.get("sell_bomb", False),
        "sell_bomb_reason": program.get("sell_bomb_reason"),
    }

    # 만기 FULL_WATCH 또는 매도폭탄 → BUY 종목을 WATCH로 강등
    if not expiry["chase_buy_allowed"] or program.get("sell_bomb"):
        downgrade_reason = (
            program.get("sell_bomb_reason", "프로그램 매도 폭탄")
            if program.get("sell_bomb")
            else expiry["reason"]
        )
        for stock in result.get("stocks", []):
            if stock.get("grade") in ("STRONG_BUY", "BUY"):
                stock["grade"] = "WATCH"
                stock["grade_label"] = "관망"
                stock["grade_confidence"] = _grade_confidence(stock.get("brain_score", 0), "WATCH")
                stock["reasoning"] = (
                    f"[만기/프로그램 강등] {downgrade_reason} | "
                    + stock.get("reasoning", "")
                )
                # Brain Audit §2-D: market_structure 강등 audit
                stock.setdefault("overrides_applied", []).append("market_structure_downgrade")
        # 등급 분포 재집계
        dist = {g: 0 for g in ("STRONG_BUY", "BUY", "WATCH", "CAUTION", "AVOID")}
        for s in result.get("stocks", []):
            g = s.get("grade", "AVOID")
            dist[g] = dist.get(g, 0) + 1
        market_brain["grade_distribution"] = dist

    result["market_brain"] = market_brain
    return result


def _apply_cboe_pcr_override(
    result: Dict[str, Any],
    portfolio: Dict[str, Any],
) -> Dict[str, Any]:
    """CBOE 풋/콜 비율 시그널을 VCI 보정 + 패닉 시 등급 상한 적용."""
    pcr = portfolio.get("cboe_pcr", {})
    if not pcr:
        return result

    market_brain = result.get("market_brain", {})
    vci_adj = pcr.get("vci_adjustment", 0.0)
    panic = pcr.get("panic_trigger", False)
    signal = pcr.get("signal", "NEUTRAL")

    if vci_adj and market_brain.get("vci") is not None:
        orig_vci = market_brain["vci"]
        market_brain["vci"] = round(max(0, min(100, orig_vci + vci_adj)), 2)
        market_brain["vci_signal"] = _reclassify_signal(market_brain["vci"])

    market_brain["cboe_pcr"] = {
        "signal": signal,
        "panic_trigger": panic,
        "vci_adjustment": vci_adj,
        "pcr_latest": pcr.get("total_pcr_latest"),
    }

    if panic:
        max_grade = "WATCH"
        existing_ov = result.get("macro_override")
        if existing_ov is None:
            result["macro_override"] = {
                "mode": "cboe_panic",
                "label": "CBOE 풋/콜 패닉",
                "message": f"PCR 극단 — {pcr.get('panic_reason', '')}",
                "reason": "cboe_pcr_panic",
                "max_grade": max_grade,
            }
        else:
            secondary = existing_ov.get("secondary_signals", [])
            secondary.append({"mode": "cboe_panic", "label": "CBOE 풋/콜 패닉", "max_grade": max_grade})
            existing_ov["secondary_signals"] = secondary

        for s in result.get("stocks", []):
            if s.get("grade") in ("STRONG_BUY", "BUY"):
                s["grade"] = max_grade
                s["grade_label"] = GRADE_LABELS.get(max_grade, max_grade)
                s["grade_confidence"] = _grade_confidence(s.get("brain_score", 0), max_grade)
                s["cboe_downgrade"] = True

    result["market_brain"] = market_brain
    return result


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

    quadrant_info = detect_economic_quadrant(portfolio)
    q_name = quadrant_info.get("quadrant")

    # V6: 레짐 자동 감지 + 팩터 가중치 multiplier
    regime_info: Dict[str, Any] = {}
    try:
        from api.analyzers.macro_adjustments import detect_market_regime
        regime_info = detect_market_regime(portfolio.get("macro", {}))
    except Exception as e:
        logger.debug("Regime detection skipped: %s", e)

    _empty_rf = {
        "auto_avoid": [], "downgrade": [],
        "auto_avoid_detail": [], "downgrade_detail": [],
        "has_critical": False, "downgrade_count": 0, "weighted_penalty": 0,
    }
    stock_results = []
    for stock in candidates:
        # 분면 정보 attach (analyze_stock 내부 unfavored 섹터 패널티 로직이 사용)
        stock["quadrant_info"] = quadrant_info
        try:
            result = analyze_stock(stock, portfolio, macro_ov, quadrant_name=q_name)
        except Exception as exc:
            logger.warning("analyze_stock failed for %s: %s", stock.get("ticker"), exc)
            result = {
                "brain_score": 0, "raw_brain_score": 0.0,
                "grade": "WATCH", "grade_label": "관망",
                "grade_confidence": "firm", "data_coverage": 0.0,
                "fact_score": {"score": 0, "components": {}, "data_coverage": 0.0},
                "sentiment_score": {"score": 0, "components": {}},
                "vci": {"vci": 0}, "vci_bonus": 0, "candle_bonus": 0,
                "brain_weights": {}, "red_flag_penalty": 0,
                "red_flags": _empty_rf,
                "position_guide": {"recommended_pct": 0, "kelly_raw_pct": 0, "max_pct": 0, "rationale": "분석 오류"},
                "reasoning": f"분석 중 오류 발생: {exc}",
                "macro_override": None,
            }
        stock_results.append({
            "ticker": stock.get("ticker"),
            "name": stock.get("name"),
            **result,
        })

    # Brain Audit §3-C: 다중 키 안정 정렬.
    #   1차 brain_score (clip 100) DESC → 등급 그룹화
    #   2차 raw_brain_score (clip 전, 100 초과 가능) DESC → 동률 시 강도 우선
    #   3차 ticker ASC → 그래도 같으면 결정적 순서 보장
    stock_results.sort(key=lambda x: (
        -float(x.get("brain_score", 0) or 0),
        -float(x.get("raw_brain_score", 0) or 0),
        str(x.get("ticker") or ""),
    ))

    scores = [r.get("brain_score", 0) for r in stock_results]
    facts = [(r.get("fact_score") or {}).get("score", 0) for r in stock_results]
    sents = [(r.get("sentiment_score") or {}).get("score", 0) for r in stock_results]

    avg = lambda xs: round(sum(xs) / len(xs)) if xs else 0
    market_brain = {
        "avg_brain_score": avg(scores),
        "avg_fact_score": avg(facts),
        "avg_sentiment_score": avg(sents),
        "avg_vci": avg(facts) - avg(sents),
        "grade_distribution": _count_grades(stock_results),
        "top_picks": [
            {
                "ticker": r["ticker"], "name": r["name"],
                "score": r["brain_score"], "grade": r["grade"],
                "grade_confidence": r.get("grade_confidence", "firm"),
                "data_coverage": r.get("data_coverage", 1.0),
            }
            for r in stock_results if r["grade"] in ("STRONG_BUY", "BUY")
        ][:5],
        "red_flag_stocks": [
            {"ticker": r["ticker"], "name": r["name"],
             "flags": (r.get("red_flags") or _empty_rf)["auto_avoid"] + (r.get("red_flags") or _empty_rf)["downgrade"]}
            for r in stock_results
            if (r.get("red_flags") or _empty_rf).get("has_critical")
            or (r.get("red_flags") or _empty_rf).get("downgrade_count", 0) >= 2
        ],
    }

    # 펀드 플로우 요약 첨부
    ff = portfolio.get("fund_flows", {})
    if ff.get("ok"):
        market_brain["fund_flows"] = {
            "rotation_signal": ff.get("rotation_signal"),
            "rotation_detail": ff.get("rotation_detail", {}).get("detail"),
            "equity_flow": ff.get("equity_flow_score"),
            "bond_flow": ff.get("bond_flow_score"),
            "safe_haven_flow": ff.get("safe_haven_flow_score"),
        }

    # CFTC COT 요약 첨부
    cot = portfolio.get("cftc_cot", {})
    if cot.get("ok"):
        market_brain["cftc_cot"] = {
            "report_date": cot.get("report_date"),
            "summary": cot.get("summary", {}),
            "sp500_net": cot.get("instruments", {}).get("SP500", {}).get("net_managed_money"),
            "gold_net": cot.get("instruments", {}).get("GOLD", {}).get("net_managed_money"),
        }

    # CNN Fear & Greed 요약 첨부
    mfg = portfolio.get("market_fear_greed", {})
    if mfg.get("ok"):
        market_brain["market_fear_greed"] = {
            "value": mfg.get("value"),
            "signal": mfg.get("signal"),
            "description_kr": mfg.get("description_kr"),
            "change_1d": mfg.get("change_1d"),
            "sub_indicators": mfg.get("sub_indicators", {}),
        }

    # 크립토 매크로 센서 요약 첨부
    crypto = portfolio.get("crypto_macro", {})
    if crypto.get("available"):
        market_brain["crypto_macro"] = {
            "composite": crypto.get("composite", {}),
            "fear_and_greed": crypto.get("fear_and_greed", {}).get("value"),
            "funding_rate_pct": crypto.get("funding_rate", {}).get("rate_pct"),
            "kimchi_premium_pct": crypto.get("kimchi_premium", {}).get("premium_pct"),
            "btc_nasdaq_corr": crypto.get("btc_nasdaq_corr", {}).get("correlation"),
            "stablecoin_mcap_b": crypto.get("stablecoin_mcap", {}).get("total_mcap_b"),
        }

    # V4: Bridgewater 경제 사이클 4분면 (이미 위에서 감지)
    market_brain["economic_quadrant"] = quadrant_info
    bw = _get_brain_weights(q_name)
    market_brain["brain_weights"] = {"fact": bw["fact"], "sentiment": bw["sentiment"], "quadrant": q_name}

    # V6: 레짐 감지 결과
    if regime_info:
        market_brain["regime"] = {
            "regime": regime_info.get("regime", "sideways"),
            "confidence": regime_info.get("confidence", 0),
            "method": regime_info.get("method", "unknown"),
        }

    # V6: IC 피드백 루프 상태
    ic_adj = _load_ic_adjustments()
    if ic_adj.get("status") == "ok" and ic_adj.get("log"):
        market_brain["ic_feedback"] = {
            "status": "active",
            "adjustments_count": len([
                v for v in ic_adj["adjustments"].values()
                if v.get("multiplier", 1.0) != 1.0
            ]),
            "log": ic_adj["log"][:10],
        }

    # V5: 버블 탐지 (Mackay/Shiller/Taleb)
    bubble = _detect_bubble_signals(portfolio)
    if bubble["detected"]:
        market_brain["bubble_warning"] = bubble

    result = {
        "macro_override": macro_ov,
        "market_brain": market_brain,
        "stocks": stock_results,
    }

    # V4.1: bond_regime 통합 — 채권 시장 신호로 최종 보정
    bond_regime = _load_bond_regime()
    if bond_regime.get("curve_shape") != "unknown":
        result = _apply_bond_regime(result, bond_regime)

    # V5.2: 만기일 + 프로그램 매매 구조 오버라이드
    result = _apply_market_structure_override(result, portfolio)

    # V5.3: CBOE 풋/콜 비율 시그널 반영
    result = _apply_cboe_pcr_override(result, portfolio)

    return result


def _count_grades(results: List[Dict[str, Any]]) -> Dict[str, int]:
    dist = {g: 0 for g in GRADE_ORDER}
    for r in results:
        g = r.get("grade", "AVOID")
        dist[g] = dist.get(g, 0) + 1
    return dist
