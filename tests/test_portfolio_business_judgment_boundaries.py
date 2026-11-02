from copy import deepcopy

import pytest

from api.intelligence import portfolio_business_judgment as business


QUOTE = ("당사는 기존의 현대중공업/삼성중공업 향 MARKⅢ 타입 뿐만 아니라 세계최초로 "
         "NO96-SUPER+를 채택한 한화오션을 새로운 고객사로 유치하여 매출 확대로 이어지며 "
         "새로운 성장동력을 확보하였습니다.")
PREFIX = ("당사는 GTT의 멤브레인(Membrane) 타입의 보냉재 생산 인증을 받아 글로벌 LNG운반선을 "
          "건조하는 국내외 조선사에 납품을 하고 있습니다.")


@pytest.mark.parametrize("left,right", [("", ""), (" ", ""), ("", "  "), ("  ", "  ")])
def test_sentence_margins_preserve_literal_quote_and_document(left, right):
    quote = left + QUOTE + right
    source = {"text": PREFIX + "  " + QUOTE + "  다음 문장입니다."}
    before = deepcopy(source)
    business._sentence(quote, source)
    assert quote == left + QUOTE + right
    assert source == before


@pytest.mark.parametrize("quote,text", [
    (" " + QUOTE[:-1], PREFIX + " " + QUOTE),
    (" 새로운 성장동력을 확보하였습니다.", PREFIX + " " + QUOTE),
    (" " + QUOTE + " 다음 문장입니다.", PREFIX + " " + QUOTE + " 다음 문장입니다."),
    (" " + QUOTE + "\n", PREFIX + " " + QUOTE + "\n"),
    (" " + QUOTE, PREFIX + " " + QUOTE + " " + QUOTE),
    (" " + QUOTE, PREFIX + QUOTE),
    (" 고객사에 공급하였습니다.", " 2025년 당사는 조건에 따라 고객사에 공급하였습니다."),
    ("당사는 고객사에 공급하였습니다.", "당사는 고객사에 공급하지 않았습니다."),  # negation
    ("고객사에 공급하였습니다.", "조건 충족 시 고객사에 공급하였습니다."),  # condition
    ("고객사에 공급하였습니다.", "한화오션은 고객사에 공급하였습니다."),  # company
    ("고객사에 공급하였습니다.", "2025년 고객사에 공급하였습니다."),  # period
])
def test_non_margin_changes_remain_rejected(quote, text):
    with pytest.raises(ValueError):
        business._sentence(quote, {"text": text})


def test_retained_proposal_and_evidence_refs_keep_raw_margins():
    source = {"text": PREFIX + " " + QUOTE + "  다음 문장입니다.",
              "issuer_id": "KR:111111", "issuer_name": "합성회사",
              "source_id": "source:synthetic", "source_version": "original-version",
              "as_of": "2026-03-12", "url": "https://example.com",
              "counterparties": [{"id": "KR:222222", "name": "한화오션"}]}
    quote = " " + QUOTE + "  "
    row = {"company_id": source["issuer_id"], "counterparty_id": "KR:222222",
           "source_id": source["source_id"], "source_version": source["source_version"],
           "quote": quote, "scope_quote": None, "period_quote": None,
           "degree": {"value": "unrated", "basis": "unrated", "quote": None},
           "impact": {"direction": "unknown", "channel": "unknown", "condition": None, "quote": None},
           "counter_evidence_quotes": [], "missing_evidence": [],
           "reason": "원문을 검토합니다.", "review_trigger": "별도 검토가 필요합니다."}
    before = deepcopy((source, row))
    result = business._validate_row(row, source, "2026-11-02")
    ref = result["evidence_refs"][0]
    assert result["proposal"] == row
    assert source["text"][ref["start"]:ref["end"]] == quote
    assert (source, row) == before
    assert result["published_on"] == source["as_of"]
