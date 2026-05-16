"""grade_distribution_drift — Brain grade 분포 drift 자동 감지 (PSI 기반).

연관:
  - audit BRAIN_SELF_GROWTH P1-3 (continuous_evolution Guard 3)
  - Perplexity NQ3 (2026-05-16): PSI 1순위 권장, KS는 N 큼 시 오탐
  - feedback_continuous_evolution (4가드 — Guard 3 = 모니터링)

PSI 표준 임계:
  PSI < 0.10  안정 (Stable) — 모니터링 유지
  0.10-0.25  중간 변동 (Moderate) — 원인 분석 시작
  PSI ≥ 0.25 중대 변동 (Major shift) — 시스템 재보정

이중 조건 (NQ3):
  PSI 단독 fail → 자연 regime shift 가능성 → regime flag (VIX/외인/USD-KRW) 확인
  Regime flag ≥ 2개 동시 → 자연 shift 인정, 4주 유예
  Regime flag < 2개 → 결함성 drift 가정, 재보정 alert
"""
from __future__ import annotations

import json
import math
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from api.config import DATA_DIR, now_kst
from api.metadata.brain_learning import load_signals

LEDGER_PATH = os.path.join(DATA_DIR, "metadata", "grade_drift_log.jsonl")
GRADES = ("STRONG_BUY", "BUY", "WATCH", "CAUTION", "AVOID")


def _normalize_grade_dist(dist: Dict[str, int]) -> Dict[str, float]:
    """등급 카운트 → 비중 (합 1.0)."""
    total = sum(dist.get(g, 0) for g in GRADES)
    if total == 0:
        return {g: 0.0 for g in GRADES}
    return {g: dist.get(g, 0) / total for g in GRADES}


def compute_psi(baseline_dist: Dict[str, int], current_dist: Dict[str, int]) -> float:
    """PSI (Population Stability Index) — 등급 비중 안정성 측정.

    PSI = Σ (p_curr - p_base) × ln(p_curr / p_base)

    bin 비중이 0 이면 0.0001 로 smoothing (ln 발산 회피).
    """
    base_p = _normalize_grade_dist(baseline_dist)
    curr_p = _normalize_grade_dist(current_dist)
    psi = 0.0
    for g in GRADES:
        p_base = max(base_p[g], 0.0001)
        p_curr = max(curr_p[g], 0.0001)
        psi += (p_curr - p_base) * math.log(p_curr / p_base)
    return round(psi, 4)


def compute_grade_share_diff(
    baseline_dist: Dict[str, int], current_dist: Dict[str, int],
) -> Dict[str, float]:
    """등급별 비중 차이 (%p) — 어느 등급이 가장 크게 변동했나."""
    base_p = _normalize_grade_dist(baseline_dist)
    curr_p = _normalize_grade_dist(current_dist)
    return {g: round((curr_p[g] - base_p[g]) * 100, 2) for g in GRADES}


def detect_regime_flags(portfolio: Dict[str, Any]) -> List[str]:
    """외생 regime flag 감지 (NQ3 권장).

    Regime flag (자연 shift 가능성):
    - VIX 주간 변화 > ±5pt
    - 외국인 수급 변화 (placeholder — 데이터 source 큐)
    - USD/KRW 주간 ±2%
    - market_horizon cycle = panic/capitulation/euphoria
    """
    flags: List[str] = []
    macro = portfolio.get("macro") or {}

    vix = (macro.get("vix") or {}).get("value")
    vix_chg = (macro.get("vix") or {}).get("change_pct")
    if vix_chg is not None:
        try:
            if abs(float(vix_chg)) > 25:  # weekly VIX 변화 추정 (일변동의 ~5배)
                flags.append(f"VIX 급변 {vix_chg:+.1f}%")
        except (TypeError, ValueError):
            pass

    fx_chg = (macro.get("usd_krw") or {}).get("change_pct")
    if fx_chg is not None:
        try:
            if abs(float(fx_chg)) > 2.0:
                flags.append(f"USD/KRW {fx_chg:+.2f}%")
        except (TypeError, ValueError):
            pass

    mh = portfolio.get("market_horizon") or {}
    cycle = mh.get("cycle_stage")
    if cycle in ("panic", "capitulation", "euphoria"):
        flags.append(f"cycle={cycle}")

    return flags


