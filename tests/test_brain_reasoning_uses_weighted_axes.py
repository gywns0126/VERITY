"""설명문·자기신고가 '점수를 만든 축' 을 가리키는지 (2026-08-23 신설).

사고 = 운영풀 38/38 전부 `reasoning` 이 "팩트 최강 prediction(80) / 최약 consensus(50)" 처럼
**기여 0 인 축**으로 종목을 설명했다. 원인은 8/16 문헌 전환 이전 15축 시절의 core_keys
하드코딩이고, 현행 가중축과 교집합이 0 이었다. 점수는 바꾸지 않는다 — 정명 조치다.
"""
from api.intelligence.verity_brain import _build_reasoning


FACT = {
    "score": 68,
    "components": {
        # 가중축 (점수를 만든 축)
        "graham_value": 92.0, "canslim_growth": 68.0,
        "quant_quality": 46, "quant_volatility": 67,
        # 기여 0 (실려 있으나 가중 없음) — 여기서 최강/최약이 나오면 회귀다
        "prediction": 80.4, "consensus": 50.0, "multi_factor": 52.0,
        "backtest": 57.7, "timing": 60.0, "export_trade": 73.0,
    },
    "coverage_scope": {
        "weighted_axes": ["canslim_growth", "graham_value", "quant_quality", "quant_volatility"],
        "weighted_axis_count": 4,
    },
}
SENT = {"score": 57, "components": {}}
VCI = {"vci": 11, "label": "팩트 우위", "signal": "CONTRARIAN_BUY", "base_vci": 11}


def _reason(fact=None):
    return _build_reasoning(
        {"name": "AMG", "multi_factor": {}},
        fact or FACT, SENT, VCI, {"auto_avoid": [], "downgrade": []}, 65, "BUY", None,
    )


def test_top_and_bottom_come_from_weighted_axes():
    r = _reason()
    assert "graham_value(92)" in r, r          # 가중축 중 최고
    assert "quant_quality(46)" in r, r         # 가중축 중 최저


def test_zero_contribution_axes_are_not_cited():
    r = _reason()
    for inert in ("prediction", "consensus", "backtest", "export_trade"):
        assert f"최강 {inert}" not in r, f"기여 0 축 {inert} 이 최강으로 인용됐다"
        assert f"최약 {inert}" not in r, f"기여 0 축 {inert} 이 최약으로 인용됐다"


def test_no_weighted_axes_means_no_claim():
    """가중축을 모를 때 아무 축이나 골라 최강이라 말하면 종전 결함의 재발이다."""
    fact = dict(FACT, coverage_scope={"weighted_axes": []})
    r = _reason(fact)
    assert "팩트 최강" not in r, r
