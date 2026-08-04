# -*- coding: utf-8 -*-
"""display_verdict 게이트 — 배지 단일 소유(Brain) + 강등 전용 (2026-08-03).

핵심 계약: 게이트는 절대 올리지 않는다 / LLM 합의는 analyst_view 로 보존 /
브레인 미채점은 소유권 이전 불가(기존 rec 유지 + 표기).
"""
from api.intelligence.display_verdict import apply_display_verdict


def _stock(grade="BUY", confidence="firm", timing="HOLD", rec="AVOID"):
    return {
        "recommendation": rec,  # LLM 합의 (배지 소유권 상실 대상)
        "verity_brain": {"grade": grade, "grade_confidence": confidence},
        "timing": {"action": timing},
    }


def test_brain_owns_badge_over_llm():
    # LLM 이 AVOID 라 해도 배지는 브레인 등급 — 소유권 이전
    s = apply_display_verdict(_stock(grade="BUY", confidence="firm", timing="HOLD", rec="AVOID"))
    assert s["recommendation"] == "BUY"
    assert s["analyst_view"] == "AVOID"
    assert s["display_verdict"]["owner"] == "brain"


def test_soft_boundary_blocks_buy():
    # 임계 경계권(soft) BUY → 한 단계 강등
    s = apply_display_verdict(_stock(grade="BUY", confidence="soft"))
    assert s["recommendation"] == "WATCH"
    assert "soft_boundary" in s["display_verdict"]["gates"]


def test_timing_conflict_demotes_to_watch():
    s = apply_display_verdict(_stock(grade="STRONG_BUY", confidence="firm", timing="SELL"))
    assert s["recommendation"] == "WATCH"
    assert "timing_conflict" in s["display_verdict"]["gates"]


def test_aligned_buy_kept_and_flagged():
    s = apply_display_verdict(_stock(grade="BUY", confidence="firm", timing="BUY"))
    assert s["recommendation"] == "BUY"
    assert s["display_verdict"]["aligned"] is True
    assert s["display_verdict"]["gates"] == []


def test_never_promotes():
    # LLM BUY + 브레인 WATCH → 배지 WATCH (승격 불가)
    s = apply_display_verdict(_stock(grade="WATCH", confidence="firm", timing="BUY", rec="BUY"))
    assert s["recommendation"] == "WATCH"
    assert s["display_verdict"]["aligned"] is False


def test_ungraded_keeps_llm_rec_with_provenance():
    s = apply_display_verdict({"recommendation": "WATCH", "verity_brain": {}, "timing": {}})
    assert s["recommendation"] == "WATCH"
    assert s["display_verdict"]["owner"] == "analyst_fallback"
    assert "brain_ungraded" in s["display_verdict"]["gates"]


def test_avoid_passthrough():
    s = apply_display_verdict(_stock(grade="AVOID", confidence="soft", timing="SELL", rec="BUY"))
    assert s["recommendation"] == "AVOID"
    assert s["display_verdict"]["gates"] == []  # BUY 이상에만 게이트 — 하위 등급은 그대로


# ── F1 조건부 신호 (PREREG_SIGNAL_FILTERS_2026_08_04 §F1) ──────────────────────

def _stock_f1(grade="WATCH", confidence="firm", timing="HOLD", brain_score=65,
              price=10_000, ma20=11_000, r5=None):
    s = _stock(grade=grade, confidence=confidence, timing=timing)
    s["verity_brain"]["brain_score"] = brain_score
    s["technical"] = {"price": price, "ma20": ma20, "return_5d_pct": r5}
    return s


def test_f1_ma20_reclaim_when_below_ma20():
    # 기아 사례형: WATCH ∧ brain≥60 ∧ 종가 < MA20 → ma20_reclaim (등록 순서 1순위)
    s = apply_display_verdict(_stock_f1(price=10_000, ma20=11_000))
    trig = s["display_verdict"]["trigger_condition"]
    assert trig["type"] == "ma20_reclaim"
    assert "11,000" in trig["message"] and "회복" in trig["message"]


def test_f1_timing_align_for_demoted_brain_buy():
    # 브레인 BUY(soft 강등 → WATCH) ∧ 종가 ≥ MA20 ∧ timing ≠ BUY → timing_align
    s = apply_display_verdict(_stock_f1(grade="BUY", confidence="soft",
                                        price=12_000, ma20=11_000))
    trig = s["display_verdict"]["trigger_condition"]
    assert trig["type"] == "timing_align"


def test_f1_pullback_hold_after_surge():
    # 5일 +15%↑ 급등 ∧ 종가 ≥ MA20 ∧ base WATCH → pullback_hold
    s = apply_display_verdict(_stock_f1(price=12_000, ma20=11_000, r5=18.2))
    trig = s["display_verdict"]["trigger_condition"]
    assert trig["type"] == "pullback_hold"
    assert "12,000" in trig["message"]


def test_f1_absent_below_brain_60():
    s = apply_display_verdict(_stock_f1(brain_score=55))
    assert "trigger_condition" not in s["display_verdict"]


def test_f1_absent_for_non_watch_badge():
    s = apply_display_verdict(_stock_f1(grade="CAUTION", brain_score=65))
    assert "trigger_condition" not in s["display_verdict"]


def test_f1_first_match_order_ma20_wins():
    # ma20_reclaim 과 pullback_hold 동시 충족 → 등록 나열 순 first-match = ma20_reclaim
    s = apply_display_verdict(_stock_f1(price=10_000, ma20=11_000, r5=20.0))
    assert s["display_verdict"]["trigger_condition"]["type"] == "ma20_reclaim"
