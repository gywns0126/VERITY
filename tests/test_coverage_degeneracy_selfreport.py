"""G6 결측·커버리지 정직 신고 계약 — PREREG_BASELINE_V1_LITERATURE_2026_08_16 §G6.

왜 이 테스트가 필요한가:
  `data_coverage` 는 **가중치로 가중된** 비율이라, 추적 결측 축과 가중치>0 축의 교집합이
  비면 어떤 입력에서도 정확히 1.0 이 된다. 2026-08-16 문헌 4축 전환 이후가 그 상태였고
  (실측 66/66 전부 1.0), 이 필드의 목적("저점수가 데이터 부재인가 실제 약신호인가")이
  그때부터 작동을 멈췄다.

  🚨 **기존 테스트 11건은 전부 통과했다.** IC 동결용으로 쓴 `가중치 0` 분기를 조용히
  타기 때문이다 ([[feedback_green_check_is_not_safety]] 검사 통과 ≠ 안전).
  그래서 값이 아니라 **신고의 정직성**을 고정한다.

🚨 이 테스트가 고정하지 **않는** 것 = 현재의 축소 상태.
  G5(가중 재배분) 등이 승인돼 교집합이 생기면 `is_degenerate` 는 False 가 되어야 하고,
  그때 이 테스트는 계속 통과해야 한다. 결함 상태를 기대값으로 고정하면 수정이 막힌다.
"""
import ast
import os

import pytest

from api.intelligence.factors.fact import _TRACKED_MISSING_AXES, _compute_fact_score
from api.intelligence.factors.sentiment import _compute_sentiment_score

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FACT_SRC = os.path.join(ROOT, "api", "intelligence", "factors", "fact.py")


def _stock():
    return {"ticker": "005930", "name": "삼성전자", "market": "KR",
            "price": 70000, "per": 12.0, "pbr": 1.2}


# ── fact ────────────────────────────────────────────────────────────────

def test_coverage_scope_is_present_with_denominator():
    """RULE 13 — 커버리지를 신고하려면 분모(어떤 축이 가중되는가)를 같이 내야 한다."""
    cs = _compute_fact_score(_stock(), portfolio={}).get("coverage_scope")
    assert cs is not None, "coverage_scope 가 산출물에서 사라졌다"
    for k in ("weighted_axes", "weighted_axis_count", "tracked_missing_axes",
              "overlap_with_tracked", "is_degenerate", "axis_measurement",
              "coverage_definition", "is_measurable"):
        assert k in cs, f"coverage_scope.{k} 누락"
    assert cs["weighted_axis_count"] == len(cs["weighted_axes"])
    assert set(cs["axis_measurement"]) == {
        "graham_value", "canslim_growth", "quant_quality", "quant_volatility"
    }


def test_degeneracy_flag_is_honest_in_both_directions():
    """🚨 교집합이 비면 반드시 is_degenerate=True, 있으면 반드시 False.

    한쪽만 검사하면 플래그가 상수 True 로 굳어도 통과한다.
    """
    cs = _compute_fact_score(_stock(), portfolio={})["coverage_scope"]
    overlap_empty = len(cs["overlap_with_tracked"]) == 0
    assert cs["is_degenerate"] is overlap_empty, (
        "is_degenerate 가 실제 교집합과 어긋난다 — 신고가 거짓이면 신고가 없느니만 못하다"
    )


def test_degenerate_coverage_can_only_be_one():
    """축소 상태라면 data_coverage 는 실제로 1.0 이어야 한다 — 진단의 전제 검증."""
    out = _compute_fact_score(_stock(), portfolio={})
    if out["coverage_scope"]["is_degenerate"]:
        assert out["data_coverage"] == 1.0, (
            "교집합이 비었는데 coverage 가 1.0 이 아니다 — 축소 논증이 틀렸다는 뜻이므로 "
            "coverage_scope 의 근거 주석을 다시 확인할 것"
        )


def test_active_fact_axes_are_all_tracked_and_empty_input_is_not_full_coverage():
    out = _compute_fact_score({"ticker": "EMPTY"}, portfolio={})
    cs = out["coverage_scope"]
    assert set(cs["weighted_axes"]) <= set(cs["tracked_missing_axes"])
    assert cs["is_degenerate"] is False
    assert out["data_coverage"] < 1.0
    assert set(cs["weighted_axes"]) <= set(out["missing_components"])


def test_tracked_axes_match_code():
    """🚨 `_TRACKED_MISSING_AXES` 가 본문 `_missing.add(...)` 목록과 일치해야 한다.

    새 결측 축을 로직에만 추가하고 상수를 안 고치면, 그 축은 커버리지 진단에서
    조용히 빠진다. 주석이 아니라 **코드**를 읽어 대조한다(AST).
    """
    with open(FACT_SRC, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    added = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if (isinstance(fn, ast.Attribute) and fn.attr == "add"
                and isinstance(fn.value, ast.Name) and fn.value.id == "_missing"):
            for a in node.args:
                if isinstance(a, ast.Constant) and isinstance(a.value, str):
                    added.add(a.value)
    assert added, "_missing.add(...) 호출을 하나도 못 찾았다 — 파서가 깨졌거나 로직이 바뀌었다"
    assert added == set(_TRACKED_MISSING_AXES), (
        f"코드가 추가하는 축 {sorted(added)} 와 상수 {sorted(_TRACKED_MISSING_AXES)} 가 다르다"
    )


# ── sentiment ───────────────────────────────────────────────────────────

def test_sentiment_reports_active_axes_and_neutral_fill():
    """이 블록은 결측 신고 필드가 아예 없었다. 다시 사라지면 여기서 걸린다."""
    se = _compute_sentiment_score(_stock(), {})
    for k in ("active_axes", "neutral_valued", "neutral_weight_share", "neutral_fill_policy"):
        assert k in se, f"sentiment.{k} 누락"
    assert se["neutral_fill_policy"] == "impute_50", (
        "결측 정책이 바뀌었다면 신고 문자열도 같이 바뀌어야 한다 "
        "(volatility 내부는 exclude_renormalize — 정책이 둘이라는 사실이 보여야 한다)"
    )


def test_neutral_valued_is_a_subset_of_active_axes():
    """가중 0 축을 중립으로 세면 비중이 부풀려진다."""
    se = _compute_sentiment_score(_stock(), {})
    assert set(se["neutral_valued"]) <= set(se["active_axes"])


def test_neutral_weight_share_is_a_fraction():
    se = _compute_sentiment_score(_stock(), {})
    sh = se["neutral_weight_share"]
    assert sh is None or 0.0 <= sh <= 1.0


def test_neutral_share_one_means_score_is_neutral():
    """🚨 활성 가중 전부가 중립이면 점수는 50 이어야 한다 — 신고와 값의 정합.

    실측(2026-08-20 · 분모 66): 094970 제이엠티가 share=1.000 · score=50.
    이 정합이 깨지면 neutral_valued 판정이 실제 계산과 갈린 것이다.
    """
    se = _compute_sentiment_score(_stock(), {})
    if se["neutral_weight_share"] is not None and se["neutral_weight_share"] >= 0.999:
        assert se["score"] == 50, (
            f"활성 가중 100%가 중립인데 점수가 {se['score']} — 신고와 계산이 어긋난다"
        )
    else:
        pytest.skip("이 입력은 전부-중립 사례가 아니다")
