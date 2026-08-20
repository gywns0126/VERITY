"""등급 도달 가능성 자기신고 계약 (G1) — PREREG_BASELINE_V1_LITERATURE_2026_08_16 개정 2026-08-20.

왜 이 테스트가 필요한가:
  PSI 드리프트 모니터는 "비중이 안 변했다" 를 안정으로 읽는다. 그런데 임계가 관측 범위
  밖이면 그 등급은 영구 0 이라 **비중 변화가 정확히 0** 이고, 모니터에는 가장 안정된
  등급처럼 보인다. 도달 불가가 드리프트 모니터의 사각지대라는 뜻이다.
  실측(2026-08-20 · 분모 3,396 종목-일 · 92일): STRONG_BUY 0건 · BUY 1.355%.
  5등급 선언인데 실질 3등급으로 돈다.

🚨 이 테스트가 고정하지 **않는** 것 = 임계값 자체.
  임계 조정(G2 백분위 재정의)은 RULE 7 쿼터 사안이고 PM 결재 대기다. 값을 여기에
  고정하면 승인이 나도 테스트가 막는다. 고정 대상은 **신고 계약**과 **출처 표기의
  정직성**뿐이다.
"""
import json
import os

import pytest

from api.observability.grade_distribution_drift import (
    GRADES,
    _PROVENANCE_KNOWN,
    compute_grade_reachability,
    evaluate_grade_drift,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONSTITUTION = os.path.join(ROOT, "data", "verity_constitution.json")


def _grades_cfg():
    with open(CONSTITUTION, encoding="utf-8") as f:
        return (json.load(f).get("decision_tree") or {}).get("grades") or {}


def test_reachability_reports_denominator_not_just_share():
    """RULE 13 — 비중만 신고하면 0% 가 표본 부족인지 도달 불가인지 갈리지 않는다."""
    r = compute_grade_reachability({"WATCH": 10}, {"WATCH": 5, "BUY": 1})
    assert r["denominator_stock_days"] == 16, "분모(종목-일)를 신고해야 한다"
    assert r["per_grade"]["WATCH"]["count"] == 15
    assert r["per_grade"]["BUY"]["count"] == 1


def test_never_fired_lists_grades_absent_from_the_window():
    r = compute_grade_reachability({"WATCH": 10}, {"CAUTION": 3})
    assert set(r["never_fired"]) == {"STRONG_BUY", "BUY", "AVOID"}
    assert r["effective_grade_count"] == 2
    assert r["declared_grade_count"] == len(GRADES)


def test_empty_window_does_not_claim_unreachable():
    """🚨 관측 0 은 '도달 불가' 가 아니라 '표본 없음' 이다. 두 사건을 섞지 않는다."""
    r = compute_grade_reachability({}, {})
    assert r["denominator_stock_days"] == 0
    assert r["never_fired"] == [], "분모 0 에서 도달 불가를 단정하면 안 된다"


def test_provenance_flag_matches_the_constitution():
    """🚨 'recorded' 라고 신고한 등급은 헌법에 실제 출처 주석이 있어야 한다.

    임계 5개 중 출처 기록 보유는 CAUTION(_note_2026_05_16) 하나뿐이라는 게 실측이다.
    누가 _PROVENANCE_KNOWN 에 등급을 더하면서 주석을 안 남기면 여기서 걸린다.
    """
    cfg = _grades_cfg()
    for g in _PROVENANCE_KNOWN:
        entry = cfg.get(g) or {}
        notes = [k for k in entry if k.startswith("_note")]
        assert notes, (
            f"{g} 를 provenance='recorded' 로 신고했는데 헌법에 _note* 주석이 없다. "
            "출처 없는 값을 있는 것처럼 신고하면 자기신고가 무의미해진다."
        )


def test_grades_without_a_recorded_source_are_reported_as_unrecorded():
    cfg = _grades_cfg()
    r = compute_grade_reachability({g: 1 for g in GRADES}, {})
    for g in GRADES:
        has_note = any(k.startswith("_note") for k in (cfg.get(g) or {}))
        expected = "recorded" if has_note else "unrecorded"
        assert r["per_grade"][g]["threshold_provenance"] == expected, (
            f"{g} 의 출처 표기가 헌법 실제 상태와 어긋난다"
        )


def test_drift_evaluation_carries_the_self_report():
    """산출물이 자기 입으로 말해야 한다 (RULE 12 #2). 키가 빠지면 조용히 사라진다."""
    out = evaluate_grade_drift({})
    if out.get("psi_tier") == "insufficient":
        pytest.skip("baseline 표본 부족 — 드리프트 평가 자체가 생략된 경로")
    gr = out.get("grade_reachability")
    assert gr is not None, "drift 산출물에 grade_reachability 가 실려야 한다"
    assert "denominator_stock_days" in gr
    assert set(gr["per_grade"]) == set(GRADES)
