"""Retained evidence through the existing worker/archive, without provider calls."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from api.intelligence import portfolio_business_judgment as business
from api.intelligence import portfolio_ai_fallback as ai
from api.intelligence import portfolio_ai_result_store as archive
from api.intelligence import portfolio_judgment_context as context
from tests.test_portfolio_business_judgment_product_identity import (
    AS_OF, NEXT_DAY, _case, _saved,
)


def _extended():
    doc, answer = _case()
    economic = "당사 전체의 2025년 APS 공급은 매출에 중요한 기여를 합니다."
    raw = doc["text"] + " " + "제품 설명 " * 130 + "끝입니다. " + economic
    doc["text"] = context._public_excerpt(raw)
    receipt = doc["source_id"].split(":")[-1]
    doc["retained_context_v1"] = {
        "issuer_name": doc["issuer_name"], "receipt_no": receipt,
        "filing_date": doc["as_of"], "text": raw,
        "raw_sha256": hashlib.sha256(raw.encode()).hexdigest(),
        "excerpt_sha256": hashlib.sha256(doc["text"].encode()).hexdigest(),
    }
    proposal = answer["judgments"][0]
    proposal["source_version"] = ai._digest(doc)
    proposal["economic_v2"] = {"materiality": {
        "value": "material", "scope": "company", "scope_quote": "당사 전체",
        "period_quote": "2025년", "quote": economic,
        "mechanism_quote": "매출에 중요한 기여",
    }}
    return doc, answer, economic


def _worker():
    path = Path(__file__).resolve().parents[1] / "scripts/member-map/run-company-judgments.py"
    spec = importlib.util.spec_from_file_location("retained_pipeline_worker", path)
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)
    return worker


def test_retained_context_is_single_prompt_copy_and_immutable_document_digest():
    doc, _, economic = _extended()
    before = deepcopy(doc)
    assert economic not in doc["text"]
    packet = business.prepare_judgment_packet([doc], as_of=AS_OF)
    source = packet["sources"][0]
    assert source["source_version"] == ai._digest(doc)
    assert source["text"] == context.validate_retained_context(doc)
    assert source["excerpt_text"] == doc["text"]
    prompt = business.prepare_judgment_prompt_packet([doc], as_of=AS_OF)
    wire = json.dumps(prompt, ensure_ascii=False)
    assert wire.count(economic) == 1
    assert "text" not in prompt["sources"][0]["retained_context_v1"]
    assert "excerpt_text" not in prompt["sources"][0]
    assert "not-full-filing" in prompt["sources"][0]["context_scope"]
    assert doc == before


def test_tail_economic_quote_survives_private_replay_but_not_automatic_acceptance():
    doc, answer, economic = _extended()
    checked = business.validate_company_judgments(answer, [doc], as_of=AS_OF)
    assert checked["rejected"] == []
    row = checked["judgments"][0]
    assert row["proposal"]["economic_v2"]["materiality"]["quote"] == economic
    assert row["materiality_review_reasons"] == []
    assert row["display"]["importance"] == "unrated"
    saved = _saved(doc, answer)
    restored = archive.replay_result(saved, doc, judgment_as_of=NEXT_DAY)
    assert restored["raw_answer"] == answer
    assert restored["provider_calls"] == 0 and not restored["published"]
    assert restored["assessed_as_of"] == AS_OF
    assert not restored["fresh_assessment"]
    changed = deepcopy(doc)
    changed["retained_context_v1"]["text"] += " "
    with pytest.raises(ValueError):
        archive.replay_result(saved, changed, judgment_as_of=NEXT_DAY)


def test_no_context_legacy_packet_unchanged():
    doc, _ = _case()
    packet = business.prepare_judgment_packet([doc], as_of=AS_OF)
    assert packet["sources"] == [{**doc, "source_version": ai._digest(doc)}]


def test_retained_context_cannot_be_loaded_as_a_different_archive_task():
    doc, answer, _ = _extended()
    saved = _saved(doc, answer)
    saved["result"].update(task_version=ai.VERSION, assessed_as_of=None,
                           status="error", raw_answer=None)
    with pytest.raises(ValueError, match="private-result-context-task"):
        archive.check_envelope(saved["result"], doc)


def test_worker_fixed_context_path_is_bounded_and_symlink_rejected(tmp_path, monkeypatch):
    worker = _worker()
    monkeypatch.setattr(worker, "ROOT", tmp_path)
    assert worker.read_retained_context() is None
    directory = tmp_path / "data"
    directory.mkdir(exist_ok=True)
    path = directory / "dart_business_overview.json"
    path.write_text('{"rows":{}}')
    assert worker.read_retained_context() == {"rows": {}}
    path.write_text('{"rows":{},"rows":{}}')
    with pytest.raises(ValueError):
        worker.read_retained_context()
    path.unlink()
    path.symlink_to(tmp_path / "absent.json")
    with pytest.raises(ValueError, match="retained-context-path"):
        worker.read_retained_context()


def test_plan_context_join_keeps_coverage_and_source_bytes(monkeypatch):
    worker = _worker()
    doc, _, _ = _extended()
    raw_context = doc.pop("retained_context_v1")
    baseline = deepcopy(doc)
    raw = {"rows": {doc["issuer_id"][3:]: {
        "name": raw_context["issuer_name"], "rcept_no": raw_context["receipt_no"],
        "rcept_dt": raw_context["filing_date"].replace("-", ""),
        "text": raw_context["text"],
    }}}
    monkeypatch.setattr(worker.ai, "select_documents", lambda *a, **k: ([doc], {"input": 1, "eligible": 1}))
    selected, coverage = worker.plan({}, as_of=AS_OF, retained_context=raw)
    assert coverage["retained_context"]["enriched"] == 1
    assert coverage["judgment_eligible"] == 1
    assert selected[0]["text"] == baseline["text"]
    assert context.validate_retained_context(selected[0]) == context._public_lines(raw_context["text"])
    assert doc == baseline
