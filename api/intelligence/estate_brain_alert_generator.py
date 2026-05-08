"""
estate_brain_alert_generator.py — brain payload → estate_alerts row 자동 생성.

Plan v0.3 brain 산출 (estate_brain_snapshots.json) 의 단지별 신호를
사용자에게 noticeable alert 로 전환. estate_alerts 테이블 (migration 004) 에 insert.

룰 3종 (V1 — 운영 1개월 후 hit rate 기반 calibration):
  ① brain_extreme       — extreme_signals_count ≥ 2 → severity=high, category=anomaly
  ② brain_lead_time     — lead_time 강 신호 (verdict 가 _strong / overheated / overhang) → mid
  ③ brain_redev_stage   — redev price_phase=max_uplift 또는 valuation_pending → high, catalyst

dedupe (migration 015):
  dedupe_key = f"{date_kst}_{subtype}_{complex_id}_{signal_subtype}"
  매일 같은 단지 같은 신호 = 1 alert 만 (cron 노이즈 방지).

T-시리즈:
  T1 fabricate X — brain 산출 부재 시 alert 생성 0건
  T2 source 명시 — body 에 "ESTATE Brain V0.3" marker
  T9 silent X — 모든 단지·신호 정합 명시
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

KST = timezone(timedelta(hours=9))

# Lead time 강 신호 verdict (plan v0.2 §V0.2 정합)
STRONG_LEAD_VERDICTS = frozenset([
    "negative_pressure_strong",     # 미분양 yoy +30%+
    "ambivalent_overheated",        # 전세가율 80%+
    "supply_overhang_in_2y",        # 착공 +10%+
    "supply_tight_in_2y",           # 착공 -10%-
    "reverse_lease_risk",           # 전세가율 < 50
    "tightening_pressure",          # 금리 +0.5pp+
    "strong_up",                    # 전세 +2.5%+
])

# extreme_signals 4종 한국어 매핑
EXTREME_SIGNAL_KO = {
    "pir_z_extreme":          "PIR z+1σ 초과",
    "jeonse_ratio_below_50":  "전세가율 50% 미만",
    "cap_treasury_inverted":  "Cap-국고채 역전",
    "kb_actual_gap_extreme":  "KB-실거래 ±10%",
}

# redev price_phase 한국어
REDEV_PHASE_KO = {
    "pre_signal":              "초기 기대",
    "max_uplift":              "최대 상승 진입",
    "moderate_uplift":         "완만 상승",
    "mid_uplift":              "중반 상승",
    "post_peak_consolidation": "정점 후 조정",
    "rental_market_spillover": "주변 전세 급등 임박",
    "new_build_premium":       "신축 프리미엄",
}


def _kst_today() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d")


def _gu_from_complex(brain: Dict[str, Any]) -> Optional[str]:
    """complex_id 첫 segment = gu (clustering.make_complex_id 정합)."""
    cid = brain.get("complex_id") or ""
    if not cid:
        return None
    parts = cid.split("_")
    return parts[0] if parts else None


def _make_alert(
    category: str,
    severity: str,
    title: str,
    body: str,
    gu: Optional[str],
    dedupe_subtype: str,
    complex_id: str,
    today: str,
) -> Dict[str, Any]:
    """estate_alerts schema 정합 + dedupe_key."""
    return {
        "user_id": None,  # V0 = 공개 alert (V1 = per-user 등록 단지 분리)
        "category": category,
        "severity": severity,
        "title": title,
        "body": body,
        "gu": gu,
        "source_url": None,
        "occurred_at": datetime.now(KST).isoformat(timespec="seconds"),
        "dedupe_key": f"{today}_{dedupe_subtype}_{complex_id}",
    }


# ────────────────────────────────────────────────────────────
# 룰 ① brain_extreme — 4중 신호 ≥ 2

def _rule_extreme(brain: Dict[str, Any], today: str) -> List[Dict[str, Any]]:
    val = brain.get("valuation") or {}
    signals = val.get("extreme_signals") or []
    count = val.get("extreme_signals_count") or 0
    if count < 2:
        return []
    cid = brain.get("complex_id", "")
    gu = _gu_from_complex(brain)
    signal_labels = [EXTREME_SIGNAL_KO.get(s, s) for s in signals]
    return [_make_alert(
        category="anomaly",
        severity="high",
        title=f"[Brain] {cid} 고평가 {count}/4 신호 발현",
        body=f"발현: {', '.join(signal_labels)} · ESTATE Brain V0.3",
        gu=gu,
        dedupe_subtype=f"brain_extreme_{count}",
        complex_id=cid,
        today=today,
    )]


# ────────────────────────────────────────────────────────────
# 룰 ② brain_lead_time — 강 신호

def _rule_lead_time(brain: Dict[str, Any], today: str) -> List[Dict[str, Any]]:
    cycle = brain.get("cycle_analog") or {}
    leads = cycle.get("lead_time_signals") or {}
    cid = brain.get("complex_id", "")
    gu = _gu_from_complex(brain)
    out: List[Dict[str, Any]] = []
    for key, sig in leads.items():
        verdict = sig.get("verdict")
        if verdict not in STRONG_LEAD_VERDICTS:
            continue
        lead_m = sig.get("lead_months")
        val = sig.get("value_pct") or sig.get("value_yoy_pct") or sig.get("rate_change_pp")
        out.append(_make_alert(
            category="anomaly",
            severity="mid",
            title=f"[Brain] {gu or cid} {key} {verdict}",
            body=f"value={val} lead={lead_m}M · ESTATE Brain V0.3",
            gu=gu,
            dedupe_subtype=f"brain_lead_{key}_{verdict}",
            complex_id=cid,
            today=today,
        ))
    return out


# ────────────────────────────────────────────────────────────
# 룰 ③ brain_redev_stage — max_uplift 또는 valuation_pending

def _rule_redev(brain: Dict[str, Any], today: str) -> List[Dict[str, Any]]:
    redev = brain.get("redevelopment_stage")
    if not redev:
        return []
    cid = brain.get("complex_id", "")
    gu = _gu_from_complex(brain)
    phase = redev.get("price_phase")
    monitoring = redev.get("monitoring") or {}
    out: List[Dict[str, Any]] = []

    # 가격 phase max_uplift = high
    if phase == "max_uplift":
        out.append(_make_alert(
            category="catalyst",
            severity="high",
            title=f"[Brain] {cid} {redev.get('stage_label_ko', '')} {REDEV_PHASE_KO['max_uplift']}",
            body=f"price_phase=max_uplift · 다음 단계까지 {redev.get('months_to_next_stage_estimated', 0)}M · ESTATE Brain V0.3",
            gu=gu,
            dedupe_subtype=f"brain_redev_max_uplift_{redev.get('stage')}",
            complex_id=cid,
            today=today,
        ))

    # 종전자산평가 발표 대기 (관리처분 인가 monitoring)
    if monitoring.get("valuation_announcement_pending"):
        out.append(_make_alert(
            category="catalyst",
            severity="high",
            title=f"[Brain] {cid} 종전자산평가 발표 대기",
            body=f"감정가 vs 기대치 — 프리미엄 변동 임박 · {redev.get('stage_label_ko', '')} · ESTATE Brain V0.3",
            gu=gu,
            dedupe_subtype="brain_redev_valuation_pending",
            complex_id=cid,
            today=today,
        ))

    # 이주·철거 진입 = 5M 내 주변 전세 급등 (plan v0.2 실증)
    if redev.get("stage") == "relocation":
        out.append(_make_alert(
            category="catalyst",
            severity="mid",
            title=f"[Brain] {cid} 이주·철거 — 주변 전세 급등 임박",
            body=f"5M 내 주변 권역 전세가 급등 선행지표 (plan v0.2) · ESTATE Brain V0.3",
            gu=gu,
            dedupe_subtype="brain_redev_relocation_spillover",
            complex_id=cid,
            today=today,
        ))

    return out


# ────────────────────────────────────────────────────────────
# Top-level

def generate_alerts(
    snapshots: Optional[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """estate_brain_snapshots.json payload → list of estate_alerts row.

    snapshots schema 정합 (estate_brain_builder):
      { complexes: {complex_id: brain_v02}, gu_aggregates: {gu: brain_v02}, ... }
    """
    if not snapshots:
        return []
    today = _kst_today()
    out: List[Dict[str, Any]] = []

    # 단지별 alert (complexes 우선 — 4 layer + redev 풍부)
    for cid, brain in (snapshots.get("complexes") or {}).items():
        if not isinstance(brain, dict):
            continue
        out.extend(_rule_extreme(brain, today))
        out.extend(_rule_lead_time(brain, today))
        out.extend(_rule_redev(brain, today))

    # 구 aggregate alert (lead_time 만 — 4 layer 없음)
    for gu, brain in (snapshots.get("gu_aggregates") or {}).items():
        if not isinstance(brain, dict):
            continue
        out.extend(_rule_lead_time(brain, today))

    return out
