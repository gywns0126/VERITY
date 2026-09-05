"""2026-09-05 외부 다중 모델 합성 종료 계약."""
from pathlib import Path

from api import config
from api.chat_hybrid import orchestrator, response_synthesizer
from api.intelligence import macro_synthesis, operator_ask


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_runtime_flags_are_fail_closed():
    assert config.CLAUDE_RUNTIME_RETIRED is True
    assert config.ANTHROPIC_API_KEY == ""
    assert config.CLAUDE_TOP_N == 0
    assert config.CLAUDE_IN_QUICK is False
    assert config.CLAUDE_IN_REALTIME is False
    assert config.CLAUDE_MORNING_STRATEGY is False
    assert config.POSTMORTEM_ENABLED is False
    assert config.STRATEGY_EVOLUTION_ENABLED is False


def test_operator_bundle_has_no_server_model_call(monkeypatch):
    facts = {
        "ticker": "AAPL",
        "name": "Apple",
        "sections": [],
        "missing": [],
        "_meta": {"collected_at": "2026-09-05T00:00:00+09:00"},
    }
    monkeypatch.setattr(operator_ask.ticker_facts, "collect", lambda _: facts)
    monkeypatch.setattr(operator_ask.ticker_facts, "render_text", lambda _: "facts")
    out = operator_ask.ask("AAPL", "최근 변화")
    assert out["_meta"] == {
        "contract": "operator-facts-v2",
        "llm_calls": 0,
        "final_reasoner": "codex_session",
        "legacy_chain_retired": True,
    }
    assert "research_questions" in out
    assert "sources" not in out


def test_macro_bundle_has_no_final_judgment_source(monkeypatch, tmp_path):
    monkeypatch.setattr(macro_synthesis, "CACHE_PATH", str(tmp_path / "cache.json"))
    monkeypatch.setattr(macro_synthesis, "_load_portfolio", lambda: {})
    monkeypatch.setattr(macro_synthesis, "_perplexity_fresh", lambda: {"content": "global", "citations": []})
    monkeypatch.setattr(macro_synthesis, "_gemini_facts", lambda grounding, fresh: {"content": "domestic"})
    out = macro_synthesis.synthesize_macro(force=True)
    assert out["contract"] == "macro-facts-v1"
    assert set(out["sources"]) == {"perplexity", "gemini"}
    assert out["disclosure"]["legacy_chain_retired"] is True


def test_hybrid_synthesizer_is_fail_closed():
    events = list(response_synthesizer.stream_response("AAPL"))
    assert events == [{
        "type": "error",
        "error": "legacy_multi_model_synthesis_retired",
        "retired": True,
        "final_reasoner": "codex_session",
    }]
    assert response_synthesizer.get_session_stats()["calls"] == 0


def test_hybrid_orchestrator_direct_call_is_fail_closed():
    events = list(orchestrator.run_hybrid("AAPL", internal=True))
    assert events == [{
        "type": "error",
        "error": "legacy_multi_model_synthesis_retired",
        "retired": True,
        "final_reasoner": "codex_session",
    }]


def test_scheduled_workflows_do_not_inject_retired_provider():
    workflows = sorted((ROOT / ".github" / "workflows").glob("*.y*ml"))
    text = "\n".join(p.read_text(encoding="utf-8") for p in workflows)
    assert "secrets.ANTHROPIC_API_KEY" not in text
    assert not (ROOT / ".github" / "workflows" / "tri_synthesis.yml").exists()


def test_retired_provider_sdk_is_not_a_runtime_dependency():
    requirements = _read("requirements.txt").lower()
    vercel_requirements = _read("vercel-api/requirements.txt").lower()
    assert "anthropic" not in requirements
    assert "anthropic" not in vercel_requirements


def test_operator_surfaces_do_not_offer_legacy_synthesis():
    surface_paths = [
        "operator-web/app/login/page.tsx",
        "operator-web/app/components/Workspace.tsx",
        "operator-web/app/components/StockFactsPanel.tsx",
        "operator-web/app/macro/page.tsx",
        "vercel-api/api/operator_ask.py",
        "vercel-api/api/chat_diag.py",
        "vercel-api/api/system_health.py",
    ]
    text = "\n".join(_read(path) for path in surface_paths).lower()
    assert "tri_synthesis" not in text
    assert "anthropic" not in text
    assert "claude" not in text


def test_retired_artifact_is_not_uploaded_or_served():
    assert "tri_synthesis" not in _read("scripts/upload_operator_data_to_supabase.py")
    assert '"tri_synthesis":' not in _read("vercel-api/api/admin.py")
