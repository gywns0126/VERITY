"""
멀티팩터 통합 점수 엔진 v3 (Quant Enhancement)
- 기존 5팩터 + 학술 퀀트 4팩터 = 9팩터 체제
- 매크로 국면에 따른 동적 가중치
- 퀀트 팩터: 모멘텀, 퀄리티, 변동성, 평균회귀
- 신호 중복 제거 + 퀀트 시그널 통합
"""
from typing import Any, Dict, List, Optional


# ── 기존 5팩터 가중치 (합 = 0.70) ──
# 나머지 0.30은 퀀트 4팩터에 배분

# ── #42 배분 재설계 (2026-08-09, PM 승인 · docs/PREREG_42_WEIGHT_REALLOCATION_2026_08_09.md) ──
# 근거 = 2026-08-08 백테스트(리밸런스 75 · 관측 186,340 · PBO 0.0001 · 임계 |t|>=2.73):
#   volatility 통과(t 4.96/6.52) · quality 부분통과(F-Score8 t 4.95/3.57)
#   **technical 신호 0(t -1.23/-0.01) · momentum 신호 0(t -0.69/-0.09)**
# 변경 = 신호 0 판정 2축을 **50%** 로 감축, 감축분은 나머지 7축에 현행 비율 pro-rata.
#   · 50% 는 자의적 단일 선택이다(완전 제거는 검정력상 과하고, 유지는 측정과 배치).
#     **재조정하지 않는다** — RULE 7 "1회만" 정신.
#   · pro-rata 재분배는 추가 가정 0(손대지 않은 축의 상대 순서 불변). 통과축 집중(대안)은
#     volatility 단일 팩터 베팅이 되어 #45 미장 검증 전에는 이르다고 판단해 채택하지 않았다.
#   · mean_reversion 은 "불통과" 이지 "신호 0" 이 아니라 손대지 않는다(상쇄 문제는 #43 소관).
# 🚨 적용 전 실측(운영 풀 40종): multi_score 중앙 55.06->56.62 · **Δbrain 중앙 +0.16점** ·
#   등급 변경 3/40 · Spearman 0.9334. **실효는 작다** — multi_factor 가 최종 점수의 12.75%
#   이기 때문이다. 그럼에도 적용하는 이유 = 근거와 배분이 어긋난 상태를 남기지 않기 위함.
# ── 2026-08-15 구조 재편 (PREREG_FORMULA_RESTRUCTURE_2026_08_15, RULE 7 1회·PM 승인) ──
# macro 축 제거 — 시장 레벨(전 종목 공통)이라 횡단면 순위 기여가 산술적으로 0
# (115일 실측: 88/115일 고유값 ≤2, 나머지는 장중 갱신 혼합. Perplexity Q2 정합).
# 🚨 macro 의 역할은 사라진 게 아니라 자리만 정리됐다: ① regime 선택자(아래
# _get_dynamic_weights 의 risk_off/on 분기)로 계속 벡터를 고른다 ② 사이징은
# macro_multiplier(B-continuous) ③ 캡은 panic_stages. breakdown 에는 macro 점수 계속
# 표기(가중 0 → 기여 0). 구 벡터 = ÷(1−macro가중) 재정규화, 잔차는 최대 축 흡수.
# #42 조정 비율(momentum/technical 절반) 보존: 구 macro 가중 = BASE .1422 /
# RISK_OFF .1874 / RISK_ON .0872. 복원은 prereg rollback 절차로만.
BASE_WEIGHTS = {
    "fundamental": 0.2487,   # <- 0.2133 ÷ 0.8578
    "technical": 0.0991,     # #42 절반 유지 (<- 0.17 신호 0)
    "sentiment": 0.1381,
    "flow": 0.1795,
    "momentum": 0.0583,      # #42 절반 유지 (<- 0.10 신호 0)
    "quality": 0.1105,
    "volatility": 0.0829,
    "mean_reversion": 0.0829,
}

# #42 동일 규칙 적용. regime 이 바뀐다고 없던 정보가 생기지 않는다.
RISK_OFF_WEIGHTS = {
    "fundamental": 0.2717,   # <- 0.2207 ÷ 0.8126
    "technical": 0.0738,
    "sentiment": 0.0813,
    "flow": 0.1356,
    "momentum": 0.0308,
    "quality": 0.1899,
    "volatility": 0.1356,
    "mean_reversion": 0.0813,
}

