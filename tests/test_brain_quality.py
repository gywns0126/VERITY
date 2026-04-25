"""Brain 시스템 품질 정량 추적 검증.

대상:
  - api/analyzers/gemini_analyst._fallback_periodic: Gemini 429 fallback 시에도
    brain_accuracy / meta_analysis 등 정량 데이터 보존
  - api/main._compute_brain_quality: 등급별 적중률·수익률 → 0~100 종합 점수
"""
import pytest


# ──────────────────────────────────────────────
# 1. _fallback_periodic — 정량 데이터 보존
# ──────────────────────────────────────────────

def test_fallback_periodic_preserves_brain_accuracy():
    """Gemini 호출 실패해도 brain_accuracy 정량 데이터는 그대로 유지돼야."""
    from api.analyzers.gemini_analyst import _fallback_periodic
    sample_brain = {
        "grades": {
            "STRONG_BUY": {"count": 5, "hit_rate": 80, "avg_return": 12.5},
            "AVOID": {"count": 3, "hit_rate": 0, "avg_return": -8.0},
        },
        "insight": "Brain STRONG_BUY 정확도 80%, AVOID 회피 평균 -8%",
    }
    data = {
        "period": "weekly",
        "period_label": "주간",
        "recommendations": {"hit_rate_pct": 60, "avg_return_pct": 5},
        "expected_return": {"count": 3, "avg_upside_pct": 8.5},
        "brain_accuracy": sample_brain,
        "meta_analysis": {"best_predictor": "Brain"},
        "news_keywords": {"top_keywords": ["반도체", "AI"]},
    }
    out = _fallback_periodic(data, error="429 RESOURCE_EXHAUSTED")
    # Gemini 실패 메시지는 들어가되
    assert "AI 리포트 생성 실패" in out["risk_watch"]
    # 정량 데이터는 보존돼야
    assert out["brain_accuracy"] == sample_brain
    assert out["meta_analysis"] == {"best_predictor": "Brain"}
    assert out["news_keywords"]["top_keywords"] == ["반도체", "AI"]


def test_fallback_periodic_when_no_quant_data():
    """정량 데이터 자체가 없을 때도 안전하게 빈 dict 반환."""
    from api.analyzers.gemini_analyst import _fallback_periodic
    out = _fallback_periodic({"period": "weekly"})
    assert out["brain_accuracy"] == {}
    assert out["meta_analysis"] == {}


# ──────────────────────────────────────────────
# 2. _compute_brain_quality — 종합 점수 산출
# ──────────────────────────────────────────────

def _quality():
    from api.main import _compute_brain_quality
    return _compute_brain_quality


def test_quality_no_data_returns_no_data_status():
    fn = _quality()
    res = fn({}, "weekly")
    assert res["score"] is None
    assert res["status"] == "no_data"


def test_quality_insufficient_samples_under_5():
    """표본 5건 미만이면 score=None + status=insufficient_data."""
    fn = _quality()
    res = fn({"grades": {
        "STRONG_BUY": {"count": 2, "hit_rate": 100, "avg_return": 10},
        "AVOID": {"count": 1, "hit_rate": 0, "avg_return": -5},
    }})
    assert res["score"] is None
    assert res["status"] == "insufficient_data"
    assert "표본" in res["note"]


def test_quality_perfect_brain():
    """완벽한 Brain — STRONG_BUY 100% hit + AVOID -10% + spread 30%p+."""
    fn = _quality()
    res = fn({"grades": {
        "STRONG_BUY": {"count": 5, "hit_rate": 100, "avg_return": 20},
        "AVOID": {"count": 5, "hit_rate": 0, "avg_return": -10},
    }})
    assert res["status"] == "ok"
    # 양성 40 + 회피 30 + 분리 30 = 100
    assert res["score"] == 100.0
    assert res["components"]["positive_hit_rate_score"] == 40.0
    assert res["components"]["avoid_avoidance_score"] == 30.0
    assert res["components"]["grade_separation_score"] == 30.0


def test_quality_mediocre_brain():
    """50% 적중 + AVOID 0% + 적당한 spread → 중간 점수."""
    fn = _quality()
    res = fn({"grades": {
        "STRONG_BUY": {"count": 5, "hit_rate": 50, "avg_return": 5},
        "AVOID": {"count": 5, "hit_rate": 50, "avg_return": 0},
    }})
    # 양성 50% × 40/100 = 20, 회피 (5-0)/15×30 = 10, 분리 5/30×30 = 5 → 35
    assert res["status"] == "ok"
    assert 30 <= res["score"] <= 40


def test_quality_terrible_brain():
    """STRONG_BUY 가 마이너스 + AVOID 가 플러스 → 거의 0점."""
    fn = _quality()
    res = fn({"grades": {
        "STRONG_BUY": {"count": 5, "hit_rate": 20, "avg_return": -10},
        "AVOID": {"count": 5, "hit_rate": 80, "avg_return": 10},
    }})
    # 양성 20%×40/100=8, 회피 (5-10)/15×30=음수→0, 분리 -20/30×30=음수→0 → 8
    assert res["status"] == "ok"
    assert res["score"] < 15


def test_quality_only_buy_no_strong_buy():
    """STRONG_BUY 표본 없이 BUY 만 있을 때도 양성 점수 산출."""
    fn = _quality()
    res = fn({"grades": {
        "BUY": {"count": 5, "hit_rate": 70, "avg_return": 8},
        "AVOID": {"count": 5, "hit_rate": 20, "avg_return": -3},
    }})
    assert res["status"] == "ok"
    # spread 는 STRONG_BUY 없어 0점이지만 양성/회피는 산출
    assert res["components"]["grade_separation_score"] == 0.0
    assert res["components"]["positive_hit_rate_score"] > 0


def test_quality_metrics_section():
    """metrics 섹션이 표본 수·평균 등 원시값 노출."""
    fn = _quality()
    res = fn({"grades": {
        "STRONG_BUY": {"count": 3, "hit_rate": 67, "avg_return": 9},
        "BUY": {"count": 4, "hit_rate": 50, "avg_return": 4},
        "AVOID": {"count": 2, "hit_rate": 50, "avg_return": -2},
    }})
    m = res["metrics"]
    assert m["total_samples"] == 9
    assert m["strong_buy_n"] == 3
    assert m["buy_n"] == 4
    assert m["avoid_n"] == 2
    assert m["avoid_avg_return"] == -2
    assert m["grade_spread_pp"] == 11.0  # 9 - (-2)
