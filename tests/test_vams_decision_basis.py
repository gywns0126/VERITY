"""체결 근거 자기신고 (2026-08-23 신설).

사고 = AMG 8/21 매수. recommendation 은 verity_brain BUY(65)를 따랐는데 buy_reason 은
ai_verdict("멀티팩터 53점 (관망)")를 그대로 써서 **체결 근거와 감사 흔적이 어긋났다.**
이 테스트는 임계를 검사하지 않는다 — 무엇을 따랐는지 신고하는지만 본다.
"""
from api.vams.engine import _buy_reason_with_basis, _decision_basis


AMG_LIKE = {
    "recommendation": "BUY",
    "ai_verdict": "멀티팩터 52점 (관망) — 관찰 필요",
    "verity_brain": {"brain_score": 65, "grade": "BUY"},
    "multi_factor": {"multi_score": 52, "grade": "관망"},
}


def test_disagreement_is_flagged():
    b = _decision_basis(AMG_LIKE)
    assert b["scores_disagree"] is True
    assert b["brain_score"] == 65 and b["multi_score"] == 52
    assert b["recommendation_source"] == "verity_brain"


def test_reason_names_the_executing_basis():
    r = _buy_reason_with_basis(AMG_LIKE)
    assert "BUY 체결" in r, r
    assert "65" in r and "52" in r, r
    assert r != AMG_LIKE["ai_verdict"], "갈렸는데 종전 문자열을 그대로 썼다"


def test_agreement_keeps_original_string():
    agree = {
        "recommendation": "WATCH",
        "ai_verdict": "멀티팩터 52점 (관망) — 관찰 필요",
        "verity_brain": {"brain_score": 52, "grade": "WATCH"},
        "multi_factor": {"multi_score": 52, "grade": "관망"},
    }
    assert _decision_basis(agree)["scores_disagree"] is False
    assert _buy_reason_with_basis(agree) == agree["ai_verdict"]


def test_missing_scores_do_not_claim_disagreement():
    """한쪽을 모를 때 '갈렸다' 고 신고하면 거짓 경보가 된다."""
    partial = {"recommendation": "BUY", "ai_verdict": "x", "multi_factor": {}}
    assert _decision_basis(partial)["scores_disagree"] is False
    assert _buy_reason_with_basis(partial) == "x"
