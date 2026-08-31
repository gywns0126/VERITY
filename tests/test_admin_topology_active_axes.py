"""Admin topology must reflect issued active fact axes without dangling edges."""

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_admin():
    spec = importlib.util.spec_from_file_location(
        "admin_topology_under_test",
        ROOT / "vercel-api" / "api" / "admin.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _portfolio(weights: dict) -> dict:
    return {
        "recommendations": [
            {"verity_brain": {"fact_score": {"weights_effective": weights}}}
        ]
    }


def test_topology_uses_issued_active_fact_axes() -> None:
    mod = _load_admin()
    weights = {
        "graham_value": 0.28,
        "canslim_growth": 0.19,
        "quant_quality": 0.28,
        "quant_volatility": 0.25,
        "consensus": 0.0,
    }
    topology = mod._build_topology({}, _portfolio(weights))
    fact_nodes = [n for n in topology["nodes"] if n.get("sub_cluster") == "fact_score"]
    assert {n["id"] for n in fact_nodes} == {
        "eng_graham_value",
        "eng_canslim_growth",
        "eng_quant_quality",
        "eng_quant_volatility",
    }
    assert topology["fact_axis_count"] == 4
    assert topology["fact_axis_source"] == "issued.weights_effective"


def test_topology_has_no_dangling_edges() -> None:
    mod = _load_admin()
    topology = mod._build_topology({}, _portfolio({
        "graham_value": 0.28,
        "canslim_growth": 0.19,
        "quant_quality": 0.28,
        "quant_volatility": 0.25,
    }))
    node_ids = {n["id"] for n in topology["nodes"]}
    dangling = [e for e in topology["edges"] if e["from"] not in node_ids or e["to"] not in node_ids]
    assert dangling == []


def test_topology_fallback_is_current_four_axis_contract() -> None:
    mod = _load_admin()
    topology = mod._build_topology({}, {})
    fact_nodes = [n for n in topology["nodes"] if n.get("sub_cluster") == "fact_score"]
    assert len(fact_nodes) == 4
    assert topology["fact_axis_source"] == "constitution_fallback"
