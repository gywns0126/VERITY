"""사이징 표시값과 집행값이 갈리는 것을 산출물이 신고하는지 (2026-08-25 신설).

사고 = PM "1천만원 중 얼마" 질문에 brain 산출물의 `position_guide.recommended_pct 3%`를
집행 규칙으로 읽어 28만원(10주)이라 답했다. 실제 집행은 `vams.execute_buy` 의
min(max_per_stock, 현금×0.9) → Kelly → 변동성 → 매크로 체인이고 **104만원(37주·10.7%)** 이었다.
어제 고친 3건(market_cap 0 · decision_basis · reasoning 축)과 같은 계열 — 표시값이 집행값인 척한다.
🚨 점수·임계·사이징 값은 바꾸지 않는다. 신고만 붙인다.
"""
from api.intelligence.verity_brain import _compute_position_guide


def test_position_guide_declares_it_is_not_the_executor():
    g = _compute_position_guide(75, "WATCH", {})
    assert g["is_executor"] is False, "집행자가 아니라는 신고가 사라졌다"
    assert "execute_buy" in g["executor"], g["executor"]
    assert "집행 크기 아님" in g["scope"], g["scope"]


def test_position_guide_values_unchanged():
    """정명 조치이므로 기존 숫자는 그대로여야 한다 (RULE 7 쿼터 미소모의 근거)."""
    g = _compute_position_guide(75, "WATCH", {})
    for k in ("recommended_pct", "kelly_raw_pct", "max_pct", "rationale"):
        assert k in g, f"{k} 가 사라졌다"
    assert isinstance(g["recommended_pct"], (int, float))
    assert g["recommended_pct"] <= g["max_pct"], "상한을 넘는 추천이 나왔다"


def test_critical_red_flag_still_zero():
    g = _compute_position_guide(90, "BUY", {"has_critical": True})
    assert g["recommended_pct"] == 0.0
    assert g["is_executor"] is False


def test_executor_reports_binding_constraint():
    """집행 체인이 '무엇이 크기를 정했는지'(max_per_stock vs 현금)를 신고하는지."""
    import inspect
    from api.vams import engine
    src = inspect.getsource(engine.execute_buy)
    for token in ("sizing_chain", "base_binding", "after_kelly", "after_volatility", "after_macro"):
        assert token in src, f"집행 자기신고 필드 {token} 가 사라졌다"
    assert "brain_position_guide_pct" in src, "참고값 대조 필드가 사라졌다"