# #42 동일 규칙. 🚨 RISK_ON 은 technical 이 큰 벡터라 신호 0 축 확대 방지 유지.
RISK_ON_WEIGHTS = {
    "fundamental": 0.1912,   # <- 0.1745 ÷ 0.9128
    "technical": 0.0986,
    "sentiment": 0.1365,
    "flow": 0.2184,
    "momentum": 0.0822,
    "quality": 0.0683,
    "volatility": 0.0683,
    "mean_reversion": 0.1365,
}


# ── V7: bond_regime 기반 rate-environment 곱셈 보정 (Druckenmiller) ──
# 명제: "Liquidity > Earnings (intermediate term)" — 단 시대 의존적.
# 2008~2021 QE 시대엔 liquidity 우위, 2022~ QT 전환 후엔 earnings 우위.
# bond_regime.rate_environment 따라 동적 우위 전환.
#
# 매핑:
#   rate_low_accommodative (QE)  → macro/flow/momentum ↑, fundamental ↓ (liquidity 시각)
#   rate_normal                  → 중립 (multiplier 1.0)
#   rate_elevated (QT 시작)      → fundamental/quality ↑, macro/momentum ↓ (earnings 시각)
#   rate_high_restrictive (QT 강)→ fundamental/quality 더 ↑, momentum 더 ↓
#
# 하이브리드 구조: macro_score(mood) 기반 BASE/RISK_OFF/RISK_ON 위에 곱셈 보정 → 정규화.
RATE_ENV_MULTIPLIERS: Dict[str, Dict[str, float]] = {
    "rate_low_accommodative": {
        "macro":       1.35,
        "flow":        1.25,
        "momentum":    1.15,
        "fundamental": 0.80,
        "quality":     0.85,
    },
    "rate_normal": {},  # 모든 팩터 1.0 (중립)
    "rate_elevated": {
        "fundamental": 1.20,
        "quality":     1.20,
        "volatility":  1.10,
        "macro":       0.85,
        "momentum":    0.90,
    },
    "rate_high_restrictive": {
        "fundamental": 1.35,
        "quality":     1.35,
        "volatility":  1.20,
        "macro":       0.70,
        "momentum":    0.75,
        "flow":        0.85,
    },
}


def _get_dynamic_weights(
    macro_score: int,
    ff_factors: Optional[Dict[str, float]] = None,
    bond_regime: Optional[Dict[str, Any]] = None,
) -> Dict[str, float]:
    """매크로 점수에 따라 가중치 동적 조정.

    레이어:
      1. macro_score(mood) 기반 BASE/RISK_OFF/RISK_ON 선택
      2. bond_regime.rate_environment 곱셈 보정 (Druckenmiller — 시대 변화 가드)
      3. Fama-French SMB/HML 미세 보정
      4. 합 1.0 으로 정규화
    """
    if macro_score <= 35:
        w = dict(RISK_OFF_WEIGHTS)
    elif macro_score >= 65:
        w = dict(RISK_ON_WEIGHTS)
    else:
        w = dict(BASE_WEIGHTS)

    # bond_regime 곱셈 보정 — Druckenmiller "regime-dependent liquidity vs earnings"
    if bond_regime:
        rate_env = bond_regime.get("rate_environment", "unknown")
        mult = RATE_ENV_MULTIPLIERS.get(rate_env, {})
        for k, m in mult.items():
            if k in w:
                w[k] = w[k] * m

    if ff_factors:
        smb = ff_factors.get("SMB", 0)
        hml = ff_factors.get("HML", 0)
        if smb > 0.05:
            w["momentum"] = w.get("momentum", 0.10) * 1.05
        elif smb < -0.05:
            w["quality"] = w.get("quality", 0.08) * 1.05
        if hml > 0.05:
            w["fundamental"] = w.get("fundamental", 0.18) * 1.05
        elif hml < -0.05:
            w["momentum"] = w.get("momentum", 0.10) * 1.05

    # 정규화 — bond_regime / ff_factors 보정 후 합 1.0 으로
    total = sum(w.values())
    if total > 0:
        w = {k: round(v / total, 4) for k, v in w.items()}

    return w


def _deduplicate_signals(signals: list) -> list:
    """신호 중복 제거 (순서 유지), 비문자열 필터"""
    seen = set()
    result = []
    for s in signals:
        if not isinstance(s, str):
            continue
        key = s.split("(")[0].strip()
        if key not in seen:
            seen.add(key)
            result.append(s)
    return result


