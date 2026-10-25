from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from api.utils import mini_codex_reader as cli
from scripts import mini_document_readers as worker


def test_cli_drops_provider_keys_and_keeps_saved_login_home():
    assert cli.cli_environment({"HOME": "/saved", "PATH": "/bin", "OPENAI_API_KEY": "sentinel",
        "CODEX_API_KEY": "sentinel", "GEMINI_API_KEY": "sentinel"}) == {"HOME": "/saved", "PATH": "/bin"}
    cmd = cli.command(Path("/cli"), Path("/job"), model="gpt-6.1-sol", search=False)
    assert "mcp_servers={}" in cmd and "--search" not in cmd
    assert "read-only" in cmd and "--output-schema" in cmd
    assert all(name in cmd for name in ("shell_tool", "unified_exec", "apps", "hooks", "multi_agent"))
    disabled = [cmd[i + 1] for i, value in enumerate(cmd) if value == "--disable"]
    enabled = [cmd[i + 1] for i, value in enumerate(cmd) if value == "--enable"]
    assert enabled == ["code_mode_host"] and "code_mode_host" not in disabled
    assert all(name in disabled for name in ("shell_tool", "apps", "multi_agent", "plugins"))
    assert 'web_search="disabled"' in cmd


def test_single_invocation_result_reused_and_no_raw_events_saved(tmp_path):
    calls = []
    def executor(args, **kwargs):
        calls.append(args)
        target = Path(args[args.index("--output-last-message") + 1])
        target.write_text(json.dumps({"result_json": '{"facilities": []}'}))
        return SimpleNamespace(returncode=0, stdout='{"type":"turn.completed"}\n', stderr="")
    options = dict(cli=Path("/cli"), model="gpt-6.1-sol", runtime=tmp_path, identity="source-fixed", executor=executor)
    first, receipt = cli.read_json_with_codex("public filing", **options)
    second, reused = cli.read_json_with_codex("public filing", **options)
    assert first == second == {"facilities": []}
    assert len(calls) == 1 and receipt["google_calls"] == 0 and reused["reused"]
    assert not list(tmp_path.rglob("events*"))


def test_uncertain_invocation_is_not_retried(tmp_path):
    calls = []
    def executor(*args, **kwargs):
        calls.append(1)
        return SimpleNamespace(returncode=1, stdout="", stderr="usage limit")
    options = dict(cli=Path("/cli"), model="gpt-6.1-sol", runtime=tmp_path, identity="fixed", executor=executor)
    with pytest.raises(ValueError, match="codex_nonzero"):
        cli.read_json_with_codex("public", **options)
    with pytest.raises(ValueError, match="previous_request_requires_review"):
        cli.read_json_with_codex("public", **options)
    assert len(calls) == 1


@pytest.mark.parametrize("raw", ['{"a":1,"a":2}', '{"a":NaN}'])
def test_strict_result_rejects_ambiguous_json(raw):
    with pytest.raises(ValueError):
        cli.strict_json(raw)


def facts():
    fact = {"text": "Policy rate is 4.00 percent.", "source_date": "2026-10-23",
            "source_url": "https://www.bok.or.kr/official-release",
            "source_quote": "October 23, 2026. The policy rate is 4.00 percent and this is an official statement."}
    return {"kr": [fact], "global": [dict(fact, source_url="https://www.federalreserve.gov/release")]}


def test_macro_requires_actual_primary_quote_and_numeric_support():
    now = datetime(2026, 10, 25, tzinfo=timezone.utc)
    good = facts()
    verified = worker.verify_macro_facts(good, now=now, reader=lambda _: good["kr"][0]["source_quote"])
    result = worker.macro_bundle(verified, model="gpt-6.1-sol", generated_at="2026-10-25T00:00:00+00:00")
    assert result["source_verification"] == "2/2" and result["google_calls"] == 0
    assert result["sources"]["codex_kr"]["source_as_of"] == "2026-10-23"
    with pytest.raises(ValueError, match="quote_not_in"):
        worker.verify_macro_facts(good, now=now, reader=lambda _: "Different text")
    good["kr"][0]["text"] = "Rate is 8.00 percent."
    with pytest.raises(ValueError, match="unsupported_macro_number"):
        worker.verify_macro_facts(good, now=now, reader=lambda _: good["kr"][0]["source_quote"])


def test_macro_date_cannot_be_fabricated_for_an_old_quote():
    old = facts()
    for region in old:
        old[region][0]["source_quote"] = "The policy rate is 4.00 percent and this is an old undated statement."
    with pytest.raises(ValueError, match="macro_date_not_in_same"):
        worker.verify_macro_facts(old, now=datetime(2026, 10, 25, tzinfo=timezone.utc),
                                  reader=lambda _: old["kr"][0]["source_quote"])


