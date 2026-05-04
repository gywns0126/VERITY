"""cross_link_layer P0 단위 테스트.

5 시나리오:
  T1. 출력 schema 정합성 + INSUFFICIENT_DATA path (Gate A 미통과)
  T2. TIER3_DISABLED 정상 PASS (n=30, hit_rate within ±1σ of baseline)
  T3. Silent PASS Tier 2 detection (ready 인데 hit_rate ≪ baseline - 2σ)
  T4. Cry-wolf Tier 2 detection (hold 인데 hit_rate ≫ baseline + 2σ, 자동 강등 X)
  T5. Self-healing loop 차단 — 현재 verdict 무관, T-14 verdict 가 평가 단위

mock fetcher 로 ground truth + baseline 주입. 라이브 호출 X.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from api.observability.cross_link_layer import run_cross_link  # noqa: E402
from api.observability.cross_link_evaluators import BrainDistributionEvaluator  # noqa: E402

KST = timezone(timedelta(hours=9))


def _iso(year=2026, month=5, day=3, hour=10):
    return datetime(year, month, day, hour, 0, 0, tzinfo=KST).isoformat()


def _seed_trust_log(path: str, t14_verdict: str | None, t14_iso: str):
    """T-14 시점 entry 1개 + 노이즈 1개."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        if t14_verdict is not None:
            entry = {
                "timestamp": t14_iso,
                "verdict": t14_verdict,
                "satisfied": 8 if t14_verdict == "ready" else 5,
                "total": 8,
                "blocking_reasons": [],
            }
            f.write(json.dumps(entry) + "\n")
        # 노이즈 (오래된 entry)
        old = {
            "timestamp": _iso(2026, 4, 1, 10),
            "verdict": "ready",
            "satisfied": 8,
            "total": 8,
            "blocking_reasons": [],
        }
        f.write(json.dumps(old) + "\n")


def _make_evaluator(hit_rate: float | None, snapshot_n: int, baseline: dict):
    """fetcher 주입형 evaluator."""

    def fetcher(evaluation_date: str):
        if evaluation_date == "__baseline__":
            return baseline
        return {
            "hit_rate": hit_rate,
            "snapshot_n": snapshot_n,
            "as_of": evaluation_date,
            "source_used": "mock",
            "snapshot_date": "2026-04-19",
        }

    return BrainDistributionEvaluator(data_dir="/tmp/__noop__", fetcher=fetcher)


class CrossLinkLayerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data_dir = self.tmp.name
        os.makedirs(os.path.join(self.data_dir, "metadata"), exist_ok=True)
        self.trust_log = os.path.join(self.data_dir, "metadata", "trust_log.jsonl")
        self.violations = os.path.join(self.data_dir, "cross_link_violations.jsonl")
        self.eval_date = _iso(2026, 5, 3, 10)
        self.t14_date = _iso(2026, 4, 19, 10)
        self.trust_ready = {
            "verdict": "ready",
            "satisfied": 8,
            "total": 8,
            "blocking_reasons": [],
        }
        self.trust_hold = {
            "verdict": "hold",
            "satisfied": 4,
            "total": 8,
            "blocking_reasons": ["x", "y", "z", "w"],
        }

    def tearDown(self):
        self.tmp.cleanup()

    # ────────── T1 ──────────
    def test_t1_schema_and_insufficient_data(self):
        _seed_trust_log(self.trust_log, "ready", self.t14_date)
        ev = _make_evaluator(
            hit_rate=0.50,
            snapshot_n=8,  # Gate A 미통과
            baseline={"baseline": 0.50, "sigma": None, "cold_start": True,
                      "n_history": 0, "floor_applied": False, "raw_mean": None},
        )
        out = run_cross_link(
            evaluation_date=self.eval_date,
            trust_score_result=self.trust_ready,
            evaluators=[ev],
            data_dir=self.data_dir,
            trust_log_path=self.trust_log,
            violations_path=self.violations,
        )
        # schema 정합성 — simplify 후 키 (rate_limit_status 폐기)
        for key in (
            "evaluation_date", "operating_phase", "snapshot_pair", "evaluators",
            "cross_link_violation_clear", "instant_hold", "escalation_result",
            "final_verdict", "alert_tier", "baseline_alert", "recompute_meta",
        ):
            self.assertIn(key, out, f"missing key: {key}")
        self.assertEqual(out["operating_phase"], "INSUFFICIENT_DATA")
        self.assertEqual(out["evaluators"][0]["evaluation"], "SKIPPED")
        self.assertTrue(out["cross_link_violation_clear"])
        # INSUFFICIENT_DATA 는 jsonl 영속 X
        self.assertFalse(os.path.exists(self.violations))

    # ────────── T2 ──────────
    def test_t2_tier3_disabled_pass(self):
        _seed_trust_log(self.trust_log, "ready", self.t14_date)
        ev = _make_evaluator(
            hit_rate=0.52,
            snapshot_n=30,  # TIER3_DISABLED 구간
            baseline={"baseline": 0.50, "sigma": 0.091, "cold_start": False,
                      "n_history": 60, "floor_applied": False, "raw_mean": 0.50},
        )
        out = run_cross_link(
            evaluation_date=self.eval_date,
            trust_score_result=self.trust_ready,
            evaluators=[ev],
            data_dir=self.data_dir,
            trust_log_path=self.trust_log,
            violations_path=self.violations,
        )
        self.assertEqual(out["operating_phase"], "TIER3_DISABLED")
        self.assertEqual(out["evaluators"][0]["evaluation"], "PASS")
        self.assertTrue(out["cross_link_violation_clear"])
        self.assertEqual(out["final_verdict"], "ready")
        self.assertIsNone(out["alert_tier"])

    # ────────── T3 (v1.4.1 분기 4 — TIER2 1건만으로는 강등 X) ──────────
    def test_t3_silent_pass_tier2(self):
        _seed_trust_log(self.trust_log, "ready", self.t14_date)
        # baseline=0.50, σ=0.091 → -2σ=0.318. hit_rate=0.30 < 0.318 → TIER2 silent_pass
        # v1.4.1 §9-1: cycle 단위 alert_tier=orange (dashboard) but verdict 영향 X
        # §9-2 escalation: TIER2 누적 1건 < 임계 3 → 미발동 → final_verdict=ready
        ev = _make_evaluator(
            hit_rate=0.30,
            snapshot_n=30,
            baseline={"baseline": 0.50, "sigma": 0.091, "cold_start": False,
                      "n_history": 60, "floor_applied": False, "raw_mean": 0.50},
        )
        out = run_cross_link(
            evaluation_date=self.eval_date,
            trust_score_result=self.trust_ready,
            evaluators=[ev],
            data_dir=self.data_dir,
            trust_log_path=self.trust_log,
            violations_path=self.violations,
        )
        self.assertEqual(out["evaluators"][0]["evaluation"], "TIER2")
        self.assertEqual(out["evaluators"][0]["violation_type"], "silent_pass")
        self.assertEqual(out["alert_tier"], "orange")  # §9-1 dashboard
        # §9-2 escalation 미발동 (누적 1건 < 임계 3)
        self.assertIsNone(out["escalation_result"])
        self.assertFalse(out["recompute_meta"]["escalation_active"])
        self.assertTrue(out["cross_link_violation_clear"])
        # final_verdict = ready (cycle 1건만으로 강등 X)
        self.assertEqual(out["final_verdict"], "ready")
        # 영속화 발생 (cycle violation 1건 trail)
        self.assertTrue(os.path.exists(self.violations))

    # ────────── T4 ──────────
    def test_t4_cry_wolf_tier2_no_auto_demote(self):
        _seed_trust_log(self.trust_log, "hold", self.t14_date)
        # baseline=0.50, σ=0.071 → +2σ=0.642. hit_rate=0.65 > 0.642 → TIER2 cry_wolf
        ev = _make_evaluator(
            hit_rate=0.65,
            snapshot_n=50,  # FULLY_ACTIVE
            baseline={"baseline": 0.50, "sigma": 0.071, "cold_start": False,
                      "n_history": 90, "floor_applied": False, "raw_mean": 0.50},
        )
        out = run_cross_link(
            evaluation_date=self.eval_date,
            trust_score_result=self.trust_hold,
            evaluators=[ev],
            data_dir=self.data_dir,
            trust_log_path=self.trust_log,
            violations_path=self.violations,
        )
        self.assertEqual(out["evaluators"][0]["evaluation"], "TIER2")
        self.assertEqual(out["evaluators"][0]["violation_type"], "cry_wolf")
        # cry_wolf 는 §9-2 escalation 합산 X (silent_pass 단방향만)
        self.assertTrue(out["cross_link_violation_clear"])
        self.assertIsNone(out["escalation_result"])
        self.assertFalse(out["recompute_meta"]["escalation_active"])
        # final_verdict 은 trust_score 의 hold 그대로 (raw_failed=4 → hold)
        self.assertEqual(out["final_verdict"], "hold")
        self.assertEqual(out["alert_tier"], "orange")  # §9-1 dashboard
        # cry_wolf 도 영속화 (trail 보존)
        self.assertTrue(os.path.exists(self.violations))

    # ────────── T5 ──────────
    def test_t5_self_healing_loop_blocked(self):
        """현재 verdict 무관, T-14 시점 verdict 가 평가 단위."""
        # T-14 시점 = hold (snapshot 발행 당시)
        _seed_trust_log(self.trust_log, "hold", self.t14_date)
        # 현재 trust_score_result 은 ready (= self-healing 으로 자동 회복된 상태)
        # 만약 self-healing loop 가 작동했다면 현재 verdict=ready 로 평가해서
        # silent_pass 만 따져야 하지만, 우리는 T-14=hold 기준이라 cry_wolf 평가
        ev = _make_evaluator(
            hit_rate=0.70,
            snapshot_n=50,
            baseline={"baseline": 0.50, "sigma": 0.071, "cold_start": False,
                      "n_history": 90, "floor_applied": False, "raw_mean": 0.50},
        )
        out = run_cross_link(
            evaluation_date=self.eval_date,
            trust_score_result=self.trust_ready,  # ← 현재는 ready
            evaluators=[ev],
            data_dir=self.data_dir,
            trust_log_path=self.trust_log,
            violations_path=self.violations,
        )
        # T-14=hold + hit_rate=0.70 ≫ baseline+kσ → cry_wolf (TIER3)
        self.assertEqual(
            out["snapshot_pair"]["verdict_at_t_minus_14"], "hold",
            "self-healing 차단 실패: 현재 verdict 가 평가 단위로 사용됨"
        )
        self.assertEqual(out["evaluators"][0]["violation_type"], "cry_wolf")
        # 만약 self-healing 으로 ready 가 사용됐다면 silent_pass 평가가 됐을 것 — 그게 아님을 확인
        self.assertNotEqual(out["evaluators"][0]["violation_type"], "silent_pass")


if __name__ == "__main__":
    unittest.main()
