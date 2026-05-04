"""brain_distribution_normal sub-factor — hit rate cross-link evaluator.

v1.3 spec:
  - ground truth source: backtest_stats.json (Primary) / generate_verification_report (Secondary)
  - baseline: 직전 90일 rolling mean. floor 0.45. cold-start 0.5.
  - 임계: baseline ± kσ (silent_pass / cry_wolf 대칭, 단 처리 정책은 비대칭)
  - unit: 0~1 비율 통일

source 가 percent (50.0) 형식이면 즉시 /100. assert 0~1.
"""
from __future__ import annotations

import json
import logging
import math
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .base import CrossLinkEvaluator

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))

BASELINE_FLOOR = 0.45
COLD_START_BASELINE = 0.50
COLD_START_LIMIT = 50  # n < 50 → cold-start
STALE_THRESHOLD_HOURS = 6


def _normalize_to_ratio(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v > 1.0:
        v = v / 100.0
    if v < 0 or v > 1:
        return None
    return v


def _parse_iso(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)
    except (TypeError, ValueError):
        return None


class BrainDistributionEvaluator(CrossLinkEvaluator):
    sub_factor_name = "brain_distribution_normal"

    def __init__(self, data_dir: Optional[str] = None, fetcher=None):
        if data_dir is None:
            from api.config import DATA_DIR
            data_dir = DATA_DIR
        self.data_dir = data_dir
        self._fetcher = fetcher  # P1 mock 주입용

    # ───────────────────── Ground truth ─────────────────────

    def fetch_ground_truth(self, evaluation_date: str) -> Dict[str, Any]:
        """v1.3 §1 — Primary: backtest_stats.json. 6h stale 시 secondary fallback."""
        if self._fetcher is not None:
            return self._fetcher(evaluation_date)

        path = os.path.join(self.data_dir, "backtest_stats.json")
        primary: Dict[str, Any] = {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                primary = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.warning("backtest_stats.json read failed: %s", e)

        as_of = primary.get("updated_at") or primary.get("collected_at") or primary.get("as_of")
        as_of_dt = _parse_iso(as_of)
        now = datetime.now(KST)
        stale = True
        if as_of_dt is not None:
            if as_of_dt.tzinfo is None:
                as_of_dt = as_of_dt.replace(tzinfo=KST)
            stale = (now - as_of_dt) > timedelta(hours=STALE_THRESHOLD_HOURS)

        if stale:
            try:
                from api.intelligence.backtest_archive import generate_verification_report
                _ = generate_verification_report()
                with open(path, "r", encoding="utf-8") as f:
                    primary = json.load(f)
                as_of = primary.get("updated_at") or as_of
                source_used = "secondary_regenerated"
            except Exception as e:
                logger.warning("generate_verification_report fallback failed: %s", e)
                source_used = "primary_stale"
        else:
            source_used = "primary"

        period_14d = (primary.get("periods") or {}).get("14d") or {}
        hit_rate_raw = period_14d.get("hit_rate")
        hit_rate = _normalize_to_ratio(hit_rate_raw)
        snapshot_n = int(period_14d.get("total_recs") or 0)

        return {
            "hit_rate": hit_rate,
            "snapshot_n": snapshot_n,
            "as_of": as_of,
            "source_used": source_used,
            "snapshot_date": period_14d.get("snapshot_date"),
        }

    # ───────────────────── Baseline ─────────────────────

    def compute_baseline(self, lookback_days: int = 90) -> Dict[str, Any]:
        """v1.3 §6 — historical mean + floor 0.45. cold-start (누적<50) 0.5 임시."""
        if self._fetcher is not None:
            override = self._fetcher("__baseline__")
            if override:
                return override

        history_path = os.path.join(self.data_dir, "metadata", "backtest_stats_history.jsonl")
        rates: List[float] = []
        if os.path.exists(history_path):
            cutoff = datetime.now(KST) - timedelta(days=lookback_days)
            try:
                with open(history_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            row = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        ts = _parse_iso(row.get("updated_at") or row.get("timestamp"))
                        if ts is None:
                            continue
                        if ts.tzinfo is None:
                            ts = ts.replace(tzinfo=KST)
                        if ts < cutoff:
                            continue
                        v = _normalize_to_ratio(row.get("hit_rate_14d") or row.get("hit_rate"))
                        if v is not None:
                            rates.append(v)
            except OSError as e:
                logger.warning("baseline history read failed: %s", e)

        n = len(rates)
        if n < COLD_START_LIMIT:
            return {
                "baseline": COLD_START_BASELINE,
                "sigma": None,  # binomial SE 는 evaluate 시점 snapshot_n 으로 산출
                "cold_start": True,
                "n_history": n,
                "floor_applied": False,
                "raw_mean": (sum(rates) / n) if n else None,
            }

        raw_mean = sum(rates) / n
        variance = sum((r - raw_mean) ** 2 for r in rates) / n
        sigma_hist = math.sqrt(variance)

        baseline = raw_mean
        floor_applied = False
        if baseline < BASELINE_FLOOR:
            baseline = BASELINE_FLOOR
            floor_applied = True

        return {
            "baseline": baseline,
            "sigma": sigma_hist if sigma_hist > 0 else None,
            "cold_start": False,
            "n_history": n,
            "floor_applied": floor_applied,
            "raw_mean": raw_mean,
        }

    # ───────────────────── Evaluate ─────────────────────

    def evaluate(
        self,
        verdict_at_t_minus_14: str,
        ground_truth: Dict[str, Any],
        baseline: Dict[str, Any],
        enabled_tiers: List[int],
    ) -> Dict[str, Any]:
        """v1.3 §3 verdict 매핑 + §7 z-score 임계 적용."""
        hit_rate = ground_truth.get("hit_rate")
        snapshot_n = int(ground_truth.get("snapshot_n") or 0)
        baseline_value = float(baseline.get("baseline", COLD_START_BASELINE))

        # σ 우선순위: historical σ > binomial SE.
        # binomial SE 의 n 은 cumulative_trades (effective_n) 우선, 없으면 snapshot_n fallback.
        sigma = baseline.get("sigma")
        if sigma is None:
            n_for_sigma = int(baseline.get("effective_n") or snapshot_n or 0)
            if n_for_sigma > 0:
                p = baseline_value
                sigma = math.sqrt(p * (1 - p) / n_for_sigma)

        # v1.3 §3: ready / hold 만 평가, manual_review 는 SKIPPED
        if verdict_at_t_minus_14 == "manual_review":
            return self._skipped_result(
                "verdict_manual_review", baseline_value, sigma
            )

        if hit_rate is None:
            return self._skipped_result(
                "hit_rate_unavailable", baseline_value, sigma
            )

        if sigma is None or sigma <= 0:
            return self._skipped_result(
                "sigma_unavailable", baseline_value, sigma
            )

        # 위반 방향: silent_pass = ready 인데 hit_rate < baseline - kσ
        #            cry_wolf  = hold  인데 hit_rate > baseline + kσ
        violation_type = None
        triggered_tier = None
        k_used = 0

        if verdict_at_t_minus_14 == "ready":
            for k in (3, 2, 1):
                if k not in enabled_tiers:
                    continue
                threshold = baseline_value - k * sigma
                if hit_rate < threshold:
                    violation_type = "silent_pass"
                    triggered_tier = k
                    k_used = k
                    break
        elif verdict_at_t_minus_14 == "hold":
            for k in (3, 2, 1):
                if k not in enabled_tiers:
                    continue
                threshold = baseline_value + k * sigma
                if hit_rate > threshold:
                    violation_type = "cry_wolf"
                    triggered_tier = k
                    k_used = k
                    break
        else:
            return self._skipped_result(
                f"unknown_verdict:{verdict_at_t_minus_14}", baseline_value, sigma
            )

        if violation_type is None:
            evaluation = "PASS"
            evidence = (
                f"hit_rate={hit_rate:.3f} within baseline={baseline_value:.3f} "
                f"± {min(enabled_tiers or [1])}σ ({sigma:.3f})"
            )
        else:
            evaluation = f"TIER{triggered_tier}"
            direction = "below" if violation_type == "silent_pass" else "above"
            sign = "-" if violation_type == "silent_pass" else "+"
            evidence = (
                f"hit_rate={hit_rate:.3f} {direction} baseline={baseline_value:.3f} "
                f"{sign}{triggered_tier}σ ({sigma:.3f})"
            )

        return {
            "sub_factor_name": self.sub_factor_name,
            "evaluation": evaluation,
            "violation_type": violation_type,
            "direction": violation_type,  # v1.4.1 §7-2 alias — 영속화 schema 정합
            "baseline_used": baseline_value,
            "sigma_used": sigma,
            "k_threshold": k_used,
            "evidence": evidence,
        }

    def _skipped_result(self, reason: str, baseline_value: float, sigma) -> Dict[str, Any]:
        return {
            "sub_factor_name": self.sub_factor_name,
            "evaluation": "SKIPPED",
            "violation_type": None,
            "baseline_used": baseline_value,
            "sigma_used": sigma,
            "k_threshold": 0,
            "evidence": f"skipped: {reason}",
        }
