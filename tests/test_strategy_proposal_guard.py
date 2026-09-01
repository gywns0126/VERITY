"""Strategy mutations must be current, scoped, and explicitly approved."""

from copy import deepcopy
from datetime import timedelta
import inspect
import json
from pathlib import Path

import pytest

from api.intelligence import strategy_evolver as se


def _constitution():
    return {
        "version": "5.0",
        "fact_score": {"weights": {"a": 0.5, "b": 0.5}},
        "sentiment_score": {"weights": {"x": 0.5, "y": 0.5}},
        "decision_tree": {
            "grades": {
                "BUY": {"min_brain_score": 60},
                "WATCH": {"min_brain_score": 45},
            }
        },
    }


def _registry():
    return {
        "current_version": 1,
        "auto_approve": False,
        "cumulative_stats": {
            "total_proposals": 1,
            "accepted": 0,
            "rejected": 0,
            "invalidated": 0,
            "unclassified": 1,
            "hit_count": 0,
        },
        "versions": [],
        "pending_proposal": None,
        "invalidated_proposals": [],
        "mutation_policy": {"mode": "manual_only", "requires_pm_approval": True},
    }


def _wire_files(monkeypatch, tmp_path, constitution=None, registry=None):
    constitution_path = tmp_path / "constitution.json"
    registry_path = tmp_path / "registry.json"
    constitution_path.write_text(
        json.dumps(constitution or _constitution()), encoding="utf-8"
    )
    registry_path.write_text(json.dumps(registry or _registry()), encoding="utf-8")
    monkeypatch.setattr(se, "_CONSTITUTION_PATH", str(constitution_path))
    monkeypatch.setattr(se, "_CONSTITUTION_BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.setattr(se, "STRATEGY_REGISTRY_PATH", str(registry_path))
    return constitution_path, registry_path


def test_context_rejects_constitution_change():
    constitution = _constitution()
    registry = _registry()
    context = se._proposal_context(constitution, registry)
    changed = deepcopy(constitution)
    changed["fact_score"]["weights"] = {"a": 0.4, "b": 0.6}

    valid, reason = se.validate_proposal_context(context, changed, registry)
    assert valid is False
    assert "content changed" in reason


def test_context_rejects_expired_proposal(monkeypatch):
    constitution = _constitution()
    registry = _registry()
    context = se._proposal_context(constitution, registry)
    context["expires_at"] = (se.now_kst() - timedelta(seconds=1)).isoformat()

    valid, reason = se.validate_proposal_context(context, constitution, registry)
    assert valid is False
    assert reason == "proposal expired"


def test_legacy_pending_is_archived_not_applied(monkeypatch, tmp_path):
    registry = _registry()
    registry["pending_proposal"] = {
        "proposal": {"changes": {"fact_score_weights": {"legacy": 1.0}}},
        "backtest_result": {},
        "proposed_at": "2026-06-05T09:00:48+09:00",
    }
    constitution_path, registry_path = _wire_files(
        monkeypatch, tmp_path, registry=registry
    )
    before = constitution_path.read_bytes()

    with pytest.raises(se.ProposalValidationError, match="context missing"):
        se.approve_pending_proposal()

    after_registry = json.loads(registry_path.read_text(encoding="utf-8"))
    assert constitution_path.read_bytes() == before
    assert after_registry["pending_proposal"] is None
    assert after_registry["cumulative_stats"]["invalidated"] == 1
    assert after_registry["invalidated_proposals"][0]["status"] == "invalidated_stale"


def test_apply_rejects_unknown_axis_even_with_current_context(monkeypatch, tmp_path):
    constitution_path, _ = _wire_files(monkeypatch, tmp_path)
    constitution = se._load_constitution()
    registry = se._load_registry()
    context = se._proposal_context(constitution, registry)
    before = constitution_path.read_bytes()

    with pytest.raises(se.ProposalValidationError, match="fact.*legacy"):
        se.apply_proposal(
            {"changes": {"fact_score_weights": {"legacy": 1.0}}},
            {},
            approval_context=context,
        )

    assert constitution_path.read_bytes() == before


def test_registry_ledger_preserves_unclassified_history():
    registry = json.loads(Path(se.STRATEGY_REGISTRY_PATH).read_text(encoding="utf-8"))
    stats = registry["cumulative_stats"]
    pending = 1 if registry.get("pending_proposal") else 0
    accounted = (
        stats.get("accepted", 0)
        + stats.get("rejected", 0)
        + stats.get("invalidated", 0)
        + stats.get("unclassified", 0)
        + pending
    )
    assert stats["total_proposals"] == accounted
    assert stats["unclassified"] == 30


def test_registry_loader_derives_missing_unclassified_count(monkeypatch, tmp_path):
    registry = _registry()
    registry["auto_approve"] = True
    registry["cumulative_stats"].pop("unclassified")
    _wire_files(monkeypatch, tmp_path, registry=registry)

    loaded = se._load_registry()

    assert loaded["cumulative_stats"]["unclassified"] == 1
    assert loaded["auto_approve"] is False


def test_retired_fixed_sample_and_auto_apply_paths_are_absent():
    source = inspect.getsource(se.run_evolution_cycle)
    assert "STRATEGY_MIN_VALIDATION_N" not in source
    assert '"n_gated"' not in source
    assert '"auto_applied"' not in source


def test_formula_freezes_do_not_promise_a_fixed_n_reactivation():
    root = Path(__file__).resolve().parents[1]
    for rel in (
        "api/intelligence/postmortem_auto_evolve.py",
        "api/quant/alpha/factor_decay.py",
    ):
        source = (root / rel).read_text(encoding="utf-8")
        assert "N 마일스톤" not in source


def test_frozen_policy_returns_before_external_analysis(monkeypatch):
    registry = _registry()
    registry["mutation_policy"]["mode"] = "frozen"
    monkeypatch.setattr(se, "_load_registry", lambda: registry)

    result = se.run_evolution_cycle({})

    assert result["status"] == "formula_frozen"
    assert result["reason"] == "formula mutation is frozen pending explicit PM approval"
