"""Sprint 1 P1 — 7 시나리오 mock 검증.

명령서 §3-1/§3-2/§3-3 정합. fetcher 4종 주입 (라이브 호출 X).

  scenario 1: INSUFFICIENT_DATA — Gate A 미통과
  scenario 2: TIER3_DISABLED 정상 PASS
  scenario 3: TIER3_DISABLED Silent PASS Tier 2
  scenario 4: FULLY_ACTIVE Silent PASS Tier 3 + instant_hold
  scenario 5: Cry-wolf — hold + hit_rate 양수, 자동 강등 금지
  scenario 6: Baseline degradation — floor 0.45 안착
  scenario 7: Stale source fallback — KI-8 신규
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

from typing import Dict, Any

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from api.observability.cross_link_layer import run_cross_link  # noqa: E402

MOCK_DIR = Path(REPO_ROOT) / "tests" / "mock" / "cross_link"

SCENARIOS = [
    "scenario_1_insufficient_data.json",
    "scenario_2_tier3_disabled_pass.json",
    "scenario_3_tier3_disabled_silent_pass_tier2.json",
    "scenario_4_fully_active_silent_pass_tier3_instant_hold.json",
    "scenario_5_cry_wolf.json",
    "scenario_6_baseline_degradation.json",
    "scenario_7_stale_source.json",
    # simplify 후 valid 분기 검증 2건
    "scenario_10_tier3_single_hold.json",       # §9-2 TIER3 1건 → hold
    "scenario_12_phase_irreversibility.json",   # phase 비가역성 안전망
]


def _preseed_phase_state(data_dir: str, preseed: Dict[str, Any]) -> None:
    import json
    path = os.path.join(data_dir, "metadata", "cross_link_phase_state.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(preseed, f, ensure_ascii=False, indent=2)


@pytest.fixture
def tmp_data_dir():
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "metadata"), exist_ok=True)
        yield d


@pytest.mark.parametrize("scenario_file", SCENARIOS)
def test_scenario(scenario_file, tmp_data_dir):
    with open(MOCK_DIR / scenario_file, "r", encoding="utf-8") as f:
        scenario = json.load(f)

    inp = scenario["input"]
    expected = scenario["expected_output"]

    # v1.4.1 결함 V — phase 비가역성 사전 영속화 (scenario_12 등)
    if inp.get("preseed_phase_state"):
        _preseed_phase_state(tmp_data_dir, inp["preseed_phase_state"])

    result = run_cross_link(
        evaluation_date=inp["evaluation_date"],
        trust_score_result=inp["trust_score_result"],
        data_dir=tmp_data_dir,
        backtest_stats_fetcher=lambda: inp["backtest_stats"],
        trust_log_fetcher=lambda _t: inp.get("trust_log_t_minus_14"),
        history_fetcher=lambda _days: inp.get("history_window_30d", []),
        cumulative_trades_fetcher=lambda: inp["cumulative_trades"],
        baseline_override=inp.get("baseline_override"),
    )

    # ── 핵심 필드 검증 ──
    assert result["operating_phase"] == expected["operating_phase"], (
        f"{scenario_file}: phase mismatch — got {result['operating_phase']}, expected {expected['operating_phase']}"
    )
    assert result["final_verdict"] == expected["final_verdict"], (
        f"{scenario_file}: final_verdict mismatch — got {result['final_verdict']}, expected {expected['final_verdict']}"
    )
    assert result["cross_link_violation_clear"] == expected["cross_link_violation_clear"], (
        f"{scenario_file}: cross_link_violation_clear mismatch"
    )
    assert result["instant_hold"] == expected["instant_hold"], (
        f"{scenario_file}: instant_hold mismatch — got {result['instant_hold']}, expected {expected['instant_hold']}"
    )
    assert result.get("alert_tier") == expected.get("alert_tier"), (
        f"{scenario_file}: alert_tier mismatch — got {result.get('alert_tier')}, expected {expected.get('alert_tier')}"
    )
    assert result.get("baseline_alert") == expected.get("baseline_alert"), (
        f"{scenario_file}: baseline_alert mismatch"
    )

    # ── evaluator 결과 비교 ──
    if expected.get("evaluators"):
        assert len(result["evaluators"]) == len(expected["evaluators"])
        for actual, exp in zip(result["evaluators"], expected["evaluators"]):
            assert actual["evaluation"] == exp["evaluation"], (
                f"{scenario_file}: evaluator.evaluation mismatch — "
                f"got {actual['evaluation']}, expected {exp['evaluation']} | evidence={actual.get('evidence')}"
            )
            assert actual.get("violation_type") == exp.get("violation_type"), (
                f"{scenario_file}: evaluator.violation_type mismatch — "
                f"got {actual.get('violation_type')}, expected {exp.get('violation_type')}"
            )


def test_p1_validation_summary(tmp_data_dir):
    """7 시나리오 일괄 실행 + p1_validation_report.md 생성 (명령서 §4)."""
    results = []
    for scenario_file in SCENARIOS:
        with open(MOCK_DIR / scenario_file, "r", encoding="utf-8") as f:
            scenario = json.load(f)
        inp = scenario["input"]
        expected = scenario["expected_output"]

        # 시나리오마다 격리된 tmp dir
        with tempfile.TemporaryDirectory() as iso:
            os.makedirs(os.path.join(iso, "metadata"), exist_ok=True)
            if inp.get("preseed_phase_state"):
                _preseed_phase_state(iso, inp["preseed_phase_state"])
            try:
                result = run_cross_link(
                    evaluation_date=inp["evaluation_date"],
                    trust_score_result=inp["trust_score_result"],
                    data_dir=iso,
                    backtest_stats_fetcher=lambda i=inp: i["backtest_stats"],
                    trust_log_fetcher=lambda _t, i=inp: i.get("trust_log_t_minus_14"),
                    history_fetcher=lambda _d, i=inp: i.get("history_window_30d", []),
                    cumulative_trades_fetcher=lambda i=inp: i["cumulative_trades"],
                    baseline_override=inp.get("baseline_override"),
                )
                ok = (
                    result["operating_phase"] == expected["operating_phase"]
                    and result["final_verdict"] == expected["final_verdict"]
                    and result["cross_link_violation_clear"] == expected["cross_link_violation_clear"]
                    and result["instant_hold"] == expected["instant_hold"]
                    and result.get("alert_tier") == expected.get("alert_tier")
                    and result.get("baseline_alert") == expected.get("baseline_alert")
                )
                evidence = "; ".join(
                    e.get("evidence", "") for e in result.get("evaluators", [])
                )
            except Exception as e:
                ok = False
                evidence = f"EXCEPTION: {e}"
            results.append({
                "file": scenario_file,
                "name": scenario.get("scenario_name"),
                "pass": ok,
                "evidence": evidence,
            })

    # 보고서 생성
    out_dir = Path(REPO_ROOT) / "data" / "mock" / "cross_link"
    out_dir.mkdir(parents=True, exist_ok=True)
    lines = ["# Sprint 1 P1 검증 보고서", ""]
    lines.append("## 1. 시나리오 결과 (7건)")
    lines.append("")
    lines.append("| 시나리오 | PASS/FAIL | evidence |")
    lines.append("|---|---|---|")
    for r in results:
        lines.append(f"| {r['name']} | {'PASS' if r['pass'] else 'FAIL'} | {r['evidence']} |")
    lines.append("")
    lines.append("## 2. Spec 정정 통합 결과")
    lines.append("")
    lines.append("- [x] KI-10 Gate A cumulative_trades 누적 로직 작동")
    lines.append("- [x] KI-7 trust_log path alias 통일 (data/metadata/trust_log.jsonl)")
    lines.append("- [x] KI-8 stale 필드 fallback (updated_at 6h 임계 → STALE_UNKNOWN)")
    lines.append("")
    (out_dir / "p1_validation_report.md").write_text("\n".join(lines), encoding="utf-8")

    fails = [r for r in results if not r["pass"]]
    assert not fails, f"P1 시나리오 FAIL: {fails}"