def evaluate_grade_drift(
    portfolio: Dict[str, Any],
    baseline_days: int = 52 * 7,  # 52주 = 1년
    current_days: int = 7,  # 최근 1주
) -> Dict[str, Any]:
    """grade 분포 drift 평가 — PSI + regime 분리 (P1-3 Guard 3).

    Returns:
        {
            "psi": float,
            "psi_tier": "stable" / "moderate" / "major",
            "share_diff": {grade: %p change, ...},
            "regime_flags": [...],
            "regime_classified": "natural_shift" / "defect_drift" / "monitor",
            "alert_level": "ok" / "watch" / "alert",
            "reason": str,
        }
    """
    sigs = load_signals(baseline_days)
    if len(sigs) < 10:
        return {
            "psi": 0.0, "psi_tier": "insufficient",
            "alert_level": "ok",
            "reason": f"baseline samples {len(sigs)} < 10 — 평가 불가",
        }

    # baseline = 가장 오래된 ~ 가장 최근 - current_days
    baseline_sigs = sigs[:-current_days] if len(sigs) > current_days else sigs
    current_sigs = sigs[-current_days:]
    if not baseline_sigs or not current_sigs:
        return {"psi": 0.0, "psi_tier": "insufficient", "alert_level": "ok",
                "reason": "baseline 또는 current 분리 불가"}

    # 평균 distribution 계산
    def _avg_dist(sigs_list: List[Dict[str, Any]]) -> Dict[str, int]:
        total = {g: 0 for g in GRADES}
        for s in sigs_list:
            d = s.get("grade_distribution") or {}
            for g in GRADES:
                total[g] += d.get(g, 0)
        return total

    baseline_dist = _avg_dist(baseline_sigs)
    current_dist = _avg_dist(current_sigs)
    psi = compute_psi(baseline_dist, current_dist)
    share_diff = compute_grade_share_diff(baseline_dist, current_dist)

    # PSI tier (Perplexity NQ3 verdict)
    if psi < 0.10:
        psi_tier = "stable"
    elif psi < 0.25:
        psi_tier = "moderate"
    else:
        psi_tier = "major"

    # Regime flags
    regime_flags = detect_regime_flags(portfolio)
    regime_count = len(regime_flags)

    # Regime 분리 (NQ3): flag ≥ 2 → 자연 shift / < 2 → 결함 drift
    if regime_count >= 2:
        regime_classified = "natural_shift"
    elif psi >= 0.10:
        regime_classified = "defect_drift"
    else:
        regime_classified = "stable"

    # Alert level 결정
    # 단일 등급 비중 ±5%p 이상 (NQ3 이중 조건)
    max_share_change = max(abs(v) for v in share_diff.values())
    big_share_shift = max_share_change >= 5.0

    if psi >= 0.25 and regime_classified == "defect_drift":
        alert_level = "alert"  # 즉시 재보정 검토
    elif psi >= 0.10 and big_share_shift and regime_count < 2:
        alert_level = "watch"  # 원인 분석 시작
    elif regime_count >= 2:
        alert_level = "ok"  # 자연 shift 유예
    else:
        alert_level = "ok"

    reason = (
        f"PSI={psi:.3f} ({psi_tier}) / max 비중 변화 {max_share_change:.1f}%p / "
        f"regime flags={regime_count} ({', '.join(regime_flags) if regime_flags else 'none'}) "
        f"→ {regime_classified} / alert={alert_level}"
    )

    return {
        "psi": psi,
        "psi_tier": psi_tier,
        "share_diff": share_diff,
        "max_share_change_pp": max_share_change,
        "regime_flags": regime_flags,
        "regime_count": regime_count,
        "regime_classified": regime_classified,
        "alert_level": alert_level,
        "baseline_samples": len(baseline_sigs),
        "current_samples": len(current_sigs),
        "reason": reason,
    }


def log_drift_evaluation(eval_result: Dict[str, Any]) -> None:
    """drift 평가 결과 ledger 적재."""
    try:
        os.makedirs(os.path.dirname(LEDGER_PATH), exist_ok=True)
        entry = {
            "ts_kst": now_kst().isoformat(),
            **eval_result,
        }
        with open(LEDGER_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        import sys
        sys.stderr.write(f"[grade_drift] ledger 적재 실패: {e}\n")
