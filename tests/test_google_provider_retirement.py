"""Provider retirement must hold even with credentials or injected clients."""
import ast
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from api.utils.google_provider_policy import GoogleProviderDisabled, genai

ROOT = Path(__file__).resolve().parents[1]


def test_policy_mirror_matches_deployment_and_env_cannot_enable_google(monkeypatch):
    assert (ROOT / "api/utils/google_provider_policy.py").read_bytes() == (ROOT / "vercel-api/google_provider_policy.py").read_bytes()
    monkeypatch.setenv("GEMINI_API_KEY", "dummy-never-sent")
    monkeypatch.setenv("GEMINI_VERDICT_ENABLE", "1")
    monkeypatch.setenv("GEMINI_PRO_ENABLE", "1")
    with pytest.raises(GoogleProviderDisabled):
        genai.Client(api_key="dummy-never-sent", vertexai=True)


@pytest.mark.parametrize("module,name,args", [
    ("api.utils.gemini_cache", "get_or_create_cache", ("model", "system")),
    ("api.utils.gemini_tracked", "tracked_generate", ("model", "input", "fact-extraction")),
    ("api.analyzers.dart_related_party", "_call_once", ("model", "input")),
    ("api.analyzers.dart_litigation", "_call_once", ("model", "input")),
    ("api.analyzers.dart_report_analyzer", "_call_gemini_once", ("model", "input")),
    ("api.analyzers.export_hscode_mapper", "_map_one_stock", (None,)),
])
def test_injected_client_cannot_bypass_retirement(module, name, args):
    import importlib
    client = Mock()
    fn = getattr(importlib.import_module(module), name)
    with pytest.raises(GoogleProviderDisabled):
        fn(client, *args)
    assert client.mock_calls == []


def test_cached_generation_blocks_before_cache_usage_log_or_retry(monkeypatch):
    from api.utils import gemini_cache as cache, gemini_tracked as tracked
    client = Mock()
    create = Mock(side_effect=AssertionError("no cache request"))
    usage = Mock(side_effect=AssertionError("not an attempted paid call"))
    monkeypatch.setattr(cache, "get_or_create_cache", create)
    monkeypatch.setattr(tracked, "log_gemini_usage", usage)
    with pytest.raises(GoogleProviderDisabled):
        cache.generate_with_cache(client, model="model", contents="input",
                                  system_instruction="system", call_type="dart_litigation")
    assert client.mock_calls == []
    create.assert_not_called()
    usage.assert_not_called()


def test_raw_google_http_cannot_receive_even_caller_supplied_key(monkeypatch):
    from api.intelligence import portfolio_ai_fallback as fallback
    request = Mock(side_effect=AssertionError("no request construction"))
    opener = Mock(side_effect=AssertionError("no network"))
    monkeypatch.setattr(fallback.urllib.request, "Request", request)
    monkeypatch.setattr(fallback.urllib.request, "build_opener", opener)
    with pytest.raises(GoogleProviderDisabled):
        fallback.google_transport({}, "dummy-never-sent")
    request.assert_not_called()
    opener.assert_not_called()
    assert fallback.PROVIDER == "openai"


def test_health_reports_deliberate_disabled_without_probe_or_error(monkeypatch):
    from api import health
    request = Mock(side_effect=AssertionError("no Google probe"))
    probe = Mock(return_value={"dart": {"status": "ok"}})
    monkeypatch.setattr(health.requests, "get", request)
    monkeypatch.setattr(health, "_probe_all", probe)
    result = health.check_api_health()
    assert result["gemini"] == {"status": "disabled_by_policy", "detail": "Gemini API 사용 중단 (사용자 정책)",
                                "latency_ms": 0, "attempts": 0}
    assert "gemini" not in [row[0] for row in probe.call_args.args[0]]
    assert {"dart", "fred", "telegram", "kipris", "public_data", "reports_signed_url", "krx_open_api"} <= {row[0] for row in probe.call_args.args[0]}
    assert health._check_gemini()[0] is True
    request.assert_not_called()


def test_deployed_chat_refuses_before_context_and_paid_fallback():
    spec = importlib.util.spec_from_file_location("retired_deployed_chat", ROOT / "vercel-api/api/chat.py")
    chat = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(chat)
    reply = Mock()
    chat.handler.do_POST(SimpleNamespace(_json_response=reply))
    assert reply.call_args.args[0] == 410
    assert reply.call_args.args[1]["status"] == "disabled_by_policy"


