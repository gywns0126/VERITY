"""Self-contained synthetic operating fixtures; no credentials, provider, or deploy."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import re
import socket
import sqlite3
import sys
from types import SimpleNamespace
import urllib.request

import pytest

from api.intelligence import portfolio_business_judgment as business
from api.intelligence.portfolio_ai_budget_ledger import SupabaseBudgetLedger


ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "scripts/member-map/run-company-judgments.py"
WORKFLOW = ROOT / ".github/workflows/member_map_judgments.yml"
AS_OF = "2026-10-11"
SOURCE_ID = "source:dart:20260312000001"
SOURCE_URL = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260312000001"
QUOTE = ("당사는 2025년 Synthetic A에 반도체 부품을 공급하며, "
         "Synthetic A는 당사의 주요 매출처입니다.")


def _doc(text=QUOTE):
    return {"source_id": SOURCE_ID, "issuer_id": "KR:111111", "issuer_name": "Synthetic Issuer",
            "as_of": "2026-03-12", "url": SOURCE_URL, "text": text,
            "counterparties": [{"id": "KR:222222", "name": "Synthetic A"}]}


@pytest.fixture
def worker(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location("operating_judgments_test", WORKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT", tmp_path)

    def forbidden(*args, **kwargs):
        pytest.fail("operating regression must not access a provider or network")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    monkeypatch.setattr(SupabaseBudgetLedger, "_rpc", forbidden)
    monkeypatch.setattr(module.ai, "openai_transport", forbidden)
    monkeypatch.setattr(module.ai, "google_transport", forbidden)
    return module


def _public_bundle():
    text = "Synthetic A는 당사의 주요 고객입니다."
    return {
        "universe_search.json": {"stocks": [
            {"ticker": "111111", "market": "KOSPI", "name": "Synthetic Issuer", "owner_id": "PRIVATE_OWNER_CANARY"},
            {"ticker": "222222", "market": "KOSDAQ", "name": "Synthetic A"},
        ]},
        "kr_business_overview_public.json": {
            "_meta": {"count": 1, "generated_at": "2026-10-01T00:00:00Z"},
            "rows": {"111111": {"name": "Synthetic Issuer", "text": text, "chars": len(text),
                                 "truncated": False, "fiscal_year": "2025", "filed_at": "20260312",
                                 "report": "사업보고서 (2025.12)", "url": SOURCE_URL,
                                 "member_notes": "PRIVATE_NOTE_CANARY"}},
        },
    }


def _cached_answer(doc):
    packet = business.prepare_judgment_packet([doc], as_of="2026-10-10")
    return {"judgments": [{
        "company_id": doc["issuer_id"], "counterparty_id": doc["counterparties"][0]["id"],
        "source_id": doc["source_id"], "source_version": packet["sources"][0]["source_version"],
        "quote": doc["text"], "scope_quote": "Synthetic A는 당사의 주요 매출처", "period_quote": "2025년",
        "degree": {"value": "medium", "basis": "reported_qualitative", "quote": "주요 매출처"},
        "impact": {"direction": "unknown", "channel": "revenue", "condition": None,
                   "quote": "Synthetic A는 당사의 주요 매출처"},
        "counter_evidence_quotes": [], "missing_evidence": [],
        "reason": "원문이 해당 회사를 주요 매출처로 명시합니다.", "review_trigger": "semantic-review-required",
    }], "remaining_count": 0}


def _payload_size(worker, doc):
    packet = worker.prepare_judgment_packet([doc], as_of=AS_OF)
    payload = worker.ai._openai_payload(doc)
    payload.update(instructions=worker.SYSTEM, input=json.dumps(packet, ensure_ascii=False))
    payload["text"]["format"].update(name="company_judgment", schema=worker.SCHEMA)
    return len(json.dumps(payload, ensure_ascii=False).encode())


def test_fixed_public_reader_delegates_only_to_existing_public_worker(worker, monkeypatch):
    bundle, seen = _public_bundle(), []
    reader = SimpleNamespace(read_sources=lambda: bundle)
    loader = SimpleNamespace(exec_module=lambda module: seen.append(module))

    def spec(name, filename):
        assert Path(filename) == WORKER.with_name("enrich-public-relations.py")
        assert name == "member_map_public_worker"
        return SimpleNamespace(loader=loader)

    monkeypatch.setattr(worker.importlib.util, "spec_from_file_location", spec)
    monkeypatch.setattr(worker.importlib.util, "module_from_spec", lambda _: reader)
    assert worker.read_sources() is bundle
    assert seen == [reader]


def test_dry_run_plans_only_closed_public_fields_without_credentials_network_or_state(worker, monkeypatch, capsys):
    class NoCredentials(dict):
        def get(self, key, *default):
            if key in {"OPENAI_API_KEY", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_URL"}:
                pytest.fail("dry-run must not inspect credentials")
            return super().get(key, *default)

        def __getitem__(self, key):
            self.get(key)
            return super().__getitem__(key)

    bundle = _public_bundle()
    hostile = deepcopy(bundle)
    hostile["member-holdings.json"] = {"private_note": "PRIVATE_SOURCE_CANARY"}
    with pytest.raises(ValueError, match="public source set rejected"):
        worker.plan(hostile, as_of=AS_OF)
    before = deepcopy(bundle)
    monkeypatch.setattr(worker, "read_sources", lambda: bundle)
    monkeypatch.setattr(worker.os, "environ", NoCredentials())
    monkeypatch.setattr(worker, "check_operating_environment", lambda _: pytest.fail("dry-run cannot authorize spending"))
    monkeypatch.setattr(worker, "run_batch", lambda *a, **k: pytest.fail("dry-run cannot execute a batch"))
    monkeypatch.setattr(sys, "argv", [str(WORKER), "--limit", "10"])
    docs, coverage = worker.plan(bundle, as_of=AS_OF)
    assert docs and coverage["judgment_eligible"] == 1
    assert set(docs[0]) <= {"source_id", "issuer_id", "issuer_name", "as_of", "url", "text", "counterparties", "resolved_relations"}
    assert "PRIVATE_" not in json.dumps(docs)
    worker.main()
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "dry-run" and result["paid_attempts"] == 0
    assert result["maximum_reserved_micro_usd"] == 10 * worker.ai.RESERVE_MICRO_USD
    assert not (worker.ROOT / ".cache").exists()
    assert bundle == before


def test_plan_checks_the_complete_utf8_payload_cap(worker, monkeypatch):
    normal = _doc()
    oversized = _doc(normal["text"] + " " + "추가원문사업문맥" * 61 + ".")
    oversized["issuer_name"] = "합성발행기업" * 24
    assert len(oversized["text"]) <= 600
    assert worker.ai.MAX_PROMPT_BYTES == 8000
    assert _payload_size(worker, normal) <= 8000 < _payload_size(worker, oversized)
    monkeypatch.setattr(worker.ai, "select_documents", lambda _, **kw: ([normal, oversized], {"input": 2, "eligible": 2}))
    docs, coverage = worker.plan({}, as_of=AS_OF)
    assert docs == [normal] and coverage["input_too_large"] == 1
    exact = _payload_size(worker, normal)
    monkeypatch.setattr(worker.ai, "MAX_PROMPT_BYTES", exact)
    assert worker.plan({}, as_of=AS_OF)[0] == [normal]
    monkeypatch.setattr(worker.ai, "MAX_PROMPT_BYTES", exact - 1)
    assert worker.plan({}, as_of=AS_OF)[0] == []


def test_probe_window_is_bounded_deterministic_and_excludes_future_sources(worker, monkeypatch):
    docs = []
    for index in range(65):
        doc = _doc()
        receipt = f"20260312{index:06d}"
        doc.update(source_id="source:dart:" + receipt,
                   url="https://dart.fss.or.kr/dsaf001/main.do?rcpNo=" + receipt)
        docs.append(doc)
    future = _doc()
    future["as_of"] = "2099-01-01"

    def select(_, *, include_claims):
        assert include_claims is True
        return [future, *docs], {"input": 66, "eligible": 66}

    monkeypatch.setattr(worker.ai, "select_documents", select)
    first, coverage = worker.plan({}, as_of=AS_OF)
    assert first == worker.plan({}, as_of=AS_OF)[0]
    assert worker.MAX_PROBES == len(first) == len({d["source_id"] for d in first}) == 40
    assert coverage["judgment_eligible"] == 65 and coverage["future_source"] == 1
    assert coverage["selected_probe_window"] == 40
    assert future not in first


@pytest.mark.parametrize("limit", [0, 11, True, 1.0])
def test_invalid_paid_limit_rejects_before_runner(worker, limit, tmp_path):
    with pytest.raises(ValueError, match="operating-limit"):
        worker.run_batch([_doc()], tmp_path / "ledger", "synthetic-key", object(),
                         as_of=AS_OF, limit=limit, runner=lambda *a, **k: pytest.fail("invalid limit cannot run"))


def test_cached_probes_do_not_consume_limit_and_one_shared_budget_is_forwarded(worker, tmp_path):
    budget, calls = object(), []

    def runner(doc, ledger, key, **kwargs):
        assert ledger == tmp_path / "ledger" and key == "synthetic-key"
        assert kwargs == {"enabled": True, "judgment_as_of": AS_OF, "budget_ledger": budget}
        calls.append(doc)
        return {"status": "cached" if len(calls) <= 29 else "ok", "judgments": []}

    result = worker.run_batch([_doc() for _ in range(40)], tmp_path / "ledger", "synthetic-key", budget,
                              as_of=AS_OF, limit=10, runner=runner)
    assert result["paid_attempts"] == 10 and result["processed_documents"] == len(calls) == 39
    assert result["results"] == {"cached": 29, "ok": 10}
    assert result["accepted_judgments"] == result["confirmed_relationships"] == 0
    assert result["published"] is False


def test_actual_cached_answer_preserves_old_assessment_and_spends_nothing(worker, tmp_path):
    doc, ledger = _doc(), tmp_path / "ledger.sqlite3"
    answer = _cached_answer(doc)
    saved = {"status": "ok", "assessed_as_of": "2026-10-10", "raw_answer": answer}
    key = worker.ai._digest([worker.ai.PROVIDER, worker.ai.MODEL, worker.ai.REASONING_EFFORT, business.VERSION, doc])
    with sqlite3.connect(ledger) as db:
        db.execute("CREATE TABLE calls (key TEXT PRIMARY KEY, day TEXT NOT NULL, reserved INTEGER NOT NULL, result TEXT)")
        db.execute("INSERT INTO calls VALUES (?,?,?,?)", (key, "2026-10-10", 123, json.dumps(saved)))
    before, seen = ledger.read_bytes(), []

    def runner(*args, **kwargs):
        result = worker.ai.run_document(*args, **kwargs)
        seen.append(result)
        return result

    summary = worker.run_batch([doc], ledger, "synthetic-key", object(), as_of=AS_OF, limit=1, runner=runner)
    assert summary["results"] == {"cached": 1} and summary["paid_attempts"] == 0
    assert seen[0]["assessed_as_of"] == "2026-10-10" and seen[0]["fresh_assessment"] is False
    assert seen[0]["raw_answer"] == answer
    assert seen[0]["judgments"][0]["display"] == {"degree": "unrated", "impact": "unknown", "importance": "unrated"}
    assert ledger.read_bytes() == before


@pytest.mark.parametrize("status,settlement,stop,paid", [
    ("result-store-unavailable", None, "result-store-unavailable", 0),
    ("budget-ledger-unavailable", None, "budget-ledger-unavailable", 0),
    ("missing-key", None, "missing-key", 0),
    ("disabled", None, "disabled", 0),
    ("budget-exhausted", None, "budget-exhausted", 0),
    ("error", None, "error", 1),
    ("ok", "pending-reservation-retained", "budget-settlement-pending", 1),
    ("cached", "pending-reservation-retained", "budget-settlement-pending", 0),
])
def test_failures_stop_before_the_next_document(worker, tmp_path, status, settlement, stop, paid):
    calls = []

    def runner(*args, **kwargs):
        calls.append(args[0])
        return {"status": status, "budget_settlement": settlement, "judgments": []}

    result = worker.run_batch([_doc(), _doc()], tmp_path / "ledger", "synthetic-key", object(),
                              as_of=AS_OF, limit=10, runner=runner)
    assert len(calls) == result["processed_documents"] == 1
    assert result["status"] == "stopped" and result["stop_reason"] == stop
    assert result["paid_attempts"] == paid and result["published"] is False


@pytest.mark.parametrize("status,settlement,exit_code", [
    ("result-store-unavailable", None, 2),
    ("budget-exhausted", None, 3),
    ("ok", "pending-reservation-retained", 2),
])
def test_execute_cli_reports_nonzero_stop_and_forwards_one_budget(worker, monkeypatch, capsys, status, settlement, exit_code):
    budget, calls = object(), []
    monkeypatch.setattr(worker, "read_sources", lambda: {})
    monkeypatch.setattr(worker, "plan", lambda *a, **k: ([_doc(), _doc()], {"selected_probe_window": 2}))
    monkeypatch.setattr(worker, "check_operating_environment", lambda _: budget)
    monkeypatch.setattr(worker.os, "environ", {"OPENAI_API_KEY": "synthetic-key"})
    monkeypatch.setattr(sys, "argv", [str(WORKER), "--execute", "--limit", "10"])

    def runner(doc, ledger, key, **kwargs):
        assert kwargs["budget_ledger"] is budget and key == "synthetic-key"
        assert ledger == worker.ROOT / ".cache/portfolio-ai/operating-ledger.sqlite3"
        calls.append(doc)
        return {"status": status, "budget_settlement": settlement, "judgments": []}

    monkeypatch.setattr(worker.ai, "run_document", runner)
    with pytest.raises(SystemExit) as stopped:
        worker.main()
    assert stopped.value.code == exit_code and len(calls) == 1
    summary = json.loads(capsys.readouterr().out)
    assert summary["status"] == "stopped" and summary["published"] is False
    assert summary["accepted_judgments"] == summary["confirmed_relationships"] == 0
    assert "synthetic-key" not in json.dumps(summary)


def _trusted_env():
    return {"PORTFOLIO_AI_OPERATING_ENABLED": "1", "PORTFOLIO_AI_LEDGER": "supabase",
            "OPENAI_API_KEY": "synthetic-key", "SUPABASE_URL": "https://synthetic.invalid",
            "SUPABASE_SERVICE_ROLE_KEY": "synthetic-service-key", "CI": "true",
            "GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": "gywns0126/VERITY",
            "GITHUB_REF": "refs/heads/main", "GITHUB_EVENT_NAME": "workflow_dispatch"}


@pytest.mark.parametrize("patch", [
    {"PORTFOLIO_AI_OPERATING_ENABLED": "0"}, {"PORTFOLIO_AI_LEDGER": "sqlite"},
    {"GITHUB_ACTIONS": "false"}, {"GITHUB_REPOSITORY": "fork/VERITY"},
    {"GITHUB_REF": "refs/heads/feature"}, {"GITHUB_REF": "refs/pull/1/merge"},
    {"GITHUB_EVENT_NAME": "pull_request"}, {"GITHUB_EVENT_NAME": "push"},
    {"VERCEL": "false"}, {"VERCEL_ENV": "preview"}, {"OPENAI_API_KEY": ""},
])
def test_untrusted_or_serverless_hosts_reject_before_budget_construction(worker, monkeypatch, patch):
    env = {**_trusted_env(), **patch}
    monkeypatch.setattr(worker, "SupabaseBudgetLedger", lambda *a: pytest.fail("rejected host cannot construct budget client"))
    with pytest.raises(ValueError, match="^operating-(consent-or-host|trusted-workflow-required|key-missing)$"):
        worker.check_operating_environment(env)


@pytest.mark.parametrize("event", ["workflow_dispatch", "workflow_run"])
def test_trusted_main_host_constructs_the_shared_budget_without_rpc(worker, monkeypatch, event):
    budget, seen = object(), []
    monkeypatch.setattr(worker, "SupabaseBudgetLedger", lambda *args: (seen.append(args), budget)[1])
    env = _trusted_env()
    env["GITHUB_EVENT_NAME"] = event
    assert worker.check_operating_environment(env) is budget
    assert seen == [("https://synthetic.invalid", "synthetic-service-key")]


def test_workflow_is_read_only_main_pinned_and_only_accepts_trusted_successful_upstream():
    source = WORKFLOW.read_text()
    assert re.search(r"(?m)^permissions:\n  contents: read\n", source)
    assert source.count("permissions:") == 1 and not re.search(r"(?m)^\s+[\w-]+: write\s*$", source)
    assert "workflows: ['kr-company-facts-backfill']" in source
    assert "types: [completed]" in source and "branches: [main]" in source
    assert "github.event.workflow_run.conclusion == 'success'" in source
    assert "github.event.workflow_run.head_branch == 'main'" in source
    assert "github.event.workflow_run.head_repository.full_name == github.repository" in source
    assert "ref: main" in source and "persist-credentials: false" in source
    assert "cancel-in-progress: false" in source
    assert "schedule:" not in source and "pull_request:" not in source
    assert "actions/upload-artifact" not in source and "git push" not in source
    plan, execute = source.split("      - name: Run bounded private judgment proposals", 1)
    assert "secrets." not in plan and "--execute" not in plan
    assert "PORTFOLIO_AI_OPERATING_ENABLED: '1'" in execute and "PORTFOLIO_AI_LEDGER: supabase" in execute
    assert "--execute --limit" in execute and "inputs.limit || '3'" in execute
