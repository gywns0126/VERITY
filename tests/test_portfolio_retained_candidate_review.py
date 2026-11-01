"""Offline candidate handoff boundaries; synthetic fixtures are not financial verdicts."""
from copy import deepcopy
import socket
import urllib.request

import pytest

from api.intelligence import portfolio_ai_fallback as ai
from api.intelligence import portfolio_business_judgment as business
from api.intelligence.portfolio_ai_budget_ledger import SupabaseBudgetLedger
from api.intelligence.portfolio_ai_public import project_public_company_judgments
from api.intelligence.portfolio_ai_review import prepare_review_candidates
from api.intelligence.portfolio_judgment_context import (
    CONTEXT_FIELD, enrich_judgment_documents, validate_retained_context,
)
from tests.test_portfolio_business_judgment_product_identity import AS_OF, _case, _candidate
from tests.test_portfolio_judgment_context import fixture


CATALOG = [
    {"market": "KR", "ticker": "111111", "name": "Synthetic Issuer"},
    {"market": "KR", "ticker": "222222", "name": "Synthetic A"},
]


@pytest.fixture(autouse=True)
def offline_only(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("retained candidate tests cannot access network, credentials or a ledger")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    monkeypatch.setattr(ai, "openai_transport", forbidden)
    monkeypatch.setattr(ai, "google_transport", forbidden)
    monkeypatch.setattr(ai.sqlite3, "connect", forbidden)
    monkeypatch.setattr(SupabaseBudgetLedger, "_rpc", forbidden)
    monkeypatch.setattr(SupabaseBudgetLedger, "from_environment", forbidden)


def retained(tail):
    doc, raw = fixture("제품의 기능을 설명합니다. " * 50 + tail)
    rows, counts = enrich_judgment_documents([doc], raw)
    assert counts["enriched"] == 1
    assert tail not in rows[0]["text"]
    assert tail in validate_retained_context(rows[0])
    return rows[0]


def review_packet(doc, quote, role="customer"):
    return {"schema": "local-ai-review-input-v1", "entries": [{
        "document": doc,
        "answer": {"candidates": [{"counterparty_id": "KR:222222", "role": role, "quote": quote}]},
    }]}


def test_tail_candidate_reaches_local_and_public_projection_without_acceptance():
    _, answer = _case(name="Synthetic A")
    proposal = answer["judgments"][0]
    doc = retained(proposal["quote"])
    proposal["source_version"] = ai._digest(doc)
    packet = review_packet(doc, proposal["quote"])
    before = deepcopy((doc, answer, packet))
    prepared = prepare_review_candidates(packet, CATALOG)
    assert prepared["coverage"] == {"input": 1, "accepted": 1, "rejected": 0, "skipped": 0}
    candidate = prepared["candidates"][0]
    assert candidate == _candidate(doc, answer)
    assert candidate["status"] == "ai_candidate"
    assert candidate["verification"] == "unreviewed-model-extraction"
    assert candidate["current_validity"] == "not-inferred"
    local = business.project_company_judgments(
        answer, [doc], prepared["candidates"], [], as_of=AS_OF)
    public = project_public_company_judgments(
        local, prepared["candidates"], source_documents=[doc])
    assert len(local["judgments"]) == len(public["judgments"]) == 1
    for row in [local["judgments"][0], public["judgments"][0]]:
        assert row["record_id"] == candidate["id"]
        assert row["quote"] == proposal["quote"]
        assert row["status"] == "pending"
        assert row["reviewed_on"] is None
        assert row["degree"] == "unrated"
        assert row["impact"]["direction"] == "unknown"
    assert public["judgments"][0]["source_version"] == ai._digest(doc)
    assert (doc, answer, packet) == before


@pytest.mark.parametrize("field,value,reason", [
    ("raw_sha256", "0" * 64, "hash"),
    ("excerpt_sha256", "0" * 64, "hash"),
    ("issuer_name", "Other Issuer", "name"),
    ("receipt_no", "20260312000002", "receipt"),
])
def test_tampered_context_is_fatal_before_review_candidates(field, value, reason):
    quote = "당사는 Synthetic A에 부품을 공급합니다."
    doc = retained(quote)
    doc[CONTEXT_FIELD][field] = value
    before = deepcopy(doc)
    with pytest.raises(ValueError, match="^" + reason + "$"):
        prepare_review_candidates(review_packet(doc, quote), CATALOG)
    assert doc == before


@pytest.mark.parametrize("tail,quote,role,reason", [
    ("종속회사는 Synthetic A에 부품을 공급합니다.",
     "종속회사는 Synthetic A에 부품을 공급합니다.", "customer", "candidate-uncertain-sentence"),
    ("종속회사는 자동차 부품을 제조합니다. Synthetic A에 부품을 공급합니다.",
     "Synthetic A에 부품을 공급합니다.", "customer", "candidate-uncertain-sentence"),
    ("당사는 Synthetic A에 부품을 공급합니다.",
     "당사는 Synthetic A에 부품을 공급합니다.", "supplier", "candidate-direction-uncertain"),
])
def test_tail_keeps_other_entity_and_role_guards(tail, quote, role, reason):
    doc = retained(tail)
    packet = review_packet(doc, quote, role)
    replay = ai.replay_answer(packet["entries"][0]["answer"], doc)
    assert replay["candidates"] == []
    assert replay["rejected"] == [{"index": 0, "reason": reason}]
    prepared = prepare_review_candidates(packet, CATALOG)
    assert prepared["candidates"] == []
    assert prepared["coverage"]["rejected"] == 1


def test_restored_tail_sentence_over_600_is_rejected_without_truncation():
    quote = "당사는 Synthetic A에 부품을 공급합니다."
    sentence = "추가 설명 " * 110 + quote
    assert len(quote) < 600 < len(sentence)
    doc = retained(sentence)
    before = deepcopy(doc)
    replay = ai.replay_answer(review_packet(doc, quote)["entries"][0]["answer"], doc)
    assert replay["candidates"] == []
    assert len(replay["rejected"]) == 1
    assert replay["rejected"][0]["reason"] in {"candidate-evidence", "candidate-uncertain-sentence"}
    assert prepare_review_candidates(review_packet(doc, quote), CATALOG)["candidates"] == []
    assert doc == before


def test_legacy_candidate_revision_and_document_cache_identity_are_unchanged():
    doc, answer = _case(name="Synthetic A")
    expected = _candidate(doc, answer)
    before = deepcopy(doc)
    digest = ai._digest(doc)
    key = ai._digest([ai.PROVIDER, ai.MODEL, ai.REASONING_EFFORT, business.CACHE_VERSION, doc])
    prepared = prepare_review_candidates(review_packet(doc, expected["quote"]), CATALOG)
    assert prepared["candidates"] == [expected]
    assert doc == before and ai._digest(doc) == digest
    assert ai._digest([ai.PROVIDER, ai.MODEL, ai.REASONING_EFFORT, business.CACHE_VERSION, doc]) == key
    assert CONTEXT_FIELD not in doc


@pytest.mark.parametrize("options", [{}, {"with_context": True}, {"with_claims": True}])
def test_tail_context_extraction_still_stops_before_ledger_or_provider(tmp_path, options):
    doc = retained("당사는 Synthetic A에 부품을 공급합니다.")
    ledger = tmp_path / "must-not-exist.sqlite3"
    with pytest.raises(ValueError, match="^retained-context-judgment-only$"):
        ai.run_document(doc, ledger, "synthetic-not-a-credential", enabled=True, **options)
    assert not ledger.exists()
