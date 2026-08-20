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


# 🚨 2026-08-20 F-c — 인플레 축이 한국 CPI 로 바뀌었다. 이 파일은 **성장 축** 계약이므로
#   인플레 축을 기본 주입해 unknown 으로 빠지지 않게 한다(인플레 계약은 별도 파일).
_KR_AXIS = {"inflation_up": False, "z": -0.8, "yoy_pct": 1.5,
            "form": "rolling_z_sign_only", "window_months": 12}


def _pf(fred=None, mood=None, with_inflation=True):
    macro = {}
    if fred is not None:
        macro["fred"] = dict(fred)
    if with_inflation:
        macro.setdefault("fred", {})["korea_cpi_axis"] = _KR_AXIS
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

    # 🚨 2026-08-20 — `growth_up_inflation_up` 이 처음 나왔다(`2026-08-20.json` 1일).
    #   이 테스트가 요구한 대로 어느 쪽인지 갈랐다: **입력 변화이지 로직 변화가 아니다.**
    #   해당 일자 근거 = inflation_z **+1.008**(12개월 롤링 z 부호) · gdp_growth 2.45 ·
    #   cpi_yoy 2.789 · source `ecos.901Y009.headline_kr`. 종전 118일은 z<0 이라
    #   inflation_down 뿐이었다. 즉 지표가 부호를 넘긴 것이고 센티넬은 정상이다.
    #
    #   🚨 그래서 **분모 고정을 목록 확장으로 때우지 않는다** — 그러면 다음 신규 사분면도
    #   똑같이 목록에 밀어넣게 되어 테스트가 고무도장이 된다. 대신 라벨과 근거값이
    #   **서로 맞는지**를 본다(부호 불일치 = 진짜 로직 결함).
    assert set(c) <= {"unknown", "growth_up_inflation_down", "growth_up_inflation_up"}, dict(c)
    assert sum(c.values()) == len(files) - sum(1 for f in files if _unreadable(f)), dict(c)

    for f in files:
        try:
            with open(f, encoding="utf-8") as fh:
                q = detect_economic_quadrant(json.load(fh))
        except (OSError, ValueError):
            continue
        z = q.get("inflation_z")
        if q["quadrant"] == "unknown" or z is None:
            continue
        if q["quadrant"].endswith("inflation_up"):
            assert z > 0, (f, q["quadrant"], z)
        elif q["quadrant"].endswith("inflation_down"):
            assert z <= 0, (f, q["quadrant"], z)


def _unreadable(path) -> bool:
    try:
        with open(path, encoding="utf-8") as fh:
            json.load(fh)
        return False
    except (OSError, ValueError):
        return True
