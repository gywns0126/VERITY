"""Offline evidence binding regressions; no claims of investment accuracy."""
from copy import deepcopy
from io import BytesIO
from pathlib import Path
import importlib
import socket
import urllib.request
import zipfile

import pytest

from api.intelligence import portfolio_ai_fallback as ai
from api.intelligence import portfolio_business_judgment as business
from api.intelligence import portfolio_reported_period as period
from tests.test_portfolio_business_judgment_product_identity import (
    AS_OF, _case, _candidate, _review,
)
from tests.test_portfolio_reported_period import (
    REGISTRY, SOURCE_ID, _source, _zip,
)


@pytest.fixture(autouse=True)
def _isolate_data_dir(monkeypatch):
    # Pure synthetic inputs: override the unrelated account/trading fixture.
    def denied(*args, **kwargs):
        raise AssertionError("evidence revision tests cannot use network or providers")
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(urllib.request, "urlopen", denied)
    monkeypatch.setattr(ai, "run_document", denied)
    monkeypatch.setattr(ai, "openai_transport", denied)
    monkeypatch.setattr(ai, "google_transport", denied)


def _validate(doc, answer, **kwargs):
    result = business.validate_company_judgments(answer, [doc], as_of=AS_OF, **kwargs)
    assert result["rejected"] == []
    assert len(result["judgments"]) == 1
    return result


def _project(doc, answer, reviews=(), **kwargs):
    return business.project_company_judgments(
        answer, [doc], [_candidate(doc, answer)], list(reviews), as_of=AS_OF, **kwargs)


def _impact_case(support, quote=None):
    doc, answer = _case()
    quote = quote or ("당사는 2025년 APS와 거래하며 당사의 전체 매출이 8,837억원 증가했고, "
                      "APS 공급 매출이 10억원 증가했습니다.")
    doc["text"] = quote
    row = answer["judgments"][0]
    row.update(quote=quote, scope_quote="당사", source_version=business._digest(doc),
               degree={"value": "unrated", "basis": "unrated", "quote": None},
               impact={"direction": "positive", "channel": "revenue",
                       "condition": "해당 거래의 증가가 유지되는 경우입니다.", "quote": support})
    return doc, answer


def test_cited_issuer_growth_cannot_borrow_an_uncited_party_mechanism():
    doc, answer = _impact_case("당사의 전체 매출이 8,837억원 증가")
    before = deepcopy((doc, answer))
    result = _validate(doc, answer)
    literal = result["judgments"][0]
    assert literal["review_reasons"] == []  # Keep the archived literal row intact.
    assert "impact-party-attribution" in {
        f["code"] for f in result["quality_review"]["findings"]}
    pending = _project(doc, answer)["judgments"][0]
    assert pending["impact"]["direction"] == "unknown"
    assert "impact-party-attribution" in pending["review_reasons"]
    with pytest.raises(ValueError, match="^judgment-review-unresolved$"):
        _project(doc, answer, [_review(literal)])
    assert (doc, answer) == before


@pytest.mark.parametrize("support", [
    "APS 공급 매출이 10억원 증가", "매출이 10억원 증가",
])
def test_cited_party_growth_remains_reviewable(support):
    doc, answer = _impact_case(support)
    result = _validate(doc, answer)
    assert result["quality_review"]["findings"] == []
    item = _project(doc, answer, [_review(result["judgments"][0])])["judgments"][0]
    assert item["status"] == "accepted" and item["impact"]["direction"] == "positive"


@pytest.mark.parametrize("separator", [",", "，", ";", "；"])
def test_repeated_mechanism_requires_a_party_specific_span(separator):
    quote = (f"당사는 2025년 APS 공급으로 매출이 10억원 증가했고{separator} "
             "다른 거래로 매출이 10억원 증가했습니다.")
    doc, answer = _impact_case("매출이 10억원 증가", quote)
    literal = _validate(doc, answer)["judgments"][0]
    with pytest.raises(ValueError, match="^judgment-review-unresolved$"):
        _project(doc, answer, [_review(literal)])
    answer["judgments"][0]["impact"]["quote"] = "APS 공급으로 매출이 10억원 증가"
    corrected = _validate(doc, answer)["judgments"][0]
    assert corrected["revision"] != literal["revision"]
    with pytest.raises(ValueError, match="^judgment-review-version$"):
        _project(doc, answer, [_review(literal)])
    assert _project(doc, answer, [_review(corrected)])["judgments"][0]["status"] == "accepted"


def test_explicit_adjacent_transaction_and_thousands_separator_remain_reviewable():
    quote = "당사는 2025년 APS에 부품을 공급하며, 해당 거래 매출이 8,837억원 증가했습니다."
    doc, answer = _impact_case("해당 거래 매출이 8,837억원 증가", quote)
    result = _validate(doc, answer)
    assert result["quality_review"]["findings"] == []
    assert _project(doc, answer, [_review(result["judgments"][0])])["judgments"][0]["status"] == "accepted"


