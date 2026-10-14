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


def test_neutral_pbr_is_a_substitute_and_never_measured():
    base = _stock(pbr=1.0, pbr_normalized_neutral=True)
    neutral = _compute_fact_score(base, portfolio={})
    absent = _compute_fact_score({**base, "pbr": None}, portfolio={})
    measured = neutral["coverage_scope"]["axis_measurement"]["graham_value"]
    assert measured["inputs"]["pbr"] == {
        "state": "substituted", "reason": "neutral_pbr_normalization",
    }
    assert neutral["data_coverage"] == absent["data_coverage"]
    assert neutral["score"] == absent["score"]
    assert neutral["components"] == absent["components"]
    assert neutral["weights_effective"] == absent["weights_effective"]


def test_brain_preserves_zero_coverage_on_empty_input():
    from api.intelligence.verity_brain import analyze_stock
    out = analyze_stock({"ticker": "EMPTY"}, portfolio={})
    assert out["fact_score"]["data_coverage"] == 0.0
    assert out["data_coverage"] == 0.0
    definition = out["fact_score"]["coverage_scope"]["grade_confidence_definition"]
    assert definition["method"] == "distance_to_grade_boundaries"
    assert definition["is_statistical_confidence"] is False


def test_existing_growth_and_strength_proxies_are_substitutes():
    out = _compute_fact_score(_stock(
        eps_quarterly_growth=None, drop_from_high_pct=-8.0,
        consensus={"consensus_score": 55, "operating_profit_yoy_est_pct": 20.0},
    ), portfolio={})
    axes = out["coverage_scope"]["axis_measurement"]
    assert axes["graham_value"]["inputs"]["eps_growth"]["state"] == "substituted"
    assert axes["canslim_growth"]["inputs"]["annual_growth"]["state"] == "substituted"
    assert axes["canslim_growth"]["inputs"]["relative_strength"]["state"] == "substituted"


def test_us_only_input_has_explicit_applicability_and_denominator():
    kr = _compute_fact_score(_stock(currency="KRW"), portfolio={})
    us = _compute_fact_score(_stock(currency="USD"), portfolio={})
    kr_axis = kr["coverage_scope"]["axis_measurement"]["canslim_growth"]
    us_axis = us["coverage_scope"]["axis_measurement"]["canslim_growth"]
    assert kr_axis["inputs"]["institutional_change"]["state"] == "not_applicable"
    assert kr_axis["input_count"] == 4
    assert us_axis["inputs"]["institutional_change"]["state"] == "missing"
    assert us_axis["input_count"] == 5
    assert kr["coverage_scope"]["component_states"]["us_fscore"] == "not_applicable"


def test_fscore_zero_measurable_count_is_not_promoted_to_nine():
    for count in (None, 0):
        quality = {"piotroski_f": 0}
        if count is not None:
            quality["piotroski_measurable"] = count
        out = _compute_fact_score(_stock(
            multi_factor={"quant_factors": {"quality": 50}},
            quant_factors={"quality": quality},
        ), portfolio={})
        part = out["coverage_scope"]["axis_measurement"]["quant_quality"]
        assert part["inputs"]["piotroski_f"]["state"] == "missing"
        assert part["inputs"]["piotroski_f"]["measured_fraction"] == 0.0


def test_financial_exclusions_are_not_missing_measurements():
    out = _compute_fact_score(_stock(
        multi_factor={"quant_factors": {"quality": 50}},
        quant_factors={"quality": {
            "piotroski_f": -1, "piotroski_measurable": 0,
            "altman": {"applicable": False, "model_variant": "excluded_financial"},
        }},
    ), portfolio={})
    inputs = out["coverage_scope"]["axis_measurement"]["quant_quality"]["inputs"]
    assert inputs["piotroski_f"]["state"] == "not_applicable"
    assert inputs["altman_z"]["state"] == "not_applicable"


def test_zero_cashflow_and_zero_income_are_observed_values():
    out = _compute_fact_score(_stock(
        multi_factor={"quant_factors": {"quality": 50}},
        quant_factors={"quality": {}},
        dart_financials={"cashflow": {"operating_cashflow": 0}}, net_income=0,
    ), portfolio={})
    inputs = out["coverage_scope"]["axis_measurement"]["quant_quality"]["inputs"]
    assert inputs["earning_quality"]["state"] == "measured"


def test_nonfinite_or_boolean_values_are_not_measured_inputs():
    for invalid in (float("inf"), float("nan"), True):
        out = _compute_fact_score(_stock(per=invalid), portfolio={})
        inputs = out["coverage_scope"]["axis_measurement"]["graham_value"]["inputs"]
        assert inputs["per"]["state"] == "missing"


def test_fixed_market_volatility_is_a_substitute_with_unchanged_score():
    base = _stock(multi_factor={"quant_factors": {"volatility": 65}})
    plain = _compute_fact_score(base, portfolio={})
    documented = _compute_fact_score({**base, "quant_factors": {
        "volatility": {"volatility_score": 65, "unmeasured_axes": []},
    }}, portfolio={})
    axis = documented["coverage_scope"]["axis_measurement"]["quant_volatility"]
    assert axis["inputs"]["idiosyncratic"]["state"] == "substituted"
    assert axis["coverage"] == 0.85
    assert plain["score"] == documented["score"]
    assert plain["components"] == documented["components"]


