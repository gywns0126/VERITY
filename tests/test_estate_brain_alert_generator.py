"""ESTATE Brain Alert Generator — 단위 테스트 (V1 wiring).

검증:
  ① _rule_extreme — 4중 신호 ≥2 → 1 alert (high anomaly)
  ② _rule_lead_time — 강 verdict 만 alert
  ③ _rule_redev — max_uplift / valuation_pending / relocation 분기
  ④ generate_alerts — snapshots 전체 → 모든 룰 union
  ⑤ dedupe_key 정합성
  ⑥ T2 source marker (body 안 "ESTATE Brain V0.3")
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from api.intelligence import estate_brain_alert_generator as gen


def _brain_with_extreme(n: int = 3) -> dict:
    sigs = ["pir_z_extreme", "jeonse_ratio_below_50", "cap_treasury_inverted",
            "kb_actual_gap_extreme"][:n]
    return {
        "complex_id": "강남구_대치동_은마_1979",
        "valuation": {"extreme_signals": sigs, "extreme_signals_count": n,
                      "weighted_score": 15, "primary_anchor_pct": 30,
                      "layers": {}},
        "cycle_analog": {"current_phase": "Rate-Shock Rebound",
                          "lead_time_signals": {}},
        "redevelopment_stage": None,
    }


def _brain_with_lead_time(verdicts: dict) -> dict:
    leads = {key: {"verdict": v, "value_pct": 1.5, "value_yoy_pct": 30,
                    "rate_change_pp": -0.25, "lead_months": 6}
             for key, v in verdicts.items()}
    return {
        "complex_id": "마포구_아현동_마포래미안푸르지오_2014",
        "valuation": {"extreme_signals": [], "extreme_signals_count": 0,
                      "layers": {}},
        "cycle_analog": {"current_phase": "Rate-Shock Rebound",
                          "lead_time_signals": leads},
        "redevelopment_stage": None,
    }


def _brain_with_redev(stage: str, phase: str, monitoring: dict = None) -> dict:
    return {
        "complex_id": "강남구_대치동_은마_1979",
        "valuation": {"extreme_signals": [], "extreme_signals_count": 0, "layers": {}},
        "cycle_analog": {"current_phase": "Rate-Shock Rebound",
                          "lead_time_signals": {}},
        "redevelopment_stage": {
            "stage": stage, "stage_label_ko": "관리처분 인가",
            "project_type": "redevelopment", "months_in_stage": 4,
            "months_to_next_stage_estimated": 5, "price_phase": phase,
            "monitoring": monitoring or {"valuation_announcement_pending": False,
                                          "general_subscription_announced": False},
        },
    }


class TestRuleExtreme:
    def test_2_signals_emits_high_anomaly(self):
        brain = _brain_with_extreme(2)
        alerts = gen._rule_extreme(brain, "2026-05-09")
        assert len(alerts) == 1
        assert alerts[0]["severity"] == "high"
        assert alerts[0]["category"] == "anomaly"
        assert "2/4" in alerts[0]["title"]
        assert "ESTATE Brain V0.3" in alerts[0]["body"]
        assert alerts[0]["dedupe_key"].startswith("2026-05-09_brain_extreme_2_")

    def test_count_under_2_no_alert(self):
        brain = _brain_with_extreme(1)
        assert gen._rule_extreme(brain, "2026-05-09") == []

    def test_count_4_emits(self):
        brain = _brain_with_extreme(4)
        alerts = gen._rule_extreme(brain, "2026-05-09")
        assert len(alerts) == 1
        assert "4/4" in alerts[0]["title"]


class TestRuleLeadTime:
    def test_strong_verdict_emits(self):
        brain = _brain_with_lead_time({"unsold_units_lead": "negative_pressure_strong"})
        alerts = gen._rule_lead_time(brain, "2026-05-09")
        assert len(alerts) == 1
        assert alerts[0]["severity"] == "mid"
        assert "negative_pressure_strong" in alerts[0]["title"]
        assert alerts[0]["dedupe_key"].startswith(
            "2026-05-09_brain_lead_unsold_units_lead_negative_pressure_strong_"
        )

    def test_weak_verdict_no_alert(self):
        brain = _brain_with_lead_time({"jeonse_3m_lead": "moderate_up"})
        assert gen._rule_lead_time(brain, "2026-05-09") == []

    def test_multiple_strong_verdicts(self):
        brain = _brain_with_lead_time({
            "unsold_units_lead": "negative_pressure_strong",
            "jeonse_ratio_24m": "ambivalent_overheated",
            "construction_starts_lead": "supply_tight_in_2y",
            "rate_lead": "tightening_pressure",
            "jeonse_3m_lead": "moderate_up",  # weak — skip
        })
        alerts = gen._rule_lead_time(brain, "2026-05-09")
        assert len(alerts) == 4  # weak 1 제외


class TestRuleRedev:
    def test_max_uplift_emits_high_catalyst(self):
        brain = _brain_with_redev("management_plan", "max_uplift")
        alerts = gen._rule_redev(brain, "2026-05-09")
        assert len(alerts) == 1
        assert alerts[0]["severity"] == "high"
        assert alerts[0]["category"] == "catalyst"
        assert "최대 상승" in alerts[0]["title"]

    def test_valuation_pending_emits(self):
        brain = _brain_with_redev("management_plan", "max_uplift",
            monitoring={"valuation_announcement_pending": True,
                        "general_subscription_announced": False})
        alerts = gen._rule_redev(brain, "2026-05-09")
        # max_uplift 1 + valuation_pending 1 = 2
        assert len(alerts) == 2
        kinds = {a["dedupe_key"].split("_")[3] for a in alerts}
        # 둘 다 다른 dedupe subtype
        assert len({a["dedupe_key"] for a in alerts}) == 2

    def test_relocation_spillover(self):
        brain = _brain_with_redev("relocation", "rental_market_spillover")
        alerts = gen._rule_redev(brain, "2026-05-09")
        # relocation = spillover 1 (max_uplift X 다른 phase)
        assert len(alerts) == 1
        assert "이주" in alerts[0]["title"]
        assert alerts[0]["severity"] == "mid"

    def test_no_redev_no_alert(self):
        brain = _brain_with_extreme(0)  # redev None
        assert gen._rule_redev(brain, "2026-05-09") == []

    def test_pre_signal_no_alert(self):
        brain = _brain_with_redev("district_designation", "pre_signal")
        assert gen._rule_redev(brain, "2026-05-09") == []


class TestGenerateAlerts:
    def test_full_snapshot_combines_rules(self):
        snapshots = {
            "complexes": {
                "강남구_대치동_은마_1979": {
                    **_brain_with_extreme(3),
                    "redevelopment_stage": {
                        "stage": "management_plan", "stage_label_ko": "관리처분 인가",
                        "project_type": "redevelopment", "months_in_stage": 4,
                        "months_to_next_stage_estimated": 5, "price_phase": "max_uplift",
                        "monitoring": {"valuation_announcement_pending": True,
                                        "general_subscription_announced": False},
                    },
                    "cycle_analog": {
                        "current_phase": "Rate-Shock Rebound",
                        "lead_time_signals": {
                            "unsold_units_lead": {"verdict": "negative_pressure_strong",
                                                   "value_yoy_pct": 35, "lead_months": 4},
                        },
                    },
                },
            },
            "gu_aggregates": {},
        }
        alerts = gen.generate_alerts(snapshots)
        # extreme(3 signals=1 alert) + lead(strong=1) + redev(max+pending=2) = 4
        assert len(alerts) == 4
        cats = {a["category"] for a in alerts}
        assert "anomaly" in cats
        assert "catalyst" in cats

    def test_empty_snapshot_returns_empty(self):
        assert gen.generate_alerts(None) == []
        assert gen.generate_alerts({}) == []
        assert gen.generate_alerts({"complexes": {}, "gu_aggregates": {}}) == []

    def test_dedupe_keys_unique(self):
        snapshots = {
            "complexes": {
                "C1": {**_brain_with_extreme(3),
                       "complex_id": "강남구_C1_apt_2010",
                       "redevelopment_stage": None,
                       "cycle_analog": {"current_phase": "x",
                                         "lead_time_signals": {}}},
                "C2": {**_brain_with_extreme(2),
                       "complex_id": "송파구_C2_apt_2015",
                       "redevelopment_stage": None,
                       "cycle_analog": {"current_phase": "x",
                                         "lead_time_signals": {}}},
            },
            "gu_aggregates": {},
        }
        alerts = gen.generate_alerts(snapshots)
        keys = [a["dedupe_key"] for a in alerts]
        assert len(set(keys)) == len(keys)  # 모두 unique


class TestSourceMarker:
    def test_all_alerts_have_brain_marker(self):
        # T2 — body 안에 "ESTATE Brain V0.3" marker 가 있어야 함 (mock vs live 구분)
        snapshots = {
            "complexes": {"x": {**_brain_with_extreme(3),
                                "redevelopment_stage": None,
                                "cycle_analog": {"current_phase": "x",
                                                  "lead_time_signals": {
                                                      "unsold_units_lead": {
                                                          "verdict": "negative_pressure_strong",
                                                          "value_yoy_pct": 30,
                                                          "lead_months": 4},
                                                  }}}},
            "gu_aggregates": {},
        }
        alerts = gen.generate_alerts(snapshots)
        for a in alerts:
            assert "ESTATE Brain V0.3" in a["body"]