def _materiality_case(*, product=False):
    doc, answer = _case("APS (Accelrator Pedal Sensor)" if product else None)
    economic = "당사 전체의 2025년 APS 공급은 매출에 중요한 기여를 합니다."
    doc["text"] += " " + economic
    row = answer["judgments"][0]
    row["source_version"] = business._digest(doc)
    row["economic_v2"] = {"materiality": {
        "value": "material", "scope": "company", "scope_quote": "당사 전체",
        "period_quote": "2025년", "quote": economic, "mechanism_quote": "매출에 중요한 기여",
    }}
    result = _validate(doc, answer)
    literal = result["judgments"][0]
    assert literal["materiality_review_reasons"] == []
    review = _review(literal)
    review["decision"] = "hold"
    review["materiality_review"] = {
        "decision": "accept", "reviewed_on": AS_OF, "reason": "합성 중요도 검수입니다.",
        "checks": {k: True for k in business._MATERIALITY_CHECKS},
    }
    return doc, answer, review


def test_separate_materiality_acceptance_cannot_bypass_product_identity_blocker():
    doc, answer, review = _materiality_case(product=True)
    before = deepcopy((doc, answer, review))
    with pytest.raises(ValueError, match="^judgment-materiality-unresolved$"):
        _project(doc, answer, [review])
    assert (doc, answer, review) == before


def test_separate_materiality_review_remains_valid_when_relation_is_held_without_identity_blocker():
    doc, answer, review = _materiality_case()
    item = _project(doc, answer, [review])["judgments"][0]
    assert item["status"] == "held" and item["degree"] == "unrated"
    assert item["economic_v2"]["materiality"]["status"] == "accepted"


def test_impact_only_blocker_does_not_couple_independent_materiality_review():
    doc, answer, review = _materiality_case()
    answer["judgments"][0]["impact"] = {
        "direction": "positive", "channel": "revenue", "quote": "주요 매출처",
        "condition": "거래가 유지되는 경우입니다.",
    }
    result = _validate(doc, answer)
    assert {f["code"] for f in result["quality_review"]["findings"]} == {"impact-mechanism-missing"}
    review["judgment_revision"] = result["judgments"][0]["revision"]
    item = _project(doc, answer, [review])["judgments"][0]
    assert item["status"] == "held" and item["impact"]["direction"] == "unknown"
    assert item["economic_v2"]["materiality"]["status"] == "accepted"


@pytest.mark.parametrize("change", ["text", "issuer_name", "party_name", "resolved_relations"])
def test_same_day_source_changes_invalidate_both_proposal_and_old_review(change):
    doc, answer = _case()
    original = deepcopy((doc, answer))
    old = _validate(doc, answer)["judgments"][0]
    review = _review(old)
    accepted = _project(doc, answer, [review])["judgments"][0]
    if change == "text":
        doc["text"] += " 추가 공시 문맥입니다."
    elif change == "issuer_name":
        doc["issuer_name"] = "Synthetic Renamed Issuer"
    elif change == "party_name":
        doc["counterparties"][0]["name"] = "Other Party"
        doc["text"] += " Other Party에 관한 문맥입니다."
    else:
        doc["resolved_relations"] = [{"counterparty_id": "KR:222222", "role": "customer"}]
    rejected = business.validate_company_judgments(answer, [doc], as_of=AS_OF)
    assert rejected["judgments"] == []
    assert rejected["rejected"] == [{"index": 0, "reason": "judgment-company-or-version"}]
    answer["judgments"][0]["source_version"] = business._digest(doc)
    if change == "party_name":
        rejected = business.validate_company_judgments(answer, [doc], as_of=AS_OF)
        assert rejected["rejected"] == [{"index": 0, "reason": "judgment-counterparty"}]
    else:
        new = _validate(doc, answer)["judgments"][0]
        assert new["id"] == old["id"] and new["revision"] != old["revision"]
        assert "source_version" in business.compare_company_judgments(old, new)["changed_fields"]
        with pytest.raises(ValueError, match="^judgment-review-version$"):
            _project(doc, answer, [review])
        pending = _project(doc, answer)["judgments"][0]
        assert pending["status"] == "pending" and pending["degree"] == "unrated"
        assert pending["read_revision"] != accepted["read_revision"]
    # Original inputs/receipts remain usable; no migration or destructive withdrawal.
    assert _project(*original, [review])["judgments"][0] == accepted


def test_assessment_day_alone_does_not_invalidate_review_or_candidate():
    doc, answer = _case()
    candidate = _candidate(doc, answer)
    before = deepcopy((doc, answer, candidate))
    literal = _validate(doc, answer)["judgments"][0]
    review = _review(literal)
    old = _project(doc, answer, [review])
    new = business.project_company_judgments(
        answer, [doc], [candidate], [review], as_of="2026-10-11")
    assert new == old and (doc, answer, candidate) == before
    assert candidate["status"] == "ai_candidate"


