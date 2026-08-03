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
    sa = build_system_action(_pf(us10=None, override=[{"mode": "yield_defense", "label": "금리 방패", "max_grade": "WATCH"}]), [])
    assert sa["rate_shield"]["on"] is True
    assert sa["rate_shield"]["grade_cap"] == "WATCH"


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
