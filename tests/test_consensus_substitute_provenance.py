"""컨센서스 슬롯의 대체 신호(flow_fallback) 정직 표기 — 측정 오염 차단.

2026-07-27. consensus_score.py 는 컨센서스가 없으면 **수급(flow) 점수**를 consensus_score 에
넣고 score_source="flow_fallback" 으로 표기한다. 값이 숫자라 data_coverage 의 _num() 검사를
통과해 "컨센서스 보유"로 계상됐음 — 실제로는 부재.

실측(2026-07-27 recommendations 44종목): flow_fallback 25(57%) / us_perplexity_consensus 18 /
consensus 1. 과반이 대체 신호인데 coverage 는 보유로 잡혔다.

🚨 점수 불변 — data_coverage/missing_components 는 informational only.
   슬롯에서 flow_fallback 을 빼는 건 산식 변경이라 RULE 7 사전승인 대상(별건).
"""
import copy

from api.intelligence.factors.fact import _compute_fact_score


def _stock(score_source, consensus_score=62):
    return {
        "ticker": "000660",
        "name": "테스트",
        "consensus": {"consensus_score": consensus_score, "score_source": score_source},
        "multi_factor": {"multi_score": 55},
        "prediction": {"up_probability": 51},
        "timing": {"timing_score": 48},
    }


def test_flow_fallback_marked_substituted_and_not_counted_as_covered():
    res = _compute_fact_score(_stock("flow_fallback"))
    assert "consensus" in res["substituted_components"]
    assert "consensus" in res["missing_components"]      # 대체분 = 부재로 계상
    assert res["consensus_source"] == "flow_fallback"


def test_real_consensus_counted_as_covered():
    res = _compute_fact_score(_stock("consensus"))
    assert res["substituted_components"] == []
    assert "consensus" not in res["missing_components"]
    assert res["consensus_source"] == "consensus"


def test_perplexity_consensus_is_real_not_substitute():
    """us_perplexity_consensus = analyst target 기반 실 컨센서스 → 대체 아님."""
    res = _compute_fact_score(_stock("us_perplexity_consensus"))
    assert res["substituted_components"] == []
    assert "consensus" not in res["missing_components"]


def test_coverage_effect_tracks_live_consensus_weight():
    """coverage 는 가중치 기반 — consensus 가중치가 살아있을 때만 대체분이 coverage 를 낮춘다.

    🚨 2026-07-27 현재는 차이가 0 이다. IC 동결(factor_decay._FROZEN_DISABLE, PM 2026-05-18)로
    consensus multiplier=0.0/DEAD 라 가중치가 0 → coverage 산식에서 빼도 동일.
    즉 지금은 consensus 슬롯이 fact_score 에 기여 0. 동결이 풀리면 이 테스트가 실 차이를 검증한다.
    """
    from api.intelligence.factors._common import _load_ic_adjustments

    real = _compute_fact_score(_stock("consensus"))
    sub = _compute_fact_score(_stock("flow_fallback"))

    adj = (_load_ic_adjustments().get("adjustments") or {}).get("consensus") or {}
    consensus_weight_alive = float(adj.get("multiplier", 1.0)) > 0

    if consensus_weight_alive:
        assert sub["data_coverage"] < real["data_coverage"]
    else:
        # 동결 중 — 가중치 0 이라 coverage 불변이 정상. 표기(substituted)만으로 구분 가능해야 함.
        assert sub["data_coverage"] == real["data_coverage"]
        assert sub["substituted_components"] == ["consensus"]
        assert real["substituted_components"] == []


def test_score_unchanged_by_provenance_marking():
    """🚨 RULE 7 안전선 — 출처 표기가 점수·컴포넌트·가중치를 바꾸면 안 됨."""
    real = _compute_fact_score(_stock("consensus", consensus_score=62))
    sub = _compute_fact_score(_stock("flow_fallback", consensus_score=62))
    assert sub["score"] == real["score"]
    assert sub["components"] == real["components"]


def test_missing_consensus_still_missing():
    """값 자체가 없으면 기존대로 missing (회귀 0)."""
    s = _stock("flow_fallback")
    s["consensus"] = {}
    res = _compute_fact_score(s)
    assert "consensus" in res["missing_components"]
    assert res["consensus_source"] is None
