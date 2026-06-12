"""sqn — System Quality Number (Van Tharp).

학술 source:
  - Van Tharp (1998) "Trade Your Way to Financial Freedom" McGraw-Hill
  - Van Tharp "The Definitive Guide to Position Sizing" (SQN 정의 원전)

PM 사전등록: [[project_b4_sprint_tools_2026_05_27]] (2026-05-27).
B4 sprint 진입 (2026-06-12) 구현. R-multiple base = [[project_r_multiple_exit]].

산식 (사전등록 그대로):
    SQN = (mean(R) / std(R)) × √N
    R = R-multiple per trade (실현 손익 / 초기 리스크 1R)
    N = trade 수

Van Tharp 평가 밴드 (사전등록 그대로):
    < 1.6        below_poor   (시스템 거래 부적합)
    1.6 ~ 1.9    poor
    2.0 ~ 2.4    average
    2.5 ~ 2.9    good
    3.0 ~ 5.0    excellent
    > 5.0        holy_grail

주의: N 이 크면 √N 항이 SQN 을 기계적으로 키움 — Van Tharp 본인도
N=100 기준 비교 (SQN-100) 병기 권장. 본 모듈 = 둘 다 반환.
N < 10 = 통계 무의미 ([[project_minimum_n_milestones_2026_05_18]] 정합) — verdict 에 명시.

RULE 7 정합: infrastructure (analyzer, 산식 자체 X).
"""
from __future__ import annotations

import math
from typing import Dict, Sequence

__all__ = ["compute_sqn", "SQN_BANDS"]

SQN_BANDS = [
    (1.6, "below_poor"),
    (2.0, "poor"),
    (2.5, "average"),
    (3.0, "good"),
    (5.0, "excellent"),
    (float("inf"), "holy_grail"),
]

_MIN_N_STATISTICAL = 10


def _band(sqn: float) -> str:
    for upper, name in SQN_BANDS:
        if sqn < upper:
            return name
    return "holy_grail"


def compute_sqn(r_multiples: Sequence[float]) -> Dict:
    """SQN = mean(R)/std(R) × √N + Van Tharp 밴드.

    Args:
        r_multiples: trade 별 R-multiple 목록 (실현 trades only).

    Returns:
        {
          "sqn": float|None,        # √N 버전 (원 산식)
          "sqn_100": float|None,    # √min(N,100) 버전 (Van Tharp 비교 표준)
          "band": str|None,         # Van Tharp 밴드 (sqn 기준)
          "n": int,
          "mean_r": float|None,
          "std_r": float|None,
          "statistically_meaningful": bool,   # N >= 10
          "_note": str|None,
        }

    Edge: N < 2 또는 std=0 → sqn None (거짓확실성 차단, psr.py None 패턴 정합).
    """
    rs = [float(r) for r in r_multiples if r is not None and math.isfinite(float(r))]
    n = len(rs)
    if n < 2:
        return {
            "sqn": None, "sqn_100": None, "band": None, "n": n,
            "mean_r": rs[0] if n == 1 else None, "std_r": None,
            "statistically_meaningful": False,
            "_note": "N < 2 — SQN 산출 불가",
        }

    mean_r = sum(rs) / n
    var = sum((r - mean_r) ** 2 for r in rs) / (n - 1)
    std_r = math.sqrt(var)
    if std_r == 0:
        return {
            "sqn": None, "sqn_100": None, "band": None, "n": n,
            "mean_r": round(mean_r, 4), "std_r": 0.0,
            "statistically_meaningful": n >= _MIN_N_STATISTICAL,
            "_note": "std(R)=0 (상수 R) — SQN 정의 불가 (거짓확실성 차단)",
        }

    sqn = (mean_r / std_r) * math.sqrt(n)
    sqn_100 = (mean_r / std_r) * math.sqrt(min(n, 100))
    meaningful = n >= _MIN_N_STATISTICAL
    return {
        "sqn": round(sqn, 4),
        "sqn_100": round(sqn_100, 4),
        "band": _band(sqn),
        "n": n,
        "mean_r": round(mean_r, 4),
        "std_r": round(std_r, 4),
        "statistically_meaningful": meaningful,
        "_note": None if meaningful else f"N={n} < {_MIN_N_STATISTICAL} — 통계 무의미 (예비값)",
    }
