# -*- coding: utf-8 -*-
"""build_system_action — 시스템 작용 패널 데이터 (표시 전용, 산식 불변) 계약."""
from api.intelligence.display_verdict import build_system_action


def _pf(us10=4.68, override=None):
    pf = {"macro": {"us_10y": {"value": us10}, "fred": {}},
          "verity_brain": {"macro_override": override or []}}
    return pf


def test_shield_on_by_threshold():
    sa = build_system_action(_pf(us10=4.68), [])
    assert sa["rate_shield"]["on"] is True
    assert sa["rate_shield"]["threshold"] == 4.5


def test_shield_off_below_threshold():
    sa = build_system_action(_pf(us10=3.9), [])
    assert sa["rate_shield"]["on"] is False
    assert sa["rate_shield"]["effect"] == "미발동"


def test_shield_on_by_override_even_if_rate_missing():
    """구 mode(yield_defense) 는 과거 발행물 재독 호환으로 계속 인식한다."""
    sa = build_system_action(_pf(us10=None, override=[{"mode": "yield_defense", "label": "금리 방패", "max_grade": "WATCH"}]), [])
    assert sa["rate_shield"]["on"] is True
    assert sa["rate_shield"]["grade_cap"] == "WATCH"


def test_observation_mode_reports_sizing_not_grade_cap():
    """2026-08-06 — 미 10Y 는 등급을 막지 않는다. 패널이 '등급 상한'을 말하면 거짓 표기다."""
    analyzed = [{"recommendation": "BUY", "ticker": "A",
                 "macro_multiplier": {"multiplier": 0.9, "yield_penalty": 0.1,
                                      "inputs": {"us_10y_percentile": 97.2}}}]
    sa = build_system_action(
        _pf(us10=4.7, override=[{"mode": "yield_observation", "label": "금리 관측"}]), analyzed)
    rs = sa["rate_shield"]
    assert rs["on"] is True
    assert rs["grade_cap"] is None
    assert rs["sizing_penalty"] == 0.1 and rs["us_10y_percentile"] == 97.2
    assert "등급 무영향" in rs["effect"] and "상한" not in rs["effect"]


def test_kr_rate_defense_still_reports_grade_cap():
    """한국 기준금리 방패는 범위 밖 — 등급 상한 표기가 그대로 남아야 한다."""
    sa = build_system_action(
        _pf(us10=4.7, override=[{"mode": "kr_rate_defense", "label": "기준금리 방패",
                                 "max_grade": "WATCH"}]), [])
    assert sa["rate_shield"]["grade_cap"] == "WATCH"
    assert "등급 상한 WATCH" in sa["rate_shield"]["effect"]


def test_verdict_gate_counts_and_aligned():
    analyzed = [
        {"recommendation": "BUY", "display_verdict": {"aligned": True, "gates": []}, "ticker": "A",
         "macro_multiplier": {"multiplier": 0.9}},
        {"recommendation": "WATCH", "display_verdict": {"aligned": False, "gates": ["soft_boundary"]}, "ticker": "B",
         "macro_multiplier": {"multiplier": 1.0}},
        {"recommendation": "AVOID", "display_verdict": {"aligned": False, "gates": []}, "ticker": "C"},
    ]
    sa = build_system_action(_pf(), analyzed)
    vg = sa["verdict_gate"]
    assert vg["buy_count"] == 1 and vg["aligned"] == ["A"] and vg["gated_count"] == 1
    assert sa["macro_multiplier_median"] == 1.0


def test_never_raises_on_empty():
    sa = build_system_action({}, [])
    assert sa["rate_shield"]["on"] is False and sa["verdict_gate"]["buy_count"] == 0
