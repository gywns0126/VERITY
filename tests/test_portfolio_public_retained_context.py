"""Synthetic retained-evidence export boundaries; no member or provider inputs."""
import builtins
from copy import deepcopy
import hashlib
import importlib
from pathlib import Path
import socket
import urllib.request

import pytest

from api.intelligence import portfolio_ai_public as public
from api.intelligence import portfolio_ai_fallback as fallback
from api.intelligence import portfolio_business_judgment as business
from api.intelligence.portfolio_judgment_context import _public_excerpt
from tests.test_portfolio_business_judgment_product_identity import (
    AS_OF, _case, _candidate, _review,
)


@pytest.fixture(autouse=True)
def _isolate_data_dir(monkeypatch):
    # Replace the unrelated account/trading fixture with a pure offline guard.
    def denied(*args, **kwargs):
        raise AssertionError("retained context tests cannot call network/providers")
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(urllib.request, "urlopen", denied)
    monkeypatch.setattr(fallback, "run_document", denied)
    monkeypatch.setattr(fallback, "openai_transport", denied)
    monkeypatch.setattr(fallback, "google_transport", denied)


def _sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def _retained_case(*, review=True, materiality_review=True):
    doc, answer = _case()
    materiality = "당사 전체의 2025년 APS 공급은 매출에 중요한 기여를 합니다."
    counter = "당사는 2025년 APS 공급의 원재료 비용 증가에 따른 부담도 보고했습니다."
    raw = doc["text"] + " " + " ".join(
        f"당사는 제{i} 제품의 제조 공정과 보관 방법을 설명합니다." for i in range(20)
    ) + " " + materiality + " " + counter
    assert 600 < len(raw) <= 2500
    doc["text"] = _public_excerpt(raw)
    assert materiality not in doc["text"] and counter not in doc["text"]
    doc["retained_context_v1"] = {
        "issuer_name": doc["issuer_name"], "receipt_no": doc["source_id"].split(":")[-1],
        "filing_date": doc["as_of"], "text": raw,
        "raw_sha256": _sha(raw), "excerpt_sha256": _sha(doc["text"]),
    }
    proposal = answer["judgments"][0]
    proposal["source_version"] = public._digest(doc)
    proposal["counter_evidence_quotes"] = [counter]
    proposal["economic_v2"] = {"materiality": {
        "value": "material", "scope": "company", "scope_quote": "당사 전체",
        "period_quote": "2025년", "quote": materiality,
        "mechanism_quote": "매출에 중요한 기여",
    }}
    result = business.validate_company_judgments(answer, [doc], as_of=AS_OF)
    assert result["rejected"] == []
    receipt = _review(result["judgments"][0])
    if materiality_review:
        receipt["materiality_review"] = {
            "decision": "accept", "reviewed_on": AS_OF, "reason": "합성 중요도 독립 검수입니다.",
            "checks": {key: True for key in business._MATERIALITY_CHECKS},
        }
    candidate = _candidate(doc, answer)
    local = business.project_company_judgments(
        answer, [doc], [candidate], [receipt] if review else [], as_of=AS_OF)
    return doc, candidate, local


def _export(doc, candidate, local):
    return public.project_public_company_judgments(local, [candidate], source_documents=[doc])


def _assert_withdrawn(doc, candidate, local):
    try:
        result = _export(doc, candidate, local)
    except ValueError as error:
        assert str(error) == "invalid-public-company-judgments"
    else:
        assert result["judgments"] == []


def test_retained_materiality_and_counter_tail_export_with_immutable_full_doc_binding():
    doc, candidate, local = _retained_case()
    before = deepcopy((doc, candidate, local))
    source = public._judgment_sources([doc])[doc["source_id"]]
    assert source == business.prepare_judgment_packet([doc], as_of=AS_OF)["sources"][0]
    assert source["excerpt_text"] == doc["text"] and source["source_version"] == public._digest(doc)
    wire = _export(doc, candidate, local)
    assert len(wire["judgments"]) == 1
    row = wire["judgments"][0]
    assert row["status"] == "accepted" and row["impact"]["direction"] == "unknown"
    economic = row["economic_v2"]
    assert economic["materiality"]["value"] == "material"
    assert row["evidence_context_v1"] == {
        "source_version": public._digest(doc),
        "raw_sha256": doc["retained_context_v1"]["raw_sha256"],
        "quotes": [economic["materiality"]["quote"], *economic["counter_evidence_quotes"]],
    }
    assert "text" not in row["evidence_context_v1"]
    assert _export(doc, candidate, wire) == wire
    assert public.validate_public_company_judgments(wire, [candidate]) == wire
    assert (doc, candidate, local) == before


