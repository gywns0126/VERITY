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