def test_graham_diagnostic_ignores_financial_objects_from_other_market():
    for currency, foreign in (
        ("KRW", {"sec_financials": {"pe_ratio": 12, "price_to_book": 1.2, "current_ratio": 200}}),
        ("USD", {"kis_financial_ratio": {"source": "kis", "per": 12, "pbr": 1.2, "current_ratio": 200}}),
    ):
        out = _compute_fact_score({"currency": currency, **foreign}, portfolio={})
        inputs = out["coverage_scope"]["axis_measurement"]["graham_value"]["inputs"]
        for key in ("per", "pbr", "current_ratio"):
            assert inputs[key]["state"] == "missing"


def test_graham_diagnostic_does_not_skip_unusable_selected_input_for_alias():
    out = _compute_fact_score(_stock(
        per="N/A", price_to_earnings=12, pbr="N/A", price_to_book=1.2,
        eps_quarterly_growth="N/A",
        consensus={"operating_profit_yoy_est_pct": 20},
    ), portfolio={})
    inputs = out["coverage_scope"]["axis_measurement"]["graham_value"]["inputs"]
    for key in ("per", "pbr", "eps_growth"):
        assert inputs[key]["state"] == "missing"


def test_kis_selected_object_does_not_use_ignored_top_level_financials():
    out = _compute_fact_score(_stock(
        currency="KRW", kis_financial_ratio={"source": "kis"},
        debt_ratio=25, roe=18,
    ), portfolio={})
    inputs = out["coverage_scope"]["axis_measurement"]["graham_value"]["inputs"]
    assert inputs["debt_ratio"]["state"] == "missing"
    assert inputs["roe"]["state"] == "missing"


def test_vendor_missing_defaults_are_not_observed_zeros_and_scores_stay_equal():
    base = _stock(currency="KRW", debt_ratio=0, roe=0, operating_margin=0,
                  multi_factor={"quant_factors": {"quality": 50}}, quant_factors={"quality": {}})
    observed = _compute_fact_score(base, portfolio={})
    missing = _compute_fact_score({**base, "fundamental_missing_fields": [
        "debt_ratio", "roe", "operating_margin",
    ]}, portfolio={})
    for field in ("debt_ratio", "roe"):
        a = observed["coverage_scope"]["axis_measurement"]["graham_value"]["inputs"][field]
        b = missing["coverage_scope"]["axis_measurement"]["graham_value"]["inputs"][field]
        assert a["state"] == "measured"
        assert b == {"state": "missing", "reason": "source_missing_default_0"}
    assert missing["coverage_scope"]["axis_measurement"]["quant_quality"]["inputs"]["stability"]["state"] == "missing"
    assert missing["data_coverage"] < observed["data_coverage"]
    assert missing["score"] == observed["score"]
    assert missing["components"] == observed["components"]
    assert missing["weights_effective"] == observed["weights_effective"]


def test_top_level_missing_flags_do_not_mask_selected_sec_or_kis_source():
    for currency, selected in (
        ("USD", {"sec_financials": {"debt_ratio": 25, "roe": 18}}),
        ("KRW", {"kis_financial_ratio": {"source": "kis", "debt_ratio": 25, "roe": 18}}),
    ):
        out = _compute_fact_score(_stock(currency=currency, debt_ratio=0, roe=0,
            fundamental_missing_fields=["debt_ratio", "roe"], **selected), portfolio={})
        inputs = out["coverage_scope"]["axis_measurement"]["graham_value"]["inputs"]
        assert inputs["debt_ratio"]["state"] == "measured"
        assert inputs["roe"]["state"] == "measured"


def test_stock_collector_source_flags_preserve_existing_records(monkeypatch):
    from unittest.mock import Mock
    import pandas as pd
    from api.collectors import stock_data
    history = pd.DataFrame({"Close": [10.0] * 25, "High": [11.0] * 25,
                            "Low": [9.0] * 25, "Volume": [100] * 25},
                           index=pd.date_range("2026-09-01", periods=25))
    vendor = Mock()
    vendor.history.return_value = history
    vendor.info = {"marketCap": 1000000, "currency": "USD"}
    monkeypatch.setattr(stock_data.yf, "Ticker", lambda ticker: vendor)
    monkeypatch.setattr("api.collectors.yfinance_safe.safe_yf_call", lambda fn, **kwargs: fn())
    missing = stock_data.get_stock_data("TEST")
    assert missing["fundamental_missing_fields"] == ["debt_ratio", "roe", "operating_margin"]
    vendor.info.update(debtToEquity=0, returnOnEquity=0, operatingMargins=0)
    observed = stock_data.get_stock_data("TEST")
    assert observed["fundamental_missing_fields"] == []
    assert {k: v for k, v in missing.items() if k != "fundamental_missing_fields"} == {
        k: v for k, v in observed.items() if k != "fundamental_missing_fields"
    }
