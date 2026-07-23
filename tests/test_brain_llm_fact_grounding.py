"""2026-07-23 RULE 7(PM 승인) — Brain fact_score 의 LLM 정성점수 grounding/정직화 검증.

배경: Brain 핵심소스 무결성 감사(origin/main 재실행) — fact_score(Brain 이 '실측'으로 신뢰하는 버킷)에
Gemini/Perplexity 가 생성한 0~100 주관 판단이 grounding 없이 주입(할루시네이션). 5 컴포넌트 유효가중 ~26%.
방향(PM 승인): ① brief_verdict(LLM 자기 투자결론) = 관측 전용(순환 echo 차단) ② analyst_report = report_count
N-guard 수축(단일 리포트 극단 차단) ③ moat 개수 스케일 = presence-only(verbosity 보상 제거) ④ risk_level
부재 = 중립(호재 아님) ⑤ LLM read provenance tag. 신호를 버리지 않고 정직 카테고리+confidence 로 재배치.
"""
from __future__ import annotations

from api.intelligence.verity_brain import _compute_fact_score
from api.intelligence.factors.moat import _compute_moat_score
from api.intelligence.perplexity_realtime import _extract_risk_level


def _stock(**over):
    s = {
        "ticker": "T",
        "multi_factor": {"multi_score": 60},
        "consensus": {"consensus_score": 55},
        "prediction": {"up_probability": 60},
        "backtest": {},
        "timing": {"timing_score": 50},
        "per": 12.0, "pbr": 1.5, "roe": 0.15, "debt_ratio": 50.0,
        "operating_margin": 10.0, "revenue_growth": 18.0,
    }
    s.update(over)
    return s


# ── ① analyst_report N-guard 수축 (Bühlmann Z=n/(n+2), 단일 리포트 극단 차단) ──

def test_analyst_single_report_extreme_shrinks_toward_neutral():
    # report_count=1 에 sentiment 95 (LG 003550 실사례) → 중립(50) 방향 수축, raw 95 그대로 통과 X.
    fs = _compute_fact_score(_stock(
        analyst_report_summary={"analyst_sentiment_score": 95.0, "report_count": 1}
    ), portfolio={})
    ar = fs["components"]["analyst_report"]
    # 50 + (95-50)*(1/3) = 65.0
    assert 64.0 <= ar <= 66.0, ar
    assert ar < 95.0  # 극단값 그대로 통과 금지


def test_analyst_more_reports_less_shrink():
    one = _compute_fact_score(_stock(
        analyst_report_summary={"analyst_sentiment_score": 90.0, "report_count": 1}
    ), portfolio={})["components"]["analyst_report"]
    five = _compute_fact_score(_stock(
        analyst_report_summary={"analyst_sentiment_score": 90.0, "report_count": 5}
    ), portfolio={})["components"]["analyst_report"]
    # 리포트 많을수록 raw(90)에 근접 (수축 약화)
    assert five > one
    assert five < 90.0


def test_analyst_downside_extreme_also_shrinks():
    # 대칭성: 단일 리포트 극단 하락(20)도 중립 방향 수축 (편향 없음).
    ar = _compute_fact_score(_stock(
        analyst_report_summary={"analyst_sentiment_score": 20.0, "report_count": 1}
    ), portfolio={})["components"]["analyst_report"]
    # 50 + (20-50)*(1/3) = 40.0
    assert 39.0 <= ar <= 41.0, ar


def test_analyst_no_report_count_uses_raw():
    # report_count 부재 시 수축 미적용(raw 유지) — 결측 종목 왜곡 방지.
    ar = _compute_fact_score(_stock(
        analyst_report_summary={"analyst_sentiment_score": 80.0}
    ), portfolio={})["components"]["analyst_report"]
    assert 79.0 <= ar <= 81.0, ar


# ── ② brief_verdict = 관측 전용 (fact 점수 제외, 순환 echo 차단) ──

def test_brief_verdict_not_in_scored_components():
    fs = _compute_fact_score(_stock(
        equity_research_brief={"brief_verdict": "STRONG_BUY"}
    ), portfolio={})
    assert "equity_brief_verdict" not in fs["components"]
    assert "equity_brief_verdict" not in fs["missing_components"]


def test_brief_verdict_exposed_as_observation():
    fs = _compute_fact_score(_stock(
        equity_research_brief={"brief_verdict": "STRONG_AVOID"}
    ), portfolio={})
    assert fs["llm_observations"]["equity_brief_verdict"] == "STRONG_AVOID"


def test_brief_verdict_does_not_move_score():
    # 순환 차단 핵심: LLM 투자결론(STRONG_BUY vs STRONG_AVOID)이 fact_score 를 움직이면 안 됨.
    buy = _compute_fact_score(_stock(
        equity_research_brief={"brief_verdict": "STRONG_BUY"}
    ), portfolio={})["score"]
    avoid = _compute_fact_score(_stock(
        equity_research_brief={"brief_verdict": "STRONG_AVOID"}
    ), portfolio={})["score"]
    assert buy == avoid


# ── ③ moat 개수 스케일 → presence-only (verbosity 보상 제거) ──

def test_moat_presence_only_no_count_scaling():
    one = _compute_moat_score(_stock(
        dart_business_analysis={"moat_indicators": ["특허"]}
    ))
    many = _compute_moat_score(_stock(
        dart_business_analysis={"moat_indicators": ["a", "b", "c", "d", "e"]}
    ))
    # 개수 보너스 동일 (5개 나열해도 1개와 존재 보너스 같음). 키워드 매칭은 별개라 '특허' 케이스와 직접비교 X —
    # 순수 개수 스케일 제거 검증 위해 키워드 없는 나열끼리: 존재 보너스만 = 동일.
    generic_one = _compute_moat_score(_stock(dart_business_analysis={"moat_indicators": ["x"]}))
    generic_many = _compute_moat_score(_stock(dart_business_analysis={"moat_indicators": ["x", "y", "z", "w"]}))
    assert generic_one == generic_many


# ── ④ risk_level 부재 → UNKNOWN (호재 아님) ──

def test_risk_level_absent_returns_unknown():
    assert _extract_risk_level("리스크 등급 언급 없는 일반 텍스트") == "UNKNOWN"


def test_risk_level_detected_when_present():
    assert _extract_risk_level("This stock has HIGH regulatory risk") == "HIGH"


def test_unknown_risk_is_missing_not_positive():
    # UNKNOWN → _RISK_SCORE_MAP 밖 → perplexity_risk 결측(중립), coverage 차감. 60 호재 주입 X.
    fs = _compute_fact_score(_stock(
        external_risk={"risk_level": "UNKNOWN"}
    ), portfolio={})
    assert "perplexity_risk" in fs["missing_components"]


# ── ⑤ LLM read provenance tag ──

def test_llm_derived_components_tagged():
    fs = _compute_fact_score(_stock(
        analyst_report_summary={"analyst_sentiment_score": 70.0, "report_count": 2},
        dart_business_analysis={"business_health_score": 60},
    ), portfolio={})
    tagged = set(fs["llm_derived_components"])
    assert "analyst_report" in tagged
    assert "dart_health" in tagged
