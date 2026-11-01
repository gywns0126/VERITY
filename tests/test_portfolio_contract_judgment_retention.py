"""Offline export retention of synthetic, already-reviewed public contract rows."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import socket
import urllib.request

import pytest

from api.intelligence import portfolio_ai_fallback as ai
from api.intelligence import portfolio_ai_public as public
from api.intelligence import portfolio_business_judgment as business
from tests.test_portfolio_contract_facts import _body, _parse


AS_OF = "2026-10-10"
JUDGMENT_SCHEMA = "local-company-judgments-v1"


@pytest.fixture(autouse=True)
def _isolate_data_dir(monkeypatch):
    # Replace the unrelated account fixture; all inputs below are synthetic.
    def denied(*args, **kwargs):
        raise AssertionError("contract retention must stay offline")
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(urllib.request, "urlopen", denied)
    monkeypatch.setattr(ai, "run_document", denied)
    monkeypatch.setattr(ai, "openai_transport", denied)
    monkeypatch.setattr(ai.sqlite3, "connect", denied)
    monkeypatch.setattr(public, "_kr_contract_today", lambda: AS_OF)


def _write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def _contract_fact():
    financial = ("<tr><td>2. 계약내역</td><td>계약금액(원)</td><td>100</td></tr>"
                 "<tr><td>최근매출액(원)</td><td>200</td></tr>"
                 "<tr><td>매출액 대비(%)</td><td>50</td></tr>")
    raw = _body(correction=False, financial_rows=financial).decode("euc-kr")
    raw = raw.replace("<td>-</td>", "<td>설비 공급 신규 계약</td>", 1)
    raw = raw.replace("글로벌 발주처", "Synthetic A").replace("2030-01-01", "2026-01-01")
    notes = "상기2. 계약내역의 최근매출액은 2025년 별도재무제표 기준임."
    raw = raw.replace("</table><script>", "<tr><td>10. 기타 투자판단에 참고할 사항</td></tr>"
                      f"<tr><td>{notes}</td></tr></table><script>")
    return _parse(raw.encode("euc-kr"))


def _reviewed_contract(event, fact):
    """Synthetic receipt fixture, never an operator approval or production writer."""
    contract = fact["contract"]
    revision = public._contract_event_revision(event)
    fact_revision = public._digest(fact)
    proof = {"basis": "contract-announcement", "event_revision": revision,
             "source_receipt": fact["receipt_no"], "body_sha256": fact["source"]["content_sha256"],
             "fact_revision": fact_revision, "checked_on": AS_OF,
             "effective_start": "2026-01-01", "effective_end": "2050-12-31",
             "review_scope": "provided-contract-family-only", "materiality": "material",
             "change_kind": "new-contract", "facts": {"contract": deepcopy(contract), "correction": None},
             "reason": "합성 검수 근거", "denominator": {
                 "year": 2025, "scope": "separate", "quote": contract["financial_notes"]["value"]}}
    row = {"record_id": event["id"], "base_read_revision": int(revision[:13], 16) + 1,
           "company_id": fact["issuer"]["id"], "counterparty_id": "KR:222222",
           "source_id": "source:dart:" + fact["receipt_no"], "source_url": fact["source"]["main_url"],
           "source_version": fact_revision, "published_on": fact["filing"]["filed_on"],
           "quote": contract["name"]["value"], "scope_quote": contract["name"]["value"],
           "period_quote": "2026-01-01 ~ 2050-12-31", "status": "accepted", "reviewed_on": AS_OF,
           "review_reason": "합성 검수 기록", "degree": "unrated",
           "impact": {"direction": "unknown", "channel": "unknown", "condition": None},
           "reason": "합성 계약 규모 근거", "review_trigger": "새 원문 확인 시 재검토",
           "missing_evidence": ["counter_evidence_not_searched"], "review_reasons": [],
           "core_selection": proof, "revision": "a" * 64, "read_revision": 1}
    row["read_revision"] = int(row["revision"][:13], 16) + 1
    row["comparison"] = {"status": "first", "unavailable_reason": None,
                         "changed_fields": [], "review_changed_fields": [], "previous": None,
                         "current": {"source_version": fact_revision, "judgment_revision": "b" * 64,
                                     "review_revision": row["revision"], "assessed_as_of": AS_OF,
                                     "reviewed_on": AS_OF, "reason": row["reason"],
                                     "review_reason": row["review_reason"]}}
    public._public_contract_judgment(row, {event["id"]: event}, {fact["receipt_no"]: fact})
    projected = public.project_public_company_judgments(
        {"schema": JUDGMENT_SCHEMA, "judgments": [row]}, [],
        contract_events={"events": {event["id"]: event}}, contract_sources={fact["receipt_no"]: fact})
    assert len(projected["judgments"]) == 1
    return projected["judgments"][0]


@pytest.fixture
def retention_case(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("contract_retention_exporter",
        root / "scripts/member-map/export-ai-candidates.py")
    exporter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(exporter)
    fact = _contract_fact()
    document = {"id": "DART:" + fact["receipt_no"], "url": fact["source"]["main_url"],
                "title": fact["filing"]["title"], "as_of": fact["filing"]["filed_on"],
                "source": "DART", "kind": "disclosure"}
    catalog = [{"id": fact["issuer"]["id"], "name": fact["issuer"]["name"],
                "market": "KR", "ticker": "028050", "documents": [document]},
               {"id": "KR:111111", "name": "Synthetic Issuer", "market": "KR", "ticker": "111111"},
               {"id": "KR:222222", "name": "Synthetic A", "market": "KR", "ticker": "222222"}]
    sources = {"member_map_auto_evidence.json": {"contract_facts": [fact]}}
    monkeypatch.setattr(exporter, "load_public_sources", lambda _: sources)
    monkeypatch.setattr(exporter, "project_public_sources", lambda _: {"companies": catalog})
    source_dir = tmp_path / "public"
    source_dir.mkdir()
    quote = "당사는 2025년 Synthetic A에 부품을 공급하며, Synthetic A는 당사의 주요 매출처입니다."
    doc = {"source_id": "source:dart:20260312000001", "issuer_id": "KR:111111",
           "issuer_name": "Synthetic Issuer", "as_of": "2026-03-12",
           "url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260312000001", "text": quote,
           "counterparties": [{"id": "KR:222222", "name": "Synthetic A"}]}
    proposal = {"company_id": doc["issuer_id"], "counterparty_id": "KR:222222",
                "source_id": doc["source_id"], "source_version": public._digest(doc), "quote": quote,
                "scope_quote": "당사의 주요 매출처", "period_quote": "2025년",
                "degree": {"value": "medium", "basis": "reported_qualitative", "quote": "주요 매출처"},
                "impact": {"direction": "unknown", "channel": "unknown", "condition": None, "quote": None},
                "counter_evidence_quotes": [], "missing_evidence": [],
                "reason": "합성 원문 범위", "review_trigger": "새 원문 확인 시 재검토"}
    answer = {"judgments": [proposal], "remaining_count": 0}
    literal = business.validate_company_judgments(answer, [doc], as_of=AS_OF)["judgments"][0]
    receipt = {"judgment_id": literal["id"], "judgment_revision": literal["revision"],
               "decision": "accept", "reviewed_on": AS_OF, "reason": "합성 검수 기록",
               "checks": {key: True for key in ("company_scope", "period", "degree_support",
                          "impact_mechanism", "counter_evidence", "source_context")}}
    incoming, raw, reviews = (tmp_path / name for name in ("incoming.json", "answer.json", "reviews.json"))
    _write(incoming, {"schema": "local-ai-review-input-v1", "entries": [{"document": doc,
           "answer": {"candidates": [{"counterparty_id": "KR:222222", "role": "customer", "quote": quote}]}}]})
    _write(raw, {"documents": [doc], "answer": answer})
    _write(reviews, [receipt])
    output = tmp_path / "member_map_ai_candidates.json"
    exporter.export_candidates(incoming, source_dir, output, judgment_input=raw,
                               judgment_reviews=reviews, judgment_as_of=AS_OF)
    baseline = json.loads(output.read_bytes())
    assert len(baseline["company_judgments"]["judgments"]) == 1
    _, events, _ = exporter._contract_context(sources, catalog)
    contract_row = _reviewed_contract(next(iter(events["events"].values())), fact)
    baseline["company_judgments"]["judgments"].append(contract_row)
    previous = tmp_path / "previous-public.json"
    _write(previous, baseline)
    return {"exporter": exporter, "sources": sources, "catalog": catalog, "fact": fact,
            "baseline": baseline, "contract_row": contract_row, "incoming": incoming,
            "source_dir": source_dir, "output": output, "previous": previous}


def _retain(case):
    result = case["exporter"].export_candidates(case["incoming"], case["source_dir"], case["output"],
        retained_public_judgments=case["previous"])
    assert result["network_calls"] == 0 and result["published"] is False
    return json.loads(case["output"].read_bytes())


def test_retains_exact_reviewed_contract_and_legacy_row(retention_case):
    case = retention_case
    before = case["previous"].read_bytes(), case["incoming"].read_bytes(), deepcopy(case["sources"])
    assert case["contract_row"]["record_id"] not in {c["id"] for c in case["baseline"]["candidates"]}
    assert _retain(case) == case["baseline"]
    assert (case["previous"].read_bytes(), case["incoming"].read_bytes(), case["sources"]) == before


@pytest.mark.parametrize("change", ["body-hash", "amount", "period", "party", "missing-fact",
                                  "correction", "termination"])
def test_withdraws_stale_contract_without_losing_legacy(retention_case, change):
    case = retention_case
    fact = case["fact"]
    if change == "body-hash":
        fact["source"]["content_sha256"] = "f" * 64
    elif change == "amount":
        fact["contract"]["financial_terms"]["amount"]["value"] = "101"
    elif change == "period":
        fact["contract"]["period"]["end"]["value"] = "2051-12-31"
    elif change == "party":
        fact["contract"]["counterparty"]["value"] = "미확인 상대방"
    elif change == "missing-fact":
        case["sources"]["member_map_auto_evidence.json"]["contract_facts"] = []
    elif change == "correction":
        amended = deepcopy(fact)
        amended["receipt_no"] = "20261001800001"
        amended["filing"]["filed_on"] = "2026-10-01"
        for key in ("main_url", "viewer_url"):
            amended["source"][key] = amended["source"][key].replace(fact["receipt_no"], amended["receipt_no"])
        amended["contract"]["financial_terms"]["amount"]["value"] = "101"
        amended["correction"] = {
            "corrected_on": {"label": "정정일자", "value": "2026-10-01"},
            "related_filing_date": {"label": "정정관련 공시서류제출일", "value": "2026-09-30"},
            "reason": {"label": "정정사유", "value": "계약금액 정정"},
            "changes": [{"field": "계약금액", "before": "100", "after": "101"}]}
        evidence = case["sources"]["member_map_auto_evidence.json"]
        evidence["contract_facts"].append(amended)
        title = "[기재정정]" + fact["filing"]["title"]
        case["catalog"][0]["documents"].append({
            "id": "DART:" + amended["receipt_no"], "url": amended["source"]["main_url"],
            "title": title, "as_of": "2026-10-01", "source": "DART", "kind": "disclosure"})
        evidence["documentFamilies"] = [{
            "issuer_id": fact["issuer"]["id"], "issuer_name": fact["issuer"]["name"],
            "corp_code": "00000001", "receipt_no": amended["receipt_no"],
            "url": amended["source"]["main_url"], "observed_at": fact["source"]["observed_at"],
            "content_sha256": "e" * 64, "members": [
                {"receipt_no": fact["receipt_no"], "title": fact["filing"]["title"],
                 "published_on": fact["filing"]["filed_on"], "amendment": False},
                {"receipt_no": amended["receipt_no"], "title": title,
                 "published_on": "2026-10-01", "amendment": True}]}]
        _, events, _ = case["exporter"]._contract_context(case["sources"], case["catalog"])
        assert len(next(iter(events["events"].values()))["documents"]) == 2
    else:
        from tests.test_portfolio_contract_termination import _body as notice_body, _parse as parse_notice
        receipt = "20261001800002"
        raw = notice_body(issuer=fact["issuer"]["name"], links=[
            ("2026-09-30 " + fact["filing"]["title"],
             fact["source"]["main_url"].removeprefix("https://dart.fss.or.kr"))])
        raw = raw.decode("euc-kr").replace("2026.09.29", "2026.10.01").replace("2026-09-29", "2026-10-01")
        notice = parse_notice(raw.encode("euc-kr"), receipt_no=receipt,
            issuer_id=fact["issuer"]["id"], issuer_name=fact["issuer"]["name"],
            expected_source_issuer_name=fact["issuer"]["name"], filed_on="2026-10-01",
            main_url=fact["source"]["main_url"].replace(fact["receipt_no"], receipt),
            viewer_url=fact["source"]["viewer_url"].replace(fact["receipt_no"], receipt))
        case["sources"]["member_map_auto_evidence.json"]["contract_terminations"] = [notice]
        case["catalog"][0]["documents"].append({
            "id": "DART:" + receipt, "url": notice["source"]["main_url"], "title": notice["filing_title"],
            "as_of": notice["as_of"], "source": "DART", "kind": "disclosure"})
        _, events, _ = case["exporter"]._contract_context(case["sources"], case["catalog"])
        assert events["coverage"]["linked_termination_notices"] == 1
    actual = _retain(case)
    assert actual["company_judgments"]["judgments"] == case["baseline"]["company_judgments"]["judgments"][:1]
    assert actual["candidates"] == case["baseline"]["candidates"]
    assert actual["coverage"] == case["baseline"]["coverage"]


def test_legacy_only_retention_stays_exact(retention_case):
    case = retention_case
    baseline = deepcopy(case["baseline"])
    baseline["company_judgments"]["judgments"].pop()
    _write(case["previous"], baseline)
    case["sources"].clear()
    assert _retain(case) == baseline


@pytest.mark.parametrize("change", ["positive-impact", "revision"])
def test_never_repairs_or_approves_tampered_public_contract(retention_case, change):
    case = retention_case
    prior = deepcopy(case["baseline"])
    row = prior["company_judgments"]["judgments"][-1]
    if change == "positive-impact":
        row["impact"] = {"direction": "positive", "channel": "revenue", "condition": "임의 조건"}
    else:
        row["revision"] = "f" * 64
        row["read_revision"] = int(row["revision"][:13], 16) + 1
    _write(case["previous"], prior)
    assert _retain(case)["company_judgments"]["judgments"] == prior["company_judgments"]["judgments"][:1]


def test_duplicate_canonical_receipt_rejects_without_replacing_output(retention_case):
    case = retention_case
    case["sources"]["member_map_auto_evidence.json"]["contract_facts"].append(deepcopy(case["fact"]))
    before = case["output"].read_bytes()
    with pytest.raises(ValueError, match="^duplicate-contract-review-source$"):
        _retain(case)
    assert case["output"].read_bytes() == before


def test_four_public_files_restore_captured_contract_through_export_and_validation(retention_case, tmp_path):
    case = retention_case
    source_dir = case["source_dir"]
    _write(source_dir / "universe_search.json", {"stocks": [
        {key: row[key] for key in ("ticker", "market", "name")} for row in case["catalog"]]})
    _write(source_dir / "public_disclosure_feed.json", {"items": []})
    _write(source_dir / "member_map_auto_evidence.json", case["sources"]["member_map_auto_evidence.json"])
    _write(source_dir / "member_map_ai_candidates.json", case["baseline"])
    _write(case["incoming"], {"schema": "local-ai-review-input-v1", "entries": []})
    before = {p.name: p.read_bytes() for p in source_dir.iterdir()}
    result = case["exporter"].export_candidates(case["incoming"], source_dir, case["output"],
        retained_public_judgments=source_dir / "member_map_ai_candidates.json")
    actual = json.loads(case["output"].read_bytes())
    assert result["network_calls"] == 0 and result["published"] is False
    assert actual["candidates"] == []  # Isolate contracts from AI-candidate bindings.
    assert actual["company_judgments"]["judgments"] == [case["contract_row"]]
    spec = importlib.util.spec_from_file_location("contract_retention_public_validator",
        Path(case["exporter"].__file__).with_name("validate-public-ai-artifact.py"))
    validator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(validator)
    destination = tmp_path / "validated" / "member_map_ai_candidates.json"
    destination.parent.mkdir()
    body = case["output"].read_bytes()
    validation = validator.validate(case["output"], hashlib.sha256(body).hexdigest(), source_dir, destination)
    assert validation["network_calls"] == 0 and destination.read_bytes() == body
    assert {p.name: p.read_bytes() for p in source_dir.iterdir()} == before


@pytest.mark.parametrize("collision", [False, True])
def test_registered_report_alias_only_restores_unambiguous_captured_issuer(retention_case, collision):
    case = retention_case
    case["catalog"][0].update(name="Registered Display Name", documents=[])
    report = {"028050": {"ticker": "028050", "market": "KR", "name": case["fact"]["issuer"]["name"]}}
    if collision:
        report["111111"] = {"ticker": "111111", "market": "KR", "name": case["fact"]["issuer"]["name"]}
    case["sources"]["stock_report_public.json"] = {"stocks": report}
    before = deepcopy(case["catalog"]), deepcopy(case["sources"])
    actual = _retain(case)
    expected = case["baseline"]["company_judgments"]["judgments"][:1] if collision else case["baseline"]["company_judgments"]["judgments"]
    assert actual["company_judgments"]["judgments"] == expected
    assert (case["catalog"], case["sources"]) == before
