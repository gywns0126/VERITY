"""B1 계약 — 결측은 값이 아니다 (PREREG_QUADRANT_DISPOSITION_2026_08_19, PM 승인 2026-08-19).

## 이 테스트가 지키는 것

118일 전수 측정에서 드러난 결함: **성장 축이 경제가 아니라 `gdp_growth` 필드의 존재
여부로 뒤집혔다** — 결측 → growth_down **37/37**, 존재 → growth_up **81/81**.

원인은 fallback `(market_mood − 50) × 0.06` 이 임계 1.5 를 넘으려면 `mood > 75` 여야
하는데 실측 범위가 30~75 라 **구조적으로 도달 불가**했다는 것. 즉 그 fallback 은
관측이 아니라 **growth_down 상수의 주입**이었다.

🚨 여기서 잠그는 계약은 "값이 옳다" 가 아니라 **"없는 걸 만들지 않는다"** 다.
"""
import json

import pytest

from api.intelligence.verity_brain import detect_economic_quadrant


def _pf(fred=None, mood=None):
    macro = {}
    if fred is not None:
        macro["fred"] = fred
    if mood is not None:
        macro["market_mood"] = {"score": mood}
    return {"macro": macro}


# ── 핵심 계약 ─────────────────────────────────────────────────────────────


def test_missing_growth_input_returns_unknown_not_a_number():
    """🚨 성장 입력이 없으면 값을 만들지 않고 unknown 을 반환한다."""
    q = detect_economic_quadrant(_pf(fred={"cpi_yoy": {"value": 2.79}}, mood=60))
    assert q["quadrant"] == "unknown"
    assert q["gdp_growth"] is None, "결측인데 숫자가 만들어졌다"
    assert q["favored"] == [] and q["unfavored"] == []
    assert q["quadrant_source"] == "unknown"
    assert q["unknown_reason"]


def test_market_mood_fallback_is_gone():
    """🚨 폐기된 fallback 이 되살아나면 잡는다.

    mood 를 어떤 값으로 줘도 성장 축이 만들어지면 안 된다 — mood=100 이면 종전 산식으로
    (100−50)×0.06 = 3.0 > 1.5 라 growth_up 이 됐다.
    """
    for mood in (0, 30, 50, 60, 75, 90, 100):
        q = detect_economic_quadrant(_pf(fred={"cpi_yoy": {"value": 2.79}}, mood=mood))
        assert q["quadrant"] == "unknown", f"mood={mood} 에서 fallback 이 부활했다"

    import inspect
    src = inspect.getsource(detect_economic_quadrant)
    assert "* 0.06" not in src, "market_mood fallback 산식이 소스에 되살아났다"


def test_pmi_path_still_works_when_present():
    """ism_pmi 는 유효한 대체 경로다 — B1 은 그걸 없애지 않았다."""
    q = detect_economic_quadrant(
        _pf(fred={"ism_pmi": {"value": 55.0}, "cpi_yoy": {"value": 2.79}}))
    assert q["quadrant"] == "growth_up_inflation_down"
    assert q["quadrant_source"] == "fred.ism_pmi"


def test_normal_path_declares_that_gdp_growth_is_not_gdp():
    """🚨 `fred.gdp_growth` 는 이름과 달리 GDP 실측이 아니다 — 산출물이 신고해야 한다."""
    q = detect_economic_quadrant(
        _pf(fred={"gdp_growth": {"value": 2.45}, "cpi_yoy": {"value": 2.79}}))
    assert q["quadrant_source"] == "fred.gdp_growth"
    assert "GDP 실측이 아니다" in (q["growth_input_note"] or "")


# ── 소비자 가드 ───────────────────────────────────────────────────────────


def test_sector_rotation_does_not_treat_unknown_as_a_regime():
    """🚨 dict 가 truthy 라 `if not quadrant_info` 만으로는 unknown 이 통과한다."""
    from api.intelligence.sector_rotation_detector import _check_quadrant_consistency

    unknown = detect_economic_quadrant(_pf(fred={}, mood=60))
    r = _check_quadrant_consistency(
        [{"name": "성장주", "return_pct": 5.0}], [{"name": "금", "return_pct": -3.0}], unknown)
    assert r["reason"] == "quadrant_unknown", "unknown 이 국면으로 취급됐다"
    assert r["drift"] is False


# ── 118일 재현 고정 ───────────────────────────────────────────────────────


def test_full_history_replay_matches_measurement():
    """🚨 실측과 시행 결과가 일치하는지 — 종전 growth_down 37일이 정확히 unknown 이어야.

    이 수치가 바뀌면 입력이 바뀐 것이거나 로직이 바뀐 것이다. 둘 다 알아야 한다.
    """
    import collections
    import glob
    import os

    files = sorted(glob.glob(os.path.join("data", "history", "20??-??-??.json")))
    if len(files) < 50:
        pytest.skip(f"history {len(files)}개 — 재현 표본 부족")

    c = collections.Counter()
    for f in files:
        try:
            with open(f, encoding="utf-8") as fh:
                c[detect_economic_quadrant(json.load(fh))["quadrant"]] += 1
        except (OSError, ValueError):
            continue

    assert c["growth_down_inflation_down"] == 0, \
        "growth_down 이 다시 나온다 — fallback 부활 또는 실입력 변화"
    assert c["unknown"] > 0, "unknown 이 0 — 센티넬이 작동하지 않는다"
    # 🚨 분모를 함께 고정한다 (RULE 13)
    assert c["unknown"] + c["growth_up_inflation_down"] == sum(c.values())
