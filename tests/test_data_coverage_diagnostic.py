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
    """🚨 2026-08-16 베이스라인 v1.0 — 가중 있는 컴포넌트로 교체.

    종전 이 테스트는 analyst_report·dart_health·perplexity_risk 를 채워 coverage 상승을
    확인했다. 그 3종은 v1.0 에서 **가중 0**(LLM 파생 → D군 분리)이라 채워도 coverage 가
    변하지 않는다 — 테스트가 옛 구성을 전제하고 있었다.
    coverage 는 "가중 있는 컴포넌트 중 실측 보유 비율" 이므로, 가중 있는 것으로 재작성한다.
    """
    from api.intelligence.factors.fact import _load_constitution
    w = (_load_constitution().get("fact_score") or {}).get("weights") or {}
    assert w, "헌법 가중 로드 실패"
    # 가중 있는 컴포넌트만 결측시켜 coverage 하락을 확인 (us_fscore 는 v1.0 에서 가중 0)
    base = _compute_fact_score(_stock(), portfolio={})["data_coverage"]
    assert 0.0 <= base <= 1.0
    # multi_factor 는 동결(×0.0)이라 quant 서브팩터가 없으면 quant_* 컴포넌트 자체가 붙지 않는다
    rich = _compute_fact_score(_stock(
        multi_factor={"multi_score": 60,
                      "quant_factors": {"quality": 70, "volatility": 65,
                                        "momentum": 50, "mean_reversion": 50}},
        quant_factors={
            "quality": {
                "quality_score": 70,
                "piotroski_f": 7,
                "piotroski_measurable": 9,
                "gross_profitability": 0.25,
                "altman": {"z_score": 3.0, "applicable": True},
                "unmeasured_axes": [],
            },
            "volatility": {"volatility_score": 65, "unmeasured_axes": []},
        },
        operating_cashflow=100,
        net_income=80,
    ), portfolio={})
    assert "quant_quality" in rich["components"], "퀀트 퀄리티가 채점 컴포넌트로 부착돼야 한다"
    assert "quant_volatility" in rich["components"]
    assert rich["data_coverage"] >= base


def test_coverage_is_diagnostic_not_scoring():
    """동일 입력 → 동일 점수 (data_coverage 는 점수에 영향 없는 진단 필드)."""
    s = _stock()
    a = _compute_fact_score(s, portfolio={})
    b = _compute_fact_score(s, portfolio={})
    assert a["score"] == b["score"]


def test_coverage_provenance_changes_metadata_not_score():
    """동일한 채점 컴포넌트에 원입력 provenance만 추가해도 점수는 불변이다."""
    base = _stock(
        multi_factor={"multi_score": 60, "quant_factors": {
            "quality": 70, "volatility": 65, "momentum": 50, "mean_reversion": 50,
        }},
    )
    plain = _compute_fact_score(base, portfolio={})
    enriched = dict(base)
    enriched.update({
        "quant_factors": {
            "quality": {
                "quality_score": 70, "piotroski_f": 7, "piotroski_measurable": 9,
                "gross_profitability": 0.25,
                "altman": {"z_score": 3.0, "applicable": True},
            },
            "volatility": {"volatility_score": 65, "unmeasured_axes": []},
        },
        "operating_cashflow": 100,
        "net_income": 80,
    })
    measured = _compute_fact_score(enriched, portfolio={})
    assert measured["score"] == plain["score"]
    assert measured["data_coverage"] > plain["data_coverage"]


def test_volatility_fallback_without_provenance_is_not_counted_as_measured():
    out = _compute_fact_score(_stock(
        multi_factor={"multi_score": 60, "quant_factors": {
            "quality": 50, "volatility": 50, "momentum": 50, "mean_reversion": 50,
        }},
        quant_factors={"volatility": {"volatility_score": 50, "signals": []}},
    ), portfolio={})
    measurement = out["coverage_scope"]["axis_measurement"]["quant_volatility"]
    assert measurement["coverage"] == 0.0
    assert "quant_volatility" in out["missing_components"]


def test_us_fscore_component():
    """2026-05-20 US Piotroski F-Score brain 컴포넌트 (RULE 7 승인, 3%)."""
    fs_no = _compute_fact_score(_stock(), portfolio={})
    assert fs_no["components"]["us_fscore"] == 50.0  # 부재 → neutral
    assert "us_fscore" in fs_no["missing_components"]
    fs_yes = _compute_fact_score(_stock(us_fscore=8), portfolio={})
    assert fs_yes["components"]["us_fscore"] == round(8 / 9 * 100, 1)  # 88.9
    assert fs_yes["score"] >= fs_no["score"]  # 높은 F-Score → fact_score ↑
