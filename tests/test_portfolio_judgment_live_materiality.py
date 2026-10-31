"""Live-contract plumbing only; synthetic cases do not prove investment quality."""
from copy import deepcopy

import pytest

from api.intelligence import portfolio_ai_fallback as ai
from api.intelligence import portfolio_ai_result_store as archive
from api.intelligence import portfolio_business_judgment as business
from tests.test_portfolio_business_judgment_product_identity import (
    AS_OF, NEXT_DAY, _case, _candidate, _review, _saved, offline,
)


def _economic_case(value="material"):
    doc, answer = _case()
    adjective = "중요한" if value == "material" else "미미한"
    economic = f"당사 전체의 2025년 APS 공급은 매출에 {adjective} 기여를 합니다."
    doc["text"] += " " + economic
    row = answer["judgments"][0]
    row["source_version"] = ai._digest(doc)
    row["economic_v2"] = {"materiality": {
        "value": value, "scope": "company", "scope_quote": "당사 전체",
        "period_quote": "2025년", "quote": economic,
        "mechanism_quote": f"매출에 {adjective} 기여",
    }}
    return doc, answer


def test_live_schema_requests_separate_materiality_without_review_authority():
    item = business.SCHEMA["properties"]["judgments"]["items"]
    assert "economic_v2" in item["required"]
    materiality = item["properties"]["economic_v2"]["properties"]["materiality"]
    assert set(materiality["required"]) == business._MATERIALITY_FIELDS
    assert materiality["additionalProperties"] is False
    assert materiality["properties"]["value"]["enum"] == ["material", "limited", "unrated"]
    assert not {"status", "reviewed_on", "checks", "confidence"} & set(materiality["properties"])
    assert "economic_v2.materiality" in business.SYSTEM
    assert business.CACHE_VERSION != business.LEGACY_CACHE_VERSIONS[0]


@pytest.mark.parametrize("value", ["material", "limited"])
def test_live_materiality_survives_private_archive_but_needs_separate_review(value):
    doc, answer = _economic_case(value)
    before = deepcopy((doc, answer))
    result = business.validate_company_judgments(answer, [doc], as_of=AS_OF)
    assert result["rejected"] == []
    literal = result["judgments"][0]
    assert literal["materiality_review_reasons"] == []
    assert literal["display"]["importance"] == "unrated"
    saved = _saved(doc, answer)
    replay = archive.replay_result(saved, doc, judgment_as_of=NEXT_DAY)
    assert replay["raw_answer"] == answer
    assert replay["assessed_as_of"] == AS_OF and not replay["fresh_assessment"]
    assert replay["provider_calls"] == 0 and not replay["published"]
    # A relationship acceptance is not permission to publish its economic grade.
    review = _review(literal)
    item = business.project_company_judgments(
        answer, [doc], [_candidate(doc, answer)], [review], as_of=AS_OF)["judgments"][0]
    assert item["status"] == "accepted"
    assert item["impact"]["direction"] == "unknown"
    assert item["economic_v2"]["materiality"]["value"] == "unrated"
    review["materiality_review"] = {
        "decision": "accept", "reviewed_on": AS_OF, "reason": "합성 경제적 근거 검수입니다.",
        "checks": {key: True for key in business._MATERIALITY_CHECKS},
    }
    reviewed = business.project_company_judgments(
        answer, [doc], [_candidate(doc, answer)], [review], as_of=AS_OF)["judgments"][0]
    assert reviewed["economic_v2"]["materiality"]["value"] == value
    assert reviewed["impact"]["direction"] == "unknown"
    assert (doc, answer) == before


def test_absent_economic_basis_stays_unknown_not_low_or_positive():
    doc, answer = _case()
    answer["judgments"][0]["economic_v2"] = {"materiality": {
        "value": "unrated", "scope": "unknown", "scope_quote": None,
        "period_quote": None, "quote": None, "mechanism_quote": None,
    }}
    result = business.validate_company_judgments(answer, [doc], as_of=AS_OF)
    assert result["rejected"] == []
    item = business.project_company_judgments(
        answer, [doc], [_candidate(doc, answer)], [], as_of=AS_OF)["judgments"][0]
    assert item["economic_v2"]["materiality"]["value"] == "unrated"
    assert item["impact"]["direction"] == "unknown" and item["status"] == "pending"


