"""Cross-link layer — VERITY-CROSSLINK-THRESHOLDS-V1.5 (simplified, 2026-05-04).

trust_score.py 의 자가진단 verdict ↔ backtest_stats.json 의 실수익 hit rate 정합성
자동 측정. 별도 모듈 (방식 B) — trust_score.py read-only.

핵심 정책:
  §1  source: backtest_stats.json (Primary) / generate_verification_report (Secondary)
  §2  snapshot-pair 모델 (rolling 아님)
  §3  verdict 3-tier (ready / manual_review / hold)
  §4  1차 scope = brain_distribution_normal sub-factor 1개 (plugin 패턴)
  §5  instant_hold: silent_pass 누적 3건 → hold (T-14 verdict 기반, self-healing 차단)
  §6  baseline = 90일 historical mean. floor 0.45. cold-start 0.5
  §7  Tier 1/2/3 = baseline ± kσ. σ = binomial SE on cumulative_trades
  §8  Gate A (cumulative_trades ≥ 20)
  §9  alert_tier (yellow/orange/red): dashboard only — verdict 영향 X
       escalation: TIER3 1건 → hold (TIER1/TIER2 분기는 simplify 단계 제거)
  §15 unit 통일: 0~1 비율
  §17 phase: INSUFFICIENT_DATA / TIER3_DISABLED / FULLY_ACTIVE / STALE_UNKNOWN

simplify retract (2026-05-04):
  - rate_limit (TIER3 일일 3건) 삭제 — TIER3 1건 즉시 hold 라 dead
  - ROLLING_STABLE 5번째 phase 삭제 — cosmetic
  - §9-2 TIER1/TIER2 강등 분기 삭제 — 결함 R (cry-wolf) + KI-18 (dead code)
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))

# ───────────────────── 상수 (v1.3 spec) ─────────────────────

GATE_A_MIN_TRADES = 20
GATE_B_MIN_PAIRS = 30
ROLLING_WINDOW_DAYS = 30
INSTANT_HOLD_THRESHOLD = 3  # silent_pass 누적 ≥ N → instant_hold

# §9-2 escalation: TIER3 1건 (±3σ extreme outlier) → hold.
# TIER1/TIER2 분기는 §5 instant_hold 와 임계 충돌(KI-18) 또는 통계적 cry-wolf(결함 R)
# 라 simplify 단계에서 제거. 향후 운영 누적 후 재도입 검토.
NOISE_FLOOR_TIER3 = 1

VIOLATIONS_FILENAME = "cross_link_violations.jsonl"
CUMULATIVE_TRADES_FILENAME = "cross_link_cumulative_trades.json"
PHASE_STATE_FILENAME = "cross_link_phase_state.json"


def _data_dir() -> str:
    from api.config import DATA_DIR
    return DATA_DIR


def _trust_log_path(data_dir: str) -> str:
    # 명령서 §2-5 의 "data/trust_score.jsonl" 가정 정정.
    # 실제 trust_score.py:36 의 _PATH = data/metadata/trust_log.jsonl
    return os.path.join(data_dir, "metadata", "trust_log.jsonl")


def _violations_path(data_dir: str) -> str:
    # v1.4 §16: data/metadata/cross_link_violations.jsonl
    return os.path.join(data_dir, "metadata", VIOLATIONS_FILENAME)


def _cumulative_trades_path(data_dir: str) -> str:
    return os.path.join(data_dir, "metadata", CUMULATIVE_TRADES_FILENAME)


def _phase_state_path(data_dir: str) -> str:
    # v1.4.1 결함 V — phase 비가역성 영속화
    return os.path.join(data_dir, "metadata", PHASE_STATE_FILENAME)


def _load_cumulative_trades(path: str) -> Dict[str, Any]:
    default = {
        "cumulative_trades": 0,
        "cumulative_pairs": 0,
        "last_evaluation_date": None,
        "last_total_recs": 0,
    }
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            state = json.load(f)
        # 호환: 구 schema 에 cumulative_pairs 누락 시 0 으로 시작
        state.setdefault("cumulative_pairs", 0)
        return state
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("cumulative_trades read failed: %s", e)
        return default


def _update_cumulative_trades(path: str, evaluation_date: str, total_recs_today: int) -> Dict[str, Any]:
    """매 cycle 1회 누적. 같은 날 중복 호출 시 누적 안 함 (idempotent).

    Returns: {"cumulative_trades": int, "cumulative_pairs": int, ...}
    """
    state = _load_cumulative_trades(path)
    last_date = (state.get("last_evaluation_date") or "")[:10]
    today = (evaluation_date or "")[:10]
    if last_date == today:
        return state
    new_state = {
        "cumulative_trades": int(state.get("cumulative_trades") or 0) + max(0, int(total_recs_today or 0)),
        "cumulative_pairs": int(state.get("cumulative_pairs") or 0) + 1,  # 1 cycle = 1 pair
        "last_evaluation_date": evaluation_date,
        "last_total_recs": total_recs_today,
    }
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(new_state, f, ensure_ascii=False, indent=2)
    except OSError as e:
        logger.warning("cumulative_trades persist failed: %s", e)
    return new_state


def _history_list_to_silent_pass_count(history: Optional[List[Dict[str, Any]]]) -> int:
    """history_fetcher 가 반환한 list 에서 silent_pass Tier2/3 카운트 산출 (§5 instant_hold용)."""
    if not history:
        return 0
    count = 0
    for entry in history:
        if not isinstance(entry, dict):
            continue
        # 호환: violation_type 또는 direction 둘 다 허용
        direction = entry.get("violation_type") or entry.get("direction")
        tier = entry.get("tier") or entry.get("evaluation")
        if direction == "silent_pass" and tier in ("TIER2", "TIER3"):
            count += 1
    return count


def _rolling_tier_counts_from_list(
    history: Optional[List[Dict[str, Any]]],
) -> Dict[str, int]:
    """history_fetcher 가 반환한 list 에서 silent_pass 단방향 Tier 별 누적 카운트.

    v1.4.1 §7-3 — §9-2 누적 verdict 강등 산출용. cry_wolf 는 §12 비대칭 path 라 여기서 제외.
    """
    counts = {"TIER1": 0, "TIER2": 0, "TIER3": 0}
    if not history:
        return counts
    for entry in history:
        if not isinstance(entry, dict):
            continue
        direction = entry.get("violation_type") or entry.get("direction")
        tier = entry.get("tier") or entry.get("evaluation")
        if direction != "silent_pass":
            continue
        if tier in counts:
            counts[tier] += 1
    return counts


def _rolling_tier_counts_from_jsonl(
    violations_path: str,
    evaluation_date: str,
    window_days: int = ROLLING_WINDOW_DAYS,
) -> Dict[str, int]:
    """v1.4.1 §7-3 운영 source — cross_link_violations.jsonl 에서 30 pair 누적 Tier 별 카운트.

    silent_pass 단방향만. cry_wolf 는 §12 비대칭 처리 path 라 §9-2 합산 X.
    """
    counts = {"TIER1": 0, "TIER2": 0, "TIER3": 0}
    if not os.path.exists(violations_path):
        return counts
    target = _parse_iso(evaluation_date)
    if target is None:
        return counts
    if target.tzinfo is None:
        target = target.replace(tzinfo=KST)
    cutoff = target - timedelta(days=window_days)

    try:
        with open(violations_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts = _parse_iso(row.get("evaluation_date"))
                if ts is None:
                    continue
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=KST)
                if ts < cutoff or ts > target:
                    continue
                for ev in row.get("evaluators") or []:
                    direction = ev.get("direction") or ev.get("violation_type")
                    tier = ev.get("evaluation")
                    if direction != "silent_pass":
                        continue
                    if tier in counts:
                        counts[tier] += 1
    except OSError:
        pass
    return counts


# ───────────────────── §9-2 escalation (TIER3 만 valid) ─────────────────────

def _evaluate_noise_floor_escalation(
    rolling_counts: Dict[str, int],
    cycle_violations: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """TIER3 silent_pass 1건 발생 시 즉시 hold (±3σ extreme outlier).

    simplify 정정 (2026-05-04):
      - TIER1 강등: 결함 R — 통계적 정상 noise 와 임계 동일, cry-wolf
      - TIER2 강등: KI-18 — §5 instant_hold (silent_pass 3건) 와 임계 충돌, dead code
      - TIER3 강등: §5 보다 strict 한 분기 (silent_pass 1건만으로 trigger 가능). 유지.
    """
    cycle_tier3 = sum(
        1 for v in (cycle_violations or [])
        if (v.get("violation_type") or v.get("direction")) == "silent_pass"
        and v.get("evaluation") == "TIER3"
    )
    total_tier3 = rolling_counts.get("TIER3", 0) + cycle_tier3

    if total_tier3 >= NOISE_FLOOR_TIER3:
        return {
            "verdict": "hold",
            "trigger_tier": "TIER3",
            "count": total_tier3,
            "threshold": NOISE_FLOOR_TIER3,
        }
    return None


# ───────────────────── Phase 비가역성 (v1.4.1 §7-4) ─────────────────────

_PHASE_RANK = {
    "INSUFFICIENT_DATA": 0,
    "TIER3_DISABLED": 1,
    "FULLY_ACTIVE": 2,
    "HISTORICAL": 3,
}


def _phase_max(p1: str, p2: str) -> str:
    return p1 if _PHASE_RANK.get(p1, 0) >= _PHASE_RANK.get(p2, 0) else p2


def _load_phase_state(path: str) -> Dict[str, Any]:
    default = {"max_snapshot_n": 0, "max_phase": "INSUFFICIENT_DATA"}
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


def _update_phase_state(
    path: str,
    current_snapshot_n: int,
    current_phase: str,
) -> Dict[str, Any]:
    state = _load_phase_state(path)
    new_state = {
        "max_snapshot_n": max(int(state.get("max_snapshot_n") or 0), int(current_snapshot_n or 0)),
        "max_phase": _phase_max(state.get("max_phase") or "INSUFFICIENT_DATA", current_phase),
    }
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(new_state, f, ensure_ascii=False, indent=2)
    except OSError as e:
        logger.warning("phase_state persist failed: %s", e)
    return new_state


def _parse_iso(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)
    except (TypeError, ValueError):
        return None


# ───────────────────── T-14 verdict 인덱싱 (§5-2 self-healing 차단) ─────────────────────

def lookup_verdict_at(
    target_iso: str,
    trust_log_path: Optional[str] = None,
    tolerance_hours: float = 36.0,
) -> Optional[Dict[str, Any]]:
    """trust_log.jsonl 에서 target_iso 시점에 가장 가까운 entry 조회.

    tolerance 안에 entry 가 없으면 None (INSUFFICIENT_DATA 처리).
    """
    if trust_log_path is None:
        trust_log_path = _trust_log_path(_data_dir())
    if not os.path.exists(trust_log_path):
        return None

    target = _parse_iso(target_iso)
    if target is None:
        return None
    if target.tzinfo is None:
        target = target.replace(tzinfo=KST)

    best = None
    best_diff = None
    try:
        with open(trust_log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts = _parse_iso(entry.get("timestamp"))
                if ts is None:
                    continue
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=KST)
                diff = abs((ts - target).total_seconds())
                if best_diff is None or diff < best_diff:
                    best_diff = diff
                    best = entry
    except OSError as e:
        logger.warning("trust_log.jsonl read failed: %s", e)
        return None

    if best is None:
        return None
    if best_diff is not None and best_diff > tolerance_hours * 3600:
        return None
    return best


# ───────────────────── Operating phase (§7-2 cold-start) ─────────────────────

def determine_operating_phase(snapshot_n: int) -> str:
    """v1.3 §7-2 cold-start 단계 판정."""
    if snapshot_n < GATE_A_MIN_TRADES:
        return "INSUFFICIENT_DATA"
    if snapshot_n < 50:
        return "TIER3_DISABLED"
    return "FULLY_ACTIVE"


def _enabled_tiers(phase: str) -> List[int]:
    if phase == "INSUFFICIENT_DATA":
        return []
    if phase == "TIER3_DISABLED":
        return [1, 2]
    return [1, 2, 3]


def _rolling_window_violations(
    violations_path: str,
    evaluation_date: str,
    window_days: int = ROLLING_WINDOW_DAYS,
) -> int:
    """30일 window 안에서 silent_pass Tier 2/3 위반 누적 카운트 (instant_hold 판정용)."""
    if not os.path.exists(violations_path):
        return 0
    target = _parse_iso(evaluation_date)
    if target is None:
        return 0
    if target.tzinfo is None:
        target = target.replace(tzinfo=KST)
    cutoff = target - timedelta(days=window_days)

    count = 0
    try:
        with open(violations_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts = _parse_iso(row.get("evaluation_date"))
                if ts is None:
                    continue
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=KST)
                if ts < cutoff or ts > target:
                    continue
                for ev in row.get("evaluators") or []:
                    if (
                        ev.get("violation_type") == "silent_pass"
                        and ev.get("evaluation") in ("TIER2", "TIER3")
                    ):
                        count += 1
    except OSError:
        return 0
    return count


# ───────────────────── Verdict 산출 (v1.4.1 §3 / §5 / §9-2) ─────────────────────

_VERDICT_RANK = {"ready": 0, "manual_review": 1, "hold": 2}


def _compute_final_verdict(
    raw_failed: int,
    instant_hold: bool,
    escalation_result: Optional[Dict[str, Any]],
    phase: str,
) -> Dict[str, Any]:
    """v1.4.1 통합 verdict — 강등 candidate 중 가장 강한 것 채택 (OR 관계).

    candidates:
      - phase=STALE_UNKNOWN → manual_review
      - §5 instant_hold → hold
      - §9-2 escalation → escalation.verdict
      - raw trust_score (8 sub-factor failed 룰) → ready / manual_review / hold

    cycle 단위 silent_pass 1건만으로는 강등 X (v1.4.1 §9-1: dashboard only).
    """
    candidates: List[tuple] = []

    if phase == "STALE_UNKNOWN":
        candidates.append(("manual_review", "stale_unknown"))

    if instant_hold:
        candidates.append(("hold", "instant_hold_override"))

    if escalation_result is not None:
        candidates.append((
            escalation_result["verdict"],
            f"escalation_{escalation_result.get('trigger_tier', '?')}",
        ))

    # raw trust_score 룰 (trust_score.py:240 정합)
    if raw_failed == 0:
        raw_verdict = "ready"
    elif raw_failed <= 2:
        raw_verdict = "manual_review"
    else:
        raw_verdict = "hold"
    candidates.append((raw_verdict, "raw_failed_count_rule"))

    # max() = 가장 강한 강등 채택
    final, logic = max(candidates, key=lambda x: _VERDICT_RANK[x[0]])

    return {
        "raw_failed": raw_failed,
        "instant_hold_active": instant_hold,
        "escalation_active": escalation_result is not None,
        "escalation_trigger_tier": (escalation_result or {}).get("trigger_tier"),
        "final_verdict": final,
        "verdict_logic": logic,
    }


# ───────────────────── 메인 진입점 ─────────────────────

def run_cross_link(
    evaluation_date: str,
    trust_score_result: Dict[str, Any],
    evaluators: Optional[List[Any]] = None,
    data_dir: Optional[str] = None,
    trust_log_path: Optional[str] = None,
    violations_path: Optional[str] = None,
    cumulative_trades_path: Optional[str] = None,
    phase_state_path: Optional[str] = None,
    persist: bool = True,
    *,
    backtest_stats_fetcher: Optional[Any] = None,
    trust_log_fetcher: Optional[Any] = None,
    history_fetcher: Optional[Any] = None,
    cumulative_trades_fetcher: Optional[Any] = None,
    rolling_violations_fetcher: Optional[Any] = None,
    baseline_override: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """v1.3 spec 진입점. 명령서 §2-2 출력 schema 정확 일치.

    P1 정정 (KI-7/8/10):
      - cumulative_trades 누적 영속화 (Gate A 정의 명확화)
      - STALE_UNKNOWN phase 추가 (stale source fallback 실패 시)
      - fetcher 4종 주입 path (mock 검증용)

    Args:
        evaluation_date: T 시점 (ISO 8601).
        trust_score_result: trust_score.report_readiness() 출력.
        evaluators: 주입형 — None 이면 BrainDistributionEvaluator 1개 (§4 1차 scope).
        data_dir / trust_log_path / violations_path: 테스트 주입용.
        persist: True 면 violations.jsonl 에 append.
    """
    if data_dir is None:
        data_dir = _data_dir()
    if trust_log_path is None:
        trust_log_path = _trust_log_path(data_dir)
    if violations_path is None:
        violations_path = _violations_path(data_dir)
    if cumulative_trades_path is None:
        cumulative_trades_path = _cumulative_trades_path(data_dir)
    if phase_state_path is None:
        phase_state_path = _phase_state_path(data_dir)

    # ── evaluator 주입 (P1: backtest_stats_fetcher / baseline_override 지원) ──
    if evaluators is None:
        from .cross_link_evaluators import BrainDistributionEvaluator
        if backtest_stats_fetcher is not None or baseline_override is not None:
            evaluators = [
                BrainDistributionEvaluator(
                    data_dir=data_dir,
                    fetcher=_make_evaluator_adapter(
                        evaluation_date,
                        backtest_stats_fetcher,
                        baseline_override,
                    ),
                )
            ]
        else:
            evaluators = [BrainDistributionEvaluator(data_dir=data_dir)]

    # ── T-14 verdict 인덱싱 (self-healing 차단) ──
    target = _parse_iso(evaluation_date)
    if target is None:
        raise ValueError(f"invalid evaluation_date: {evaluation_date}")
    if target.tzinfo is None:
        target = target.replace(tzinfo=KST)
    t_minus_14_iso = (target - timedelta(days=14)).isoformat()
    if trust_log_fetcher is not None:
        t14_entry = trust_log_fetcher(t_minus_14_iso)
    else:
        t14_entry = lookup_verdict_at(t_minus_14_iso, trust_log_path=trust_log_path)
    verdict_at_t_minus_14 = (t14_entry or {}).get("verdict")

    # ── ground truth + baseline ──
    primary_eval = evaluators[0]
    ground_truth = primary_eval.fetch_ground_truth(evaluation_date)
    baseline = primary_eval.compute_baseline(lookback_days=90)

    # ── cumulative_trades / pairs 누적 (KI-10 + Gate B) ──
    total_recs_today = int(ground_truth.get("snapshot_n") or 0)
    if cumulative_trades_fetcher is not None:
        cumulative_trades = int(cumulative_trades_fetcher() or 0)
        cumulative_pairs = cumulative_trades  # mock: pair 카운터 없으면 trades 와 동일 가정
    else:
        cum_state = _update_cumulative_trades(
            cumulative_trades_path, evaluation_date, total_recs_today
        )
        cumulative_trades = int(cum_state.get("cumulative_trades") or 0)
        cumulative_pairs = int(cum_state.get("cumulative_pairs") or 0)

    # σ 산출 시 cumulative_trades 기준으로 binomial SE 계산하도록 baseline 에 effective_n 주입
    if isinstance(baseline, dict) and "effective_n" not in baseline:
        baseline = {**baseline, "effective_n": cumulative_trades}

    # ── phase 판정 ──
    source_used = (ground_truth or {}).get("source_used") or "primary"
    if source_used == "stale_unknown":
        phase = "STALE_UNKNOWN"
    else:
        # 1차 산출: cumulative_trades 기반
        base_phase = determine_operating_phase(cumulative_trades)

        # phase 비가역성 (snapshot_n 변동으로 reverse 차단)
        prev_state = _load_phase_state(phase_state_path)
        irreversible_phase = _phase_max(
            prev_state.get("max_phase") or "INSUFFICIENT_DATA", base_phase
        )
        _update_phase_state(
            phase_state_path,
            current_snapshot_n=total_recs_today,
            current_phase=irreversible_phase,
        )
        phase = irreversible_phase
    enabled_tiers = _enabled_tiers(phase)

    # ── baseline degradation alert (§6 floor) ──
    baseline_alert = None
    if baseline.get("floor_applied"):
        baseline_alert = "ALERT_BASELINE_DEGRADATION"

    # ── snapshot_pair 구성 ──
    snapshot_pair = {
        "verdict_at_t_minus_14": verdict_at_t_minus_14 or "MISSING",
        "hit_rate_from_snapshot": ground_truth.get("hit_rate"),
        "snapshot_n": total_recs_today,
        "cumulative_trades": cumulative_trades,
        "cumulative_pairs": cumulative_pairs,
        "as_of": ground_truth.get("as_of"),
        "source_used": source_used,
    }

    # ── STALE_UNKNOWN path ──
    if phase == "STALE_UNKNOWN":
        return _build_result(
            evaluation_date=evaluation_date,
            phase="STALE_UNKNOWN",
            snapshot_pair=snapshot_pair,
            evaluator_results=[
                _skipped_eval(ev.sub_factor_name, "stale_source_no_fallback")
                for ev in evaluators
            ],
            trust_score_result=trust_score_result,
            baseline_alert=baseline_alert,
            violations_path=violations_path,
            history_fetcher=history_fetcher,
            rolling_violations_fetcher=rolling_violations_fetcher,
            persist=False,
        )

    # ── INSUFFICIENT_DATA / verdict 부재 path ──
    if verdict_at_t_minus_14 is None:
        return _build_result(
            evaluation_date=evaluation_date,
            phase="INSUFFICIENT_DATA",
            snapshot_pair=snapshot_pair,
            evaluator_results=[
                _skipped_eval(ev.sub_factor_name, "t_minus_14_verdict_missing")
                for ev in evaluators
            ],
            trust_score_result=trust_score_result,
            baseline_alert=baseline_alert,
            violations_path=violations_path,
            history_fetcher=history_fetcher,
            rolling_violations_fetcher=rolling_violations_fetcher,
            persist=False,
        )

    if phase == "INSUFFICIENT_DATA":
        return _build_result(
            evaluation_date=evaluation_date,
            phase="INSUFFICIENT_DATA",
            snapshot_pair=snapshot_pair,
            evaluator_results=[
                _skipped_eval(
                    ev.sub_factor_name,
                    f"cumulative_trades={cumulative_trades} below Gate A ({GATE_A_MIN_TRADES})",
                )
                for ev in evaluators
            ],
            trust_score_result=trust_score_result,
            baseline_alert=baseline_alert,
            violations_path=violations_path,
            history_fetcher=history_fetcher,
            rolling_violations_fetcher=rolling_violations_fetcher,
            persist=False,
        )

    # ── 평가 ──
    evaluator_results: List[Dict[str, Any]] = []
    for ev in evaluators:
        result = ev.evaluate(
            verdict_at_t_minus_14=verdict_at_t_minus_14,
            ground_truth=ground_truth,
            baseline=baseline,
            enabled_tiers=enabled_tiers,
        )
        evaluator_results.append(result)

    return _build_result(
        evaluation_date=evaluation_date,
        phase=phase,
        snapshot_pair=snapshot_pair,
        evaluator_results=evaluator_results,
        trust_score_result=trust_score_result,
        baseline_alert=baseline_alert,
        violations_path=violations_path,
        history_fetcher=history_fetcher,
        rolling_violations_fetcher=rolling_violations_fetcher,
        persist=persist,
    )


def _make_evaluator_adapter(
    evaluation_date: str,
    backtest_stats_fetcher: Optional[Any],
    baseline_override: Optional[Dict[str, Any]],
):
    """run_cross_link 의 mock fetcher 를 evaluator-internal fetcher 인터페이스로 변환."""
    STALE_HOURS = 6

    def adapter(req: str):
        if req == "__baseline__":
            return baseline_override

        if backtest_stats_fetcher is None:
            return None

        stats = backtest_stats_fetcher() or {}
        period = (stats.get("periods") or {}).get("14d") or {}
        as_of = stats.get("updated_at") or stats.get("collected_at") or stats.get("as_of")

        # stale 판정
        as_of_dt = _parse_iso(as_of)
        eval_dt = _parse_iso(evaluation_date) or datetime.now(KST)
        if eval_dt.tzinfo is None:
            eval_dt = eval_dt.replace(tzinfo=KST)
        stale = True
        if as_of_dt is not None:
            if as_of_dt.tzinfo is None:
                as_of_dt = as_of_dt.replace(tzinfo=KST)
            stale = (eval_dt - as_of_dt) > timedelta(hours=STALE_HOURS)

        from .cross_link_evaluators.brain_distribution_evaluator import _normalize_to_ratio

        return {
            "hit_rate": _normalize_to_ratio(period.get("hit_rate")),
            "snapshot_n": int(period.get("total_recs") or 0),
            "as_of": as_of,
            "source_used": "stale_unknown" if stale else "primary_mock",
            "snapshot_date": period.get("snapshot_date"),
        }

    return adapter


def _skipped_eval(name: str, reason: str) -> Dict[str, Any]:
    return {
        "sub_factor_name": name,
        "evaluation": "SKIPPED",
        "violation_type": None,
        "baseline_used": None,
        "sigma_used": None,
        "k_threshold": 0,
        "evidence": f"skipped: {reason}",
    }


def _build_result(
    evaluation_date: str,
    phase: str,
    snapshot_pair: Dict[str, Any],
    evaluator_results: List[Dict[str, Any]],
    trust_score_result: Dict[str, Any],
    baseline_alert: Optional[str],
    violations_path: str,
    persist: bool,
    history_fetcher: Optional[Any] = None,
    rolling_violations_fetcher: Optional[Any] = None,
) -> Dict[str, Any]:
    # ── violation 집계 ──
    violations = [r for r in evaluator_results if r.get("violation_type") is not None]
    silent_pass_violations = [
        r for r in violations if r.get("violation_type") == "silent_pass"
    ]
    cry_wolf_violations = [
        r for r in violations if r.get("violation_type") == "cry_wolf"
    ]

    # ── §9-1 alert_tier (dashboard only — verdict 영향 X, v1.4.1 §9-1) ──
    tier_rank = {"TIER1": 1, "TIER2": 2, "TIER3": 3}
    max_tier = 0
    for r in violations:
        t = tier_rank.get(r.get("evaluation"), 0)
        if t > max_tier:
            max_tier = t
    alert_tier = {0: None, 1: "yellow", 2: "orange", 3: "red"}[max_tier]

    # ── §5 instant_hold 판정 (silent_pass rolling+this ≥ 3) ──
    if history_fetcher is not None:
        rolling_silent_pass_count = _history_list_to_silent_pass_count(
            history_fetcher(ROLLING_WINDOW_DAYS)
        )
    else:
        rolling_silent_pass_count = _rolling_window_violations(violations_path, evaluation_date)
    instant_hold = (
        rolling_silent_pass_count + len(silent_pass_violations)
    ) >= INSTANT_HOLD_THRESHOLD

    # ── §9-2 escalation 산출 (TIER2≥3 / TIER3≥1, TIER1 비활성) ──
    if rolling_violations_fetcher is not None:
        rolling_counts = _rolling_tier_counts_from_list(
            rolling_violations_fetcher(ROLLING_WINDOW_DAYS)
        )
    elif history_fetcher is not None:
        # history_fetcher 가 list 반환 시 그대로 Tier 카운트로 활용
        rolling_counts = _rolling_tier_counts_from_list(history_fetcher(ROLLING_WINDOW_DAYS))
    else:
        rolling_counts = _rolling_tier_counts_from_jsonl(violations_path, evaluation_date)
    escalation_result = _evaluate_noise_floor_escalation(
        rolling_counts=rolling_counts,
        cycle_violations=violations,
    )

    # ── verdict 통합 산출 ──
    raw_failed = (trust_score_result or {}).get("total", 0) - (trust_score_result or {}).get("satisfied", 0)
    if raw_failed < 0:
        raw_failed = 0
    verdict_meta = _compute_final_verdict(
        raw_failed=raw_failed,
        instant_hold=instant_hold,
        escalation_result=escalation_result,
        phase=phase,
    )

    # cross_link_violation_clear: §9-2 escalation 또는 instant_hold 발동 = False
    cross_link_violation_clear = (escalation_result is None) and (not instant_hold)

    result = {
        "evaluation_date": evaluation_date,
        "operating_phase": phase,
        "snapshot_pair": snapshot_pair,
        "evaluators": evaluator_results,
        "cross_link_violation_clear": cross_link_violation_clear,
        "instant_hold": instant_hold,
        "escalation_result": escalation_result,
        "final_verdict": verdict_meta["final_verdict"],
        "alert_tier": alert_tier,
        "baseline_alert": baseline_alert,
        "recompute_meta": {
            "raw_failed": verdict_meta["raw_failed"],
            "instant_hold_active": verdict_meta["instant_hold_active"],
            "escalation_active": verdict_meta["escalation_active"],
            "escalation_trigger_tier": verdict_meta["escalation_trigger_tier"],
            "verdict_logic": verdict_meta["verdict_logic"],
        },
        "_meta": {
            "rolling_window_silent_pass_count": rolling_silent_pass_count,
            "rolling_tier_counts": rolling_counts,
            "cry_wolf_count_in_run": len(cry_wolf_violations),
            "spec_version": "VERITY-CROSSLINK-THRESHOLDS-V1.5-simplified",
        },
    }

    if persist and (violations or baseline_alert):
        _persist(result, violations_path)

    return result


def _persist(result: Dict[str, Any], violations_path: str) -> None:
    """v1.4.1 §16 영속화. cross_link_violations.jsonl entry 1줄."""
    try:
        os.makedirs(os.path.dirname(violations_path) or ".", exist_ok=True)
        with open(violations_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(result, ensure_ascii=False, default=str) + "\n")
    except OSError as e:
        logger.warning("cross_link_violations.jsonl persist failed: %s", e)
