# -*- coding: utf-8 -*-
"""사전등록 산출물 계약 — 세션 경계를 넘는 강제 장치 (2026-08-15 신설).

🚨 이 테스트가 존재하는 이유는 규율이 3일 만에 퇴화했기 때문이다.

```
prereg_safety_score_20260809.json        min_detectable_ic 있음
prereg_safety_score_full_20260810.json   min_detectable_ic 있음
prereg_portfolio_20260813.json           없음   ← 여기서 사라짐
… 이후 8/15 까지 6건 전부 없음
```

그리고 그 6건은 전부 **운영에 쓰이지 않는 점수(C3)** 를 쟀는데 그 사실이 산출물 어디에도
없어서, 다음 세션이 "우리 점수는 6개월 검증됐다" 로 읽을 수 있었다.

기억으로는 안 막힌다. **신규 산출물은 자기 입으로 신고해야 하고, 안 하면 CI 가 막는다.**
"""
import glob
import json
import os

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DIR = os.path.join(_ROOT, "data", "analysis")

# 이 계약 이전 산출물 — 소급 적용하지 않되 **목록으로 남겨** 미준수를 보이게 한다
GRANDFATHERED = {
    "prereg_safety_score_20260809.json", "prereg_safety_score_20260809_diagnosis.json",
    "prereg_safety_score_full_20260810.json", "prereg_exclusion_gate_20260812.json",
    "prereg_formula_rebuild_20260812.json", "prereg_gate_strength_20260812.json",
    "prereg_portfolio_20260813.json", "prereg_transfer_diagnosis_20260814.json",
    "prereg_segment_ic_20260814.json", "prereg_segment_allocation_20260814.json",
    "prereg_dividend_total_return_20260815.json", "prereg_stoploss_20260815.json",
    "prereg_market_neutral_20260815.json",
}
CONTRACT_FROM = "2026-08-16"      # 이 날짜 이후 실행분부터 계약 적용


def _artifacts():
    return sorted(glob.glob(os.path.join(_DIR, "prereg_*.json")))


def test_new_artifacts_declare_score_system_and_power():
    """신규 사전등록 산출물은 ① 어떤 점수인지 ② 검출하한 을 반드시 신고한다."""
    missing = []
    for p in _artifacts():
        base = os.path.basename(p)
        if base in GRANDFATHERED:
            continue
        try:
            with open(p, encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            continue
        m = d.get("_meta") or {}
        when = str(m.get("executed_at") or "")
        if when and when[:10] < CONTRACT_FROM:
            continue
        if "score_system" not in m:
            missing.append(f"{base}: _meta.score_system 없음 — 어떤 점수를 쟀는지, "
                           "그게 운영에 쓰이는지 신고할 것 (prereg_contract.declare_score_system)")
        if "min_detectable" not in m:
            missing.append(f"{base}: _meta.min_detectable 없음 — |t|=3 검출하한 신고할 것 "
                           "(prereg_contract.declare_power). 판정력 없는 등록은 무의미하다")
    assert not missing, "사전등록 산출물 계약 위반:\n  " + "\n  ".join(missing)


def test_operational_score_registry_is_explicit():
    """운영 점수 목록이 코드에 명시돼 있어야 한다 — 암묵이면 다음 세션이 또 오독한다."""
    from api.quant.backtest.prereg_contract import (
        BACKTEST_ONLY_SCORES, OPERATIONAL_SCORES, declare_score_system,
    )
    assert "safety_pct" in OPERATIONAL_SCORES, "VAMS 게이트 점수가 등록돼 있어야 한다"
    assert "C3" in BACKTEST_ONLY_SCORES, "C3 는 백테스트 전용으로 표시돼야 한다"

    d = declare_score_system("C3", ["ep", "bp", "dy"])
    assert d["is_operational"] is False
    assert "do_not_read_as" in d, "비운영 점수는 오독 방지 문구를 달아야 한다"

    d2 = declare_score_system("safety_pct", ["drop", "debt"])
    assert d2["is_operational"] is True
    assert "do_not_read_as" not in d2


def test_power_declaration_flags_incapable_ledger():
    """검출하한이 현실 범위를 넘는 원장은 '판정 불가' 로 신고돼야 한다."""
    from api.quant.backtest.prereg_contract import declare_power

    # #368 실측 재현: 평균 −0.5418, t −0.66 → SE 0.82 → 검출하한 2.45%/월
    res = {"a_20d": {"mean_pct": -0.5418, "nw": {"t": -0.66}},
           "a_60d": {"mean_pct": -0.8837, "nw": {"t": -1.17}}}
    p = declare_power(res, plausible_max=1.0)
    assert p["median_floor"] > 1.0
    assert p["incapable_tests"], "판정 불가 검정이 목록으로 나와야 한다"
    assert "판정 불가" in p["verdict"]

    # 판정력 있는 경우 (#367 A1 수준: SE 0.18 → 하한 0.54)
    ok = {"b_20d": {"mean_pct": -0.2407, "nw": {"t": -1.34}}}
    p2 = declare_power(ok, plausible_max=1.0)
    assert p2["median_floor"] < 1.0
    assert not p2["incapable_tests"]


def test_grandfathered_list_is_documented_not_silent():
    """소급 면제 목록은 비어 있지 않아야 하고, 존재하는 파일만 담아야 한다.

    면제를 조용히 늘리는 것을 막는다 — 목록에 있는데 파일이 없으면 정리 대상이다.
    """
    present = {os.path.basename(p) for p in _artifacts()}
    stale = GRANDFATHERED - present
    assert not stale, f"면제 목록에 없는 파일이 남아 있다(정리 필요): {sorted(stale)}"