@pytest.mark.parametrize("url", ["http://www.bok.or.kr/a", "https://www.bok.or.kr.evil.test/a",
    "https://user:password@www.bok.or.kr/a", "https://127.0.0.1/a", "https://www.bok.or.kr:8443/a"])
def test_macro_source_cannot_escape_official_allowlist(url):
    with pytest.raises(ValueError):
        worker._official_url(url)


def test_macro_retired_cloud_reader_cannot_force_generation(tmp_path, monkeypatch):
    from api.intelligence import macro_synthesis as macro
    monkeypatch.setattr(macro, "OUT_PATH", str(tmp_path / "out.json"))
    monkeypatch.setattr(macro, "CACHE_PATH", str(tmp_path / "cache.json"))
    monkeypatch.setenv("GEMINI_API_KEY", "must-not-be-used")
    assert macro.synthesize_macro(force=True)["status"] == "pending_mini_producer"
    original = {"producer": "mac-mini-codex", "contract": "macro-facts-v1", "source_verification": "2/2",
                "generated_at": "2026-10-23T01:00:00+00:00", "sources": {}}
    (tmp_path / "out.json").write_text(json.dumps(original))
    assert macro.synthesize_macro(force=True)["generated_at"] == original["generated_at"]


def test_owner_dispatch_rechecks_public_source_and_preserves_generation(tmp_path):
    day = datetime.now(worker.KST).strftime("%Y-%m-%d")
    source = f"{day}. The policy rate is 4.00 percent in this official release."
    original = facts()
    for region in original:
        original[region][0].update(source_date=day, source_quote=source)
    verified = worker.verify_macro_facts(original, reader=lambda _: source)
    generated = worker.stamp()
    doc = worker.macro_bundle(verified, model="gpt-6.1-sol", generated_at=generated)
    doc["verified_at"] = generated
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"action": "mini_macro_facts", "client_payload": {"document": doc}}))
    env = {"GITHUB_EVENT_NAME": "repository_dispatch", "GITHUB_ACTOR": "owner", "GITHUB_REPOSITORY_OWNER": "owner"}
    checks = []
    def reader(url):
        checks.append(url)
        return source
    result = worker.receive_dispatch(event, root=tmp_path, reader=reader, environ=env)
    assert result["source_verification"] == "2/2" and len(checks) == 2
    saved = cli.strict_json((tmp_path / "data/macro_synthesis.json").read_bytes())
    assert saved["generated_at"] == generated and saved["google_calls"] == 0
    with pytest.raises(ValueError, match="actor_not_owner"):
        worker.receive_dispatch(event, root=tmp_path, reader=reader, environ=dict(env, GITHUB_ACTOR="other"))
    with pytest.raises(ValueError, match="quote_not_in_primary_source"):
        worker.receive_dispatch(event, root=tmp_path, reader=lambda _: "not the source", environ=env)
    doc["generated_at"] = "2020-01-01T00:00:00Z"
    event.write_text(json.dumps({"action": "mini_macro_facts", "client_payload": {"document": doc}}))
    with pytest.raises(ValueError, match="generation_clock"):
        worker.receive_dispatch(event, root=tmp_path, reader=reader, environ=env)


@pytest.mark.parametrize("ticker,currency", [("005930", "KRW"), ("005930.KS", "KRW"), ("AAPL", "USD")])
def test_manual_filing_identity_routes_correctly_without_advancing_rotation(tmp_path, monkeypatch, ticker, currency):
    def source(row):
        assert row["currency"] == currency
        raise ValueError("source_pending")
    monkeypatch.setattr(worker, "filing_input", source)
    args = SimpleNamespace(ticker=ticker, runtime=tmp_path, max_filings=1)
    result = worker.run_filings(args)
    assert result["results"][0]["reason"] == "source_pending"
    assert not (tmp_path / "filing-rotation.json").exists()


def test_cli_item_error_cannot_be_mistaken_for_completed_result(tmp_path):
    def executor(args, **kwargs):
        target = Path(args[args.index("--output-last-message") + 1])
        target.write_text(json.dumps({"result_json": '{"global": [], "kr": []}'}))
        return SimpleNamespace(returncode=0, stdout='{"type":"item.completed","item":{"type":"error","message":"tool unavailable"}}\n{"type":"turn.completed"}\n', stderr="")
    with pytest.raises(ValueError, match="codex_reader_item_error"):
        cli.read_json_with_codex("public", cli=Path("/cli"), model="gpt-6.1-sol", runtime=tmp_path,
                                identity="failed-tool", search=True, executor=executor)
    receipt = cli.strict_json(next(tmp_path.rglob("receipt.json")).read_bytes())
    assert receipt["status"] == "uncertain" and receipt["diagnostics"] == ["reader_item_error"]
