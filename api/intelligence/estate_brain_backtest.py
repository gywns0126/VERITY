"""
ESTATE Brain V0.2 backward 검증 — 권역 단위 retrospective.

V0 forward 검증 (운영 누적 6-12M) 단축 path:
  ① cycle_analog 정합성: 1997/2008/2022 plan 가정 vs 실측 R-ONE 시계열 drop
  ② 미분양 yoy +30% 신호 → 6M 후 가격 변동 lead time hit rate
  ③ 권역 단위 weighted_score IC (V1 게이트 — KOSIS/전세 statId 박힌 후)

source: plan v0.2 §운영 검증 (1-2개월/3-6개월/12개월 단계 검증).
       feedback_real_call_over_llm_consensus 정합 — 실 R-ONE 시계열로 plan LLM 가정 검증.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple


# ────────────────────────────────────────────────────────────
# 시계열 산식 — forward return / drop from peak

def compute_forward_return_pct(
    series: List[Dict[str, Any]],
    horizon_weeks: int = 52,
    value_key: str = "index",
) -> List[Optional[float]]:
    """각 시점 t 의 t+horizon_weeks return (%). 시계열 끝부분 horizon 만큼 None."""
    n = len(series)
    out: List[Optional[float]] = [None] * n
    for i in range(n - horizon_weeks):
        a = series[i].get(value_key)
        b = series[i + horizon_weeks].get(value_key)
        if a and a > 0 and b is not None:
            out[i] = round((b - a) / a * 100, 2)
    return out


def compute_drop_from_peak_pct(
    series: List[Dict[str, Any]],
    value_key: str = "index",
) -> Optional[float]:
    """peak → trough 최대 drop (%). cycle_analog drop_seoul_pct 정합 검증."""
    if not series:
        return None
    values = [s.get(value_key) for s in series if s.get(value_key) is not None]
    if len(values) < 2:
        return None
    peak = max(values)
    if peak <= 0:
        return None
    trough = min(values)
    return round((trough - peak) / peak * 100, 2)


# ────────────────────────────────────────────────────────────
# Cycle Analog 정합성 검증

# Period 라벨 → Plan 패턴명 매핑 (plan v0.2 §3 cycle analog)
_PERIOD_TO_PATTERN: Dict[str, str] = {
    "1997": "Shock-Recovery",
    "2008": "Debt-Deflation Drag",
    "2022": "Rate-Shock Rebound",
}


def validate_cycle_analog(
    actual_drops_by_period: Dict[str, float],
    plan_drops_by_pattern: Dict[str, float],
    tolerance_pct: float = 5.0,
) -> Dict[str, Any]:
    """plan v0.2 cycle_analog drop_pct vs 실측 R-ONE.

    actual: {"1997": -18.5, "2008": -12.5, "2022": -19.0}
    plan:   {"Shock-Recovery": -18.2, "Debt-Deflation Drag": -12.0, "Rate-Shock Rebound": -20.0}
    """
    result: Dict[str, Any] = {}
    for period, actual in actual_drops_by_period.items():
        pattern = _PERIOD_TO_PATTERN.get(period)
        if not pattern:
            continue
        plan = plan_drops_by_pattern.get(pattern)
        if plan is None:
            continue
        diff = actual - plan
        result[pattern] = {
            "period": period,
            "actual_drop_pct": round(actual, 2),
            "plan_drop_pct": round(plan, 2),
            "diff_pct": round(diff, 2),
            "within_tolerance": abs(diff) <= tolerance_pct,
            "tolerance_pct": tolerance_pct,
        }
    return result


# ────────────────────────────────────────────────────────────
# 신호 retrospective — 미분양 yoy + (V1) PIR z / 전세가율 / Cap 역전

def detect_unsold_yoy_signal(
    unsold_series: List[Dict[str, Any]],
    t_idx: int,
    threshold_yoy_pct: float = 30.0,
    value_key: str = "unsold",
) -> bool:
    """시점 t 의 미분양 12M YoY ≥ threshold → 발현 (lead 3-6M, plan v0.2)."""
    if t_idx < 12 or t_idx >= len(unsold_series):
        return False
    current = unsold_series[t_idx].get(value_key)
    prior = unsold_series[t_idx - 12].get(value_key)
    if current is None or prior is None or prior <= 0:
        return False
    yoy = (current - prior) / prior * 100
    return yoy >= threshold_yoy_pct


def compute_signal_hit_rate(
    signal_events: List[bool],
    future_returns: List[Optional[float]],
    direction: str = "negative",
    threshold_pct: float = -5.0,
) -> Dict[str, Any]:
    """신호 발현 시점 → forward return hit rate.

    direction='negative': return ≤ threshold (예: -5% 이하) → hit (가격 하락 적중)
    direction='positive': return ≥ threshold → hit
    """
    n = min(len(signal_events), len(future_returns))
    triggered: List[Tuple[int, float]] = [
        (i, future_returns[i]) for i in range(n)
        if signal_events[i] and future_returns[i] is not None
    ]
    if not triggered:
        return {
            "trigger_count": 0, "hit_count": 0,
            "hit_rate_pct": None, "mean_return_pct": None,
            "threshold_pct": threshold_pct, "direction": direction,
        }

    if direction == "negative":
        hits = sum(1 for _, r in triggered if r <= threshold_pct)
    elif direction == "positive":
        hits = sum(1 for _, r in triggered if r >= threshold_pct)
    else:
        raise ValueError(f"unknown direction: {direction}")

    mean_ret = sum(r for _, r in triggered) / len(triggered)
    return {
        "trigger_count": len(triggered),
        "hit_count": hits,
        "hit_rate_pct": round(hits / len(triggered) * 100, 1),
        "mean_return_pct": round(mean_ret, 2),
        "threshold_pct": threshold_pct,
        "direction": direction,
    }


# ────────────────────────────────────────────────────────────
# Spearman rank IC (landex_meta_validation 패턴 정합 — 자체 구현)
# scripts/ 가 패키지 X 라 동일 산식 자체 박음. n=25 (서울 구) 표본 가정.

def compute_ic(
    scores: List[Optional[float]],
    returns: List[Optional[float]],
) -> Tuple[Optional[float], Optional[float]]:
    """Spearman rank IC + p-value. n<3 시 (None, None)."""
    valid = [(s, r) for s, r in zip(scores, returns)
             if s is not None and r is not None]
    n = len(valid)
    if n < 3:
        return None, None
    s_vals = [v[0] for v in valid]
    r_vals = [v[1] for v in valid]
    s_ranks = _rankdata(s_vals)
    r_ranks = _rankdata(r_vals)
    mean_s = sum(s_ranks) / n
    mean_r = sum(r_ranks) / n
    cov = sum((s_ranks[i] - mean_s) * (r_ranks[i] - mean_r) for i in range(n)) / n
    var_s = sum((x - mean_s) ** 2 for x in s_ranks) / n
    var_r = sum((x - mean_r) ** 2 for x in r_ranks) / n
    if var_s == 0 or var_r == 0:
        return 0.0, 1.0
    rho = cov / ((var_s * var_r) ** 0.5)
    rho = max(-1.0, min(1.0, rho))
    if n > 2 and abs(rho) < 1.0:
        t = rho * ((n - 2) / max(1e-12, 1 - rho ** 2)) ** 0.5
        p = _two_sided_pvalue_t(t, n - 2)
    else:
        p = 0.0 if abs(rho) >= 1.0 else 1.0
    return round(rho, 4), round(p, 4)


def _rankdata(values: List[float]) -> List[float]:
    n = len(values)
    sorted_pairs = sorted(enumerate(values), key=lambda x: x[1])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and sorted_pairs[j + 1][1] == sorted_pairs[i][1]:
            j += 1
        avg_rank = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[sorted_pairs[k][0]] = avg_rank
        i = j + 1
    return ranks


def _two_sided_pvalue_t(t: float, df: int) -> float:
    """t-분포 양측 p-value 근사 (n>=10 정확도 OK, df>30 정규 근사)."""
    if df <= 0:
        return 1.0
    if df > 30:
        z_eq = abs(t)
    else:
        # df 10-30 보정
        z_eq = abs(t) * (1 - 1 / (4 * df))
    # 양측: 2 * (1 - Phi(z_eq))
    p = 2 * (1 - 0.5 * (1 + math.erf(z_eq / math.sqrt(2))))
    return max(0.0, min(1.0, p))


# ────────────────────────────────────────────────────────────
# Quintile spread (Q5 - Q1)

def compute_quintile_spread(
    scores: List[Optional[float]],
    returns: List[Optional[float]],
) -> Optional[Dict[str, float]]:
    """score 5분위 (Q1=하위 20% / Q5=상위 20%) 의 평균 forward return.

    Q5 - Q1 spread > 0 → score 가 forward return 예측력 있음.
    n<5 시 None (분위 분할 불가능).
    """
    valid = [(s, r) for s, r in zip(scores, returns)
             if s is not None and r is not None]
    n = len(valid)
    if n < 5:
        return None
    valid.sort(key=lambda x: x[0])
    q_size = n // 5
    if q_size == 0:
        return None
    q1 = valid[:q_size]
    q5 = valid[-q_size:]
    q1_mean = sum(r for _, r in q1) / len(q1)
    q5_mean = sum(r for _, r in q5) / len(q5)
    return {
        "q1_mean_return_pct": round(q1_mean, 2),
        "q5_mean_return_pct": round(q5_mean, 2),
        "spread_pct": round(q5_mean - q1_mean, 2),
        "q_size": q_size,
        "n_total": n,
    }