def test_deployment_bundle_needs_no_repository_root_or_google_sdk(tmp_path):
    script = r'''import importlib.util, pathlib, sys
root = pathlib.Path(sys.argv[1])
sys.path.insert(0, str(root))
for relative, function, argument in [
    ("api/chat_hybrid/intent_classifier.py", "classify", "question"),
    ("api/chat_hybrid/search/gemini_grounding.py", "search", "question"),
]:
    spec = importlib.util.spec_from_file_location("isolated_" + function, root / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = getattr(module, function)(argument)
    assert result.get("status", result.get("_source")) == "disabled_by_policy"
    if function == "classify":
        assert result["needs_perplexity"] is False and result["needs_gemini_grounding"] is False
from google_provider_policy import genai
try:
    genai.Client(api_key="dummy-never-sent")
except Exception as error:
    assert type(error).__name__ == "GoogleProviderDisabled"
else:
    raise AssertionError("Google constructor enabled")
'''
    subprocess.run([sys.executable, "-I", "-c", script, str(ROOT / "vercel-api")],
                   cwd=tmp_path, env={"PATH": os.environ.get("PATH", ""), "GEMINI_API_KEY": "dummy-never-sent"},
                   check=True, capture_output=True, text=True)


def test_no_live_google_sdk_import_or_raw_google_endpoint_remains():
    """Census guard: a new SDK alias/HTTP path must not silently bypass policy."""
    violations = []
    processed = 0
    for directory in ("api", "scripts", "server", "vercel-api"):
        for path in (ROOT / directory).rglob("*.py"):
            if {"_archive", "node_modules", "__pycache__"} & set(path.parts):
                continue
            source = path.read_text()
            tree = ast.parse(source)
            processed += 1
            for node in ast.walk(tree):
                live_import = (isinstance(node, ast.ImportFrom) and
                               ((node.module == "google" and any(a.name == "genai" for a in node.names)) or
                                (node.module in {"google.genai", "google.generativeai"} and any(a.name != "types" for a in node.names))))
                live_import |= isinstance(node, ast.Import) and any(a.name.startswith(("google.genai", "google.generativeai", "vertexai")) for a in node.names)
                endpoint = isinstance(node, ast.Constant) and isinstance(node.value, str) and any(
                    host in node.value for host in ("generativelanguage.googleapis.com", "aiplatform.googleapis.com"))
                if live_import or endpoint:
                    violations.append((str(path.relative_to(ROOT)), node.lineno))
    assert processed > 0
    assert violations == []


def test_arbitrary_client_generation_helpers_guard_before_generation():
    found = []
    for path in (ROOT / "api").rglob("*.py"):
        tree = ast.parse(path.read_text())
        for function in (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)):
            if "client" not in [a.arg for a in function.args.args]:
                continue
            network = [n for n in ast.walk(function) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                       and n.func.attr in {"generate_content", "generate_content_stream"}]
            if not network:
                continue
            guards = [n for n in function.body if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)
                      and isinstance(n.value.func, ast.Name) and n.value.func.id == "require_google_provider"]
            assert guards and guards[0].lineno < min(n.lineno for n in network), (path, function.name)
            found.append((str(path.relative_to(ROOT)), function.name))
    assert found


def test_disabled_dart_reader_preserves_prior_cache_bytes_and_dates(tmp_path, monkeypatch):
    import json
    from api.analyzers import dart_report_analyzer as reader
    path = tmp_path / "analysis.json"
    prior = {"updated_at": "2026-09-01T09:00:00+09:00", "by_ticker": {
        "000001": {"2026": {"business_health_score": 60, "analyzed_at": "2026-09-01T08:00:00+09:00"}}}}
    raw = json.dumps(prior).encode()
    path.write_bytes(raw)
    monkeypatch.setattr(reader, "CACHE_PATH", str(path))
    monkeypatch.setattr(reader, "GEMINI_API_KEY", "dummy-never-sent")
    analyze = getattr(reader.analyze_all_business_reports, "__wrapped__", reader.analyze_all_business_reports)
    result = analyze({
        "000001": {"bsns_year": "2026"},
        "000002": {"bsns_year": "2026", "business_facilities_raw": {"raw_text": "public source " * 60}},
    }, auto_fetch_missing=False)
    assert result["stats"]["new_analyzed"] == 0
    assert result["stats"]["cache_hit"] == 1
    assert result["results"]["000001"]["analyzed_at"] == "2026-09-01T08:00:00+09:00"
    assert path.read_bytes() == raw