@pytest.mark.parametrize("field,value", [
    ("text", "변경된 원문입니다."), ("raw_sha256", "a" * 64),
    ("excerpt_sha256", "b" * 64), ("filing_date", "2026-03-13"),
    ("receipt_no", "20260312000002"), ("issuer_name", "Different Issuer"),
])
def test_tampered_retained_proof_cannot_export(field, value):
    doc, candidate, local = _retained_case()
    doc["retained_context_v1"][field] = value
    _assert_withdrawn(doc, candidate, local)


@pytest.mark.parametrize("field,value", [
    ("issuer_id", "KR:333333"), ("issuer_name", "Different Issuer"),
    ("source_id", "source:dart:20260312000002"), ("as_of", "2026-03-13"),
    ("url", "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260312000002"),
    ("text", "당사는 다른 사업을 설명합니다."),
])
def test_changed_original_document_cannot_reuse_receipt(field, value):
    doc, candidate, local = _retained_case()
    doc[field] = value
    _assert_withdrawn(doc, candidate, local)


def test_valid_new_tail_hash_still_withdraws_old_source_revision():
    doc, candidate, local = _retained_case()
    wire = _export(doc, candidate, local)
    context = doc["retained_context_v1"]
    context["text"] += " 당사는 후속 설명을 추가했습니다."
    context["raw_sha256"] = _sha(context["text"])
    assert public._judgment_sources([doc])[doc["source_id"]]["source_version"] != wire["judgments"][0]["source_version"]
    _assert_withdrawn(doc, candidate, wire)


@pytest.mark.parametrize("change", ["extra-key", "raw-hash", "source-version", "duplicate",
                                    "empty", "too-many", "too-long", "unfinished", "fragment"])
def test_context_closed_shape_and_whole_sentence_export_boundary(change):
    doc, candidate, local = _retained_case()
    row = local["judgments"][0]
    context = row["evidence_context_v1"]
    if change == "extra-key":
        context["reviewed"] = True
    elif change == "raw-hash":
        context["raw_sha256"] = "a" * 64
    elif change == "source-version":
        context["source_version"] = "b" * 64
    elif change == "duplicate":
        context["quotes"].append(context["quotes"][0])
    elif change == "empty":
        context["quotes"] = []
    elif change == "too-many":
        context["quotes"] = [f"당사는 항목 {i}을 보고합니다." for i in range(6)]
    elif change == "too-long":
        context["quotes"][0] = "가" * 600 + "."
    else:
        quote = context["quotes"][0]
        replacement = quote[:-1] if change == "unfinished" else quote[quote.index("2025년"):]
        context["quotes"][0] = replacement
        row["economic_v2"]["materiality"]["quote"] = replacement
    _assert_withdrawn(doc, candidate, local)


def test_repeated_retained_sentence_is_not_unique_source_evidence():
    doc, candidate, local = _retained_case()
    row = local["judgments"][0]
    retained = doc["retained_context_v1"]
    retained["text"] += " " + row["evidence_context_v1"]["quotes"][0]
    retained["raw_sha256"] = _sha(retained["text"])
    row["source_version"] = public._digest(doc)
    row["evidence_context_v1"].update(source_version=row["source_version"], raw_sha256=retained["raw_sha256"])
    _assert_withdrawn(doc, candidate, local)


@pytest.mark.parametrize("target", ["primary", "impact", "materiality-fragment", "counter-fragment", "period"])
def test_tail_support_cannot_expand_other_axes_or_drop_sentence_context(target):
    doc, candidate, local = _retained_case()
    row = local["judgments"][0]
    economic = row["economic_v2"]
    quote = row["evidence_context_v1"]["quotes"][0]
    if target == "primary":
        row["quote"] = quote
    elif target == "impact":
        economic["impact_quote"] = quote
    elif target == "materiality-fragment":
        economic["materiality"]["quote"] = quote[quote.index("2025년"):]
    elif target == "counter-fragment":
        economic["counter_evidence_quotes"] = ["원재료 비용 증가에 따른 부담도 보고했습니다."]
    else:
        row["period_context_v2"] = {"source_version": public._digest(doc), "quote": quote}
    _assert_withdrawn(doc, candidate, local)


@pytest.mark.parametrize("review,materiality_review", [(False, False), (True, False)])
def test_extra_evidence_cannot_grant_an_unreviewed_grade(review, materiality_review):
    doc, candidate, local = _retained_case(review=review, materiality_review=materiality_review)
    row = _export(doc, candidate, local)["judgments"][0]
    assert row["status"] == ("accepted" if review else "pending")
    assert row["economic_v2"]["materiality"]["value"] == "unrated"
    assert row["impact"]["direction"] == "unknown"