def _period_case():
    doc = _source()
    row = _case()[1]["judgments"][0]
    row.update(company_id=doc["issuer_id"], counterparty_id=doc["counterparties"][0]["id"],
               source_id=doc["source_id"], source_version=business._digest(doc), quote=doc["text"],
               scope_quote="당사의 항공사업", missing_evidence=["denominator"],
               degree={"value": "medium", "basis": "reported_qualitative", "quote": "주요 고객"})
    archive = _zip()
    row["period_context_v3"] = period.build_reported_customer_period(
        doc, row, archives={SOURCE_ID: archive}, issuer_registry=REGISTRY)
    return doc, {"judgments": [row], "remaining_count": 0}, archive


@pytest.mark.parametrize("change", ["issuer", "period", "form", "amendment", "amount", "denominator"])
def test_original_filing_changes_cannot_reuse_period_witness(change):
    doc, answer, archive = _period_case()
    result = _validate(doc, answer, period_archives={SOURCE_ID: archive}, issuer_registry=REGISTRY)
    assert result["judgments"][0]["proposal"]["degree"]["value"] == "medium"
    assert "denominator" in result["judgments"][0]["missing_evidence"]
    before = deepcopy((doc, answer))
    with zipfile.ZipFile(BytesIO(archive)) as zipped:
        member = zipped.namelist()[0]
        xml = zipped.read(member).decode()
    old, new = {
        "issuer": ('AREGCIK="01101254"', 'AREGCIK="00000000"'),
        "period": ('AUNITVALUE="20251231"', 'AUNITVALUE="20241231"'),
        "form": ('ACODE="11011"', 'ACODE="11013"'),
        "amendment": (">사업보고서</DOCUMENT-NAME>", ">[기재정정]사업보고서</DOCUMENT-NAME>"),
        "amount": ("18,925", "19,925"),
        "denominator": ("9,246", "99,246"),
    }[change]
    assert old in xml
    changed = BytesIO()
    with zipfile.ZipFile(changed, "w", compression=zipfile.ZIP_DEFLATED) as zipped:
        zipped.writestr(member, xml.replace(old, new).encode())
    result = business.validate_company_judgments(
        answer, [doc], as_of=AS_OF, period_archives={SOURCE_ID: changed.getvalue()},
        issuer_registry=REGISTRY)
    assert result["judgments"] == [] and len(result["rejected"]) == 1
    assert (doc, answer) == before


def test_amount_and_share_do_not_supply_a_qualitative_degree_or_company_materiality():
    doc, answer = _case()
    quote = "당사는 2025년 APS에 100억원을 공급하며 이는 국내 제품 매출의 87%입니다."
    doc["text"] = quote
    row = answer["judgments"][0]
    row.update(quote=quote, scope_quote="국내 제품 매출", source_version=business._digest(doc),
               degree={"value": "high", "basis": "reported_qualitative", "quote": "87%"})
    result = _validate(doc, answer)
    literal = result["judgments"][0]
    assert "qualitative-degree-support" in literal["review_reasons"]
    assert literal["display"]["importance"] == "unrated"
    with pytest.raises(ValueError, match="^judgment-review-unresolved$"):
        _project(doc, answer, [_review(literal)])


@pytest.mark.parametrize("valid", [True, False])
def test_new_export_reaches_actual_deployed_projection_without_business_judgment_mirror(monkeypatch, valid):
    from api.intelligence import portfolio_ai_public as public
    root = Path(__file__).resolve().parents[1]
    monkeypatch.syspath_prepend(str(root / "vercel-api/api"))
    deployed = importlib.import_module("portfolio_core.portfolio_ai_public")
    assert Path(deployed.__file__).resolve() == root / "vercel-api/api/portfolio_core/portfolio_ai_public.py"
    support = "APS 공급 매출이 10억원 증가" if valid else "당사의 전체 매출이 8,837억원 증가"
    doc, answer = _impact_case(support)
    candidate = _candidate(doc, answer)
    reviews = [_review(_validate(doc, answer)["judgments"][0])] if valid else []
    local = _project(doc, answer, reviews)
    prepared = public.project_public_company_judgments(local, [candidate], source_documents=[doc])
    assert len(prepared["judgments"]) == 1
    artifact = {"schema": "local-ai-review-v1", "candidates": [candidate],
                "coverage": {"input": 1, "accepted": 1, "rejected": 0, "skipped": 0},
                "company_judgments": prepared}
    catalog = [{"market": "KR", "ticker": "111111", "name": doc["issuer_name"]},
               {"market": "KR", "ticker": "222222", "name": "APS"}]
    delivered = deployed.project_public_ai_review(artifact, catalog, [doc["issuer_id"]])
    assert delivered["company_judgments"] == prepared and delivered["candidates"] == [candidate]
    item = delivered["company_judgments"]["judgments"][0]
    assert item["status"] == ("accepted" if valid else "pending")
    assert item["impact"]["direction"] == ("positive" if valid else "unknown")
    assert ("impact-party-attribution" in item["review_reasons"]) is (not valid)