def test_v2_archive_remains_readable_without_rewriting_as_a_v3_assessment():
    doc, answer = _case()
    saved = _saved(doc, answer)
    saved["key"] = ai._digest([ai.PROVIDER, ai.MODEL, ai.REASONING_EFFORT,
                               "company-business-judgment-prompt-v2", doc])
    before = deepcopy(saved)
    replay = archive.replay_result(saved, doc, judgment_as_of=NEXT_DAY)
    assert replay["raw_answer"] == answer
    assert "economic_v2" not in replay["raw_answer"]["judgments"][0]
    assert replay["assessed_as_of"] == AS_OF and not replay["fresh_assessment"]
    assert replay["provider_calls"] == 0 and saved == before


@pytest.mark.parametrize("value", ["material", "limited"])
def test_reviewed_economic_sentence_reaches_existing_public_projection(value):
    from api.intelligence import portfolio_ai_public as public
    doc, answer = _economic_case(value)
    proposal = answer["judgments"][0]
    # Public evidence must be on the existing candidate, not silently appended
    # as a second unsupported public statement from a private response.
    doc["text"] = proposal["economic_v2"]["materiality"]["quote"]
    proposal.update(quote=doc["text"], scope_quote="당사 전체",
                    source_version=ai._digest(doc),
                    degree={"value": "unrated", "basis": "unrated", "quote": None})
    literal = business.validate_company_judgments(answer, [doc], as_of=AS_OF)["judgments"][0]
    receipt = _review(literal)
    receipt["materiality_review"] = {
        "decision": "accept", "reviewed_on": AS_OF, "reason": "합성 경제적 근거 검수입니다.",
        "checks": {key: True for key in business._MATERIALITY_CHECKS},
    }
    candidate = _candidate(doc, answer)
    local = business.project_company_judgments(
        answer, [doc], [candidate], [receipt], as_of=AS_OF)
    output = public.project_public_company_judgments(local, [candidate], source_documents=[doc])
    assert len(output["judgments"]) == 1
    item = output["judgments"][0]
    assert item["economic_v2"]["materiality"]["value"] == value
    assert item["economic_v2"]["materiality"]["status"] == "accepted"
    assert item["impact"]["direction"] == "unknown"
    assert public.project_public_company_judgments(output, [candidate]) == output


@pytest.mark.parametrize("direction,mechanism", [
    ("positive", "APS 공급 매출이 증가했습니다"),
    ("negative", "APS 공급 매출이 감소했습니다"),
    ("mixed", "APS 공급 매출이 국내에서는 증가하고 해외에서는 감소했습니다"),
])
def test_supported_direction_can_reach_public_without_inventing_materiality(direction, mechanism):
    from api.intelligence import portfolio_ai_public as public
    doc, answer = _case()
    doc["text"] = f"당사는 2025년 {mechanism}."
    proposal = answer["judgments"][0]
    proposal.update(
        quote=doc["text"], source_version=ai._digest(doc), scope_quote="당사",
        degree={"value": "unrated", "basis": "unrated", "quote": None},
        impact={"direction": direction, "channel": "revenue", "quote": mechanism,
                "condition": "해당 보고기간과 납품 매출 범위에 한정합니다."},
        economic_v2={"materiality": {"value": "unrated", "scope": "unknown",
                     "scope_quote": None, "period_quote": None, "quote": None,
                     "mechanism_quote": None}},
    )
    result = business.validate_company_judgments(answer, [doc], as_of=AS_OF)
    assert result["rejected"] == [] and result["quality_review"]["findings"] == []
    candidate = _candidate(doc, answer)
    pending = business.project_company_judgments(answer, [doc], [candidate], [], as_of=AS_OF)
    assert pending["judgments"][0]["impact"]["direction"] == "unknown"
    reviewed = business.project_company_judgments(
        answer, [doc], [candidate], [_review(result["judgments"][0])], as_of=AS_OF)
    output = public.project_public_company_judgments(reviewed, [candidate], source_documents=[doc])
    assert len(output["judgments"]) == 1
    assert output["judgments"][0]["impact"]["direction"] == direction
    assert output["judgments"][0]["economic_v2"]["materiality"]["value"] == "unrated"
    assert candidate["status"] == "ai_candidate"
