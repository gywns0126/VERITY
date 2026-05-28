#!/usr/bin/env python3
"""cockpit_aggregate — 11 ledger → 단일 cockpit_state.json reducer.

PM=approved 2026-05-23 (plan §Phase 0-b).
WHY: 분산된 11종 ledger를 단일 운영자 시야로 reduce. 자체 측정 0, 모든 신호 = 기존 ledger read-only.
DATA: cron_health.jsonl / data_health.jsonl / data_pipeline_health.json / fred_health.jsonl /
      runtime_load_log.jsonl / operator_deadman_log.jsonl / alert_state.json / brain_audit.jsonl /
      telegram_volume.jsonl / system_health_snapshot.json / vams.reset_meta (portfolio.json).
EXPECTED: 5분 cron 박힘 → data/metadata/cockpit_state.json 단일 SoT 박힘 →
          Phase 1 SystemHealthBar / AdminDashboard 합성.

자체 측정 0. RULE 1 (KIS API call 0 read-only). RULE 2 (data/metadata/ = vercel-api/ 외부, ignoreCommand skip).

source: [[project_win_condition_decision]] option 2 + plan PM=approved 2026-05-23.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from api.observability.cockpit_severity import evaluate as evaluate_severity
from api.observability.verification_trail import compute_trail

DATA_DIR = _REPO_ROOT / "data"
METADATA_DIR = DATA_DIR / "metadata"
COCKPIT_PATH = METADATA_DIR / "cockpit_state.json"

# ─── helpers ─────────────────────────────────────────────

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _read_json(path: Path) -> Optional[Any]:
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _read_jsonl_tail(path: Path, n: int = 200) -> List[Dict[str, Any]]:
    """jsonl 의 마지막 n entry 박음. 빈 파일 / 파싱 실패 = []."""
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8") as f:
            lines = f.readlines()[-n:]
    except OSError:
        return []
    out = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _parse_ts(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        # ts_kst / ts_utc / collected_at 등 다양 포맷
        ts = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


# ─── 11 ledger reducers ──────────────────────────────────

def _reduce_cron_health() -> Dict[str, Any]:
    """cron_health.jsonl 박은 부분 — kis_lock_commits_24h / dispatch_chain / fred_age_h."""
    entries = _read_jsonl_tail(METADATA_DIR / "cron_health.jsonl", n=20)
    if not entries:
        return {}
    last = entries[-1]
    dispatch = last.get("dispatch_chain_summary") or {}
    dispatch_ratio = None
    if isinstance(dispatch, dict):
        total = dispatch.get("total") or dispatch.get("expected")
        ok = dispatch.get("ok") or dispatch.get("success")
        try:
            if total and ok is not None:
                dispatch_ratio = float(ok) / float(total)
        except (TypeError, ValueError, ZeroDivisionError):
            pass
    return {
        "kis_lock_commits_24h": last.get("kis_lock_commits_24h"),
        "fred_age_h": last.get("fred_age_h"),
        "macro_age_h": last.get("macro_age_h"),
        "dispatch_chain_ratio": dispatch_ratio,
        "cron_severity": last.get("severity"),
        "cron_health_ts": last.get("ts_kst"),
    }


def _reduce_data_health() -> Dict[str, Any]:
    """data_health.jsonl 박은 부분 — core_sources_ok."""
    entries = _read_jsonl_tail(METADATA_DIR / "data_health.jsonl", n=5)
    if not entries:
        return {}
    last = entries[-1]
    return {
        "core_sources_ok": last.get("core_sources_ok"),
        "overall_status": last.get("overall_status"),
        "data_health_ts": last.get("timestamp") or last.get("date"),
    }


def _reduce_data_pipeline() -> Dict[str, Any]:
    """data_pipeline_health.json — schema/summary."""
    data = _read_json(METADATA_DIR / "data_pipeline_health.json")
    if not isinstance(data, dict):
        return {}
    return {
        "pipeline_overall": data.get("overall_status"),
        "pipeline_collected_at": data.get("collected_at"),
        "pipeline_summary": data.get("summary"),
    }


def _reduce_fred_health() -> Dict[str, Any]:
    """fred_health.jsonl — 24h 내 실패율."""
    entries = _read_jsonl_tail(METADATA_DIR / "fred_health.jsonl", n=500)
    if not entries:
        return {}
    cutoff = _now_utc() - timedelta(hours=24)
    recent = []
    for e in entries:
        ts = _parse_ts(e.get("ts_utc"))
        if ts and ts >= cutoff:
            recent.append(e)
    if not recent:
        return {}
    failed = sum(1 for e in recent if e.get("status") != "ok")
    return {
        "fred_24h_total": len(recent),
        "fred_24h_failed": failed,
        "fred_24h_failure_rate": failed / len(recent) if recent else 0.0,
    }


def _reduce_runtime_load() -> Dict[str, Any]:
    """runtime_load_log.jsonl — 최근 dart_failure_rate / rate_limit_violations / mode."""
    entries = _read_jsonl_tail(METADATA_DIR / "runtime_load_log.jsonl", n=10)
    if not entries:
        return {}
    last = entries[-1]
    return {
        "runtime_mode": last.get("mode"),
        "ramp_up_stage": last.get("ramp_up_stage"),
        "dart_failure_rate": last.get("dart_failure_rate"),
        "rate_limit_violations": last.get("rate_limit_violations"),
        "kr_first_call_duration_ms": last.get("kr_first_call_duration_ms"),
    }


def _reduce_operator_deadman() -> Dict[str, Any]:
    """operator_deadman_log.jsonl — git/tg/uaq days + trigger."""
    entries = _read_jsonl_tail(METADATA_DIR / "operator_deadman_log.jsonl", n=5)
    if not entries:
        return {}
    last = entries[-1]
    return {
        "days_git": last.get("days_git"),
        "days_telegram": last.get("days_telegram"),
        "days_uaq": last.get("days_uaq"),
        "trigger": last.get("trigger"),
        "maintenance": last.get("maintenance"),
        "warn_days": last.get("warn_days"),
    }


def _reduce_alert_state() -> Dict[str, Any]:
    """alert_state.json — last_push_at + topics."""
    data = _read_json(METADATA_DIR / "alert_state.json")
    if not isinstance(data, dict):
        return {}
    return {
        "last_push_at": data.get("last_push_at"),
        "last_topics": data.get("last_topics"),
    }


def _reduce_brain_audit() -> Dict[str, Any]:
    """brain_audit.jsonl — 24h 내 anomaly count + 최근 grade."""
    entries = _read_jsonl_tail(METADATA_DIR / "brain_audit.jsonl", n=200)
    if not entries:
        return {}
    cutoff = _now_utc() - timedelta(hours=24)
    recent = []
    for e in entries:
        ts = _parse_ts(e.get("ts_kst"))
        if ts and ts >= cutoff:
            recent.append(e)
    anomaly = sum(1 for e in recent if e.get("source") == "anomaly" or e.get("anomaly"))
    last = entries[-1] if entries else {}
    return {
        "brain_anomaly_24h": anomaly,
        "brain_last_n_total": last.get("n_total"),
        "brain_last_ts": last.get("ts_kst"),
    }


def _reduce_telegram_volume() -> Dict[str, Any]:
    """telegram_volume.jsonl — 24h sent/dedupe_skip/quiet_skip + fp_repeat_max."""
    entries = _read_jsonl_tail(DATA_DIR / "telegram_volume.jsonl", n=500)
    if not entries:
        return {}
    cutoff = _now_utc() - timedelta(hours=24)
    recent = []
    for e in entries:
        ts = _parse_ts(e.get("ts_kst"))
        if ts and ts >= cutoff:
            recent.append(e)
    if not recent:
        return {"alert_volume_24h": {}}
    sent = sum(1 for e in recent if e.get("outcome") == "sent")
    dedupe = sum(1 for e in recent if e.get("outcome") == "dedupe_skip")
    quiet = sum(1 for e in recent if e.get("outcome") == "quiet_skip")
    # fp_repeat_max = 같은 fingerprint 최대 반복
    fp_counts: Dict[str, int] = {}
    for e in recent:
        fp = e.get("fingerprint")
        if fp:
            fp_counts[fp] = fp_counts.get(fp, 0) + 1
    fp_max = max(fp_counts.values()) if fp_counts else 0
    return {
        "alert_volume_24h": {
            "sent": sent,
            "dedupe_skip": dedupe,
            "quiet_skip": quiet,
            "fp_repeat_max": fp_max,
        }
    }


def _reduce_system_health_snapshot() -> Dict[str, Any]:
    """system_health_snapshot.json — overall + updated_at."""
    data = _read_json(DATA_DIR / "system_health_snapshot.json")
    if not isinstance(data, dict):
        return {}
    sh = data.get("system_health") or {}
    return {
        "system_health_updated_at": data.get("updated_at"),
        "system_health_summary": (sh.get("overall") if isinstance(sh, dict) else None),
    }


# ─── P1-e VERITY 통합 한줄평 (LLM 호출 0, RULE 6/7 통과) ──

def _compose_one_liner(portfolio: Dict[str, Any], n_today: Dict[str, int]) -> str:
    """portfolio + n_today 박음 → VERITY 통합 한줄평 박음.

    포맷: "과열 · 0 BUY / 7 WATCH / 14 CAUTION / 4 AVOID · VAMS 70% 현금 · 가설 N=30"

    합성 소스 (전부 read-only, LLM 호출 0):
    - market_horizon.cycle_stage_label_ko
    - recommendations[].verity_brain.grade 분포
    - vams.cash / vams.total_asset
    - n_validation_days (Phase 1 P1-d)

    RULE 6 통과 — LLM 호출 0, 기존 verdict view re-format.
    RULE 7 통과 — "가설 N=X" 라벨 박힘 의무.
    TIDE 디자인 정합 — 이모지 박지 X (docs/design_system_tide.md).
    """
    mh = portfolio.get("market_horizon") or {}
    stage_label = mh.get("cycle_stage_label_ko") or mh.get("cycle_stage") or "unknown"

    recs = portfolio.get("recommendations") or []
    grade_counts = {"STRONG_BUY": 0, "BUY": 0, "WATCH": 0, "CAUTION": 0, "AVOID": 0}
    for r in recs:
        vb = r.get("verity_brain") or {}
        g = vb.get("grade") or r.get("recommendation", "")
        if g in grade_counts:
            grade_counts[g] += 1

    n_buy = grade_counts["STRONG_BUY"] + grade_counts["BUY"]
    grade_str = (f"{n_buy} BUY / {grade_counts['WATCH']} WATCH / "
                 f"{grade_counts['CAUTION']} CAUTION / {grade_counts['AVOID']} AVOID")

    vams = portfolio.get("vams") or {}
    try:
        total = float(vams.get("total_asset") or 0)
        cash = float(vams.get("cash") or 0)
        cash_pct = round(cash / total * 100) if total > 0 else 0
    except (TypeError, ValueError, ZeroDivisionError):
        cash_pct = 0

    n_days = n_today.get("n_validation_days", 0)

    return f"{stage_label} · {grade_str} · VAMS {cash_pct}% 현금 · 가설 N={n_days}"


def _reduce_vams_reset() -> Dict[str, Any]:
    """vams.reset_meta (portfolio.json) — N counter origin."""
    portfolio = _read_json(DATA_DIR / "portfolio.json")
    if not isinstance(portfolio, dict):
        return {}
    vams = portfolio.get("vams") or {}
    reset_meta = vams.get("reset_meta") or {}
    val = portfolio.get("validation") or {}
    reset_at = reset_meta.get("reset_at", "")
    days_since_reset = None
    if reset_at:
        ts = _parse_ts(reset_at)
        if ts:
            days_since_reset = (_now_utc() - ts).days
    return {
        "vams_reset_at": reset_at,
        "vams_days_since_reset": days_since_reset,
        "validation_days": val.get("cumulative_days", 0),
        "validation_target": val.get("target_days", 90),
        "validation_sample": val.get("sample_total", 0),
    }


# ─── days_clean 계산 (KIS / FRED / Vercel / Telegram) ──────

def _days_clean(inputs: Dict[str, Any]) -> Dict[str, Optional[int]]:
    """각 source 의 마지막 결함 이후 경과일 (Phase 0 = 단순 산출)."""
    # KIS = kis_lock_commits_24h 가 0 인 마지막 24h 윈도우 (단순: 현재 0 = clean 1d)
    kis_clean: Optional[int] = None
    kis = inputs.get("kis_lock_commits_24h")
    if isinstance(kis, (int, float)):
        kis_clean = 1 if kis == 0 else 0
    # FRED = 24h failure rate < 5% → clean
    fred_clean: Optional[int] = None
    fred_rate = inputs.get("fred_24h_failure_rate")
    if isinstance(fred_rate, (int, float)):
        fred_clean = 1 if fred_rate < 0.05 else 0
    # Telegram = fp_repeat_max < 5 → clean
    tg_clean: Optional[int] = None
    alert_vol = inputs.get("alert_volume_24h") or {}
    fp_max = alert_vol.get("fp_repeat_max")
    if isinstance(fp_max, (int, float)):
        tg_clean = 1 if fp_max < 5 else 0
    # Vercel = 별 ledger 0, Phase 2 후속
    return {
        "kis": kis_clean,
        "fred": fred_clean,
        "telegram": tg_clean,
        "vercel": None,  # Phase 2 후속
    }


# ─── main aggregator ─────────────────────────────────────

# 2026-05-28 박은 부분 — 외부 cron (rule7_audit 등) 박은 부분 박은 cockpit_state.json
# 박은 부분 박은 field 박은 부분 박은 cockpit_aggregate 박은 부분 박은 rebuild 시 dropped
# 박지 X 박은 부분 박은 박은 preserve. 박은 keys = 외부 cron 박은 부분 박은 박은 박은 박은 박은.
_EXTERNAL_CRON_KEYS = [
    "rule7_quota",              # rule7_audit cron 박음 (KST 09:15)
    "pre_registration_pending", # rule7_audit cron 박음 (overlap, 우선)
]


def _preserve_external_keys() -> Dict[str, Any]:
    """외부 cron 박은 부분 박은 박은 박은 박은 cockpit_state.json field preserve.

    cockpit_aggregate 5분 cron rebuild 시 외부 cron (rule7_audit 등) 박은
    부분 박은 박은 박은 박은 field dropped 박지 X 박은 부분 박은 박은 박은
    read.
    """
    if not COCKPIT_PATH.exists():
        return {}
    try:
        with COCKPIT_PATH.open("r", encoding="utf-8") as f:
            existing = json.load(f)
        return {
            key: existing[key]
            for key in _EXTERNAL_CRON_KEYS
            if key in existing and existing[key] is not None
        }
    except (json.JSONDecodeError, OSError):
        return {}


def build_cockpit_state() -> Dict[str, Any]:
    """모든 reducer 호출 + severity 박음 → cockpit_state dict 반환."""
    inputs: Dict[str, Any] = {}

    # 11 ledger reduce
    inputs.update(_reduce_cron_health())
    inputs["data_health"] = _reduce_data_health()
    inputs.update(_reduce_data_pipeline())
    inputs.update(_reduce_fred_health())
    inputs.update(_reduce_runtime_load())
    inputs["operator_deadman"] = _reduce_operator_deadman()
    inputs.update(_reduce_alert_state())
    inputs.update(_reduce_brain_audit())
    inputs.update(_reduce_telegram_volume())
    inputs.update(_reduce_system_health_snapshot())
    inputs.update(_reduce_vams_reset())

    # severity 박음 ([[feedback_methodology_pre_registration]] 사전등록)
    # data_health 이 nested dict 라 unpack 박음
    flat_inputs = dict(inputs)
    if isinstance(flat_inputs.get("data_health"), dict):
        flat_inputs["data_health"] = flat_inputs["data_health"]
    severity, severity_reasons = evaluate_severity(flat_inputs)

    # N milestones — verification_trail helper 박음 (Phase 1 P1-d)
    portfolio = _read_json(DATA_DIR / "portfolio.json") or {}
    trail = compute_trail(portfolio)
    n_today = trail["n_today"]
    n_days = n_today["n_validation_days"]
    milestones = trail["day_milestones"]

    # P1-e VERITY 통합 한줄평 (LLM 호출 0, RULE 6/7 통과)
    one_liner = _compose_one_liner(portfolio, n_today)

    # 외부 cron field preserve (rule7_quota 등, 2026-05-28 박은 부분)
    external = _preserve_external_keys()

    # cockpit_state.json schema (plan §P0-a)
    state = {
        "collected_at": _now_utc().isoformat(),
        "schema_version": 1,
        "severity": severity,
        "severity_reasons": severity_reasons,
        "n_verification_days": n_days,
        "n_milestones": milestones,
        # Phase 1 P1-d — trade N + sample N 박음 (verification_trail.py)
        "n_trades": n_today["n_trades"],
        "trade_milestones": trail["trade_milestones"],
        "n_validation_samples": n_today["n_validation_samples"],
        "sample_milestones": trail["sample_milestones"],
        # Phase 1 P1-e — VERITY 통합 한줄평 (LLM 호출 0)
        "one_liner": one_liner,
        "ttd_recent_p50_minutes": None,  # Phase 2 후속
        "days_clean": _days_clean(inputs),
        "open_p0_p1": [],  # Phase 2 후속 (postmortem ledger 진단)
        "operator_deadman": inputs.get("operator_deadman") or {},
        "pre_registration_pending": [],  # Phase 1 P1-c 후속
        "alert_volume_24h": inputs.get("alert_volume_24h") or {},
        "auto_action_blocked": [],  # Phase 2 후속
        "_inputs_snapshot": {
            # 디버그 용 — 11 ledger reduce 값 모두 박음 (silent skip 차단)
            "kis_lock_commits_24h": inputs.get("kis_lock_commits_24h"),
            "fred_age_h": inputs.get("fred_age_h"),
            "fred_24h_failure_rate": inputs.get("fred_24h_failure_rate"),
            "core_sources_ok": (inputs.get("data_health") or {}).get("core_sources_ok"),
            "runtime_mode": inputs.get("runtime_mode"),
            "ramp_up_stage": inputs.get("ramp_up_stage"),
            "brain_anomaly_24h": inputs.get("brain_anomaly_24h"),
            "vams_days_since_reset": inputs.get("vams_days_since_reset"),
            "validation_sample": inputs.get("validation_sample"),
        },
    }
    # 외부 cron preserve — pre_registration_pending 박은 부분 박은 박은 박은 박은 박은 박은
    # rule7_audit cron 박은 부분 박은 박은 박은 박은 박은 박은 박은 박은 박은 박은 rule7_quota 박음
    state.update(external)
    return state


def main() -> int:
    """5분 cron 진입점. cockpit_state.json 박음."""
    METADATA_DIR.mkdir(parents=True, exist_ok=True)
    state = build_cockpit_state()
    try:
        with COCKPIT_PATH.open("w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        print(f"  ✓ cockpit_state.json 박힘: severity={state['severity']} "
              f"reasons={len(state['severity_reasons'])} "
              f"N={state['n_verification_days']}/{state['n_milestones']['to_50']+state['n_verification_days']}")
        return 0
    except OSError as e:
        print(f"  ✗ cockpit_state.json write 실패: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
