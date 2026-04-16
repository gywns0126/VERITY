"""
팩터 수명(Decay) 모니터

학술 근거:
  - McLean & Pontiff (2016): 학술 논문 발표 후 팩터 수익률이 58% 감소
  - Chordia, Subrahmanyam & Tong (2014): 시장 이상현상의 수명은 유한
  - 팩터 크라우딩: 너무 많은 투자자가 같은 팩터를 쓰면 수익 감소

기능:
  1. IC 히스토리에서 팩터별 추세선(선형 회귀) 계산
  2. 구조적 붕괴 vs 일시적 부진 분류
  3. 팩터 교체 제안 → Strategy Evolver에 전달
  4. 텔레그램 경고 메시지 생성
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

import numpy as np

from api.config import DATA_DIR, now_kst


IC_CACHE_PATH = os.path.join(DATA_DIR, "factor_ic_history.json")


def _load_ic_history() -> List[Dict[str, Any]]:
    try:
        with open(IC_CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _linear_trend(values: List[float]) -> Dict[str, float]:
    """선형 회귀로 추세 기울기와 R² 계산."""
    n = len(values)
    if n < 3:
        return {"slope": 0, "r_squared": 0, "intercept": 0}

    x = np.arange(n, dtype=float)
    y = np.array(values, dtype=float)

    x_mean = np.mean(x)
    y_mean = np.mean(y)

    ss_xy = np.sum((x - x_mean) * (y - y_mean))
    ss_xx = np.sum((x - x_mean) ** 2)

    if ss_xx == 0:
        return {"slope": 0, "r_squared": 0, "intercept": float(y_mean)}

    slope = ss_xy / ss_xx
    intercept = y_mean - slope * x_mean

    y_pred = slope * x + intercept
    ss_res = np.sum((y - y_pred) ** 2)
    ss_tot = np.sum((y - y_mean) ** 2)
    r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0

    return {
        "slope": round(float(slope), 6),
        "r_squared": round(float(r_squared), 4),
        "intercept": round(float(intercept), 6),
    }


def analyze_factor_decay(
    min_history_days: int = 14,
    forward_days: int | None = None,
) -> Dict[str, Any]:
    """
    모든 팩터의 IC 추세를 분석하여 수명 상태를 판별.

    Args:
        min_history_days: 최소 필요 히스토리 일수
        forward_days: None이면 모든 윈도우 통합, 지정하면 해당 윈도우만 분석

    분류:
      - HEALTHY: IC 양수 + 추세 안정/상승
      - WEAKENING: IC 양수이나 하락 추세
      - DECAYING: IC가 0 근처로 수렴 (구조적 붕괴)
      - DEAD: IC 음수로 전환
      - EMERGING: 최근 IC가 급등 (새로운 알파 등장)
      - INSUFFICIENT: 데이터 부족
    """
    raw_history = _load_ic_history()

    if forward_days is not None:
        history = [h for h in raw_history if h.get("forward_days", 7) == forward_days]
    else:
        history = raw_history

    if len(history) < min_history_days:
        return {
            "status": "insufficient_data",
            "history_days": len(history),
            "min_required": min_history_days,
            "forward_days_filter": forward_days,
            "factors": {},
        }

    factor_names = set()
    for entry in history:
        factor_names.update(entry.get("factors", {}).keys())

    results: Dict[str, Dict[str, Any]] = {}

    for factor in factor_names:
        ic_values = []
        icir_values = []

        for entry in history:
            fd = entry.get("factors", {}).get(factor, {})
            ic = fd.get("ic_mean")
            icir = fd.get("icir")
            if ic is not None:
                ic_values.append(ic)
            if icir is not None:
                icir_values.append(icir)

        if len(ic_values) < 5:
            results[factor] = {
                "status": "INSUFFICIENT",
                "label": "데이터 부족",
                "ic_mean_all": 0,
                "ic_recent": 0,
                "trend": {},
            }
            continue

        ic_trend = _linear_trend(ic_values)
        ic_mean_all = float(np.mean(ic_values))
        ic_recent = float(np.mean(ic_values[-5:]))
        ic_earliest = float(np.mean(ic_values[:5]))

        status, label = _classify_decay(
            ic_mean_all, ic_recent, ic_earliest, ic_trend
        )

        results[factor] = {
            "status": status,
            "label": label,
            "ic_mean_all": round(ic_mean_all, 5),
            "ic_recent": round(ic_recent, 5),
            "ic_earliest": round(ic_earliest, 5),
            "trend": ic_trend,
            "sample_count": len(ic_values),
        }

    healthy = [k for k, v in results.items() if v["status"] == "HEALTHY"]
    weakening = [k for k, v in results.items() if v["status"] == "WEAKENING"]
    decaying = [k for k, v in results.items() if v["status"] in ("DECAYING", "DEAD")]
    emerging = [k for k, v in results.items() if v["status"] == "EMERGING"]

    return {
        "status": "ok",
        "history_days": len(history),
        "forward_days_filter": forward_days,
        "factors": results,
        "healthy_factors": healthy,
        "weakening_factors": weakening,
        "decaying_factors": decaying,
        "emerging_factors": emerging,
        "analyzed_at": now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
    }


def _classify_decay(
    ic_all: float,
    ic_recent: float,
    ic_early: float,
    trend: Dict[str, float],
) -> tuple:
    """팩터 수명 상태 분류."""
    slope = trend.get("slope", 0)
    r2 = trend.get("r_squared", 0)

    # DEAD: 최근 IC가 음수
    if ic_recent < -0.02:
        return "DEAD", f"IC 음수 전환 ({ic_recent:.4f}) — 팩터 무효"

    # EMERGING: 최근 IC가 급등
    if ic_recent > ic_early + 0.05 and ic_recent > 0.05:
        return "EMERGING", f"IC 급등 ({ic_early:.4f} → {ic_recent:.4f}) — 새 알파"

    # DECAYING: 추세적 하락 + 0 수렴
    if slope < -0.001 and r2 > 0.3 and ic_recent < 0.03:
        return "DECAYING", f"구조적 붕괴 (기울기 {slope:.5f}, IC→{ic_recent:.4f})"

    # WEAKENING: IC 양수이나 하락 추세
    if ic_all > 0.03 and ic_recent < ic_all * 0.6:
        return "WEAKENING", f"약화 중 (전체 {ic_all:.4f} → 최근 {ic_recent:.4f})"

    if slope < -0.0005 and ic_all > 0.02:
        return "WEAKENING", f"완만한 하락 (기울기 {slope:.5f})"

    # HEALTHY
    if ic_recent > 0.03:
        return "HEALTHY", f"유효 (IC {ic_recent:.4f})"

    return "NEUTRAL", f"중립 (IC {ic_recent:.4f})"


def compute_ic_weight_adjustments() -> Dict[str, Any]:
    """IC/ICIR 히스토리 기반 팩터별 가중치 multiplier 산출.

    Brain fact_score 가중치에 피드백되는 폐루프의 핵심 함수.
    7일 윈도우를 primary로 사용, 14/30일 윈도우가 있으면 교차 검증.
    상태별 multiplier:
      HEALTHY → 1.0, EMERGING → 1.15, NEUTRAL → 1.0,
      WEAKENING → 0.85, DECAYING → 0.6, DEAD → 0.3
    brain_score/safety_score 는 순환 참조 방지를 위해 제외.
    """
    decay_7d = analyze_factor_decay(forward_days=7)
    decay_14d = analyze_factor_decay(forward_days=14)
    decay_30d = analyze_factor_decay(forward_days=30)

    primary = decay_7d if decay_7d.get("status") == "ok" else None
    if primary is None:
        primary = decay_14d if decay_14d.get("status") == "ok" else None
    if primary is None:
        primary = decay_30d if decay_30d.get("status") == "ok" else None
    if primary is None:
        return {"status": "insufficient_data", "adjustments": {}, "log": []}

    _STATUS_MULT = {
        "HEALTHY": 1.0,
        "EMERGING": 1.15,
        "NEUTRAL": 1.0,
        "WEAKENING": 0.85,
        "DECAYING": 0.6,
        "DEAD": 0.3,
        "INSUFFICIENT": 1.0,
    }

    _EXCLUDE = {"brain_score", "safety_score"}

    aux_reports = {}
    for label, rpt in [("14d", decay_14d), ("30d", decay_30d)]:
        if rpt.get("status") == "ok":
            aux_reports[label] = rpt.get("factors", {})

    adjustments: Dict[str, Dict[str, Any]] = {}
    log: List[str] = []

    for factor, info in primary.get("factors", {}).items():
        if factor in _EXCLUDE:
            continue
        status = info.get("status", "NEUTRAL")
        mult = _STATUS_MULT.get(status, 1.0)

        ic_recent = info.get("ic_recent", 0)
        if ic_recent > 0.10:
            mult = min(mult * 1.05, 1.20)
        elif ic_recent < -0.03:
            mult = min(mult, 0.50)

        cross_check = {}
        for label, aux_factors in aux_reports.items():
            aux = aux_factors.get(factor, {})
            if aux:
                cross_check[label] = {
                    "status": aux.get("status", "?"),
                    "ic_recent": round(float(aux.get("ic_recent", 0)), 5),
                }

        adjustments[factor] = {
            "multiplier": round(float(mult), 3),
            "status": status,
            "ic_recent": round(float(ic_recent), 5),
        }
        if cross_check:
            adjustments[factor]["cross_window"] = cross_check

        if mult != 1.0:
            log.append(f"{factor}: {status} (IC {ic_recent:.4f}) → x{mult:.2f}")

    return {
        "status": "ok",
        "primary_window": primary.get("forward_days_filter", 7),
        "adjustments": adjustments,
        "log": log,
        "computed_at": now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
    }


def generate_decay_alerts(
    decay_report: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """
    팩터 수명 분석 결과에서 텔레그램/Strategy Evolver용 경고 생성.
    """
    if decay_report is None:
        decay_report = analyze_factor_decay()

    if decay_report.get("status") != "ok":
        return []

    alerts: List[Dict[str, Any]] = []

    for factor, info in decay_report.get("factors", {}).items():
        status = info.get("status", "")

        if status == "DECAYING":
            alerts.append({
                "level": "critical",
                "factor": factor,
                "message": f"팩터 '{factor}' 구조적 붕괴 감지 — 가중치 축소 또는 교체 필요",
                "detail": info.get("label", ""),
                "action": "reduce_weight",
            })
        elif status == "DEAD":
            alerts.append({
                "level": "critical",
                "factor": factor,
                "message": f"팩터 '{factor}' IC 음수 — 즉시 비활성화 권장",
                "detail": info.get("label", ""),
                "action": "disable",
            })
        elif status == "WEAKENING":
            alerts.append({
                "level": "warning",
                "factor": factor,
                "message": f"팩터 '{factor}' 약화 추세 — 모니터링 강화",
                "detail": info.get("label", ""),
                "action": "monitor",
            })
        elif status == "EMERGING":
            alerts.append({
                "level": "info",
                "factor": factor,
                "message": f"팩터 '{factor}' 새 알파 감지 — 가중치 상향 검토",
                "detail": info.get("label", ""),
                "action": "increase_weight",
            })

    alerts.sort(key=lambda x: {"critical": 0, "warning": 1, "info": 2}.get(x["level"], 3))
    return alerts
