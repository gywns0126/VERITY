# -*- coding: utf-8 -*-
"""prereg_contract — 사전등록 산출물이 **스스로 신고해야 하는 것**.

2026-08-15 신설. 하루에 같은 실패가 세 번 났고 원인이 하나였다 —
**한 세션이 아는 것이 다음 세션으로 넘어가지 않는다.**

```
252 게이트 폐기   대화에만 존재      → 다음 세션이 죽은 전제를 하루 종일 인용
검정력 계산       8/9~8/10 하다 소멸  → 3일 만에 규율 퇴화, 아무도 눈치 못 챔
C3 ≠ 운영 점수    코드에만 암묵       → 운영과 무관한 점수를 6개월치라 믿고 검정
```

기억·습관·체크리스트로는 안 막힌다. **산출물이 자기 입으로 말하게** 해야 한다
([[feedback_verify_by_load_bearing_not_surprise]] 의 "숨기면 결국 안 돌린다" 와 같은 원리).

이 모듈은 두 가지를 강제한다:
  ① `score_system`  — 어떤 점수를 쟀는지 + **그게 운영에 쓰이는 것인지**
  ② `min_detectable` — |t|=3 을 만드는 효과 크기. 이게 현실 범위 밖이면 그 등록은 무의미하다

`tests/test_prereg_artifact_contract.py` 가 신규 산출물에 대해 이 계약을 검사한다.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Optional, Sequence

# 🚨 운영이 실제로 쓰는 점수 (2026-08-15 grep 실측)
#    · safety_pct(안심점수 6축) → VAMS 게이트 `safety_pct >= GATE_BOTTOM_PCT` (8/12 컷오버)
#    · fact_score / sentiment_score / VCI → Brain 판단·사이트 노출
#    C3(ep bp dy opm roa vol fs8 illiq nearhigh) 는 **백테스트 전용**이며 운영 경로에 없다.
OPERATIONAL_SCORES = frozenset({"safety_pct", "fact_score", "sentiment_score", "vci"})
BACKTEST_ONLY_SCORES = frozenset({"C3", "c3", "safety_full", "formula_rebuild"})


def declare_score_system(name: str, axes: Sequence[str], note: str = "") -> Dict[str, Any]:
    """이 등록이 어떤 점수를 쟀는지, 그게 운영에 쓰이는지 산출물에 명시한다.

    🚨 `is_operational=False` 면 결과를 운영 판단으로 옮겨 읽으면 안 된다.
       2026-08-13~15 등록 9건이 전부 C3(백테스트 전용)를 쟀는데 그 사실이 어디에도
       적혀 있지 않아, 다음 세션이 "우리 점수는 검증됐다" 로 오독할 수 있었다.
    """
    op = name in OPERATIONAL_SCORES
    d: Dict[str, Any] = {
        "name": name,
        "axes": list(axes),
        "is_operational": op,
        "note": note or ("운영 경로에서 사용" if op
                         else "🚨 백테스트 전용 — 운영은 이 점수를 쓰지 않는다"),
    }
    if not op:
        d["do_not_read_as"] = ("이 결과를 '우리 시스템이 검증됐다' 로 읽지 말 것. "
                               f"운영 점수는 {sorted(OPERATIONAL_SCORES)} 이다")
    return d


def detectable_floor(mean_pct: Optional[float], t: Optional[float],
                     t_target: float = 3.0) -> Optional[float]:
    """|t| = t_target 을 만드는 효과 크기. SE = |mean/t| 에서 역산."""
    if mean_pct is None or not t:
        return None
    return round(abs(mean_pct / t) * t_target, 4)


def declare_power(results: Dict[str, Any], plausible_max: float,
                  unit: str = "%/월") -> Dict[str, Any]:
    """원장 전체의 검정력을 신고한다. **판정력 없는 등록은 등록 자체가 무의미하다.**

    Args:
        results: {검정명: {"mean_pct":…, "nw": {"t":…}}} 형태
        plausible_max: 이 도메인에서 현실적인 효과 크기 상한. 검출하한이 이를 넘으면
                       그 검정은 어떤 결과도 낼 수 없다(= "무유의" 가 정보가 아니다).
    """
    floors: Dict[str, Optional[float]] = {}
    for k, v in (results or {}).items():
        t = (v.get("nw") or {}).get("t") if isinstance(v, dict) else None
        floors[k] = detectable_floor(v.get("mean_pct") if isinstance(v, dict) else None, t)
    vals = [f for f in floors.values() if f is not None]
    med = sorted(vals)[len(vals) // 2] if vals else None
    incapable = [k for k, f in floors.items() if f is not None and f > plausible_max]
    return {
        "unit": unit,
        "t_target": 3.0,
        "plausible_max": plausible_max,
        "per_test_floor": floors,
        "median_floor": med,
        "incapable_tests": incapable,
        "verdict": ("🚨 판정 불가 — 검출하한이 현실적 효과 범위를 넘는다. "
                    "이 등록의 '무유의' 는 세상에 대한 정보가 아니라 자의 눈금 문제다"
                    if med is not None and med > plausible_max else
                    ("경계 — 일부 검정만 판정력이 있다" if incapable else "판정력 있음")),
    }


def contract(score: Dict[str, Any], power: Dict[str, Any]) -> Dict[str, Any]:
    """산출물 `_meta` 에 넣을 계약 블록."""
    return {"score_system": score, "min_detectable": power,
            "contract_version": "2026-08-15"}