def compute_multi_factor_score(
    fundamental_score: int,
    technical: Dict,
    sentiment: Dict,
    flow: Dict,
    macro_mood: Dict,
    quant_factors: Optional[Dict[str, Any]] = None,
    social_sentiment: Optional[Dict[str, Any]] = None,
    bond_regime: Optional[Dict[str, Any]] = None,
) -> Dict:
    """
    9개 팩터를 동적 가중 합산하여 멀티팩터 점수 산출 (0~100)

    기존 5팩터: fundamental, technical, sentiment, flow, macro
    퀀트 4팩터: momentum, quality, volatility, mean_reversion
    """
    # 측정 정화 (2026-08-03): 엔진이 "데이터 부재" 로 None 을 반환하면 중립 50 대입
    # (2026-05-20 확정 설계 — 결측 = 중립 imputation). 종전 .get(key, 50) 은 키가 있고
    # 값이 None 이면 None 을 통과시켜 합산에서 TypeError 가 나거나, 0-채움 가짜 점수
    # (quality 6/100)가 실측처럼 유입됐다.
    def _neutral(d: Optional[Dict], key: str) -> float:
        v = (d or {}).get(key)
        return v if isinstance(v, (int, float)) else 50

    tech_score = _neutral(technical, "technical_score")
    news_score = sentiment.get("score", 50)
    social = social_sentiment or {}
    social_score = social.get("score", 50) if social else 50
    sent_score = round(news_score * 0.6 + social_score * 0.4) if social else news_score
    flow_score = _neutral(flow, "flow_score")
    macro_score = macro_mood.get("score", 50)

    qf = quant_factors or {}
    momentum_score = _neutral(qf.get("momentum"), "momentum_score")
    quality_score = _neutral(qf.get("quality"), "quality_score")
    volatility_score = _neutral(qf.get("volatility"), "volatility_score")
    mr_score = _neutral(qf.get("mean_reversion"), "mean_reversion_score")
    quality_data_missing = (qf.get("quality") or {}).get("applicable") is False

    weights = _get_dynamic_weights(macro_score, bond_regime=bond_regime)
    regime = "risk_off" if macro_score <= 35 else "risk_on" if macro_score >= 65 else "neutral"
    rate_env = (bond_regime or {}).get("rate_environment", "unknown") if bond_regime else "unknown"

    breakdown = {
        "fundamental": fundamental_score,
        "technical": tech_score,
        "sentiment": sent_score,
        "flow": flow_score,
        "macro": macro_score,
        "momentum": momentum_score,
        "quality": quality_score,
        "volatility": volatility_score,
        "mean_reversion": mr_score,
    }

    multi = sum(breakdown[k] * weights.get(k, 0) for k in breakdown)
    multi = round(max(0, min(100, multi)))

    if multi >= 75:
        grade = "강력 매수"
    elif multi >= 60:
        grade = "매수"
    elif multi >= 45:
        grade = "관망"
    elif multi >= 30:
        grade = "주의"
    else:
        grade = "회피"

    all_signals: List[str] = []
    all_signals.extend(technical.get("signals", []))
    all_signals.extend(flow.get("flow_signals", []))

    if sent_score >= 70:
        all_signals.append("뉴스 긍정적")
    elif sent_score <= 30:
        all_signals.append("뉴스 부정적")
    if macro_score >= 65:
        all_signals.append("매크로 낙관")
    elif macro_score <= 35:
        all_signals.append("매크로 비관")

    if quality_data_missing:
        # 정직 신호 — 6/100 같은 가짜 실측 대신 "미산출 · 중립 대입" 을 명시 (측정 정화 2026-08-03)
        all_signals.append("퀄리티 미산출 — 재무 데이터 부재 (중립 50 대입)")

    for factor_key in ["momentum", "quality", "volatility", "mean_reversion"]:
        factor_data = qf.get(factor_key, {})
        for sig in (factor_data or {}).get("signals", []):
            all_signals.append(sig)

    all_signals = _deduplicate_signals(all_signals)

    contribution = {
        k: round(breakdown[k] * weights.get(k, 0), 1) for k in breakdown
    }

    quant_sub = {
        "momentum": momentum_score,
        "quality": quality_score,
        "volatility": volatility_score,
        "mean_reversion": mr_score,
    }

    return {
        "multi_score": multi,
        "grade": grade,
        "regime": regime,
        "rate_environment": rate_env,
        "weights_used": {k: round(v, 2) for k, v in weights.items()},
        "factor_breakdown": breakdown,
        "factor_contribution": contribution,
        "quant_factors": quant_sub,
        "all_signals": all_signals,
    }
