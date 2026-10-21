"""Synthetic identity/recovery boundaries; not live-company quality evidence."""
from copy import deepcopy
import json
import socket
import sqlite3
import urllib.request

import pytest

from api.intelligence import portfolio_ai_fallback as ai
from api.intelligence import portfolio_ai_result_store as archive
from api.intelligence import portfolio_business_judgment as business
from api.intelligence.portfolio_ai_budget_ledger import SupabaseBudgetLedger


AS_OF = "2026-10-10"
NEXT_DAY = "2026-10-11"
CODE = "counterparty-product-acronym"
SOURCE_ID = "source:dart:20260312000001"
SOURCE_URL = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260312000001"


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("product-identity fixtures cannot use providers, network or credentials")
    monkeypatch.setattr(ai, "openai_transport", forbidden)
    monkeypatch.setattr(ai, "google_transport", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    monkeypatch.setattr(SupabaseBudgetLedger, "_rpc", forbidden)
    monkeypatch.setattr(SupabaseBudgetLedger, "from_environment", forbidden)


def _case(definition=None, *, name="APS", inline=False):
    subject = definition if inline else name
    quote = f"당사는 2025년 {subject}에 부품을 공급하며, {name}는 당사의 주요 매출처입니다."
    prefix = f"당사는 2025년 {definition} 제품을 제조합니다. " if definition and not inline else ""
    doc = {"source_id": SOURCE_ID, "issuer_id": "KR:111111", "issuer_name": "Synthetic Issuer",
           "as_of": "2026-03-12", "url": SOURCE_URL, "text": prefix + quote,
           "counterparties": [{"id": "KR:222222", "name": name}]}
    row = {"company_id": doc["issuer_id"], "counterparty_id": "KR:222222",
           "source_id": SOURCE_ID, "source_version": business.prepare_judgment_packet(
               [doc], as_of=AS_OF)["sources"][0]["source_version"],
           "quote": quote, "scope_quote": f"{name}는 당사의 주요 매출처", "period_quote": "2025년",
           "degree": {"value": "medium", "basis": "reported_qualitative", "quote": "주요 매출처"},
           "impact": {"direction": "unknown", "channel": "unknown", "condition": None, "quote": None},
           "counter_evidence_quotes": [], "missing_evidence": [],
           "reason": "합성 원문의 발행회사 범위와 거래처 표기를 검토합니다.",
           "review_trigger": "기업과 제품 식별을 별도 검수합니다."}
    return doc, {"judgments": [row], "remaining_count": 0}


def _validate(doc, answer):
    result = business.validate_company_judgments(answer, [doc], as_of=AS_OF)
    assert result["rejected"] == [] and len(result["judgments"]) == 1
    return result


def _flags(result):
    return [finding for finding in result["quality_review"]["findings"] if finding["code"] == CODE]


def _candidate(doc, answer):
    row = answer["judgments"][0]
    candidate = {"issuer_id": doc["issuer_id"], "counterparty_id": row["counterparty_id"],
                 "role": "customer", "quote": row["quote"], "source_id": SOURCE_ID,
                 "url": SOURCE_URL, "as_of": doc["as_of"], "status": "ai_candidate",
                 "verification": "unreviewed-model-extraction", "issuer_name": doc["issuer_name"],
                 "counterparty_name": doc["counterparties"][0]["name"],
                 "evidence_scope": "unspecified", "current_validity": "not-inferred"}
    candidate["id"] = "automatic:ai:" + ai._digest([
        SOURCE_ID, candidate["issuer_id"], candidate["counterparty_id"], "customer"])[:24]
    candidate["revision"] = ai._digest(candidate)
    return candidate


def _review(literal):
    return {"judgment_id": literal["id"], "judgment_revision": literal["revision"],
            "decision": "accept", "reviewed_on": AS_OF, "reason": "합성 독립 검수 영수증입니다.",
            "checks": {key: True for key in ("company_scope", "period", "degree_support",
                                            "impact_mechanism", "counter_evidence", "source_context")}}


@pytest.mark.parametrize("name,expansion", [
    ("APS", "Accelrator Pedal Sensor"), ("APS", "Brake Pedal Switch"),
    ("APS", "Dynamic Random Access Memory"), ("APS", "Vehicle Control Module"),
    ("APS", "Head Up Display"), ("AB", "Pedal Sensor"), ("ABCDEFGH", "Pedal Sensor"),
])
def test_source_whole_product_definition_flags_selected_named_quote(name, expansion):
    definition = f"{name} ({expansion})"
    doc, answer = _case(definition, name=name)
    result = _validate(doc, answer)
    assert definition not in answer["judgments"][0]["quote"]
    assert _flags(result) == [{"judgment_id": result["judgments"][0]["id"],
                               "axis": "source_context", "code": CODE,
                               "evidence_quotes": [doc["text"].split(". ", 1)[0] + "."]}]


def test_inline_product_definition_is_also_flagged():
    doc, answer = _case("APS(Accelrator Pedal Sensor)", inline=True)
    assert _flags(_validate(doc, answer))[0]["evidence_quotes"] == [answer["judgments"][0]["quote"]]


@pytest.mark.parametrize("name,definition", [
    ("APS", None), ("APS", "APS (APS Inc.)"), ("APS", "APS (Applied Product Systems)"),
    ("APS", "XAPS (Accelrator Pedal Sensor)"), ("APS", "BPS (Brake Pedal Sensor)"),
    ("A", "A (Pedal Sensor)"), ("ABCDEFGHI", "ABCDEFGHI (Pedal Sensor)"),
    ("aps", "aps (Pedal Sensor)"),
])
def test_company_expansions_other_products_and_out_of_range_names_are_not_flagged(name, definition):
    doc, answer = _case(definition, name=name)
    assert _flags(_validate(doc, answer)) == []


def test_product_definition_needs_target_in_the_selected_quote():
    doc, answer = _case("APS (Accelrator Pedal Sensor)")
    literal = deepcopy(_validate(doc, answer)["judgments"][0])
    literal["proposal"]["quote"] = "당사는 2025년 부품을 제조합니다."
    # Isolate this quality predicate; do not present the altered row as validated.
    source = business.prepare_judgment_packet([doc], as_of=AS_OF)["sources"][0]
    assert not any(finding["code"] == CODE for finding in business._quality_findings(literal, source))


def _saved(doc, answer):
    raw = {"status": "ok", "provider": ai.PROVIDER, "model": ai.MODEL,
           "reasoning_effort": ai.REASONING_EFFORT, "assessed_as_of": AS_OF,
           "usage": {"input_tokens": 100, "output_tokens": 30,
                     "thinking_tokens": 0, "cached_input_tokens": 0}, "raw_answer": answer}
    key = ai._digest([ai.PROVIDER, ai.MODEL, ai.REASONING_EFFORT, business.VERSION, doc])
    return {"status": "stored", "key": key, "document": deepcopy(doc),
            "result": archive.pack_result(raw, doc, business.VERSION, 25)}


class ReadOnlyBudget:
    def __init__(self, saved):
        self.saved, self.get_calls, self.reserve_calls, self.settle_calls = saved, 0, 0, 0

    def _rpc(self, name, payload, *, namespace="budget", max_bytes=8192):
        assert name == "get" and namespace == "result" and max_bytes == 131072
        self.get_calls += 1
        if self.saved is None:
            return {"status": "missing"}
        assert self.saved["key"] in payload["p_keys"]
        return deepcopy(self.saved)

    def reserve(self, *args):
        self.reserve_calls += 1
        pytest.fail("archive/oversize fixture cannot reserve budget")

    def settle(self, *args):
        self.settle_calls += 1
        pytest.fail("archive/oversize fixture cannot settle budget")


def test_raw_pack_get_replay_preserves_old_answer_identity_and_revision():
    doc, answer = _case("APS (Accelrator Pedal Sensor)")
    source = business.prepare_judgment_packet([doc], as_of=AS_OF)["sources"][0]
    literal = business._validate_row(answer["judgments"][0], source, AS_OF)
    assert business.VERSION == "company-business-judgment-v2"
    assert _validate(doc, answer)["judgments"][0] == literal
    safe = business.safe_saved_judgment_answer(answer, [doc], as_of=AS_OF)
    assert safe == answer and safe is not answer and safe["judgments"][0] is not answer["judgments"][0]
    saved = _saved(doc, answer)
    before = deepcopy((doc, answer, saved))
    budget = ReadOnlyBudget(saved)
    restored = archive.SupabaseResultStore(budget).get([saved["key"]])
    replay = archive.replay_result(restored, doc, judgment_as_of=NEXT_DAY)
    assert replay["raw_answer"] == answer and replay["judgments"][0] == literal
    assert replay["status"] == "cached" and replay["original_status"] == "ok"
    assert replay["assessed_as_of"] == AS_OF and replay["fresh_assessment"] is False
    assert replay["provider_calls"] == 0 and replay["published"] is False and _flags(replay)
    assert replay["judgments"][0]["display"] == {"degree": "unrated", "impact": "unknown", "importance": "unrated"}
    assert (doc, answer, saved) == before and budget.get_calls == 1
    assert budget.reserve_calls == budget.settle_calls == 0


def test_v1_archived_judgment_remains_readable_after_v2_prompt_namespace():
    doc, answer = _case("APS (Accelrator Pedal Sensor)")
    _validate(doc, answer)
    legacy_version = "company-business-judgment-v1"
    raw = {"status": "error", "provider": ai.PROVIDER, "model": ai.MODEL,
           "reasoning_effort": ai.REASONING_EFFORT, "assessed_as_of": AS_OF,
           "usage": {"input_tokens": 100, "output_tokens": 30,
                     "thinking_tokens": 0, "cached_input_tokens": 0}, "raw_answer": answer}
    legacy_result = archive.pack_result(raw, doc, legacy_version, 25)
    legacy_key = ai._digest([ai.PROVIDER, ai.MODEL, ai.REASONING_EFFORT, legacy_version, doc])
    restored = {"status": "stored", "key": legacy_key, "document": deepcopy(doc),
                "result": legacy_result}
    budget = ReadOnlyBudget(restored)
    fetched = archive.SupabaseResultStore(budget).get([legacy_key])
    replay = archive.replay_result(fetched, doc, judgment_as_of=NEXT_DAY)
    assert replay["status"] == "cached" and replay["original_status"] == "error"
    assert replay["raw_answer"] == answer and replay["provider_calls"] == 0
    assert budget.get_calls == 1 and budget.reserve_calls == budget.settle_calls == 0
    assert business.VERSION == "company-business-judgment-v2"
    assert business.VERSION != legacy_version


def test_product_flag_reaches_pending_projection_and_blocks_even_complete_accept_receipt():
    doc, answer = _case("APS (Accelrator Pedal Sensor)")
    literal = _validate(doc, answer)["judgments"][0]
    assert literal["review_reasons"] == []  # Acceptance must be blocked by the new quality axis.
    candidate = _candidate(doc, answer)
    before = deepcopy((doc, answer, candidate))
    projection = business.project_company_judgments(answer, [doc], [candidate], [], as_of=AS_OF)
    row = projection["judgments"][0]
    assert row["status"] == "pending" and CODE in row["review_reasons"]
    assert row["degree"] == "unrated" and row["impact"]["direction"] == "unknown"
    with pytest.raises(ValueError, match="^judgment-review-unresolved$"):
        business.project_company_judgments(answer, [doc], [candidate], [_review(literal)], as_of=AS_OF)
    assert (doc, answer, candidate) == before and candidate["status"] == "ai_candidate"


def test_normal_company_review_control_remains_accepted_without_fact_promotion():
    doc, answer = _case("APS (Applied Product Systems)")
    result = _validate(doc, answer)
    assert not result["quality_review"]["findings"]
    candidate = _candidate(doc, answer)
    row = business.project_company_judgments(
        answer, [doc], [candidate], [_review(result["judgments"][0])], as_of=AS_OF)["judgments"][0]
    assert row["status"] == "accepted" and row["degree"] == "medium"
    assert row["impact"]["direction"] == "unknown" and candidate["status"] == "ai_candidate"


def _oversized_case():
    doc, answer = _case()
    extras = [{"id": f"KR:{100001 + index:06d}", "name": "합성거래처" + "가" * 45 + str(index)}
              for index in range(7)]
    prefix = doc["text"] + " " + " ".join(party["name"] for party in extras) + " "
    doc.update(issuer_name="합성발행기업" * 24, text=prefix + "가" * (599 - len(prefix)) + ".",
               counterparties=doc["counterparties"] + extras)
    packet = business.prepare_judgment_packet([doc], as_of=AS_OF)
    answer["judgments"][0]["source_version"] = packet["sources"][0]["source_version"]
    payload = ai._openai_payload(doc)
    payload.update(instructions=business.SYSTEM, input=json.dumps(packet, ensure_ascii=False))
    payload["text"]["format"].update(name="company_judgment", schema=business.SCHEMA)
    assert len(doc["text"]) == 600 and ai.MAX_PROMPT_BYTES == 8000
    assert len(json.dumps(payload, ensure_ascii=False).encode()) > ai.MAX_PROMPT_BYTES
    return doc, answer


@pytest.mark.parametrize("cached", [True, False])
def test_oversized_outbound_payload_allows_free_restore_but_never_a_new_reservation(tmp_path, cached):
    doc, answer = _oversized_case()
    saved = _saved(doc, answer) if cached else None
    before = deepcopy((doc, answer, saved))
    budget = ReadOnlyBudget(saved)
    ledger = tmp_path / "oversized.sqlite3"
    result = ai.run_document(doc, ledger, "synthetic-key", enabled=True, judgment_as_of=NEXT_DAY,
                             budget_ledger=budget, result_store=archive.SupabaseResultStore(budget))
    assert budget.get_calls == 1 and budget.reserve_calls == budget.settle_calls == 0
    if cached:
        assert result["status"] == "cached" and result["raw_answer"] == answer and result["provider_calls"] == 0
        assert result["assessed_as_of"] == AS_OF and result["fresh_assessment"] is False
        assert result["judgments"][0]["display"]["degree"] == "unrated"
    else:
        assert result == {"status": "input-too-large", "candidates": []}
    with sqlite3.connect(ledger) as db:
        assert db.execute("SELECT COUNT(*) FROM calls").fetchone()[0] == 0
    assert (doc, answer, saved) == before
