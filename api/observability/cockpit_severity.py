"""Cockpit severity — 3-tier 통합 룰 (RED/YELLOW/GREEN).

PM=approved 2026-05-23 (plan `/Users/macbookpro/.claude/plans/1-tidy-breeze.md` §Phase 0-c).
WHY: 11 ledger 분산 → 단일 operator 시야 통합. severity 산식 분산 → 단일 source.
DATA: cron_health.severity / data_health.core_sources_ok / operator_deadman.trigger /
      kis_lock_commits_24h / fred staleness / dispatch_chain_summary 등 합성.
EXPECTED: scripts/cockpit_aggregate.py 가 11 ledger 입력 dict 박음 → evaluate() 호출
          → severity(GREEN/YELLOW/RED) + severity_reasons[] 박음.

자기 산식 규율 ([[feedback_methodology_pre_registration]]):
- 룰 변경 = 1회만, PM 승인 의무 (RULE 7).
- 신규 룰 추가 시 commit message PM=approved + WHY/DATA/EXPECTED 박음.

source: [[project_win_condition_decision]] option 2, plan PM 승인 2026-05-23.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple


# ── RED triggers (단일 만족 시 즉시 RED) ─────────────────────────
def _check_red(inputs: Dict[str, Any]) -> List[str]:
    reasons: List[str] = []

    # KIS lock commits 24h ≥ 3 (RULE 1 위반 시그널, 5/16 폭주 학습)
    kis_lock = inputs.get("kis_lock_commits_24h")
    if isinstance(kis_lock, (int, float)) and kis_lock >= 3:
        reasons.append(f"KIS lock commits 24h={int(kis_lock)} (≥3, RULE 1 risk)")

    # operator_deadman maintenance trigger
    odm = inputs.get("operator_deadman") or {}
    if odm.get("trigger") == "maintenance":
        reasons.append("operator_deadman maintenance 진입")

    # core_sources_ok=false 24h 누적 (data_health)
    data_health = inputs.get("data_health") or {}
    if data_health.get("core_sources_ok") is False:
        reasons.append("data_health.core_sources_ok=false")

    # 신규 P0 postmortem 24h+ 미박힘 (open_p0_p1 list 박혔지만 24h 지남)
    open_p0 = inputs.get("open_p0_aged_24h", []) or []
    if isinstance(open_p0, list) and len(open_p0) > 0:
        reasons.append(f"P0 postmortem 24h+ 미박힘 ×{len(open_p0)}")

    # 2026-05-29 추가 — infra_status RED tier 룰
    infra = inputs.get("infra_status") or {}
    providers = infra.get("providers") or []
    alert_providers = [p for p in providers if p.get("status") == "ALERT"]

    # 단일 billing/payment 관련 ALERT → 즉시 RED
    for p in alert_providers:
        detail = (p.get("detail") or "").lower()
        if any(kw in detail for kw in ["payment", "spending", "billing", "rate limit"]):
            reasons.append(f"infra ALERT {p.get('provider')}: {p.get('detail','')[:80]}")

    # ALERT 2개 이상 동시 → RED (인프라 다중 사고)
    if len(alert_providers) >= 2:
        provider_names = ", ".join(p.get("provider", "?") for p in alert_providers)
        reasons.append(f"infra 다중 ALERT ×{len(alert_providers)} ({provider_names})")

    # LLM budget ALERT (월 $20 초과) → RED
    for p in alert_providers:
        if p.get("provider") == "LLM Budget":
            reasons.append(f"LLM Budget 한도 초과: {p.get('detail','')[:80]}")

    return reasons


# ── YELLOW triggers (warning) ─────────────────────────────────
def _check_yellow(inputs: Dict[str, Any]) -> List[str]:
    reasons: List[str] = []

    # KIS lock = 2 (RULE 1 임박)
    kis_lock = inputs.get("kis_lock_commits_24h")
    if isinstance(kis_lock, (int, float)) and kis_lock == 2:
        reasons.append(f"KIS lock commits 24h=2 (임박, RULE 1)")

    # FRED stale (fred_age_h > 6h)
    fred_age = inputs.get("fred_age_h")
    if isinstance(fred_age, (int, float)) and fred_age > 6:
        reasons.append(f"FRED stale {fred_age:.1f}h (>6h)")

    # dispatch_chain ratio < 80%
    dispatch = inputs.get("dispatch_chain_ratio")
    if isinstance(dispatch, (int, float)) and 0 <= dispatch < 0.8:
        reasons.append(f"dispatch_chain ratio {dispatch*100:.0f}% (<80%)")

    # pre_registration_pending ≥ 1 (7d+) — Phase 1 placeholder, Phase 0 = 0
    pre_reg = inputs.get("pre_registration_pending", []) or []
    if isinstance(pre_reg, list) and len(pre_reg) >= 1:
        reasons.append(f"pre_registration pending ×{len(pre_reg)} (7d+)")

    # feature_drift warning
    if inputs.get("feature_drift_warning"):
        reasons.append("feature_drift warning 박힘")

    # brain anomaly ≥ 3 (brain_audit 24h 내 anomaly)
    brain_anom = inputs.get("brain_anomaly_24h")
    if isinstance(brain_anom, (int, float)) and brain_anom >= 3:
        reasons.append(f"brain anomaly 24h={int(brain_anom)} (≥3)")

    # rule7_quota EXCEEDED (분기 산식 변경 4회 초과 = 확증편향 risk, 2026-05-29)
    quota = inputs.get("rule7_quota") or {}
    if quota.get("status") == "EXCEEDED":
        reasons.append(
            f"rule7_quota {quota.get('quarter')} "
            f"{quota.get('count')}/{quota.get('limit')} EXCEEDED"
        )

    return reasons


def evaluate(inputs: Dict[str, Any]) -> Tuple[str, List[str]]:
    """11 ledger 입력 dict → (severity, severity_reasons).

    Args:
        inputs: cockpit_aggregate.py 가 박은 정규화 dict.
            예상 키: kis_lock_commits_24h / operator_deadman / data_health /
            fred_age_h / dispatch_chain_ratio / open_p0_aged_24h /
            pre_registration_pending / feature_drift_warning / brain_anomaly_24h

    Returns:
        ("GREEN" | "YELLOW" | "RED", reasons[])

    룰 우선순위: RED > YELLOW > GREEN. 단일 RED 만족 시 즉시 RED.
    """
    red_reasons = _check_red(inputs)
    if red_reasons:
        return "RED", red_reasons

    yellow_reasons = _check_yellow(inputs)
    if yellow_reasons:
        return "YELLOW", yellow_reasons

    return "GREEN", []