def test_legacy_without_extension_keeps_existing_shape_and_roundtrip():
    doc, answer = _case()
    candidate = _candidate(doc, answer)
    local = business.project_company_judgments(answer, [doc], [candidate], [], as_of=AS_OF)
    assert public._judgment_sources([doc])[doc["source_id"]] == {**doc, "source_version": public._digest(doc)}
    wire = _export(doc, candidate, local)
    assert len(wire["judgments"]) == 1 and "evidence_context_v1" not in wire["judgments"][0]
    assert public.validate_public_company_judgments(wire, [candidate]) == wire


def test_prepared_wire_and_deployed_mirror_need_no_offline_imports(monkeypatch):
    doc, candidate, local = _retained_case()
    wire = _export(doc, candidate, local)
    root = Path(__file__).resolve().parents[1]
    assert (root / "api/intelligence/portfolio_ai_public.py").read_bytes() == (
        root / "vercel-api/api/portfolio_core/portfolio_ai_public.py").read_bytes()
    monkeypatch.syspath_prepend(str(root / "vercel-api/api"))
    original_import = builtins.__import__
    def guarded(name, *args, **kwargs):
        if any(module in name for module in ("portfolio_judgment_context", "portfolio_business_judgment",
                                             "portfolio_ai_fallback", "portfolio_ai_result_store")):
            raise AssertionError("prepared public wire imported offline code: " + name)
        return original_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", guarded)
    deployed = importlib.import_module("portfolio_core.portfolio_ai_public")
    for module in (public, deployed):
        assert module.validate_public_company_judgments(wire, [candidate]) == wire
        payload = {"schema": "local-ai-review-v1", "candidates": [candidate],
                   "coverage": {"input": 1, "accepted": 1, "rejected": 0, "skipped": 0},
                   "company_judgments": wire}
        catalog = [{"market": "KR", "ticker": identifier[3:], "name": name} for identifier, name in (
            (candidate["issuer_id"], candidate["issuer_name"]),
            (candidate["counterparty_id"], candidate["counterparty_name"]))]
        projected = module.project_public_ai_review(payload, catalog, [candidate["issuer_id"]])
        assert projected["candidates"] == [candidate]
        assert projected["candidates"][0]["status"] == "ai_candidate"
        row = projected["company_judgments"]["judgments"][0]
        assert row["impact"]["direction"] == "unknown" and "core_selection" not in row
        assert module.project_public_ai_review(payload, catalog, [candidate["counterparty_id"]])[
            "company_judgments"]["judgments"] == []
        changed = deepcopy(wire)
        changed["judgments"][0]["evidence_context_v1"]["raw_sha256"] = "f" * 64
        with pytest.raises(ValueError, match="invalid-public-company-judgments"):
            module.validate_public_company_judgments(changed, [candidate])


@pytest.mark.parametrize("tail_field", ["current_quote", "period_quote", "change_quote"])
def test_retained_tail_cannot_supply_core_selection_proof(tail_field):
    # Isolate the existing core-proof gate with an otherwise passing proof.
    # No inferred proof is inserted into a producer artifact.
    doc, candidate, local = _retained_case()
    row = _export(doc, candidate, local)["judgments"][0]
    current = "당사 전체는 2026-03-12 현재 APS에 부품을 공급하고 있습니다."
    period = "당사 전체의 APS 공급은 2026-01-01부터 2026-12-31까지 유효합니다."
    change = "당사 전체의 APS 공급 매출은 2026-03-12 증가했습니다."
    previous_quote = "당사 전체의 APS 공급 매출은 이전 보고기간 수준입니다."
    row["economic_v2"]["materiality"]["quote"] = change
    previous_id = "source:dart:20260311000001"
    previous_url = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260311000001"
    proof = {"checked_on": "2026-03-12", "effective_start": "2026-01-01",
             "effective_end": "2026-12-31", "current_quote": current, "period_quote": period,
             "change_quote": change, "reason": "합성 별도 검수입니다.",
             "candidate_revision": candidate["revision"],
             "previous": {"record_id": candidate["id"], "source_id": previous_id,
                          "source_url": previous_url, "published_on": "2026-03-11",
                          "source_version": "a" * 64, "review_revision": "b" * 64,
                          "quote": previous_quote}}
    sources = {row["source_id"]: {"text": " ".join((current, period, change))},
               previous_id: {"source_version": "a" * 64, "issuer_id": row["company_id"],
                             "url": previous_url, "as_of": "2026-03-11", "text": previous_quote,
                             "counterparties": [{"id": row["counterparty_id"]}]}}
    assert public._public_core_selection(proof, row, candidate, sources)["change_quote"] == change
    sources[row["source_id"]]["excerpt_text"] = " ".join(
        quote for quote in (current, period, change) if quote != proof[tail_field])
    with pytest.raises(ValueError, match="invalid-public-ai-review"):
        public._public_core_selection(proof, row, candidate, sources)
