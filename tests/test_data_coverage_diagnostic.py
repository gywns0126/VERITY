"""2026-05-20 — fact_score data_coverage 진단 필드 검증.

PM 승인 의제 "결측 컴포넌트 50 fallback 제외+재정규화" → 수학적 no-op 입증 (imputation ≡
제외+재정규화+coverage deflate). 점수는 미변경, data_coverage 는 저점수가 (데이터 부재) vs
(약신호) 인지 구분하는 진단 필드로만 노출.
"""
from __future__ import annotations

from api.intelligence.verity_brain import _compute_fact_score


def _stock(**over):
    s = {
        "ticker": "T",
        "multi_factor": {"multi_score": 60},
        "consensus": {"consensus_score": 55},
        "prediction": {"up_probability": 60},
        "backtest": {},
        "timing": {"timing_score": 50},
        "commodity_margin": {},
        "per": 12.0, "pbr": 1.5, "roe": 0.15, "debt_ratio": 50.0,
        "operating_margin": 10.0, "revenue_growth": 18.0,
    }
    s.update(over)
    return s


def test_data_coverage_field_present():
    fs = _compute_fact_score(_stock(), portfolio={})
    assert 0.0 <= fs["data_coverage"] <= 1.0
    assert isinstance(fs["missing_components"], list)


def test_missing_lists_absent_components():
    m = set(_compute_fact_score(_stock(), portfolio={})["missing_components"])
    assert "backtest" in m            # backtest={} → total_trades 0
    assert "analyst_report" in m      # analyst_report_summary 부재
    assert "dart_health" in m         # dart_business_analysis 부재
    assert "perplexity_risk" in m     # external_risk 부재
    assert "consensus" not in m       # consensus_score=55 존재


def test_higher_coverage_when_more_data():
    low = _compute_fact_score(_stock(), portfolio={})["data_coverage"]
    high = _compute_fact_score(_stock(
        analyst_report_summary={"analyst_sentiment_score": 70},
        dart_business_analysis={"business_health_score": 60},
        external_risk={"risk_level": "LOW"},
    ), portfolio={})["data_coverage"]
    assert high > low


def test_coverage_is_diagnostic_not_scoring():
    """동일 입력 → 동일 점수 (data_coverage 는 점수에 영향 없는 진단 필드)."""
    s = _stock()
    a = _compute_fact_score(s, portfolio={})
    b = _compute_fact_score(s, portfolio={})
    assert a["score"] == b["score"]


def test_us_fscore_component():
    """2026-05-20 US Piotroski F-Score brain 컴포넌트 (RULE 7 승인, 3%)."""
    fs_no = _compute_fact_score(_stock(), portfolio={})
    assert fs_no["components"]["us_fscore"] == 50.0  # 부재 → neutral
    assert "us_fscore" in fs_no["missing_components"]
    fs_yes = _compute_fact_score(_stock(us_fscore=8), portfolio={})
    assert fs_yes["components"]["us_fscore"] == round(8 / 9 * 100, 1)  # 88.9
    assert fs_yes["score"] >= fs_no["score"]  # 높은 F-Score → fact_score ↑
